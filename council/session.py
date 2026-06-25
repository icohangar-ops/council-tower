"""Mutable deliberation session shared across Data Agent tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from council.models import Post, RoomStatus


@dataclass
class DeliberationSession:
    """Accumulates council state while the Data Agent orchestrates tools."""

    topic: str
    domain: str
    context: str = ""
    posts: list[Post] = field(default_factory=list)
    analysis_records: list[tuple[str, str, str]] = field(default_factory=list)
    challenge_content: str = ""
    final_summary: str = ""
    summary_confidence: float = 0.0
    phases_completed: set[str] = field(default_factory=set)
    deliberation_id: str = ""
    stored: bool = False
    storage_info: dict = field(default_factory=dict)
    tool_trace: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def phases_remaining(self) -> list[str]:
        order = ["ANALYSIS", "CHALLENGE", "VALIDATION", "LOCK", "SUMMARY"]
        return [phase for phase in order if phase not in self.phases_completed]

    def is_complete(self) -> bool:
        required = {"ANALYSIS", "CHALLENGE", "VALIDATION", "LOCK", "SUMMARY"}
        return required.issubset(self.phases_completed)
