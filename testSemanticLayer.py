from dotenv import load_dotenv
import neo4jHelpers.database as neo4jdb
from tools.semanticLayerTool import create_semantic_tools

load_dotenv(override=True)
def ask_question():
    driver = neo4jdb.getDriver()
    try:
        tools = create_semantic_tools(driver, threshold=0.7)
        result = tools[0].invoke(input("Enter a question about HR data: "))
        print(result)
    finally:
        driver.close()

if __name__ == "__main__":
    ask_question()