"""
Closed-loop audit trail.

ACR requires that a critical finding is not just SENT but ACKNOWLEDGED, with a
timestamped record. We persist that trail in EdgeOne's memory store, keyed per
study, so /analyze (page) and /ack (acknowledge) share one durable timeline.

The store in cloud functions is synchronous (see cloud-functions/history/index.py).
Every call is defensively wrapped so an audit hiccup never breaks the workflow.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _conv_id(study_uid: str) -> str:
    return f"criticall::audit::{study_uid}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_event(store, study_uid: str, event: dict) -> dict:
    """Append one event to the study's audit trail. Returns the stored event."""
    event = {"ts": _now(), **event}
    try:
        store.append_message(_conv_id(study_uid), "assistant", json.dumps(event))
    except Exception:
        pass  # never let audit persistence break the clinical path
    return event


def get_timeline(store, study_uid: str) -> list[dict]:
    """Read the ordered audit trail for a study."""
    try:
        msgs = store.get_messages(conversation_id=_conv_id(study_uid), limit=100, order="asc") or []
    except Exception:
        return []
    out = []
    for m in msgs:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if not content:
            continue
        try:
            out.append(json.loads(content))
        except (ValueError, TypeError):
            continue
    return out
