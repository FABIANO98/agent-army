"""ResearchManager Agent - Deep research on prospects."""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import httpx
from bs4 import BeautifulSoup

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import ProspectStatus

if TYPE_CHECKING:
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..scrapers.browser_manager import BrowserManager
    from ..scrapers.website_analyzer import WebsiteAnalyzer
    from ..utils.config import Settings


RESEARCH_SYSTEM_PROMPT = """Du bist ein erfahrener Business-Researcher fuer Schweizer KMUs.
Analysiere die gegebene Webseite und extrahiere strukturierte Informationen.
Antworte NUR mit validem JSON."""


class ResearchManagerAgent(BaseAgent):
    """
    Performs deep research on prospects.

    Gathers detailed information about companies including:
    - CEO/decision maker names
    - Website analysis
    - Social media presence
    - Budget estimates
    - Buying signals
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
        browser_manager: Optional[BrowserManager] = None,
        website_analyzer: Optional[WebsiteAnalyzer] = None,
    ) -> None:
        """Initialize ResearchManager agent."""
        super().__init__(
            name="ResearchManager",
            agent_type="research_manager",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._browser = browser_manager
        self._analyzer = website_analyzer
        self._http_client: Optional[httpx.AsyncClient] = None
        self._pending_prospects: list[dict[str, Any]] = []
        self._max_per_batch = 5

        if settings:
            self._max_per_batch = settings.agents.max_research_per_batch

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
        """Main agent loop - process pending prospects."""
        # Check for new prospects from database if queue is empty
        if not self._pending_prospects and self._db:
            prospects = await self._db.get_new_prospects(limit=self._max_per_batch)
            for p in prospects:
                self._pending_prospects.append(p.to_dict())

        if not self._pending_prospects:
            await asyncio.sleep(60)  # Wait if no work
            return

        self.status = AgentStatus.WORKING

        # Process a batch of prospects
        batch = self._pending_prospects[: self._max_per_batch]
        self._pending_prospects = self._pending_prospects[self._max_per_batch:]

        researched_profiles: list[dict[str, Any]] = []

        for prospect in batch:
            self.log(f"Researching: {prospect.get('name', 'Unknown')}")

            try:
                profile = await self._research_prospect(prospect)
                if profile:
                    # Save to database
                    if self._db and prospect.get("id"):
                        await self._db.create_company_profile(
                            prospect_id=prospect["id"],
                            ceo_name=profile.get("ceo_name"),
                            ceo_email=profile.get("ceo_email"),
                            employees_count=profile.get("employees_count"),
                            website_problems=profile.get("website_problems"),
                            website_tech_stack=profile.get("tech_stack"),
                            social_media=profile.get("social_media"),
                            budget_estimate=profile.get("budget_estimate"),
                            buying_signals=profile.get("buying_signals"),
                            sentiment_score=profile.get("sentiment_score"),
                            pain_points=profile.get("pain_points"),
                            research_data=profile,
                        )
                        await self._db.update_prospect_status(
                            prospect["id"], ProspectStatus.RESEARCHED
                        )

                    profile["prospect"] = prospect
                    researched_profiles.append(profile)
                    self.log(
                        f"Research complete: {prospect.get('name')} "
                        f"(Score: {profile.get('sentiment_score', 'N/A')})"
                    )

            except Exception as e:
                self.log(
                    f"Research failed for {prospect.get('name')}: {e}",
                    level="WARNING",
                )

            # Rate limiting
            await asyncio.sleep(2)

        # Send top profiles to EmailWriter
        if researched_profiles:
            # Sort by sentiment score and take top 5
            sorted_profiles = sorted(
                researched_profiles,
                key=lambda x: x.get("sentiment_score", 0),
                reverse=True,
            )
            top_profiles = sorted_profiles[:5]

            self.log(
                f"Sending {len(top_profiles)} hot leads to EmailWriter. "
                f"@EmailWriter please draft emails!"
            )

            await self.send_message(
                recipient_id="email_writer",
                message_type=MessageType.PROSPECT_RESEARCH_COMPLETE.value,
                payload={
                    "profiles": top_profiles,
                    "count": len(top_profiles),
                    "text": f"@EmailWriter {len(top_profiles)} new profiles ready for outreach",
                },
                priority="normal",
            )

        self.status = AgentStatus.IDLE

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK_ASSIGNED.value:
            await self._execute_subtask(message.payload)

        elif message.message_type == MessageType.NEW_PROSPECTS.value:
            # Add new prospects to queue
            prospects = message.payload.get("prospects", [])
            self._pending_prospects.extend(prospects)
            self.log(
                f"Received {len(prospects)} new prospects from ProspectFinder. "
                f"Queue size: {len(self._pending_prospects)}"
            )

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def _execute_subtask(self, payload: dict[str, Any]) -> None:
        """Execute a subtask assigned by TaskManager."""
        task_id = payload.get("task_id")
        subtask_id = payload.get("subtask_id")
        self.log(f"Executing subtask #{subtask_id} for task #{task_id}")

        try:
            # Get prospects from input_data (passed from ProspectFinder via TaskManager)
            input_data = payload.get("input_data", {})
            prospects = input_data.get("prospects", [])

            # Also check internal queue as fallback
            if not prospects and self._pending_prospects:
                prospects = self._pending_prospects[:self._max_per_batch]
                self._pending_prospects = self._pending_prospects[self._max_per_batch:]

            self.log(f"Researching {len(prospects)} prospects for subtask #{subtask_id}")

            results = []
            for p in prospects[:self._max_per_batch]:
                profile = await self._research_prospect(p)
                if profile:
                    results.append(profile)

            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_SUBTASK_COMPLETE.value,
                payload={
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "output_data": {
                        "type": "research",
                        "title": f"{len(results)} Profile recherchiert",
                        "profiles": results,
                        "count": len(results),
                    },
                },
            )
        except Exception as e:
            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_FAILED.value,
                payload={"task_id": task_id, "subtask_id": subtask_id, "error": str(e)},
            )

    async def _research_prospect(self, prospect: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Perform deep research on a prospect.

        Args:
            prospect: Prospect information

        Returns:
            Research profile dict
        """
        url = prospect.get("url", "")
        if not url:
            return None

        profile: dict[str, Any] = {
            "prospect_id": prospect.get("id"),
            "researched_at": datetime.now().isoformat(),
        }

        try:
            # Scrape main page
            main_page = await self._fetch_page(url)
            if main_page:
                profile.update(self._analyze_main_page(main_page, url))

            # Try to find and scrape About page
            about_page = await self._fetch_page(f"{url}/ueber-uns") or \
                         await self._fetch_page(f"{url}/about") or \
                         await self._fetch_page(f"{url}/firma")
            if about_page:
                profile.update(self._analyze_about_page(about_page))

            # Try contact page
            contact_page = await self._fetch_page(f"{url}/kontakt") or \
                           await self._fetch_page(f"{url}/contact")
            if contact_page:
                profile.update(self._analyze_contact_page(contact_page))

            # Search for social media
            profile["social_media"] = await self._find_social_media(url, main_page)

            # Analyze website problems
            profile["website_problems"] = self._identify_website_problems(
                main_page, prospect.get("website_signals", [])
            )

            # If LLM available, do a Claude-enhanced analysis
            all_content = (main_page or "") + (about_page or "") + (contact_page or "")
            if self._llm and all_content:
                llm_profile = await self._research_with_llm(url, all_content, prospect)
                if llm_profile:
                    # Merge LLM results (LLM overrides heuristic where present)
                    for key in ["ceo_name", "ceo_email", "employees_count",
                                "founding_year", "buying_signals", "pain_points",
                                "budget_estimate", "sentiment_score"]:
                        if llm_profile.get(key):
                            profile[key] = llm_profile[key]
                    # Append LLM-found problems
                    if llm_profile.get("website_problems"):
                        existing = set(profile.get("website_problems", []))
                        for p in llm_profile["website_problems"]:
                            if p not in existing:
                                profile.setdefault("website_problems", []).append(p)
                    return profile

            # Fallback to heuristic analysis
            profile["buying_signals"] = self._identify_buying_signals(all_content)
            profile["budget_estimate"] = self._estimate_budget(profile, all_content)
            profile["sentiment_score"] = self._calculate_sentiment_score(profile)
            profile["pain_points"] = self._identify_pain_points(
                profile.get("website_problems", []),
                prospect.get("industry", ""),
            )

            return profile

        except Exception as e:
            self.log(f"Research error for {url}: {e}", level="WARNING")
            return None

    async def _research_with_llm(
        self, url: str, content: str, prospect: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Use Claude to perform deep research analysis."""
        if not self._llm:
            return None

        content_truncated = content[:8000]
        try:
            return await self._llm.complete_structured(
                prompt=f"""Analysiere diese Webseite eines Schweizer KMU:
URL: {url}
Branche: {prospect.get('industry', 'unbekannt')}
Region: {prospect.get('region', 'Schweiz')}

Website-Inhalt:
{content_truncated}""",
                system=RESEARCH_SYSTEM_PROMPT,
                response_schema={
                    "type": "object",
                    "properties": {
                        "ceo_name": {"type": "string"},
                        "ceo_email": {"type": "string"},
                        "employees_count": {"type": "integer"},
                        "founding_year": {"type": "integer"},
                        "website_problems": {"type": "array", "items": {"type": "string"}},
                        "buying_signals": {"type": "array", "items": {"type": "string"}},
                        "pain_points": {"type": "array", "items": {"type": "string"}},
                        "budget_estimate": {"type": "string"},
                        "sentiment_score": {"type": "number"},
                    },
                },
                agent_id="research_manager",
            )
        except Exception as e:
            self.log(f"LLM research failed: {e}", level="WARNING")
            return None

    async def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a webpage - tries Playwright first, then httpx."""
        # Try browser manager for JS-heavy pages
        if self._browser and self._browser.is_available:
            content = await self._browser.get_page_content(url)
            if content:
                return content

        # Fallback to httpx
        if not self._http_client:
            return None

        try:
            response = await self._http_client.get(url)
            if response.status_code == 200:
                return response.text
        except Exception:
            pass

        return None

    def _analyze_main_page(self, html: str, url: str) -> dict[str, Any]:
        """Analyze the main page for company information."""
        soup = BeautifulSoup(html, "lxml")
        result: dict[str, Any] = {}

        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            result["page_title"] = title_tag.get_text(strip=True)

        # Look for meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result["meta_description"] = meta_desc.get("content", "")

        # Analyze tech stack
        result["tech_stack"] = self._detect_tech_stack(html, soup)

        return result

    def _analyze_about_page(self, html: str) -> dict[str, Any]:
        """Analyze the about page for CEO/team info."""
        soup = BeautifulSoup(html, "lxml")
        result: dict[str, Any] = {}

        text = soup.get_text()

        # Look for CEO/Geschäftsführer
        ceo_patterns = [
            r"Geschäftsführer[:\s]+([A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+)",
            r"CEO[:\s]+([A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+)",
            r"Inhaber[:\s]+([A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+)",
            r"Gründer[:\s]+([A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+)",
        ]

        for pattern in ceo_patterns:
            match = re.search(pattern, text)
            if match:
                result["ceo_name"] = match.group(1).strip()
                break

        # Look for employee count
        employee_patterns = [
            r"(\d+)\s*Mitarbeiter",
            r"Team\s+von\s+(\d+)",
            r"(\d+)\s*Angestellte",
        ]

        for pattern in employee_patterns:
            match = re.search(pattern, text)
            if match:
                result["employees_count"] = int(match.group(1))
                break

        # Look for founding year
        year_pattern = r"(?:gegründet|seit)\s*(\d{4})"
        year_match = re.search(year_pattern, text.lower())
        if year_match:
            result["founding_year"] = int(year_match.group(1))

        return result

    def _analyze_contact_page(self, html: str) -> dict[str, Any]:
        """Analyze contact page for email and contact info."""
        soup = BeautifulSoup(html, "lxml")
        result: dict[str, Any] = {}

        text = soup.get_text()

        # Extract emails
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, text)
        valid_emails = [
            e for e in emails
            if not any(x in e.lower() for x in ["@example", "@test", "noreply", "no-reply"])
        ]
        if valid_emails:
            result["contact_email"] = valid_emails[0]
            # Check if it looks like a personal email (could be CEO)
            if any(name in valid_emails[0].lower() for name in ["info", "kontakt"]):
                pass  # Generic email
            else:
                result["ceo_email"] = valid_emails[0]

        # Extract phone
        phone_pattern = r"\+41[\s\d]{9,}"
        phones = re.findall(phone_pattern, text)
        if phones:
            result["phone"] = phones[0].strip()

        return result

    def _detect_tech_stack(self, html: str, soup: BeautifulSoup) -> list[str]:
        """Detect technologies used on the website."""
        tech: list[str] = []

        # Check for common frameworks/CMS
        if "wp-content" in html or "wordpress" in html.lower():
            tech.append("WordPress")
        if "joomla" in html.lower():
            tech.append("Joomla")
        if "drupal" in html.lower():
            tech.append("Drupal")
        if "wix.com" in html:
            tech.append("Wix")
        if "squarespace" in html.lower():
            tech.append("Squarespace")

        # Check for JS frameworks
        if "react" in html.lower() or "reactjs" in html.lower():
            tech.append("React")
        if "vue" in html.lower() or "vuejs" in html.lower():
            tech.append("Vue.js")
        if "angular" in html.lower():
            tech.append("Angular")

        # Check for jQuery (often indicates older sites)
        if "jquery" in html.lower():
            tech.append("jQuery")

        # Check for Bootstrap
        if "bootstrap" in html.lower():
            tech.append("Bootstrap")

        return tech

    async def _find_social_media(
        self, url: str, html: Optional[str]
    ) -> dict[str, str]:
        """Find social media links."""
        social: dict[str, str] = {}

        if not html:
            return social

        soup = BeautifulSoup(html, "lxml")

        # Look for social media links
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if "linkedin.com" in href:
                social["linkedin"] = link["href"]
            elif "facebook.com" in href:
                social["facebook"] = link["href"]
            elif "instagram.com" in href:
                social["instagram"] = link["href"]
            elif "twitter.com" in href or "x.com" in href:
                social["twitter"] = link["href"]

        return social

    def _identify_website_problems(
        self, html: Optional[str], existing_signals: list[str]
    ) -> list[str]:
        """Identify specific website problems."""
        problems = list(existing_signals)

        if not html:
            return problems

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text()

        # Check for old copyright
        copyright_pattern = r"©\s*(\d{4})|copyright\s*(\d{4})"
        matches = re.findall(copyright_pattern, text.lower())
        if matches:
            years = [int(y) for match in matches for y in match if y]
            if years and max(years) < 2023:
                problems.append(f"Veralteter Copyright ({max(years)})")

        # Check viewport
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport and "Nicht für mobile Geräte optimiert" not in problems:
            problems.append("Nicht für mobile Geräte optimiert")

        # Check for tables layout
        tables = soup.find_all("table", attrs={"width": True})
        if tables and "Veraltetes Webdesign" not in str(problems):
            problems.append("Veraltetes Tabellen-Layout")

        # Check for missing images
        broken_images = soup.find_all("img", src=lambda x: not x)
        if broken_images:
            problems.append("Fehlende/kaputte Bilder")

        # Check for inline styles (indicates poor code quality)
        inline_styles = soup.find_all(style=True)
        if len(inline_styles) > 10:
            problems.append("Unstrukturierter Code (viele Inline-Styles)")

        return list(set(problems))  # Remove duplicates

    def _identify_buying_signals(self, content: str) -> list[str]:
        """Identify buying signals in the content."""
        signals: list[str] = []
        content_lower = content.lower()

        # Look for growth indicators
        growth_keywords = [
            ("wir suchen", "Stellenanzeigen gefunden"),
            ("karriere", "Karriereseite vorhanden"),
            ("jobs", "Stellenangebote"),
            ("wir wachsen", "Wachstum erwähnt"),
            ("expansion", "Expansion geplant"),
            ("neue standorte", "Expansion geplant"),
            ("neueröffnung", "Neueröffnung"),
        ]

        for keyword, signal in growth_keywords:
            if keyword in content_lower:
                signals.append(signal)

        # Look for digitalization mentions
        digital_keywords = [
            ("digitalisierung", "Interesse an Digitalisierung"),
            ("online präsenz", "Online-Präsenz als Thema"),
            ("modernisierung", "Modernisierung gewünscht"),
        ]

        for keyword, signal in digital_keywords:
            if keyword in content_lower:
                signals.append(signal)

        return list(set(signals))

    def _estimate_budget(self, profile: dict[str, Any], content: str) -> str:
        """Estimate budget based on company indicators."""
        employees = profile.get("employees_count", 0)

        if employees > 50:
            return "high"  # > 20k CHF
        elif employees > 20:
            return "medium"  # 10-20k CHF
        elif employees > 5:
            return "standard"  # 5-10k CHF
        else:
            return "small"  # < 5k CHF

    def _calculate_sentiment_score(self, profile: dict[str, Any]) -> float:
        """
        Calculate how "hot" a lead is (1-10).

        Higher score = more likely to convert.
        """
        score = 5.0  # Base score

        # Positive factors
        if profile.get("ceo_name"):
            score += 1.0  # We can personalize

        if profile.get("ceo_email"):
            score += 0.5  # Direct contact

        website_problems = profile.get("website_problems", [])
        if len(website_problems) >= 3:
            score += 1.5  # Clear need
        elif len(website_problems) >= 1:
            score += 0.5

        buying_signals = profile.get("buying_signals", [])
        if buying_signals:
            score += len(buying_signals) * 0.5  # Up to 2 points

        if profile.get("budget_estimate") in ["high", "medium"]:
            score += 1.0

        # Negative factors
        tech_stack = profile.get("tech_stack", [])
        if "React" in tech_stack or "Vue.js" in tech_stack:
            score -= 1.0  # Modern site, less need

        if "Wix" in tech_stack or "Squarespace" in tech_stack:
            score -= 0.5  # Already using site builder

        return min(10.0, max(1.0, score))

    def _identify_pain_points(
        self, website_problems: list[str], industry: str
    ) -> list[str]:
        """Identify specific pain points to mention in outreach."""
        pain_points: list[str] = []

        # Map problems to pain points
        problem_to_pain = {
            "mobile": "Kunden können Ihre Seite auf dem Handy nicht richtig nutzen",
            "langsam": "Potenzielle Kunden verlassen Ihre Seite bevor sie lädt",
            "veraltet": "Ihr professionelles Image leidet unter dem veralteten Design",
            "ssl": "Browser zeigen Sicherheitswarnungen - das schreckt Kunden ab",
            "kontakt": "Kunden können Sie nicht einfach kontaktieren",
        }

        for problem in website_problems:
            for key, pain in problem_to_pain.items():
                if key in problem.lower() and pain not in pain_points:
                    pain_points.append(pain)

        # Add industry-specific pain points
        industry_pains = {
            "bau": "Referenzprojekte können nicht ansprechend präsentiert werden",
            "transport": "Kunden können keine Anfragen online stellen",
            "logistik": "Ihre Services sind online nicht klar kommuniziert",
            "handwerk": "Ihre hochwertige Arbeit kommt online nicht zur Geltung",
        }

        if industry.lower() in industry_pains:
            pain_points.append(industry_pains[industry.lower()])

        return pain_points[:3]  # Max 3 pain points
