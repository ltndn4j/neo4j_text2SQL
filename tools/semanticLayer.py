from langchain_core.tools import tool
import neo4j
import openai
import json

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

def get_neo4j_driver(neo4j_uri: str, neo4j_username: str, neo4j_password: str):
    return neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

def create_semantic_tools(driver: neo4j.Driver):

    @tool
    def glossary_columns_and_joins(query: str) -> str:
        """
        Get the metadata schema by semantic similarity to the query.
        Uses embedding based semantic similarity and graph traversal to find the most similar metadata schema.
        """
        q = (query or "").strip()
        if not q:
            return "Provide a non-empty query."
        
        embedding = openai.embeddings.create(input=q, model=EMBEDDING_MODEL).data[0].embedding

        cypher="""
            CALL () {
            CALL db.index.vector.queryNodes('column_similarity', 10, $queryEmbedding)
            YIELD node, score
            WHERE score > 0.6
            WITH node as column, score
            MATCH (column)<-[:HAS_COLUMN]-(table:Table)
            OPTIONAL MATCH (term:Term)-[:DEFINED]->(column)
            RETURN DISTINCT table, column.tableName as table_name, column.name as column_name
            UNION
            CALL db.index.vector.queryNodes('term_similarity', 10, $queryEmbedding)
            YIELD node, score
            WHERE score > 0.6
            WITH node as term, score
            MATCH (term)-[HAS_TERM]->+(:Term)-[:DEFINED]->(target)
            OPTIONAL MATCH (target)-[:HAS_COLUMN]->(c:Column)
            WITH term, target, c, score
            RETURN DISTINCT
                CASE 
                    WHEN 'Table' IN labels(target) THEN target
                    ELSE [(table)-[:HAS_COLUMN]->(target) | table][0]
                END AS table,
                CASE 
                    WHEN 'Column' IN labels(target) THEN target.tableName
                    ELSE c.name 
                END AS table_name,
                CASE 
                    WHEN 'Column' IN labels(target) THEN target.name 
                    ELSE c.name 
                END AS column_name
            }
            WITH table, table_name, column_name
            OPTIONAL MATCH (table)-[:HAS_COLUMN]-(col:Column)

            // Path 1: Direct Reference
            OPTIONAL MATCH (col)-[:REFERENCES]-(refCol:Column)

            // Path 2: Foreign Key Chain
            OPTIONAL MATCH (col)-[:HAS_FOREIGN_KEY|ON_COLUMN]-()-[:HAS_FOREIGN_KEY|ON_COLUMN]-(fkCol:Column)

            WITH table_name, column_name, col, collect(DISTINCT refCol) + collect(DISTINCT fkCol) AS linkedColumns
            UNWIND linkedColumns AS linkedColumn
            MATCH (d:Database)-[:CONTAINS_SCHEMA]->(s:Schema)-[:CONTAINS_TABLE]->(table:Table {name:table_name})
            MATCH (schemaLinkedCol:Schema)-->(:Table)-->(linkedColumn)
            WITH 
            d.name as database,
            s.name as schema,
            table_name,
            [(t:Term)-[:DEFINED]->(:Table {name:table_name}) | t.name + ": " + t.definition] as table_description,
            collect(DISTINCT {
            source:{schema:s.name, table:col.tableName, column:col.name},
            target:{schema:schemaLinkedCol.name, table:linkedColumn.tableName, column:linkedColumn.name}
            }) as table_joins,
            collect(DISTINCT {
            column_name:column_name, 
            description:[(t:Term)-[:DEFINED]->(:Column {tableName:table_name, name:column_name}) | t.name + ": " + t.definition],
            values: [(:Column {tableName:table_name, name:column_name})-[:HAS_VALUE]->(v:Value) | v.value]
            }) as columns
            RETURN {
            database:database,
            schema:schema,
            table_name:table_name,
            table_description:table_description,
            table_joins:table_joins,
            columns:columns
            } as result
        """
        with driver.session() as session:
            result = session.run(cypher, queryEmbedding=embedding)
            result_list = [row.data()['result'] for row in result]
            return json.dumps(result_list)
    return [glossary_columns_and_joins]