import neo4jHelpers.database as neo4jdb
from langchain_ollama import OllamaEmbeddings
from dotenv import load_dotenv

load_dotenv(override=True)

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSIONS = 768

def update() -> bool:
    embeddingModel = OllamaEmbeddings(model="nomic-embed-text", dimensions=EMBEDDING_DIMENSIONS)
    driver = neo4jdb.getDriver()
    EmbeddingsCount=0
    with driver.session() as session:
        query = """
        MATCH (e:Term | Column)
        WHERE e.embedding IS NOT NULL
        RETURN 
        elementId(e) as id, 
        coalesce(e.name || " " || e.tableName, e.name || ": " || e.definition) as text
        """
        result = session.run(query)
        for record in result:
            embedding = embeddingModel.embed_query(record["text"])
            params = {"id": record["id"], "embedding": embedding}
            session.run("MATCH (e:Term | Column) WHERE elementId(e) = $id SET e.localEmbedding = $embedding", params)
            EmbeddingsCount += 1
        session.run(f"""
            CREATE VECTOR INDEX column_similarity_local IF NOT EXISTS
                FOR (c:Column)
                ON c.localEmbedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
        session.run(f"""
            CREATE VECTOR INDEX term_similarity_local IF NOT EXISTS
                FOR (t:Term)
                ON t.localEmbedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
    return EmbeddingsCount

if __name__ == "__main__":
    EmbeddingsCount = update()
    print(f"Added {EmbeddingsCount} local embeddings")