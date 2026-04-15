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
st.title("Neo4j Semantic Layer")

api_base = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
try:
    if hasattr(st, "secrets") and "API_BASE" in st.secrets:
        api_base = str(st.secrets["API_BASE"]).rstrip("/")
except (FileNotFoundError, KeyError, TypeError, RuntimeError):
    pass

if "messages" not in st.session_state:
    st.session_state.messages = []
if "suppress_example_buttons" not in st.session_state:
    st.session_state.suppress_example_buttons = False

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("usage"):
            with st.expander("Usage"):
                st.json(msg["usage"])
        if msg.get("sql_query"):
            with st.expander("SQL Query"):
                st.code(msg["sql_query"])

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
            if usage_data:
                with st.expander("Usage"):
                    st.json(usage_data)
            if sql_query:
                with st.expander("SQL Query"):
                    st.code(sql_query)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer_text or "_No response._",
                "usage": usage_data,
                "sql_query": sql_query or "",
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
