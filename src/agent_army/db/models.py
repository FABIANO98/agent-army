"""SQLAlchemy models for the Agent Army database."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class ProspectStatus(str, Enum):
    """Status of a prospect in the pipeline."""

    NEW = "new"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"
    UNSUBSCRIBED = "unsubscribed"


class DealStage(str, Enum):
    """Stages of a deal in the pipeline."""

    COLD_PROSPECT = "cold_prospect"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    MEETING_SCHEDULED = "meeting_scheduled"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class ResponseCategory(str, Enum):
    """Categories for email responses."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    QUESTION = "question"
    OUT_OF_OFFICE = "out_of_office"


class EmailStatus(str, Enum):
    """Status of an email."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    SENT = "sent"
    BOUNCED = "bounced"
    DELIVERED = "delivered"


class Prospect(Base):
    """
    Represents a potential customer/lead.

    Contains basic company information found during prospecting.
    """

    __tablename__ = "prospects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    size: Mapped[Optional[str]] = mapped_column(String(50))  # small, medium, large
    region: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), default=ProspectStatus.NEW.value, index=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100))  # how we found them
    found_date: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )
    last_contacted: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    profile: Mapped[Optional["CompanyProfile"]] = relationship(
        "CompanyProfile", back_populates="prospect", uselist=False
    )
    emails: Mapped[list["Email"]] = relationship("Email", back_populates="prospect")
    deal: Mapped[Optional["Deal"]] = relationship(
        "Deal", back_populates="prospect", uselist=False
    )

    # Indexes created via column index=True for compatibility

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "industry": self.industry,
            "size": self.size,
            "region": self.region,
            "email": self.email,
            "status": self.status,
            "found_date": self.found_date.isoformat() if self.found_date else None,
        }


class CompanyProfile(Base):
    """
    Detailed research profile for a prospect.

    Contains in-depth information gathered during research phase.
    """

    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prospects.id"), unique=True, index=True
    )
    ceo_name: Mapped[Optional[str]] = mapped_column(String(255))
    ceo_email: Mapped[Optional[str]] = mapped_column(String(255))
    ceo_linkedin: Mapped[Optional[str]] = mapped_column(String(500))
    employees_count: Mapped[Optional[int]] = mapped_column(Integer)
    website_problems: Mapped[Optional[list[str]]] = mapped_column(JSON)
    website_tech_stack: Mapped[Optional[list[str]]] = mapped_column(JSON)
    social_media: Mapped[Optional[dict[str, str]]] = mapped_column(JSON)
    budget_estimate: Mapped[Optional[str]] = mapped_column(String(50))
    buying_signals: Mapped[Optional[list[str]]] = mapped_column(JSON)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)  # 1-10 hotness
    pain_points: Mapped[Optional[list[str]]] = mapped_column(JSON)
    research_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    researched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationship
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="profile")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "prospect_id": self.prospect_id,
            "ceo_name": self.ceo_name,
            "ceo_email": self.ceo_email,
            "employees_count": self.employees_count,
            "website_problems": self.website_problems,
            "budget_estimate": self.budget_estimate,
            "buying_signals": self.buying_signals,
            "sentiment_score": self.sentiment_score,
            "pain_points": self.pain_points,
        }


class Email(Base):
    """
    Email sent to or received from a prospect.

    Tracks the full lifecycle of email communication.
    """

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prospects.id"), index=True
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    email_type: Mapped[str] = mapped_column(
        String(50), default="cold_outreach"
    )  # cold_outreach, follow_up, response
    status: Mapped[str] = mapped_column(
        String(50), default=EmailStatus.DRAFT.value, index=True
    )
    personalization_score: Mapped[Optional[float]] = mapped_column(Float)
    spam_score: Mapped[Optional[float]] = mapped_column(Float)
    quality_feedback: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    opened: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    bounced: Mapped[bool] = mapped_column(Boolean, default=False)
    bounce_reason: Mapped[Optional[str]] = mapped_column(String(255))
    tracking_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="emails")
    responses: Mapped[list["Response"]] = relationship(
        "Response", back_populates="email"
    )

    # Indexes created via column index=True for compatibility

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "prospect_id": self.prospect_id,
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "opened": self.opened,
            "clicked": self.clicked,
        }


class Response(Base):
    """
    Response received to an email.

    Contains analysis of the response sentiment and content.
    """

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emails.id"), index=True
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    sentiment: Mapped[Optional[str]] = mapped_column(String(50))  # positive, negative, neutral
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    category: Mapped[str] = mapped_column(
        String(50), default=ResponseCategory.NEUTRAL.value, index=True
    )
    extracted_info: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    meeting_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    meeting_time_suggested: Mapped[Optional[datetime]] = mapped_column(DateTime)
    budget_mentioned: Mapped[Optional[str]] = mapped_column(String(100))
    needs_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationship
    email: Mapped["Email"] = relationship("Email", back_populates="responses")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "email_id": self.email_id,
            "response_text": self.response_text[:200] + "..." if len(self.response_text) > 200 else self.response_text,
            "sentiment": self.sentiment,
            "category": self.category,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "meeting_requested": self.meeting_requested,
        }


class Deal(Base):
    """
    Deal/opportunity associated with a prospect.

    Tracks the sales pipeline progression.
    """

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prospects.id"), unique=True, index=True
    )
    stage: Mapped[str] = mapped_column(
        String(50), default=DealStage.COLD_PROSPECT.value, index=True
    )
    value: Mapped[Optional[float]] = mapped_column(Float)  # Estimated deal value in CHF
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    probability: Mapped[Optional[float]] = mapped_column(Float)  # Win probability %
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    actual_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    lost_reason: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationship
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="deal")

    # Indexes created via column index=True for compatibility

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "prospect_id": self.prospect_id,
            "stage": self.stage,
            "value": self.value,
            "probability": self.probability,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }


class TaskStatus(str, Enum):
    """Status of a task."""

    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """User-created task that gets decomposed into subtasks."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), default=TaskStatus.PENDING.value, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=5)
    plan: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    subtasks: Mapped[list["Subtask"]] = relationship("Subtask", back_populates="task")
    results: Mapped[list["TaskResult"]] = relationship("TaskResult", back_populates="task")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "plan": self.plan,
            "result_summary": self.result_summary,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Subtask(Base):
    """A subtask assigned to a specific agent."""

    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    assigned_agent: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(50), default=TaskStatus.PENDING.value, index=True
    )
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    depends_on: Mapped[Optional[list[int]]] = mapped_column(JSON)
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    task: Mapped["Task"] = relationship("Task", back_populates="subtasks")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "sequence_order": self.sequence_order,
            "depends_on": self.depends_on,
            "input_data": self.input_data,
            "output_data": self.output_data,
        }


class TaskResult(Base):
    """Structured result from a completed task."""

    __tablename__ = "task_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), index=True)
    result_type: Mapped[str] = mapped_column(String(100), default="text")
    title: Mapped[Optional[str]] = mapped_column(String(500))
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="results")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "result_type": self.result_type,
            "title": self.title,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentCommunication(Base):
    """Logged inter-agent communication."""

    __tablename__ = "agent_communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_agent: Mapped[str] = mapped_column(String(100), index=True)
    receiver_agent: Mapped[str] = mapped_column(String(100))
    message_type: Mapped[str] = mapped_column(String(100))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender_agent": self.sender_agent,
            "receiver_agent": self.receiver_agent,
            "message_type": self.message_type,
            "summary": self.summary,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class AgentLog(Base):
    """
    Log entries from agents.

    Stores detailed activity logs for debugging and analytics.
    """

    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(100), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    # Indexes created via column index=True for compatibility

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "level": self.level,
            "message": self.message,
        }
