"""LongMemEval dataset loading and helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_longmemeval(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def is_abstention(item: Dict[str, Any]) -> bool:
    question_id = str(item.get("question_id") or "")
    return question_id.endswith("_abs")


def parse_question_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # LongMemEval format: "2023/05/30 (Tue) 23:40"
    match = re.match(
        r"^(\d{4})/(\d{2})/(\d{2})\s+\([^)]+\)\s+(\d{2}):(\d{2})$",
        text,
    )
    if match:
        y, mo, d, h, mi = map(int, match.groups())
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
    return None


def session_transcript(turns: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for turn in turns:
        role = str(turn.get("role", "user")).capitalize()
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def truncate_text(text: str, max_chars: int) -> str:
    """Keep head+tail when truncating long plain text."""
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head - 40
    if tail < 0:
        return text[:max_chars]
    return f"{text[:head]}\n\n[... truncated ...]\n\n{text[-tail:]}"


def truncate_session_transcript(turns: List[Dict[str, Any]], max_chars: int) -> str:
    """Build a session transcript, always keeping full user turns.

    LongMemEval answer sessions often bury the key fact in a mid-session user
    turn while assistant replies dominate character count. Head/tail truncation
    drops those facts; user turns are preserved and assistant turns fill the
    remaining budget in order.
    """
    if max_chars <= 0:
        return session_transcript(turns)

    lines: List[str] = []
    size = 0
    for turn in turns:
        role = str(turn.get("role", "user")).capitalize()
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        line = f"{role}: {content}"
        sep = 1 if lines else 0
        is_user = role.lower() == "user"

        if is_user:
            lines.append(line)
            size += sep + len(line)
            continue

        if size + sep + len(line) <= max_chars:
            lines.append(line)
            size += sep + len(line)
            continue

        remaining = max_chars - size - sep
        if remaining > 80:
            lines.append(line[: remaining - 3] + "...")
        break

    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    return truncate_text(text, max_chars)


def iter_sessions(item: Dict[str, Any]):
    session_ids = item.get("haystack_session_ids") or []
    session_dates = item.get("haystack_dates") or []
    sessions = item.get("haystack_sessions") or []
    for idx, turns in enumerate(sessions):
        session_id = session_ids[idx] if idx < len(session_ids) else f"session-{idx}"
        session_date = session_dates[idx] if idx < len(session_dates) else None
        yield session_id, turns, session_date
