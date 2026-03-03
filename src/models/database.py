"""
MongoDB database models and connection management
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MongoDB connection and collections"""

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.initialized = False

    async def connect(self):
        """Establish connection to MongoDB"""
        if self.initialized:
            return

        try:
            mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/website_intelligence")
            self.client = AsyncIOMotorClient(mongo_uri)
            self.db = self.client.get_database()

            # Test connection
            await self.client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")

            # Initialize collections and indexes
            await self._init_collections()
            self.initialized = True

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self.initialized = False
            logger.info("Disconnected from MongoDB")

    async def _init_collections(self):
        """Initialize collections with indexes"""

        # Features collection
        features_indexes = [
            IndexModel([("feature_id", ASCENDING)], unique=True),
            IndexModel([("category", ASCENDING)]),
            IndexModel([("tags", ASCENDING)]),
            IndexModel([("name", TEXT), ("description", TEXT)])
        ]
        await self.db.features.create_indexes(features_indexes)

        # Pages collection
        pages_indexes = [
            IndexModel([("page_id", ASCENDING)], unique=True),
            IndexModel([("feature_id", ASCENDING)]),
            IndexModel([("url_pattern", ASCENDING)]),
            IndexModel([("content_hash", ASCENDING)]),
            IndexModel([("last_crawled", DESCENDING)])
        ]
        await self.db.pages.create_indexes(pages_indexes)

        # Clients collection
        clients_indexes = [
            IndexModel([("client_id", ASCENDING)], unique=True),
            IndexModel([("name", ASCENDING)]),
            IndexModel([("plan", ASCENDING)]),
            IndexModel([("last_config_change", DESCENDING)])
        ]
        await self.db.clients.create_indexes(clients_indexes)

        # Client configs collection
        client_configs_indexes = [
            IndexModel([("client_id", ASCENDING)], unique=True),
            IndexModel([("client_id", ASCENDING), ("feature_configs.feature_id", ASCENDING)])
        ]
        await self.db.client_configs.create_indexes(client_configs_indexes)

        # Client roles collection
        client_roles_indexes = [
            IndexModel([("client_id", ASCENDING)]),
            IndexModel([("client_id", ASCENDING), ("roles.role_id", ASCENDING)])
        ]
        await self.db.client_roles.create_indexes(client_roles_indexes)

        # Memory entries collection
        memory_indexes = [
            IndexModel([("memory_id", ASCENDING)], unique=True),
            IndexModel([("metadata.client_id", ASCENDING)]),
            IndexModel([("metadata.role_id", ASCENDING)]),
            IndexModel([("metadata.feature_id", ASCENDING)]),
            IndexModel([("metadata.client_id", ASCENDING), ("metadata.role_id", ASCENDING)]),
            IndexModel([("metadata.tags", ASCENDING)]),
            IndexModel([("metadata.priority", ASCENDING)]),
            IndexModel([("text", TEXT)])
        ]
        await self.db.memory_entries.create_indexes(memory_indexes)

        # Crawl logs collection
        crawl_logs_indexes = [
            IndexModel([("crawl_id", ASCENDING)], unique=True),
            IndexModel([("client_id", ASCENDING)]),
            IndexModel([("trigger", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("started_at", DESCENDING)])
        ]
        await self.db.crawl_logs.create_indexes(crawl_logs_indexes)

        logger.info("All collections and indexes initialized")


class BaseRepository:
    """Base repository class for database operations"""

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        self.db = db
        self.collection = db[collection_name]

    async def create(self, document: Dict[str, Any]) -> str:
        """Insert a new document"""
        result = await self.collection.insert_one(document)
        return str(result.inserted_id)

    async def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document"""
        return await self.collection.find_one(filter)

    async def find_many(
        self,
        filter: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple documents"""
        cursor = self.collection.find(filter)

        if sort:
            cursor = cursor.sort(sort)

        cursor = cursor.skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """Update a single document"""
        result = await self.collection.update_one(
            filter,
            {"$set": update},
            upsert=upsert
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def delete_one(self, filter: Dict[str, Any]) -> bool:
        """Delete a single document"""
        result = await self.collection.delete_one(filter)
        return result.deleted_count > 0

    async def count(self, filter: Dict[str, Any]) -> int:
        """Count documents matching filter"""
        return await self.collection.count_documents(filter)


class FeatureRepository(BaseRepository):
    """Repository for Feature documents"""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "features")

    async def get_by_feature_id(self, feature_id: str) -> Optional[Dict[str, Any]]:
        """Get feature by ID"""
        return await self.find_one({"feature_id": feature_id})

    async def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all features in a category"""
        return await self.find_many({"category": category})

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """Search features by text"""
        return await self.find_many(
            {"$text": {"$search": query}},
            limit=20
        )


class PageRepository(BaseRepository):
    """Repository for Page documents"""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "pages")

    async def get_by_page_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Get page by ID"""
        return await self.find_one({"page_id": page_id})

    async def get_by_feature(self, feature_id: str) -> List[Dict[str, Any]]:
        """Get all pages for a feature"""
        return await self.find_many({"feature_id": feature_id})

    async def get_changed_pages(self, since: datetime) -> List[Dict[str, Any]]:
        """Get pages changed since a timestamp"""
        return await self.find_many(
            {"last_crawled": {"$gte": since}},
            sort=[("last_crawled", DESCENDING)]
        )


class ClientRepository(BaseRepository):
    """Repository for Client documents"""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "clients")

    async def get_by_client_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get client by ID"""
        return await self.find_one({"client_id": client_id})

    async def get_by_plan(self, plan: str) -> List[Dict[str, Any]]:
        """Get all clients on a specific plan"""
        return await self.find_many({"plan": plan})

    async def get_recently_updated(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently updated clients"""
        return await self.find_many(
            {},
            limit=limit,
            sort=[("last_config_change", DESCENDING)]
        )


class MemoryRepository(BaseRepository):
    """Repository for Memory entries"""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "memory_entries")

    async def get_by_memory_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get memory entry by ID"""
        return await self.find_one({"memory_id": memory_id})

    async def get_client_memories(
        self,
        client_id: str,
        role_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all memory entries for a client and role"""
        filter = {"metadata.client_id": client_id}
        if role_id:
            filter["metadata.role_id"] = role_id

        return await self.find_many(filter, limit=1000)

    async def search_memories(
        self,
        client_id: str,
        query: str,
        role_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search memory entries"""
        filter = {
            "metadata.client_id": client_id,
            "$text": {"$search": query}
        }

        if role_id:
            filter["metadata.role_id"] = role_id

        return await self.find_many(filter, limit=limit)

    async def bulk_upsert(self, memories: List[Dict[str, Any]]):
        """Bulk upsert memory entries"""
        operations = []
        for memory in memories:
            operations.append(
                {
                    "updateOne": {
                        "filter": {"memory_id": memory["memory_id"]},
                        "update": {"$set": memory},
                        "upsert": True
                    }
                }
            )

        if operations:
            await self.collection.bulk_write(operations)


class CrawlLogRepository(BaseRepository):
    """Repository for Crawl logs"""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "crawl_logs")

    async def get_latest_crawl(
        self,
        client_id: Optional[str] = None,
        crawl_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent crawl log"""
        filter = {}
        if client_id:
            filter["client_id"] = client_id
        if crawl_type:
            filter["crawl_type"] = crawl_type

        results = await self.find_many(
            filter,
            limit=1,
            sort=[("started_at", DESCENDING)]
        )

        return results[0] if results else None

    async def get_running_crawls(self) -> List[Dict[str, Any]]:
        """Get all currently running crawls"""
        return await self.find_many({"status": "running"})


# Singleton instance
db_manager = DatabaseManager()