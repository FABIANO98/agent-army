"""EmailWriter Agent - Writes personalized cold emails."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import EmailStatus
from ..templates.email_templates import EmailTemplateManager

if TYPE_CHECKING:
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


EMAIL_WRITER_SYSTEM_PROMPT = """Du bist ein erfahrener B2B Email-Copywriter fuer Schweizer KMUs.
Du schreibst personalisierte Kaltakquise-Emails auf Deutsch (Schweizer Hochdeutsch).
Die Emails sollen:
- Professionell aber persoenlich sein
- Konkrete Probleme der Webseite ansprechen
- Einen klaren Nutzen kommunizieren
- Kurz und praegnant sein (150-250 Woerter)
- Einen klaren Call-to-Action haben
- Den CEO/Geschaeftsfuehrer direkt ansprechen
Antworte NUR mit validem JSON."""


class EmailWriterAgent(BaseAgent):
    """
    Writes personalized cold emails.

    Creates highly personalized outreach emails based on:
    - Company research profiles
    - CEO/decision maker information
    - Industry-specific pain points
    - Identified website problems
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        """Initialize EmailWriter agent."""
        super().__init__(
            name="EmailWriter",
            agent_type="email_writer",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._template_manager = EmailTemplateManager()
        self._pending_profiles: list[dict[str, Any]] = []
        self._signature = ""

        if settings:
            self._signature = settings.email.signature

    async def run(self) -> None:
        """Main agent loop - process pending profiles and write emails."""
        # Check for profiles from database if queue is empty
        if not self._pending_profiles and self._db:
            prospects = await self._db.get_researched_prospects(limit=5)
            for p in prospects:
                profile = await self._db.get_company_profile(p.id)
                if profile:
                    self._pending_profiles.append({
                        "prospect": p.to_dict(),
                        "profile": profile.to_dict(),
                    })

        if not self._pending_profiles:
            await asyncio.sleep(60)  # Wait if no work
            return

        self.status = AgentStatus.WORKING

        # Process one profile at a time for quality
        data = self._pending_profiles.pop(0)
        prospect = data.get("prospect", {})
        profile = data.get("profile", data)  # Profile might be at root level

        self.log(f"Writing email for: {prospect.get('name', 'Unknown')}")

        try:
            email_draft = await self._write_email(prospect, profile)

            if email_draft:
                # Save to database
                if self._db and prospect.get("id"):
                    db_email = await self._db.create_email(
                        prospect_id=prospect["id"],
                        subject=email_draft["subject"],
                        body=email_draft["body"],
                        email_type="cold_outreach",
                    )
                    email_draft["id"] = db_email.id

                    # Update status to pending review
                    await self._db.update_email_status(
                        db_email.id,
                        EmailStatus.PENDING_REVIEW,
                        personalization_score=email_draft.get("personalization_score"),
                    )

                self.log(
                    f"Email draft ready for {prospect.get('name')}. "
                    f"Sending to @QualityControl for review."
                )

                # Send to QualityControl
                await self.send_message(
                    recipient_id="quality_control",
                    message_type=MessageType.EMAIL_QUALITY_CHECK.value,
                    payload={
                        "email_draft": email_draft,
                        "prospect": prospect,
                        "profile": profile,
                        "text": "@QualityControl please review this email",
                    },
                    priority="normal",
                )

        except Exception as e:
            self.log(f"Error writing email for {prospect.get('name')}: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK_ASSIGNED.value:
            await self._execute_subtask(message.payload)

        elif message.message_type == MessageType.PROSPECT_RESEARCH_COMPLETE.value:
            # Receive researched profiles
            profiles = message.payload.get("profiles", [])
            self._pending_profiles.extend(profiles)
            self.log(
                f"Received {len(profiles)} profiles from ResearchManager. "
                f"Queue size: {len(self._pending_profiles)}"
            )

        elif message.message_type == MessageType.EMAIL_REJECTED.value:
            # Handle rejected email - rewrite it
            email_data = message.payload.get("email_data", {})
            feedback = message.payload.get("feedback", {})
            self.log(
                f"Email rejected. Feedback: {feedback.get('issues', [])}. "
                "Rewriting..."
            )
            # Add back to queue with feedback for rewrite
            email_data["rewrite_feedback"] = feedback
            self._pending_profiles.insert(0, email_data)

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
            count = 0
            for data in self._pending_profiles[:5]:
                prospect = data.get("prospect", {})
                profile = data.get("profile", data)
                draft = await self._write_email(prospect, profile)
                if draft:
                    count += 1
            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_SUBTASK_COMPLETE.value,
                payload={
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "output_data": {"type": "emails", "title": f"{count} Emails geschrieben", "count": count},
                },
            )
        except Exception as e:
            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_FAILED.value,
                payload={"task_id": task_id, "subtask_id": subtask_id, "error": str(e)},
            )

    async def _write_email(
        self, prospect: dict[str, Any], profile: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """
        Write a personalized email.

        Args:
            prospect: Prospect basic info
            profile: Research profile

        Returns:
            Email draft dict with subject, body, and metadata
        """
        # Try Claude-powered email writing first
        if self._llm:
            llm_result = await self._write_email_with_llm(prospect, profile)
            if llm_result:
                return llm_result

        # Fallback to template-based writing
        # Extract key information
        ceo_name = profile.get("ceo_name", "")
        firma_name = prospect.get("name", "Ihre Firma")
        industry = prospect.get("industry", "")
        region = prospect.get("region", "Schweiz")
        website_problems = profile.get("website_problems", [])
        pain_points = profile.get("pain_points", [])
        buying_signals = profile.get("buying_signals", [])

        # Handle rewrite case
        rewrite_feedback = profile.get("rewrite_feedback", {})
        variant = 1
        if rewrite_feedback:
            # Try a different template variant on rewrite
            variant = rewrite_feedback.get("suggested_variant", 2)

        # Choose subject line category based on profile
        if buying_signals:
            subject_category = "curiosity"
        elif len(website_problems) >= 2:
            subject_category = "problem_focused"
        else:
            subject_category = "value_focused"

        # Personalize the greeting
        if ceo_name:
            # Try to determine gender from name (simplified)
            anrede = self._determine_anrede(ceo_name)
            ceo_last_name = ceo_name.split()[-1] if " " in ceo_name else ceo_name
        else:
            anrede = ""
            ceo_last_name = ""
            ceo_name = "geschätzte Geschäftsleitung"

        # Get subject lines
        subject_context = {
            "firma_name": firma_name,
            "ceo_name": ceo_last_name or ceo_name,
            "industry": industry,
            "region": region,
        }
        subject_lines = self._template_manager.get_subject_lines(
            subject_category, subject_context
        )
        subject = subject_lines[0] if subject_lines else f"Kurze Frage zu {firma_name}"

        # Prepare context for template
        context = {
            "anrede": anrede,
            "ceo_name": ceo_last_name or ceo_name,
            "firma_name": firma_name,
            "industry": industry,
            "region": region,
            "website_problems": website_problems[:3],  # Max 3 problems
            "main_problem": website_problems[0] if website_problems else "Optimierungspotenzial",
            "pain_points": pain_points,
            "buying_signal_hook": self._create_buying_signal_hook(buying_signals),
            "signature": self._signature,
            "subject_line": subject,
        }

        # Render the email
        try:
            subject, body = self._template_manager.render_cold_email(
                ceo_name=ceo_last_name or ceo_name,
                firma_name=firma_name,
                industry=industry,
                region=region,
                website_problems=website_problems[:3],
                variant=variant,
                signature=self._signature,
                **context,
            )
        except Exception as e:
            self.log(f"Template rendering error: {e}", level="WARNING")
            # Fallback to simple email
            subject, body = self._write_simple_email(context)

        # Calculate personalization score
        personalization_score = self._calculate_personalization_score(
            body, ceo_name, firma_name, website_problems
        )

        return {
            "subject": subject,
            "body": body,
            "prospect_id": prospect.get("id"),
            "personalization_score": personalization_score,
            "word_count": len(body.split()),
            "template_variant": variant,
            "created_at": datetime.now().isoformat(),
        }

    def _determine_anrede(self, name: str) -> str:
        """Determine appropriate salutation based on name."""
        first_name = name.split()[0].lower() if name else ""

        # Common Swiss German female names
        female_names = [
            "anna", "maria", "sandra", "claudia", "monika", "petra", "andrea",
            "christine", "nicole", "sabine", "daniela", "barbara", "susanne",
            "karin", "brigitte", "silvia", "verena", "ruth", "cornelia",
        ]

        # Common Swiss German male names
        male_names = [
            "peter", "hans", "thomas", "daniel", "martin", "andreas", "michael",
            "stefan", "markus", "beat", "bruno", "christian", "patrick", "urs",
            "marcel", "rolf", "franz", "walter", "kurt", "max",
        ]

        if first_name in female_names:
            return "Frau"
        elif first_name in male_names:
            return "Herr"
        else:
            return "Herr/Frau"

    def _create_buying_signal_hook(self, signals: list[str]) -> str:
        """Create a hook based on buying signals."""
        if not signals:
            return "Es scheint der richtige Zeitpunkt zu sein"

        signal = signals[0]

        if "Stellenanzeigen" in signal or "wachsen" in signal.lower():
            return "Ihr Unternehmen wächst - Ihre Webseite sollte mitwachsen"
        elif "Karriere" in signal:
            return "Sie suchen neue Mitarbeiter - Ihre Online-Präsenz ist Teil des ersten Eindrucks"
        elif "Digitalisierung" in signal:
            return "Sie denken bereits über Digitalisierung nach"
        else:
            return "Jetzt ist der richtige Moment für eine Modernisierung"

    def _write_simple_email(self, context: dict[str, Any]) -> tuple[str, str]:
        """Write a simple fallback email."""
        subject = f"{context['firma_name']} - Kurze Frage"

        body = f"""Guten Tag {context['anrede']} {context['ceo_name']},

ich bin auf {context['firma_name']} aufmerksam geworden und hätte eine kurze Frage:

Ist die Modernisierung Ihrer Online-Präsenz aktuell ein Thema für Sie?

Als Webentwickler helfe ich Schweizer KMUs, ihre Webseite auf den neuesten Stand zu bringen - professionell und bezahlbar.

Falls Sie Interesse haben, stehe ich gerne für ein unverbindliches Gespräch zur Verfügung.

{context['signature']}"""

        return subject, body

    async def _write_email_with_llm(
        self, prospect: dict[str, Any], profile: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Write a personalized email using Claude."""
        if not self._llm:
            return None

        try:
            result = await self._llm.complete_structured(
                prompt=f"""Schreibe eine personalisierte Kaltakquise-Email fuer:

Firma: {prospect.get('name', 'Unbekannt')}
Branche: {prospect.get('industry', '')}
Region: {prospect.get('region', 'Schweiz')}
CEO/Ansprechperson: {profile.get('ceo_name', 'unbekannt')}
Webseite-Probleme: {', '.join(profile.get('website_problems', [])[:3]) or 'keine bekannt'}
Buying Signals: {', '.join(profile.get('buying_signals', [])[:3]) or 'keine'}
Pain Points: {', '.join(profile.get('pain_points', [])[:3]) or 'keine bekannt'}

Signatur: {self._signature}""",
                system=EMAIL_WRITER_SYSTEM_PROMPT,
                response_schema={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["subject", "body"],
                },
                agent_id="email_writer",
            )

            if result and result.get("subject") and result.get("body"):
                return {
                    "subject": result["subject"],
                    "body": result["body"],
                    "prospect_id": prospect.get("id"),
                    "personalization_score": self._calculate_personalization_score(
                        result["body"],
                        profile.get("ceo_name", ""),
                        prospect.get("name", ""),
                        profile.get("website_problems", []),
                    ),
                    "word_count": len(result["body"].split()),
                    "template_variant": 0,  # LLM-generated
                    "created_at": datetime.now().isoformat(),
                }
        except Exception as e:
            self.log(f"LLM email writing failed: {e}", level="WARNING")

        return None

    def _calculate_personalization_score(
        self,
        body: str,
        ceo_name: str,
        firma_name: str,
        problems: list[str],
    ) -> float:
        """
        Calculate how personalized the email is (1-10).

        Checks for:
        - Use of CEO name
        - Company name mentions
        - Specific problems mentioned
        - Industry-specific content
        """
        score = 5.0  # Base score

        body_lower = body.lower()

        # CEO name used (not just generic)
        if ceo_name and ceo_name.lower() in body_lower:
            if ceo_name.lower() not in ["geschäftsleitung", "herr/frau"]:
                score += 2.0

        # Company name used multiple times
        firma_lower = firma_name.lower()
        firma_mentions = body_lower.count(firma_lower)
        if firma_mentions >= 2:
            score += 1.0
        if firma_mentions >= 3:
            score += 0.5

        # Specific problems mentioned
        for problem in problems[:3]:
            if problem.lower() in body_lower:
                score += 0.5

        # Length check (not too short, not too long)
        word_count = len(body.split())
        if 150 <= word_count <= 250:
            score += 1.0
        elif 100 <= word_count <= 300:
            score += 0.5

        return min(10.0, max(1.0, score))
