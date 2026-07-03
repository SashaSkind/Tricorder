"""
Tricorder acknowledgment webhook -- EdgeOne Makers Python cloud function.

The inbound side of the closed loop. Three entry paths, all landing on the same
_acknowledge():
  1. POST JSON            -- the in-app phone panel  { study_uid, responder?, reply? }
  2. GET  ?study=&r=      -- the tap-to-ACK magic link inside the SMS (returns a
                             friendly HTML page for the phone)
  3. POST form-encoded    -- a REAL Twilio inbound "reply ACK" webhook (Body, From);
                             we map the sender to their open page and reply TwiML

Either way it records a timestamped acknowledgment, closing the ACR-mandated
communication loop.
"""

import json
import os
import sys
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger              # noqa: E402
from _cases import get_case, CASES             # noqa: E402
from _audit import record_event, get_timeline  # noqa: E402

logger = create_logger("ack")


def _turnaround_seconds(timeline: list):
    paged = next((e for e in timeline if e.get("type") == "paged"), None)
    ack = next((e for e in timeline if e.get("type") == "acknowledged"), None)
    if not paged or not ack:
        return None
    try:
        return max(0, int((datetime.fromisoformat(ack["ts"]) - datetime.fromisoformat(paged["ts"])).total_seconds()))
    except (ValueError, KeyError, TypeError):
        return None


def _acknowledge(store, study_uid: str, responder: str, reply: str) -> dict:
    """Idempotently record an acknowledgment and return the closed-loop payload."""
    existing = get_timeline(store, study_uid)
    already = next((e for e in existing if e.get("type") == "acknowledged"), None)
    if already:
        return {"acknowledged": True, "duplicate": True, "ack": already,
                "turnaround_seconds": _turnaround_seconds(existing), "timeline": existing}

    record_event(store, study_uid, {"type": "acknowledged", "responder": responder,
                                    "reply": reply, "channel": "sms"})
    timeline = get_timeline(store, study_uid)
    return {"acknowledged": True, "ack": timeline[-1], "paged": any(e.get("type") == "paged" for e in existing),
            "turnaround_seconds": _turnaround_seconds(timeline), "timeline": timeline}


def _find_open_study(store, from_number: str):
    """Map an inbound SMS sender to their most recent paged-but-unacked study."""
    from _sms import target_number
    best = None
    for uid, case in CASES.items():
        tl = get_timeline(store, uid)
        paged = any(e.get("type") == "paged" for e in tl)
        acked = any(e.get("type") == "acknowledged" for e in tl)
        if not paged or acked:
            continue
        # Match the number we paged (demo override aware); fall back to most recent.
        if from_number and target_number(case["order"]["phone"]) not in (from_number, ""):
            continue
        ts = next((e["ts"] for e in tl if e.get("type") == "paged"), "")
        if best is None or ts > best[1]:
            best = (uid, ts)
    return best[0] if best else None


class handler(BaseHTTPRequestHandler):
    # ── shared writers ──
    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _twiml(self, message: str):
        xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'
        body = xml.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── GET: tap-to-ACK magic link from the SMS ──
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        study_uid = (q.get("study") or [""])[0].strip()
        responder = (q.get("r") or [""])[0].strip()
        if not study_uid or not get_case(study_uid):
            self._html("<h2>Invalid or expired acknowledgment link.</h2>", 400)
            return
        case = get_case(study_uid)
        if not responder:
            responder = case["order"]["ordering_provider"]
        try:
            res = _acknowledge(self.context.agent.store, study_uid, responder, "ACK (tap)")
            ta = res.get("turnaround_seconds")
            self._html(_ack_page(case, ta))
        except Exception as e:
            logger.error(f"ack GET failed: {e}\n{traceback.format_exc()}")
            self._html("<h2>Could not record acknowledgment.</h2>", 500)

    # ── POST: in-app JSON, or real Twilio inbound form ──
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "ignore") if length > 0 else ""
        ctype = (self.headers.get("Content-Type") or "").lower()

        try:
            store = self.context.agent.store

            if "application/x-www-form-urlencoded" in ctype:
                # Real Twilio inbound reply
                form = {k: v[0] for k, v in parse_qs(raw).items()}
                from_number = form.get("From", "").strip()
                body_txt = form.get("Body", "").strip()
                if "ACK" not in body_txt.upper():
                    self._twiml("Reply ACK to acknowledge this critical result.")
                    return
                study_uid = _find_open_study(store, from_number)
                if not study_uid:
                    self._twiml("No open critical result found for this number.")
                    return
                case = get_case(study_uid)
                _acknowledge(store, study_uid, case["order"]["ordering_provider"], body_txt)
                self._twiml(f"✓ Acknowledged {case['accession']}. Logged for the radiologist. Thank you.")
                return

            # In-app JSON path
            data = json.loads(raw) if raw else {}
            study_uid = str(data.get("study_uid") or "").strip()
            if not study_uid:
                self._json(400, {"error": "'study_uid' is required"})
                return
            case = get_case(study_uid)
            responder = str(data.get("responder") or (case["order"]["ordering_provider"] if case else "")).strip()
            res = _acknowledge(store, study_uid, responder, str(data.get("reply") or "ACK"))
            logger.log(f"ack study={study_uid} responder={responder!r} turnaround={res.get('turnaround_seconds')}s")
            self._json(200, res)
        except Exception as e:
            logger.error(f"ack POST failed: {e}\n{traceback.format_exc()}")
            self._json(500, {"error": "ack failed", "detail": str(e)})


def _ack_page(case: dict, turnaround) -> str:
    ta = f"{turnaround}s after page" if turnaround is not None else "logged"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acknowledged</title></head>
<body style="margin:0;font-family:-apple-system,sans-serif;background:#0a0e14;color:#e6edf6;
display:grid;place-items:center;height:100vh;text-align:center">
<div style="padding:30px">
<div style="font-size:56px">✓</div>
<h1 style="color:#45d483;margin:10px 0">Critical result acknowledged</h1>
<p style="color:#8697ad">{case['accession']} · {case['patient']['name']}</p>
<p style="color:#5f7089;font-family:monospace;font-size:13px">Loop closed ({ta}) · documented for ACR compliance</p>
</div></body></html>"""
