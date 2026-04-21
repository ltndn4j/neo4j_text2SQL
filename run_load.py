import load.postgreSQL_init as pgi
import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg

def main():
    if input("Do you want to initialize the PostgreSQL database (y/n) ? ") == "y":
        pgi.createDB()
    if input("Do you want to load the SQL schema to Neo4j (y/n) ? ") == "y":
        lss.load()
    if input("Do you want to load the transactions log to Neo4j (y/n) ? ") == "y":
        ltl.load()
    if input("Do you want to load the business glossary to Neo4j (y/n) ? ") == "y":
        lbg.load()

if __name__ == "__main__":
    main()
