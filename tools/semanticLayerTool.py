from langchain_core.tools import tool
import neo4j
import openai
import json

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

CYPHER_SIMILARITY_QUERY_BASE = """CYPHER 25
CALL () {
    MATCH (column:Column)
        SEARCH column IN (VECTOR INDEX column_similarity FOR $userEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold
    RETURN DISTINCT column
    UNION
    MATCH (entryTerm:Term)
        SEARCH entryTerm IN (VECTOR INDEX term_similarity FOR $userEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold-0.1
    MATCH (entryTerm)-[:HAS_TERM*0..]->(:Term)-[:DEFINES|HAS_COLUMN*1..2]->(column:Column)
    RETURN DISTINCT column
    UNION
    MATCH (column:Column)
        SEARCH column IN (VECTOR INDEX column_similarity FOR $agentEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold
    RETURN DISTINCT column
    UNION
    MATCH (entryTerm:Term)
        SEARCH entryTerm IN (VECTOR INDEX term_similarity FOR $agentEmbedding LIMIT 10) SCORE as score
        WHERE score>$threshold-0.1
    MATCH (entryTerm)-[:HAS_TERM*0..]->(:Term)-[:DEFINES|HAS_COLUMN*1..2]->(column:Column)
    RETURN DISTINCT column
}
WITH collect(DISTINCT column) as columns
UNWIND columns as sourceColumn
UNWIND columns as targetColumn
WITH sourceColumn, targetColumn
OPTIONAL MATCH links = SHORTEST 1
    (:Table {name:sourceColumn.tableName})
    (()-[:HAS_COLUMN|HAS_FOREIGN_KEY|ON_COLUMN|REFERENCES]-(x)){0,16}
    (targetTable:Table {name:targetColumn.tableName})
"""

def create_semantic_tools(driver: neo4j.Driver, threshold: float,context: dict = None):

    @tool
    def glossary_columns_and_joins(user_query: str, agent_query: str = None) -> str:
        """
        Get the metadata schema by semantic similarity to the query. Most likely the entry point to know how to query the dataset.
        You must be able to answer the question with the metadata returned by this tool.
        * On user_query, provide the question exactly as it is asked by the user, without any pre-processing. 
        * On agent_query, provide the question as it is processed by the agent, which may include additional context or reformulation.
        """
        if not user_query.strip():
            return "Provide a non-empty query."

        user_embedding = openai.embeddings.create(input=user_query, model=EMBEDDING_MODEL).data[0].embedding
        agent_embedding = openai.embeddings.create(input=user_query, model=EMBEDDING_MODEL).data[0].embedding
        if isinstance(context, dict):
            context["embeddings"] = {"user":user_embedding, "agent": agent_embedding}
            context["question"] = agent_query
        cypher=CYPHER_SIMILARITY_QUERY_BASE + """
WITH DISTINCT sourceColumn as columnSimilarity, targetTable, [step in x[..-1] where step:Column or step:Table | step] as path
UNWIND range(0, CASE WHEN size(path)=0 THEN 0 ELSE size(path) - 2 END) AS i
WITH DISTINCT columnSimilarity, targetTable, path, i, CASE WHEN path is null THEN NULL ELSE path[i] END AS current, CASE WHEN path is null THEN NULL ELSE path[i+1] END AS next
WHERE (current:Column AND next:Column) OR size(path)=0 
WITH DISTINCT 
  columnSimilarity, 
  targetTable, 
  collect({
    from_schema: current.schemaName,
    from_table: current.tableName, 
    from_column: current.name,
    to_schema: next.schemaName, 
    to_table:next.tableName, 
    to_column: next.name
  }) as join_path
WITH columnSimilarity, 
  collect(
  CASE
    WHEN targetTable IS NULL OR targetTable.name=columnSimilarity.tableName THEN NULL
    ELSE {
     targetTable:targetTable.name,
     join_path:join_path
    }
  END) AS table_joins
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
       definition: col_terms,
       sample_values: col_values
     }) as columns

// Final formatting
OPTIONAL MATCH (:Term)-[:HAS_TERM*0..]->(tt:Term)-[:DEFINES]->(table)

RETURN {
    database: db.name,
    schema: schema.name,
    table_name: table.name,
    table_description: table.comment,
    table_definition: tt.definition,
    table_joins: table_joins,
    columns: columns
} as result
"""

        with driver.session() as session:
            try:
                session.run(
                    """MERGE (le:LastExecution) 
                       SET le.userQuery = $userQ, le.agentQuery = $agentQ, le.userEmbedding = $userE, le.agentEmbedding = $agentE""",
                    {"userQ": user_query, "userE": user_embedding, "agentQ": agent_query, "agentE": agent_embedding}
                )
                result = session.run(cypher, {"userEmbedding": user_embedding, "agentEmbedding": agent_embedding, "threshold":threshold})
                result_list = [row.data()['result'] for row in result]
                return json.dumps(result_list)
            except Exception as e:
                print(f"Error during glossary_columns_and_joins: {e}")
                return {"error": "An error occurred while fetching schema information."}
    
    return [glossary_columns_and_joins]
