import neo4j
import pandas as pd

SCHEMA_QUERY = """
CALL db.schema.visualization() yield nodes, relationships
UNWIND relationships AS rel
RETURN 
    type(rel) AS relationshipType,
    elementId(startNode(rel)) AS sourceNodeId,
    labels(startNode(rel)) AS sourceLabels,
    elementId(endNode(rel)) AS targetNodeId,
    labels(endNode(rel)) AS targetLabels,
    properties(rel) as relProperties,
    properties(startNode(rel)) as sourceNodeProperties,
    properties(endNode(rel)) as endNodeProperties
"""

def get_model(driver: neo4j.Driver) -> pd.DataFrame:
    result = driver.execute_query(
        SCHEMA_QUERY,
        result_transformer_=neo4j.Result.to_df
    )
    return result

CONTEXT_QUERY = """
CALL () {
            CALL db.index.vector.queryNodes('column_similarity', 10, $queryEmbedding)
            YIELD node, score
            WHERE score > 0.7
            WITH node as column, score
            MATCH (column)<-[:HAS_COLUMN]-(table:Table)
            RETURN DISTINCT table
            UNION
            CALL db.index.vector.queryNodes('term_similarity', 10, $queryEmbedding)
            YIELD node, score
            WHERE score > 0.65
            WITH node as entryTerm, score
            MATCH (entryTerm)-[:HAS_TERM*0..]->(:Term)-[:DEFINES|HAS_COLUMN*1..2]->(c:Column)
            MATCH (c)<-[:HAS_COLUMN]-(table:Table)
            RETURN DISTINCT table
            }
WITH collect(table) as tables
UNWIND tables as sourceTable
UNWIND tables as targetTable
WITH sourceTable, targetTable
CALL (sourceTable, targetTable) {
  OPTIONAL MATCH links = (sourceTable)-->(:Column)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(:ForeignKey)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(:Column)<--(targetTable)
  RETURN links
  UNION 
  OPTIONAL MATCH links = (sourceTable)-->(:Column)-[:REFERENCES]-(:Column)<--(targetTable)
  RETURN links
}
WITH links, sourceTable as table
MATCH p=(:Schema)-[:CONTAINS_TABLE]->(table)-[:HAS_COLUMN]->(column:Column)
OPTIONAL MATCH termCol = (:Term)-[:HAS_TERM*0..]->(:Term)-[:DEFINES]->(column)
OPTIONAL MATCH termTable = (:Term)-[:HAS_TERM*0..]->(:Term)-[:DEFINES]->(table)
WITH collect(links)+collect(p)+collect(termCol)+collect(termTable) as allpath
UNWIND allpath as path
CALL (path) {
    WITH nodes(path) as nodes
    UNWIND nodes as node
    RETURN "NODE" as class, elementId(node) as id, labels(node) as labels, "" as type, "" as source, "" as target, apoc.map.removeKey(properties(node), "embedding") as properties
    UNION
    WITH relationships(path) as rels
    UNWIND rels as rel
    RETURN "REL"  as class, "" as id, [] as labels, type(rel) as type, elementId(startNode(rel)) AS source, elementId(endNode(rel)) AS target, properties(rel) as properties
}
RETURN DISTINCT class, id, labels, type, source, target, properties
"""

def get_context_graph(driver: neo4j.Driver, embedding: list) -> pd.DataFrame:
    result = driver.execute_query(
        CONTEXT_QUERY,
        queryEmbedding=embedding,
        result_transformer_=neo4j.Result.to_df
    )
    return result
        
