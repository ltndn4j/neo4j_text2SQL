from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage

import tools.postgresqlTool as db
from tools.semanticLayerTool import create_semantic_tools
from tools.staticContextTool import create_static_context_tools

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

import neo4jHelpers.database as neo4jdb

from dotenv import load_dotenv
load_dotenv(override=True)

PG_SCHEMA = "employees"

SYSTEM_PROMPT = """You are a Text2SQL agent and are tasked with answering questions about our Human Resources datasets. 
Use the metadata tools to collect relevant schema to inform your SQL queries.
Rules:
* Always call the tool to get the metadata schema before writing a query
* Return result to the user in a readable format in plain text
* Always ensure that tables are qualified with the full name
* Don't display the SQL query to the user, only the results of the query execution
"""

def create_executor(driver, db_conn, usage_callback, threshold: float, yaml_agent=False, context=None):
    tools = (
        db.create_db_tools(db_conn)
        + (create_static_context_tools() if yaml_agent else create_semantic_tools(driver, threshold, context))
    )
    llm = ChatOpenAI(
        model="gpt-5.4-mini", temperature=0, callbacks=[usage_callback], reasoning={"effort": "low"}
    )
    graph = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
    return graph

def test_agent():
    cb = UsageMetadataCallbackHandler()
    driver = neo4jdb.getDriver()
    db_conn = db.get_db_connect()
    executor = create_executor(driver, db_conn, cb, 0.7)
    try:
        questions = [
            "How many employees are there in the company ?",
            "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
        ]
        last_total_tokens = 0
        last_input_tokens = 0
        for question in questions:
            print(f"\033[94m\nQuestion: {question}\033[0m")
            result = executor.invoke({"messages": [HumanMessage(content=question)]})
            steps = result.get("messages", [])
            tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
            tools_name = " -> ".join([tool["name"] for tool in tools])
            SQL_queries = [tool["args"].get("query") for tool in tools if tool["name"] == "run_sql"]
            final_answer = [content["text"] for content in steps[-1].content if content.get("phase") == "final_answer"][0]
            print(final_answer)
            modelName = list(cb.usage_metadata.keys())[0]
            print(f"\033[94mModel used: {modelName}\033[0m")
            total_tokens = cb.usage_metadata[modelName]["total_tokens"]
            input_tokens = cb.usage_metadata[modelName]["input_tokens"]
            print(f"\033[94mTotal tokens: {total_tokens - last_total_tokens}\033[0m")
            print(f"\033[93mInput tokens: {input_tokens - last_input_tokens}\033[0m")
            print(f"\033[94mTools used: {tools_name}\033[0m")
            print(f"SQL Queries used: \n\033[92m{"\n\n".join(SQL_queries)}\033[0m")
            last_total_tokens = total_tokens
            last_input_tokens = input_tokens
    finally:
        driver.close()
        db_conn.close()

if __name__ == "__main__":
    test_agent()
