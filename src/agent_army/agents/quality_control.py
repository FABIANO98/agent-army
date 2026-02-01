"""QualityControl Agent - Checks email quality before sending."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, Optional

import httpx

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import EmailStatus

if TYPE_CHECKING:
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


class QualityControlAgent(BaseAgent):
    """
    Checks email quality before sending.

    Validates:
    - Grammar and spelling (LanguageTool API)
    - Spam score (custom rules)
    - Personalization level
    - Length requirements
    - Call-to-action presence
    - No forgotten placeholders
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize QualityControl agent."""
        super().__init__(
            name="QualityControl",
            agent_type="quality_control",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._pending_emails: list[dict[str, Any]] = []

        # Quality thresholds
        self._min_personalization_score = 7
        self._min_words = 150
        self._max_words = 250
        self._max_spam_score = 5

        if settings:
            self._min_personalization_score = settings.agents.min_personalization_score
            self._min_words = settings.agents.min_email_words
            self._max_words = settings.agents.max_email_words

    async def start(self) -> None:
        """Start the agent and initialize HTTP client."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        await super().start()

    async def stop(self) -> None:
        """Stop the agent and close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
        await super().stop()

    async def run(self) -> None:
        """Main agent loop - process pending emails for review."""
        # Check database for pending review emails
        if not self._pending_emails and self._db:
            pending = await self._db.get_pending_emails(limit=10)
            for email in pending:
                prospect = await self._db.get_prospect(email.prospect_id)
                self._pending_emails.append({
                    "email_draft": email.to_dict(),
                    "prospect": prospect.to_dict() if prospect else {},
                })

        if not self._pending_emails:
            await asyncio.sleep(30)  # Check frequently
            return

        self.status = AgentStatus.WORKING

        # Process one email at a time
        email_data = self._pending_emails.pop(0)
        email_draft = email_data.get("email_draft", {})
        prospect = email_data.get("prospect", {})
        profile = email_data.get("profile", {})

        self.log(f"Reviewing email for: {prospect.get('name', 'Unknown')}")

        try:
            # Perform quality checks
            result = await self._check_quality(email_draft, prospect, profile)

            if result["approved"]:
                self.log(
                    f"Email approved! Score: {result['total_score']}/10. "
                    f"Sending to @EmailSender"
                )

                # Update database
                if self._db and email_draft.get("id"):
                    await self._db.update_email_status(
                        email_draft["id"],
                        EmailStatus.APPROVED,
                        spam_score=result.get("spam_score"),
                        quality_feedback=str(result),
                    )

                # Send to EmailSender
                await self.send_message(
                    recipient_id="email_sender",
                    message_type=MessageType.EMAIL_APPROVED.value,
                    payload={
                        "email_draft": email_draft,
                        "prospect": prospect,
                        "quality_report": result,
                        "text": "@EmailSender ready to send",
                    },
                    priority="normal",
                )
            else:
                self.log(
                    f"Email needs revision. Issues: {result['issues']}. "
                    f"Sending back to @EmailWriter"
                )

                # Update database
                if self._db and email_draft.get("id"):
                    await self._db.update_email_status(
                        email_draft["id"],
                        EmailStatus.REJECTED,
                        quality_feedback=str(result),
                    )

                # Send back to EmailWriter
                await self.send_message(
                    recipient_id="email_writer",
                    message_type=MessageType.EMAIL_REJECTED.value,
                    payload={
                        "email_data": email_data,
                        "feedback": result,
                        "text": "@EmailWriter please revise",
                    },
                    priority="high",
                )

        except Exception as e:
            self.log(f"Error reviewing email: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.EMAIL_QUALITY_CHECK.value:
            # Add to review queue
            self._pending_emails.append(message.payload)
            self.log(
                f"Email queued for review. Queue size: {len(self._pending_emails)}"
            )

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def _check_quality(
        self,
        email_draft: dict[str, Any],
        prospect: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Perform all quality checks on an email.

        Returns:
            Quality report dict with approval status and issues
        """
        issues: list[str] = []
        suggestions: list[str] = []
        scores: dict[str, float] = {}

        subject = email_draft.get("subject", "")
        body = email_draft.get("body", "")

        # 1. Check for forgotten placeholders
        placeholder_check = self._check_placeholders(subject + body)
        if not placeholder_check["ok"]:
            issues.append(f"Platzhalter gefunden: {placeholder_check['found']}")

        # 2. Check word count
        word_count = len(body.split())
        if word_count < self._min_words:
            issues.append(f"Zu kurz ({word_count} Wörter, min. {self._min_words})")
            suggestions.append("Mehr Details oder Nutzen-Argumente hinzufügen")
        elif word_count > self._max_words:
            issues.append(f"Zu lang ({word_count} Wörter, max. {self._max_words})")
            suggestions.append("Kürzen und auf das Wesentliche fokussieren")
        scores["length"] = min(10, max(1, 10 - abs(200 - word_count) / 20))

        # 3. Check personalization
        personalization_score = email_draft.get("personalization_score", 5)
        if personalization_score < self._min_personalization_score:
            issues.append(
                f"Personalisierung zu gering ({personalization_score}/10, "
                f"min. {self._min_personalization_score})"
            )
            suggestions.append("CEO-Name und spezifische Probleme erwähnen")
        scores["personalization"] = personalization_score

        # 4. Check for call-to-action
        cta_check = self._check_call_to_action(body)
        if not cta_check["ok"]:
            issues.append("Kein klarer Call-to-Action")
            suggestions.append("Klare Handlungsaufforderung am Ende hinzufügen")
        scores["cta"] = 10 if cta_check["ok"] else 3

        # 5. Check spam score
        spam_result = await self._calculate_spam_score(subject, body)
        if spam_result["score"] > self._max_spam_score:
            issues.append(f"Spam-Risiko zu hoch ({spam_result['score']}/10)")
            suggestions.extend(spam_result.get("suggestions", []))
        scores["spam"] = 10 - spam_result["score"]

        # 6. Check grammar (if API available)
        grammar_result = await self._check_grammar(body)
        if grammar_result.get("errors"):
            error_count = len(grammar_result["errors"])
            if error_count > 3:
                issues.append(f"Grammatik/Rechtschreibung: {error_count} Fehler")
            scores["grammar"] = max(1, 10 - error_count)
        else:
            scores["grammar"] = 10

        # 7. Check subject line
        subject_check = self._check_subject_line(subject)
        if not subject_check["ok"]:
            issues.extend(subject_check.get("issues", []))
        scores["subject"] = subject_check.get("score", 5)

        # Calculate total score
        total_score = sum(scores.values()) / len(scores)

        # Determine if approved
        approved = len(issues) == 0 or (
            len(issues) <= 1 and total_score >= 7 and "Platzhalter" not in str(issues)
        )

        return {
            "approved": approved,
            "issues": issues,
            "suggestions": suggestions,
            "scores": scores,
            "total_score": round(total_score, 1),
            "spam_score": spam_result["score"],
            "word_count": word_count,
            "suggested_variant": 2 if not approved else None,
        }

    def _check_placeholders(self, text: str) -> dict[str, Any]:
        """Check for forgotten placeholders."""
        # Common placeholder patterns
        patterns = [
            r"\{\{.*?\}\}",  # {{placeholder}}
            r"\[\[.*?\]\]",  # [[placeholder]]
            r"<.*?>",  # <placeholder> (but not HTML tags)
            r"\[NAME\]",
            r"\[FIRMA\]",
            r"\[EMAIL\]",
            r"XXX",
            r"TODO",
            r"FIXME",
        ]

        found: list[str] = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            # Filter out likely HTML tags
            matches = [m for m in matches if not m.startswith("<a") and not m.startswith("<br")]
            found.extend(matches)

        return {"ok": len(found) == 0, "found": found}

    def _check_call_to_action(self, body: str) -> dict[str, Any]:
        """Check for presence of call-to-action."""
        cta_keywords = [
            "gespräch",
            "termin",
            "antwort",
            "antworten",
            "kontakt",
            "erreichen",
            "anruf",
            "meeting",
            "interesse",
            "link",
            "klick",
        ]

        body_lower = body.lower()

        # Check last paragraph for CTA
        paragraphs = body.strip().split("\n\n")
        last_paragraphs = " ".join(paragraphs[-2:]).lower() if len(paragraphs) > 1 else body_lower

        has_cta = any(keyword in last_paragraphs for keyword in cta_keywords)

        # Check for question mark (implies engagement)
        has_question = "?" in last_paragraphs

        return {"ok": has_cta or has_question}

    async def _calculate_spam_score(
        self, subject: str, body: str
    ) -> dict[str, Any]:
        """Calculate spam score based on common spam indicators."""
        score = 0
        suggestions: list[str] = []

        full_text = (subject + " " + body).lower()

        # Spam trigger words
        spam_words = {
            "gratis": 1,
            "kostenlos": 0.5,  # Less spammy in German
            "garantiert": 1,
            "sofort": 0.5,
            "jetzt kaufen": 2,
            "limitiert": 1,
            "exklusiv": 0.5,
            "gewinn": 1.5,
            "rabatt": 1,
            "sonderangebot": 1.5,
            "!!!": 2,
            "€€€": 2,
            "chf": 0,  # Currency mention is normal
        }

        for word, weight in spam_words.items():
            if word in full_text:
                score += weight
                if weight > 1:
                    suggestions.append(f"Wort '{word}' vermeiden")

        # Check for ALL CAPS
        caps_words = re.findall(r"\b[A-Z]{4,}\b", subject + body)
        if caps_words:
            score += len(caps_words) * 0.5
            suggestions.append("Grossbuchstaben-Wörter vermeiden")

        # Check for excessive punctuation
        if "!!" in full_text or "??" in full_text:
            score += 1
            suggestions.append("Weniger Satzzeichen verwenden")

        # Check for too many links
        link_count = full_text.count("http")
        if link_count > 2:
            score += link_count - 1
            suggestions.append("Weniger Links verwenden")

        # Subject line checks
        if subject.isupper():
            score += 2
            suggestions.append("Betreff nicht komplett gross schreiben")

        if len(subject) > 70:
            score += 1
            suggestions.append("Kürzeren Betreff verwenden")

        return {
            "score": min(10, score),
            "suggestions": suggestions,
        }

    async def _check_grammar(self, text: str) -> dict[str, Any]:
        """
        Check grammar using LanguageTool API.

        Note: Requires LanguageTool API or local instance.
        """
        if not self._http_client:
            return {"errors": []}

        # Try LanguageTool public API (rate limited)
        try:
            response = await self._http_client.post(
                "https://api.languagetool.org/v2/check",
                data={
                    "text": text,
                    "language": "de-CH",  # Swiss German
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                result = response.json()
                errors = [
                    {
                        "message": match.get("message"),
                        "context": match.get("context", {}).get("text", ""),
                        "suggestions": [r.get("value") for r in match.get("replacements", [])[:3]],
                    }
                    for match in result.get("matches", [])
                ]
                return {"errors": errors}

        except Exception as e:
            self.log(f"Grammar check failed: {e}", level="DEBUG")

        return {"errors": []}

    def _check_subject_line(self, subject: str) -> dict[str, Any]:
        """Check subject line quality."""
        issues: list[str] = []
        score = 10

        # Length check
        if len(subject) < 10:
            issues.append("Betreff zu kurz")
            score -= 2
        elif len(subject) > 60:
            issues.append("Betreff zu lang (wird abgeschnitten)")
            score -= 1

        # Check for company/person name (personalization)
        # This is a simple check - in production, match against actual data
        has_personalization = any(
            word[0].isupper() and len(word) > 2
            for word in subject.split()
            if word not in ["Kurze", "Frage", "Ihre", "Eine"]
        )
        if not has_personalization:
            score -= 1

        # Check for spam indicators
        if subject.count("!") > 1:
            issues.append("Zu viele Ausrufezeichen im Betreff")
            score -= 2

        if subject.isupper():
            issues.append("Betreff nicht in Grossbuchstaben")
            score -= 3

        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "score": max(1, score),
        }
