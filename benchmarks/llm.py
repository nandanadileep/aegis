"""LiteLLM helpers for benchmark extraction, reading, and judging."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import litellm
from litellm.exceptions import (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
)

_RETRY_AFTER_RE = re.compile(r"try again in (\d+(?:\.\d+)?)s", re.I)
_MAX_RETRIES = int(os.getenv("BENCH_LLM_MAX_RETRIES", "12"))
_TRANSIENT_ERRORS = (
    RateLimitError,
    InternalServerError,
    APIConnectionError,
    ServiceUnavailableError,
)


def _sleep_for_retry(exc: Exception, attempt: int) -> None:
    if isinstance(exc, RateLimitError):
        msg = str(exc)
        match = _RETRY_AFTER_RE.search(msg)
        if match:
            wait_s = float(match.group(1)) + 0.5
        else:
            wait_s = min(60.0, 3.0 * (2 ** attempt))
        print(f"[bench] rate limited, sleeping {wait_s:.1f}s (attempt {attempt + 1})", flush=True)
    else:
        wait_s = min(30.0, 2.0 * (2 ** attempt))
        print(f"[bench] transient LLM error, sleeping {wait_s:.1f}s (attempt {attempt + 1})", flush=True)
    time.sleep(wait_s)


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, _TRANSIENT_ERRORS):
        return True
    msg = str(exc).lower()
    return "connection reset" in msg or "timeout" in msg or "temporarily unavailable" in msg


def _is_non_retryable_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "request too large" in msg or "reduce your message size" in msg


def _completion_with_retry(**kwargs):
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            return litellm.completion(**kwargs)
        except Exception as exc:
            last_exc = exc
            if _is_non_retryable_llm_error(exc) or not _is_transient_error(exc):
                break
            if attempt + 1 >= _MAX_RETRIES:
                break
            _sleep_for_retry(exc, attempt)
    assert last_exc is not None
    raise last_exc


def bench_completion(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    resp = _completion_with_retry(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def bench_llm_fn(model: str):
    """Adapter matching graph_memory llm_fn signature."""
    def _call(messages, temperature=0.0, max_tokens=None, **kwargs):
        kw = dict(kwargs)
        if max_tokens is not None:
            kw["max_tokens"] = max_tokens
        try:
            return _completion_with_retry(
                model=model,
                messages=messages,
                temperature=temperature,
                **kw,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Benchmark LLM call failed for model {model!r} after retries. "
                f"Re-run to resume from checkpoint. Original error: {exc}"
            ) from exc
    return _call


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    return json.loads(text)


def judge_answer(
    question: str,
    gold_answer: str,
    hypothesis: str,
    model: Optional[str] = None,
) -> bool:
    """LLM-as-judge aligned with LongMemEval QA evaluation."""
    judge_model = model or os.getenv("BENCH_JUDGE_MODEL", "anthropic/claude-3-5-sonnet-latest")
    prompt = f"""You are evaluating whether a chat assistant's answer is correct.

Question:
{question}

Gold answer:
{gold_answer}

Assistant answer:
{hypothesis}

Return ONLY JSON:
{{"label": "correct"}} if the assistant answer is correct or equivalent to the gold answer.
{{"label": "incorrect"}} otherwise.
"""
    raw = bench_completion(judge_model, [{"role": "user", "content": prompt}], temperature=0.0)
    try:
        parsed = _extract_json_object(raw)
        return str(parsed.get("label", "")).lower() == "correct"
    except Exception:
        return False
