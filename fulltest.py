from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from agent import create_executor
from LLM import compare_answer_accuracy
import neo4jHelpers.database as neo4jdb
import tools.postgresqlTool as db
import json
import time
from concurrent.futures import ThreadPoolExecutor

QUESTION_SUGGESTIONS = json.load(open("data/reference_questions.json"))
def get_sql_query(steps: list):
    tools = [tool for sublist in [step.tool_calls for step in steps if isinstance(step, AIMessage)] for tool in sublist]
    SQL_queries = [tool["args"].get("query") for tool in tools if tool["name"] == "run_sql"]
    return SQL_queries

def get_answer(steps: list):
    final_answer = str(steps[-1])
    for step in steps:
        if isinstance(step, AIMessage):
            for content in step.content:
                if content.get("phase") == "final_answer":
                    final_answer = content["text"]
    return str(final_answer)

def check_question(question: dict, yaml_agent: bool):
    cb = UsageMetadataCallbackHandler()
    driver = neo4jdb.getDriver()
    db_conn = db.get_db_connect()
    try:
        executor = create_executor(driver,db_conn,cb,0.7,yaml_agent=yaml_agent)
        result = executor.invoke({"messages": [HumanMessage(content=question["question"])]})
        steps = result.get("messages", [])
        reference_sql = "\n".join(question["reference_sql_lines"])
        validation = compare_answer_accuracy(db_conn, question["columns_to_compare"], reference_sql, get_sql_query(steps), get_answer(steps))
        usage_data =  json.loads(json.dumps(getattr(cb, "usage_metadata", None), default=str))
        modelName = list(usage_data.keys())[0]
        tokens = usage_data[modelName]["total_tokens"]
    finally:
        db_conn.close()
        driver.close()
    return validation["accuracy"], tokens

def run_tests():
    result = []
    for yaml_agent in [True, False]:
        for question in QUESTION_SUGGESTIONS:
            accuracies = []
            usages = []
            loops = 100
            time_start = time.time()
            with ThreadPoolExecutor(max_workers=10) as executor:
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
    run_tests()