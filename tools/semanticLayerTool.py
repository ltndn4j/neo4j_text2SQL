from langchain_core.tools import tool
import neo4j
import openai
import json

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

def create_semantic_tools(driver: neo4j.Driver, threshold: float,context: dict = None):

    @tool
    def glossary_columns_and_joins(query: str) -> str:
        """
        Get the metadata schema by semantic similarity to the query. Most likely the entry point to know how to query the dataset.
        Uses embedding based semantic similarity and graph traversal to find the most similar metadata schema.
        """
        q = (query or "").strip()
        if not q:
            return "Provide a non-empty query."

        embedding = openai.embeddings.create(input=q, model=EMBEDDING_MODEL).data[0].embedding
        if isinstance(context, dict):
            context["embedding"] = embedding
            context["question"] = q
        cypher="""
CYPHER 25
CALL () {
    MATCH (column:Column)
        SEARCH column IN (VECTOR INDEX column_similarity FOR $queryEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold
    RETURN DISTINCT column
    UNION
    MATCH (entryTerm:Term)
        SEARCH entryTerm IN (VECTOR INDEX term_similarity FOR $queryEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold
    MATCH (entryTerm)-[:HAS_TERM*0..]->(:Term)-[:DEFINES|HAS_COLUMN*1..2]->(column:Column)
    RETURN DISTINCT column
}
WITH collect(column) as columns
UNWIND columns as sourceColumn
UNWIND columns as targetColumn
WITH sourceColumn, targetColumn
CALL (sourceColumn, targetColumn) {
    OPTIONAL MATCH (fromSchema:Schema)-->(:Table {name:sourceColumn.tableName})-->(fromColumn:Column)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(:ForeignKey)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(toColumn:Column)<--(:Table {name:targetColumn.tableName})<--(toSchema:Schema)
    RETURN fromSchema, fromColumn, toSchema, toColumn
    UNION 
    OPTIONAL MATCH (fromSchema:Schema)-->(:Table {name:sourceColumn.tableName})-->(fromColumn:Column)-[:REFERENCES]-(toColumn:Column)<--(:Table {name:targetColumn.tableName})<--(toSchema:Schema)
    RETURN fromSchema, fromColumn, toSchema, toColumn
}
WITH DISTINCT sourceColumn as columnSimilarity, fromSchema, fromColumn, toSchema, toColumn
WITH columnSimilarity, 
CASE 
  WHEN toSchema IS NULL THEN NULL
  ELSE {
    source:{schema:fromSchema.name, table:fromColumn.tableName, column:fromColumn.name},
    target:{schema:toSchema.name, table:toColumn.tableName, column:toColumn.name}
  }
END as join
WITH columnSimilarity, collect(join) as table_joins

// Reach out to Schema and Database context
MATCH (db:Database)-[:CONTAINS_SCHEMA]->(schema:Schema)-[:CONTAINS_TABLE]->(table:Table)-[:HAS_COLUMN]->(columnSimilarity)
MATCH (table)-[:HAS_COLUMN]->(column:Column)

// Aggregate Column details
OPTIONAL MATCH (:Term)-[:HAS_TERM*0..]->(tc:Term)-[:DEFINES]->(column)
OPTIONAL MATCH (column)-[:HAS_VALUE]->(v:Value)

WITH db, schema, table, table_joins, column, 
     collect(DISTINCT tc.definition) as col_terms, 
     collect(DISTINCT v.value) as col_values

WITH db, schema, table, table_joins, 
     collect({
       name: column.name,
       type: column.type,
       description: col_terms,
       sample_values: col_values
     }) as columns

// Final formatting
OPTIONAL MATCH (:Term)-[:HAS_TERM*0..]->(tt:Term)-[:DEFINES]->(table)

RETURN {
    database: db.name,
    schema: schema.name,
    table_name: table.name,
    table_comment: table.comment,
    table_description: tt.definition,
    table_joins: table_joins,
    columns: columns
} as result
"""

        with driver.session() as session:
            session.run(
                "MERGE (le:LastExecution) SET le.toolEmbedding = $embedding, le.agentQuestion = $q", 
                {"embedding": embedding, "q": q}
            )
            result = session.run(cypher, {"queryEmbedding":embedding, "threshold":threshold})
            result_list = [row.data()['result'] for row in result]
            return json.dumps(result_list)
    return [glossary_columns_and_joins]
