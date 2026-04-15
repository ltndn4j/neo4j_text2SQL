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

# Rules:
* Always ensure that tables are qualified with schema name
* Always ensure you have the appropriate postgresql schema from the Metadata before write a query
* Return query results to the user in a readable format

# Schema
```yaml
{schema}
```

# Output format
You must return the SQL query in a JSON object with the following format:
{{
    "query": "SELECT * FROM employees.employee",
    "reasoning": "I used the metadata schema to inform my query"
}}
"""

prompt_with_data = """
# Identity
You are a data analyst agent and are tasked with answering questions based on the data provided.

# Rules:
* Return the answer in a readable format
* Don't make up data, only use the data provided

# Data
{data}
"""

model_name = "gpt-5-mini"

llm = OpenAILLM(
    model_name=model_name,
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
    print(f"\n\033[94mQuestion: {question}\033[0m")
    with open("data/database_schema.md", "r") as schema:
        response = llm.client.responses.create(
            model=model_name,
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
            response_with_data = llm.client.responses.create(
                    model=model_name,
                    input=[
                        {
                            "role": "developer",
                            "content": [{"type": "input_text","text": prompt_with_data.format(data=df.to_markdown())}]
                        },
                        {
                            "role": "user",
                            "content": [{"type": "input_text","text": question}]
                        }
                    ],
                    reasoning={},
                    tools=[],
                    store=False
                )
            output_text = response_with_data.output_text
            input_tokens = response.usage.input_tokens + response_with_data.usage.input_tokens
            output_tokens = response.usage.output_tokens + response_with_data.usage.output_tokens
            total_tokens = response.usage.total_tokens + response_with_data.usage.total_tokens
        except Exception as e:
            output_text = f"\033[91mError: {e}\033[0m"
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = response.usage.total_tokens

    #print(f"\033[91m{response_json.get('reasoning')}\033[0m")
    print(output_text)
    print(f"\033[94mModel used: {response.model}\033[0m")
    print(f"\033[94mTotal tokens: {total_tokens}\033[0m")
    print(f"\033[93mInput tokens: {input_tokens}\033[0m")
    print(f"SQL Query used: \n\033[92m{query}\033[0m")


            
            
            
            
            