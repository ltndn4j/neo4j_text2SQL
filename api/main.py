"""
Text2SQL agent HTTP API.

Local run (terminal 1):
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

Pair with Streamlit (terminal 2); set API_BASE to this server's URL.
"""

import json
import os
import io
from fastapi import Response
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import tools.postgresqlTool as db
from agent import NEO4J_INSTANCE, PROJECT_ID, create_executor
from LLM import run_yaml_llm_question, compare_answer_accuracy
from aura.setupAura import getInstanceId
from tools.semanticLayerTool import get_neo4j_driver
from semanticLayer import get_context_graph, get_model


def _db_conn_ok(conn) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
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
        return toolAction_SQL[-1].tool_input.get('query')
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
    neo4j_config = getInstanceId(PROJECT_ID, NEO4J_INSTANCE)
    uri = neo4j_config["neo4j_uri"]
    user = neo4j_config["neo4j_username"]
    password = neo4j_config["neo4j_password"] or os.getenv("neo4j_password")
    driver = get_neo4j_driver(uri, user, password)
    conn = db.get_db_connect()
    app.state.neo4j_driver = driver
    app.state.db_conn = conn
    yield
    driver.close()
    conn.close()


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

class ChatResponse(BaseModel):
    answer: str
    with_error: bool = False
    usage: Optional[dict] = None
    sql_query: Optional[str] = None
    tools: Optional[list] = None
    embeddings: Optional[list] = None


class ValidateSQLAnswerRequest(BaseModel):
    columns_to_compare: str
    reference_sql: str
    generated_sql: str

class ValidateSQLAnswerResponse(BaseModel):
    summary: str
    accuracy: float
    accuracy_details: dict

class ContextGraphRequest(BaseModel):
    embedding: Optional[list] = None

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    cb = UsageMetadataCallbackHandler()
    context = {}
    executor = create_executor(
        app.state.neo4j_driver,
        app.state.db_conn,
        cb,
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
        sql_query=_serialize_sql_query(steps), 
        tools=_serialize_tools(steps, context.get("question", None)),
        embeddings=context.get("embedding", None)
    )

@app.post("/yaml-llm", response_model=ChatResponse)
async def yaml_llm(body: ChatRequest):
    if not await run_in_threadpool(_db_conn_ok, app.state.db_conn):
        print("The database connection is unavailable. RESTARTING CONNECTION.")
        app.state.db_conn = db.get_db_connect()
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
        sql_query=out.get("sql_query"),
    )

@app.post("/validate-sql-answer", response_model=ValidateSQLAnswerResponse)
async def validate_sql_answer(body: ValidateSQLAnswerRequest):
    result = compare_answer_accuracy(app.state.db_conn, body.columns_to_compare, body.reference_sql, body.generated_sql)
    return ValidateSQLAnswerResponse(
        summary=result["summary"],
        accuracy=result["average_accuracy"],
        accuracy_details=result["accuracy"],
    )

@app.post("/context-graph")
async def context_graph(body: ContextGraphRequest):
    if body.embedding is None:
        df = get_model(app.state.neo4j_driver)
    else:
        df = get_context_graph(app.state.neo4j_driver, body.embedding)
    # Convert to Parquet in memory
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine='pyarrow')
    return Response(
        content=buffer.getvalue(), 
        media_type="application/octet-stream"
    )