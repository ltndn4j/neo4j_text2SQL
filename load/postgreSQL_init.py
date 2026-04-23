import os
import psycopg2
from dotenv import load_dotenv
import requests
import bz2
import re
import io

load_dotenv(override=True)

DOMAIN = "@semantictech.com"

def createDB(initialize: bool = False):
    print("Connecting to PostgreSQL database....")
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DATABASE") or "postgres",
        user=os.getenv("POSTGRES_USERNAME"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT") or 5432,
    )
    conn.autocommit = False
    try:
        #Initialize the database
        if initialize or input("Do you want to drop all the PostgreSQL database before creating it (y/n) ? ") == "y":
            DROP_ALL = """
            DROP SCHEMA IF EXISTS employees CASCADE;
            DROP SCHEMA IF EXISTS payroll CASCADE;
            DROP SCHEMA IF EXISTS recruitment CASCADE;
            DROP SCHEMA IF EXISTS training CASCADE;
            DROP SCHEMA IF EXISTS benefits CASCADE;
            DROP SCHEMA IF EXISTS assets CASCADE;
            DROP SCHEMA IF EXISTS compliance CASCADE;
            DROP SCHEMA IF EXISTS timekeeping CASCADE;
            DROP SCHEMA IF EXISTS org CASCADE;
            DROP SCHEMA IF EXISTS projects CASCADE;
            DROP SCHEMA IF EXISTS expenses CASCADE;
            DROP SCHEMA IF EXISTS performance CASCADE;
            DROP SCHEMA IF EXISTS leave_mgmt CASCADE;
            DROP SCHEMA IF EXISTS vendors CASCADE;
            DROP SCHEMA IF EXISTS skills CASCADE;
            DROP SCHEMA IF EXISTS documents CASCADE;
            DROP SCHEMA IF EXISTS onboarding CASCADE;
            DROP SCHEMA IF EXISTS announcements CASCADE;
            """
            url = "https://raw.githubusercontent.com/h8/employees-database/refs/heads/master/employees_data.sql.bz2"
            print("Downloading database data from GitHub....")
            response = requests.get(url)
            response.raise_for_status()
            sql_file = bz2.decompress(response.content).decode('utf-8')

            #Split the file into the initial SQL and the copy statements to load with python instead of psql 
            first_copy_index = sql_file.find('COPY')
            initialSQL = sql_file[:first_copy_index]
            copy_blocks = sql_file[first_copy_index:]
            with conn.cursor() as cur:
                #Drop all the schemas
                print("Dropping all the target schemas if exists....")
                cur.execute(DROP_ALL)
                
                #Load the initial SQL
                print("Loading data in the database....")
                cur.execute(initialSQL)
                #Load all the copy statements with python instead of psql
                parts = re.split(r'\n\\\.\n', copy_blocks)
                for part in parts[:-1]:
                    copy_block = part[part.find('COPY'):]
                    copy_statement = copy_block.split('\n')[0]
                    raw_data = '\n'.join(copy_block.split('\n')[1:])
                    cur.copy_expert(copy_statement, io.StringIO(raw_data))
                #Load the last SQL part
                cur.execute(parts[-1])
                
                #Commit the changes
                conn.commit()
            print("Database backup restored successfully.")

        with conn.cursor() as cur:
            if initialize or input("Do you want to refresh the email of the employees (y/n) ? ") == "y":
                cur.execute(
                    """
                    ALTER TABLE employees.employee
                    ADD COLUMN IF NOT EXISTS email TEXT;
                    """
                )
                cur.execute(
                    """
                    WITH RankedUsers AS (
                        SELECT 
                            id,
                            first_name,
                            last_name,
                            ROW_NUMBER() OVER (
                                PARTITION BY LOWER(first_name), LOWER(last_name) 
                                ORDER BY id
                            ) as name_rank
                        FROM employees.employee
                    )
                    UPDATE employees.employee e
                    SET email = LOWER(
                        RankedUsers.first_name || '.' || RankedUsers.last_name || 
                        CASE 
                            WHEN RankedUsers.name_rank > 1 THEN '-' || RankedUsers.name_rank
                            ELSE '' 
                        END || %s
                    )
                    FROM RankedUsers
                    WHERE e.id = RankedUsers.id;                
                    """,
                    (DOMAIN,),
                )
                updated = cur.rowcount
                comment = "The data in this table contains historical data. If you need to know the active value, filter the column to_date with '9999-01-01'"
                cur.execute("COMMENT ON TABLE employees.department_employee IS %s",(comment,),)
                cur.execute("COMMENT ON TABLE employees.department_manager IS %s",(comment,),)
                cur.execute("COMMENT ON TABLE employees.salary IS %s",(comment,),)
                cur.execute("COMMENT ON TABLE employees.title IS %s",(comment,),)
                conn.commit()
                print(f"{updated} emails added on employees.employee table; tables with historical data description set.")

        with conn.cursor() as cur:
            if initialize or input("Do you want to refresh the survey data (y/n) ? ") == "y":
                with open("data/addDBData.sql", "r") as file:
                    sql = file.read()
                    cur.execute(sql)
                    conn.commit()
                    print("Survey data refreshed successfully.")
            with open("data/newTables.sql", "r") as file:
                sql = file.read()
                cur.execute(sql)
                conn.commit()
                print("New HR tables created successfully.")
        
        #Force PostgreSQL to compute statistics on all tables
        with conn.cursor() as cur:
            cur.execute("ANALYZE VERBOSE;")
            conn.commit()
        
        print(f"Database '{os.getenv('POSTGRES_DATABASE')}' successfully initialized with employees data.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()