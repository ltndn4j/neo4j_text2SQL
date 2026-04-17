import psycopg2
import neo4j
from dotenv import load_dotenv
from aura.setupAura import getInstanceId
import os
import openai

load_dotenv(override=True)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

def load_schema(db_conn: psycopg2.extensions.connection, driver: neo4j.GraphDatabase.driver, schema_name: str):
    session = driver.session()
    with db_conn.cursor() as cur:
        #Retrieve the tables of the database
        query = """
        SELECT
            t.table_catalog,
            t.table_schema,
            t.table_name,
            obj_description(c.oid, 'pg_class') AS table_description
        FROM information_schema.tables AS t
        LEFT JOIN pg_catalog.pg_namespace AS n
            ON n.nspname = t.table_schema
        LEFT JOIN pg_catalog.pg_class AS c
            ON c.relnamespace = n.oid
            AND c.relname = t.table_name
            AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
        WHERE t.table_schema = %s
        """
        cur.execute(query, (schema_name,))
        tables = cur.fetchall()
        for table in tables:
            cypher="""
                MERGE (d:Database {name: $table_catalog})
                MERGE (s:Schema {name: $table_schema})
                MERGE (t:Table {name: $table_name})
                SET t.comment = $table_comment
                MERGE (d)-[:CONTAINS_SCHEMA]->(s)
                MERGE (s)-[:CONTAINS_TABLE]->(t)
            """
            params={
                "table_catalog": table[0],
                "table_schema": table[1],
                "table_name": table[2],
                "table_comment": table[3],
            }
            session.run(cypher, params)

        #retieve all the columns of the tables
        query = """
        SELECT
            isc.table_name,
            isc.column_name,
            isc.data_type,
            isc.is_nullable,
            pgs.n_distinct as distinct_values
        FROM information_schema.columns AS isc
        LEFT OUTER JOIN pg_stats pgs
            ON isc.table_name = pgs.tablename 
            AND isc.column_name = pgs.attname
            AND isc.table_schema = pgs.schemaname
        WHERE isc.table_schema = %s
        ORDER BY table_name, column_name
        """
        cur.execute(query, (schema_name,))
        columns = cur.fetchall()
        for c in columns:
            cypher="""
                MERGE (t:Table {name: $table_name})
                MERGE (c:Column {tableName: $table_name, name: $column_name})
                SET c.type=$data_type, c.nullable=$is_nullable, c.embedding=$embedding
                MERGE (t)-[:HAS_COLUMN]->(c)
            """
            embedding = openai.embeddings.create(
                input=f"{c[0]} {c[1]}",
                model=EMBEDDING_MODEL
            ).data[0].embedding

            params={
                "table_name": c[0],
                "column_name": c[1],
                "data_type": c[2],
                "is_nullable": c[3]=="YES",
                "embedding": embedding
            }
            session.run(cypher, params)

            if type(c[4]) in (int, float) and 0 < c[4] < 50:
                query=f"SELECT DISTINCT {c[1]} FROM {schema_name}.{c[0]}"
                curVal = db_conn.cursor()
                curVal.execute(query)
                values = curVal.fetchall()
                cypherValue="""
                    MERGE (c:Column {tableName: $table_name, name: $column_name})
                    MERGE (v:Value {value: $value})
                    MERGE (c)-[:HAS_VALUE]->(v)
                """
                for value in values:
                    paramsValue={
                        "table_name": c[0],
                        "column_name": c[1],
                        "value": value[0]
                    }
                    session.run(cypherValue, paramsValue)

        #Retrieve all the foreign keys of the tables
        query="""
        SELECT
            tc.table_name, 
            tc.constraint_name, 
            kcu.column_name, 
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name 
        FROM information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE 
            tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = %s
        ORDER BY tc.table_name, tc.constraint_name
        """
        cur.execute(query, (schema_name,))
        foreign_keys = cur.fetchall()
        for fk in foreign_keys:
            cypher="""
                MERGE (c:Column {tableName: $table_name, name: $column_name})
                MERGE (fk:ForeignKey {name: $constraint_name})
                MERGE (cfk:Column {tableName: $foreign_table_name, name: $foreign_column_name})
                MERGE (c)-[:HAS_FOREIGN_KEY]->(fk)
                MERGE (fk)-[:ON_COLUMN]->(cfk)
            """
            params={
                "table_name": fk[0],
                "column_name": fk[2],
                "constraint_name": fk[1],
                "foreign_table_name": fk[3],
                "foreign_column_name": fk[4]
            }
            session.run(cypher, params)

        #Retrieve all the indexes of the tables with their columns
        query="""
        SELECT
            i.relname AS index_name,
            t.relname AS table_name,
            ix.indisprimary AS is_primary_key,
            array_agg(a.attname) AS column_name
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE n.nspname = %s
        GROUP BY i.relname, t.relname, ix.indisprimary
        ORDER BY i.relname
        """
        cur.execute(query, (schema_name,))
        indexes = cur.fetchall()
        for index in indexes:
            cypher="""
                MERGE (t:Table {name: $table_name})
                MERGE (i:Index {name: $index_name})
                MERGE (t)-[:HAS_INDEX]->(i)
                WITH t, i
                UNWIND $column_names AS col
                MERGE (c:Column {tableName: $table_name, name: col})
                MERGE (i)-[:INDEXES_COLUMN]->(c)
            """
            params={
                "index_name": index[0],
                "table_name": index[1],
                "column_names": index[3]
            }
            session.run(cypher, params)
            if index[2]:
                cypher="""
                    MERGE (t:Table {name: $table_name})
                    MERGE (co:Constraint {name: $constraint_name})
                    SET co.primaryKey=true
                    MERGE (t)-[:HAS_CONSTRAINT]->(co)
                    WITH t, co
                    UNWIND $column_names AS col
                    MERGE (c:Column {tableName: $table_name, name: col})
                    MERGE (co)-[:CONSTRAINTS_COLUMN]->(c)
                """
                params={
                    "constraint_name": index[0],
                    "table_name": index[1],
                    "column_names": index[3]
                }
                session.run(cypher, params)

        #add vector index if no exists
        session.run(f"""
        CREATE VECTOR INDEX column_similarity IF NOT EXISTS
            FOR (c:Column)
            ON c.embedding
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                    `vector.similarity_function`: 'cosine'
                }}
            }}
        """)

def load():
    #Connect to the PostgreSQL database
    conn = psycopg2.connect(
        host=os.getenv('postgres_host'),
        database='postgres',
        user=os.getenv('postgres_username'),
        password=os.getenv('postgres_password')
    )

    #Connect to the Neo4j database
    neo4j_config = getInstanceId("875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc","text2sql-instance")
    neo4j_uri = neo4j_config["neo4j_uri"]
    neo4j_username = neo4j_config["neo4j_username"]
    neo4j_password = neo4j_config["neo4j_password"] or os.getenv('neo4j_password')
    driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

    if input("Do you want to erase all the data from the Neo4j database before loading (y/n) ? ") == "y":
        session = driver.session()
        session.run("MATCH (n) DETACH DELETE n")
        session.close()
        print("All data from the Neo4j database erased.")

    schemas = ["employees", "hr_survey", "payroll","recruitment","training","benefits","assets","compliance","timekeeping","org","projects","expenses","performance","leave_mgmt","vendors","skills","documents","onboarding","announcements"]
    for schema in schemas:
        load_schema(conn, driver, schema)

    conn.close()
    driver.close()

if __name__ == "__main__":
    load()