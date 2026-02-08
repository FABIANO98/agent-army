"""Website analyzer using Crawl4AI + Claude."""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger


class WebsiteAnalyzer:
    """
    Analyzes websites using Crawl4AI for scraping and Claude for analysis.

    Falls back to basic httpx+BeautifulSoup if Crawl4AI is unavailable.
    """

    def __init__(
        self,
        llm_service: Any = None,
        browser_manager: Any = None,
    ) -> None:
        self._llm = llm_service
        self._browser = browser_manager
        self._logger = logger.bind(component="WebsiteAnalyzer")

    async def analyze(self, url: str) -> dict[str, Any]:
        """
        Scrape and analyze a website.

        Returns structured analysis including:
        - company_info: Name, industry, description
        - tech_analysis: Tech stack, mobile readiness, performance
        - problems: Identified issues
        - opportunities: Improvement opportunities
        - contact_info: Emails, phones, social media
        """
        # Try Crawl4AI first
        content = await self._scrape_with_crawl4ai(url)

        if not content:
            # Fallback to browser manager
            if self._browser and self._browser.is_available:
                content = await self._browser.get_page_content(url)

        if not content:
            # Fallback to basic httpx
            content = await self._scrape_basic(url)

        if not content:
            return {"error": "Could not fetch website", "url": url}

        # Analyze with Claude if available
        if self._llm and self._llm.is_available:
            return await self._analyze_with_llm(url, content)

        # Fallback to basic analysis
        return self._analyze_basic(url, content)

    async def _scrape_with_crawl4ai(self, url: str) -> Optional[str]:
        """Scrape using Crawl4AI."""
        try:
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url)
                if result and result.markdown:
                    return result.markdown
                return None
        except ImportError:
            self._logger.debug("crawl4ai not available")
            return None
        except Exception as e:
            self._logger.debug(f"crawl4ai error: {e}")
            return None

    async def _scrape_basic(self, url: str) -> Optional[str]:
        """Basic scraping with httpx."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
        except Exception as e:
            self._logger.debug(f"Basic scrape error: {e}")
        return None

    async def _analyze_with_llm(self, url: str, content: str) -> dict[str, Any]:
        """Analyze website content using Claude."""
        # Truncate content for LLM
        content_truncated = content[:8000]

        try:
            result = await self._llm.complete_structured(
                prompt=f"""Analysiere diese Webseite: {url}

Inhalt:
{content_truncated}

Erstelle eine strukturierte Analyse.""",
                system="""Du bist ein Webseiten-Analyst fuer Schweizer KMUs.
Analysiere die Webseite und identifiziere:
1. Firmeninfo (Name, Branche, Beschreibung)
2. Technische Analyse (Tech Stack, Mobile-Readiness, Performance-Indikatoren)
3. Probleme (veraltetes Design, fehlende Features, schlechte UX)
4. Verbesserungsmoeglichkeiten
5. Kontaktinfo (Emails, Telefon, Social Media)

Antworte NUR mit validem JSON.""",
                response_schema={
                    "type": "object",
                    "properties": {
                        "company_info": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "industry": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                        "tech_analysis": {
                            "type": "object",
                            "properties": {
                                "tech_stack": {"type": "array", "items": {"type": "string"}},
                                "mobile_ready": {"type": "boolean"},
                                "has_ssl": {"type": "boolean"},
                                "performance_issues": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "problems": {"type": "array", "items": {"type": "string"}},
                        "opportunities": {"type": "array", "items": {"type": "string"}},
                        "contact_info": {
                            "type": "object",
                            "properties": {
                                "emails": {"type": "array", "items": {"type": "string"}},
                                "phones": {"type": "array", "items": {"type": "string"}},
                                "social_media": {"type": "object"},
                            },
                        },
                    },
                },
                agent_id="website_analyzer",
            )
            result["url"] = url
            return result
        except Exception as e:
            self._logger.warning(f"LLM analysis failed: {e}")
            return self._analyze_basic(url, content)

    def _analyze_basic(self, url: str, content: str) -> dict[str, Any]:
        """Basic analysis without LLM."""
        import re

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "lxml") if "<html" in content.lower() else None
        text = soup.get_text() if soup else content

        problems: list[str] = []
        tech_stack: list[str] = []
        emails: list[str] = []

        if soup:
            if not soup.find("meta", attrs={"name": "viewport"}):
                problems.append("Nicht mobile-optimiert")
            if soup.find("table", attrs={"width": True}):
                problems.append("Veraltetes Tabellen-Layout")
            if soup.find("font"):
                problems.append("Veraltete HTML-Elemente")

            content_lower = content.lower()
            if "wordpress" in content_lower or "wp-content" in content_lower:
                tech_stack.append("WordPress")
            if "jquery" in content_lower:
                tech_stack.append("jQuery")
            if "bootstrap" in content_lower:
                tech_stack.append("Bootstrap")
            if "react" in content_lower:
                tech_stack.append("React")

        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        found_emails = re.findall(email_pattern, text)
        emails = [e for e in found_emails if "@example" not in e and "@test" not in e]

        return {
            "url": url,
            "company_info": {"name": "", "industry": "", "description": ""},
            "tech_analysis": {
                "tech_stack": tech_stack,
                "mobile_ready": "Nicht mobile-optimiert" not in problems,
                "has_ssl": url.startswith("https"),
                "performance_issues": [],
            },
            "problems": problems,
            "opportunities": [],
            "contact_info": {
                "emails": emails[:5],
                "phones": [],
                "social_media": {},
            },
        }
