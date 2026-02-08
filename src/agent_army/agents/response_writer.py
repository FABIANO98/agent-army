"""ResponseWriter Agent - Writes responses to incoming emails."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import ResponseCategory
from ..templates.email_templates import EmailTemplateManager

if TYPE_CHECKING:
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


RESPONSE_WRITER_SYSTEM_PROMPT = """Du bist ein erfahrener B2B-Vertriebsexperte fuer Schweizer KMUs.
Du schreibst kontextuelle, personalisierte Antworten auf Emails.
Die Antworten sollen professionell, freundlich und zielgerichtet sein.
Passe den Ton an die erhaltene Nachricht an.
Antworte NUR mit validem JSON."""


class ResponseWriterAgent(BaseAgent):
    """
    Writes responses to incoming emails.

    Handles:
    - Positive responses (meeting proposals)
    - Questions (detailed answers)
    - Meeting confirmations
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        """Initialize ResponseWriter agent."""
        super().__init__(
            name="ResponseWriter",
            agent_type="response_writer",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._template_manager = EmailTemplateManager()
        self._pending_responses: list[dict[str, Any]] = []
        self._signature = ""
        self._calendar_link = ""

        if settings:
            self._signature = settings.email.signature

    async def run(self) -> None:
        """Main agent loop - process pending response requests."""
        # Check database for unprocessed responses
        if not self._pending_responses and self._db:
            unprocessed = await self._db.get_unprocessed_responses(limit=5)
            for response in unprocessed:
                email_obj = await self._db.get_email(response.email_id)
                if email_obj:
                    prospect = await self._db.get_prospect(email_obj.prospect_id)
                    self._pending_responses.append({
                        "response": response.to_dict(),
                        "category": response.category,
                        "original_email": email_obj.to_dict(),
                        "prospect": prospect.to_dict() if prospect else {},
                    })

        if not self._pending_responses:
            await asyncio.sleep(60)
            return

        self.status = AgentStatus.WORKING

        # Process one response at a time
        data = self._pending_responses.pop(0)
        response = data.get("response", {})
        category = data.get("category", "neutral")
        original_email = data.get("original_email", {})
        prospect = data.get("prospect", {})
        extracted_info = data.get("extracted_info", {})

        self.log(f"Writing reply for: {prospect.get('name', 'Unknown')} ({category})")

        try:
            reply = await self._write_reply(
                response, category, original_email, prospect, extracted_info
            )

            if reply:
                self.log(f"Reply drafted. Sending to @EmailSender")

                # Send to EmailSender
                await self.send_message(
                    recipient_id="email_sender",
                    message_type=MessageType.EMAIL_APPROVED.value,
                    payload={
                        "email_draft": reply,
                        "prospect": prospect,
                        "is_reply": True,
                        "text": "@EmailSender reply ready to send",
                    },
                    priority="high",
                )

                # Update response as replied
                if self._db and response.get("id"):
                    async with self._db.session() as session:
                        from sqlalchemy import select
                        from ..db.models import Response

                        result = await session.execute(
                            select(Response).where(Response.id == response["id"])
                        )
                        db_response = result.scalar_one_or_none()
                        if db_response:
                            db_response.replied_at = datetime.now()
                            db_response.needs_reply = False

        except Exception as e:
            self.log(f"Error writing reply: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE

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
                    "output_data": {"type": "response", "title": "Antwort verfasst"},
                },
            )

        elif message.message_type == MessageType.RESPONSE_RECEIVED.value:
            self._pending_responses.append(message.payload)
            category = message.payload.get("category", "unknown")
            self.log(
                f"Response queued for reply ({category}). "
                f"Queue size: {len(self._pending_responses)}"
            )

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def _write_reply(
        self,
        response: dict[str, Any],
        category: str,
        original_email: dict[str, Any],
        prospect: dict[str, Any],
        extracted_info: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Write an appropriate reply based on response category."""
        # Get profile for personalization
        profile = {}
        if self._db and prospect.get("id"):
            db_profile = await self._db.get_company_profile(prospect["id"])
            if db_profile:
                profile = db_profile.to_dict()

        # Try LLM-powered contextual reply
        if self._llm:
            llm_reply = await self._write_reply_with_llm(
                response, category, original_email, prospect, profile, extracted_info
            )
            if llm_reply:
                return llm_reply

        # Fallback to template-based replies
        ceo_name = profile.get("ceo_name", "")
        if ceo_name:
            ceo_last_name = ceo_name.split()[-1] if " " in ceo_name else ceo_name
            anrede = self._determine_anrede(ceo_name)
        else:
            ceo_last_name = ""
            anrede = ""

        # Generate reply based on category
        if category == ResponseCategory.POSITIVE.value:
            return self._write_positive_reply(
                response, original_email, prospect, profile, extracted_info
            )
        elif category == ResponseCategory.QUESTION.value:
            return self._write_question_reply(
                response, original_email, prospect, profile
            )
        elif category == ResponseCategory.NEUTRAL.value:
            return self._write_neutral_reply(
                response, original_email, prospect, profile
            )
        else:
            return None

    def _write_positive_reply(
        self,
        response: dict[str, Any],
        original_email: dict[str, Any],
        prospect: dict[str, Any],
        profile: dict[str, Any],
        extracted_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Write reply to positive response."""
        ceo_name = profile.get("ceo_name", "")
        ceo_last_name = ceo_name.split()[-1] if ceo_name and " " in ceo_name else ceo_name
        anrede = self._determine_anrede(ceo_name) if ceo_name else ""

        # Check if meeting was requested
        if extracted_info.get("meeting_requested"):
            subject = f"Re: {original_email.get('subject', 'Unser Gespräch')}"
            body = self._generate_meeting_proposal(
                anrede, ceo_last_name, prospect, extracted_info
            )
        else:
            subject = f"Re: {original_email.get('subject', '')}"
            body = self._generate_interest_response(
                anrede, ceo_last_name, prospect
            )

        return {
            "subject": subject,
            "body": body,
            "prospect_id": prospect.get("id"),
            "email_type": "response",
            "in_reply_to": original_email.get("message_id"),
            "created_at": datetime.now().isoformat(),
        }

    def _write_question_reply(
        self,
        response: dict[str, Any],
        original_email: dict[str, Any],
        prospect: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Write reply to question."""
        ceo_name = profile.get("ceo_name", "")
        ceo_last_name = ceo_name.split()[-1] if ceo_name and " " in ceo_name else ceo_name
        anrede = self._determine_anrede(ceo_name) if ceo_name else ""

        response_text = response.get("response_text", "")

        subject = f"Re: {original_email.get('subject', '')}"
        body = self._generate_question_response(
            anrede, ceo_last_name, prospect, response_text
        )

        return {
            "subject": subject,
            "body": body,
            "prospect_id": prospect.get("id"),
            "email_type": "response",
            "in_reply_to": original_email.get("message_id"),
            "created_at": datetime.now().isoformat(),
        }

    def _write_neutral_reply(
        self,
        response: dict[str, Any],
        original_email: dict[str, Any],
        prospect: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Write reply to neutral response."""
        ceo_name = profile.get("ceo_name", "")
        ceo_last_name = ceo_name.split()[-1] if ceo_name and " " in ceo_name else ceo_name
        anrede = self._determine_anrede(ceo_name) if ceo_name else ""

        subject = f"Re: {original_email.get('subject', '')}"
        body = f"""Guten Tag {anrede} {ceo_last_name},

vielen Dank für Ihre Rückmeldung.

Ich stehe Ihnen gerne zur Verfügung, falls Sie weitere Informationen benötigen oder ein kurzes Gespräch wünschen.

{self._signature}"""

        return {
            "subject": subject,
            "body": body,
            "prospect_id": prospect.get("id"),
            "email_type": "response",
            "in_reply_to": original_email.get("message_id"),
            "created_at": datetime.now().isoformat(),
        }

    async def _write_reply_with_llm(
        self,
        response: dict[str, Any],
        category: str,
        original_email: dict[str, Any],
        prospect: dict[str, Any],
        profile: dict[str, Any],
        extracted_info: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Write a contextual reply using Claude."""
        if not self._llm:
            return None

        try:
            time_slots = self._generate_time_slots()
            result = await self._llm.complete_structured(
                prompt=f"""Schreibe eine Antwort auf diese Email:

Kategorie: {category}
Empfaenger: {prospect.get('name', 'Unbekannt')}
CEO: {profile.get('ceo_name', 'unbekannt')}

Urspruengliche Email (Betreff): {original_email.get('subject', '')}

Erhaltene Antwort:
{response.get('response_text', response.get('body', ''))[:2000]}

Extrahierte Infos: Meeting gewuenscht={extracted_info.get('meeting_requested', False)}, Budget={extracted_info.get('budget', 'unbekannt')}

Verfuegbare Termine: {', '.join(time_slots[:3])}
Signatur: {self._signature}""",
                system=RESPONSE_WRITER_SYSTEM_PROMPT,
                response_schema={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["subject", "body"],
                },
                agent_id="response_writer",
            )

            if result and result.get("body"):
                return {
                    "subject": result.get("subject", f"Re: {original_email.get('subject', '')}"),
                    "body": result["body"],
                    "prospect_id": prospect.get("id"),
                    "email_type": "response",
                    "in_reply_to": original_email.get("message_id"),
                    "created_at": datetime.now().isoformat(),
                }
        except Exception as e:
            self.log(f"LLM reply writing failed: {e}", level="WARNING")

        return None

    def _generate_meeting_proposal(
        self,
        anrede: str,
        name: str,
        prospect: dict[str, Any],
        extracted_info: dict[str, Any],
    ) -> str:
        """Generate meeting proposal email."""
        # Generate time slots (next 3 weekdays at 10:00 and 14:00)
        time_slots = self._generate_time_slots()

        mentioned_times = extracted_info.get("mentioned_times", [])
        if mentioned_times:
            time_reference = f"\n\nSie haben {mentioned_times[0]} erwähnt - dieser Zeitpunkt passt mir gut."
        else:
            time_reference = ""

        return f"""Guten Tag {anrede} {name},

vielen Dank für Ihr Interesse! Das freut mich sehr.{time_reference}

Gerne schlage ich folgende Termine für ein kurzes Gespräch vor:

• {time_slots[0]}
• {time_slots[1]}
• {time_slots[2]}

Das Gespräch dauert ca. 15-20 Minuten. Ich zeige Ihnen konkret, welche Verbesserungen für {prospect.get('name', 'Ihre Webseite')} möglich wären.

Welcher Termin passt Ihnen am besten?

{self._signature}"""

    def _generate_interest_response(
        self, anrede: str, name: str, prospect: dict[str, Any]
    ) -> str:
        """Generate response to general interest."""
        time_slots = self._generate_time_slots()

        return f"""Guten Tag {anrede} {name},

vielen Dank für Ihre positive Rückmeldung!

Ich würde Ihnen gerne in einem kurzen Gespräch zeigen, welche konkreten Möglichkeiten es für {prospect.get('name', 'Ihr Unternehmen')} gibt.

Hätten Sie diese Woche Zeit für einen kurzen Austausch? Hier ein paar Vorschläge:

• {time_slots[0]}
• {time_slots[1]}

Alternativ können Sie mir auch gerne einen Termin vorschlagen, der Ihnen besser passt.

Ich freue mich auf unser Gespräch!

{self._signature}"""

    def _generate_question_response(
        self,
        anrede: str,
        name: str,
        prospect: dict[str, Any],
        question_text: str,
    ) -> str:
        """Generate response to a question."""
        # Analyze the question to generate appropriate answer
        question_lower = question_text.lower()

        if "preis" in question_lower or "kostet" in question_lower or "kosten" in question_lower:
            answer = """Zur Preisfrage: Das hängt natürlich vom Umfang ab. Für eine moderne, mobilfreundliche Unternehmenswebseite mit den wichtigsten Funktionen beginnen die Investitionen typischerweise bei CHF 3'000.-

Aber um Ihnen ein genaues Angebot machen zu können, würde ich gerne Ihre konkreten Anforderungen besser verstehen. Das geht am besten in einem kurzen Gespräch."""

        elif "zeit" in question_lower or "dauer" in question_lower or "lange" in question_lower:
            answer = """Zur Zeitfrage: Ein typisches Projekt für eine Unternehmenswebseite dauert etwa 4-6 Wochen, je nach Umfang und wie schnell Inhalte und Feedback kommen.

Für eine genauere Einschätzung würde ich gerne mehr über Ihre spezifischen Anforderungen erfahren."""

        elif "referenz" in question_lower or "beispiel" in question_lower:
            answer = """Gerne zeige ich Ihnen Beispiele meiner Arbeit in einem persönlichen Gespräch. So kann ich Ihnen auch Projekte zeigen, die zu Ihrer Branche passen.

Alternativ können Sie sich auch auf meiner Webseite www.frascati-systems.ch einen ersten Eindruck verschaffen."""

        else:
            answer = """Vielen Dank für Ihre Frage. Um sie bestmöglich zu beantworten, würde ich gerne kurz telefonieren - so kann ich auch auf Rückfragen direkt eingehen."""

        return f"""Guten Tag {anrede} {name},

vielen Dank für Ihre Nachricht und die gute Frage.

{answer}

Hätten Sie Zeit für ein kurzes Gespräch in den nächsten Tagen?

{self._signature}"""

    def _generate_time_slots(self) -> list[str]:
        """Generate available time slots for the next few days."""
        slots: list[str] = []
        now = datetime.now()

        days_added = 0
        current = now + timedelta(days=1)

        while len(slots) < 4 and days_added < 10:
            if current.weekday() < 5:  # Weekday
                day_name = [
                    "Montag", "Dienstag", "Mittwoch",
                    "Donnerstag", "Freitag"
                ][current.weekday()]
                date_str = current.strftime("%d.%m.")

                slots.append(f"{day_name}, {date_str} um 10:00 Uhr")
                if len(slots) < 4:
                    slots.append(f"{day_name}, {date_str} um 14:00 Uhr")

            current += timedelta(days=1)
            days_added += 1

        return slots[:3]

    def _determine_anrede(self, name: str) -> str:
        """Determine appropriate salutation."""
        if not name:
            return ""

        first_name = name.split()[0].lower()

        female_names = [
            "anna", "maria", "sandra", "claudia", "monika", "petra",
            "andrea", "christine", "nicole", "sabine", "daniela",
        ]
        male_names = [
            "peter", "hans", "thomas", "daniel", "martin", "andreas",
            "michael", "stefan", "markus", "beat", "bruno",
        ]

        if first_name in female_names:
            return "Frau"
        elif first_name in male_names:
            return "Herr"
        return "Herr/Frau"
