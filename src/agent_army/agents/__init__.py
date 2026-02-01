"""Agent implementations for the Agent Army system."""

from .prospect_finder import ProspectFinderAgent
from .research_manager import ResearchManagerAgent
from .email_writer import EmailWriterAgent
from .quality_control import QualityControlAgent
from .email_sender import EmailSenderAgent
from .response_monitor import ResponseMonitorAgent
from .response_writer import ResponseWriterAgent
from .deal_tracker import DealTrackerAgent

__all__ = [
    "ProspectFinderAgent",
    "ResearchManagerAgent",
    "EmailWriterAgent",
    "QualityControlAgent",
    "EmailSenderAgent",
    "ResponseMonitorAgent",
    "ResponseWriterAgent",
    "DealTrackerAgent",
]
