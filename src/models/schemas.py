"""
Data schemas for the Website Intelligence Platform
Defines all core entities and their relationships
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, validator


class CrawlTriggerType(str, Enum):
    """Types of triggers that initiate a crawl"""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    CONFIG_CHANGE = "config_change"


class CrawlType(str, Enum):
    """Types of crawl operations"""
    FULL = "full"
    INCREMENTAL = "incremental"
    CONFIG = "config"
    SPOT = "spot"


class AccessLevel(str, Enum):
    """Access levels for pages/features"""
    FULL = "full"
    READ_ONLY = "read_only"
    HIDDEN = "hidden"


class AuthMethod(str, Enum):
    """Authentication methods for client crawling"""
    SESSION_TOKEN = "session_token"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BASIC = "basic"


# ============= Global Registry Schemas =============

class NavigationEntry(BaseModel):
    """Represents a navigation entry point"""
    label: str
    location: str  # e.g., "left_sidebar", "top_nav", "footer"
    icon: Optional[str] = None
    url: Optional[str] = None
    children: Optional[List['NavigationEntry']] = []


class PageComponent(BaseModel):
    """UI component within a page"""
    name: str
    purpose: str
    component_type: str  # e.g., "table", "form", "chart", "filter_panel"
    actions: List[str] = []
    fields: Optional[Dict[str, str]] = {}  # For forms


class LinkedPage(BaseModel):
    """Link to another page"""
    page_id: str
    trigger: str  # e.g., "Click on alarm row", "Submit form"
    label: Optional[str] = None


class Feature(BaseModel):
    """Global feature definition"""
    feature_id: str
    name: str
    description: str
    category: str  # e.g., "operations", "analytics", "admin"
    pages: List[str] = []  # List of page_ids
    entry_points: List[NavigationEntry] = []
    key_actions: List[str] = []
    dependencies: List[str] = []  # Other feature_ids
    requires_roles: List[str] = []
    tags: List[str] = []
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class Page(BaseModel):
    """Global page definition"""
    page_id: str
    feature_id: Optional[str] = None
    url_pattern: str
    title: str
    summary: str
    navigation_path: List[str] = []  # e.g., ["Sidebar", "Alarms"]
    breadcrumb: List[str] = []
    components: List[PageComponent] = []
    linked_pages: List[LinkedPage] = []
    forms: List[Dict[str, Any]] = []
    meta_description: Optional[str] = None
    last_crawled: datetime = Field(default_factory=datetime.utcnow)
    content_hash: str

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============= Client-Specific Schemas =============

class ClientAuth(BaseModel):
    """Authentication configuration for a client"""
    method: AuthMethod
    token_ref: Optional[str] = None  # Vault reference
    credentials: Optional[Dict[str, str]] = {}  # Encrypted


class ClientProfile(BaseModel):
    """Client organization profile"""
    client_id: str
    name: str
    industry_segment: str  # e.g., "large_utility", "commercial", "residential"
    plan: str  # e.g., "enterprise", "professional", "basic"
    region: str
    base_url: HttpUrl
    auth: ClientAuth
    asset_types: List[str] = []  # e.g., ["solar_pv", "battery_storage"]
    plant_count: int = 0
    roles: List[str] = []
    custom_domain: Optional[HttpUrl] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_config_change: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class FeatureConfig(BaseModel):
    """Client-specific feature configuration"""
    feature_id: str
    enabled: bool
    label_override: Optional[str] = None
    nav_position: Optional[int] = None
    priority: str = "medium"  # high, medium, low
    condition: Optional[str] = None  # e.g., "has_asset_type:battery_storage"
    disabled_reason: Optional[str] = None
    custom_settings: Dict[str, Any] = {}


class ClientFeatureConfig(BaseModel):
    """All feature configurations for a client"""
    client_id: str
    feature_configs: List[FeatureConfig] = []
    nav_tree: Dict[str, Any] = {}  # Nested navigation structure
    theme_overrides: Dict[str, str] = {}
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============= Role-Based Access Schemas =============

class PageRestriction(BaseModel):
    """Page-level access restriction"""
    page_id: str
    access: AccessLevel


class RoleConfig(BaseModel):
    """Role configuration within a client"""
    role_id: str
    label: str
    accessible_features: Any  # List[str] or "all_enabled"
    restricted_features: List[str] = []
    page_restrictions: List[PageRestriction] = []
    data_scope: str  # e.g., "all_plants", "assigned_plants_only"
    custom_permissions: Dict[str, bool] = {}


class ClientRoleConfig(BaseModel):
    """All role configurations for a client"""
    client_id: str
    roles: List[RoleConfig] = []
    default_role: str = "viewer"
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============= Memory and Vector Store Schemas =============

class MemoryMetadata(BaseModel):
    """Metadata for memory entries"""
    client_id: str
    role_id: Optional[str] = None
    feature_id: Optional[str] = None
    page_id: Optional[str] = None
    label: str
    canonical_name: str
    url: str
    nav_path: str
    tags: List[str] = []
    priority: str = "medium"
    version: int = 1
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MemoryEntry(BaseModel):
    """Entry in the vector store"""
    memory_id: str
    text: str  # The actual text that gets embedded
    metadata: MemoryMetadata
    embedding: Optional[List[float]] = None  # Vector embedding
    confidence_score: float = 1.0
    review_required: bool = False

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============= Crawl Management Schemas =============

class CrawlDiff(BaseModel):
    """Change detected during crawl"""
    page_id: str
    change_type: str  # "content_updated", "new_page", "removed", "nav_changed"
    fields_changed: List[str] = []
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None


class CrawlLog(BaseModel):
    """Audit log for a crawl operation"""
    crawl_id: str
    client_id: Optional[str] = None  # None for global crawls
    trigger: CrawlTriggerType
    crawl_type: CrawlType
    status: str  # "pending", "running", "completed", "failed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    pages_crawled: int = 0
    pages_changed: int = 0
    pages_added: int = 0
    pages_removed: int = 0
    memory_entries_updated: int = 0
    errors: List[Dict[str, str]] = []
    diff_summary: List[CrawlDiff] = []
    duration_seconds: Optional[float] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============= Query and Response Schemas =============

class QueryRequest(BaseModel):
    """Request for querying the memory"""
    query: str
    client_id: str
    role_id: Optional[str] = None
    limit: int = 5
    filters: Dict[str, Any] = {}
    include_metadata: bool = True


class QueryResult(BaseModel):
    """Result from a memory query"""
    memory_id: str
    text: str
    score: float  # Similarity score
    metadata: Optional[MemoryMetadata] = None
    source_page: Optional[str] = None


class QueryResponse(BaseModel):
    """Response containing query results"""
    query: str
    results: List[QueryResult]
    total_results: int
    execution_time_ms: float
    filters_applied: Dict[str, Any] = {}


# ============= Webhook Schemas =============

class WebhookPayload(BaseModel):
    """Payload from CI/CD webhook"""
    event: str  # "deployment", "config_change", "feature_release"
    timestamp: datetime
    changes: List[str] = []  # Files/features changed
    environment: str  # "production", "staging", "development"
    triggered_by: str  # User or system that triggered it
    metadata: Dict[str, Any] = {}


class WebhookResponse(BaseModel):
    """Response to webhook trigger"""
    status: str
    crawl_id: Optional[str] = None
    message: str
    queued_tasks: List[str] = []


# Fix for forward references
NavigationEntry.model_rebuild()