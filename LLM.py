import json
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import tools.postgresqlTool as db

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

PROMPT_VALIDATION = f"""
# Identity
You are a data analyst agent and are tasked to validate the answer of a LLM agent comparing the differences between 2 datasets

# Rules:
* Compare the generated answer with the reference data
* Return the answer in a readable format
* Don't make up data, only use the data provided
* Only compare the values, not the titles or the order of the columns
* Match the value of the generated answer with the reference data using the SQL query and the result provided in the generated data.
* In the accuracy object, the key is the column name and the value is the accuracy between the reference and the generated value using the formula: (1 - (abs(reference - generated) / reference))

# Output format
You must return the result in a JSON object with the following format:
{{
    "summary": "The summary of the differences between the 2 datasets",
    "average_accuracy": 0.95,
    "accuracy": {{"column1": 0.8, "column2": 0.9, "column3": 0.7}}
}}
"""

MODEL_NAME = "gpt-5.4-mini"
REASONING_EFFORT = "low"

llm = ChatOpenAI(use_responses_api=True, temperature=0)

def _load_schema_text() -> str:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()

def run_yaml_llm_question(
    question: str,
    *,
    conn,
    schema_text: str | None = None,
    only_data: bool = False,
    only_sql: bool = False,
) -> dict:
    if schema_text is None:
        schema_text = _load_schema_text()

    response = llm.invoke(
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
        reasoning={"effort": REASONING_EFFORT},
        temperature=0,
        tools=[],
        store=False,
    )
    usage = {
                "model": response.response_metadata["model_name"],
                "input_tokens": response.usage_metadata["input_tokens"],
                "output_tokens": response.usage_metadata["output_tokens"],
                "total_tokens": response.usage_metadata["total_tokens"],
            }
    try:
        response_json = json.loads(response.content[0]["text"])
        
    except (json.JSONDecodeError, TypeError) as e:
        return {
            "with_error": False,
            "answer": f"Could not parse model output as JSON: {e}",
            "sql_query": None,
            "reasoning": None,
            "usage": usage,
        }

    query = response_json.get("query")
    reasoning = response_json.get("reasoning")

    if not query or not isinstance(query, str):
        return {
            "with_error": False,
            "answer": "Model did not return a valid SQL query string.",
            "sql_query": query if isinstance(query, str) else None,
            "reasoning": reasoning if isinstance(reasoning, str) else None,
            "usage": usage
        }
    if only_sql:
        return {
            "with_error": False,
            "answer": "None",
            "sql_query": query,
            "usage": usage
        }
    with conn.cursor() as cur:
        failed = False
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
                if only_data:
                    return df
                response_with_data = llm.invoke(
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
                    temperature=0,
                    tools=[],
                    store=False,
                )
                output_text = response_with_data.content[0]["text"]
                input_tokens = (
                    response.usage_metadata["input_tokens"]
                    + response_with_data.usage_metadata["input_tokens"]
                )
                output_tokens = (
                    response.usage_metadata["output_tokens"]
                    + response_with_data.usage_metadata["output_tokens"]
                )
                total_tokens = (
                    response.usage_metadata["total_tokens"]
                    + response_with_data.usage_metadata["total_tokens"]
                )
        except Exception as e:
            failed = True
            output_text = f"Error: {e}"
            input_tokens = response.usage_metadata["input_tokens"]
            output_tokens = response.usage_metadata["output_tokens"]
            total_tokens = response.usage_metadata["total_tokens"]

    return {
        "with_error": failed,
        "answer": output_text,
        "sql_query": query,
        "reasoning": reasoning if isinstance(reasoning, str) else None,
        "usage": {
            "backend": "LLM+YAML Grounding",
            "model": response.response_metadata["model_name"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }

PROMPT_VALIDATION_DATA = """#Generated answer
{generated_answer}
#Columns to compare:
{focus}
#Reference data:
## SQL Query
{ref_sql}
## Result
{ref_data}
#Generated data:
"""
PROMPT_VALIDATION_DATA_GENERATED = """## SQL Query
{gen_sql}
## Result
{gen_data}
"""

def compare_answer_accuracy(conn, columns_to_compare: str, reference_sql: str, generated_sql: list[str], generated_answer: str = None) -> dict:
    with conn.cursor() as cur:
        cur.execute(reference_sql)
        ref_df = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])
        ref_data = ref_df.to_markdown()
        prompt = PROMPT_VALIDATION_DATA.format(focus=columns_to_compare,ref_sql=reference_sql, ref_data=ref_data, generated_answer=generated_answer)
        for sql in generated_sql:
            try:    
                cur.execute(sql)
                gen_df = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])
                gen_data = gen_df.to_markdown()
            except Exception as e:
                gen_data = f"Error: {e}"
            prompt += PROMPT_VALIDATION_DATA_GENERATED.format(gen_sql=sql, gen_data=gen_data)
    response = llm.invoke(
        model=MODEL_NAME,
        input=[
            {
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": PROMPT_VALIDATION}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        text={"format": {"type": "json_object"}},
        reasoning={"effort": REASONING_EFFORT},
        temperature=0,
        tools=[],
        store=False,
    )
    return json.loads(response.content[0]["text"])


def test_yaml_grounding():
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

def test_sql_result_loop():

    question = "What is the average salary and its related satisfaction for man and woman ?"
    sql_answer = """
    SELECT e.gender,
	   AVG(s.amount) AS average_salary,
       AVG(ss.payroll_score) AS average_satisfaction
    FROM employees.employee e
    JOIN employees.salary s
        ON s.employee_id = e.id 
        AND s.from_date <= DATE '2026-04-15' AND s.to_date > DATE '2026-04-16'
    LEFT JOIN hr_survey.satisfaction_survey ss
        ON ss.employee_email = e.email
    GROUP BY e.gender
    """
    conn = db.get_db_connect()
    reference_answer = {"Men":{}, "Women":{}}
    with conn.cursor() as cur:
        cur.execute(sql_answer)
        rows = cur.fetchall()
        for row in rows:
            if row[0] == "M":
                reference_answer["Men"]["average_salary"] = row[1]
                reference_answer["Men"]["average_satisfaction"] = row[2]
            else:
                reference_answer["Women"]["average_salary"] = row[1]
                reference_answer["Women"]["average_satisfaction"] = row[2]
    print("Reference answer:")
    print(pd.DataFrame(rows, columns=[desc[0] for desc in cur.description]).to_markdown())
    print("--------------------------------\n")
    #Execute 10 times the query and get the average of the results
    for i in range(10):
        out = run_yaml_llm_question(question, conn=conn, only_data=True)
        if type(out) == pd.DataFrame:
            print(f"{out.to_markdown()}\n")
        else:
            print(f"{out['answer']}")
            conn = db.get_db_connect()

if __name__ == "__main__":
    print("Testing YAML Grounding")
    test_yaml_grounding()
    print("Testing RAW SQL Result 10 times")
    test_sql_result_loop()