from tools.semanticLayerTool import get_neo4j_driver
from aura.setupAura import getInstanceId, NEO4J_INSTANCE, PROJECT_ID
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
    labels(endNode(rel)) AS targetLabels
"""

def get_context_graph(embedding: list) -> pd.DataFrame:
    neo4j_config = getInstanceId(PROJECT_ID, NEO4J_INSTANCE)
    uri = neo4j_config["neo4j_uri"]
    user = neo4j_config["neo4j_username"]
    password = neo4j_config["neo4j_password"]
    driver = get_neo4j_driver(uri, user, password)
    result = driver.execute_query(
        SCHEMA_QUERY,
        embedding=embedding,
        result_transformer_=neo4j.Result.to_df
    )
    return result
        