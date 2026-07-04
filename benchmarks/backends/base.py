"""Memory backend protocol for benchmark runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class RetrieveResult:
    session_ids: List[str]
    context_text: str
    latency_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryBackend(Protocol):
    name: str

    def reset(self, instance_id: str) -> None:
        ...

    def insert_session(
        self,
        instance_id: str,
        session_id: str,
        turns: List[Dict[str, Any]],
        session_date: Optional[str] = None,
        prior_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        ...

    def retrieve(
        self,
        instance_id: str,
        query: str,
        as_of: Optional[datetime] = None,
        top_k: int = 20,
    ) -> RetrieveResult:
        ...
