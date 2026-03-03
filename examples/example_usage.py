"""
Example usage of the Website Intelligence Platform
Demonstrates common use cases and integration patterns
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.schemas import ClientProfile, QueryRequest
from src.models.database import db_manager
from src.config.client_manager import ClientConfigurationManager
from src.services.orchestrator import CrawlOrchestrator
from src.memory.vector_store import VectorStoreFactory, HybridSearch
from src.extractors.llm_summarizer import LLMSummarizer, MemoryGenerator


class WebsiteIntelligencePlatformExample:
    """
    Example usage of the Website Intelligence Platform
    """

    def __init__(self):
        self.db_manager = db_manager
        self.config_manager = None
        self.orchestrator = None
        self.vector_store = None

    async def setup(self):
        """Initialize all services"""
        print("Setting up Website Intelligence Platform...")

        # Connect to database
        await self.db_manager.connect()

        # Initialize configuration manager
        self.config_manager = ClientConfigurationManager(self.db_manager)

        # Initialize vector store
        vector_config = {
            "collection_name": "website_memory_example",
            "host": os.getenv("CHROMADB_HOST", "localhost"),
            "port": int(os.getenv("CHROMADB_PORT", "8000")),
            "embedding_model_type": "sentence-transformers"
        }
        self.vector_store = VectorStoreFactory.create("chromadb", vector_config)
        await self.vector_store.initialize()

        # Initialize orchestrator
        self.orchestrator = CrawlOrchestrator(self.db_manager, self.vector_store)

        print("Setup complete!")

    async def example_1_register_client(self):
        """Example 1: Register a new B2B client"""
        print("\n=== Example 1: Registering a New Client ===")

        # Create client profile for a solar energy company
        client_profile = ClientProfile(
            client_id="demo_solar_corp",
            name="Demo Solar Corporation",
            industry_segment="large_utility",
            plan="enterprise",
            region="US",
            base_url="https://demo.solarplatform.com",
            auth={
                "method": "session_token",
                "token_ref": "demo_token_123"
            },
            asset_types=["solar_pv", "battery_storage", "inverter"],
            plant_count=25,
            roles=["admin", "operator", "viewer", "finance"]
        )

        # Register the client
        client_id = await self.config_manager.register_client(client_profile)
        print(f"✓ Registered client: {client_id}")

        # Get enabled features for the client
        features = await self.config_manager.get_client_features(
            client_id,
            enabled_only=True
        )
        print(f"✓ Enabled features: {[f['name'] for f in features[:5]]}...")

        return client_id

    async def example_2_customize_features(self, client_id: str):
        """Example 2: Customize features for a client"""
        print("\n=== Example 2: Customizing Client Features ===")

        # Rename a feature for the client
        await self.config_manager.set_label_override(
            client_id,
            "alarm_management",
            "Fault Tracker"
        )
        print("✓ Renamed 'Alarm Management' to 'Fault Tracker'")

        # Enable additional feature
        await self.config_manager.toggle_feature(
            client_id,
            "yield_forecasting",
            enabled=True
        )
        print("✓ Enabled 'Yield Forecasting' feature")

        # Update feature configuration
        await self.config_manager.update_feature_config(
            client_id,
            "dashboard",
            {
                "priority": "high",
                "nav_position": 1
            }
        )
        print("✓ Set Dashboard as high priority")

    async def example_3_crawl_website(self, client_id: str):
        """Example 3: Crawl website and extract information"""
        print("\n=== Example 3: Crawling Website ===")

        # Trigger a full crawl for the client
        print("Starting full crawl...")
        crawl_id = await self.orchestrator.execute_crawl(
            crawl_type="full",
            client_id=client_id,
            trigger="manual"
        )
        print(f"✓ Crawl completed with ID: {crawl_id}")

        # Get crawl results
        from src.models.database import CrawlLogRepository
        crawl_repo = CrawlLogRepository(self.db_manager.db)
        crawl_log = await crawl_repo.find_one({"crawl_id": crawl_id})

        if crawl_log:
            print(f"  Pages crawled: {crawl_log.get('pages_crawled', 0)}")
            print(f"  Memory entries created: {crawl_log.get('memory_entries_created', 0)}")
            print(f"  Errors: {len(crawl_log.get('errors', []))}")

        return crawl_id

    async def example_4_simulate_page_data(self, client_id: str):
        """Example 4: Simulate page data and create memories"""
        print("\n=== Example 4: Simulating Page Data ===")

        # Simulate crawled page data
        simulated_pages = [
            {
                "url": "https://demo.solarplatform.com/dashboard",
                "page_id": "page_dashboard",
                "feature_id": "dashboard",
                "metadata": {
                    "title": "Solar Fleet Dashboard",
                    "description": "Overview of all solar plants"
                },
                "content": {
                    "main_text": "Dashboard showing real-time performance metrics for all solar plants. View production, efficiency, and alerts."
                },
                "navigation": {
                    "main_nav": [
                        {"label": "Dashboard", "url": "/dashboard"},
                        {"label": "Plants", "url": "/plants"},
                        {"label": "Analytics", "url": "/analytics"}
                    ]
                },
                "components": [
                    {
                        "name": "Production Chart",
                        "component_type": "chart",
                        "purpose": "Shows daily energy production"
                    },
                    {
                        "name": "Alert Table",
                        "component_type": "table",
                        "purpose": "Lists active system alerts"
                    }
                ]
            },
            {
                "url": "https://demo.solarplatform.com/alarms",
                "page_id": "page_alarms",
                "feature_id": "alarm_management",
                "metadata": {
                    "title": "Alarm Management",
                    "description": "Monitor and manage system alarms"
                },
                "content": {
                    "main_text": "Comprehensive alarm management system. View, acknowledge, and resolve alarms across all plants."
                },
                "navigation": {
                    "breadcrumb": ["Home", "Operations", "Alarms"]
                },
                "components": [
                    {
                        "name": "Alarm List",
                        "component_type": "table",
                        "purpose": "Displays all active and historical alarms"
                    }
                ]
            }
        ]

        # Create LLM summarizer and memory generator
        llm_config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo-preview"
        }
        summarizer = LLMSummarizer(llm_config)
        memory_generator = MemoryGenerator(summarizer)

        # Generate memories for simulated pages
        memories_created = 0
        for page in simulated_pages:
            # Simulate summary (in production, this would come from LLM)
            summary = {
                "purpose": f"Page for {page['metadata']['title']}",
                "key_actions": ["View data", "Filter results", "Export"],
                "navigation_path": f"Main menu → {page['metadata']['title']}",
                "user_instructions": f"Navigate to {page['url']} to access this page"
            }

            # Generate memory entry
            context = {
                "client_id": client_id,
                "role_id": "operator"
            }

            memory = await memory_generator.generate_memory_entry(
                summary,
                page,
                context
            )

            # Store in vector database
            await self.vector_store.add_memory(memory)
            memories_created += 1

        print(f"✓ Created {memories_created} memory entries from simulated data")

    async def example_5_query_memory(self, client_id: str):
        """Example 5: Query the memory like an AI agent would"""
        print("\n=== Example 5: Querying Website Memory ===")

        # Initialize hybrid search
        from src.models.database import MemoryRepository
        memory_repo = MemoryRepository(self.db_manager.db)
        hybrid_search = HybridSearch(self.vector_store, memory_repo)

        # Example queries an AI agent might ask
        queries = [
            "How do I navigate to the dashboard?",
            "Where can I see alarms?",
            "How to view plant performance?",
            "What actions can I perform on the alarm page?"
        ]

        for query in queries:
            print(f"\nQuery: '{query}'")

            # Perform search
            results = await hybrid_search.search(
                query=query,
                filters={
                    "client_id": client_id,
                    "role_id": "operator"
                },
                limit=3
            )

            # Display results
            if results:
                best_result = results[0]
                print(f"Answer (Score: {best_result.score:.2f}):")
                print(f"  {best_result.text[:200]}...")
            else:
                print("  No results found")

    async def example_6_incremental_crawl(self, client_id: str):
        """Example 6: Simulate incremental crawl after changes"""
        print("\n=== Example 6: Incremental Crawl After Changes ===")

        # Simulate that some pages have changed
        print("Simulating website changes...")

        # Trigger incremental crawl
        crawl_id = await self.orchestrator.execute_crawl(
            crawl_type="incremental",
            client_id=client_id,
            trigger="webhook"
        )

        print(f"✓ Incremental crawl completed: {crawl_id}")

        # Check what changed
        from src.services.change_detector import SmartChangeDetector
        change_detector = SmartChangeDetector(self.db_manager)

        # Get change summary (simulated)
        print("✓ Changes detected:")
        print("  - 2 pages with content updates")
        print("  - 1 page with navigation changes")
        print("  - Memory entries updated automatically")

    async def example_7_role_based_access(self, client_id: str):
        """Example 7: Demonstrate role-based memory access"""
        print("\n=== Example 7: Role-Based Access Control ===")

        # Get permissions for different roles
        roles = ["admin", "operator", "viewer"]

        for role_id in roles:
            print(f"\nRole: {role_id}")

            # Get role permissions
            permissions = await self.config_manager.get_role_permissions(
                client_id,
                role_id
            )

            if permissions:
                print(f"  Accessible features: {permissions.get('accessible_features', [])[:3]}...")
                print(f"  Data scope: {permissions.get('data_scope', 'unknown')}")

                # Query with role context
                from src.memory.vector_store import HybridSearch
                from src.models.database import MemoryRepository
                memory_repo = MemoryRepository(self.db_manager.db)
                hybrid_search = HybridSearch(self.vector_store, memory_repo)

                results = await hybrid_search.search(
                    query="How to access settings?",
                    filters={
                        "client_id": client_id,
                        "role_id": role_id
                    },
                    limit=1
                )

                if results:
                    print(f"  Can access: Yes")
                else:
                    print(f"  Can access: No (restricted)")

    async def example_8_webhook_simulation(self, client_id: str):
        """Example 8: Simulate CI/CD webhook trigger"""
        print("\n=== Example 8: CI/CD Webhook Integration ===")

        # Simulate webhook payload from deployment
        webhook_payload = {
            "event": "deployment",
            "timestamp": datetime.utcnow().isoformat(),
            "environment": "production",
            "changes": [
                "pages/dashboard.tsx",
                "components/AlarmTable.tsx",
                "navigation/sidebar.tsx"
            ],
            "triggered_by": "github-actions"
        }

        print("Received deployment webhook:")
        print(f"  Environment: {webhook_payload['environment']}")
        print(f"  Changed files: {len(webhook_payload['changes'])}")

        # Process webhook (trigger incremental crawl)
        print("Processing webhook...")
        crawl_id = await self.orchestrator.execute_crawl(
            crawl_type="incremental",
            client_id=client_id,
            trigger="webhook"
        )

        print(f"✓ Webhook processed, triggered crawl: {crawl_id}")
        print("✓ AI agents will now have updated navigation information")

    async def cleanup(self):
        """Cleanup resources"""
        print("\nCleaning up...")

        # Clear test data
        if self.vector_store:
            await self.vector_store.clear_client_memories("demo_solar_corp")

        # Disconnect from database
        await self.db_manager.disconnect()

        print("✓ Cleanup complete")


async def main():
    """Run all examples"""
    example = WebsiteIntelligencePlatformExample()

    try:
        # Setup
        await example.setup()

        # Run examples
        client_id = await example.example_1_register_client()
        await example.example_2_customize_features(client_id)

        # Note: In production, example_3 would actually crawl a real website
        # await example.example_3_crawl_website(client_id)

        # For demo purposes, we'll use simulated data
        await example.example_4_simulate_page_data(client_id)
        await example.example_5_query_memory(client_id)
        await example.example_6_incremental_crawl(client_id)
        await example.example_7_role_based_access(client_id)
        await example.example_8_webhook_simulation(client_id)

        print("\n" + "="*50)
        print("All examples completed successfully!")
        print("="*50)

    except Exception as e:
        print(f"Error running examples: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await example.cleanup()


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())