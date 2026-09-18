import os
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
import tools.postgresqlTool as db
from pydantic import BaseModel, Field


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

# User Question to translate into SQL query
{question}
"""

PROMPT_RESULT = """
# Identity
You are a data analyst agent and are tasked with answering questions based on the data provided.

# Rules:
* Return the answer in a readable format
* Don't make up data, only use the data provided

# User Question
{question}

# Data
{data}
"""

class SQLResult(BaseModel):
    query: str
    reasoning: str

class ColumnAccuracy(BaseModel):
    column_name: str = Field(description="The name of the column in the generated data")
    column_reference: str = Field(description="The name of the column used as reference for the comparison")
    accuracy: float = Field(description="The accuracy between the reference and the generated value for this column")

class ValidationResult(BaseModel):
    summary: str = Field(description="A summary of the validation results")
    average_accuracy: float = Field(description="The average accuracy between the reference and the generated value for all columns")
    accuracy: list[ColumnAccuracy] = Field(description="The accuracy between the reference and the generated value for each column")

def get_llm(callbacks=None, advanced_config=False):
    if os.getenv("LOCAL_MODEL") == "true":
        return ChatOllama(model="devstral-small-2", temperature=0, callbacks=callbacks)
    else:
        if advanced_config:
            return ChatOpenAI(model="gpt-5.4-mini", temperature=0, callbacks=callbacks, reasoning={"effort": "low"})
        else:
            return ChatOpenAI(model="gpt-5.4-mini", temperature=0, callbacks=callbacks)

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

    prompt = PROMPT_SQL.format(schema=schema_text, question=question)
    llm = get_llm()
    response = llm.with_structured_output(SQLResult, method="json_schema", include_raw=True).invoke(prompt)
    raw = response["raw"]
    result = response["parsed"]

    usage = {
                "model": raw.response_metadata["model_name"],
                "input_tokens": raw.usage_metadata["input_tokens"],
                "output_tokens": raw.usage_metadata["output_tokens"],
                "total_tokens": raw.usage_metadata["total_tokens"],
            }

    query = result.query
    reasoning = result.reasoning

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
                input_tokens = usage["input_tokens"]
                output_tokens = usage["output_tokens"]
                total_tokens = usage["total_tokens"]
            else:
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=[desc[0] for desc in cur.description])
                if only_data:
                    return df
                prompt = PROMPT_RESULT.format(data=df.to_markdown(), question=question)
                answer = llm.invoke(prompt)
                output_text = answer.content
                input_tokens = usage["input_tokens"] + answer.usage_metadata["input_tokens"]
                output_tokens = usage["output_tokens"] + answer.usage_metadata["output_tokens"]
                total_tokens = usage["total_tokens"] + answer.usage_metadata["total_tokens"]
        except Exception as e:
            failed = True
            output_text = f"Error: {e}"
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            total_tokens = usage["total_tokens"]
            conn.rollback()

    return {
        "with_error": failed,
        "answer": output_text,
        "sql_query": query,
        "reasoning": reasoning if isinstance(reasoning, str) else None,
        "usage": {
            "backend": "LLM+YAML Grounding",
            "model": usage["model"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }

PROMPT_VALIDATION_DATA = """# Identity
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
    "average_accuracy": 0.85,
    "accuracy": [
        {{"column_name": "column1", "column_reference": "column_one", "accuracy": 0.8}}, 
        {{"column_name": "column2", "column_reference": "column_two", "accuracy": 0.9}} 
    ]
}}

#Generated answer
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
        try:
            cur.execute(reference_sql)
            ref_df = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])
            ref_data = ref_df.to_markdown()
        except Exception as e:
            conn.rollback()
            return {"summary": "Error in reference SQL: " + str(e), "accuracy": 0, "accuracy_details": {}}
        prompt = PROMPT_VALIDATION_DATA.format(focus=columns_to_compare,ref_sql=reference_sql, ref_data=ref_data, generated_answer=generated_answer)
        for sql in generated_sql:
            try:    
                cur.execute(sql)
                gen_df = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])
                gen_data = gen_df.to_markdown()
            except Exception as e:
                gen_data = f"Error: {e}"
                conn.rollback()
            prompt += PROMPT_VALIDATION_DATA_GENERATED.format(gen_sql=sql, gen_data=gen_data)
    response = ValidationResult(summary="None", average_accuracy=0, accuracy=[])
    if os.getenv("LOCAL_MODEL") == "true":
        response = get_llm().with_structured_output(ValidationResult, method="json_schema").invoke(prompt)
    else:
        raw = get_llm(advanced_config=True).invoke(prompt)
        try:
            final_answer = [content["text"] for content in raw.content if content.get("phase", None) == "final_answer"][0]
            response = ValidationResult.model_validate_json(final_answer)
        except Exception as e:
            response.summary = "Error: " + str(e)
    
    response.average_accuracy = response.average_accuracy if isinstance(response.average_accuracy, (int, float)) and response.average_accuracy > 0 else 0
    return {
            "summary": response.summary,
            "accuracy": response.average_accuracy,
            "accuracy_details": {
                item.column_name: {"column_reference": item.column_reference, "accuracy": item.accuracy}
                for item in response.accuracy
            }
        }