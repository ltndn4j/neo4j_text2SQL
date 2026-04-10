import os

import tools.postgresql as db
from tools.semanticLayer import get_neo4j_driver, create_semantic_tools
from tools.dummyTool import create_dummy_tools

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from aura.setupAura import getInstanceId

from dotenv import load_dotenv
load_dotenv(override=True)

PG_SCHEMA = "employees"
PROJECT_ID = "875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc"
NEO4J_INSTANCE = "text2sql-instance"

SYSTEM_PROMPT = """You are a Text2SQL agent and are tasked with answering questions about our dataset on employees. 
Use the metadata graph to collect relevant schema to inform your SQL queries.
Rules:
* Always ensure that tables are qualified with project and dataset names
* Always ensure you have the appropriate schema from the Metadata Graph before write a query
* Return query results to the user in a readable format
* Don't display the SQL query to the user, only the results of the query execution
"""

def build_executor():
    # Neo4j
    neo4j_config = getInstanceId(PROJECT_ID, NEO4J_INSTANCE)
    uri = neo4j_config["neo4j_uri"]
    user = neo4j_config["neo4j_username"]
    password = neo4j_config["neo4j_password"] or os.getenv("neo4j_password")
    driver = get_neo4j_driver(uri, user, password)
    
    # Database
    db_conn = db.get_db_connect()
    
    tools = db.create_db_tools(db_conn) + create_semantic_tools(driver) + create_dummy_tools()
    llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return (
        AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        ),
        driver,
    )

def main():
    executor, driver = build_executor()
    try:
        question = input("Question: ").strip()
        result = executor.invoke({"input": question})
        print(result.get("output", result))
    finally:
        driver.close()

if __name__ == "__main__":
    main()
