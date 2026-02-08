"""DealTracker Agent - Tracks the entire sales pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

from rich.console import Console
from rich.table import Table

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import DealStage

if TYPE_CHECKING:
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


DEAL_TRACKER_SYSTEM_PROMPT = """Du bist ein Sales-Analyst fuer Schweizer KMU-Vertrieb.
Erstelle narrative Reports und Next-Step-Empfehlungen basierend auf Pipeline-Daten.
Antworte NUR mit validem JSON."""


class DealTrackerAgent(BaseAgent):
    """
    Tracks the entire sales pipeline.

    Features:
    - Pipeline monitoring through stages
    - Daily reports
    - Stale lead identification
    - Follow-up triggering
    - Important event alerts
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        """Initialize DealTracker agent."""
        super().__init__(
            name="DealTracker",
            agent_type="deal_tracker",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._console = Console()
        self._last_report_date: Optional[datetime] = None
        self._last_stale_check: Optional[datetime] = None

        # Configuration
        self._report_hour = 18  # 18:00
        self._stale_days = 7
        self._check_interval = 3600  # 1 hour

        if settings:
            self._report_hour = settings.agents.daily_report_hour
            self._stale_days = settings.agents.stale_lead_days

    async def run(self) -> None:
        """Main agent loop - monitor pipeline and generate reports."""
        now = datetime.now()

        # Check if it's time for daily report
        if self._should_generate_report(now):
            await self._generate_daily_report()
            self._last_report_date = now

        # Check for stale leads periodically
        if self._should_check_stale_leads(now):
            await self._check_stale_leads()
            self._last_stale_check = now

        await asyncio.sleep(300)  # Check every 5 minutes

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK_ASSIGNED.value:
            task_id = message.payload.get("task_id")
            subtask_id = message.payload.get("subtask_id")
            report = {}
            if self._db:
                report = await self._db.get_daily_report()
            await self.send_message(
                recipient_id="task_manager",
                message_type=MessageType.TASK_SUBTASK_COMPLETE.value,
                payload={
                    "task_id": task_id, "subtask_id": subtask_id,
                    "output_data": {"type": "report", "title": "Pipeline Report", "data": report},
                },
            )

        elif message.message_type == MessageType.EMAIL_SENT.value:
            # Track sent email
            prospect_id = message.payload.get("prospect", {}).get("id")
            if prospect_id:
                await self._update_deal_activity(prospect_id)
            self.log(
                f"Email sent tracked for prospect {message.payload.get('prospect', {}).get('name')}"
            )

        elif message.message_type == MessageType.DEAL_STAGE_UPDATE.value:
            # Update deal stage
            prospect_id = message.payload.get("prospect_id")
            new_stage = message.payload.get("new_stage")
            reason = message.payload.get("reason", "")

            if prospect_id and new_stage:
                await self._update_deal_stage(prospect_id, new_stage, reason)

        elif message.message_type == MessageType.DEAL_ALERT.value:
            # Handle important alerts
            alert_type = message.payload.get("alert_type")
            await self._handle_alert(message.payload)

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    def _should_generate_report(self, now: datetime) -> bool:
        """Check if daily report should be generated."""
        if self._last_report_date and self._last_report_date.date() == now.date():
            return False

        return now.hour >= self._report_hour

    def _should_check_stale_leads(self, now: datetime) -> bool:
        """Check if stale lead check is needed."""
        if not self._last_stale_check:
            return True

        elapsed = (now - self._last_stale_check).total_seconds()
        return elapsed >= self._check_interval

    async def _generate_daily_report(self) -> None:
        """Generate and log daily report."""
        self.status = AgentStatus.WORKING
        self.log("Generating daily report...")

        if not self._db:
            self.log("No database connection - cannot generate report", level="WARNING")
            return

        try:
            report = await self._db.get_daily_report()
            pipeline = await self._db.get_pipeline_stats()

            # Format report - use LLM for narrative if available
            if self._llm:
                report_text = await self._generate_narrative_report(report, pipeline)
            else:
                report_text = self._format_report(report, pipeline)

            # Log the report
            self.log(f"Daily Report:\n{report_text}")

            # Broadcast report to all agents
            await self.send_message(
                recipient_id="broadcast",
                message_type=MessageType.BROADCAST.value,
                payload={
                    "type": "daily_report",
                    "report": report,
                    "pipeline": pipeline,
                    "text": f"Daily Report for {report['date']}",
                },
                priority="low",
            )

        except Exception as e:
            self.log(f"Error generating report: {e}", level="ERROR")

        self.status = AgentStatus.IDLE

    def _format_report(
        self, report: dict[str, Any], pipeline: dict[str, Any]
    ) -> str:
        """Format the daily report as text."""
        lines = [
            f"\n{'='*50}",
            f"DAILY REPORT - {report['date']}",
            f"{'='*50}",
            "",
            "TODAY'S ACTIVITY:",
            f"  Prospects found:     {report['prospects_found']}",
            f"  Emails sent:         {report['emails_sent']}",
            f"  Responses received:  {report['responses_received']}",
            f"  Positive responses:  {report['positive_responses']}",
            "",
            "PIPELINE STATUS:",
        ]

        stages = pipeline.get("stages", {})
        stage_names = {
            "cold_prospect": "Cold Prospects",
            "contacted": "Contacted",
            "responded": "Responded",
            "meeting_scheduled": "Meeting Scheduled",
            "proposal_sent": "Proposal Sent",
            "negotiation": "Negotiation",
            "won": "Won",
            "lost": "Lost",
        }

        for stage, name in stage_names.items():
            data = stages.get(stage, {"count": 0, "value": 0})
            count = data.get("count", 0)
            value = data.get("value", 0)
            if count > 0 or stage in ["won", "lost"]:
                value_str = f" (CHF {value:,.0f})" if value else ""
                lines.append(f"  {name:20} {count:3}{value_str}")

        total = pipeline.get("total", {})
        lines.extend([
            "",
            f"TOTAL DEALS: {total.get('count', 0)}",
            f"TOTAL VALUE: CHF {total.get('value', 0):,.0f}",
            f"{'='*50}",
        ])

        # Calculate conversion rates
        contacted = stages.get("contacted", {}).get("count", 0)
        responded = stages.get("responded", {}).get("count", 0)
        won = stages.get("won", {}).get("count", 0)

        if contacted > 0:
            response_rate = (responded / contacted) * 100
            lines.append(f"Response Rate: {response_rate:.1f}%")

        if responded > 0:
            win_rate = (won / responded) * 100
            lines.append(f"Win Rate: {win_rate:.1f}%")

        return "\n".join(lines)

    async def _generate_narrative_report(
        self, report: dict[str, Any], pipeline: dict[str, Any]
    ) -> str:
        """Generate a narrative report using Claude."""
        if not self._llm:
            return self._format_report(report, pipeline)

        try:
            import json
            result = await self._llm.complete_structured(
                prompt=f"""Erstelle einen kurzen narrativen Tagesbericht:

Tages-Aktivitaet:
{json.dumps(report, indent=2, default=str)}

Pipeline-Status:
{json.dumps(pipeline, indent=2, default=str)}""",
                system=DEAL_TRACKER_SYSTEM_PROMPT,
                response_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "highlights": {"type": "array", "items": {"type": "string"}},
                        "recommendations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary"],
                },
                agent_id="deal_tracker",
            )

            if result:
                lines = [
                    f"\n{'='*50}",
                    f"DAILY REPORT - {report.get('date', 'today')}",
                    f"{'='*50}",
                    "",
                    result.get("summary", ""),
                    "",
                ]
                if result.get("highlights"):
                    lines.append("HIGHLIGHTS:")
                    for h in result["highlights"]:
                        lines.append(f"  * {h}")
                    lines.append("")
                if result.get("recommendations"):
                    lines.append("NEXT STEPS:")
                    for r in result["recommendations"]:
                        lines.append(f"  → {r}")
                lines.append(f"{'='*50}")
                return "\n".join(lines)
        except Exception as e:
            self.log(f"LLM report generation failed: {e}", level="WARNING")

        return self._format_report(report, pipeline)

    async def _check_stale_leads(self) -> None:
        """Check for and handle stale leads."""
        if not self._db:
            return

        self.log("Checking for stale leads...")

        try:
            stale_deals = await self._db.get_stale_deals(days=self._stale_days)

            if stale_deals:
                self.log(
                    f"Found {len(stale_deals)} stale leads "
                    f"(no activity in {self._stale_days}+ days)"
                )

                for deal in stale_deals:
                    prospect = await self._db.get_prospect(deal.prospect_id)
                    if not prospect:
                        continue

                    self.log(
                        f"Stale lead: {prospect.name} "
                        f"(Stage: {deal.stage}, Last activity: {deal.last_activity})"
                    )

                    # Request follow-up
                    await self.send_message(
                        recipient_id="email_sender",
                        message_type=MessageType.EMAIL_DRAFT_REQUEST.value,
                        payload={
                            "prospect": prospect.to_dict(),
                            "email_type": "follow_up",
                            "reason": "stale_lead",
                            "days_inactive": self._stale_days,
                        },
                        priority="low",
                    )

        except Exception as e:
            self.log(f"Error checking stale leads: {e}", level="ERROR")

    async def _update_deal_activity(self, prospect_id: int) -> None:
        """Update deal last activity timestamp."""
        if not self._db:
            return

        deal = await self._db.get_deal_by_prospect(prospect_id)
        if deal:
            await self._db.update_deal_stage(
                deal.id,
                DealStage(deal.stage),
            )

    async def _update_deal_stage(
        self, prospect_id: int, new_stage: str, reason: str = ""
    ) -> None:
        """Update deal stage."""
        if not self._db:
            return

        try:
            stage = DealStage(new_stage)
        except ValueError:
            self.log(f"Invalid stage: {new_stage}", level="WARNING")
            return

        deal = await self._db.get_deal_by_prospect(prospect_id)
        if deal:
            old_stage = deal.stage
            kwargs: dict[str, Any] = {}

            if stage == DealStage.LOST:
                kwargs["lost_reason"] = reason

            await self._db.update_deal_stage(deal.id, stage, **kwargs)

            prospect = await self._db.get_prospect(prospect_id)
            name = prospect.name if prospect else f"ID {prospect_id}"
            self.log(f"Deal stage updated: {name} ({old_stage} -> {new_stage})")

    async def _handle_alert(self, payload: dict[str, Any]) -> None:
        """Handle important alerts."""
        alert_type = payload.get("alert_type")

        if alert_type == "positive_response":
            response = payload.get("response", {})
            self.log(
                f"ALERT: Positive response from {response.get('from_name', 'Unknown')}!",
                level="WARNING",
            )

        elif alert_type == "meeting_scheduled":
            prospect_id = payload.get("prospect_id")
            if self._db and prospect_id:
                prospect = await self._db.get_prospect(prospect_id)
                if prospect:
                    self.log(
                        f"ALERT: Meeting scheduled with {prospect.name}!",
                        level="WARNING",
                    )

        elif alert_type == "deal_won":
            prospect_id = payload.get("prospect_id")
            value = payload.get("value", 0)
            if self._db and prospect_id:
                prospect = await self._db.get_prospect(prospect_id)
                if prospect:
                    self.log(
                        f"ALERT: Deal WON! {prospect.name} - CHF {value:,.0f}",
                        level="WARNING",
                    )

    async def get_pipeline_summary(self) -> dict[str, Any]:
        """Get current pipeline summary."""
        if not self._db:
            return {}

        return await self._db.get_pipeline_stats()

    async def get_recent_activity(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent activity from logs."""
        if not self._db:
            return []

        logs = await self._db.get_agent_logs(limit=limit)
        return [log.to_dict() for log in logs]
