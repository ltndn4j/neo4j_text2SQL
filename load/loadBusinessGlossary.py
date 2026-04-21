import neo4j
from dotenv import load_dotenv
from aura.setupAura import getInstanceId
import os
import openai
import json

load_dotenv(override=True)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

def load_terms(session: neo4j.GraphDatabase.driver, parentTerm: str, business_glossary: list):
    for term in business_glossary:
        table_name = None
        column_name = None
        embedding = openai.embeddings.create(
            input=f"{term['term']}: {term['definition']}",
            model=EMBEDDING_MODEL
        ).data[0].embedding

        cypher=f"""
            MERGE (t:Term {{name: $term}})
            {f"MERGE (p:Term {{name: $parentTerm}}) MERGE (p)-[:HAS_TERM]->(t)" if parentTerm else ""}
            SET t.definition = $definition
            SET t.embedding = $embedding
        """
        params={
            "parentTerm": parentTerm,
            "term": term["term"],
            "definition": term["definition"],
            "embedding": embedding
        }
        session.run(cypher, params)

        if term.get("technical_mappings"):
            for mapping in term["technical_mappings"]:
                table_name = mapping["table"]
                if mapping.get("column"): 
                    column_name = mapping["column"]
                    targetNode = "MERGE (x:Column {tableName: $table_name, name: $column_name})"
                else:
                    targetNode = "MERGE (x:Table {name: $table_name})"
                cypher=f"""
                    MERGE (t:Term {{name: $term}})
                    {targetNode} 
                    MERGE (t)-[:DEFINES]->(x)
                """
                params={
                    "term": term["term"],
                    "table_name": table_name,
                    "column_name": column_name
                }
                session.run(cypher, params)
        
        if term.get("terms"):
            load_terms(session, term["term"], term["terms"])

def load():
    #Connect to the Neo4j database
    neo4j_config = getInstanceId("875a99c2-d2e2-4bf6-8ddb-78dcc7d2fecc","text2sql-instance")
    neo4j_uri = neo4j_config["neo4j_uri"]
    neo4j_username = neo4j_config["neo4j_username"]
    neo4j_password = neo4j_config["neo4j_password"] or os.getenv('neo4j_password')
    driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
    session = driver.session()

    #add vector index if no exists
    session.run(f"""
    CREATE VECTOR INDEX term_similarity IF NOT EXISTS
        FOR (t:Term)
        ON t.embedding
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                `vector.similarity_function`: 'cosine'
            }}
        }}
    """)

    with open("data/business_glossary.json", "r") as f:
        glossary = json.load(f)
    
    load_terms(session, None, glossary)
    session.close()