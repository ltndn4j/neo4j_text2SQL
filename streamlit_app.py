"""
Streamlit chat UI for the Text2SQL API.

Local run (after the API is up):
    API_BASE=http://127.0.0.1:8000 streamlit run streamlit_app.py

Start the API first, for example:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

# Same examples as agent.py main()
QUESTION_SUGGESTIONS = [
    "How many employees are there in the company ?",
    "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
]


def _queue_suggestion(suggestion: str) -> None:
    st.session_state.pending_prompt = suggestion
    st.session_state.suppress_example_buttons = True


st.set_page_config(page_title="Text2SQL", page_icon="💬")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "suppress_example_buttons" not in st.session_state:
    st.session_state.suppress_example_buttons = False
if "show_usage" not in st.session_state:
    st.session_state.show_usage = True
if "show_sql_query" not in st.session_state:
    st.session_state.show_sql_query = True
if "show_tools" not in st.session_state:
    st.session_state.show_tools = False

_title_col, _settings_col = st.columns([12, 1], gap="small")
with _title_col:
    st.title("Neo4j Semantic Layer")
with _settings_col:
    with st.popover("⚙️", help="Display settings"):
        st.markdown("**Show under assistant messages**")
        st.session_state.show_usage = st.toggle(
            "Usage",
            value=st.session_state.show_usage,
            help="Token usage and model metadata from the agent run.",
        )
        st.session_state.show_sql_query = st.toggle(
            "SQL query",
            value=st.session_state.show_sql_query,
            help="The SQL returned by the agent when it called the database tool.",
        )
        st.session_state.show_tools = st.toggle(
            "Tools",
            value=st.session_state.show_tools,
            help="Which tools the agent invoked for that answer.",
        )

api_base = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
try:
    if hasattr(st, "secrets") and "API_BASE" in st.secrets:
        api_base = str(st.secrets["API_BASE"]).rstrip("/")
except (FileNotFoundError, KeyError, TypeError, RuntimeError):
    pass

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if st.session_state.show_usage and msg.get("usage"):
            with st.expander("Usage"):
                st.json(msg["usage"])
        if st.session_state.show_sql_query and msg.get("sql_query"):
            with st.expander("SQL Query"):
                st.code(msg["sql_query"])
        if st.session_state.show_tools and msg.get("tools"):
            with st.expander("Tools"):
                st.json(msg["tools"])

chat_input = st.chat_input("Ask about the employee dataset")
pending_prompt = st.session_state.pop("pending_prompt", None)
prompt = pending_prompt or chat_input
from_example_question = pending_prompt is not None

if prompt:
    if from_example_question or st.session_state.suppress_example_buttons:
        prev_footer = st.session_state.get("_suggestions_footer")
        if prev_footer is not None:
            prev_footer.empty()
    try:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        answer_text = ""
        usage_data = None
        sql_query = None
        tools = None
        with st.chat_message("assistant"):
            try:
                with st.spinner("Waiting for the agent…"):
                    with httpx.Client(timeout=300.0) as client:
                        r = client.post(f"{api_base}/chat", json={"message": prompt})
                r.raise_for_status()
                data = r.json()
                answer_text = data.get("answer") or ""
                usage_data = data.get("usage")
                sql_query = data.get("sql_query")
                tools = data.get("tools")
            except httpx.HTTPStatusError:
                st.error(
                    "The API returned an error. Check server logs and try again."
                )
            except httpx.RequestError:
                st.error(
                    f"Could not reach the API at {api_base}. "
                    "Start the FastAPI server, then retry."
                )
            if answer_text:
                st.markdown(answer_text)
            if st.session_state.show_usage and usage_data:
                with st.expander("Usage"):
                    st.json(usage_data)
            if st.session_state.show_sql_query and sql_query:
                with st.expander("SQL Query"):
                    st.code(sql_query)
            if st.session_state.show_tools and tools:
                with st.expander("Tools"):
                    st.json(tools)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer_text or "_No response._",
                "usage": usage_data,
                "sql_query": sql_query or "",
                "tools": tools or [],
            }
        )
    finally:
        st.session_state.suppress_example_buttons = False

suggestions_slot = st.empty()
st.session_state._suggestions_footer = suggestions_slot
if st.session_state.suppress_example_buttons:
    suggestions_slot.empty()
else:
    with suggestions_slot.container():
        st.caption("Example questions")
        for i, suggestion in enumerate(QUESTION_SUGGESTIONS):
            st.button(
                suggestion,
                key=f"example_q_{i}",
                use_container_width=True,
                on_click=_queue_suggestion,
                args=(suggestion,),
            )
