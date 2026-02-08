"""EmailSender Agent - Sends emails strategically."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import EmailStatus, ProspectStatus, DealStage

if TYPE_CHECKING:
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


class EmailSenderAgent(BaseAgent):
    """
    Sends emails strategically.

    Features:
    - SMTP integration
    - Optimal timing (10:00 for Swiss B2B)
    - Rate limiting (max 50/day)
    - Email tracking
    - Bounce handling
    - Follow-up scheduling
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize EmailSender agent."""
        super().__init__(
            name="EmailSender",
            agent_type="email_sender",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._pending_emails: list[dict[str, Any]] = []
        self._daily_sent = 0
        self._last_reset_date: Optional[datetime] = None

        # Configuration
        self._smtp_host = "smtp.gmail.com"
        self._smtp_port = 587
        self._smtp_username = ""
        self._smtp_password = ""
        self._from_email = ""
        self._from_name = "Fabiano Frascati"
        self._daily_limit = 50
        self._optimal_send_hour = 10  # 10:00 Swiss time
        self._follow_up_days = 3

        if settings:
            self._smtp_host = settings.email.smtp_host
            self._smtp_port = settings.email.smtp_port
            self._smtp_username = settings.email.smtp_username
            self._smtp_password = settings.email.smtp_password
            self._from_email = settings.email.from_email
            self._from_name = settings.email.from_name
            self._daily_limit = settings.agents.daily_email_limit
            self._optimal_send_hour = settings.agents.optimal_send_hour
            self._follow_up_days = settings.agents.follow_up_days

    async def run(self) -> None:
        """Main agent loop - send pending emails."""
        now = datetime.now()

        # Reset daily counter at midnight
        if self._last_reset_date is None or self._last_reset_date.date() != now.date():
            self._daily_sent = 0
            self._last_reset_date = now
            if self._db:
                self._daily_sent = await self._db.get_today_sent_count()

        # Check daily limit
        if self._daily_sent >= self._daily_limit:
            self.log(
                f"Daily limit reached ({self._daily_sent}/{self._daily_limit}). "
                "Waiting until tomorrow."
            )
            await asyncio.sleep(3600)
            return

        # Check if it's optimal sending time
        if not self._is_optimal_send_time(now):
            # Still process queue but with lower priority
            await asyncio.sleep(300)  # Check every 5 minutes

        # Load approved emails from database
        if not self._pending_emails and self._db:
            approved = await self._db.get_approved_emails(limit=10)
            for email in approved:
                prospect = await self._db.get_prospect(email.prospect_id)
                if prospect and prospect.email:
                    self._pending_emails.append({
                        "email_draft": email.to_dict(),
                        "prospect": prospect.to_dict(),
                        "recipient_email": prospect.email,
                    })

        # Check for follow-ups needed
        if self._db:
            await self._check_followups()

        if not self._pending_emails:
            await asyncio.sleep(60)
            return

        self.status = AgentStatus.WORKING

        # Send one email at a time with delay
        email_data = self._pending_emails.pop(0)

        try:
            success = await self._send_email(email_data)

            if success:
                self._daily_sent += 1
                self.log(
                    f"Email sent to {email_data.get('prospect', {}).get('name')}! "
                    f"({self._daily_sent}/{self._daily_limit} today)"
                )

                # Notify DealTracker
                await self.send_message(
                    recipient_id="deal_tracker",
                    message_type=MessageType.EMAIL_SENT.value,
                    payload={
                        "email": email_data["email_draft"],
                        "prospect": email_data["prospect"],
                        "sent_at": datetime.now().isoformat(),
                    },
                    priority="normal",
                )
            else:
                self.log(
                    f"Failed to send email to {email_data.get('prospect', {}).get('name')}",
                    level="WARNING",
                )

        except Exception as e:
            self.log(f"Error sending email: {e}", level="ERROR")
            self._metrics.errors.append(str(e))

        self.status = AgentStatus.IDLE

        # Rate limiting - wait between sends
        await asyncio.sleep(60)  # 1 minute between emails

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
                    "output_data": {"type": "send", "title": "Email-Versand ausgefuehrt"},
                },
            )

        elif message.message_type == MessageType.EMAIL_APPROVED.value:
            email_draft = message.payload.get("email_draft", {})
            prospect = message.payload.get("prospect", {})

            # Get recipient email
            recipient_email = prospect.get("email")
            if not recipient_email and self._db and prospect.get("id"):
                db_prospect = await self._db.get_prospect(prospect["id"])
                if db_prospect:
                    recipient_email = db_prospect.email

            if recipient_email:
                self._pending_emails.append({
                    "email_draft": email_draft,
                    "prospect": prospect,
                    "recipient_email": recipient_email,
                })
                self.log(
                    f"Email queued for sending to {prospect.get('name')}. "
                    f"Queue size: {len(self._pending_emails)}"
                )
            else:
                self.log(
                    f"No email address for {prospect.get('name')}",
                    level="WARNING",
                )

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    def _is_optimal_send_time(self, now: datetime) -> bool:
        """Check if current time is optimal for sending B2B emails."""
        # Optimal: Weekdays 9:00-17:00, best at 10:00
        if now.weekday() >= 5:  # Weekend
            return False

        hour = now.hour
        return 9 <= hour <= 17

    async def _send_email(self, email_data: dict[str, Any]) -> bool:
        """
        Send an email via SMTP.

        Args:
            email_data: Email data including draft and recipient

        Returns:
            True if sent successfully
        """
        email_draft = email_data.get("email_draft", {})
        recipient_email = email_data.get("recipient_email", "")
        prospect = email_data.get("prospect", {})

        if not recipient_email:
            return False

        # Check if SMTP is configured
        if not self._smtp_username or not self._smtp_password:
            self.log("SMTP not configured - simulating send", level="WARNING")
            return await self._simulate_send(email_data)

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email_draft.get("subject", "")
            msg["From"] = f"{self._from_name} <{self._from_email}>"
            msg["To"] = recipient_email

            # Generate tracking ID
            tracking_id = str(uuid.uuid4())

            # Create text and HTML parts
            text_body = email_draft.get("body", "")
            html_body = self._text_to_html(text_body, tracking_id)

            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Send via SMTP
            async with aiosmtplib.SMTP(
                hostname=self._smtp_host,
                port=self._smtp_port,
                use_tls=False,
            ) as smtp:
                await smtp.starttls()
                await smtp.login(self._smtp_username, self._smtp_password)
                await smtp.send_message(msg)

            # Update database
            if self._db and email_draft.get("id"):
                await self._db.update_email_status(
                    email_draft["id"],
                    EmailStatus.SENT,
                    sent_at=datetime.now(),
                    tracking_id=tracking_id,
                )

                # Update prospect status
                if prospect.get("id"):
                    await self._db.update_prospect_status(
                        prospect["id"], ProspectStatus.CONTACTED
                    )

                    # Create/update deal
                    deal = await self._db.get_deal_by_prospect(prospect["id"])
                    if not deal:
                        await self._db.create_deal(
                            prospect_id=prospect["id"],
                            stage=DealStage.CONTACTED,
                        )
                    else:
                        await self._db.update_deal_stage(deal.id, DealStage.CONTACTED)

            return True

        except Exception as e:
            self.log(f"SMTP error: {e}", level="ERROR")

            # Handle bounces
            if "550" in str(e) or "bounced" in str(e).lower():
                if self._db and email_draft.get("id"):
                    await self._db.update_email_status(
                        email_draft["id"],
                        EmailStatus.BOUNCED,
                        bounce_reason=str(e),
                    )

            return False

    async def _simulate_send(self, email_data: dict[str, Any]) -> bool:
        """Simulate sending for testing without SMTP config."""
        email_draft = email_data.get("email_draft", {})
        prospect = email_data.get("prospect", {})

        self.log(
            f"[SIMULATED] Would send to: {email_data.get('recipient_email')}\n"
            f"Subject: {email_draft.get('subject')}"
        )

        # Update database as if sent
        if self._db and email_draft.get("id"):
            tracking_id = str(uuid.uuid4())
            await self._db.update_email_status(
                email_draft["id"],
                EmailStatus.SENT,
                sent_at=datetime.now(),
                tracking_id=tracking_id,
            )

            if prospect.get("id"):
                await self._db.update_prospect_status(
                    prospect["id"], ProspectStatus.CONTACTED
                )

                deal = await self._db.get_deal_by_prospect(prospect["id"])
                if not deal:
                    await self._db.create_deal(
                        prospect_id=prospect["id"],
                        stage=DealStage.CONTACTED,
                    )

        return True

    def _text_to_html(self, text: str, tracking_id: str) -> str:
        """Convert plain text email to HTML with tracking pixel."""
        # Simple conversion - preserve line breaks
        html_body = text.replace("\n", "<br>\n")

        # Add tracking pixel (would need a tracking server in production)
        tracking_pixel = (
            f'<img src="https://track.frascati-systems.ch/open/{tracking_id}" '
            'width="1" height="1" style="display:none" />'
        )

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        {html_body}
        {tracking_pixel}
        </body>
        </html>
        """

    async def _check_followups(self) -> None:
        """Check for emails that need follow-up."""
        if not self._db:
            return

        # Get emails sent X days ago with no response
        followup_emails = await self._db.get_emails_needing_followup(
            days=self._follow_up_days
        )

        for email in followup_emails:
            # Check if we already sent a follow-up
            # (In production, track follow-up count in database)
            prospect = await self._db.get_prospect(email.prospect_id)
            if not prospect:
                continue

            self.log(
                f"Follow-up needed for {prospect.name} "
                f"(sent {self._follow_up_days} days ago, no response)"
            )

            # Request follow-up email from EmailWriter
            # This would trigger the follow-up template
            await self.send_message(
                recipient_id="email_writer",
                message_type=MessageType.EMAIL_DRAFT_REQUEST.value,
                payload={
                    "prospect": prospect.to_dict(),
                    "email_type": "follow_up",
                    "original_email_id": email.id,
                    "follow_up_number": 1,
                },
                priority="low",
            )
