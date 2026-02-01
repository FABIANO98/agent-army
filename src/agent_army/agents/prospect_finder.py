"""ProspectFinder Agent - Finds new Swiss SME prospects daily."""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import ProspectStatus

if TYPE_CHECKING:
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


class ProspectFinderAgent(BaseAgent):
    """
    Finds new Swiss SME prospects daily.

    Searches for companies in target industries with potential website issues.
    Uses web search and scraping to find and evaluate prospects.
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize ProspectFinder agent."""
        super().__init__(
            name="ProspectFinder",
            agent_type="prospect_finder",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._last_search_time: Optional[datetime] = None
        self._daily_count = 0

        # Search queries for finding prospects
        self._search_queries = [
            "{industry} Unternehmen {region} Schweiz",
            "{industry} Firma {region}",
            "{industry} KMU {region} Kontakt",
            "{industry} Betrieb {region}",
            "kleine {industry} Firma {region}",
        ]

        # Default target settings
        self._target_industries = ["bau", "transport", "logistik", "handwerk"]
        self._target_regions = ["zürich", "bern", "basel", "luzern", "st. gallen"]
        self._daily_target = 20
        self._search_interval = 3600  # 1 hour

        if settings:
            self._target_industries = settings.agents.target_industries
            self._target_regions = settings.agents.target_regions
            self._daily_target = settings.agents.daily_prospect_target
            self._search_interval = settings.agents.prospect_finder_interval

    async def start(self) -> None:
        """Start the agent and initialize HTTP client."""
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        await super().start()

    async def stop(self) -> None:
        """Stop the agent and close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
        await super().stop()

    async def run(self) -> None:
        """Main agent loop - search for new prospects."""
        # Check if we should search
        now = datetime.now()

        # Reset daily count at midnight
        if self._last_search_time and self._last_search_time.date() != now.date():
            self._daily_count = 0

        # Check if we've hit daily target
        if self._daily_count >= self._daily_target:
            self.log(
                f"Daily target reached ({self._daily_count}/{self._daily_target}). "
                "Waiting until tomorrow."
            )
            await asyncio.sleep(3600)  # Check again in 1 hour
            return

        # Check if enough time has passed since last search
        if self._last_search_time:
            elapsed = (now - self._last_search_time).total_seconds()
            if elapsed < self._search_interval:
                await asyncio.sleep(60)  # Check again in 1 minute
                return

        # Time to search!
        self.status = AgentStatus.WORKING
        self.log(
            f"Starting prospect search. Current: {self._daily_count}/{self._daily_target}"
        )

        try:
            prospects = await self._find_prospects()
            self._last_search_time = datetime.now()

            if prospects:
                self._daily_count += len(prospects)
                self.log(
                    f"Found {len(prospects)} new prospects! "
                    f"Total today: {self._daily_count}/{self._daily_target}"
                )

                # Send to ResearchManager
                await self.send_message(
                    recipient_id="research_manager",
                    message_type=MessageType.NEW_PROSPECTS.value,
                    payload={
                        "prospects": prospects,
                        "count": len(prospects),
                        "search_date": datetime.now().isoformat(),
                    },
                    priority="normal",
                )
            else:
                self.log("No new prospects found in this search cycle.")

        except Exception as e:
            self.log(f"Error during prospect search: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE
        await asyncio.sleep(300)  # Wait 5 minutes before next iteration

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def _find_prospects(self) -> list[dict[str, Any]]:
        """
        Find new prospects through web search.

        Returns:
            List of prospect dictionaries
        """
        prospects: list[dict[str, Any]] = []
        remaining = self._daily_target - self._daily_count

        # Randomly select industry and region combinations
        for _ in range(min(3, remaining // 5 + 1)):  # Search 3 times max per cycle
            industry = random.choice(self._target_industries)
            region = random.choice(self._target_regions)

            self.log(f"Searching: {industry} in {region}")

            try:
                # Simulate search results (in production, use actual search API)
                search_results = await self._search_companies(industry, region)

                for result in search_results:
                    if len(prospects) >= remaining:
                        break

                    # Validate and enrich the prospect
                    prospect = await self._evaluate_prospect(result, industry, region)

                    if prospect and not await self._prospect_exists(prospect["url"]):
                        # Save to database
                        if self._db:
                            db_prospect = await self._db.create_prospect(
                                name=prospect["name"],
                                url=prospect["url"],
                                industry=prospect["industry"],
                                region=prospect["region"],
                                size=prospect.get("size"),
                                email=prospect.get("email"),
                                source="web_search",
                            )
                            prospect["id"] = db_prospect.id

                        prospects.append(prospect)
                        self.log(f"Added prospect: {prospect['name']}")

            except Exception as e:
                self.log(f"Error searching {industry}/{region}: {e}", level="WARNING")

            # Rate limiting
            await asyncio.sleep(2)

        return prospects

    async def _search_companies(
        self, industry: str, region: str
    ) -> list[dict[str, Any]]:
        """
        Search for companies matching criteria.

        In production, this would use Google Search API, Bing API, or similar.
        For now, returns simulated results for demonstration.

        Args:
            industry: Target industry
            region: Target region

        Returns:
            List of search results
        """
        # Simulated search results for demonstration
        # In production, implement actual search API integration
        sample_companies = [
            {
                "name": f"Müller {industry.title()} AG",
                "url": f"https://mueller-{industry}.ch",
                "snippet": f"Ihr Partner für {industry.title()} in {region}",
            },
            {
                "name": f"{region.title()} {industry.title()} GmbH",
                "url": f"https://{region.lower()}-{industry}.ch",
                "snippet": f"Professionelle {industry.title()}-Dienstleistungen",
            },
            {
                "name": f"Weber & Söhne {industry.title()}",
                "url": f"https://weber-{industry}.ch",
                "snippet": f"Tradition seit 1985 - {industry.title()} in der Schweiz",
            },
        ]

        # Add some randomization
        return random.sample(sample_companies, min(len(sample_companies), random.randint(1, 3)))

    async def _evaluate_prospect(
        self, result: dict[str, Any], industry: str, region: str
    ) -> Optional[dict[str, Any]]:
        """
        Evaluate if a search result is a valid prospect.

        Checks for signs of website issues and extracts basic info.

        Args:
            result: Search result to evaluate
            industry: Industry category
            region: Geographic region

        Returns:
            Prospect dict if valid, None otherwise
        """
        url = result.get("url", "")
        if not url:
            return None

        prospect: dict[str, Any] = {
            "name": result.get("name", self._extract_company_name(url)),
            "url": url,
            "industry": industry,
            "region": region,
            "size": "small",  # Default assumption for SME
            "website_signals": [],
        }

        # Try to analyze the website
        try:
            website_info = await self._analyze_website(url)
            if website_info:
                prospect.update(website_info)

                # Check for "bad website" signals
                if website_info.get("has_issues"):
                    prospect["website_signals"] = website_info.get("issues", [])
                    return prospect

        except Exception as e:
            self.log(f"Could not analyze {url}: {e}", level="DEBUG")
            # If we can't reach the site, that's also a signal
            prospect["website_signals"] = ["Seite nicht erreichbar oder sehr langsam"]
            return prospect

        return prospect

    async def _analyze_website(self, url: str) -> Optional[dict[str, Any]]:
        """
        Analyze a website for quality signals.

        Args:
            url: Website URL to analyze

        Returns:
            Analysis results dict
        """
        if not self._http_client:
            return None

        issues: list[str] = []
        info: dict[str, Any] = {"has_issues": False, "issues": []}

        try:
            # Request the page
            start_time = datetime.now()
            response = await self._http_client.get(url)
            load_time = (datetime.now() - start_time).total_seconds()

            # Check load time
            if load_time > 3:
                issues.append(f"Langsame Ladezeit ({load_time:.1f}s)")

            # Check for HTTPS
            if not url.startswith("https"):
                issues.append("Keine HTTPS-Verschlüsselung")

            # Parse HTML
            soup = BeautifulSoup(response.text, "lxml")

            # Check for viewport meta tag (mobile responsiveness)
            viewport = soup.find("meta", attrs={"name": "viewport"})
            if not viewport:
                issues.append("Nicht für mobile Geräte optimiert")

            # Check for old HTML patterns
            if soup.find("table", attrs={"width": True}):
                issues.append("Veraltetes Webdesign (Tabellen-Layout)")

            if soup.find("font"):
                issues.append("Veraltete HTML-Elemente")

            # Check for flash content
            if soup.find("object") or soup.find("embed"):
                issues.append("Flash oder veraltete Plugins")

            # Check for contact form
            forms = soup.find_all("form")
            has_contact_form = any(
                "contact" in str(f).lower() or "kontakt" in str(f).lower()
                for f in forms
            )
            if not has_contact_form:
                issues.append("Kein Kontaktformular gefunden")

            # Extract email if found
            email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
            emails = re.findall(email_pattern, response.text)
            if emails:
                # Filter out common generic emails
                valid_emails = [
                    e for e in emails
                    if not any(x in e.lower() for x in ["@example", "@test", "noreply"])
                ]
                if valid_emails:
                    info["email"] = valid_emails[0]

            # Check copyright year (old copyright = old site)
            copyright_pattern = r"©\s*(\d{4})|copyright\s*(\d{4})"
            copyright_matches = re.findall(copyright_pattern, response.text.lower())
            if copyright_matches:
                years = [int(y) for match in copyright_matches for y in match if y]
                if years and max(years) < 2022:
                    issues.append(f"Veralteter Copyright-Hinweis ({max(years)})")

            info["has_issues"] = len(issues) > 0
            info["issues"] = issues
            info["load_time"] = load_time

            return info

        except httpx.TimeoutException:
            return {"has_issues": True, "issues": ["Webseite antwortet nicht (Timeout)"]}
        except Exception as e:
            self.log(f"Website analysis error for {url}: {e}", level="DEBUG")
            return None

    def _extract_company_name(self, url: str) -> str:
        """Extract company name from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        name = domain.split(".")[0]
        return name.replace("-", " ").title()

    async def _prospect_exists(self, url: str) -> bool:
        """Check if prospect already exists in database."""
        if not self._db:
            return False
        return await self._db.prospect_exists(url)

    async def _find_email(self, url: str, company_name: str) -> Optional[str]:
        """
        Find email address for a company.

        Could integrate with Hunter.io or similar services.

        Args:
            url: Company website URL
            company_name: Company name

        Returns:
            Email address if found
        """
        # In production, implement Hunter.io API integration
        # For now, return None
        return None
