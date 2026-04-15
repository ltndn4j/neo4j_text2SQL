import json
import os
import pandas as pd
from dotenv import load_dotenv
from neo4j_graphrag.llm import OpenAILLM
import tools.postgresql as db

load_dotenv(override=True)

SCHEMA_PATH = "data/database_schema.yaml"
PROMPT_SQL = """
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
PROMPT_RESULT = """
# Identity
You are a data analyst agent and are tasked with answering questions based on the data provided.

# Rules:
* Return the answer in a readable format
* Don't make up data, only use the data provided

# Data
{data}
"""

MODEL_NAME = "gpt-5-mini"

llm = OpenAILLM(
    model_name=MODEL_NAME,
    model_params={
        "response_format": {"type": "json_object"},
        "temperature": 0,
    },
)

def _load_schema_text() -> str:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()

def run_yaml_llm_question(
    question: str,
    *,
    conn,
    schema_text: str | None = None,
) -> dict:
    if schema_text is None:
        schema_text = _load_schema_text()

    response = llm.client.responses.create(
        model=MODEL_NAME,
        input=[
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": PROMPT_SQL.format(schema=schema_text)}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": question}],
            },
        ],
        text={"format": {"type": "json_object"}},
        reasoning={},
        tools=[],
        store=False,
    )

    try:
        response_json = json.loads(response.output_text)
    except (json.JSONDecodeError, TypeError) as e:
        return {
            "answer": f"Could not parse model output as JSON: {e}",
            "sql_query": None,
            "reasoning": None,
            "usage": {
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

    query = response_json.get("query")
    reasoning = response_json.get("reasoning")

    if not query or not isinstance(query, str):
        return {
            "answer": "Model did not return a valid SQL query string.",
            "sql_query": query if isinstance(query, str) else None,
            "reasoning": reasoning if isinstance(reasoning, str) else None,
            "usage": {
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

    with conn.cursor() as cur:
        try:
            cur.execute(query)
            if cur.description is None:
                output_text = "Query executed successfully; no rows to display."
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                total_tokens = response.usage.total_tokens
            else:
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=[desc[0] for desc in cur.description])
                response_with_data = llm.client.responses.create(
                    model=MODEL_NAME,
                    input=[
                        {
                            "role": "developer",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": PROMPT_RESULT.format(data=df.to_markdown()),
                                }
                            ],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": question}],
                        },
                    ],
                    reasoning={},
                    tools=[],
                    store=False,
                )
                output_text = response_with_data.output_text
                input_tokens = (
                    response.usage.input_tokens
                    + response_with_data.usage.input_tokens
                )
                output_tokens = (
                    response.usage.output_tokens
                    + response_with_data.usage.output_tokens
                )
                total_tokens = (
                    response.usage.total_tokens
                    + response_with_data.usage.total_tokens
                )
        except Exception as e:
            output_text = f"Error: {e}"
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = response.usage.total_tokens

    return {
        "answer": output_text,
        "sql_query": query,
        "reasoning": reasoning if isinstance(reasoning, str) else None,
        "usage": {
            "backend": "LLM+YAML Grounding",
            "model": response.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }


def main():
    questions = [
        "How many employees are there in the company ?",
        "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
    ]
    conn = db.get_db_connect()
    try:
        for question in questions:
            print(f"\n\033[94mQuestion: {question}\033[0m")
            out = run_yaml_llm_question(question, conn=conn)
            print(out["answer"])
            print(f"\033[94mModel used: {out['usage']['model']}\033[0m")
            u = out["usage"]
            print(f"\033[94mTotal tokens: {u['total_tokens']}\033[0m")
            print(f"\033[93mInput tokens: {u['input_tokens']}\033[0m")
            print(f"SQL Query used: \n\033[92m{out['sql_query']}\033[0m")
    finally:
        conn.close()

if __name__ == "__main__":
    main()