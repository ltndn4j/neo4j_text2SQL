import neo4j
import pandas as pd

SCHEMA_QUERY = """
CALL db.schema.visualization() yield nodes, relationships
UNWIND relationships AS rel
RETURN 
    type(rel) AS relationshipType,
    elementId(startNode(rel)) AS sourceNodeId,
    labels(startNode(rel))[0] AS sourceLabels,
    elementId(endNode(rel)) AS targetNodeId,
    labels(endNode(rel))[0] AS targetLabels
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
            WHERE score > 0.6
            WITH node as column, score
            MATCH p1 = (column)<-[hc:HAS_COLUMN]-(table:Table)
            OPTIONAL MATCH p2 = (term:Term)-[d:DEFINED]->(column)
            RETURN DISTINCT p1, p2
            UNION
            CALL db.index.vector.queryNodes('term_similarity', 10, $queryEmbedding)
            YIELD node, score
            WHERE score > 0.6
            WITH node as entryTerm, score
            MATCH p1 = (entryTerm)-[HAS_TERM]->+(term:Term)-[d:DEFINED]->(target)
            OPTIONAL MATCH p2 = (target)-[hc:HAS_COLUMN]->(c:Column)
            RETURN DISTINCT p1, p2
            }
WITH collect(p1)+collect(p2) as allpath
UNWIND allpath as path
CALL (path) {
    WITH nodes(path) as nodes
    UNWIND nodes as node
    RETURN "NODE" as type, elementId(node) as id, labels(node)[0] as label, node.name as name, "" as source, "" as target
    UNION
    WITH relationships(path) as rels
    UNWIND rels as rel
    RETURN "REL"  as type, "" as id, type(rel) as label, "" as name, elementId(startNode(rel)) AS source, elementId(endNode(rel)) AS target
}
RETURN type, id, label, name, source, target
"""

def get_context_graph(driver: neo4j.Driver, embedding: list) -> pd.DataFrame:
    result = driver.execute_query(
        CONTEXT_QUERY,
        queryEmbedding=embedding,
        result_transformer_=neo4j.Result.to_df
    )
    return result
        
