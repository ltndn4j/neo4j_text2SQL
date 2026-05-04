"""
Streamlit chat UI for the Text2SQL API.

Local run (after the API is up):
    API_BASE=http://127.0.0.1:8000 streamlit run streamlit_app.py
Start the API first, for example:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

Or use the CLI:
    neo4j-text2sql ui
    Start the Streamlit app with:
    neo4j-text2sql api
"""

import os
import pandas as pd
import io
import json
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

PUBLIC_API_MODES = ["yaml_agent", "agent"]
HIDDEN_API_MODES = ["yaml_llm"]

THRESHOLD = 0.7
WORKERS = 6

# Curated example questions with reference SQL (expected answer query).
QUESTION_SUGGESTIONS = [
    {
        "question": "How many candidates are there ?",
        "reference_sql": "SELECT COUNT(*) AS candidate_count FROM recruitment.candidate;",
        "columns_to_compare": "candidate_count",
        "type": "default",
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
        "columns_to_compare": "Compare only the two columns average_salary and average_payroll_satisfaction, using the column gender as the reference where M matches man or men, F matches woman or women",
        "type": "default",
    },
    {
        "question": "Can you give me all the first names on each current role that are most common ?",
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
SELECT r1.title, r1.first_name, r1.employee_count
FROM RankedEmployees r1
JOIN RankedEmployees r2 ON r1.title = r2.title AND r1.employee_count = r2.employee_count
WHERE r2.rank_id = 1
ORDER BY r1.title, r1.first_name
""",
        "columns_to_compare": "Compare only the column first_name and employee_count if avaiblable, using the column title as the reference. Make sure to check all the first names for each title.",
        "type": "default",
    }
]


def request_answer_sql_validation(
    client: httpx.Client,
    api_base: str,
    columns_to_compare: str,
    reference_sql: str,
    generated_sql: list[str],
    answer: str,
    user_message: str = None,
    backend: str = PUBLIC_API_MODES[0],
    threshold: float = THRESHOLD,
    resample_loops: int = 0,
    workers: int = WORKERS,
    on_progress=None
) -> dict:
    """
    Call POST ``{api_base}/validate-answer`` with the reference and generated SQL.

    The FastAPI route is not implemented yet; this will raise until the server adds it.
    """
    base = api_base.rstrip("/")
    payload = {
        "columns_to_compare": columns_to_compare,
        "reference_sql": reference_sql, 
        "generated_sql": generated_sql, 
        "generated_answer": answer,
        "user_message": user_message,
        "backend": backend,
        "threshold": threshold,
        "resample_loops": resample_loops,
        "workers": workers
    }
    headers={"Accept": "text/event-stream"}
    with client.stream("POST", f"{base}/validate-answer", json=payload, headers=headers) as response:
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if data.get("status") == "running":
                    on_progress(data.get("done", 0))
                elif data.get("status") == "error":
                    return {"summary": data.get("message"), "accuracy":0, "accuracy_details":{}}
                else:
                    return data.get("data")

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

def get_context_graph(api_base: str, embeddings: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_cols = ["id", "labels", "properties"]
    rel_cols = ["type", "source", "target", "properties"]
    with httpx.Client(timeout=300.0) as client:
        r = client.post(f"{api_base}/context-graph", json={"embeddings": embeddings, "threshold": st.session_state.threshold})
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
            "Database":"#a964f6", "Schema": "#0020ff", "Table": "#6793c9", "Column": "#57c7e3", 
            "Constraint":"#f16667", "ForeignKey":"#f79767", "Index":"#ffc454",
            "Term":"#347b64", "Value":"#8dcc93"
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
        if "Value" in node.properties.get("labels") and properties.get("value") is not None:
            properties["name"] = properties.get("value")
        node.properties = properties
    for rel in vg.relationships:
        properties = {"type": rel.properties.get("type")}
        for key, value in rel.properties["properties"].items():
            if value is not None:
                properties[key] = value
        rel.properties = properties
        if rel.properties.get("type") == "REFERENCES":
            rel.width = 4
    html = vg.render(height=f"{CONTENT_HEIGHT_PX-39}px", theme=st.context.theme.type).data
    return html

def _fill_context_graph_placeholder(placeholder, message: str, force_redraw: bool = False) -> None:
    with placeholder.container():
        with st.container(border=True):
            if st.session_state.graph_nodes is not None:
                if force_redraw or st.session_state.graph_html is None:
                    nodes_df = st.session_state.graph_nodes
                    rels_df = st.session_state.graph_rels
                    html = create_visualization_graph(nodes_df, rels_df)
                    st.session_state.graph_html = html
                    st.iframe(html, height="content")
                else:
                    st.iframe(st.session_state.graph_html, height="content")
            else:
                st.caption(message)

@st.dialog("Define your example question")
def open_settings_window():
    question_input = st.text_input(
        "Question",
        key="accuracy_question_input",
        value=st.session_state.UDF[0]["question"] if "UDF" in st.session_state and len(st.session_state.UDF) > 0 else "",
        placeholder="As of today, what is the employee headcount for each age ?",
    )
    reference_sql_input = st.text_area(
        "SQL reference to validate the generated answer",
        key="accuracy_reference_sql_input",
        placeholder="SELECT\n  EXTRACT(YEAR FROM age(birth_date)) AS years_old_age,\n  count(id) as count_employees\nFROM employees.employee\nGROUP BY years_old_age\nORDER BY years_old_age",
        value=st.session_state.UDF[0]["reference_sql"] if "UDF" in st.session_state and len(st.session_state.UDF) > 0 else "",
        height=180
    )
    comparison_instruction_input = st.text_input(
            "Comparison instruction to validate the generated answer",
            key="accuracy_comparison_instruction_input",
            value=st.session_state.UDF[0]["columns_to_compare"] if "UDF" in st.session_state and len(st.session_state.UDF) > 0 else "",
            placeholder="Compare employees count using years_old_age as the reference column",
    )
    if st.button("Add to the list", key="set_accuracy_check_inputs", use_container_width=True):
        if question_input and reference_sql_input and comparison_instruction_input:
            st.session_state.UDF = [{
                "question": question_input,
                "reference_sql": reference_sql_input,
                "columns_to_compare": comparison_instruction_input,
                "type": "udf",
            }]
            st.rerun()
        else:
            st.error("Please fill all the fields to add your example question")

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
if "threshold" not in st.session_state:
    st.session_state.threshold = THRESHOLD
if "workers" not in st.session_state:
    st.session_state.workers = WORKERS
if "show_sql_query" not in st.session_state:
    st.session_state.show_sql_query = False
if "show_tools" not in st.session_state:
    st.session_state.show_tools = False
if "graph_nodes" not in st.session_state:
    st.session_state.graph_nodes = None
if "graph_rels" not in st.session_state:
    st.session_state.graph_rels = None
if "saved_context_graph_nodes" not in st.session_state:
    st.session_state.saved_context_graph_nodes = None
if "saved_context_graph_rels" not in st.session_state:
    st.session_state.saved_context_graph_rels = None
if "context_graph_displayed" not in st.session_state:
    st.session_state.context_graph_displayed = False
if "show_hidden_backends" not in st.session_state:
    st.session_state.show_hidden_backends = False
if "UDF" not in st.session_state:
    st.session_state.UDF = []
if "graph_html" not in st.session_state:
    st.session_state.graph_html = None

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        margin-top: 0rem;
    }
    div.st-key-agent_settings_header button {
        font-weight: 700;
        font-size: 1rem;
        padding: 0;
        margin: 0;
        border: none;
        background: transparent;
        color: inherit;
        min-height: unset;
        line-height: 1.5;
        text-align: left;
        width: auto;
    }
    div.st-key-agent_settings_header button:hover {
        cursor: default;
        color: inherit;
    },
    div.st-key-agent_settings_header button:focus {
        border: none;
        color: inherit;
    }
    div.st-key-agent_settings_header button:focus-visible {
        outline: 2px solid currentColor;
        outline-offset: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True
)
_header_was_suppressed = st.session_state.suppress_example_buttons

_title_col, _semantic_graph_col, _dialog, _settings_col = st.columns([20, 0.8, 0.8, 1], vertical_alignment="bottom")
with _title_col:
    st.title("Talk to your HR data")
with _dialog:
    if st.button("",icon=":material/playlist_add:", help="Add your own example question", disabled=st.session_state.suppress_example_buttons):
        open_settings_window()
with _semantic_graph_col:
    with st.container(horizontal_alignment="right"):
        icon = (
            ":material/graph_3:"
            if st.session_state.saved_context_graph_nodes is not None
            else ":material/graph_2:"
        )
        button = st.button(
            "",
            key="show_graph",
            help="Display the semantic layer model/context graph",
            icon=icon,use_container_width=True,
            disabled=st.session_state.suppress_example_buttons
        )
        if button:
            st.session_state.graph_html = None
            if st.session_state.saved_context_graph_nodes is not None:
                st.session_state.graph_nodes = st.session_state.saved_context_graph_nodes
                st.session_state.graph_rels = st.session_state.saved_context_graph_rels
                st.session_state.saved_context_graph_nodes = None
                st.session_state.saved_context_graph_rels = None
                st.session_state.context_graph_displayed = True
            else:
                if st.session_state.context_graph_displayed:
                    st.session_state.saved_context_graph_nodes = st.session_state.graph_nodes
                    st.session_state.saved_context_graph_rels = st.session_state.graph_rels
                nodes_df, rels_df = get_semantic_layer_model(api_base)
                st.session_state.graph_nodes = nodes_df
                st.session_state.graph_rels = rels_df
                st.session_state.context_graph_displayed = False
            st.rerun()
with _settings_col:
    with st.container(horizontal_alignment="right"):
        with st.popover("⚙️", help="Settings", disabled=st.session_state.suppress_example_buttons):
            if  st.button("**Define the settings for the agent**",key="agent_settings_header",type="tertiary"):
                st.session_state.show_hidden_backends = True
                st.rerun()
            st.session_state.answer_validation = st.toggle(
                "Check Answer accuracy",
                value=True,
                help="For curated example questions, compare the generated answer to the reference",
            )
            resample_loops_options = list(range(20))
            if st.session_state.show_hidden_backends:
                resample_loops_options += [29, 39, 49]
            st.session_state.validation_loop_count = st.select_slider(
                "Accuracy resample loops",
                options=resample_loops_options,
                value=0,
                help="Re-run the backend this many times to get an average accuracy. Set to 0 to disable.",
                disabled=not st.session_state.answer_validation,
            )
            if st.session_state.show_hidden_backends:
                st.session_state.workers = st.select_slider(
                    "Number of workers for parallel processing",
                    options=[2, 4, 6, 8, 10],
                    value=WORKERS
                )
            if st.session_state.validation_loop_count > 6:
                st.warning("Many loops may take 1-2mn.", icon="🚨")
            st.session_state.show_usage = st.toggle(
                "Usage",
                value=True,
                help="Token usage and model metadata from the agent run.",
            )
            st.session_state.show_sql_query = st.toggle(
                "SQL query",
                value=False,
                help="The SQL returned by the agent when it called the database tool.",
            )
            st.session_state.show_tools = st.toggle(
                "Tools",
                value=False,
                help="Which tools the agent invoked for that answer.",
            )
            _backend_options = list(PUBLIC_API_MODES)
            if st.session_state.show_hidden_backends:
                _backend_options = list(PUBLIC_API_MODES) + list(HIDDEN_API_MODES)
            api_mode = st.radio(
                "Backend",
                options=_backend_options,
                format_func=lambda x: (
                    "Neo4j Semantic Layer agent"
                    if x == "agent"
                    else "YAML agent"
                    if x == "yaml_agent"
                    else "YAML AI (RAG)"
                ),
                help="Neo4j Agent uses the Neo4j semantic layer; YAML agent/AI uses the schema-backed Text2SQL agent/pipeline.",
                key="api_mode",
            )
            if st.session_state.show_hidden_backends:
                print(f"api_mode: {api_mode}")
                st.session_state.threshold = st.select_slider(
                    "Semantic similarity threshold",
                    options=[0, 0.2, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85],
                    value=THRESHOLD,
                    disabled=api_mode != "agent",
                    help="Select the Neo4j semantic layer backend to enable this option. Use with caution, higher threshold reduces provided context."
                )

pending_prompt = st.session_state.pop("pending_prompt", None)
pending_reference_sql = st.session_state.pop("pending_reference_sql", None)
pending_columns_to_compare = st.session_state.pop("pending_columns_to_compare", None)
queued_chat_prompt = st.session_state.pop("queued_chat_prompt", None)
chat_input = st.chat_input("Ask about the employee dataset")
if chat_input:
    st.session_state.queued_chat_prompt = chat_input
    st.session_state.suppress_example_buttons = True
    st.rerun()
prompt = pending_prompt or queued_chat_prompt
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
                    with st.expander(f'Usage &nbsp; ({msg["usage"]["total_tokens"]} tokens)'):
                        st.json(msg["usage"])
                if st.session_state.show_sql_query and msg.get("sql_query"):
                    with st.expander("SQL Query"):
                        for sql in msg["sql_query"]:
                            st.code(sql)
                if st.session_state.show_tools and msg.get("tools"):
                    with st.expander("Tools"):
                        st.json(msg["tools"])
                if msg.get("sql_validation") is not None:
                    with st.expander(f"Accuracy &nbsp; {msg['accuracy_icon']}"):
                        st.json(msg["sql_validation"])
    
        if prompt:
            st.session_state.graph_nodes = None
            st.session_state.graph_rels = None
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
                            else "Waiting for AI…"
                        )
                        with st.spinner(spinner_label):
                            with httpx.Client(timeout=300.0) as client:
                                chat_json = {
                                    "message": prompt,
                                    "yaml_agent": api_mode == "yaml_agent",
                                    "threshold": st.session_state.threshold,
                                }
                                r = client.post(f"{api_base}{endpoint}", json=chat_json)
                        r.raise_for_status()
                        data = r.json()
                        embeddings = data.get("embeddings")
                        with_error = data.get("with_error")
                        answer_text = data.get("answer") or ""
                        usage_data = data.get("usage")
                        sql_query = data.get("sql_queries")
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
                                for sql in sql_query:
                                    st.code(sql)
                        if st.session_state.show_tools and tools:
                            with st.expander("Tools"):
                                st.json(tools)
                        accuracy_details = None
    
                        # Context graph for the right column (keep last graph until a new one succeeds)
                        if embeddings:
                            nodes_df, rels_df = get_context_graph(api_base, embeddings)
                            st.session_state.graph_nodes = nodes_df
                            st.session_state.graph_rels = rels_df
                            st.session_state.context_graph_displayed = True
                        _fill_context_graph_placeholder(context_graph_area, "No context graph for the selected settings.", force_redraw=True)

                        if (st.session_state.answer_validation and pending_reference_sql and sql_query):
                            accuracy_details = {}
                            total_loops = int(st.session_state.validation_loop_count)+1
                            progressBar_message = "Validating answer accuracy..."
                            progress_text = f"{progressBar_message} 0/{total_loops}"
                            my_bar = st.progress(0/total_loops, text=progress_text)
                            with my_bar:
                                mistakes = []
                                with httpx.Client(timeout=300.0) as v_client:
                                    sql_validation = request_answer_sql_validation(
                                        v_client,
                                        api_base,
                                        pending_columns_to_compare,
                                        pending_reference_sql,
                                        sql_query,
                                        answer_text,
                                        user_message=prompt,
                                        backend=api_mode,
                                        threshold=st.session_state.threshold,
                                        resample_loops=st.session_state.validation_loop_count,
                                        workers=st.session_state.workers,
                                        on_progress=lambda p: my_bar.progress(
                                            p / total_loops,
                                            text=f"{progressBar_message} {p}/{total_loops}",
                                        )
                                    )
                                    if "average_accuracy" in sql_validation and sql_validation["average_accuracy"] is not None:
                                        accuracy_details = sql_validation
                                        icon = _accuracy_answer_icon(float(sql_validation["average_accuracy"]))
                                    else :
                                        accuracy_details["summary"] = sql_validation["summary"]
                                        accuracy_details["accuracy"] = sql_validation["accuracy"]
                                        accuracy_details["accuracy_details"] = sql_validation["accuracy_details"]
                                        icon = _accuracy_answer_icon(float(sql_validation["accuracy"]))
                                    
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
                        "sql_query": sql_query or [],
                        "tools": tools or [],
                        "sql_validation": accuracy_details,
                        "accuracy_icon": icon,
                    }
                )
            finally:
                st.session_state.suppress_example_buttons = False
        if _header_was_suppressed: 
            st.rerun()
        suggestions_slot = st.empty()
        st.session_state._suggestions_footer = suggestions_slot
        if st.session_state.suppress_example_buttons:
            suggestions_slot.empty()
        else:
            with suggestions_slot.container():
                st.caption("Example questions (Only suggested questions can have the accuracy checked)")
                for i, item in enumerate(QUESTION_SUGGESTIONS + st.session_state.UDF):
                    st.button(
                        item["question"],
                        key=f"example_q_{i}",
                        use_container_width=True,
                        on_click=_queue_suggestion,
                        icon="✏️" if item["type"] == "udf" else None,
                        args=(item["question"], item["reference_sql"], item["columns_to_compare"]),
                    )