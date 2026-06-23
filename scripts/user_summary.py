"""
User narrative-summary helpers.

These were originally part of scripts/memory_pipeline.py. After the migration to
the Zep-style Entity-Relation-Fact graph, only the summary-generation helpers
remain here so the rest of the old pipeline can be removed.
"""
import os
from typing import Any, Dict, List

import litellm

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def _user_summary_key(person_id: str) -> str:
    return f"user_summary:{person_id}"


def invalidate_user_summary(redis_client, person_id: str) -> None:
    """Invalidate the cached user summary when memory changes."""
    try:
        redis_client.delete(_user_summary_key(person_id))
    except Exception:
        pass


def generate_user_summary(records: List[Dict[str, Any]], llm_fn=None) -> str:
    """Generate a narrative user summary from memory records.

    llm_fn: optional callable with signature llm_fn(messages, temperature, **kw).
            Falls back to litellm.completion with the default model.
    """
    if not records:
        return ""

    fact_lines = []
    for rec in records:
        labels = rec.get("labels", [])
        label = labels[0] if labels else "Memory"
        key = rec.get("key", "")
        value = rec.get("value", "")
        if key and value and key != value:
            fact_lines.append(f"- {label}: {key} = {value}")
        elif value:
            fact_lines.append(f"- {label}: {value}")
        elif key:
            fact_lines.append(f"- {label}: {key}")

    if not fact_lines:
        return ""

    memory_text = "\n".join(fact_lines)
    prompt = (
        "Write a concise 2-3 sentence summary of who this person is. "
        "Capture their identity, values, current focus, and any defining goals. "
        "Write in the third person. Do not list facts verbatim; synthesize them into a narrative.\n\n"
        "Stored facts:\n" + memory_text + "\n\nSummary:"
    )

    try:
        if llm_fn is not None:
            completion = llm_fn(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=200)
        else:
            model_name = os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")
            completion = litellm.completion(model=model_name, messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=200)
        summary = completion.choices[0].message.content.strip()
        summary = summary.strip('"').strip("'")
        return summary
    except Exception:
        return ""


def get_user_summary(redis_client, person_id: str, records: List[Dict[str, Any]], llm_fn=None) -> str:
    """Return cached user summary or generate and cache a new one."""
    try:
        cached = redis_client.get(_user_summary_key(person_id))
        if cached:
            return cached
    except Exception:
        pass

    summary = generate_user_summary(records, llm_fn=llm_fn)
    if summary:
        try:
            redis_client.set(_user_summary_key(person_id), summary, ex=3600)
        except Exception:
            pass
    return summary


# Old episode-state Redis keys (kept for backwards compatibility with /clear-history).
def _keywords_key(person_id: str) -> str:
    return f"last_keywords:{person_id}"


def _episode_key(person_id: str) -> str:
    return f"current_episode_id:{person_id}"


def clear_episode_state(redis_client, person_id: str) -> None:
    """Clear cached keywords and episode_id so the next turn starts fresh."""
    try:
        redis_client.delete(_keywords_key(person_id))
        redis_client.delete(_episode_key(person_id))
    except Exception:
        pass
