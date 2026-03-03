"""
Orchestrator service that coordinates crawling, summarization, and memory management
"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from ..crawlers.static_crawler import StaticBatchCrawler
from ..crawlers.dynamic_crawler import DynamicCrawler
from ..extractors.llm_summarizer import BatchSummarizer, LLMSummarizer, MemoryGenerator
from ..services.change_detector import IncrementalCrawlManager, ChangeNotifier, SmartChangeDetector
from ..memory.vector_store import VectorStore
from ..models.schemas import CrawlLog, CrawlType, CrawlTriggerType, MemoryEntry
from ..models.database import (
    DatabaseManager, PageRepository, ClientRepository,
    CrawlLogRepository, MemoryRepository
)

logger = logging.getLogger(__name__)


class CrawlOrchestrator:
    """
    Orchestrates the entire crawl-summarize-store pipeline
    """

    def __init__(self, db_manager: DatabaseManager, vector_store: VectorStore):
        self.db = db_manager.db
        self.vector_store = vector_store

        # Initialize repositories
        self.page_repo = PageRepository(self.db)
        self.client_repo = ClientRepository(self.db)
        self.crawl_log_repo = CrawlLogRepository(self.db)
        self.memory_repo = MemoryRepository(self.db)

        # Initialize services
        self.change_detector = SmartChangeDetector(db_manager)
        self.incremental_manager = IncrementalCrawlManager(db_manager, self.change_detector)
        self.change_notifier = ChangeNotifier()

        # LLM services
        llm_config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo-preview",
            "temperature": 0.3
        }
        self.summarizer = LLMSummarizer(llm_config)
        self.batch_summarizer = BatchSummarizer(self.summarizer)
        self.memory_generator = MemoryGenerator(self.summarizer)

        # Crawl state
        self.active_crawls = {}

    async def execute_crawl(
        self,
        crawl_type: str,
        client_id: Optional[str] = None,
        trigger: str = "manual"
    ) -> str:
        """
        Execute a complete crawl operation

        Args:
            crawl_type: Type of crawl (full, incremental, config)
            client_id: Client to crawl for (None for global)
            trigger: What triggered the crawl

        Returns:
            Crawl ID
        """
        crawl_id = str(uuid.uuid4())

        try:
            # Create crawl log entry
            crawl_log = CrawlLog(
                crawl_id=crawl_id,
                client_id=client_id,
                trigger=CrawlTriggerType(trigger),
                crawl_type=CrawlType(crawl_type),
                status="running",
                started_at=datetime.utcnow()
            )

            await self.crawl_log_repo.create(crawl_log.dict())
            self.active_crawls[crawl_id] = crawl_log

            # Execute based on crawl type
            if crawl_type == "full":
                results = await self._execute_full_crawl(client_id, crawl_id)
            elif crawl_type == "incremental":
                results = await self._execute_incremental_crawl(client_id, crawl_id)
            elif crawl_type == "config":
                results = await self._execute_config_crawl(client_id, crawl_id)
            else:
                raise ValueError(f"Unknown crawl type: {crawl_type}")

            # Update crawl log with results
            await self._complete_crawl(crawl_id, results)

            return crawl_id

        except Exception as e:
            logger.error(f"Crawl {crawl_id} failed: {e}")
            await self._fail_crawl(crawl_id, str(e))
            raise

    async def _execute_full_crawl(
        self,
        client_id: Optional[str],
        crawl_id: str
    ) -> Dict[str, Any]:
        """Execute a full crawl of all pages"""
        logger.info(f"Starting full crawl {crawl_id} for client {client_id or 'global'}")

        results = {
            "pages_crawled": 0,
            "pages_changed": 0,
            "pages_added": 0,
            "memory_entries_created": 0,
            "errors": []
        }

        # Get URLs to crawl
        if client_id:
            client = await self.client_repo.get_by_client_id(client_id)
            if not client:
                raise ValueError(f"Client {client_id} not found")
            base_url = client["base_url"]
            auth_config = client.get("auth", {})
        else:
            # Global crawl configuration
            base_url = os.getenv("DEFAULT_BASE_URL", "https://app.solarplatform.com")
            auth_config = {}

        # Initialize crawler
        crawler = await self._get_crawler(base_url, auth_config, client_id)

        try:
            # Get sitemap URLs
            sitemap_urls = await crawler.get_sitemap()
            logger.info(f"Found {len(sitemap_urls)} URLs in sitemap")

            # Crawl pages in batches
            batch_size = 10
            all_page_data = {}

            for i in range(0, len(sitemap_urls), batch_size):
                batch = sitemap_urls[i:i + batch_size]

                if isinstance(crawler, StaticBatchCrawler):
                    batch_results = await crawler.crawl_batch(batch)
                else:
                    # Dynamic crawler - crawl sequentially
                    batch_results = {}
                    for url in batch:
                        page_data = await crawler.crawl(url)
                        if page_data:
                            batch_results[url] = page_data

                all_page_data.update(batch_results)
                results["pages_crawled"] += len(batch_results)

                # Process batch immediately to save memory
                await self._process_crawled_pages(
                    batch_results,
                    client_id,
                    crawl_id,
                    results
                )

            # Process changes
            changes = await self.incremental_manager.process_crawl_results(
                all_page_data,
                crawl_id
            )

            results["pages_changed"] = changes["pages_updated"]
            results["pages_added"] = changes["pages_added"]

            # Notify about changes
            await self.change_notifier.notify_changes(changes, crawl_id)

        finally:
            await crawler.cleanup()

        return results

    async def _execute_incremental_crawl(
        self,
        client_id: Optional[str],
        crawl_id: str
    ) -> Dict[str, Any]:
        """Execute incremental crawl of changed pages only"""
        logger.info(f"Starting incremental crawl {crawl_id} for client {client_id or 'global'}")

        results = {
            "pages_crawled": 0,
            "pages_changed": 0,
            "pages_added": 0,
            "memory_entries_updated": 0,
            "errors": []
        }

        # Get pages to crawl
        pages_to_crawl = await self.incremental_manager.get_pages_to_crawl(client_id)

        if not pages_to_crawl:
            logger.info("No pages need re-crawling")
            return results

        logger.info(f"Found {len(pages_to_crawl)} pages to re-crawl")

        # Get client configuration
        base_url, auth_config = await self._get_client_config(client_id)

        # Initialize crawler
        crawler = await self._get_crawler(base_url, auth_config, client_id)

        try:
            # Crawl changed pages
            crawled_data = {}

            if isinstance(crawler, StaticBatchCrawler):
                crawled_data = await crawler.crawl_batch(pages_to_crawl)
            else:
                for url in pages_to_crawl:
                    page_data = await crawler.crawl(url)
                    if page_data:
                        crawled_data[url] = page_data

            results["pages_crawled"] = len(crawled_data)

            # Process pages
            await self._process_crawled_pages(
                crawled_data,
                client_id,
                crawl_id,
                results
            )

            # Detect and process changes
            changes = await self.incremental_manager.process_crawl_results(
                crawled_data,
                crawl_id
            )

            results["pages_changed"] = changes["pages_updated"]
            results["pages_added"] = changes["pages_added"]

            # Notify about changes
            if changes["total_changes"] > 0:
                await self.change_notifier.notify_changes(changes, crawl_id)

        finally:
            await crawler.cleanup()

        return results

    async def _execute_config_crawl(
        self,
        client_id: str,
        crawl_id: str
    ) -> Dict[str, Any]:
        """Execute crawl after client configuration change"""
        logger.info(f"Starting config crawl {crawl_id} for client {client_id}")

        if not client_id:
            raise ValueError("Client ID required for config crawl")

        results = {
            "memory_entries_updated": 0,
            "errors": []
        }

        # Get updated client configuration
        client = await self.client_repo.get_by_client_id(client_id)
        if not client:
            raise ValueError(f"Client {client_id} not found")

        # Get all existing pages for features enabled for this client
        # This would involve checking which features are enabled and regenerating
        # memory entries with updated labels/permissions

        # Get client's enabled features
        from ..models.database import BaseRepository
        config_repo = BaseRepository(self.db, "client_configs")
        client_config = await config_repo.find_one({"client_id": client_id})

        if client_config:
            # Regenerate memory entries for all enabled features
            memory_entries = []

            for feature_config in client_config.get("feature_configs", []):
                if feature_config["enabled"]:
                    # Get pages for this feature
                    feature_pages = await self.page_repo.get_by_feature(
                        feature_config["feature_id"]
                    )

                    for page in feature_pages:
                        # Generate memory with client context
                        context = {
                            "client_id": client_id,
                            "label_override": feature_config.get("label_override")
                        }

                        # Summarize page with context
                        summary = await self.summarizer.summarize_page(page, context)

                        # Generate memory entry
                        memory = await self.memory_generator.generate_memory_entry(
                            summary,
                            page,
                            context
                        )

                        memory_entries.append(memory)

            # Update vector store
            if memory_entries:
                # Clear old memories for this client
                await self.vector_store.clear_client_memories(client_id)

                # Add new memories
                await self.vector_store.add_memories(memory_entries)

                # Save to database
                await self.memory_repo.bulk_upsert(
                    [m.dict() for m in memory_entries]
                )

                results["memory_entries_updated"] = len(memory_entries)

        return results

    async def _process_crawled_pages(
        self,
        pages: Dict[str, Dict[str, Any]],
        client_id: Optional[str],
        crawl_id: str,
        results: Dict[str, Any]
    ):
        """Process crawled pages: summarize and create memory entries"""

        # Get client context if applicable
        context = None
        if client_id:
            client = await self.client_repo.get_by_client_id(client_id)
            context = {
                "client_id": client_id,
                "client_type": client.get("industry_segment"),
                "asset_types": client.get("asset_types", [])
            }

        # Batch summarize pages
        page_list = list(pages.values())
        summaries = await self.batch_summarizer.summarize_batch(page_list, context)

        # Generate memory entries
        memory_entries = []

        for page_data, summary in zip(page_list, summaries):
            if "error" in summary:
                results["errors"].append({
                    "url": page_data.get("url"),
                    "error": summary["error"]
                })
                continue

            # Generate memory entry
            memory = await self.memory_generator.generate_memory_entry(
                summary,
                page_data,
                context
            )

            memory_entries.append(memory)

        # Store memories
        if memory_entries:
            # Add to vector store
            await self.vector_store.add_memories(memory_entries)

            # Save to database
            await self.memory_repo.bulk_upsert(
                [m.dict() for m in memory_entries]
            )

            results["memory_entries_created"] = len(memory_entries)
            logger.info(f"Created {len(memory_entries)} memory entries")

    async def _get_crawler(
        self,
        base_url: str,
        auth_config: Dict[str, Any],
        client_id: Optional[str]
    ):
        """Get appropriate crawler based on site type"""

        # Determine if site needs dynamic crawling
        # This could be based on client configuration or auto-detection
        needs_js = auth_config.get("requires_js", False)

        crawler_config = {
            "base_url": base_url,
            "max_depth": 3,
            "rate_limit_requests": 10,
            "rate_limit_window": 60,
            "user_agent": "WebsiteIntelligencePlatform/1.0",
            "respect_robots_txt": True
        }

        # Add authentication
        if auth_config:
            crawler_config.update(auth_config)

        if needs_js:
            # Use dynamic crawler for JavaScript-heavy sites
            crawler = DynamicCrawler(crawler_config)
        else:
            # Use static crawler for server-rendered sites
            crawler = StaticBatchCrawler(crawler_config)

        await crawler.initialize()
        return crawler

    async def _get_client_config(
        self,
        client_id: Optional[str]
    ) -> Tuple[str, Dict[str, Any]]:
        """Get client crawl configuration"""

        if client_id:
            client = await self.client_repo.get_by_client_id(client_id)
            if not client:
                raise ValueError(f"Client {client_id} not found")

            base_url = client["base_url"]
            auth_config = client.get("auth", {})
        else:
            # Global configuration
            base_url = os.getenv("DEFAULT_BASE_URL", "https://app.solarplatform.com")
            auth_config = {}

        return base_url, auth_config

    async def _complete_crawl(self, crawl_id: str, results: Dict[str, Any]):
        """Mark crawl as completed"""

        await self.crawl_log_repo.update_one(
            {"crawl_id": crawl_id},
            {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                **results
            }
        )

        if crawl_id in self.active_crawls:
            del self.active_crawls[crawl_id]

        logger.info(f"Crawl {crawl_id} completed successfully")

    async def _fail_crawl(self, crawl_id: str, error: str):
        """Mark crawl as failed"""

        await self.crawl_log_repo.update_one(
            {"crawl_id": crawl_id},
            {
                "status": "failed",
                "completed_at": datetime.utcnow(),
                "errors": [{"error": error}]
            }
        )

        if crawl_id in self.active_crawls:
            del self.active_crawls[crawl_id]

        logger.error(f"Crawl {crawl_id} failed: {error}")

    async def trigger_client_crawl(self, client_id: str, trigger: str):
        """Trigger a crawl for a specific client"""

        # Check if crawl already running for this client
        running_crawls = await self.crawl_log_repo.get_running_crawls()
        for crawl in running_crawls:
            if crawl.get("client_id") == client_id:
                logger.warning(f"Crawl already running for client {client_id}")
                return

        # Execute crawl
        await self.execute_crawl(
            crawl_type="config",
            client_id=client_id,
            trigger=trigger
        )


class CrawlScheduler:
    """
    Manages scheduled crawling tasks
    """

    def __init__(self, orchestrator: CrawlOrchestrator):
        self.orchestrator = orchestrator
        self.scheduled_tasks = {}
        self.running = False

    async def start(self):
        """Start the scheduler"""
        self.running = True
        logger.info("Crawl scheduler started")

        # Schedule tasks
        asyncio.create_task(self._run_global_crawl())
        asyncio.create_task(self._run_client_crawls())

    async def stop(self):
        """Stop the scheduler"""
        self.running = False

        # Cancel scheduled tasks
        for task in self.scheduled_tasks.values():
            task.cancel()

        logger.info("Crawl scheduler stopped")

    async def _run_global_crawl(self):
        """Run periodic global crawl"""
        while self.running:
            try:
                # Run daily at 2 AM
                await asyncio.sleep(86400)  # 24 hours

                logger.info("Running scheduled global crawl")
                await self.orchestrator.execute_crawl(
                    crawl_type="incremental",
                    client_id=None,
                    trigger="scheduled"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Global crawl failed: {e}")

    async def _run_client_crawls(self):
        """Run periodic client-specific crawls"""
        while self.running:
            try:
                # Run every 6 hours
                await asyncio.sleep(21600)  # 6 hours

                # Get all clients
                client_repo = ClientRepository(self.orchestrator.db)
                clients = await client_repo.find_many({})

                for client in clients:
                    if not self.running:
                        break

                    client_id = client["client_id"]
                    logger.info(f"Running scheduled crawl for client {client_id}")

                    await self.orchestrator.execute_crawl(
                        crawl_type="incremental",
                        client_id=client_id,
                        trigger="scheduled"
                    )

                    # Space out client crawls
                    await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Client crawl failed: {e}")


# Add missing import
import os