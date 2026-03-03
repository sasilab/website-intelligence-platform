"""
Dynamic content crawler using Playwright
Handles JavaScript-rendered content and SPAs
"""

import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright, Page as PlaywrightPage, Browser
from bs4 import BeautifulSoup
import logging

from .base_crawler import BaseCrawler
from ..models.schemas import PageComponent

logger = logging.getLogger(__name__)


class DynamicCrawler(BaseCrawler):
    """Crawler for JavaScript-rendered content"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.browser: Optional[Browser] = None
        self.context = None
        self.playwright = None

    async def _setup_session(self):
        """Setup Playwright browser"""
        self.playwright = await async_playwright().start()

        # Browser options
        browser_type = self.config.get("browser", "chromium")
        headless = self.config.get("headless", True)

        if browser_type == "chromium":
            self.browser = await self.playwright.chromium.launch(headless=headless)
        elif browser_type == "firefox":
            self.browser = await self.playwright.firefox.launch(headless=headless)
        else:
            self.browser = await self.playwright.webkit.launch(headless=headless)

        # Create browser context with authentication if needed
        context_options = {
            "user_agent": self.config.get("user_agent", "WebsiteIntelligencePlatform/1.0"),
            "viewport": {"width": 1920, "height": 1080}
        }

        # Add authentication if provided
        if self.config.get("auth_cookies"):
            context_options["storage_state"] = self.config["auth_cookies"]
        elif self.config.get("http_credentials"):
            context_options["http_credentials"] = self.config["http_credentials"]

        self.context = await self.browser.new_context(**context_options)

    async def _fetch_and_parse(self, url: str) -> Dict[str, Any]:
        """Fetch and parse a dynamic page"""
        page = None
        try:
            page = await self.context.new_page()

            # Set up event listeners for network activity
            network_idle_promise = self._wait_for_network_idle(page)

            # Navigate to the page
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=self.config.get("timeout", 30000)
            )

            # Wait for specific elements if configured
            if self.config.get("wait_selector"):
                await page.wait_for_selector(
                    self.config["wait_selector"],
                    timeout=10000
                )

            # Wait for network to be idle
            await network_idle_promise

            # Additional wait for dynamic content
            await page.wait_for_timeout(1000)

            # Get the fully rendered HTML
            html_content = await page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract page data
            page_data = {
                "url": url,
                "status_code": response.status if response else 200,
                "content_hash": self._generate_content_hash(html_content),
                "metadata": self._extract_metadata(soup),
                "navigation": await self._extract_dynamic_navigation(page, soup),
                "components": await self._extract_dynamic_components(page, soup),
                "linked_pages": self._extract_linked_pages(soup, url),
                "content": self._extract_content(soup),
                "headings": self._extract_headings(soup),
                "screenshots": []
            }

            # Take screenshot if configured
            if self.config.get("take_screenshots", False):
                screenshot_path = await self._take_screenshot(page, url)
                if screenshot_path:
                    page_data["screenshots"].append(screenshot_path)

            # Extract JavaScript-generated content
            page_data["js_data"] = await self._extract_js_data(page)

            return page_data

        except asyncio.TimeoutError:
            logger.error(f"Timeout while loading {url}")
            return {}
        except Exception as e:
            logger.error(f"Error crawling dynamic page {url}: {e}")
            return {}
        finally:
            if page:
                await page.close()

    async def _wait_for_network_idle(self, page: PlaywrightPage, timeout: int = 5000):
        """Wait for network activity to settle"""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except:
            # Network idle timeout is not critical
            pass

    async def _extract_dynamic_navigation(self, page: PlaywrightPage, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract navigation including dynamically loaded elements"""
        nav_data = self._extract_navigation(soup)

        # Check for hidden/collapsed navigation that needs interaction
        try:
            # Look for hamburger menu or mobile nav
            hamburger_selectors = [
                'button[aria-label*="menu"]',
                '.hamburger',
                '.menu-toggle',
                '[class*="menu-button"]'
            ]

            for selector in hamburger_selectors:
                if await page.locator(selector).count() > 0:
                    # Click to open menu
                    await page.click(selector)
                    await page.wait_for_timeout(500)

                    # Re-extract navigation
                    expanded_html = await page.content()
                    expanded_soup = BeautifulSoup(expanded_html, "html.parser")
                    expanded_nav = self._extract_navigation(expanded_soup)

                    # Merge with original navigation
                    for key in expanded_nav:
                        if expanded_nav[key] and len(expanded_nav[key]) > len(nav_data.get(key, [])):
                            nav_data[key] = expanded_nav[key]

                    break

        except Exception as e:
            logger.debug(f"Error extracting dynamic navigation: {e}")

        return nav_data

    async def _extract_dynamic_components(self, page: PlaywrightPage, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract components including dynamically rendered ones"""
        components = [comp.dict() for comp in self._extract_page_components(soup)]

        # Look for React/Vue/Angular components
        try:
            # Check for common component patterns
            component_info = await page.evaluate("""
                () => {
                    const components = [];

                    // React components
                    const reactRoots = document.querySelectorAll('[data-reactroot]');
                    reactRoots.forEach(root => {
                        components.push({
                            type: 'react',
                            name: root.getAttribute('data-component-name') || 'ReactComponent'
                        });
                    });

                    // Vue components
                    if (window.Vue || window.$nuxt) {
                        components.push({type: 'vue', name: 'VueApp'});
                    }

                    // Angular components
                    const angularElements = document.querySelectorAll('[ng-controller], [ng-app]');
                    angularElements.forEach(elem => {
                        components.push({
                            type: 'angular',
                            name: elem.getAttribute('ng-controller') || 'AngularComponent'
                        });
                    });

                    // Custom data attributes
                    const customComponents = document.querySelectorAll('[data-component]');
                    customComponents.forEach(comp => {
                        components.push({
                            type: 'custom',
                            name: comp.getAttribute('data-component')
                        });
                    });

                    return components;
                }
            """)

            for comp in component_info:
                components.append({
                    "name": comp.get("name", "DynamicComponent"),
                    "purpose": f"{comp.get('type', 'Unknown')} component",
                    "component_type": "dynamic",
                    "actions": []
                })

        except Exception as e:
            logger.debug(f"Error extracting dynamic components: {e}")

        return components

    async def _extract_js_data(self, page: PlaywrightPage) -> Dict[str, Any]:
        """Extract data from JavaScript context"""
        js_data = {}

        try:
            # Extract common data patterns
            js_data = await page.evaluate("""
                () => {
                    const data = {};

                    // Check for common state management
                    if (window.__REDUX_STATE__) {
                        data.redux_state = Object.keys(window.__REDUX_STATE__);
                    }

                    if (window.__INITIAL_STATE__) {
                        data.initial_state = Object.keys(window.__INITIAL_STATE__);
                    }

                    // Check for API endpoints
                    if (window.API_BASE_URL) {
                        data.api_base = window.API_BASE_URL;
                    }

                    // Check for feature flags
                    if (window.FEATURES || window.featureFlags) {
                        data.features = window.FEATURES || window.featureFlags;
                    }

                    // Get page-specific data
                    const pageData = document.querySelector('[data-page-data]');
                    if (pageData) {
                        try {
                            data.page_data = JSON.parse(pageData.textContent);
                        } catch (e) {}
                    }

                    return data;
                }
            """)

        except Exception as e:
            logger.debug(f"Error extracting JavaScript data: {e}")

        return js_data

    def _extract_content(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract main content from the page"""
        content = {
            "main_text": "",
            "important_elements": []
        }

        # Try multiple selectors for main content
        main_selectors = [
            "main",
            "article",
            '[role="main"]',
            ".main-content",
            "#content",
            ".content",
            ".container"
        ]

        main_content = None
        for selector in main_selectors:
            if selector.startswith(".") or selector.startswith("#"):
                main_content = soup.select_one(selector)
            else:
                main_content = soup.find(selector)

            if main_content:
                break

        if main_content:
            content["main_text"] = main_content.get_text(separator=" ", strip=True)

            # Extract interactive elements
            for element in main_content.find_all(["button", "a", "input", "select"]):
                elem_info = {
                    "tag": element.name,
                    "text": element.get_text(strip=True) if element.name != "input" else "",
                    "type": element.get("type", ""),
                    "attributes": {}
                }

                if element.get("id"):
                    elem_info["attributes"]["id"] = element["id"]
                if element.get("class"):
                    elem_info["attributes"]["class"] = " ".join(element["class"])
                if element.name == "a" and element.get("href"):
                    elem_info["attributes"]["href"] = element["href"]

                content["important_elements"].append(elem_info)

        return content

    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract heading structure"""
        headings = []

        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            headings.append({
                "level": int(heading.name[1]),
                "text": heading.get_text(strip=True),
                "id": heading.get("id", "")
            })

        return headings

    async def _take_screenshot(self, page: PlaywrightPage, url: str) -> Optional[str]:
        """Take a screenshot of the page"""
        try:
            import hashlib
            from pathlib import Path

            # Create screenshots directory
            screenshots_dir = Path(self.config.get("screenshots_path", "./data/screenshots"))
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename from URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
            filename = screenshots_dir / f"{url_hash}.png"

            await page.screenshot(path=str(filename), full_page=True)
            return str(filename)

        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return None

    async def cleanup(self):
        """Cleanup browser resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


class DynamicInteractiveCrawler(DynamicCrawler):
    """Advanced crawler that can interact with page elements"""

    async def crawl_with_interaction(self, url: str, interactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Crawl a page with specific interactions"""
        page = None
        try:
            page = await self.context.new_page()
            await page.goto(url, wait_until="networkidle")

            results = {"initial_state": await self._fetch_and_parse(url)}

            # Perform interactions
            for interaction in interactions:
                action_type = interaction.get("type")
                selector = interaction.get("selector")

                if action_type == "click":
                    await page.click(selector)
                elif action_type == "fill":
                    await page.fill(selector, interaction.get("value", ""))
                elif action_type == "select":
                    await page.select_option(selector, interaction.get("value", ""))
                elif action_type == "hover":
                    await page.hover(selector)

                # Wait for changes to load
                await page.wait_for_timeout(1000)

                # Capture state after interaction
                state_name = interaction.get("name", f"after_{action_type}")
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                results[state_name] = {
                    "components": await self._extract_dynamic_components(page, soup),
                    "content": self._extract_content(soup)
                }

            return results

        finally:
            if page:
                await page.close()