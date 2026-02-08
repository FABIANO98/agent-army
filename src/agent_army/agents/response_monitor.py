"""ResponseMonitor Agent - Monitors email responses."""

from __future__ import annotations

import asyncio
import email
import re
from datetime import datetime
from email.header import decode_header
from typing import TYPE_CHECKING, Any, Optional

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import ResponseCategory, ProspectStatus, DealStage

if TYPE_CHECKING:
    from aioimaplib import IMAP4_SSL
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


RESPONSE_MONITOR_SYSTEM_PROMPT = """Du bist ein Experte fuer die Analyse von Email-Antworten im B2B-Kontext.
Kategorisiere die Antwort und extrahiere relevante Informationen.
Kategorien: positive, negative, question, neutral, out_of_office
Antworte NUR mit validem JSON."""


class ResponseMonitorAgent(BaseAgent):
    """
    Monitors email responses.

    Features:
    - IMAP inbox monitoring
    - Response matching to original emails
    - Sentiment analysis
    - Response categorization
    - Alert on positive responses
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        """Initialize ResponseMonitor agent."""
        super().__init__(
            name="ResponseMonitor",
            agent_type="response_monitor",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._last_check: Optional[datetime] = None

        # IMAP configuration
        self._imap_host = "imap.gmail.com"
        self._imap_port = 993
        self._imap_username = ""
        self._imap_password = ""
        self._check_interval = 1800  # 30 minutes

        if settings:
            self._imap_host = settings.email.imap_host
            self._imap_port = settings.email.imap_port
            self._imap_username = settings.email.imap_username
            self._imap_password = settings.email.imap_password
            self._check_interval = settings.agents.response_monitor_interval

    async def run(self) -> None:
        """Main agent loop - check for new responses."""
        now = datetime.now()

        # Check if enough time has passed since last check
        if self._last_check:
            elapsed = (now - self._last_check).total_seconds()
            if elapsed < self._check_interval:
                await asyncio.sleep(60)
                return

        self.status = AgentStatus.WORKING
        self.log("Checking inbox for responses...")

        try:
            responses = await self._check_inbox()
            self._last_check = datetime.now()

            if responses:
                self.log(f"Found {len(responses)} new responses!")

                for response in responses:
                    await self._process_response(response)
            else:
                self.log("No new responses")

        except Exception as e:
            self.log(f"Error checking inbox: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE
        await asyncio.sleep(60)

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK_ASSIGNED.value:
            task_id = message.payload.get("task_id")
            subtask_id = message.payload.get("subtask_id")
            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_SUBTASK_COMPLETE.value,
                payload={
                    "task_id": task_id, "subtask_id": subtask_id,
                    "output_data": {"type": "monitor", "title": "Inbox geprueft"},
                },
            )

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def _check_inbox(self) -> list[dict[str, Any]]:
        """
        Check IMAP inbox for new responses.

        Returns:
            List of response dicts
        """
        responses: list[dict[str, Any]] = []

        # Check if IMAP is configured
        if not self._imap_username or not self._imap_password:
            self.log("IMAP not configured - simulating inbox check", level="WARNING")
            return await self._simulate_inbox_check()

        try:
            import aioimaplib

            imap = aioimaplib.IMAP4_SSL(
                host=self._imap_host,
                port=self._imap_port,
            )
            await imap.wait_hello_from_server()
            await imap.login(self._imap_username, self._imap_password)
            await imap.select("INBOX")

            # Search for unread messages
            _, message_numbers = await imap.search("UNSEEN")

            if message_numbers and message_numbers[0]:
                msg_ids = message_numbers[0].split()

                for msg_id in msg_ids[-10:]:  # Process last 10 max
                    _, msg_data = await imap.fetch(msg_id.decode(), "(RFC822)")

                    if msg_data and len(msg_data) >= 2:
                        raw_email = msg_data[1]
                        parsed = self._parse_email(raw_email)
                        if parsed:
                            responses.append(parsed)

            await imap.logout()

        except ImportError:
            self.log("aioimaplib not installed", level="WARNING")
        except Exception as e:
            self.log(f"IMAP error: {e}", level="ERROR")

        return responses

    async def _simulate_inbox_check(self) -> list[dict[str, Any]]:
        """Simulate inbox check for testing."""
        # In a real scenario, this would return actual emails
        # For testing, we can return mock responses occasionally
        import random

        if random.random() < 0.1:  # 10% chance of simulated response
            return [{
                "subject": "Re: Kurze Frage zu Test AG",
                "from_email": "ceo@test-ag.ch",
                "from_name": "Hans Muster",
                "body": "Guten Tag, vielen Dank für Ihre Nachricht. "
                        "Das Thema interessiert uns. Können wir nächste Woche telefonieren?",
                "received_at": datetime.now(),
                "message_id": f"simulated_{datetime.now().timestamp()}",
            }]
        return []

    def _parse_email(self, raw_email: bytes) -> Optional[dict[str, Any]]:
        """Parse raw email into structured dict."""
        try:
            msg = email.message_from_bytes(raw_email)

            # Decode subject
            subject_header = msg.get("Subject", "")
            subject_parts = decode_header(subject_header)
            subject = "".join(
                part.decode(charset or "utf-8") if isinstance(part, bytes) else part
                for part, charset in subject_parts
            )

            # Parse from address
            from_header = msg.get("From", "")
            from_match = re.search(r"([^<]*)<([^>]+)>", from_header)
            if from_match:
                from_name = from_match.group(1).strip().strip('"')
                from_email = from_match.group(2)
            else:
                from_name = ""
                from_email = from_header

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")

            # Get date
            date_header = msg.get("Date", "")
            # Parse date (simplified)
            received_at = datetime.now()

            return {
                "subject": subject,
                "from_email": from_email,
                "from_name": from_name,
                "body": body,
                "received_at": received_at,
                "message_id": msg.get("Message-ID", ""),
                "in_reply_to": msg.get("In-Reply-To", ""),
                "references": msg.get("References", ""),
            }

        except Exception as e:
            self.log(f"Email parsing error: {e}", level="WARNING")
            return None

    async def _process_response(self, response: dict[str, Any]) -> None:
        """Process and categorize a response."""
        # Try to match to original email
        original_email = await self._match_to_original(response)

        if not original_email:
            self.log(
                f"Could not match response from {response.get('from_email')} to any sent email",
                level="DEBUG",
            )
            return

        # Use LLM for nuanced categorization if available
        if self._llm:
            llm_analysis = await self._analyze_response_with_llm(response)
            if llm_analysis:
                cat_str = llm_analysis.get("category", "neutral")
                try:
                    category = ResponseCategory(cat_str)
                except ValueError:
                    category = ResponseCategory.NEUTRAL
                sentiment = llm_analysis.get("sentiment", "neutral")
                extracted = llm_analysis.get("extracted_info", {})
            else:
                category = self._categorize_response(response)
                sentiment = self._analyze_sentiment(response["body"])
                extracted = self._extract_info(response["body"])
        else:
            # Fallback to heuristic categorization
            category = self._categorize_response(response)
            sentiment = self._analyze_sentiment(response["body"])
            extracted = self._extract_info(response["body"])

        self.log(
            f"Response from {response.get('from_name', response.get('from_email'))}: "
            f"Category={category.value}, Sentiment={sentiment}"
        )

        # Save to database
        if self._db:
            db_response = await self._db.create_response(
                email_id=original_email["id"],
                response_text=response["body"],
                subject=response.get("subject"),
                sentiment=sentiment,
                category=category.value,
                extracted_info=extracted,
                meeting_requested=extracted.get("meeting_requested", False),
                budget_mentioned=extracted.get("budget"),
            )

            # Update prospect status
            if original_email.get("prospect_id"):
                new_status = {
                    ResponseCategory.POSITIVE: ProspectStatus.RESPONDED,
                    ResponseCategory.NEGATIVE: ProspectStatus.UNSUBSCRIBED,
                    ResponseCategory.QUESTION: ProspectStatus.RESPONDED,
                    ResponseCategory.NEUTRAL: ProspectStatus.RESPONDED,
                    ResponseCategory.OUT_OF_OFFICE: ProspectStatus.CONTACTED,
                }.get(category, ProspectStatus.RESPONDED)

                await self._db.update_prospect_status(
                    original_email["prospect_id"], new_status
                )

                # Update deal stage
                deal = await self._db.get_deal_by_prospect(original_email["prospect_id"])
                if deal and category in [ResponseCategory.POSITIVE, ResponseCategory.QUESTION]:
                    new_stage = DealStage.RESPONDED
                    if extracted.get("meeting_requested"):
                        new_stage = DealStage.MEETING_SCHEDULED
                    await self._db.update_deal_stage(deal.id, new_stage)

        # Send notifications based on category
        if category == ResponseCategory.POSITIVE:
            self.log(
                f"Positive response! @ResponseWriter please draft a reply",
                level="INFO",
            )
            await self.send_message(
                recipient_id="response_writer",
                message_type=MessageType.RESPONSE_RECEIVED.value,
                payload={
                    "response": response,
                    "category": category.value,
                    "original_email": original_email,
                    "extracted_info": extracted,
                    "text": "@ResponseWriter positive response - please draft reply",
                },
                priority="high",
            )

            # Also alert DealTracker
            await self.send_message(
                recipient_id="deal_tracker",
                message_type=MessageType.DEAL_ALERT.value,
                payload={
                    "alert_type": "positive_response",
                    "response": response,
                    "prospect_id": original_email.get("prospect_id"),
                },
                priority="high",
            )

        elif category == ResponseCategory.QUESTION:
            await self.send_message(
                recipient_id="response_writer",
                message_type=MessageType.RESPONSE_RECEIVED.value,
                payload={
                    "response": response,
                    "category": category.value,
                    "original_email": original_email,
                    "extracted_info": extracted,
                    "text": "@ResponseWriter question received - please answer",
                },
                priority="normal",
            )

        elif category == ResponseCategory.NEGATIVE:
            self.log(f"Negative response - no follow-up needed")
            await self.send_message(
                recipient_id="deal_tracker",
                message_type=MessageType.DEAL_STAGE_UPDATE.value,
                payload={
                    "prospect_id": original_email.get("prospect_id"),
                    "new_stage": "lost",
                    "reason": "Negative response",
                },
                priority="low",
            )

    async def _match_to_original(
        self, response: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Match response to original sent email."""
        if not self._db:
            return None

        from_email = response.get("from_email", "").lower()
        subject = response.get("subject", "")

        # Check In-Reply-To header
        in_reply_to = response.get("in_reply_to", "")
        if in_reply_to:
            # Would match against message_id in database
            pass

        # Match by email address - find any sent email to this address
        # This is simplified - production would use better matching
        async with self._db.session() as session:
            from sqlalchemy import select
            from ..db.models import Email, Prospect

            result = await session.execute(
                select(Email, Prospect)
                .join(Prospect, Email.prospect_id == Prospect.id)
                .where(Prospect.email == from_email)
                .order_by(Email.sent_at.desc())
                .limit(1)
            )
            row = result.first()
            if row:
                email_obj, prospect = row
                return {
                    "id": email_obj.id,
                    "prospect_id": prospect.id,
                    "subject": email_obj.subject,
                }

        return None

    def _categorize_response(self, response: dict[str, Any]) -> ResponseCategory:
        """Categorize the response type."""
        body = response.get("body", "").lower()
        subject = response.get("subject", "").lower()

        # Out of Office
        ooo_indicators = [
            "out of office",
            "abwesend",
            "nicht im büro",
            "urlaub",
            "ferien",
            "automatische antwort",
            "auto-reply",
        ]
        if any(indicator in body or indicator in subject for indicator in ooo_indicators):
            return ResponseCategory.OUT_OF_OFFICE

        # Negative
        negative_indicators = [
            "kein interesse",
            "nicht interessiert",
            "abmelden",
            "unsubscribe",
            "bitte keine",
            "nicht mehr kontaktieren",
            "entfernen sie",
        ]
        if any(indicator in body for indicator in negative_indicators):
            return ResponseCategory.NEGATIVE

        # Positive
        positive_indicators = [
            "interesse",
            "interessiert",
            "gerne",
            "termin",
            "meeting",
            "gespräch",
            "angebot",
            "mehr erfahren",
            "rufen sie",
            "ja",
            "klingt gut",
            "telefonieren",
        ]
        positive_count = sum(1 for ind in positive_indicators if ind in body)
        if positive_count >= 2:
            return ResponseCategory.POSITIVE

        # Question
        question_indicators = [
            "?",
            "frage",
            "wie",
            "was kostet",
            "preis",
            "können sie",
            "mehr informationen",
        ]
        if any(indicator in body for indicator in question_indicators):
            return ResponseCategory.QUESTION

        return ResponseCategory.NEUTRAL

    def _analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis."""
        text_lower = text.lower()

        positive_words = [
            "danke", "gut", "super", "toll", "interessant", "freue",
            "gerne", "ja", "positiv", "perfekt",
        ]
        negative_words = [
            "nein", "leider", "nicht", "kein", "absagen", "schlecht",
            "unpassend", "störend",
        ]

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        return "neutral"

    async def _analyze_response_with_llm(
        self, response: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Use Claude for nuanced response categorization and sentiment analysis."""
        if not self._llm:
            return None

        try:
            return await self._llm.complete_structured(
                prompt=f"""Analysiere diese Email-Antwort auf eine B2B-Kaltakquise:

Betreff: {response.get('subject', '')}
Von: {response.get('from_name', '')} <{response.get('from_email', '')}>

Text:
{response.get('body', '')[:3000]}""",
                system=RESPONSE_MONITOR_SYSTEM_PROMPT,
                response_schema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": ["positive", "negative", "question", "neutral", "out_of_office"]},
                        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                        "confidence": {"type": "number"},
                        "summary": {"type": "string"},
                        "extracted_info": {
                            "type": "object",
                            "properties": {
                                "meeting_requested": {"type": "boolean"},
                                "budget": {"type": "string"},
                                "phone": {"type": "string"},
                                "mentioned_times": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "required": ["category", "sentiment"],
                },
                agent_id="response_monitor",
            )
        except Exception as e:
            self.log(f"LLM response analysis failed: {e}", level="WARNING")
            return None

    def _extract_info(self, text: str) -> dict[str, Any]:
        """Extract key information from response."""
        info: dict[str, Any] = {}
        text_lower = text.lower()

        # Check for meeting request
        meeting_words = ["termin", "meeting", "gespräch", "telefonat", "call"]
        info["meeting_requested"] = any(word in text_lower for word in meeting_words)

        # Extract potential dates/times
        time_patterns = [
            r"(\d{1,2}[.:]\d{2})",  # 10:00 or 10.00
            r"(montag|dienstag|mittwoch|donnerstag|freitag)",
            r"(\d{1,2}\.\s*\w+)",  # 15. Januar
        ]
        for pattern in time_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                info["mentioned_times"] = matches

        # Extract budget mentions
        budget_pattern = r"(\d+[\'.]?\d*)\s*(chf|franken|sfr|€|euro)"
        budget_match = re.search(budget_pattern, text_lower)
        if budget_match:
            info["budget"] = budget_match.group(0)

        # Extract phone numbers
        phone_pattern = r"\+?[\d\s]{10,}"
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            info["phone"] = phone_match.group(0).strip()

        return info
