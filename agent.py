import tools.postgresqlTool as db
from tools.semanticLayerTool import create_semantic_tools
from tools.staticContextTool import create_static_context_tools

from langchain.agents import create_agent

from LLM import get_llm
from dotenv import load_dotenv
load_dotenv(override=True)

SYSTEM_PROMPT = """You are a Text2SQL agent and are tasked with answering questions about our Human Resources datasets. 
Use the metadata tools to collect relevant schema to inform your SQL queries.
Rules:
* Always call the tool to get the metadata schema before writing a query
* Return result to the user in a readable format in plain text
* Always ensure that tables are qualified with the full name
* Don't display the SQL query to the user, only the results of the query execution
"""

def create_executor(driver, db_conn, usage_callback, threshold: float, yaml_agent=False, context=None):
    llm = get_llm([usage_callback], advanced_config=True)
    tools = (
        db.create_db_tools(db_conn)
        + (create_static_context_tools() if yaml_agent else create_semantic_tools(driver, threshold, context))
    )
    return create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
