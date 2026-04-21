"""
Streamlit chat UI for the Text2SQL API.

Local run (after the API is up):
    API_BASE=http://127.0.0.1:8000 streamlit run streamlit_app.py

Start the API first, for example:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

import os
import pandas as pd
import io
import httpx
import streamlit as st
from neo4j_viz.colors import ColorSpace
from neo4j_viz.pandas import from_dfs

CONTENT_HEIGHT_PX = 640

AVATAR = {
    "user":None,
    "yaml_llm":"✨", 
    "yaml_agent":"./icon/ai-assistant.png", 
    "agent":"./icon/Neo4j-icon-color.png"
} 

# Curated example questions with reference SQL (expected answer query).
QUESTION_SUGGESTIONS = [
    {
        "question": "How many divisions are there in the company ?",
        "reference_sql": "SELECT COUNT(*) AS division_count FROM employees.department;",
        "columns_to_compare": "division_count",
    },
    {
        "question": "What is the average salary and its related satisfaction for men and women ?",
        "reference_sql": """SELECT e.gender,
  count(ss.employee_email) as survey_answer,
  count(e.id) as employee_count,
  AVG(s.amount) AS average_salary,
  AVG(ss.payroll_score) AS average_payroll_satisfaction
FROM employees.employee e
JOIN employees.salary s ON s.employee_id = e.id  AND s.from_date <= DATE '2026-04-15' AND s.to_date > DATE '2026-04-16'
LEFT JOIN hr_survey.satisfaction_survey ss ON ss.employee_email = e.email
GROUP BY e.gender""",
        "columns_to_compare": "Compare only the two columns average_salary and average_payroll_satisfaction, using the column gender as the reference.",
    },
    {
        "question": "Can you give me all the first names on each role that are most common ?",
        "reference_sql": """WITH RankedEmployees AS (
    SELECT 
        t.title, 
        e.first_name, 
        COUNT(e.id) AS employee_count,
        ROW_NUMBER() OVER(PARTITION BY t.title ORDER BY COUNT(e.id) DESC) as rank_id
    FROM employees.employee e
    JOIN employees.title t ON t.employee_id = e.id
    WHERE t.to_date = DATE '9999-01-01'
    GROUP BY t.title, e.first_name
)
SELECT title, first_name, employee_count
FROM RankedEmployees
WHERE rank_id = 1
ORDER BY title;
""",
        "columns_to_compare": "Compare only the column first_name and employee_count if avaiblable, using the column title as the reference.",
    }
]


def request_answer_sql_validation(
    client: httpx.Client,
    api_base: str,
    columns_to_compare: str,
    reference_sql: str,
    generated_sql: str,
) -> dict:
    """
    Call POST ``{api_base}/validate-sql-answer`` with the reference and generated SQL.

    The FastAPI route is not implemented yet; this will raise until the server adds it.
    """
    base = api_base.rstrip("/")
    response = client.post(
        f"{base}/validate-sql-answer",
        json={"columns_to_compare": columns_to_compare,"reference_sql": reference_sql, "generated_sql": generated_sql},
    )
    response.raise_for_status()
    return response.json()


def _queue_suggestion(question: str, reference_sql: str, columns_to_compare: str) -> None:
    st.session_state.pending_prompt = question
    st.session_state.pending_reference_sql = reference_sql
    st.session_state.pending_columns_to_compare = columns_to_compare
    st.session_state.suppress_example_buttons = True

def get_semantic_layer_model(api_base: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    with httpx.Client(timeout=300.0) as client:
        r = client.post(f"{api_base}/context-graph", json={})
        r.raise_for_status()
        df = pd.read_parquet(io.BytesIO(r.content))
        sources = df[['sourceNodeId', 'sourceLabels', 'sourceNodeProperties']]
        sources = sources.rename(columns={'sourceNodeId': 'id', 'sourceLabels': 'labels', 'sourceNodeProperties': 'properties'})
        targets = df[['targetNodeId', 'targetLabels', 'endNodeProperties']]
        targets = targets.rename(columns={'targetNodeId': 'id', 'targetLabels': 'labels', 'endNodeProperties': 'properties'})
        combined_df = pd.concat([sources, targets], ignore_index=True)
        nodes_df = combined_df.drop_duplicates(subset=['id'])
        rels_df = df[['relationshipType', 'sourceNodeId', 'targetNodeId', 'relProperties']].rename(columns={
            'relationshipType': 'type',
            'sourceNodeId': 'source',
            'targetNodeId': 'target',
            'relProperties': 'properties'
        })
        return nodes_df, rels_df

def get_context_graph(api_base: str, embedding: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_cols = ["id", "labels", "properties"]
    rel_cols = ["type", "source", "target", "properties"]
    with httpx.Client(timeout=300.0) as client:
        r = client.post(f"{api_base}/context-graph", json={"embedding": embedding})
        df = pd.read_parquet(io.BytesIO(r.content))
        nodes_df = df.loc[df["class"] == "NODE", node_cols].copy()
        rels_df = df.loc[df["class"] == "REL", rel_cols].copy()
        return nodes_df.reset_index(drop=True), rels_df.reset_index(drop=True)

def _accuracy_answer_icon(average_accuracy: float) -> str:
    if average_accuracy >= 0.95:
        return "🟢"
    if average_accuracy >= 0.9:
        return "🟡"
    if average_accuracy >= 0.85:
        return "🟠"
    return "🔴"

def create_visualization_graph(nodes_df: pd.DataFrame, rels_df: pd.DataFrame) -> str:
    nodes_df['labelColor'] = nodes_df['labels'].apply(lambda x: x[0] if x else None)
    vg = from_dfs(nodes_df, rels_df)
    vg.color_nodes(
        property="labelColor",
        colors={
            "Database":"#a964f6", "Schema": "#0020ff", "Table": "#6d98cb", "Column": "#57c7e3", 
            "Constraint":"#f16667", "ForeignKey":"#f79767", "Index":"#ffc454",
            "Term":"#3ca180", "Value":"#8dcc93"
        }, 
        color_space=ColorSpace.DISCRETE
    )
    vg.color_relationships(
        property="type",
        colors={"REFERENCES": "#00ffb9"}, 
        color_space=ColorSpace.DISCRETE
    )
    for node in vg.nodes:
        properties = {"labels": node.properties.get("labels").tolist()}
        for key, value in node.properties["properties"].items():
            if value is not None:
                properties[key] = value
        node.properties = properties
    for rel in vg.relationships:
        type = rel.properties.get("type")
        if rel.properties.get("properties") is not None:
            rel.properties = rel.properties.get("properties")
        else:
            rel.properties = {}
        rel.properties["type"] = type
        if rel.properties.get("type") == "REFERENCES":
            rel.width = 4
    html = vg.render(height=f"{CONTENT_HEIGHT_PX-39}px", theme=st.context.theme.type).data
    return html

def _fill_context_graph_placeholder(placeholder, message: str) -> None:
    with placeholder.container():
        with st.container(border=True):
            if st.session_state.context_graph_nodes is not None:
                nodes_df = st.session_state.context_graph_nodes
                rels_df = st.session_state.context_graph_rels
                html = create_visualization_graph(nodes_df, rels_df)
                st.iframe(html, height="content")
            else:
                st.caption(message)


api_base = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
try:
    if hasattr(st, "secrets") and "API_BASE" in st.secrets:
        api_base = str(st.secrets["API_BASE"]).rstrip("/")
except (FileNotFoundError, KeyError, TypeError, RuntimeError):
    pass

st.set_page_config(page_title="Neo4j Semantic Layer Demo", page_icon="💬", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "suppress_example_buttons" not in st.session_state:
    st.session_state.suppress_example_buttons = False
if "show_usage" not in st.session_state:
    st.session_state.show_usage = True
if "answer_validation" not in st.session_state:
    st.session_state.answer_validation = True
if "validation_loop_count" not in st.session_state:
    st.session_state.validation_loop_count = 0
if "show_sql_query" not in st.session_state:
    st.session_state.show_sql_query = False
if "show_tools" not in st.session_state:
    st.session_state.show_tools = False
if "context_graph_nodes" not in st.session_state:
    st.session_state.context_graph_nodes = None
if "context_graph_rels" not in st.session_state:
    st.session_state.context_graph_rels = None

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        margin-top: 0rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

_title_col, _semantic_graph_col, _settings_col = st.columns([20, 1, 1], vertical_alignment="bottom")
with _title_col:
    st.title("Talk to your HR data")
with _semantic_graph_col:
    with st.container(horizontal_alignment="right"):
        if st.button(
            "",
            help="Display the semantic layer model",
            icon=":material/graph_3:",
            use_container_width=True,
        ):
            nodes_df, rels_df = get_semantic_layer_model(api_base)
            st.session_state.context_graph_nodes = nodes_df
            st.session_state.context_graph_rels = rels_df
with _settings_col:
    with st.container(horizontal_alignment="right"):
        with st.popover("⚙️", help="Settings"):
            st.markdown("**Show under assistant messages**")
            st.session_state.answer_validation = st.toggle(
                "Check Answer accuracy",
                value=st.session_state.answer_validation,
                help="For curated example questions, compare the generated answer to the reference",
            )
            st.session_state.validation_loop_count = st.select_slider(
                "Accuracy resample loops",
                options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                value=int(st.session_state.validation_loop_count),
                help="Re-run the backend this many times to get an average accuracy. Set to 0 to disable.",
                disabled=not st.session_state.answer_validation,
            )
            if st.session_state.validation_loop_count > 2:
                st.warning("Many loops will take 2-3mn.", icon="🚨")
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
            api_mode = st.radio(
                "Backend",
                options=["yaml_llm", "yaml_agent", "agent"],
                format_func=lambda x: (
                    "Neo4j Semantic Layer agent"
                    if x == "agent"
                    else "YAML agent"
                    if x == "yaml_agent"
                    else "LLM+YAML Grounding"
                ),
                help="Neo4j Agent uses the Neo4j semantic layer; YAML agent & LLM uses the schema-backed Text2SQL agent/pipeline.",
                key="api_mode",
            )

pending_prompt = st.session_state.pop("pending_prompt", None)
pending_reference_sql = st.session_state.pop("pending_reference_sql", None)
pending_columns_to_compare = st.session_state.pop("pending_columns_to_compare", None)
chat_input = st.chat_input("Ask about the employee dataset")
prompt = pending_prompt or chat_input
from_example_question = pending_prompt is not None

col_chat, col_viz = st.columns([3, 2], gap="medium")
with col_viz:
    context_graph_area = st.empty()
    _fill_context_graph_placeholder(
        context_graph_area,
        "Ask a question using neo4j semantic layer (can be changed in settings) to see the context graph."
    )
with col_chat:
    with st.container(height=CONTENT_HEIGHT_PX, gap="xxsmall"):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"],avatar=AVATAR[msg["role"]]):
                st.markdown(msg["content"])
                if st.session_state.show_usage and msg.get("usage"):
                    with st.expander(f"Usage &nbsp; ({msg["usage"]["total_tokens"]} tokens)"):
                        st.json(msg["usage"])
                if st.session_state.show_sql_query and msg.get("sql_query"):
                    with st.expander("SQL Query"):
                        st.code(msg["sql_query"])
                if st.session_state.show_tools and msg.get("tools"):
                    with st.expander("Tools"):
                        st.json(msg["tools"])
                if msg.get("sql_validation") is not None:
                    with st.expander(f"Accuracy &nbsp; {msg['accuracy_icon']}"):
                        st.json(msg["sql_validation"])
    
        if prompt:
            st.session_state.context_graph_nodes = None
            st.session_state.context_graph_rels = None
            message = "Processing question..."
            message = message + "The graph will be updated when the question is answered." if api_mode == "agent" else message
            _fill_context_graph_placeholder(context_graph_area, message)
            if from_example_question or st.session_state.suppress_example_buttons:
                prev_footer = st.session_state.get("_suggestions_footer")
                if prev_footer is not None:
                    prev_footer.empty()
            try:
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user",avatar=AVATAR["user"]):
                    st.markdown(prompt)
    
                answer_text = ""
                usage_data = None
                sql_query = None
                tools = None
                sql_validation = None
                with st.chat_message("assistant",avatar=AVATAR[api_mode]):
                    try:
                        endpoint = "/chat" if api_mode == "agent" or api_mode == "yaml_agent" else "/yaml-llm"
                        spinner_label = (
                            "Waiting for the agent…"
                            if api_mode == "agent" or api_mode == "yaml_agent"
                            else "Waiting for YAML LLM…"
                        )
                        with st.spinner(spinner_label):
                            with httpx.Client(timeout=300.0) as client:
                                chat_json = {
                                    "message": prompt,
                                    "yaml_agent": api_mode == "yaml_agent",
                                }
                                r = client.post(f"{api_base}{endpoint}", json=chat_json)
                        r.raise_for_status()
                        data = r.json()
                        embeddings = data.get("embeddings")
                        with_error = data.get("with_error")
                        answer_text = data.get("answer") or ""
                        usage_data = data.get("usage")
                        sql_query = data.get("sql_query")
                        tools = data.get("tools")
                        icon = ""
    
                        if answer_text:
                            answer_md_slot = st.empty()
                            answer_md_slot.markdown(answer_text)
                        if st.session_state.show_usage and usage_data:
                            with st.expander(f"Usage &nbsp; ({usage_data['total_tokens']} tokens)"):
                                st.json(usage_data)
                        if st.session_state.show_sql_query and sql_query:
                            with st.expander("SQL Query"):
                                st.code(sql_query)
                        if st.session_state.show_tools and tools:
                            with st.expander("Tools"):
                                st.json(tools)
                        accuracy_details = {
                            "summary": "",
                            "accuracy": None,
                            "accuracy_details": {}
                        }
    
                        # Context graph for the right column (keep last graph until a new one succeeds)
                        if embeddings:
                            nodes_df, rels_df = get_context_graph(api_base, embeddings)
                            st.session_state.context_graph_nodes = nodes_df
                            st.session_state.context_graph_rels = rels_df
                        _fill_context_graph_placeholder(context_graph_area, "No context graph for the selected settings.")

                        if (st.session_state.answer_validation and pending_reference_sql and sql_query):
                            progress_text = "Validating answer accuracy..."
                            total_steps = (int(st.session_state.validation_loop_count)+1)*2
                            my_bar = st.progress(1/total_steps, text=progress_text)
                            with my_bar:
                                with httpx.Client(timeout=300.0) as v_client:
                                    sql_validation = request_answer_sql_validation(
                                        v_client,
                                        api_base,
                                        pending_columns_to_compare,
                                        pending_reference_sql,
                                        sql_query,
                                    )
                                    accuracy_details["summary"] = sql_validation["summary"]
                                    accuracy_details["accuracy"] = sql_validation["accuracy"]
                                    accuracy_details["accuracy_details"] = sql_validation["accuracy_details"]
                                    my_bar.progress(2/total_steps, text=progress_text)
    
                                    #TEST LOOP
                                    params = {"message": prompt,"yaml_agent": api_mode == "yaml_agent", "only_sql": True}
                                    average_accuracy = [accuracy_details["accuracy"]]
                                    for i in range(int(st.session_state.validation_loop_count)):
                                        with httpx.Client(timeout=300.0) as client:
                                            r = client.post(f"{api_base}{endpoint}", json=params)
                                            generated_sql = r.json().get("sql_query")
                                            my_bar.progress((2*i+3)/total_steps, text=progress_text)
                                            v = request_answer_sql_validation(v_client,api_base,pending_columns_to_compare,pending_reference_sql,generated_sql)
                                            average_accuracy.append(v["accuracy"])
                                        my_bar.progress((2*i+4)/total_steps, text=progress_text)
                                    accuracy_details["average_accuracy"] = sum(average_accuracy) / len(average_accuracy)
                                    icon = _accuracy_answer_icon(float(accuracy_details["average_accuracy"]))
                                    accuracy_details["average_accuracy_values"] = average_accuracy
                                with st.expander(f"Accuracy &nbsp; {icon}"):
                                    st.json(accuracy_details)
                    except httpx.HTTPStatusError as exc:
                        st.error(f"Error: {str(exc)}")
                        icon = "🔴"
                    except httpx.RequestError as exc:
                        st.error(f"Error: {str(exc)}")
                        icon = "🔴"
    
                st.session_state.messages.append(
                    {
                        "role": api_mode,
                        "content": answer_text or "_No response._",
                        "usage": usage_data,
                        "sql_query": sql_query or "",
                        "tools": tools or [],
                        "sql_validation": accuracy_details,
                        "accuracy_icon": icon,
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
                for i, item in enumerate(QUESTION_SUGGESTIONS):
                    st.button(
                        item["question"],
                        key=f"example_q_{i}",
                        use_container_width=True,
                        on_click=_queue_suggestion,
                        args=(item["question"], item["reference_sql"], item["columns_to_compare"]),
                    )