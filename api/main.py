"""
Text2SQL agent HTTP API.

Local run (terminal 1):
    neo4j-text2sql api
or
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

Pair with Streamlit (terminal 2); set API_BASE to this server's URL.
"""

import json
import io
from fastapi import Response, FastAPI, HTTPException
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import tools.postgresqlTool as db
from agent import create_executor
from LLM import run_yaml_llm_question, compare_answer_accuracy
import neo4jHelpers.database as neo4jdb
from semanticLayer import get_context_graph, get_model


def _db_conn_ok(conn) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False

def _neo4j_conn_ok(driver) -> bool:
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return True
    except Exception:
        return False

def _serialize_usage(cb: UsageMetadataCallbackHandler, is_yaml_agent: bool = False):
    raw = getattr(cb, "usage_metadata", None) or {}
    if not raw:
        return None
    try:
        usage_data =  json.loads(json.dumps(raw, default=str))
        usage_info = {}
        modelName = list(usage_data.keys())[0]
        usage_info["backend"] = "Neo4j Semantic Layer" if not is_yaml_agent else "YAML Agent"
        usage_info["model"] = modelName
        usage_info["input_tokens"] = usage_data[modelName]["input_tokens"]
        usage_info["output_tokens"] = usage_data[modelName]["output_tokens"]
        usage_info["total_tokens"] = usage_data[modelName]["total_tokens"]
        return usage_info

    except (TypeError, ValueError):
        return None

def _serialize_sql_query(steps: list):
    toolAction_SQL = [action for (action, result) in steps if action.tool == "run_sql"]
    if len(toolAction_SQL) > 0:
        return [action.tool_input.get('query') for action in toolAction_SQL]
    return None

def _serialize_tools(steps: list, question: Optional[str] = None):
    tools = ["Question rephrased by agent: " + question] if question else []
    tools.extend(["Tool used: " + action.tool for (action, result) in steps])
    return tools

def clean_answer(out: str):
    value = out
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        value = out[0]
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
    return str(value)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(override=True)
    driver = neo4jdb.getDriver()
    conn = db.get_db_connect()
    app.state.neo4j_driver = driver
    app.state.db_conn = conn
    yield
    driver.close()
    conn.close()

async def check_db_conn(app: FastAPI):
    if not await run_in_threadpool(_db_conn_ok, app.state.db_conn):
        print("The database connection is unavailable. RESTARTING CONNECTION.")
        app.state.db_conn = db.get_db_connect()
    if not await run_in_threadpool(_neo4j_conn_ok, app.state.neo4j_driver):
        print("The semantic layer connection is unavailable. RESTARTING CONNECTION.")
        app.state.neo4j_driver = neo4jdb.getDriver()

app = FastAPI(title="neo4j_text2SQL API", lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    yaml_agent: bool = Field(
        False,
        description="If true, use static context tools instead of the Neo4j semantic layer.",
    )
    only_sql: bool = Field(
        False,
        description="If true, only return the SQL query.",
    )
    threshold: float = Field(
        0.65,
        description="The threshold for the Neo4j semantic layer.",
    )

class ChatResponse(BaseModel):
    answer: str
    with_error: bool = False
    usage: Optional[dict] = None
    sql_queries: Optional[list] = None
    tools: Optional[list] = None
    embeddings: Optional[list] = None


class ValidateSQLAnswerRequest(BaseModel):
    columns_to_compare: str
    reference_sql: str
    generated_sql: list[str]
    generated_answer: Optional[str] = None

class ValidateSQLAnswerResponse(BaseModel):
    summary: str
    accuracy: float
    accuracy_details: dict

class ContextGraphRequest(BaseModel):
    embedding: Optional[list] = None
    threshold: float = Field(
        0.65,
        description="The threshold for the Neo4j semantic layer.",
    )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    await check_db_conn(app)
    cb = UsageMetadataCallbackHandler()
    context = {}
    executor = create_executor(
        app.state.neo4j_driver,
        app.state.db_conn,
        cb,
        body.threshold,
        yaml_agent=body.yaml_agent,
        context=context
    )
    try:
        result = await run_in_threadpool(
            executor.invoke, {"input": body.message.strip()}
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="The agent could not complete this request.",
        ) from None
    out = result.get("output", result)
    steps = result.get("intermediate_steps")
    answer = clean_answer(out)
    return ChatResponse(
        answer=answer,
        usage=_serialize_usage(cb, body.yaml_agent), 
        sql_queries=_serialize_sql_query(steps), 
        tools=_serialize_tools(steps, context.get("question", None)),
        embeddings=context.get("embedding", None)
    )

@app.post("/yaml-llm", response_model=ChatResponse)
async def yaml_llm(body: ChatRequest):
    await check_db_conn(app)
    try:
        out = await run_in_threadpool(
            lambda: run_yaml_llm_question(
                body.message.strip(), conn=app.state.db_conn, only_sql=body.only_sql
            ),
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="The yaml LLM pipeline could not complete this request.",
        ) from None
    return ChatResponse(
        with_error=out["with_error"],
        answer=out["answer"],
        usage=out.get("usage"),
        sql_queries=[out.get("sql_query")],
    )

@app.post("/validate-sql-answer", response_model=ValidateSQLAnswerResponse)
async def validate_sql_answer(body: ValidateSQLAnswerRequest):
    await check_db_conn(app)
    result = compare_answer_accuracy(app.state.db_conn, body.columns_to_compare, body.reference_sql, body.generated_sql, body.generated_answer)
    return ValidateSQLAnswerResponse(
        summary=result["summary"],
        accuracy=0 if result["average_accuracy"] is None else result["average_accuracy"],
        accuracy_details=result["accuracy"],
    )

@app.post("/context-graph")
async def context_graph(body: ContextGraphRequest):
    await check_db_conn(app)
    if body.embedding is None:
        df = get_model(app.state.neo4j_driver)
    else:
        df = get_context_graph(app.state.neo4j_driver, body.embedding, body.threshold)
    # Convert to Parquet in memory
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine='pyarrow')
    return Response(
        content=buffer.getvalue(), 
        media_type="application/octet-stream"
    )