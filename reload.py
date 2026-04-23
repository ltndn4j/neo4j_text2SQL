import load.postgreSQL_init as pgi
import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg
import neo4jHelpers.database as neo4jdb

def run_reload() -> None:
    driver = neo4jdb.getDriver()
    try:
        if input("Do you want to initialize the PostgreSQL database (y/n) ? ") == "y":
            pgi.createDB()
        if input("Do you want to load the SQL schema to Neo4j (y/n) ? ") == "y":
            lss.load(driver)
        if input("Do you want to load the transactions log to Neo4j (y/n) ? ") == "y":
            ltl.load(driver)
        if input("Do you want to load the business glossary to Neo4j (y/n) ? ") == "y":
            lbg.load(driver)
    finally:
        driver.close()

if __name__ == "__main__":
    run_reload()