import structlog
from typing import List
from src.config import settings

logger = structlog.get_logger(__name__)

class Embedder:
    """
    Responsible for generating embeddings for chunks and query texts.
    Leverages Gemini (Google GenAI) depending on configured settings,
    with a local fallback for testing.
    """
    def __init__(self):
        self.use_mock = True
        
        if settings.GEMINI_API_KEY:
            logger.info("Initializing Google Gemini Embedder client")
            try:
                from google import genai
                self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
                self.use_mock = False
            except ImportError:
                logger.warn("google-genai package not found. Using fallback embeddings.")
                

        if self.use_mock:
            logger.warn("No active LLM credentials. Using mock embedding helper (dimension=768)")

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        """
        if self.use_mock:
            # Simple deterministic projection for mock testing
            import numpy as np
            words = text.split()
            seed = sum(ord(c) for c in text) % 1000
            rng = np.random.default_rng(seed)
            return rng.normal(size=768).tolist()

        try:
            # Call Google GenAI Embed API
            response = self.client.models.embed_content(
                model="text-embedding-004",
                contents=text
            )
            # response.embeddings holds the list of embeddings
            return response.embeddings[0].values
                
        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            # Fallback to mock vector rather than crashing
            import numpy as np
            return np.zeros(768).tolist()

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        """
        return [self.get_embedding(t) for t in texts]
