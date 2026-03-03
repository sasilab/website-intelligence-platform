"""
Base crawler implementation with support for both static and dynamic content
"""

import os
import time
import hashlib
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging

import aiohttp
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser

from ..models.schemas import Page, PageComponent, LinkedPage
from ..utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """Abstract base class for web crawlers"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "")
        self.max_depth = config.get("max_depth", 5)
        self.rate_limiter = RateLimiter(
            requests_per_window=config.get("rate_limit_requests", 10),
            window_seconds=config.get("rate_limit_window", 60)
        )
        self.visited_urls = set()
        self.url_queue = asyncio.Queue()
        self.respect_robots = config.get("respect_robots_txt", True)
        self.robots_parser = None
        self.session = None

    async def initialize(self):
        """Initialize the crawler"""
        await self._setup_session()
        if self.respect_robots:
            await self._load_robots_txt()

    @abstractmethod
    async def _setup_session(self):
        """Setup the HTTP session or browser"""
        pass

    async def _load_robots_txt(self):
        """Load and parse robots.txt"""
        try:
            robots_url = urljoin(self.base_url, "/robots.txt")
            self.robots_parser = RobotFileParser()
            self.robots_parser.set_url(robots_url)
            self.robots_parser.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Failed to load robots.txt: {e}")
            self.robots_parser = None

    def can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        if not self.respect_robots or not self.robots_parser:
            return True

        user_agent = self.config.get("user_agent", "*")
        return self.robots_parser.can_fetch(user_agent, url)

    async def crawl(self, start_url: str, depth: int = 0) -> Dict[str, Any]:
        """Main crawl method"""
        if depth > self.max_depth:
            return {}

        if start_url in self.visited_urls:
            return {}

        if not self.can_fetch(start_url):
            logger.warning(f"Robots.txt disallows fetching: {start_url}")
            return {}

        await self.rate_limiter.acquire()
        self.visited_urls.add(start_url)

        try:
            page_data = await self._fetch_and_parse(start_url)
            if page_data:
                page_data["crawl_depth"] = depth
                page_data["timestamp"] = datetime.utcnow()

                # Recursively crawl linked pages
                linked_pages = page_data.get("linked_pages", [])
                for link in linked_pages[:10]:  # Limit to prevent explosion
                    if link not in self.visited_urls:
                        await self.url_queue.put((link, depth + 1))

            return page_data

        except Exception as e:
            logger.error(f"Error crawling {start_url}: {e}")
            return {}

    @abstractmethod
    async def _fetch_and_parse(self, url: str) -> Dict[str, Any]:
        """Fetch and parse a single page"""
        pass

    def _extract_navigation(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract navigation structure from HTML"""
        nav_data = {
            "main_nav": [],
            "sidebar_nav": [],
            "footer_nav": [],
            "breadcrumb": []
        }

        # Main navigation (typically in header)
        nav_elements = soup.find_all(["nav", "header"])
        for nav in nav_elements:
            links = nav.find_all("a", href=True)
            for link in links:
                nav_item = {
                    "label": link.get_text(strip=True),
                    "url": urljoin(self.base_url, link["href"]),
                    "location": "main"
                }
                nav_data["main_nav"].append(nav_item)

        # Sidebar navigation
        sidebar = soup.find(class_=["sidebar", "side-nav", "left-nav"])
        if sidebar:
            links = sidebar.find_all("a", href=True)
            for link in links:
                nav_item = {
                    "label": link.get_text(strip=True),
                    "url": urljoin(self.base_url, link["href"]),
                    "location": "sidebar"
                }
                nav_data["sidebar_nav"].append(nav_item)

        # Breadcrumb
        breadcrumb = soup.find(class_=["breadcrumb", "breadcrumbs"])
        if breadcrumb:
            items = breadcrumb.find_all(["a", "span"])
            nav_data["breadcrumb"] = [item.get_text(strip=True) for item in items]

        return nav_data

    def _extract_page_components(self, soup: BeautifulSoup) -> List[PageComponent]:
        """Extract UI components from the page"""
        components = []

        # Tables
        tables = soup.find_all("table")
        for i, table in enumerate(tables):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            component = PageComponent(
                name=f"Table_{i+1}",
                purpose=f"Data table with columns: {', '.join(headers[:5])}",
                component_type="table",
                actions=["Sort", "Filter", "Export"] if headers else []
            )
            components.append(component)

        # Forms
        forms = soup.find_all("form")
        for i, form in enumerate(forms):
            inputs = form.find_all(["input", "select", "textarea"])
            fields = {}
            for input_elem in inputs:
                field_name = input_elem.get("name", input_elem.get("id", f"field_{i}"))
                field_type = input_elem.get("type", input_elem.name)
                if field_name:
                    fields[field_name] = field_type

            component = PageComponent(
                name=f"Form_{i+1}",
                purpose=form.get("action", "Form submission"),
                component_type="form",
                actions=["Submit", "Reset"],
                fields=fields
            )
            components.append(component)

        # Charts/Graphs (common class names)
        charts = soup.find_all(class_=["chart", "graph", "visualization", "plot"])
        for i, chart in enumerate(charts):
            component = PageComponent(
                name=f"Chart_{i+1}",
                purpose="Data visualization",
                component_type="chart",
                actions=["Zoom", "Export", "Filter"]
            )
            components.append(component)

        return components

    def _extract_linked_pages(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """Extract all linked pages from the current page"""
        linked_pages = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip anchors, javascript, and external links
            if href.startswith("#") or href.startswith("javascript:"):
                continue

            # Convert to absolute URL
            absolute_url = urljoin(current_url, href)

            # Only include URLs from the same domain
            if urlparse(absolute_url).netloc == urlparse(self.base_url).netloc:
                if absolute_url not in seen_urls:
                    seen_urls.add(absolute_url)
                    linked_pages.append(absolute_url)

        return linked_pages

    def _generate_content_hash(self, content: str) -> str:
        """Generate hash of page content for change detection"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract page metadata"""
        metadata = {}

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            metadata["description"] = meta_desc.get("content", "")

        # Open Graph data
        og_tags = soup.find_all("meta", property=lambda x: x and x.startswith("og:"))
        for tag in og_tags:
            key = tag.get("property", "").replace("og:", "og_")
            metadata[key] = tag.get("content", "")

        return metadata

    async def get_sitemap(self) -> List[str]:
        """Fetch and parse sitemap.xml"""
        sitemap_urls = []

        try:
            sitemap_url = urljoin(self.base_url, "/sitemap.xml")
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        root = ET.fromstring(content)

                        # Handle different sitemap formats
                        namespaces = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                        # Check for sitemap index
                        sitemaps = root.findall(".//ns:sitemap/ns:loc", namespaces)
                        if sitemaps:
                            for sitemap in sitemaps:
                                # Recursively fetch sub-sitemaps
                                sub_urls = await self._fetch_sub_sitemap(sitemap.text)
                                sitemap_urls.extend(sub_urls)
                        else:
                            # Direct URL entries
                            urls = root.findall(".//ns:url/ns:loc", namespaces)
                            sitemap_urls = [url.text for url in urls]

        except Exception as e:
            logger.warning(f"Failed to fetch sitemap: {e}")

        return sitemap_urls

    async def _fetch_sub_sitemap(self, sitemap_url: str) -> List[str]:
        """Fetch and parse a sub-sitemap"""
        urls = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        root = ET.fromstring(content)
                        namespaces = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                        url_elements = root.findall(".//ns:url/ns:loc", namespaces)
                        urls = [url.text for url in url_elements]

        except Exception as e:
            logger.warning(f"Failed to fetch sub-sitemap {sitemap_url}: {e}")

        return urls

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()