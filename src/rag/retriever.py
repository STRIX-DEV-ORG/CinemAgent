import structlog
from typing import List, Dict, Any
from src.db.clickhouse_client import get_clickhouse_client
from src.rag.embedder import Embedder
from src.graph.graph_manager import GraphManager

logger = structlog.get_logger(__name__)

class Retriever:
    """
    Orchestrates Hybrid RAG Retrieval:
    1. Vector Retrieval in ClickHouse
    2. Knowledge Graph neighborhood querying in ClickHouse
    """
    def __init__(self):
        try:
            self.client = get_clickhouse_client()
        except Exception as e:
            logger.warning("Retriever running in offline/disconnected mode", error=str(e))
            self.client = None
        self.embedder = Embedder()
        self.graph_manager = GraphManager()

    def vector_search(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Query Clickhouse using vector similarity.
        Uses native Clickhouse 'cosineDistance' calculations.
        """
        logger.info("Performing vector search", query=query_text)
        try:
            query_vector = self.embedder.get_embedding(query_text)
            
            # Clickhouse SQL query calculating distance
            # order by distance ascending (where 0 is identical, 2 is diametrically opposite)
            sql = """
            SELECT 
                id, 
                document_id,
                chunk_index,
                content, 
                metadata,
                cosineDistance(embedding, {vector:Array(Float32)}) AS distance
            FROM document_chunks
            ORDER BY distance ASC
            LIMIT {limit:UInt32}
            """
            params = {
                "vector": query_vector,
                "limit": limit
            }
            result = self.client.query(sql, parameters=params)
            
            hits = []
            for row in result.result_rows:
                hits.append({
                    "id": str(row[0]),
                    "document_id": row[1],
                    "chunk_index": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "distance": float(row[5])
                })
            return hits
        except Exception as e:
            logger.error("Vector search failed in ClickHouse", error=str(e))
            return []

    def extract_entities_stub(self, query_text: str) -> List[str]:
        """
        Simple entities extractor stub.
        In production, use named entity recognition (NER) or LLM calls.
        For this skeleton, we split by capitalized words and filter out common stopwords.
        """
        words = query_text.replace("?", "").replace(".", "").replace(",", "").split()
        stopwords = {"a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "or", "is", "are", "was", "were", "what", "who", "where", "how", "movie", "film"}
        entities = []
        for w in words:
            if w.istitle() or w.isupper() or len(w) > 4:
                cleaned = w.lower()
                if cleaned not in stopwords:
                    entities.append(cleaned)
        return list(set(entities))

    def retrieve_context(self, query_text: str, limit: int = 5) -> Dict[str, Any]:
        """
        Retrieve combined Vector and Graph Context.
        """
        logger.info("Executing Hybrid RAG retrieval", query=query_text)
        
        # 1. Vector Search
        vector_hits = self.vector_search(query_text, limit=limit)
        vector_context = "\n\n".join([f"Source: {hit['document_id']} (Chunk {hit['chunk_index']})\nContent: {hit['content']}" for hit in vector_hits])
        
        # 2. Graph Search
        entities = self.extract_entities_stub(query_text)
        graph_context = self.graph_manager.get_graph_neighborhood_context(entities)
        
        combined_context = (
            f"=== SEMANTIC VECTOR CONTEXT ===\n"
            f"{vector_context or 'No semantic document matches found.'}\n\n"
            f"=== KNOWLEDGE GRAPH RELATIONSHIPS ===\n"
            f"{graph_context}\n"
        )
        
        return {
            "combined_context": combined_context,
            "vector_hits": vector_hits,
            "graph_entities": entities
        }
