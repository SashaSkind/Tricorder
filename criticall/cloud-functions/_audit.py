"""
Closed-loop audit trail.

ACR requires that a critical finding is not just SENT but ACKNOWLEDGED, with a
timestamped record. We persist that trail so /analyze (page) and /ack
(acknowledge) share one timeline per study.

Two layers, merged on read so the demo is bulletproof:
  1. EdgeOne memory store  -- durable, cross-instance. Its methods may be async
     while cloud-function handlers are sync, so we await them defensively.
  2. In-process mirror     -- a module-level dict that always works within a
     warm worker (dev + warm serverless), covering any store hiccup.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger("audit")

# In-process mirror: study_uid -> list[event]
_MIRROR: dict[str, list[dict]] = {}


def _conv_id(study_uid: str) -> str:
    return f"tricorder::audit::{study_uid}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(value):
    """Resolve a possibly-awaitable store result from a sync handler."""
    if inspect.isawaitable(value):
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(value)
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            log.error("audit await failed: %s: %s", type(e).__name__, e)
            return None
    return value


def record_event(store, study_uid: str, event: dict) -> dict:
    """Append one event to the study's audit trail (mirror + durable store)."""
    event = {"ts": _now(), **event}
    _MIRROR.setdefault(study_uid, []).append(event)
    try:
        _run(store.append_message(_conv_id(study_uid), "assistant", json.dumps(event)))
    except Exception as e:  # noqa: BLE001
        log.error("audit append failed: %s: %s", type(e).__name__, e)
    return event


def get_timeline(store, study_uid: str) -> list[dict]:
    """Return the ordered audit trail, merging durable store + in-process mirror."""
    events: list[dict] = []

    try:
        msgs = _run(store.get_messages(conversation_id=_conv_id(study_uid), limit=100, order="asc")) or []
        for m in msgs:
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
            if not content:
                continue
            try:
                events.append(json.loads(content))
            except (ValueError, TypeError):
                continue
    except Exception as e:  # noqa: BLE001
        log.error("audit read failed: %s: %s", type(e).__name__, e)

    events.extend(_MIRROR.get(study_uid, []))

    # De-dupe (store + mirror can overlap) and order by timestamp.
    seen, merged = set(), []
    for e in events:
        key = (e.get("type"), e.get("ts"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda e: e.get("ts", ""))
    return merged
