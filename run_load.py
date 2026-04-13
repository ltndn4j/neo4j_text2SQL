import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg

def main():
    if input("Type n if you don't want to load the SQL schema to Neo4j") != "n":
        lss.load()
    if input("Type n if you don't want to load the transactions log to Neo4j") != "n":
        ltl.load()
    if input("Type n if you don't want to load the business glossary to Neo4j") != "n":
        lbg.load()

if __name__ == "__main__":
    main()
