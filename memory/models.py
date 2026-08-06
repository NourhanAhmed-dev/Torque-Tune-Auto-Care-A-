from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MemoryItem:
    """
    Base memory object used throughout the memory system.
    """

    memory_id: str
    content: str
    memory_type: str  # e.g. conversation, preference, reminder

    importance: int = 1

    client_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    tech_id: Optional[int] = None
    appointment_id: Optional[int] = None

    created_at: datetime = field(default_factory=datetime.utcnow)

    metadata: dict = field(default_factory=dict)


@dataclass
class EpisodicMemory(MemoryItem):
    """
    Memory promoted from short-term storage.
    """
    promoted_from: str = "short_term"


@dataclass
class SemanticMemory:
    """
    Long-term factual memory.
    """

    fact_id: str
    fact: str
    category: str

    version: int = 1
    active: bool = True

    expires_at: Optional[datetime] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    source_episode: Optional[str] = None

    client_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    tech_id: Optional[int] = None