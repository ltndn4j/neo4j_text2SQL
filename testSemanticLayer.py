from dotenv import load_dotenv
import neo4jHelpers.database as neo4jdb
from tools.semanticLayerTool import create_semantic_tools

load_dotenv(override=True)
driver = neo4jdb.getDriver()
try:
    tools = create_semantic_tools(driver, threshold=0.65)
    result = tools[0].invoke("What is the average salary for each role ?")
    print(result)
finally:
    driver.close()