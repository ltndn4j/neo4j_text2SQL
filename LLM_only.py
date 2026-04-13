import json
import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from neo4j_graphrag.llm import OpenAILLM

load_dotenv(override=True)

prompt = """
# Identity
You are a Text2SQL agent and are tasked with answering questions about our postgresql dataset on Human resources. 
Use the metadata schema to inform your SQL queries.

Rules:
* Always ensure that tables are qualified with schema name
* Always ensure you have the appropriate postgresql schema from the Metadata before write a query
* Return query results to the user in a readable format

# Schema
{schema}

# Output format
You must return the SQL query in a JSON object with the following format:
{{
    "query": "SELECT * FROM employees.employee",
    "reasoning": "I used the metadata schema to inform my query"
}}
"""

llm = OpenAILLM(
    model_name="gpt-5-mini",
    model_params={
        "response_format": {"type": "json_object"},
        "temperature": 0,
    },
)
    
questions = [
    "How many employees are there in the company ?",
    "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
]
for question in questions:
    print(f"\033[94mQuestion: {question}\033[0m")
    with open("data/database_schema.yaml", "r") as schema:
        response = llm.client.responses.create(
            model="gpt-5-mini",
            input=[
                {
                    "role": "developer",
                    "content": [{"type": "input_text","text": prompt.format(schema=schema.read())}]
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text","text": question}]
                }
            ],
            text={"format": {"type": "json_object"}},
            reasoning={},
            tools=[],
            store=False
        )

    response_json = json.loads(response.output_text)
    print(f"\033[91m{response_json.get('reasoning')}\033[0m")
    print(f"\033[92mSQL query: {response_json.get('query')}\033[0m")

    # postgresql → pandas, then print as a fixed-width table
    query = response_json.get("query")
    conn = psycopg2.connect(
        host=os.getenv("postgres_host"),
        database=os.getenv("postgres_database") or "postgres",
        user=os.getenv("postgres_username"),
        password=os.getenv("postgres_password"),
        port=os.getenv("postgres_port") or 5432,
    )

    with conn.cursor() as cur:
        try:
            cur.execute(query)
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=[desc[0] for desc in cur.description])
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", None)
            print(f"\033[93mResults:\033[0m")
            print(df.to_string(index=False))
        except Exception as e:
            print(f"\033[91mError: {e}\033[0m")
        print(f"\033[94mModel used: {response.model}\033[0m")
        print(f"\033[94mTotal tokens: {response.usage.total_tokens}\033[0m")
        print(f"\033[93mInput tokens: {response.usage.input_tokens}\033[0m")
    