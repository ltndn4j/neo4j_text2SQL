import neo4j
import json
import os
import psycopg2
import pandas as pd
from google.cloud import bigquery
from dotenv import load_dotenv
from neo4j_graphrag.llm import OpenAILLM


from setupAura import getInstanceId

load_dotenv(override=True)


neo4j_config = getInstanceId("875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc","text2sql-instance")
neo4j_uri = neo4j_config["neo4j_uri"]
neo4j_username = neo4j_config["neo4j_username"]
neo4j_password = neo4j_config["neo4j_password"] or os.getenv('neo4j_password')
AUTH = (neo4j_username, neo4j_password)

driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=AUTH)

prompt = """
# Identity
You are a Text2SQL agent and are tasked with answering questions about our BigQuery dataset on ecommerce. 
Use the metadata schema to inform your SQL queries.

Rules:
* Always ensure that tables are qualified with project and dataset names
* Always ensure you have the appropriate BigQuery schema from the Metadata before write a query
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

schema = """
TABLE `bulkimportbuckettest.demo_ecommerce.order_items`:
 - order_item_id: INT64, PRIMARY KEY
 - order_id: INT64, FOREIGN KEY to orders.order_id
 - price: NUMERIC
 - product_id: INT64, FOREIGN KEY to products.product_id
 - quantity: INT64
  
TABLE `bulkimportbuckettest.demo_ecommerce.products`:
 - product_id: INT64, PRIMARY KEY
 - product_name: STRING
 - category: STRING
 - price: NUMERIC
 
TABLE `bulkimportbuckettest.demo_ecommerce.orders`:
 - order_id: INT64, PRIMARY KEY
 - customer_id: INT64, FOREIGN KEY to customers.customer_id
 - order_date TIMESTAMP
 - total_amount NUMERIC
 
TABLE `bulkimportbuckettest.demo_ecommerce.customers`:
 - customer_id: INT64, PRIMARY KEY
 - customer_name: STRING
 - email: STRING
 - created_at: TIMESTAMP
"""

llm = OpenAILLM(
    model_name="gpt-4o-mini",
    model_params={
        "max_completion_tokens": 2000,
        "response_format": {"type": "json_object"},
        "temperature": 0,
    },
)
    
question = "Can you give me the top category and the total amount on which the customer alice@example.com is buying ?"
response = llm.client.responses.create(
    model="gpt-4o-mini",
    #model="gpt-5-mini",
    input=[
        {
            "role": "developer",
            "content": [{"type": "input_text","text": prompt.format(schema=schema)}]
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

# BigQuery → pandas, then print as a fixed-width table
query = response_json.get("query")
client = bigquery.Client()
df = client.query(query).to_dataframe()
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
print(f"\033[93mResults:\033[0m")
print(df.to_string(index=False))