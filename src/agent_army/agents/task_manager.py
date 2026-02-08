"""TaskManager Agent - Decomposes user tasks and coordinates execution."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from ..core.base_agent import BaseAgent, AgentStatus
from ..core.message_bus import Message, MessageType
from ..db.database import Database
from ..db.models import TaskStatus

if TYPE_CHECKING:
    from ..core.llm_service import LLMService
    from ..core.message_bus import MessageBus
    from ..core.registry import AgentRegistry
    from ..utils.config import Settings


TASK_PLANNER_SYSTEM = """Du bist der TaskManager eines B2B Lead-Generierungs-Systems fuer Schweizer KMUs.

Verfuegbare Agenten und deren Faehigkeiten:
- ProspectFinder: Findet neue Unternehmen/Prospects via Web-Suche (Branchen, Regionen, Schweizer KMUs)
- ResearchManager: Recherchiert Unternehmen im Detail (CEO, Mitarbeiter, Website-Analyse, Buying Signals)
- EmailWriter: Schreibt personalisierte Cold-Emails basierend auf Research-Daten
- QualityControl: Prueft Email-Qualitaet (Spam, Personalisierung, Grammatik)
- EmailSender: Versendet Emails via SMTP, timing-optimiert
- ResponseMonitor: Ueberwacht Inbox auf Antworten, kategorisiert Responses
- ResponseWriter: Verfasst Antworten auf eingehende Emails
- DealTracker: Verfolgt Sales Pipeline, generiert Reports

Zerlege die Aufgabe in konkrete Subtasks. Jeder Subtask wird einem Agenten zugewiesen.
Beachte Abhaengigkeiten zwischen Subtasks (z.B. Research vor Email-Schreiben).

Antworte NUR mit validem JSON.
"""

TASK_PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assigned_agent": {"type": "string"},
                    "sequence_order": {"type": "integer"},
                    "depends_on": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


class TaskManagerAgent(BaseAgent):
    """
    Manages user tasks: decomposes them into subtasks,
    assigns them to agents, and tracks progress.
    """

    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        database: Optional[Database] = None,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        super().__init__(
            name="TaskManager",
            agent_type="task_manager",
            message_bus=message_bus,
            registry=registry,
        )
        self._db = database
        self._settings = settings
        self._llm = llm_service
        self._pending_tasks: list[int] = []
        self._active_tasks: dict[int, dict[str, Any]] = {}

    async def run(self) -> None:
        """Process pending tasks and monitor active ones."""
        # Process pending tasks
        if self._pending_tasks:
            task_id = self._pending_tasks.pop(0)
            await self._plan_and_execute_task(task_id)

        # Monitor active tasks
        for task_id in list(self._active_tasks.keys()):
            await self._check_task_progress(task_id)

        await asyncio.sleep(5)

    async def process_message(self, message: Message) -> None:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK_CREATED.value:
            task_id = message.payload.get("task_id")
            if task_id:
                self._pending_tasks.append(task_id)
                self.log(f"New task received: #{task_id}")

        elif message.message_type == MessageType.TASK_SUBTASK_COMPLETE.value:
            task_id = message.payload.get("task_id")
            subtask_id = message.payload.get("subtask_id")
            output_data = message.payload.get("output_data", {})
            if task_id and subtask_id:
                await self._handle_subtask_complete(task_id, subtask_id, output_data)

        elif message.message_type == MessageType.TASK_FAILED.value:
            task_id = message.payload.get("task_id")
            error = message.payload.get("error", "Unknown error")
            if task_id:
                await self._handle_task_failure(task_id, error)

        elif message.message_type == MessageType.HEALTH_CHECK.value:
            await self.send_message(
                recipient_id=message.sender_id,
                message_type=MessageType.HEALTH_RESPONSE.value,
                payload=await self.health_check(),
            )

    async def create_task(self, title: str, description: Optional[str] = None) -> int:
        """Create a new task via API."""
        if not self._db:
            raise RuntimeError("No database connection")

        task = await self._db.create_task(title=title, description=description)
        self._pending_tasks.append(task.id)

        # Notify via message bus
        await self.send_message(
            recipient_id="broadcast",
            message_type=MessageType.TASK_CREATED.value,
            payload={"task_id": task.id, "title": title},
            priority="normal",
        )

        self.log(f"Task created: #{task.id} - {title}")
        return task.id

    async def _plan_and_execute_task(self, task_id: int) -> None:
        """Use Claude to decompose and plan task execution."""
        if not self._db:
            return

        task = await self._db.get_task(task_id)
        if not task:
            return

        self.status = AgentStatus.WORKING
        self.log(f"Planning task #{task_id}: {task.title}")

        await self._db.update_task(task_id, status=TaskStatus.PLANNING.value)

        try:
            # Use LLM to plan subtasks
            if self._llm and self._llm.is_available:
                plan = await self._llm.complete_structured(
                    prompt=f"Aufgabe: {task.title}\n\nBeschreibung: {task.description or task.title}\n\nZerlege diese Aufgabe in konkrete Subtasks fuer die verfuegbaren Agenten.",
                    system=TASK_PLANNER_SYSTEM,
                    response_schema=TASK_PLANNER_SCHEMA,
                    agent_id=self.agent_id,
                )
            else:
                # Fallback: simple heuristic planning
                plan = self._plan_without_llm(task.title, task.description or "")

            # Save plan
            await self._db.update_task(task_id, plan=plan)

            # Create subtasks in DB
            subtask_ids: list[int] = []
            for i, st in enumerate(plan.get("subtasks", [])):
                subtask = await self._db.create_subtask(
                    task_id=task_id,
                    title=st["title"],
                    description=st.get("description", ""),
                    assigned_agent=st.get("assigned_agent", ""),
                    sequence_order=st.get("sequence_order", i),
                    depends_on=st.get("depends_on"),
                    input_data=st.get("input_data"),
                )
                subtask_ids.append(subtask.id)

            # Update task status
            await self._db.update_task(
                task_id,
                status=TaskStatus.IN_PROGRESS.value,
            )

            # Track active task
            self._active_tasks[task_id] = {
                "subtask_ids": subtask_ids,
                "completed": [],
                "plan": plan,
            }

            # Dispatch first runnable subtasks
            await self._dispatch_ready_subtasks(task_id)

            self.log(f"Task #{task_id} planned with {len(subtask_ids)} subtasks")

            await self.send_message(
                recipient_id="broadcast",
                message_type=MessageType.TASK_PLAN_READY.value,
                payload={
                    "task_id": task_id,
                    "plan": plan,
                    "subtask_count": len(subtask_ids),
                },
            )

        except Exception as e:
            self.log(f"Failed to plan task #{task_id}: {e}", level="ERROR")
            await self._db.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                result_summary=f"Planning failed: {str(e)}",
            )

        self.status = AgentStatus.IDLE

    def _plan_without_llm(self, title: str, description: str) -> dict[str, Any]:
        """Heuristic task planning without LLM."""
        text = (title + " " + description).lower()
        subtasks: list[dict[str, Any]] = []

        if any(w in text for w in ["finde", "suche", "unternehmen", "firma", "prospect"]):
            subtasks.append({
                "title": "Unternehmen suchen",
                "description": f"Suche nach: {title}",
                "assigned_agent": "prospect_finder",
                "sequence_order": 0,
                "depends_on": [],
            })
            subtasks.append({
                "title": "Unternehmen recherchieren",
                "description": "Detailrecherche der gefundenen Unternehmen",
                "assigned_agent": "research_manager",
                "sequence_order": 1,
                "depends_on": [0],
            })

        if any(w in text for w in ["email", "anschreiben", "kontaktier"]):
            order = len(subtasks)
            deps = [order - 1] if subtasks else []
            subtasks.append({
                "title": "Emails schreiben",
                "description": "Personalisierte Emails verfassen",
                "assigned_agent": "email_writer",
                "sequence_order": order,
                "depends_on": deps,
            })
            subtasks.append({
                "title": "Qualitaetskontrolle",
                "description": "Emails pruefen und freigeben",
                "assigned_agent": "quality_control",
                "sequence_order": order + 1,
                "depends_on": [order],
            })

        if any(w in text for w in ["report", "bericht", "pipeline", "status"]):
            subtasks.append({
                "title": "Report erstellen",
                "description": "Pipeline-Report generieren",
                "assigned_agent": "deal_tracker",
                "sequence_order": len(subtasks),
                "depends_on": [],
            })

        if not subtasks:
            subtasks.append({
                "title": title,
                "description": description or title,
                "assigned_agent": "research_manager",
                "sequence_order": 0,
                "depends_on": [],
            })

        return {"subtasks": subtasks, "summary": f"Plan fuer: {title}"}

    async def _dispatch_ready_subtasks(self, task_id: int) -> None:
        """Dispatch subtasks whose dependencies are met."""
        if not self._db:
            return

        task_info = self._active_tasks.get(task_id, {})
        completed_orders = set()

        subtasks = await self._db.get_subtasks(task_id)

        # Build map of completed subtasks and their output_data
        completed_output: dict[int, dict[str, Any]] = {}
        for st in subtasks:
            if st.status == TaskStatus.COMPLETED.value:
                completed_orders.add(st.sequence_order)
                completed_output[st.sequence_order] = st.output_data or {}

        for st in subtasks:
            if st.status != TaskStatus.PENDING.value:
                continue

            deps = st.depends_on or []
            if all(d in completed_orders for d in deps):
                # Collect output_data from all completed dependencies
                input_data = st.input_data or {}
                for dep_order in deps:
                    dep_output = completed_output.get(dep_order, {})
                    if dep_output:
                        input_data.update(dep_output)

                # Dispatch this subtask
                await self._db.update_subtask(st.id, status=TaskStatus.IN_PROGRESS.value)

                agent_type = st.assigned_agent or ""
                await self.send_message(
                    recipient_id=agent_type,
                    message_type=MessageType.TASK_ASSIGNED.value,
                    payload={
                        "task_id": task_id,
                        "subtask_id": st.id,
                        "title": st.title,
                        "description": st.description,
                        "input_data": input_data,
                    },
                    priority="high",
                )
                self.log(f"Dispatched subtask #{st.id} to {agent_type}")

    async def _handle_subtask_complete(
        self, task_id: int, subtask_id: int, output_data: dict[str, Any]
    ) -> None:
        """Handle completion of a subtask."""
        if not self._db:
            return

        await self._db.update_subtask(
            subtask_id,
            status=TaskStatus.COMPLETED.value,
            output_data=output_data,
        )

        # Update progress
        subtasks = await self._db.get_subtasks(task_id)
        total = len(subtasks)
        completed = sum(1 for st in subtasks if st.status == TaskStatus.COMPLETED.value)
        progress = int((completed / total) * 100) if total > 0 else 0

        await self._db.update_task(task_id, progress_pct=progress)

        # Notify progress
        await self.send_message(
            recipient_id="broadcast",
            message_type=MessageType.TASK_PROGRESS.value,
            payload={
                "task_id": task_id,
                "progress_pct": progress,
                "completed": completed,
                "total": total,
            },
        )

        self.log(f"Task #{task_id} progress: {progress}% ({completed}/{total})")

        # Save result if provided
        if output_data:
            await self._db.create_task_result(
                task_id=task_id,
                result_type=output_data.get("type", "data"),
                title=output_data.get("title", f"Subtask #{subtask_id} Result"),
                data=output_data,
            )

        # Check if task is complete
        if completed == total:
            await self._complete_task(task_id)
        else:
            # Dispatch next ready subtasks
            await self._dispatch_ready_subtasks(task_id)

    async def _complete_task(self, task_id: int) -> None:
        """Mark a task as completed and compile results."""
        if not self._db:
            return

        results = await self._db.get_task_results(task_id)
        summary_parts: list[str] = []
        for r in results:
            if r.title:
                summary_parts.append(r.title)

        # Use LLM to create summary if available
        summary = "; ".join(summary_parts) if summary_parts else "Task abgeschlossen"

        if self._llm and self._llm.is_available and summary_parts:
            try:
                result_text = "\n".join(
                    f"- {r.title}: {str(r.data)[:200]}" for r in results
                )
                summary = await self._llm.complete_fast(
                    prompt=f"Fasse diese Ergebnisse kurz zusammen (1-2 Saetze, Deutsch):\n{result_text}",
                    agent_id=self.agent_id,
                )
            except Exception:
                pass

        await self._db.update_task(
            task_id,
            status=TaskStatus.COMPLETED.value,
            result_summary=summary,
            progress_pct=100,
            completed_at=datetime.now(),
        )

        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

        self.log(f"Task #{task_id} completed!")

        await self.send_message(
            recipient_id="broadcast",
            message_type=MessageType.TASK_COMPLETED.value,
            payload={"task_id": task_id, "summary": summary},
            priority="high",
        )

    async def _handle_task_failure(self, task_id: int, error: str) -> None:
        """Handle task failure."""
        if not self._db:
            return

        await self._db.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            result_summary=f"Fehler: {error}",
        )

        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

        self.log(f"Task #{task_id} failed: {error}", level="ERROR")

    async def _check_task_progress(self, task_id: int) -> None:
        """Check and update task progress."""
        if not self._db:
            return

        subtasks = await self._db.get_subtasks(task_id)
        total = len(subtasks)
        completed = sum(1 for st in subtasks if st.status == TaskStatus.COMPLETED.value)
        failed = sum(1 for st in subtasks if st.status == TaskStatus.FAILED.value)

        if failed > 0 and completed + failed == total:
            await self._handle_task_failure(task_id, f"{failed} subtask(s) failed")
