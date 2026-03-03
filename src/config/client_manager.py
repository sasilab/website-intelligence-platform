"""
Client Configuration Management System
Handles multi-tenant configurations, feature flags, and role-based access
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from ..models.schemas import (
    ClientProfile, ClientFeatureConfig, ClientRoleConfig,
    FeatureConfig, RoleConfig, Feature
)
from ..models.database import (
    DatabaseManager, ClientRepository, FeatureRepository,
    BaseRepository
)

logger = logging.getLogger(__name__)


class ClientConfigurationManager:
    """
    Manages client-specific configurations and customizations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager.db
        self.client_repo = ClientRepository(self.db)
        self.feature_repo = FeatureRepository(self.db)
        self.config_repo = BaseRepository(self.db, "client_configs")
        self.role_repo = BaseRepository(self.db, "client_roles")

    async def register_client(self, client_profile: ClientProfile) -> str:
        """
        Register a new client in the system

        Args:
            client_profile: Client profile information

        Returns:
            Client ID
        """
        # Check if client already exists
        existing = await self.client_repo.get_by_client_id(client_profile.client_id)
        if existing:
            raise ValueError(f"Client {client_profile.client_id} already exists")

        # Create client profile
        await self.client_repo.create(client_profile.dict())

        # Initialize default feature configuration
        await self._initialize_default_features(client_profile)

        # Initialize default roles
        await self._initialize_default_roles(client_profile)

        logger.info(f"Registered new client: {client_profile.client_id}")
        return client_profile.client_id

    async def _initialize_default_features(self, client: ClientProfile):
        """Initialize default feature configuration based on client plan"""

        # Get all available features
        all_features = await self.feature_repo.find_many({})

        # Determine which features to enable based on plan
        plan_features = self._get_features_for_plan(client.plan)

        # Create feature configurations
        feature_configs = []

        for feature in all_features:
            feature_id = feature["feature_id"]
            enabled = feature_id in plan_features

            # Check if feature is applicable based on asset types
            if enabled and feature.get("dependencies"):
                # Check if client has required asset types
                required_assets = feature.get("required_assets", [])
                if required_assets:
                    has_assets = any(
                        asset in client.asset_types
                        for asset in required_assets
                    )
                    if not has_assets:
                        enabled = False

            feature_config = FeatureConfig(
                feature_id=feature_id,
                enabled=enabled,
                label_override=None,
                nav_position=feature.get("default_position"),
                priority="medium"
            )

            feature_configs.append(feature_config)

        # Create client feature configuration
        client_config = ClientFeatureConfig(
            client_id=client.client_id,
            feature_configs=feature_configs,
            nav_tree=self._build_default_nav_tree(feature_configs, all_features)
        )

        # Save to database
        await self.config_repo.create(client_config.dict())

    async def _initialize_default_roles(self, client: ClientProfile):
        """Initialize default roles for the client"""

        # Default roles based on industry segment
        default_roles = self._get_default_roles(client.industry_segment)

        role_configs = []
        for role_def in default_roles:
            role_config = RoleConfig(
                role_id=role_def["id"],
                label=role_def["label"],
                accessible_features=role_def["accessible_features"],
                restricted_features=role_def.get("restricted_features", []),
                page_restrictions=[],
                data_scope=role_def["data_scope"]
            )
            role_configs.append(role_config)

        # Create client role configuration
        client_roles = ClientRoleConfig(
            client_id=client.client_id,
            roles=role_configs
        )

        # Save to database
        await self.role_repo.create(client_roles.dict())

    def _get_features_for_plan(self, plan: str) -> List[str]:
        """Get feature IDs available for a plan"""

        plan_features = {
            "basic": [
                "dashboard",
                "plant_monitoring",
                "alarm_management",
                "basic_reporting"
            ],
            "professional": [
                "dashboard",
                "plant_monitoring",
                "alarm_management",
                "reporting",
                "analytics",
                "yield_forecasting",
                "maintenance_planning",
                "user_management"
            ],
            "enterprise": [
                "dashboard",
                "portfolio_overview",
                "plant_monitoring",
                "alarm_management",
                "reporting",
                "analytics",
                "yield_forecasting",
                "maintenance_planning",
                "user_management",
                "api_access",
                "custom_dashboards",
                "scada_integration",
                "battery_management",
                "financial_analytics"
            ]
        }

        return plan_features.get(plan, plan_features["basic"])

    def _get_default_roles(self, industry_segment: str) -> List[Dict[str, Any]]:
        """Get default roles based on industry segment"""

        base_roles = [
            {
                "id": "admin",
                "label": "Administrator",
                "accessible_features": "all_enabled",
                "data_scope": "all_plants"
            },
            {
                "id": "operator",
                "label": "Plant Operator",
                "accessible_features": [
                    "dashboard",
                    "plant_monitoring",
                    "alarm_management",
                    "maintenance_planning"
                ],
                "restricted_features": ["user_management", "api_access"],
                "data_scope": "assigned_plants_only"
            },
            {
                "id": "viewer",
                "label": "Viewer",
                "accessible_features": [
                    "dashboard",
                    "plant_monitoring",
                    "reporting"
                ],
                "restricted_features": ["*_management", "api_access"],
                "data_scope": "all_plants"
            }
        ]

        # Add segment-specific roles
        if industry_segment == "large_utility":
            base_roles.append({
                "id": "finance",
                "label": "Financial Analyst",
                "accessible_features": [
                    "dashboard",
                    "financial_analytics",
                    "reporting"
                ],
                "data_scope": "all_plants"
            })

        return base_roles

    def _build_default_nav_tree(
        self,
        feature_configs: List[FeatureConfig],
        all_features: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build default navigation tree based on enabled features"""

        nav_tree = {}

        # Group features by category
        categories = {}
        for config in feature_configs:
            if not config.enabled:
                continue

            # Find feature details
            feature = next(
                (f for f in all_features if f["feature_id"] == config.feature_id),
                None
            )

            if feature:
                category = feature.get("category", "Other")
                if category not in categories:
                    categories[category] = []

                categories[category].append({
                    "label": config.label_override or feature["name"],
                    "path": feature.get("default_path", f"/{config.feature_id}")
                })

        # Build tree structure
        category_order = ["operations", "analytics", "admin", "other"]

        for category in category_order:
            if category in categories:
                if len(categories[category]) == 1:
                    # Single item - add directly
                    item = categories[category][0]
                    nav_tree[item["label"]] = item["path"]
                else:
                    # Multiple items - create submenu
                    submenu = {}
                    for item in categories[category]:
                        submenu[item["label"]] = item["path"]
                    nav_tree[category.title()] = submenu

        return nav_tree

    async def update_feature_config(
        self,
        client_id: str,
        feature_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update configuration for a specific feature

        Args:
            client_id: Client ID
            feature_id: Feature ID
            updates: Configuration updates

        Returns:
            Success status
        """
        # Get current configuration
        config = await self.config_repo.find_one({"client_id": client_id})

        if not config:
            raise ValueError(f"Configuration not found for client {client_id}")

        # Find and update the specific feature config
        updated = False
        for feature_config in config["feature_configs"]:
            if feature_config["feature_id"] == feature_id:
                feature_config.update(updates)
                updated = True
                break

        if not updated:
            raise ValueError(f"Feature {feature_id} not found for client {client_id}")

        # Update last modified timestamp
        config["last_updated"] = datetime.utcnow()

        # Save updated configuration
        success = await self.config_repo.update_one(
            {"client_id": client_id},
            config
        )

        if success:
            logger.info(f"Updated feature {feature_id} config for client {client_id}")

        return success

    async def toggle_feature(
        self,
        client_id: str,
        feature_id: str,
        enabled: bool
    ) -> bool:
        """Enable or disable a feature for a client"""
        return await self.update_feature_config(
            client_id,
            feature_id,
            {"enabled": enabled}
        )

    async def set_label_override(
        self,
        client_id: str,
        feature_id: str,
        label: str
    ) -> bool:
        """Set custom label for a feature"""
        return await self.update_feature_config(
            client_id,
            feature_id,
            {"label_override": label}
        )

    async def get_client_features(
        self,
        client_id: str,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all features for a client

        Args:
            client_id: Client ID
            enabled_only: Only return enabled features

        Returns:
            List of feature configurations
        """
        config = await self.config_repo.find_one({"client_id": client_id})

        if not config:
            return []

        features = config.get("feature_configs", [])

        if enabled_only:
            features = [f for f in features if f.get("enabled")]

        # Enhance with feature details
        enhanced = []
        for feature_config in features:
            feature = await self.feature_repo.get_by_feature_id(
                feature_config["feature_id"]
            )

            if feature:
                enhanced_config = {
                    **feature_config,
                    "name": feature["name"],
                    "description": feature["description"],
                    "category": feature["category"]
                }
                enhanced.append(enhanced_config)

        return enhanced

    async def get_role_permissions(
        self,
        client_id: str,
        role_id: str
    ) -> Dict[str, Any]:
        """
        Get permissions for a specific role

        Args:
            client_id: Client ID
            role_id: Role ID

        Returns:
            Role permissions
        """
        roles_config = await self.role_repo.find_one({"client_id": client_id})

        if not roles_config:
            return {}

        for role in roles_config.get("roles", []):
            if role["role_id"] == role_id:
                return role

        return {}

    async def update_role_permissions(
        self,
        client_id: str,
        role_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update permissions for a role"""
        roles_config = await self.role_repo.find_one({"client_id": client_id})

        if not roles_config:
            return False

        updated = False
        for role in roles_config.get("roles", []):
            if role["role_id"] == role_id:
                role.update(updates)
                updated = True
                break

        if updated:
            roles_config["last_updated"] = datetime.utcnow()
            return await self.role_repo.update_one(
                {"client_id": client_id},
                roles_config
            )

        return False

    async def add_custom_role(
        self,
        client_id: str,
        role: RoleConfig
    ) -> bool:
        """Add a custom role for a client"""
        roles_config = await self.role_repo.find_one({"client_id": client_id})

        if not roles_config:
            return False

        # Check if role already exists
        existing = any(
            r["role_id"] == role.role_id
            for r in roles_config.get("roles", [])
        )

        if existing:
            raise ValueError(f"Role {role.role_id} already exists")

        # Add new role
        roles_config["roles"].append(role.dict())
        roles_config["last_updated"] = datetime.utcnow()

        return await self.role_repo.update_one(
            {"client_id": client_id},
            roles_config
        )


class ConfigurationValidator:
    """
    Validates client configurations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager.db
        self.feature_repo = FeatureRepository(self.db)

    async def validate_feature_config(
        self,
        client_config: ClientFeatureConfig
    ) -> Dict[str, Any]:
        """
        Validate feature configuration

        Returns:
            Validation result with any issues found
        """
        issues = []

        # Get all valid features
        all_features = await self.feature_repo.find_many({})
        valid_feature_ids = {f["feature_id"] for f in all_features}

        # Check each feature configuration
        for config in client_config.feature_configs:
            # Check if feature exists
            if config.feature_id not in valid_feature_ids:
                issues.append(f"Unknown feature: {config.feature_id}")

            # Check dependencies
            if config.enabled:
                feature = next(
                    (f for f in all_features if f["feature_id"] == config.feature_id),
                    None
                )

                if feature and feature.get("dependencies"):
                    for dep in feature["dependencies"]:
                        # Check if dependency is enabled
                        dep_config = next(
                            (c for c in client_config.feature_configs
                             if c.feature_id == dep),
                            None
                        )

                        if not dep_config or not dep_config.enabled:
                            issues.append(
                                f"Feature {config.feature_id} requires {dep} to be enabled"
                            )

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }

    async def validate_role_config(
        self,
        role_config: ClientRoleConfig,
        feature_config: ClientFeatureConfig
    ) -> Dict[str, Any]:
        """Validate role configuration against enabled features"""
        issues = []

        enabled_features = {
            fc.feature_id
            for fc in feature_config.feature_configs
            if fc.enabled
        }

        for role in role_config.roles:
            if isinstance(role.accessible_features, list):
                # Check if all accessible features are enabled
                for feature_id in role.accessible_features:
                    if feature_id not in enabled_features:
                        issues.append(
                            f"Role {role.role_id} references disabled feature: {feature_id}"
                        )

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }


class ConfigurationMigrator:
    """
    Handles configuration migrations when platform features change
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager.db

    async def migrate_all_clients(self, migration_spec: Dict[str, Any]):
        """
        Apply a migration to all client configurations

        Args:
            migration_spec: Specification of the migration to apply
        """
        client_repo = ClientRepository(self.db)
        config_repo = BaseRepository(self.db, "client_configs")

        # Get all clients
        clients = await client_repo.find_many({})

        for client in clients:
            client_id = client["client_id"]

            try:
                # Get current configuration
                config = await config_repo.find_one({"client_id": client_id})

                if config:
                    # Apply migration
                    updated_config = await self._apply_migration(
                        config,
                        migration_spec
                    )

                    # Save updated configuration
                    await config_repo.update_one(
                        {"client_id": client_id},
                        updated_config
                    )

                    logger.info(f"Migrated configuration for client {client_id}")

            except Exception as e:
                logger.error(f"Failed to migrate client {client_id}: {e}")

    async def _apply_migration(
        self,
        config: Dict[str, Any],
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply migration specification to a configuration"""

        # Example migrations:
        # - Rename feature
        # - Add new feature
        # - Remove deprecated feature
        # - Update feature dependencies

        if spec.get("type") == "rename_feature":
            old_id = spec["old_id"]
            new_id = spec["new_id"]

            for fc in config.get("feature_configs", []):
                if fc["feature_id"] == old_id:
                    fc["feature_id"] = new_id

        elif spec.get("type") == "add_feature":
            new_feature = FeatureConfig(**spec["feature_config"])
            config["feature_configs"].append(new_feature.dict())

        elif spec.get("type") == "remove_feature":
            feature_id = spec["feature_id"]
            config["feature_configs"] = [
                fc for fc in config.get("feature_configs", [])
                if fc["feature_id"] != feature_id
            ]

        # Update timestamp
        config["last_updated"] = datetime.utcnow()

        return config