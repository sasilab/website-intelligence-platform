"""
Static HTML crawler using aiohttp and BeautifulSoup
Optimized for server-rendered websites and documentation sites
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import logging

from .base_crawler import BaseCrawler
from ..models.schemas import Page, PageComponent

logger = logging.getLogger(__name__)


class StaticCrawler(BaseCrawler):
    """Crawler for static HTML content"""

    async def _setup_session(self):
        """Setup aiohttp session"""
        timeout = aiohttp.ClientTimeout(total=self.config.get("timeout", 30))
        headers = {
            "User-Agent": self.config.get("user_agent", "WebsiteIntelligencePlatform/1.0")
        }

        # Support for authentication if needed
        auth = None
        if self.config.get("auth_type") == "basic":
            auth = aiohttp.BasicAuth(
                self.config.get("username", ""),
                self.config.get("password", "")
            )

        connector = aiohttp.TCPConnector(limit=10, force_close=True)

        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            auth=auth,
            connector=connector
        )

    async def _fetch_and_parse(self, url: str) -> Dict[str, Any]:
        """Fetch and parse a static HTML page"""
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Got status {response.status} for {url}")
                    return {}

                html_content = await response.text()
                soup = BeautifulSoup(html_content, "html.parser")

                # Extract all page data
                page_data = {
                    "url": url,
                    "status_code": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "content_hash": self._generate_content_hash(html_content),
                    "metadata": self._extract_metadata(soup),
                    "navigation": self._extract_navigation(soup),
                    "components": [comp.dict() for comp in self._extract_page_components(soup)],
                    "linked_pages": self._extract_linked_pages(soup, url),
                    "content": self._extract_content(soup)
                }

                # Extract headings for structure
                page_data["headings"] = self._extract_headings(soup)

                # Extract any JavaScript-rendered content markers
                page_data["requires_js"] = self._check_js_requirements(soup)

                return page_data

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching {url}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return {}

    def _extract_content(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract main content from the page"""
        content = {
            "main_text": "",
            "important_elements": []
        }

        # Try to find main content area
        main_content = soup.find(["main", "article"]) or soup.find(
            class_=["content", "main-content", "container"]
        )

        if main_content:
            # Extract text while preserving some structure
            content["main_text"] = main_content.get_text(separator=" ", strip=True)

            # Extract important elements
            for element in main_content.find_all(["h1", "h2", "h3", "button", "a"]):
                elem_info = {
                    "tag": element.name,
                    "text": element.get_text(strip=True),
                    "attributes": {}
                }

                # Get relevant attributes
                if element.name == "a" and element.get("href"):
                    elem_info["attributes"]["href"] = element["href"]
                if element.get("id"):
                    elem_info["attributes"]["id"] = element["id"]
                if element.get("class"):
                    elem_info["attributes"]["class"] = " ".join(element["class"])

                content["important_elements"].append(elem_info)
        else:
            # Fallback: get body text
            body = soup.find("body")
            if body:
                content["main_text"] = body.get_text(separator=" ", strip=True)

        return content

    def _extract_headings(self, soup: BeautifulSoup) -> list:
        """Extract heading structure"""
        headings = []

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            heading = {
                "level": int(tag.name[1]),
                "text": tag.get_text(strip=True),
                "id": tag.get("id", "")
            }
            headings.append(heading)

        return headings

    def _check_js_requirements(self, soup: BeautifulSoup) -> bool:
        """Check if page requires JavaScript rendering"""
        js_indicators = [
            # React
            soup.find(id="root"),
            soup.find(id="app"),
            soup.find(attrs={"data-react-root": True}),

            # Vue
            soup.find(id="vue-app"),
            soup.find(attrs={"v-app": True}),

            # Angular
            soup.find("app-root"),
            soup.find(attrs={"ng-app": True}),

            # Generic SPA indicators
            soup.find(class_=["loading", "spinner"]),
            soup.find(text=lambda text: text and "Loading..." in text)
        ]

        # Check for common SPA patterns
        scripts = soup.find_all("script", src=True)
        for script in scripts:
            src = script.get("src", "")
            if any(framework in src.lower() for framework in ["react", "vue", "angular"]):
                return True

        return any(js_indicators)


class StaticBatchCrawler(StaticCrawler):
    """Optimized crawler for batch processing multiple URLs"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.semaphore = asyncio.Semaphore(config.get("max_concurrent", 5))

    async def crawl_batch(self, urls: list) -> Dict[str, Dict[str, Any]]:
        """Crawl multiple URLs concurrently"""
        tasks = [self._crawl_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        crawled_data = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to crawl {url}: {result}")
                crawled_data[url] = {"error": str(result)}
            else:
                crawled_data[url] = result

        return crawled_data

    async def _crawl_with_semaphore(self, url: str) -> Dict[str, Any]:
        """Crawl with concurrency control"""
        async with self.semaphore:
            await self.rate_limiter.acquire()
            return await self._fetch_and_parse(url)