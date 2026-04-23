import os
from langchain_core.callbacks import UsageMetadataCallbackHandler

import tools.postgresqlTool as db
from tools.semanticLayerTool import create_semantic_tools
from tools.staticContextTool import create_static_context_tools

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

import neo4jHelpers.database as neo4jdb

from dotenv import load_dotenv
load_dotenv(override=True)

PG_SCHEMA = "employees"

SYSTEM_PROMPT = """You are a Text2SQL agent and are tasked with answering questions about our Human Resources datasets. 
Use the metadata to collect relevant schema to inform your SQL queries.
Rules:
* Return result to the user in a readable format in plain text
* Don't ask for clarification, use the metadata and query the database to answer the question
* Always ensure that tables are qualified with the full name
* Always ensure you have the appropriate schema from the Metadata before write a query
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
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=False,
        return_intermediate_steps=True,
    )

def test_agent():
    cb = UsageMetadataCallbackHandler()
    executor = create_executor(driver, db_conn, cb, 0.65)
    driver = neo4jdb.getDriver()
    db_conn = db.get_db_connect()
    try:
        questions = [
            "How many employees are there in the company ?",
            "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
        ]
        last_total_tokens = 0
        last_input_tokens = 0
        for question in questions:
            print(f"\033[94m\nQuestion: {question}\033[0m")
            result = executor.invoke({"input": question})
            steps = result.get("intermediate_steps")
            tools = [action.tool for (action, result) in steps]
            tools = " -> ".join(tools)
            toolAction_SQL = [action for (action, result) in steps if action.tool == "run_sql"][-1]
            sqlQuery = toolAction_SQL.tool_input.get('query')
            print(result.get("output", result))
            modelName = list(cb.usage_metadata.keys())[0]
            print(f"\033[94mModel used: {modelName}\033[0m")
            total_tokens = cb.usage_metadata[modelName]["total_tokens"]
            input_tokens = cb.usage_metadata[modelName]["input_tokens"]
            print(f"\033[94mTotal tokens: {total_tokens - last_total_tokens}\033[0m")
            print(f"\033[93mInput tokens: {input_tokens - last_input_tokens}\033[0m")
            print(f"\033[94mTools used: {tools}\033[0m")
            print(f"SQL Query used: \n\033[92m{sqlQuery}\033[0m")
            last_total_tokens = total_tokens
            last_input_tokens = input_tokens

    finally:
        driver.close()
        db_conn.close()

if __name__ == "__main__":
    test_agent()
