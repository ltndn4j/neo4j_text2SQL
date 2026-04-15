"""
Text2SQL agent HTTP API.

Local run (terminal 1):
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

Pair with Streamlit (terminal 2); set API_BASE to this server's URL.
"""

import json
import os
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import tools.postgresql as db
from agent import NEO4J_INSTANCE, PROJECT_ID, create_executor
from aura.setupAura import getInstanceId
from tools.semanticLayer import get_neo4j_driver


def _serialize_usage(cb: UsageMetadataCallbackHandler):
    raw = getattr(cb, "usage_metadata", None) or {}
    if not raw:
        return None
    try:
        usage_data =  json.loads(json.dumps(raw, default=str))
        usage_info = {}
        modelName = list(usage_data.keys())[0]
        usage_info["model"] = modelName
        usage_info["input_tokens"] = usage_data[modelName]["input_tokens"]
        usage_info["output_tokens"] = usage_data[modelName]["output_tokens"]
        usage_info["total_tokens"] = usage_data[modelName]["total_tokens"]
        return usage_info

    except (TypeError, ValueError):
        return None

def _serialize_sql_query(steps: list):
    toolAction_SQL = [action for (action, result) in steps if action.tool == "run_sql"][0]
    return toolAction_SQL.tool_input.get('query')

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


class ChatResponse(BaseModel):
    answer: str
    usage: Optional[dict] = None
    sql_query: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    cb = UsageMetadataCallbackHandler()
    executor = create_executor(app.state.neo4j_driver, app.state.db_conn, cb)
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
    answer = out if isinstance(out, str) else str(out)    
    return ChatResponse(answer=answer, usage=_serialize_usage(cb), sql_query=_serialize_sql_query(steps))
