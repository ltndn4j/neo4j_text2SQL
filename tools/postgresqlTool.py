from langchain_core.tools import tool
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv(override=True)

def get_db_connect():
    host = os.getenv("POSTGRES_HOST")
    user = os.getenv("POSTGRES_USERNAME")
    pwd = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DATABASE") or "postgres"
    port = os.getenv("POSTGRES_PORT") or 5432
    sslmode = os.getenv("POSTGRES_SSLMODE")
    conn = psycopg2.connect(host=host, database=db, user=user, password=pwd, port=port, sslmode=sslmode)
    return conn

def create_db_tools(conn: psycopg2.extensions.connection):

    @tool
    def run_sql(query: str) -> str:
        """Execute a single PostgreSQL query. Use schema-qualified names. This tool is used when you have the full query ready to execute.
        Before using this tool, you must call the tool to get metadata schema to know the tables and columns to use in the query.
        On error, fix the SQL and try again."""
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                if cur.description is None:
                    return "Query executed; no rows to display."
                colnames = [d[0] for d in cur.description]
                rows = cur.fetchall()
        except Exception as e:
            return f"SQL error: {e}"
        if not rows:
            return "0 rows.\nColumns: " + ", ".join(colnames)
        width = min(len(rows), 100)
        lines = ["\t".join(colnames)]
        for r in rows[:width]:
            lines.append("\t".join("" if v is None else str(v) for v in r))
        out = "\n".join(lines)
        if len(rows) > width:
            out += f"\n... ({len(rows) - width} more rows)"
        return out

    @tool
    def list_schema(pg_schema: str) -> str:
        """Return all table names and columns in the database schema (PostgreSQL).
        Call this when you have a doubt about the tables and columns of a specific schema."""
        rows = []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s
                    ORDER BY table_name, ordinal_position
                    """,
                    (pg_schema,),
                )
                rows = cur.fetchall()
        except Exception as e:
            return f"Schema query error: {e}"
        if not rows:
            return f"No columns found for schema {pg_schema!r}."
        lines = [f"{t}.{c} ({dt}, nullable={n})" for t, c, dt, n in rows]
        return "\n".join(lines)
    return [run_sql, list_schema]