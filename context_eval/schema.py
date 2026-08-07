from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class TurnType(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUMMARY = "summary"


@dataclass
class Message:
    turn_id: int
    role: TurnType
    content: str
    seq: int = 0
    tool_name: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pinned: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def is_tool_output(self) -> bool:
        return self.role == TurnType.TOOL_RESULT or "tool_name" in self.metadata


Transcript = List[Message]

_ROLE_MAP = {t.value: t for t in TurnType}
_ROLE_MAP["tool"] = TurnType.TOOL_RESULT   


def from_buffer(msgs: list[dict]) -> Transcript:
    """Adapter: ShortTermMemory.get_messages() -> Transcript."""
    out: Transcript = []
    turn = -1
    for i, m in enumerate(msgs):
        if m["role"] == "user":
            turn += 1
        meta = m.get("metadata") or {}
        out.append(Message(
            turn_id=max(turn, 0),
            role=_ROLE_MAP.get(m["role"], TurnType.USER),
            content=m["content"],
            seq=i,
            tool_name=meta.get("tool_name"),
            pinned=(m["role"] == "system"),
            metadata=meta,
        ))
    return out