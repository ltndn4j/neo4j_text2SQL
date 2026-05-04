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
from langchain_core.messages import HumanMessage, AIMessage
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
    tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
    SQL_queries = [tool["args"].get("query") for tool in tools if tool["name"] == "run_sql"]
    return SQL_queries

def _serialize_tools(steps: list, question: Optional[str] = None):
    tools_name = ["Question rephrased by agent: " + question] if question else []
    tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
    tools_name.extend(["Tool used: " + f"{tool["name"]} ({tool["args"]["pg_schema"]})" if tool["name"] == "list_schema" else tool["name"] for tool in tools])
    return tools_name

def clean_answer(steps: list):
    final_answer = str(steps[-1])
    for step in steps:
        if isinstance(step, AIMessage):
            for content in step.content:
                if content.get("phase") == "final_answer":
                    final_answer = content["text"]
    return str(final_answer)

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
        0.7,
        description="The threshold for the Neo4j semantic layer.",
    )

class ChatResponse(BaseModel):
    answer: str
    with_error: bool = False
    usage: Optional[dict] = None
    sql_queries: Optional[list] = None
    tools: Optional[list] = None
    embeddings: Optional[dict] = None


class ValidateAnswerRequest(BaseModel):
    columns_to_compare: str
    reference_sql: str
    generated_sql: list[str]
    generated_answer: str
    user_message: Optional[str] = None
    backend: Optional[str] = None
    threshold: Optional[float] = 0.7
    resample_loops: Optional[int] = 0

class ValidateAnswerResponse(BaseModel):
    summary: str
    accuracy: float
    accuracy_details: dict
    average_accuracy: Optional[float] = None
    average_accuracy_values: Optional[list[float]] = None
    average_total_tokens_resample: Optional[int] = None
    average_accuracy_summary_focus: Optional[list[dict]] = None
    

class ContextGraphRequest(BaseModel):
    embeddings: Optional[dict] = None
    threshold: float = Field(
        0.7,
        description="The threshold for the Neo4j semantic layer.",
    )

@app.get("/health")
def health():
    return {"status": "ok"}

async def _answer_question(threshold: float, yaml_agent: bool, message: str):
    cb = UsageMetadataCallbackHandler()
    context = {}
    executor = create_executor(
        app.state.neo4j_driver,
        app.state.db_conn,
        cb,
        threshold,
        yaml_agent=yaml_agent,
        context=context
    )
    result = await run_in_threadpool(
        executor.invoke, {"messages": [HumanMessage(content=message.strip())]}
    )
    steps = result.get("messages", [])
    return cb, steps, context

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    await check_db_conn(app)
    try:
        cb, steps, context = await _answer_question(body.threshold, body.yaml_agent, body.message)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="The agent could not complete this request. Error: " + str(e),
        ) from None
    return ChatResponse(
        answer=clean_answer(steps),
        usage=_serialize_usage(cb, body.yaml_agent), 
        sql_queries=_serialize_sql_query(steps), 
        tools=_serialize_tools(steps, context.get("question", None)),
        embeddings=context.get("embeddings", None)
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

@app.post("/validate-answer", response_model=ValidateAnswerResponse)
async def validate_answer(body: ValidateAnswerRequest):
    await check_db_conn(app)
    conn = app.state.db_conn
    result = compare_answer_accuracy(conn, body.columns_to_compare, body.reference_sql, body.generated_sql, body.generated_answer)
    average_accuracy = None
    average_accuracy_values = None
    average_tokens = None
    summary_focus =  None

    if body.resample_loops > 0:
        average_accuracy_values = [result["accuracy"]]
        if result["accuracy"] < 0.5:
            summary_focus = [{"loopNumber":0,"accuracy": result["accuracy"], "summary": result["summary"]}]
        else:
            summary_focus = []
        total_tokens = 0
        for i in range(body.resample_loops):
            generated_sql = []
            generated_answer = ""
            if body.backend == "yaml_llm":
                out = await run_in_threadpool(
                            lambda: run_yaml_llm_question(
                                body.user_message, conn=app.state.db_conn
                            ),
                        )
                total_tokens += out["usage"]["total_tokens"]
                generated_sql = [out["sql_query"]]
                generated_answer = out["answer"]
            else:
                isYamlAgent = body.backend == "yaml_agent"
                cb, steps, context = await _answer_question(body.threshold, isYamlAgent, body.user_message)
                total_tokens += _serialize_usage(cb, isYamlAgent)["total_tokens"]
                generated_sql = _serialize_sql_query(steps)
                generated_answer = clean_answer(steps),
            
            resample_result = compare_answer_accuracy(conn, body.columns_to_compare, body.reference_sql, generated_sql, generated_answer)
            average_accuracy_values.append(resample_result["accuracy"])
            if resample_result["accuracy"] < 0.5:
                summary_focus.append({"loopNumber":i+1,"accuracy": resample_result["accuracy"], "summary": resample_result["summary"]})
        average_tokens = total_tokens / body.resample_loops
        average_accuracy = sum(average_accuracy_values) / len(average_accuracy_values)

    return ValidateAnswerResponse(
        summary=result["summary"],
        accuracy=result["accuracy"],
        accuracy_details=result["accuracy_details"],
        average_accuracy=average_accuracy,
        average_accuracy_values=average_accuracy_values,
        average_total_tokens_resample=average_tokens,
        average_accuracy_summary_focus=summary_focus
    )

@app.post("/context-graph")
async def context_graph(body: ContextGraphRequest):
    await check_db_conn(app)
    if body.embeddings is None:
        df = get_model(app.state.neo4j_driver)
    else:
        df = get_context_graph(app.state.neo4j_driver, body.embeddings, body.threshold)
    # Convert to Parquet in memory
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine='pyarrow')
    return Response(
        content=buffer.getvalue(), 
        media_type="application/octet-stream"
    )