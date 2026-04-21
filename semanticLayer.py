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
    YIELD node, score WHERE score > $threshold + 0.05
    WITH node as column
    RETURN DISTINCT column
    UNION
    CALL db.index.vector.queryNodes('term_similarity', 10, $queryEmbedding)
    YIELD node, score WHERE score > $threshold
    WITH node as entryTerm
    MATCH (entryTerm)-[:HAS_TERM*0..]->(:Term)-[:DEFINES|HAS_COLUMN*1..2]->(column:Column)
    RETURN DISTINCT column
}
WITH collect(column) as columns
UNWIND columns as sourceColumn
UNWIND columns as targetColumn
WITH sourceColumn, targetColumn
CALL (sourceColumn, targetColumn) {
    OPTIONAL MATCH links=(fromSchema:Schema)-->(:Table {name:sourceColumn.tableName})-->(fromColumn:Column)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(:ForeignKey)-[:HAS_FOREIGN_KEY|ON_COLUMN]-(toColumn:Column)<--(:Table {name:targetColumn.tableName})<--(toSchema:Schema)
    RETURN links
    UNION 
    OPTIONAL MATCH links=(fromSchema:Schema)-->(:Table {name:sourceColumn.tableName})-->(fromColumn:Column)-[:REFERENCES]-(toColumn:Column)<--(:Table {name:targetColumn.tableName})<--(toSchema:Schema)
    RETURN links
}
WITH DISTINCT sourceColumn as column, links
MATCH p=(:Schema)-[:CONTAINS_TABLE]->(table:Table)-[:HAS_COLUMN]->(column:Column)
OPTIONAL MATCH termCol = (:Term)-[:HAS_TERM*0..]->(:Term)-[:DEFINES]->(column)
OPTIONAL MATCH termTable = (:Term)-[:HAS_TERM*0..]->(:Term)-[:DEFINES]->(table)
OPTIONAL MATCH values = (column)-[:HAS_VALUE]->(:Value)
WITH collect(links)+collect(p)+collect(termCol)+collect(termTable)+collect(values) as allpath
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

def get_context_graph(driver: neo4j.Driver, embedding: list, threshold: float) -> pd.DataFrame:
    result = driver.execute_query(
        CONTEXT_QUERY,
        {"queryEmbedding":embedding, "threshold":threshold},
        result_transformer_=neo4j.Result.to_df
    )
    return result
        
