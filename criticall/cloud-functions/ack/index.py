"""
CritiCall acknowledgment webhook -- EdgeOne Makers Python cloud function.

POST /ack
  Body:    { study_uid, responder?, reply? }
  Returns: { acknowledged: true, ack: {...}, timeline: [...] }

This is the inbound side of the closed loop. In production this endpoint is the
webhook a texting provider (e.g. Twilio) POSTs to when the ER physician replies
"ACK" to the critical-finding SMS. In the demo the in-app phone panel calls it.
Either way it records a timestamped acknowledgment on the audit trail, closing
the ACR-mandated communication loop.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger              # noqa: E402
from _cases import get_case                    # noqa: E402
from _audit import record_event, get_timeline  # noqa: E402

logger = create_logger("ack")


def _read_body(rfile, headers) -> dict:
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


class handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = _read_body(self.rfile, self.headers)
        study_uid = str(body.get("study_uid") or "").strip()
        if not study_uid:
            self._write_json(400, {"error": "'study_uid' is required"})
            return

        case = get_case(study_uid)
        responder = str(body.get("responder") or "").strip()
        if not responder and case:
            responder = case["order"]["ordering_provider"]
        reply = str(body.get("reply") or "ACK").strip()

        try:
            store = self.context.agent.store
            existing = get_timeline(store, study_uid)
            paged = any(e.get("type") == "paged" for e in existing)
            already = next((e for e in existing if e.get("type") == "acknowledged"), None)

            if already:
                # Idempotent: don't double-record.
                self._write_json(200, {
                    "acknowledged": True,
                    "duplicate": True,
                    "ack": already,
                    "timeline": existing,
                })
                return

            ack = record_event(store, study_uid, {
                "type": "acknowledged",
                "responder": responder,
                "reply": reply,
                "channel": "sms",
            })
            timeline = get_timeline(store, study_uid)

            # Turnaround: seconds from page -> acknowledgment (the metric hospitals track).
            turnaround = _turnaround_seconds(timeline)

            logger.log(f"ack study={study_uid} responder={responder!r} paged={paged} "
                       f"turnaround={turnaround}s")
            self._write_json(200, {
                "acknowledged": True,
                "paged": paged,
                "ack": ack,
                "turnaround_seconds": turnaround,
                "timeline": timeline,
            })
        except Exception as e:
            logger.error(f"ack failed study={study_uid}: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            self._write_json(500, {"error": "ack failed", "detail": str(e)})


def _turnaround_seconds(timeline: list) -> int | None:
    paged = next((e for e in timeline if e.get("type") == "paged"), None)
    ack = next((e for e in timeline if e.get("type") == "acknowledged"), None)
    if not paged or not ack:
        return None
    try:
        t0 = datetime.fromisoformat(paged["ts"])
        t1 = datetime.fromisoformat(ack["ts"])
        return max(0, int((t1 - t0).total_seconds()))
    except (ValueError, KeyError, TypeError):
        return None
