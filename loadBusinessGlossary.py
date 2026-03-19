import neo4j
from dotenv import load_dotenv
from setupAura import getInstanceId
import os

load_dotenv(override=True)

#Connect to the Neo4j database
neo4j_config = getInstanceId("875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc","text2sql-instance")
neo4j_uri = neo4j_config["neo4j_uri"]
neo4j_username = neo4j_config["neo4j_username"]
neo4j_password = neo4j_config["neo4j_password"] or os.getenv('neo4j_password')
driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
session = driver.session()

business_glossary = [
    {
      "term": "Employee",
      "definition": "An individual currently or previously hired by the organization to perform specific roles or duties.",
      "technical_mapping": {
        "table": "employee"
      }
    },
    {
      "term": "Department",
      "definition": "A distinct functional unit or division within the organization.",
      "technical_mapping": {
        "table": "department",
      }
    },
    {
      "term": "Department Assignment",
      "definition": "The historical and current record of an employee's allocation to a specific functional department including the period during which the assignment is considered active and valid.",
      "technical_mapping": {
        "table": "department_employee"
      }
    },
    {
      "term": "Department Manager",
      "definition": "An employee designated with leadership and oversight responsibilities for a specific department within a defined timeframe.",
      "technical_mapping": {
        "table": "department_manager"
      }
    },
    {
      "term": "Job Title",
      "definition": "The formal designation or rank held by an employee, reflecting their professional role and responsibilities (e.g., 'Senior Engineer').",
      "technical_mapping": {
        "table": "title",
        "column": "title"
      }
    },
    {
      "term": "Base Salary",
      "definition": "The fixed amount of monetary compensation paid to an employee for a specific period of their employment.",
      "technical_mapping": {
        "table": "salary",
        "column": "amount"
      }
    },
    {
      "term": "Hire Date",
      "definition": "The specific calendar date on which an individual officially began their employment contract with the organization.",
      "technical_mapping": {
        "table": "employee",
        "column": "hire_date"
      }
    },
    {
      "term": "Employee Gender",
      "definition": "The gender identity of the employee as recorded for administrative and legal compliance purposes.",
      "technical_mapping": {
        "table": "employee",
        "column": "gender"
      }
    }
]

for term in business_glossary:
    technical_mapping = term["technical_mapping"]
    if technical_mapping.get("column"): 
        nodeDefined = "MERGE (x:Column {tableName: $table_name, name: $column_name})"
    else:
        nodeDefined = "MERGE (x:Table {name: $table_name})"
    
    cypher=f"""
        MERGE (t:Term {{name: $term}})
        SET t.definition = $definition
        {nodeDefined}
        MERGE (x)-[:IS_DEFINED_BY]->(t)
    """
    params={
        "term": term["term"],
        "definition": term["definition"],
        "table_name": technical_mapping["table"],
        "column_name": technical_mapping.get("column")
    }
    session.run(cypher, params)
