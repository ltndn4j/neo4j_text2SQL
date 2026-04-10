import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg

def main():
    lss.load()
    #ltl.load()  
    #lbg.load()

if __name__ == "__main__":
    main()
