import load.postgreSQL_init as pgi
import load.loadSQLSchema2Neo as lss
import load.loadTransactionsLog as ltl
import load.loadBusinessGlossary as lbg
import neo4jHelpers.database as neo4jdb

driver = neo4jdb.getDriver()
try:
    pgi.createDB(initialize=True)
    lss.load(driver, initialize=True)
    ltl.load(driver, initialize=True)
    lbg.load(driver, initialize=True)
finally:
    driver.close()

print("All Done! You can now start the API and use the Text2SQL agent.")
print("Start the API with: \033[92muvicorn api.main:app --reload --host 127.0.0.1 --port 8000\033[0m")
print("Start the Streamlit app with: \033[92mstreamlit run streamlit_app.py\033[0m")
