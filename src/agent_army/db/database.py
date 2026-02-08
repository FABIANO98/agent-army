"""Database handler for the Agent Army system."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Optional, Sequence

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import (
    AgentCommunication,
    AgentLog,
    Base,
    CompanyProfile,
    Deal,
    DealStage,
    Email,
    EmailStatus,
    Prospect,
    ProspectStatus,
    Response,
    ResponseCategory,
    Subtask,
    Task,
    TaskResult,
    TaskStatus,
)


class Database:
    """
    Async database handler with SQLAlchemy.

    Provides high-level operations for all database entities.
    """

    def __init__(self, database_url: str, echo: bool = False) -> None:
        """
        Initialize the database handler.

        Args:
            database_url: SQLAlchemy database URL
            echo: Whether to echo SQL statements
        """
        self._engine = create_async_engine(database_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._logger = logger.bind(component="Database")

    async def init_db(self, drop_existing: bool = False) -> None:
        """Initialize the database schema."""
        async with self._engine.begin() as conn:
            if drop_existing:
                await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        self._logger.info("Database initialized")

    async def close(self) -> None:
        """Close the database connection."""
        await self._engine.dispose()
        self._logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session.

        Yields:
            AsyncSession instance
        """
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ==================== Prospect Operations ====================

    async def create_prospect(
        self,
        name: str,
        url: Optional[str] = None,
        industry: Optional[str] = None,
        size: Optional[str] = None,
        region: Optional[str] = None,
        email: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Prospect:
        """Create a new prospect."""
        async with self.session() as session:
            prospect = Prospect(
                name=name,
                url=url,
                industry=industry,
                size=size,
                region=region,
                email=email,
                source=source,
            )
            session.add(prospect)
            await session.flush()
            return prospect

    async def get_prospect(self, prospect_id: int) -> Optional[Prospect]:
        """Get a prospect by ID."""
        async with self.session() as session:
            result = await session.execute(
                select(Prospect).where(Prospect.id == prospect_id)
            )
            return result.scalar_one_or_none()

    async def get_prospects_by_status(
        self, status: ProspectStatus, limit: int = 100
    ) -> Sequence[Prospect]:
        """Get prospects by status."""
        async with self.session() as session:
            result = await session.execute(
                select(Prospect)
                .where(Prospect.status == status.value)
                .order_by(Prospect.found_date.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def get_new_prospects(self, limit: int = 20) -> Sequence[Prospect]:
        """Get new prospects that need research."""
        return await self.get_prospects_by_status(ProspectStatus.NEW, limit)

    async def get_researched_prospects(self, limit: int = 10) -> Sequence[Prospect]:
        """Get researched prospects ready for outreach."""
        return await self.get_prospects_by_status(ProspectStatus.RESEARCHED, limit)

    async def update_prospect_status(
        self, prospect_id: int, status: ProspectStatus
    ) -> None:
        """Update prospect status."""
        async with self.session() as session:
            result = await session.execute(
                select(Prospect).where(Prospect.id == prospect_id)
            )
            prospect = result.scalar_one_or_none()
            if prospect:
                prospect.status = status.value
                prospect.updated_at = datetime.now()

    async def prospect_exists(self, url: str) -> bool:
        """Check if a prospect with this URL already exists."""
        async with self.session() as session:
            result = await session.execute(
                select(func.count()).select_from(Prospect).where(Prospect.url == url)
            )
            return result.scalar() > 0  # type: ignore

    async def get_today_prospect_count(self) -> int:
        """Get count of prospects found today."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Prospect)
                .where(Prospect.found_date >= today_start)
            )
            return result.scalar() or 0

    # ==================== Company Profile Operations ====================

    async def create_company_profile(
        self, prospect_id: int, **kwargs: Any
    ) -> CompanyProfile:
        """Create a company profile for a prospect."""
        async with self.session() as session:
            profile = CompanyProfile(prospect_id=prospect_id, **kwargs)
            session.add(profile)
            await session.flush()

            # Update prospect status
            result = await session.execute(
                select(Prospect).where(Prospect.id == prospect_id)
            )
            prospect = result.scalar_one_or_none()
            if prospect:
                prospect.status = ProspectStatus.RESEARCHED.value

            return profile

    async def get_company_profile(self, prospect_id: int) -> Optional[CompanyProfile]:
        """Get company profile for a prospect."""
        async with self.session() as session:
            result = await session.execute(
                select(CompanyProfile).where(
                    CompanyProfile.prospect_id == prospect_id
                )
            )
            return result.scalar_one_or_none()

    async def get_hot_profiles(
        self, min_score: float = 7.0, limit: int = 5
    ) -> Sequence[CompanyProfile]:
        """Get profiles with high sentiment scores."""
        async with self.session() as session:
            result = await session.execute(
                select(CompanyProfile)
                .where(CompanyProfile.sentiment_score >= min_score)
                .order_by(CompanyProfile.sentiment_score.desc())
                .limit(limit)
            )
            return result.scalars().all()

    # ==================== Email Operations ====================

    async def create_email(
        self,
        prospect_id: int,
        subject: str,
        body: str,
        email_type: str = "cold_outreach",
    ) -> Email:
        """Create an email draft."""
        async with self.session() as session:
            email = Email(
                prospect_id=prospect_id,
                subject=subject,
                body=body,
                email_type=email_type,
                status=EmailStatus.DRAFT.value,
            )
            session.add(email)
            await session.flush()
            return email

    async def get_email(self, email_id: int) -> Optional[Email]:
        """Get an email by ID."""
        async with self.session() as session:
            result = await session.execute(
                select(Email).where(Email.id == email_id)
            )
            return result.scalar_one_or_none()

    async def get_pending_emails(self, limit: int = 10) -> Sequence[Email]:
        """Get emails pending review."""
        async with self.session() as session:
            result = await session.execute(
                select(Email)
                .where(Email.status == EmailStatus.PENDING_REVIEW.value)
                .order_by(Email.created_at)
                .limit(limit)
            )
            return result.scalars().all()

    async def get_approved_emails(self, limit: int = 10) -> Sequence[Email]:
        """Get emails approved for sending."""
        async with self.session() as session:
            result = await session.execute(
                select(Email)
                .where(Email.status == EmailStatus.APPROVED.value)
                .order_by(Email.created_at)
                .limit(limit)
            )
            return result.scalars().all()

    async def update_email_status(
        self,
        email_id: int,
        status: EmailStatus,
        **kwargs: Any,
    ) -> None:
        """Update email status and optional fields."""
        async with self.session() as session:
            result = await session.execute(
                select(Email).where(Email.id == email_id)
            )
            email = result.scalar_one_or_none()
            if email:
                email.status = status.value
                for key, value in kwargs.items():
                    if hasattr(email, key):
                        setattr(email, key, value)

    async def get_today_sent_count(self) -> int:
        """Get count of emails sent today."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Email)
                .where(
                    Email.status == EmailStatus.SENT.value,
                    Email.sent_at >= today_start,
                )
            )
            return result.scalar() or 0

    async def get_emails_needing_followup(self, days: int = 3) -> Sequence[Email]:
        """Get sent emails that need follow-up."""
        cutoff = datetime.now() - timedelta(days=days)
        async with self.session() as session:
            # Get sent emails with no response after X days
            result = await session.execute(
                select(Email)
                .where(
                    Email.status == EmailStatus.SENT.value,
                    Email.sent_at <= cutoff,
                    Email.email_type == "cold_outreach",
                )
                .order_by(Email.sent_at)
            )
            return result.scalars().all()

    # ==================== Response Operations ====================

    async def create_response(
        self,
        email_id: int,
        response_text: str,
        subject: Optional[str] = None,
        **kwargs: Any,
    ) -> Response:
        """Create a response record."""
        async with self.session() as session:
            response = Response(
                email_id=email_id,
                response_text=response_text,
                subject=subject,
                **kwargs,
            )
            session.add(response)
            await session.flush()
            return response

    async def get_unprocessed_responses(self, limit: int = 10) -> Sequence[Response]:
        """Get responses that need reply."""
        async with self.session() as session:
            result = await session.execute(
                select(Response)
                .where(Response.needs_reply == True, Response.replied_at == None)  # noqa: E712
                .order_by(Response.received_at)
                .limit(limit)
            )
            return result.scalars().all()

    async def get_positive_responses(self, limit: int = 10) -> Sequence[Response]:
        """Get positive responses."""
        async with self.session() as session:
            result = await session.execute(
                select(Response)
                .where(Response.category == ResponseCategory.POSITIVE.value)
                .order_by(Response.received_at.desc())
                .limit(limit)
            )
            return result.scalars().all()

    # ==================== Deal Operations ====================

    async def create_deal(
        self,
        prospect_id: int,
        stage: DealStage = DealStage.COLD_PROSPECT,
        value: Optional[float] = None,
    ) -> Deal:
        """Create a deal for a prospect."""
        async with self.session() as session:
            deal = Deal(
                prospect_id=prospect_id,
                stage=stage.value,
                value=value,
            )
            session.add(deal)
            await session.flush()
            return deal

    async def get_deal(self, deal_id: int) -> Optional[Deal]:
        """Get a deal by ID."""
        async with self.session() as session:
            result = await session.execute(
                select(Deal).where(Deal.id == deal_id)
            )
            return result.scalar_one_or_none()

    async def get_deal_by_prospect(self, prospect_id: int) -> Optional[Deal]:
        """Get deal for a prospect."""
        async with self.session() as session:
            result = await session.execute(
                select(Deal).where(Deal.prospect_id == prospect_id)
            )
            return result.scalar_one_or_none()

    async def update_deal_stage(
        self, deal_id: int, stage: DealStage, **kwargs: Any
    ) -> None:
        """Update deal stage."""
        async with self.session() as session:
            result = await session.execute(
                select(Deal).where(Deal.id == deal_id)
            )
            deal = result.scalar_one_or_none()
            if deal:
                deal.stage = stage.value
                deal.last_activity = datetime.now()
                for key, value in kwargs.items():
                    if hasattr(deal, key):
                        setattr(deal, key, value)

    async def get_deals_by_stage(
        self, stage: DealStage, limit: int = 100
    ) -> Sequence[Deal]:
        """Get deals by stage."""
        async with self.session() as session:
            result = await session.execute(
                select(Deal)
                .where(Deal.stage == stage.value)
                .order_by(Deal.last_activity.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def get_stale_deals(self, days: int = 7) -> Sequence[Deal]:
        """Get deals with no activity for X days."""
        cutoff = datetime.now() - timedelta(days=days)
        async with self.session() as session:
            result = await session.execute(
                select(Deal)
                .where(
                    Deal.last_activity <= cutoff,
                    Deal.stage.not_in([DealStage.WON.value, DealStage.LOST.value]),
                )
                .order_by(Deal.last_activity)
            )
            return result.scalars().all()

    async def get_pipeline_stats(self) -> dict[str, Any]:
        """Get pipeline statistics."""
        async with self.session() as session:
            stats: dict[str, Any] = {"stages": {}}

            for stage in DealStage:
                result = await session.execute(
                    select(func.count(), func.sum(Deal.value))
                    .select_from(Deal)
                    .where(Deal.stage == stage.value)
                )
                row = result.one()
                stats["stages"][stage.value] = {
                    "count": row[0] or 0,
                    "value": row[1] or 0,
                }

            # Total stats
            result = await session.execute(
                select(func.count(), func.sum(Deal.value)).select_from(Deal)
            )
            row = result.one()
            stats["total"] = {"count": row[0] or 0, "value": row[1] or 0}

            return stats

    # ==================== Agent Log Operations ====================

    async def log_agent_activity(
        self,
        agent_id: str,
        agent_name: str,
        message: str,
        level: str = "INFO",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log agent activity."""
        async with self.session() as session:
            log = AgentLog(
                agent_id=agent_id,
                agent_name=agent_name,
                message=message,
                level=level,
                context=context,
            )
            session.add(log)

    async def get_agent_logs(
        self,
        agent_id: Optional[str] = None,
        level: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> Sequence[AgentLog]:
        """Get agent logs with filters."""
        async with self.session() as session:
            query = select(AgentLog)

            if agent_id:
                query = query.where(AgentLog.agent_id == agent_id)
            if level:
                query = query.where(AgentLog.level == level)
            if since:
                query = query.where(AgentLog.timestamp >= since)

            query = query.order_by(AgentLog.timestamp.desc()).limit(limit)

            result = await session.execute(query)
            return result.scalars().all()

    # ==================== Reports ====================

    async def get_daily_report(self) -> dict[str, Any]:
        """Generate daily activity report."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        async with self.session() as session:
            # Prospects found today
            prospects_result = await session.execute(
                select(func.count())
                .select_from(Prospect)
                .where(Prospect.found_date >= today_start)
            )

            # Emails sent today
            emails_result = await session.execute(
                select(func.count())
                .select_from(Email)
                .where(
                    Email.sent_at >= today_start,
                    Email.status == EmailStatus.SENT.value,
                )
            )

            # Responses received today
            responses_result = await session.execute(
                select(func.count())
                .select_from(Response)
                .where(Response.received_at >= today_start)
            )

            # Positive responses today
            positive_result = await session.execute(
                select(func.count())
                .select_from(Response)
                .where(
                    Response.received_at >= today_start,
                    Response.category == ResponseCategory.POSITIVE.value,
                )
            )

            pipeline = await self.get_pipeline_stats()

            return {
                "date": today_start.date().isoformat(),
                "prospects_found": prospects_result.scalar() or 0,
                "emails_sent": emails_result.scalar() or 0,
                "responses_received": responses_result.scalar() or 0,
                "positive_responses": positive_result.scalar() or 0,
                "pipeline": pipeline,
            }

    # ==================== Task Operations ====================

    async def create_task(
        self, title: str, description: Optional[str] = None, priority: int = 5
    ) -> Task:
        """Create a new task."""
        async with self.session() as session:
            task = Task(title=title, description=description, priority=priority)
            session.add(task)
            await session.flush()
            return task

    async def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID with subtasks and results."""
        async with self.session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            return result.scalar_one_or_none()

    async def update_task(self, task_id: int, **kwargs: Any) -> Optional[Task]:
        """Update a task's fields."""
        async with self.session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                for key, value in kwargs.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                task.updated_at = datetime.now()
            return task

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Task]:
        """List tasks with optional status filter."""
        async with self.session() as session:
            query = select(Task)
            if status:
                query = query.where(Task.status == status)
            query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(query)
            return result.scalars().all()

    async def create_subtask(
        self,
        task_id: int,
        title: str,
        description: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        sequence_order: int = 0,
        depends_on: Optional[list[int]] = None,
        input_data: Optional[dict[str, Any]] = None,
    ) -> Subtask:
        """Create a subtask for a task."""
        async with self.session() as session:
            subtask = Subtask(
                task_id=task_id,
                title=title,
                description=description,
                assigned_agent=assigned_agent,
                sequence_order=sequence_order,
                depends_on=depends_on,
                input_data=input_data,
            )
            session.add(subtask)
            await session.flush()
            return subtask

    async def update_subtask(self, subtask_id: int, **kwargs: Any) -> Optional[Subtask]:
        """Update a subtask."""
        async with self.session() as session:
            result = await session.execute(select(Subtask).where(Subtask.id == subtask_id))
            subtask = result.scalar_one_or_none()
            if subtask:
                for key, value in kwargs.items():
                    if hasattr(subtask, key):
                        setattr(subtask, key, value)
            return subtask

    async def get_subtasks(self, task_id: int) -> Sequence[Subtask]:
        """Get all subtasks for a task."""
        async with self.session() as session:
            result = await session.execute(
                select(Subtask)
                .where(Subtask.task_id == task_id)
                .order_by(Subtask.sequence_order)
            )
            return result.scalars().all()

    async def create_task_result(
        self,
        task_id: int,
        result_type: str = "text",
        title: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> TaskResult:
        """Create a result entry for a task."""
        async with self.session() as session:
            task_result = TaskResult(
                task_id=task_id,
                result_type=result_type,
                title=title,
                data=data,
            )
            session.add(task_result)
            await session.flush()
            return task_result

    async def get_task_results(self, task_id: int) -> Sequence[TaskResult]:
        """Get all results for a task."""
        async with self.session() as session:
            result = await session.execute(
                select(TaskResult).where(TaskResult.task_id == task_id)
            )
            return result.scalars().all()

    async def log_agent_communication(
        self,
        sender_agent: str,
        receiver_agent: str,
        message_type: str,
        summary: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> None:
        """Log an agent communication event."""
        async with self.session() as session:
            comm = AgentCommunication(
                sender_agent=sender_agent,
                receiver_agent=receiver_agent,
                message_type=message_type,
                summary=summary,
                task_id=task_id,
            )
            session.add(comm)

    async def get_communications(
        self, limit: int = 100, task_id: Optional[int] = None
    ) -> Sequence[AgentCommunication]:
        """Get agent communications."""
        async with self.session() as session:
            query = select(AgentCommunication)
            if task_id:
                query = query.where(AgentCommunication.task_id == task_id)
            query = query.order_by(AgentCommunication.timestamp.desc()).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """Get aggregated dashboard statistics."""
        async with self.session() as session:
            # Active tasks
            active_tasks = await session.execute(
                select(func.count())
                .select_from(Task)
                .where(Task.status.in_([TaskStatus.IN_PROGRESS.value, TaskStatus.PLANNING.value]))
            )

            # Total tasks
            total_tasks = await session.execute(
                select(func.count()).select_from(Task)
            )

            # Pipeline value
            pipeline_value = await session.execute(
                select(func.sum(Deal.value))
                .select_from(Deal)
                .where(Deal.stage.not_in([DealStage.LOST.value, DealStage.WON.value]))
            )

            # Emails sent today
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            emails_today = await session.execute(
                select(func.count())
                .select_from(Email)
                .where(Email.sent_at >= today_start, Email.status == EmailStatus.SENT.value)
            )

            # Total prospects
            total_prospects = await session.execute(
                select(func.count()).select_from(Prospect)
            )

            # Prospects found today
            prospects_today = await session.execute(
                select(func.count())
                .select_from(Prospect)
                .where(Prospect.found_date >= today_start)
            )

            return {
                "active_tasks": active_tasks.scalar() or 0,
                "total_tasks": total_tasks.scalar() or 0,
                "pipeline_value": pipeline_value.scalar() or 0,
                "emails_today": emails_today.scalar() or 0,
                "total_prospects": total_prospects.scalar() or 0,
                "prospects_today": prospects_today.scalar() or 0,
            }
