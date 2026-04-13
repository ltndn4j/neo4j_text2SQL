import os

import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

DOMAIN = "@semantictech.com"

def main():
    conn = psycopg2.connect(
        host=os.getenv("postgres_host"),
        database=os.getenv("postgres_database") or "postgres",
        user=os.getenv("postgres_username"),
        password=os.getenv("postgres_password"),
        port=os.getenv("postgres_port") or 5432,
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE employees.employee
                ADD COLUMN IF NOT EXISTS email TEXT;
                """
            )
            cur.execute(
                """
                UPDATE employees.employee
                SET email = LOWER(first_name) || '.' || LOWER(last_name) || %s
                WHERE first_name IS NOT NULL
                  AND last_name IS NOT NULL;
                """,
                (DOMAIN,),
            )
            updated = cur.rowcount
            comment = "The salary data contains historical salary data for each employee. If you need to know the current salary, filter the column to_date with '9999-01-01'"
            cur.execute("COMMENT ON TABLE employees.salary IS %s",(comment,),)
        conn.commit()
        print(f"email column ensured; {updated} row(s) updated; employees.salary description set.")

        with conn.cursor() as cur:
            #Execute addDBData.sql
            with open("data/addDBData.sql", "r") as file:
                sql = file.read()
                cur.execute(sql)
                conn.commit()
                print("addDBData.sql executed successfully.")
            with open("data/newTables.sql", "r") as file:
                sql = file.read()
                cur.execute(sql)
                conn.commit()
                print("newTables.sql executed successfully.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
