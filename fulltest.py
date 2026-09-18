from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from agent import create_executor
from LLM import compare_answer_accuracy
import neo4jHelpers.database as neo4jdb
import tools.postgresqlTool as db
import json
import time
import os
from concurrent.futures import ThreadPoolExecutor
from LLM import run_yaml_llm_question
import pandas as pd
from api.main import clean_answer
from dotenv import load_dotenv

load_dotenv(override=True)

QUESTION_SUGGESTIONS = json.load(open("data/reference_questions.json"))
def get_sql_query(steps: list):
    tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
    SQL_queries = [tool["args"].get("query") for tool in tools if tool["name"] == "run_sql"]
    return SQL_queries

def check_question(question: dict, yaml_agent: bool):
    cb = UsageMetadataCallbackHandler()
    driver = neo4jdb.getDriver()
    db_conn = db.get_db_connect()
    try:
        executor = create_executor(driver,db_conn,cb,0.7,yaml_agent=yaml_agent)
        result = executor.invoke({"messages": [HumanMessage(content=question["question"])]})
        steps = result.get("messages", [])
        reference_sql = "\n".join(question["reference_sql_lines"])
        validation = compare_answer_accuracy(db_conn, question["columns_to_compare"], reference_sql, get_sql_query(steps), clean_answer(steps))
        usage_data =  json.loads(json.dumps(getattr(cb, "usage_metadata", None), default=str))
        modelName = list(usage_data.keys())[0]
        tokens = usage_data[modelName]["total_tokens"]
    finally:
        db_conn.close()
        driver.close()
    return validation["accuracy"], tokens

def test_agent():
    cb = UsageMetadataCallbackHandler()
    driver = neo4jdb.getDriver()
    db_conn = db.get_db_connect()
    executor = create_executor(driver, db_conn, cb, 0.7)
    try:
        questions = [
            "How many employees are there in the company ?",
            "What is the average salary and the related satifaction on the compensation for man and woman in the company ?",
        ]
        last_total_tokens = 0
        last_input_tokens = 0
        for question in questions:
            print(f"\033[94m\nQuestion: {question}\033[0m")
            result = executor.invoke({"messages": [HumanMessage(content=question)]})
            steps = result.get("messages", [])
            tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
            tools_name = " -> ".join([tool["name"] for tool in tools])
            SQL_queries = [tool["args"].get("query") for tool in tools if tool["name"] == "run_sql"]
            final_answer = clean_answer(steps)
            print(final_answer)
            modelName = list(cb.usage_metadata.keys())[0]
            print(f"\033[94mModel used: {modelName}\033[0m")
            total_tokens = cb.usage_metadata[modelName]["total_tokens"]
            input_tokens = cb.usage_metadata[modelName]["input_tokens"]
            print(f"\033[94mTotal tokens: {total_tokens - last_total_tokens}\033[0m")
            print(f"\033[93mInput tokens: {input_tokens - last_input_tokens}\033[0m")
            print(f"\033[94mTools used: {tools_name}\033[0m")
            print(f"SQL Queries used: \n\033[92m{"\n\n".join(SQL_queries)}\033[0m")
            last_total_tokens = total_tokens
            last_input_tokens = input_tokens
    finally:
        driver.close()
        db_conn.close()

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

def test_sql_result_loop(loops=10):

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
    #Execute # times the query
    for i in range(loops-1):
        out = run_yaml_llm_question(question, conn=conn, only_data=True)
        if type(out) == pd.DataFrame:
            print(f"{out.to_markdown()}\n")
        else:
            print(f"{out['answer']}")
            conn = db.get_db_connect()

def run_tests(loops=100):
    result = []
    for yaml_agent in [True, False]:
        for question in QUESTION_SUGGESTIONS:
            accuracies = []
            usages = []
            time_start = time.time()
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(check_question, question, yaml_agent) for _ in range(loops)]
                for future in futures:
                    accuracy, tokens = future.result()
                    accuracies.append(accuracy)
                    usages.append(tokens)
            print(f"Average accuracy for \033[94m{'yaml' if yaml_agent else 'semantic layer'} agent\033[0m for question \033[94m{question['question']}\033[0m: \033[92m{sum(accuracies) / loops}\033[0m [~{sum(usages) / loops} tokens]")
            result.append({
                "question": question["question"],
                "agent": "yaml" if yaml_agent else "semantic layer",
                "accuracy": round(sum(accuracies) / loops * 100, 2),
                "tokens": round(sum(usages) / loops),
                "time": round((time.time() - time_start) / loops, 2)
            })
    #Compare result for similar questions
    for i in range(len(result)):
        for j in range(i + 1, len(result)):
            if result[i]["question"] == result[j]["question"]:
                print(f"Question \033[94m{result[i]['question']}\033[0m")
                if result[i]["accuracy"] > result[j]["accuracy"]:
                    colori = "92"
                    colorj = "91"
                elif result[i]["accuracy"] < result[j]["accuracy"]:
                    colori = "91"
                    colorj = "92"
                else:
                    colori = "92"
                    colorj = "92"
                print(f"Accuracy: \033[{colori}m{result[i]['agent']} ({result[i]['accuracy']}%)\033[0m vs \033[{colorj}m{result[j]['agent']} ({result[j]['accuracy']}%)\033[0m")
                if result[i]["tokens"] < result[j]["tokens"]:
                    colori = "92"
                    colorj = "91"
                elif result[i]["tokens"] > result[j]["tokens"]:
                    colori = "91"
                    colorj = "92"
                else:
                    colori = "92"
                    colorj = "92"
                print(f"Tokens: \033[{colori}m{result[i]['agent']} ({result[i]['tokens']})\033[0m vs \033[{colorj}m{result[j]['agent']} ({result[j]['tokens']})\033[0m")
                if result[i]["time"] < result[j]["time"]:
                    colori = "92"
                    colorj = "91"
                elif result[i]["time"] > result[j]["time"]:
                    colori = "91"
                    colorj = "92"
                else:
                    colori = "92"
                    colorj = "92"
                print(f"Time: \033[{colori}m{result[i]['agent']} ({result[i]['time']}s)\033[0m vs \033[{colorj}m{result[j]['agent']} ({result[j]['time']}s)\033[0m")

if __name__ == "__main__":
    if os.getenv("LOCAL_MODEL") == "true":
        print("\033[91mTesting YAML Grounding\033[0m")
        test_yaml_grounding()
        print("\033[91mTesting RAW SQL Result 5 times\033[0m")
        test_sql_result_loop(loops=5)
        print("\033[91mTesting Agent\033[0m")
        test_agent()
    else:
        print("\033[91mRunning benchmark with 100 resamples (very long)\033[0m")
        run_tests(loops=100)