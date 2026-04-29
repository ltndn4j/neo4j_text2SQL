from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from agent import create_executor
from LLM import compare_answer_accuracy
import neo4jHelpers.database as neo4jdb
import tools.postgresqlTool as db
import json
from concurrent.futures import ThreadPoolExecutor

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
        validation = compare_answer_accuracy(db_conn, question["columns_to_compare"], question["reference_sql"], get_sql_query(steps), get_answer(steps))
        accuracy = 0 if validation["average_accuracy"] is None or validation["average_accuracy"] < 0 else validation["average_accuracy"]
        usage_data =  json.loads(json.dumps(getattr(cb, "usage_metadata", None), default=str))
        modelName = list(usage_data.keys())[0]
        tokens = usage_data[modelName]["total_tokens"]
    finally:
        db_conn.close()
        driver.close()
    return accuracy, tokens

def run_tests():
    result = []
    for yaml_agent in [True, False]:
        for question in QUESTION_SUGGESTIONS:
            accuracies = []
            usages = []
            loops = 10
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
                "accuracy": sum(accuracies) / loops,
                "tokens": sum(usages) / loops
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
                print(f"Accuracy: \033[{colori}m{result[i]['agent']} ({result[i]['accuracy']})\033[0m vs \033[{colorj}m{result[j]['agent']} ({result[j]['accuracy']})\033[0m")
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

if __name__ == "__main__":
    run_tests()