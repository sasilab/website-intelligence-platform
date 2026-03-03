"""
Pytest configuration and fixtures
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.database import DatabaseManager
from src.memory.vector_store import VectorStoreFactory
from src.models.schemas import ClientProfile, MemoryEntry


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_manager():
    """Provide a test database manager."""
    manager = DatabaseManager()
    # Use test database
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test_wip"
    await manager.connect()
    yield manager
    # Cleanup
    await manager.db.drop_database("test_wip")
    await manager.disconnect()


@pytest.fixture
async def vector_store():
    """Provide a test vector store."""
    config = {
        "collection_name": "test_memory",
        "persist_directory": "./test_chromadb",
        "embedding_model_type": "sentence-transformers"
    }
    store = VectorStoreFactory.create("chromadb", config)
    await store.initialize()
    yield store
    # Cleanup
    await store.clear_client_memories("test_client")


@pytest.fixture
def sample_client_profile():
    """Provide a sample client profile."""
    return ClientProfile(
        client_id="test_client",
        name="Test Client Corp",
        industry_segment="enterprise",
        plan="professional",
        region="US",
        base_url="https://test.example.com",
        auth={
            "method": "session_token",
            "token_ref": "test_token"
        },
        asset_types=["solar_pv"],
        plant_count=5,
        roles=["admin", "operator", "viewer"]
    )


@pytest.fixture
def sample_page_data():
    """Provide sample crawled page data."""
    return {
        "url": "https://test.example.com/dashboard",
        "page_id": "page_dashboard",
        "feature_id": "dashboard",
        "status_code": 200,
        "content_hash": "abc123",
        "metadata": {
            "title": "Dashboard",
            "description": "Main dashboard"
        },
        "navigation": {
            "main_nav": [
                {"label": "Dashboard", "url": "/dashboard"},
                {"label": "Settings", "url": "/settings"}
            ]
        },
        "components": [
            {
                "name": "Stats Widget",
                "component_type": "widget",
                "purpose": "Display statistics"
            }
        ],
        "content": {
            "main_text": "Dashboard content here"
        },
        "headings": [
            {"level": 1, "text": "Dashboard", "id": "dashboard"}
        ],
        "linked_pages": [
            "https://test.example.com/settings",
            "https://test.example.com/profile"
        ]
    }


@pytest.fixture
def sample_memory_entry():
    """Provide a sample memory entry."""
    return MemoryEntry(
        memory_id="mem_test_123",
        text="To access the Dashboard, click 'Dashboard' in the main navigation menu.",
        metadata={
            "client_id": "test_client",
            "role_id": "operator",
            "feature_id": "dashboard",
            "page_id": "page_dashboard",
            "label": "Dashboard",
            "canonical_name": "Dashboard",
            "url": "/dashboard",
            "nav_path": "Main menu → Dashboard",
            "tags": ["dashboard", "navigation", "main"],
            "priority": "high",
            "version": 1
        },
        confidence_score=0.95
    )


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    mock = MagicMock()
    mock.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"purpose": "Test page", "key_actions": ["Test action"]}'
                    )
                )
            ]
        )
    )
    return mock


@pytest.fixture
def mock_crawler():
    """Mock crawler for testing."""
    mock = AsyncMock()
    mock.crawl = AsyncMock(return_value={
        "url": "https://test.example.com",
        "content": "Test content",
        "status_code": 200
    })
    mock.get_sitemap = AsyncMock(return_value=[
        "https://test.example.com/page1",
        "https://test.example.com/page2"
    ])
    return mock


@pytest.fixture
async def api_client():
    """Provide a test API client."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    client = TestClient(app)
    yield client