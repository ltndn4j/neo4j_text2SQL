import neo4j
import pandas as pd
from tools.semanticLayerTool import CYPHER_SIMILARITY_QUERY_BASE

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

CONTEXT_QUERY = CYPHER_SIMILARITY_QUERY_BASE + """
WITH DISTINCT sourceColumn as columnSimilarity, links
MATCH (table:Table)-[:HAS_COLUMN]->(columnSimilarity:Column)
MATCH p=(:Schema)-[:CONTAINS_TABLE]->(table)-[:HAS_COLUMN]->(column:Column)
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

def get_context_graph(driver: neo4j.Driver, embeddings: dict, threshold: float) -> pd.DataFrame:
    result = driver.execute_query(
        CONTEXT_QUERY,
        {"userEmbedding": embeddings["user"], "agentEmbedding": embeddings["agent"], "threshold":threshold},
        result_transformer_=neo4j.Result.to_df
    )
    return result
        
