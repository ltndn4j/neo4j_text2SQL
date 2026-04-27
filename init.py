import load.postgreSQL_init as pgi
import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg
import neo4jHelpers.database as neo4jdb
import tools.postgresqlTool as db
import psycopg2
import neo4j

def test_connection(conn: psycopg2.connect, driver: neo4j.GraphDatabase.driver) -> None:
    test = {"db_OK": True, "neo4j_OK": True, "apoc_OK": True}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        test["db_OK"] = False
    try:
        with driver.session() as session:
            session.run("RETURN 1")
    except Exception:
        test["neo4j_OK"] = False
    try:
        with driver.session() as session:
            session.run("RETURN apoc.map.removeKey({test'KO'}, 'test')")
    except Exception:
        test["apoc_OK"] = False
    return test

def run_initialization() -> bool:
    driver = neo4jdb.getDriver()
    conn = db.get_db_connect()
    test = test_connection(conn, driver)
    if not test["db_OK"]:
        print("\033[91mPostgreSQL connection failed.\033[0m Please check your connection settings.")
        return False
    if not test["neo4j_OK"]:
        print("\033[91mNeo4j connection failed.\033[0m Please check your connection settings.")
        return False
    if not test["apoc_OK"]:
        print("\033[91mAPOC plugin missing\033[0m on Neo4j database. Please install it and try again.")
        return False
    print("PostgreSQL and Neo4j OK. Initializing the databases...")
    try:
        pgi.createDB(initialize=True)
        lss.load(driver, initialize=True)
        ltl.load(driver, initialize=True)
        lbg.load(driver, initialize=True)
    finally:
        driver.close()
    return True
    
def main() -> None:
    if run_initialization():
        print("All Done! You can now start the API and use the Text2SQL agent.")
        print("Start the API with: \033[92muvicorn api.main:app --reload --host 127.0.0.1 --port 8000\033[0m")
        print("Start the Streamlit app with: \033[92mstreamlit run streamlit_app.py\033[0m")

if __name__ == "__main__":
    main()
