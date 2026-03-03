"""
FastAPI application for Website Intelligence Platform
Provides REST API endpoints for agents to query website memory
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..models.schemas import (
    QueryRequest, QueryResponse, QueryResult,
    WebhookPayload, WebhookResponse,
    CrawlLog, ClientProfile, MemoryEntry
)
from ..models.database import db_manager, MemoryRepository, ClientRepository
from ..memory.vector_store import VectorStoreFactory, HybridSearch
from ..services.orchestrator import CrawlOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Website Intelligence Platform API",
    description="AI-powered website navigation intelligence extraction and memory management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Global instances (initialized on startup)
vector_store = None
hybrid_search = None
crawl_orchestrator = None


# ============= Dependency Functions =============

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Verify API key"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # In production, validate against database
    # For now, check against environment variable
    valid_keys = os.getenv("API_KEYS", "").split(",")
    if api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


async def get_client_context(
    client_id: str,
    role_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get client context for filtering"""
    client_repo = ClientRepository(db_manager.db)
    client = await client_repo.get_by_client_id(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    context = {
        "client_id": client_id,
        "role_id": role_id,
        "client_profile": client
    }

    return context


# ============= Startup/Shutdown Events =============

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global vector_store, hybrid_search, crawl_orchestrator

    try:
        # Connect to database
        await db_manager.connect()

        # Initialize vector store
        store_type = os.getenv("VECTOR_STORE_TYPE", "chromadb")
        vector_config = {
            "collection_name": "website_memory",
            "host": os.getenv("CHROMADB_HOST", "localhost"),
            "port": int(os.getenv("CHROMADB_PORT", "8000")),
            "embedding_model_type": "sentence-transformers"
        }

        vector_store = VectorStoreFactory.create(store_type, vector_config)
        await vector_store.initialize()

        # Initialize hybrid search
        memory_repo = MemoryRepository(db_manager.db)
        hybrid_search = HybridSearch(vector_store, memory_repo)

        # Initialize crawl orchestrator
        from ..services.orchestrator import CrawlOrchestrator
        crawl_orchestrator = CrawlOrchestrator(db_manager, vector_store)

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await db_manager.disconnect()


# ============= Health Check =============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "services": {
            "database": db_manager.initialized,
            "vector_store": vector_store is not None,
            "crawler": crawl_orchestrator is not None
        }
    }


# ============= Query Endpoints =============

@app.post("/api/query", response_model=QueryResponse)
async def query_memory(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Query the website memory for navigation information

    This endpoint is the primary interface for AI agents to retrieve
    information about website navigation and functionality.
    """
    try:
        # Get client context
        context = await get_client_context(request.client_id, request.role_id)

        # Build filters
        filters = {
            "client_id": request.client_id,
            "role_id": request.role_id,
            **request.filters
        }

        # Perform search
        import time
        start_time = time.time()

        results = await hybrid_search.search(
            query=request.query,
            filters=filters,
            limit=request.limit,
            rerank=True
        )

        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        # Build response
        response = QueryResponse(
            query=request.query,
            results=results,
            total_results=len(results),
            execution_time_ms=execution_time,
            filters_applied=filters
        )

        return response

    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/{memory_id}")
async def get_memory(
    memory_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get a specific memory entry by ID"""
    memory_repo = MemoryRepository(db_manager.db)
    memory = await memory_repo.get_by_memory_id(memory_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return memory


# ============= Client Management Endpoints =============

@app.get("/api/clients", response_model=List[ClientProfile])
async def list_clients(
    api_key: str = Depends(verify_api_key)
):
    """List all registered clients"""
    client_repo = ClientRepository(db_manager.db)
    clients = await client_repo.find_many({})
    return clients


@app.get("/api/clients/{client_id}")
async def get_client(
    client_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get client profile and configuration"""
    context = await get_client_context(client_id)
    return context["client_profile"]


@app.post("/api/clients")
async def create_client(
    client: ClientProfile,
    api_key: str = Depends(verify_api_key)
):
    """Register a new client"""
    client_repo = ClientRepository(db_manager.db)

    # Check if client already exists
    existing = await client_repo.get_by_client_id(client.client_id)
    if existing:
        raise HTTPException(status_code=400, detail="Client already exists")

    # Create client
    await client_repo.create(client.dict())

    return {"message": "Client created successfully", "client_id": client.client_id}


@app.put("/api/clients/{client_id}/config")
async def update_client_config(
    client_id: str,
    config: Dict[str, Any],
    api_key: str = Depends(verify_api_key)
):
    """Update client configuration"""
    client_repo = ClientRepository(db_manager.db)

    # Update config
    success = await client_repo.update_one(
        {"client_id": client_id},
        {"last_config_change": datetime.utcnow(), **config}
    )

    if not success:
        raise HTTPException(status_code=404, detail="Client not found")

    # Trigger re-crawl for this client
    await crawl_orchestrator.trigger_client_crawl(client_id, "config_change")

    return {"message": "Configuration updated", "client_id": client_id}


# ============= Crawl Management Endpoints =============

@app.post("/api/crawl/trigger")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    crawl_type: str = "incremental",
    client_id: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    """Manually trigger a crawl operation"""
    try:
        # Add crawl to background tasks
        background_tasks.add_task(
            crawl_orchestrator.execute_crawl,
            crawl_type=crawl_type,
            client_id=client_id,
            trigger="manual"
        )

        return {
            "message": "Crawl triggered",
            "crawl_type": crawl_type,
            "client_id": client_id
        }

    except Exception as e:
        logger.error(f"Failed to trigger crawl: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/crawl/status")
async def get_crawl_status(
    client_id: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    """Get current crawl status"""
    from ..models.database import CrawlLogRepository
    crawl_repo = CrawlLogRepository(db_manager.db)

    # Get running crawls
    running = await crawl_repo.get_running_crawls()

    # Get last completed crawl
    last_crawl = await crawl_repo.get_latest_crawl(client_id=client_id)

    return {
        "running_crawls": running,
        "last_completed": last_crawl,
        "timestamp": datetime.utcnow()
    }


@app.get("/api/crawl/history")
async def get_crawl_history(
    client_id: Optional[str] = None,
    limit: int = 10,
    api_key: str = Depends(verify_api_key)
):
    """Get crawl history"""
    from ..models.database import CrawlLogRepository
    crawl_repo = CrawlLogRepository(db_manager.db)

    filters = {}
    if client_id:
        filters["client_id"] = client_id

    crawls = await crawl_repo.find_many(
        filters,
        limit=limit,
        sort=[("started_at", -1)]
    )

    return crawls


# ============= Memory Management Endpoints =============

@app.post("/api/memory/refresh/{client_id}")
async def refresh_client_memory(
    client_id: str,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Refresh all memory entries for a client"""
    try:
        # Clear existing memories
        await vector_store.clear_client_memories(client_id)

        # Trigger full crawl
        background_tasks.add_task(
            crawl_orchestrator.execute_crawl,
            crawl_type="full",
            client_id=client_id,
            trigger="manual"
        )

        return {
            "message": "Memory refresh initiated",
            "client_id": client_id
        }

    except Exception as e:
        logger.error(f"Failed to refresh memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Delete a specific memory entry"""
    try:
        await vector_store.delete_memory(memory_id)
        return {"message": "Memory deleted", "memory_id": memory_id}
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Webhook Endpoints =============

@app.post("/api/webhooks/deployment", response_model=WebhookResponse)
async def handle_deployment_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Handle deployment webhooks from CI/CD pipeline

    This endpoint is called when new code is deployed to trigger
    automatic re-crawling of changed pages.
    """
    try:
        logger.info(f"Received deployment webhook: {payload.event}")

        # Determine crawl type based on changes
        crawl_type = "incremental"
        if payload.event == "major_release":
            crawl_type = "full"

        # Queue crawl tasks
        tasks = []

        if payload.environment == "production":
            # Trigger crawl for all clients
            clients = await ClientRepository(db_manager.db).find_many({})
            for client in clients:
                background_tasks.add_task(
                    crawl_orchestrator.execute_crawl,
                    crawl_type=crawl_type,
                    client_id=client["client_id"],
                    trigger="webhook"
                )
                tasks.append(f"crawl_{client['client_id']}")
        else:
            # Development/staging - crawl test client only
            background_tasks.add_task(
                crawl_orchestrator.execute_crawl,
                crawl_type=crawl_type,
                client_id="test_client",
                trigger="webhook"
            )
            tasks.append("crawl_test_client")

        response = WebhookResponse(
            status="accepted",
            message=f"Deployment webhook processed",
            queued_tasks=tasks
        )

        return response

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Analytics Endpoints =============

@app.get("/api/analytics/summary")
async def get_analytics_summary(
    api_key: str = Depends(verify_api_key)
):
    """Get platform analytics summary"""
    memory_repo = MemoryRepository(db_manager.db)
    client_repo = ClientRepository(db_manager.db)

    # Count statistics
    total_memories = await memory_repo.count({})
    total_clients = await client_repo.count({})

    # Get recent activity
    recent_clients = await client_repo.get_recently_updated(limit=5)

    return {
        "total_memories": total_memories,
        "total_clients": total_clients,
        "recent_activity": recent_clients,
        "timestamp": datetime.utcnow()
    }


# ============= Error Handlers =============

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)