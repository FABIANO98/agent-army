"""Shared Playwright browser manager."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from loguru import logger


class BrowserManager:
    """
    Manages a shared Playwright browser instance with concurrency control.

    Uses a semaphore to limit concurrent page operations.
    """

    def __init__(
        self,
        headless: bool = True,
        max_concurrent_pages: int = 3,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    ) -> None:
        self._headless = headless
        self._max_pages = max_concurrent_pages
        self._user_agent = user_agent
        self._semaphore = asyncio.Semaphore(max_concurrent_pages)
        self._browser: Any = None
        self._playwright: Any = None
        self._logger = logger.bind(component="BrowserManager")

    async def start(self) -> None:
        """Start the Playwright browser."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
            )
            self._logger.info("Browser started")
        except ImportError:
            self._logger.warning("playwright not installed - browser features disabled")
        except Exception as e:
            self._logger.warning(f"Failed to start browser: {e}")

    async def stop(self) -> None:
        """Stop the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._logger.info("Browser stopped")

    @property
    def is_available(self) -> bool:
        return self._browser is not None

    async def get_page_content(self, url: str, wait_for: Optional[str] = None) -> Optional[str]:
        """
        Fetch page content using Playwright.

        Args:
            url: URL to fetch
            wait_for: Optional CSS selector to wait for

        Returns:
            Page HTML content or None on failure
        """
        if not self._browser:
            return None

        async with self._semaphore:
            context = None
            page = None
            try:
                context = await self._browser.new_context(
                    user_agent=self._user_agent,
                )
                page = await context.new_page()

                await page.goto(url, wait_until="networkidle", timeout=30000)

                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=10000)

                content = await page.content()
                return content

            except Exception as e:
                self._logger.debug(f"Browser fetch error for {url}: {e}")
                return None
            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()

    async def screenshot(self, url: str) -> Optional[bytes]:
        """Take a screenshot of a URL."""
        if not self._browser:
            return None

        async with self._semaphore:
            context = None
            page = None
            try:
                context = await self._browser.new_context(
                    user_agent=self._user_agent,
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await page.screenshot(full_page=False)
            except Exception as e:
                self._logger.debug(f"Screenshot error for {url}: {e}")
                return None
            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()
