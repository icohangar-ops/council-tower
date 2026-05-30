"""Data models for the Council deliberation engine."""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json


class Phase(str, Enum):
    ANALYSIS = "ANALYSIS"
    CHALLENGE = "CHALLENGE"
    VALIDATION = "VALIDATION"
    LOCK = "LOCK"
    SUMMARY = "SUMMARY"


class LockState(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    LOCKED = "LOCKED"


class RoomStatus(str, Enum):
    EXPLORING = "EXPLORING"
    PROVISIONAL = "PROVISIONAL"
    CHALLENGED = "CHALLENGED"
    VALIDATED = "VALIDATED"
    LOCKED = "LOCKED"
    FAILED = "FAILED"


class Domain(str, Enum):
    FINANCE = "finance"
    STRATEGY = "strategy"
    GENERAL = "general"


@dataclass
class AgentConfig:
    """Configuration for a council agent."""
    role: str
    name: str
    system_prompt: str


@dataclass
class Post:
    """A single deliberation post by an agent."""
    agent_id: str
    agent_name: str
    role: str
    content: str
    phase: Phase
    lock_state: LockState = LockState.PROVISIONAL
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DeliberationResult:
    """Complete result of a council deliberation."""
    topic: str
    domain: str
    status: RoomStatus
    posts: list[Post] = field(default_factory=list)
    final_summary: str = ""
    quality_score: float = 0.0
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "topic": self.topic,
            "domain": self.domain,
            "status": self.status.value,
            "posts": [
                {
                    "agent_id": p.agent_id,
                    "agent_name": p.agent_name,
                    "role": p.role,
                    "content": p.content,
                    "phase": p.phase.value,
                    "lock_state": p.lock_state.value,
                    "confidence": p.confidence,
                    "created_at": p.created_at.isoformat(),
                }
                for p in self.posts
            ],
            "final_summary": self.final_summary,
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
