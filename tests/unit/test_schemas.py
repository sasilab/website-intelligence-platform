"""
Unit tests for data schemas
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models.schemas import (
    ClientProfile,
    Feature,
    Page,
    MemoryEntry,
    QueryRequest,
    CrawlLog,
    FeatureConfig,
    CrawlType,
    CrawlTriggerType
)


class TestClientProfile:
    """Test ClientProfile schema."""

    def test_valid_client_profile(self):
        """Test creating a valid client profile."""
        profile = ClientProfile(
            client_id="test_123",
            name="Test Company",
            industry_segment="enterprise",
            plan="professional",
            region="US",
            base_url="https://test.com",
            auth={"method": "session_token", "token_ref": "token_123"},
            asset_types=["solar_pv"],
            plant_count=10,
            roles=["admin", "operator"]
        )

        assert profile.client_id == "test_123"
        assert profile.name == "Test Company"
        assert profile.plan == "professional"
        assert len(profile.asset_types) == 1
        assert profile.plant_count == 10

    def test_invalid_url(self):
        """Test that invalid URL raises validation error."""
        with pytest.raises(ValidationError):
            ClientProfile(
                client_id="test_123",
                name="Test Company",
                industry_segment="enterprise",
                plan="professional",
                region="US",
                base_url="not-a-url",  # Invalid URL
                auth={"method": "session_token"},
                asset_types=[],
                plant_count=0,
                roles=[]
            )

    def test_default_values(self):
        """Test default values are set correctly."""
        profile = ClientProfile(
            client_id="test_123",
            name="Test Company",
            industry_segment="enterprise",
            plan="basic",
            region="US",
            base_url="https://test.com",
            auth={"method": "api_key"}
        )

        assert profile.asset_types == []
        assert profile.plant_count == 0
        assert profile.roles == []
        assert isinstance(profile.created_at, datetime)


class TestFeature:
    """Test Feature schema."""

    def test_valid_feature(self):
        """Test creating a valid feature."""
        feature = Feature(
            feature_id="dashboard",
            name="Dashboard",
            description="Main dashboard view",
            category="operations",
            pages=["page_dashboard", "page_overview"],
            key_actions=["View metrics", "Export data"],
            tags=["dashboard", "main"]
        )

        assert feature.feature_id == "dashboard"
        assert feature.category == "operations"
        assert len(feature.pages) == 2
        assert len(feature.key_actions) == 2

    def test_feature_with_dependencies(self):
        """Test feature with dependencies."""
        feature = Feature(
            feature_id="advanced_analytics",
            name="Advanced Analytics",
            description="Advanced analytics features",
            category="analytics",
            dependencies=["basic_analytics", "data_export"],
            requires_roles=["admin", "analyst"]
        )

        assert len(feature.dependencies) == 2
        assert "basic_analytics" in feature.dependencies
        assert len(feature.requires_roles) == 2


class TestMemoryEntry:
    """Test MemoryEntry schema."""

    def test_valid_memory_entry(self):
        """Test creating a valid memory entry."""
        entry = MemoryEntry(
            memory_id="mem_123",
            text="Navigation instructions here",
            metadata={
                "client_id": "client_123",
                "role_id": "admin",
                "feature_id": "dashboard",
                "page_id": "page_dashboard",
                "label": "Dashboard",
                "canonical_name": "Dashboard",
                "url": "/dashboard",
                "nav_path": "Main → Dashboard",
                "tags": ["dashboard"],
                "priority": "high",
                "version": 1
            }
        )

        assert entry.memory_id == "mem_123"
        assert entry.confidence_score == 1.0  # Default value
        assert entry.review_required == False  # Default value
        assert entry.metadata["priority"] == "high"

    def test_memory_with_embedding(self):
        """Test memory entry with embedding."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        entry = MemoryEntry(
            memory_id="mem_123",
            text="Test text",
            metadata={
                "client_id": "test",
                "label": "Test",
                "canonical_name": "Test",
                "url": "/test",
                "nav_path": "Test",
                "version": 1
            },
            embedding=embedding,
            confidence_score=0.85
        )

        assert entry.embedding == embedding
        assert entry.confidence_score == 0.85


class TestQueryRequest:
    """Test QueryRequest schema."""

    def test_valid_query_request(self):
        """Test creating a valid query request."""
        request = QueryRequest(
            query="How to navigate to settings?",
            client_id="client_123",
            role_id="operator",
            limit=5
        )

        assert request.query == "How to navigate to settings?"
        assert request.client_id == "client_123"
        assert request.limit == 5
        assert request.include_metadata == True  # Default

    def test_query_with_filters(self):
        """Test query request with filters."""
        request = QueryRequest(
            query="Dashboard navigation",
            client_id="client_123",
            filters={"feature_id": "dashboard", "priority": "high"}
        )

        assert request.filters["feature_id"] == "dashboard"
        assert request.filters["priority"] == "high"


class TestCrawlLog:
    """Test CrawlLog schema."""

    def test_valid_crawl_log(self):
        """Test creating a valid crawl log."""
        log = CrawlLog(
            crawl_id="crawl_123",
            client_id="client_123",
            trigger=CrawlTriggerType.MANUAL,
            crawl_type=CrawlType.FULL,
            status="running",
            started_at=datetime.utcnow()
        )

        assert log.crawl_id == "crawl_123"
        assert log.trigger == CrawlTriggerType.MANUAL
        assert log.crawl_type == CrawlType.FULL
        assert log.status == "running"
        assert log.pages_crawled == 0  # Default

    def test_completed_crawl_log(self):
        """Test crawl log with completion data."""
        started = datetime.utcnow()
        completed = datetime.utcnow()

        log = CrawlLog(
            crawl_id="crawl_123",
            trigger=CrawlTriggerType.WEBHOOK,
            crawl_type=CrawlType.INCREMENTAL,
            status="completed",
            started_at=started,
            completed_at=completed,
            pages_crawled=50,
            pages_changed=10,
            pages_added=2,
            memory_entries_updated=12
        )

        assert log.status == "completed"
        assert log.pages_crawled == 50
        assert log.pages_changed == 10
        assert log.memory_entries_updated == 12


class TestFeatureConfig:
    """Test FeatureConfig schema."""

    def test_valid_feature_config(self):
        """Test creating a valid feature configuration."""
        config = FeatureConfig(
            feature_id="dashboard",
            enabled=True,
            label_override="Control Panel",
            nav_position=1,
            priority="high"
        )

        assert config.feature_id == "dashboard"
        assert config.enabled == True
        assert config.label_override == "Control Panel"
        assert config.nav_position == 1

    def test_disabled_feature(self):
        """Test disabled feature configuration."""
        config = FeatureConfig(
            feature_id="advanced_feature",
            enabled=False,
            disabled_reason="not_in_plan"
        )

        assert config.enabled == False
        assert config.disabled_reason == "not_in_plan"
        assert config.priority == "medium"  # Default