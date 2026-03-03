"""
Vector store integration for semantic search and memory management
Supports multiple vector database backends
"""

import os
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import logging
import numpy as np

# Vector store imports
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

try:
    import pinecone
    HAS_PINECONE = True
except ImportError:
    HAS_PINECONE = False

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False

# Embedding model imports
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from ..models.schemas import MemoryEntry, QueryRequest, QueryResult

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract base class for vector stores"""

    @abstractmethod
    async def initialize(self):
        """Initialize the vector store connection"""
        pass

    @abstractmethod
    async def add_memory(self, memory: MemoryEntry):
        """Add a single memory entry"""
        pass

    @abstractmethod
    async def add_memories(self, memories: List[MemoryEntry]):
        """Add multiple memory entries"""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        limit: int = 10
    ) -> List[QueryResult]:
        """Search for similar memories"""
        pass

    @abstractmethod
    async def update_memory(self, memory_id: str, memory: MemoryEntry):
        """Update an existing memory"""
        pass

    @abstractmethod
    async def delete_memory(self, memory_id: str):
        """Delete a memory"""
        pass

    @abstractmethod
    async def clear_client_memories(self, client_id: str):
        """Clear all memories for a client"""
        pass


class EmbeddingGenerator:
    """Generates embeddings for text using various models"""

    def __init__(self, model_type: str = "sentence-transformers", model_name: Optional[str] = None):
        self.model_type = model_type
        self.model_name = model_name or self._get_default_model()
        self._init_model()

    def _get_default_model(self) -> str:
        """Get default model based on type"""
        if self.model_type == "sentence-transformers":
            return "all-MiniLM-L6-v2"
        elif self.model_type == "openai":
            return "text-embedding-3-small"
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    def _init_model(self):
        """Initialize the embedding model"""
        if self.model_type == "sentence-transformers" and HAS_SENTENCE_TRANSFORMERS:
            self.model = SentenceTransformer(self.model_name)
        elif self.model_type == "openai" and HAS_OPENAI:
            openai.api_key = os.getenv("OPENAI_API_KEY")
            self.model = openai
        else:
            raise ValueError(f"Model type {self.model_type} not available")

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        if self.model_type == "sentence-transformers":
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        elif self.model_type == "openai":
            response = await self._call_openai_embedding(text)
            return response
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        if self.model_type == "sentence-transformers":
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        elif self.model_type == "openai":
            # OpenAI supports batch embedding
            return await self._call_openai_embeddings_batch(texts)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    async def _call_openai_embedding(self, text: str) -> List[float]:
        """Call OpenAI embedding API for single text"""
        try:
            response = self.model.embeddings.create(
                model=self.model_name,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            return []

    async def _call_openai_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Call OpenAI embedding API for batch"""
        try:
            response = self.model.embeddings.create(
                model=self.model_name,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI batch embedding error: {e}")
            return [[] for _ in texts]


class ChromaVectorStore(VectorStore):
    """ChromaDB vector store implementation"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.collection_name = config.get("collection_name", "website_memory")
        self.embedding_generator = EmbeddingGenerator(
            model_type=config.get("embedding_model_type", "sentence-transformers")
        )
        self.client = None
        self.collection = None

    async def initialize(self):
        """Initialize ChromaDB connection"""
        if not HAS_CHROMA:
            raise ImportError("ChromaDB not installed")

        # Configure ChromaDB
        settings = Settings(
            chroma_server_host=self.config.get("host", "localhost"),
            chroma_server_http_port=self.config.get("port", 8000)
        )

        # Create client
        if self.config.get("persist_directory"):
            self.client = chromadb.PersistentClient(
                path=self.config["persist_directory"],
                settings=settings
            )
        else:
            self.client = chromadb.HttpClient(
                host=settings.chroma_server_host,
                port=settings.chroma_server_http_port
            )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Website navigation memory"}
        )

        logger.info(f"ChromaDB initialized with collection: {self.collection_name}")

    async def add_memory(self, memory: MemoryEntry):
        """Add a single memory entry"""
        # Generate embedding
        embedding = await self.embedding_generator.generate_embedding(memory.text)

        # Prepare metadata
        metadata = memory.metadata.dict() if hasattr(memory.metadata, 'dict') else memory.metadata
        metadata = self._clean_metadata(metadata)

        # Add to collection
        self.collection.add(
            ids=[memory.memory_id],
            embeddings=[embedding],
            documents=[memory.text],
            metadatas=[metadata]
        )

    async def add_memories(self, memories: List[MemoryEntry]):
        """Add multiple memory entries"""
        if not memories:
            return

        # Generate embeddings for all texts
        texts = [m.text for m in memories]
        embeddings = await self.embedding_generator.generate_embeddings(texts)

        # Prepare data
        ids = [m.memory_id for m in memories]
        metadatas = [
            self._clean_metadata(m.metadata.dict() if hasattr(m.metadata, 'dict') else m.metadata)
            for m in memories
        ]

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

        logger.info(f"Added {len(memories)} memories to ChromaDB")

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        limit: int = 10
    ) -> List[QueryResult]:
        """Search for similar memories"""
        # Generate query embedding
        query_embedding = await self.embedding_generator.generate_embedding(query)

        # Build where clause for filtering
        where_clause = self._build_where_clause(filters)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            where=where_clause,
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        # Convert to QueryResult objects
        query_results = []
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                result = QueryResult(
                    memory_id=results['ids'][0][i],
                    text=results['documents'][0][i],
                    score=1.0 - results['distances'][0][i],  # Convert distance to similarity
                    metadata=results['metadatas'][0][i] if results['metadatas'] else None
                )
                query_results.append(result)

        return query_results

    async def update_memory(self, memory_id: str, memory: MemoryEntry):
        """Update an existing memory"""
        # Delete old version
        await self.delete_memory(memory_id)
        # Add new version
        await self.add_memory(memory)

    async def delete_memory(self, memory_id: str):
        """Delete a memory"""
        self.collection.delete(ids=[memory_id])

    async def clear_client_memories(self, client_id: str):
        """Clear all memories for a client"""
        where_clause = {"client_id": {"$eq": client_id}}
        self.collection.delete(where=where_clause)

    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Clean metadata for ChromaDB compatibility"""
        cleaned = {}
        for key, value in metadata.items():
            # ChromaDB doesn't support None values
            if value is None:
                continue

            # Convert datetime to string
            if hasattr(value, 'isoformat'):
                cleaned[key] = value.isoformat()
            # Convert lists to JSON strings
            elif isinstance(value, list):
                cleaned[key] = json.dumps(value)
            # Keep strings and numbers
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value

        return cleaned

    def _build_where_clause(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build ChromaDB where clause from filters"""
        where = {}

        if filters.get("client_id"):
            where["client_id"] = {"$eq": filters["client_id"]}

        if filters.get("role_id"):
            where["role_id"] = {"$eq": filters["role_id"]}

        if filters.get("feature_id"):
            where["feature_id"] = {"$eq": filters["feature_id"]}

        if filters.get("priority"):
            where["priority"] = {"$eq": filters["priority"]}

        return where


class PineconeVectorStore(VectorStore):
    """Pinecone vector store implementation"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.index_name = config.get("index_name", "website-memory")
        self.embedding_generator = EmbeddingGenerator(
            model_type=config.get("embedding_model_type", "openai")
        )
        self.index = None

    async def initialize(self):
        """Initialize Pinecone connection"""
        if not HAS_PINECONE:
            raise ImportError("Pinecone not installed")

        # Initialize Pinecone
        pinecone.init(
            api_key=os.getenv("PINECONE_API_KEY"),
            environment=os.getenv("PINECONE_ENVIRONMENT")
        )

        # Create index if it doesn't exist
        if self.index_name not in pinecone.list_indexes():
            pinecone.create_index(
                self.index_name,
                dimension=self._get_embedding_dimension(),
                metric="cosine"
            )

        # Connect to index
        self.index = pinecone.Index(self.index_name)
        logger.info(f"Pinecone initialized with index: {self.index_name}")

    def _get_embedding_dimension(self) -> int:
        """Get embedding dimension based on model"""
        model_dimensions = {
            "all-MiniLM-L6-v2": 384,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072
        }
        return model_dimensions.get(self.embedding_generator.model_name, 1536)

    async def add_memory(self, memory: MemoryEntry):
        """Add a single memory entry"""
        embedding = await self.embedding_generator.generate_embedding(memory.text)

        # Prepare metadata
        metadata = memory.metadata.dict() if hasattr(memory.metadata, 'dict') else memory.metadata
        metadata = self._clean_metadata_for_pinecone(metadata)
        metadata["text"] = memory.text  # Store text in metadata

        # Upsert to Pinecone
        self.index.upsert([(memory.memory_id, embedding, metadata)])

    async def add_memories(self, memories: List[MemoryEntry]):
        """Add multiple memory entries"""
        if not memories:
            return

        # Generate embeddings
        texts = [m.text for m in memories]
        embeddings = await self.embedding_generator.generate_embeddings(texts)

        # Prepare vectors
        vectors = []
        for memory, embedding in zip(memories, embeddings):
            metadata = memory.metadata.dict() if hasattr(memory.metadata, 'dict') else memory.metadata
            metadata = self._clean_metadata_for_pinecone(metadata)
            metadata["text"] = memory.text

            vectors.append((memory.memory_id, embedding, metadata))

        # Batch upsert
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            self.index.upsert(batch)

        logger.info(f"Added {len(memories)} memories to Pinecone")

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        limit: int = 10
    ) -> List[QueryResult]:
        """Search for similar memories"""
        # Generate query embedding
        query_embedding = await self.embedding_generator.generate_embedding(query)

        # Build filter
        pinecone_filter = self._build_pinecone_filter(filters)

        # Search
        results = self.index.query(
            vector=query_embedding,
            filter=pinecone_filter,
            top_k=limit,
            include_metadata=True
        )

        # Convert to QueryResult objects
        query_results = []
        for match in results.matches:
            metadata = match.metadata
            text = metadata.pop("text", "")

            result = QueryResult(
                memory_id=match.id,
                text=text,
                score=match.score,
                metadata=metadata
            )
            query_results.append(result)

        return query_results

    async def update_memory(self, memory_id: str, memory: MemoryEntry):
        """Update an existing memory"""
        await self.add_memory(memory)  # Pinecone upsert handles updates

    async def delete_memory(self, memory_id: str):
        """Delete a memory"""
        self.index.delete(ids=[memory_id])

    async def clear_client_memories(self, client_id: str):
        """Clear all memories for a client"""
        # Pinecone doesn't support bulk delete by metadata
        # Need to query and delete
        results = self.index.query(
            vector=[0] * self._get_embedding_dimension(),
            filter={"client_id": client_id},
            top_k=10000,
            include_metadata=False
        )

        if results.matches:
            ids = [match.id for match in results.matches]
            self.index.delete(ids=ids)

    def _clean_metadata_for_pinecone(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Clean metadata for Pinecone compatibility"""
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                continue

            # Convert datetime to string
            if hasattr(value, 'isoformat'):
                cleaned[key] = value.isoformat()
            # Keep strings and numbers
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            # Convert lists to strings
            elif isinstance(value, list):
                cleaned[key] = json.dumps(value)

        return cleaned

    def _build_pinecone_filter(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build Pinecone filter from query filters"""
        pinecone_filter = {}

        for key, value in filters.items():
            if value is not None:
                pinecone_filter[key] = value

        return pinecone_filter if pinecone_filter else None


class VectorStoreFactory:
    """Factory for creating vector store instances"""

    @staticmethod
    def create(store_type: str, config: Dict[str, Any]) -> VectorStore:
        """Create a vector store instance"""
        if store_type == "chromadb":
            return ChromaVectorStore(config)
        elif store_type == "pinecone":
            return PineconeVectorStore(config)
        elif store_type == "qdrant":
            # Qdrant implementation would go here
            raise NotImplementedError("Qdrant support coming soon")
        else:
            raise ValueError(f"Unknown vector store type: {store_type}")


class HybridSearch:
    """
    Combines vector search with traditional filtering for better results
    """

    def __init__(self, vector_store: VectorStore, db_repository):
        self.vector_store = vector_store
        self.db_repo = db_repository

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        limit: int = 10,
        rerank: bool = True
    ) -> List[QueryResult]:
        """
        Perform hybrid search combining vector similarity and metadata filtering

        Args:
            query: Search query
            filters: Metadata filters
            limit: Number of results
            rerank: Whether to rerank results

        Returns:
            List of search results
        """
        # Get vector search results
        vector_results = await self.vector_store.search(query, filters, limit * 2)

        # Get keyword search results from database
        db_results = await self.db_repo.search_memories(
            filters.get("client_id"),
            query,
            filters.get("role_id"),
            limit
        )

        # Combine and deduplicate results
        combined_results = self._combine_results(vector_results, db_results)

        # Rerank if requested
        if rerank:
            combined_results = await self._rerank_results(combined_results, query)

        return combined_results[:limit]

    def _combine_results(
        self,
        vector_results: List[QueryResult],
        db_results: List[Dict[str, Any]]
    ) -> List[QueryResult]:
        """Combine and deduplicate results from different sources"""
        seen_ids = set()
        combined = []

        # Add vector results first (usually more relevant)
        for result in vector_results:
            if result.memory_id not in seen_ids:
                seen_ids.add(result.memory_id)
                combined.append(result)

        # Add database results
        for db_result in db_results:
            memory_id = db_result.get("memory_id")
            if memory_id and memory_id not in seen_ids:
                seen_ids.add(memory_id)
                combined.append(
                    QueryResult(
                        memory_id=memory_id,
                        text=db_result.get("text", ""),
                        score=0.5,  # Lower score for keyword matches
                        metadata=db_result.get("metadata")
                    )
                )

        return combined

    async def _rerank_results(
        self,
        results: List[QueryResult],
        query: str
    ) -> List[QueryResult]:
        """Rerank results using additional signals"""
        # Simple reranking based on metadata priority
        for result in results:
            if result.metadata:
                # Boost high priority items
                if result.metadata.get("priority") == "high":
                    result.score *= 1.2
                elif result.metadata.get("priority") == "low":
                    result.score *= 0.8

        # Sort by adjusted score
        return sorted(results, key=lambda x: x.score, reverse=True)