"""
Change detection service for identifying website updates
"""

import hashlib
import difflib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging

from ..models.schemas import Page, CrawlDiff, CrawlType
from ..models.database import PageRepository, CrawlLogRepository, DatabaseManager

logger = logging.getLogger(__name__)


class ChangeDetector:
    """
    Detects changes between crawled pages and stored versions
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager.db
        self.page_repo = PageRepository(self.db)
        self.crawl_log_repo = CrawlLogRepository(self.db)

    async def detect_changes(
        self,
        new_page_data: Dict[str, Any],
        page_id: str
    ) -> Optional[CrawlDiff]:
        """
        Detect changes between new page data and stored version

        Returns:
            CrawlDiff object if changes detected, None otherwise
        """
        # Get stored page
        stored_page = await self.page_repo.get_by_page_id(page_id)

        if not stored_page:
            # New page
            return CrawlDiff(
                page_id=page_id,
                change_type="new_page",
                new_hash=new_page_data.get("content_hash", "")
            )

        # Compare content hashes
        old_hash = stored_page.get("content_hash", "")
        new_hash = new_page_data.get("content_hash", "")

        if old_hash == new_hash:
            # No changes
            return None

        # Determine what changed
        fields_changed = await self._identify_changed_fields(stored_page, new_page_data)

        change_type = self._categorize_change(fields_changed)

        return CrawlDiff(
            page_id=page_id,
            change_type=change_type,
            fields_changed=fields_changed,
            old_hash=old_hash,
            new_hash=new_hash
        )

    async def _identify_changed_fields(
        self,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> List[str]:
        """Identify which specific fields have changed"""
        changed_fields = []

        # Check navigation changes
        if self._hash_dict(old_data.get("navigation", {})) != self._hash_dict(new_data.get("navigation", {})):
            changed_fields.append("navigation")

        # Check component changes
        if self._hash_list(old_data.get("components", [])) != self._hash_list(new_data.get("components", [])):
            changed_fields.append("components")

        # Check content changes
        old_content = old_data.get("content", {}).get("main_text", "")
        new_content = new_data.get("content", {}).get("main_text", "")
        if self._is_significant_text_change(old_content, new_content):
            changed_fields.append("content")

        # Check metadata changes
        if old_data.get("metadata") != new_data.get("metadata"):
            changed_fields.append("metadata")

        # Check heading structure changes
        if old_data.get("headings") != new_data.get("headings"):
            changed_fields.append("headings")

        # Check linked pages changes
        old_links = set(old_data.get("linked_pages", []))
        new_links = set(new_data.get("linked_pages", []))
        if old_links != new_links:
            changed_fields.append("linked_pages")

        return changed_fields

    def _categorize_change(self, fields_changed: List[str]) -> str:
        """Categorize the type of change based on fields"""
        if "navigation" in fields_changed:
            return "nav_changed"
        elif "content" in fields_changed and len(fields_changed) == 1:
            return "content_updated"
        elif "components" in fields_changed:
            return "structure_changed"
        else:
            return "minor_update"

    def _hash_dict(self, data: Dict) -> str:
        """Generate hash for a dictionary"""
        import json
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _hash_list(self, data: List) -> str:
        """Generate hash for a list"""
        import json
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _is_significant_text_change(self, old_text: str, new_text: str, threshold: float = 0.1) -> bool:
        """
        Check if text change is significant enough to warrant update

        Args:
            threshold: Minimum percentage of change to be considered significant
        """
        if not old_text and new_text:
            return True
        if old_text and not new_text:
            return True
        if not old_text and not new_text:
            return False

        # Calculate similarity ratio
        similarity = difflib.SequenceMatcher(None, old_text, new_text).ratio()

        # Change is significant if similarity is below (1 - threshold)
        return similarity < (1 - threshold)


class IncrementalCrawlManager:
    """
    Manages incremental crawling based on changes
    """

    def __init__(self, db_manager: DatabaseManager, change_detector: ChangeDetector):
        self.db = db_manager.db
        self.page_repo = PageRepository(self.db)
        self.crawl_log_repo = CrawlLogRepository(self.db)
        self.change_detector = change_detector

    async def get_pages_to_crawl(
        self,
        client_id: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> List[str]:
        """
        Get list of pages that need to be crawled

        Returns:
            List of page URLs to crawl
        """
        pages_to_crawl = []

        # Get last successful crawl
        last_crawl = await self.crawl_log_repo.get_latest_crawl(
            client_id=client_id,
            crawl_type=CrawlType.FULL.value
        )

        if not last_crawl:
            # No previous crawl, need full crawl
            return []

        last_crawl_time = last_crawl.get("completed_at")
        if not last_crawl_time:
            last_crawl_time = last_crawl.get("started_at")

        # Get pages modified since last crawl
        if since:
            check_time = since
        else:
            check_time = last_crawl_time

        # Get all pages
        all_pages = await self.page_repo.find_many({})

        for page in all_pages:
            # Check if page should be recrawled
            if await self._should_recrawl_page(page, check_time):
                pages_to_crawl.append(page.get("url_pattern", ""))

        return pages_to_crawl

    async def _should_recrawl_page(self, page: Dict[str, Any], since: datetime) -> bool:
        """
        Determine if a page should be recrawled

        Criteria:
        - Page hasn't been crawled in X hours
        - Page is marked as high priority
        - Page has frequent changes historically
        """
        last_crawled = page.get("last_crawled")

        if not last_crawled:
            return True

        # Convert string to datetime if needed
        if isinstance(last_crawled, str):
            last_crawled = datetime.fromisoformat(last_crawled.replace('Z', '+00:00'))

        # Always recrawl if older than threshold
        age_threshold = timedelta(hours=24)  # Configurable
        if datetime.utcnow() - last_crawled > age_threshold:
            return True

        # Check priority pages (could be stored in page metadata)
        if page.get("priority") == "high":
            priority_threshold = timedelta(hours=6)
            if datetime.utcnow() - last_crawled > priority_threshold:
                return True

        return False

    async def process_crawl_results(
        self,
        crawl_results: Dict[str, Dict[str, Any]],
        crawl_id: str
    ) -> Dict[str, Any]:
        """
        Process results from a crawl and identify changes

        Returns:
            Summary of changes detected
        """
        changes_summary = {
            "pages_added": 0,
            "pages_updated": 0,
            "pages_removed": 0,
            "total_changes": 0,
            "changes": []
        }

        for url, page_data in crawl_results.items():
            if "error" in page_data:
                continue

            # Generate page_id from URL
            page_id = self._generate_page_id(url)

            # Detect changes
            change_diff = await self.change_detector.detect_changes(page_data, page_id)

            if change_diff:
                changes_summary["changes"].append(change_diff.dict())

                if change_diff.change_type == "new_page":
                    changes_summary["pages_added"] += 1
                else:
                    changes_summary["pages_updated"] += 1

                changes_summary["total_changes"] += 1

                # Update page in database
                await self._update_page(page_id, page_data)

        return changes_summary

    async def _update_page(self, page_id: str, page_data: Dict[str, Any]):
        """Update page in database"""
        page_data["page_id"] = page_id
        page_data["last_crawled"] = datetime.utcnow()

        await self.page_repo.update_one(
            {"page_id": page_id},
            page_data,
            upsert=True
        )

    def _generate_page_id(self, url: str) -> str:
        """Generate consistent page ID from URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]


class ChangeNotifier:
    """
    Notifies relevant systems about detected changes
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url
        self.subscribers = []

    def subscribe(self, callback):
        """Subscribe to change notifications"""
        self.subscribers.append(callback)

    async def notify_changes(self, changes: Dict[str, Any], crawl_id: str):
        """Notify all subscribers about changes"""
        notification = {
            "crawl_id": crawl_id,
            "timestamp": datetime.utcnow().isoformat(),
            "changes": changes
        }

        # Notify local subscribers
        for subscriber in self.subscribers:
            try:
                await subscriber(notification)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")

        # Send webhook notification
        if self.webhook_url and changes.get("total_changes", 0) > 0:
            await self._send_webhook(notification)

    async def _send_webhook(self, notification: Dict[str, Any]):
        """Send webhook notification"""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=notification,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Webhook returned status {response.status}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


class SmartChangeDetector(ChangeDetector):
    """
    Advanced change detector with ML-based significance scoring
    """

    async def calculate_change_significance(
        self,
        change_diff: CrawlDiff,
        page_data: Dict[str, Any]
    ) -> float:
        """
        Calculate significance score for a change (0-1)

        Factors:
        - Type of change (nav > content > metadata)
        - Page importance (based on traffic, links)
        - Historical change frequency
        """
        score = 0.0

        # Base score by change type
        change_type_scores = {
            "new_page": 1.0,
            "nav_changed": 0.9,
            "structure_changed": 0.7,
            "content_updated": 0.5,
            "minor_update": 0.2
        }

        score = change_type_scores.get(change_diff.change_type, 0.3)

        # Adjust based on fields changed
        critical_fields = ["navigation", "components", "linked_pages"]
        for field in change_diff.fields_changed:
            if field in critical_fields:
                score += 0.1

        # Adjust based on page priority
        if page_data.get("priority") == "high":
            score *= 1.2
        elif page_data.get("priority") == "low":
            score *= 0.8

        # Normalize score to 0-1 range
        return min(1.0, max(0.0, score))

    async def get_change_summary(
        self,
        changes: List[CrawlDiff],
        verbose: bool = False
    ) -> str:
        """Generate human-readable change summary"""
        if not changes:
            return "No changes detected."

        summary_parts = []

        # Group changes by type
        changes_by_type = {}
        for change in changes:
            change_type = change.change_type
            if change_type not in changes_by_type:
                changes_by_type[change_type] = []
            changes_by_type[change_type].append(change)

        # Generate summary for each type
        for change_type, type_changes in changes_by_type.items():
            count = len(type_changes)

            if change_type == "new_page":
                summary_parts.append(f"{count} new page(s) added")
            elif change_type == "nav_changed":
                summary_parts.append(f"{count} page(s) with navigation changes")
            elif change_type == "content_updated":
                summary_parts.append(f"{count} page(s) with content updates")
            elif change_type == "structure_changed":
                summary_parts.append(f"{count} page(s) with structural changes")

            if verbose:
                # Add details about specific pages
                for change in type_changes[:3]:  # Limit to 3 examples
                    page_id = change.page_id[:8] + "..."
                    fields = ", ".join(change.fields_changed[:3])
                    summary_parts.append(f"  - Page {page_id}: {fields}")

        return "; ".join(summary_parts)