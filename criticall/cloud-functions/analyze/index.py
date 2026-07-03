"""
CritiCall analyze handler -- EdgeOne Makers Python cloud function.

POST /analyze
  Body:    { study_uid }
  Returns: full pipeline result -- detection + plain-English impression +
           ordering ER physician + the paging alert (or a "no critical finding"
           result when the study is negative, so we don't page needlessly).

Pipeline:
  study_uid -> detect_fracture() -> generate_impression() -> page ordering ER doc
            -> record "paged" event on the closed-loop audit trail.
"""

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger      # noqa: E402
from _cases import get_case            # noqa: E402
from _detect import detect_fracture    # noqa: E402
from _impression import generate_impression  # noqa: E402
from _audit import record_event, get_timeline  # noqa: E402
from _sms import send_sms, target_number, sms_configured  # noqa: E402

logger = create_logger("analyze")


def _read_body(rfile, headers) -> dict:
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


def run_pipeline(store, study_uid: str, base_url: str = "") -> dict:
    """Pure pipeline -- returns the analyze payload for a study."""
    case = get_case(study_uid)
    if case is None:
        return {"error": f"Unknown study_uid: {study_uid}"}

    detection = detect_fracture(study_uid)
    crit = detection["critical"]

    result = {
        "study_uid": study_uid,
        "accession": case["accession"],
        "patient": case["patient"],
        "indication": case["indication"],
        "acquired": case["acquired"],
        "order": case["order"],
        "detection": detection,
        "critical": crit,
    }

    if not crit["is_critical"]:
        # Negative study: agent explicitly does NOT page (specificity / no alert fatigue).
        result["paged"] = False
        result["impression"] = (
            f"No cervical-spine fracture detected (overall {round(detection['patient_overall']*100)}% "
            f"below {round(crit['threshold']*100)}% threshold). Routine reporting; ordering "
            f"physician not paged."
        )
        result["impression_source"] = "template"
        record_event(store, study_uid, {
            "type": "screened_negative",
            "overall": detection["patient_overall"],
        })
        result["timeline"] = get_timeline(store, study_uid)
        return result

    # Positive study: generate the impression and page the ordering ER physician.
    imp = generate_impression(case, detection)
    result["impression"] = imp["impression"]
    result["impression_source"] = imp["source"]

    provider = case["order"]["ordering_provider"]
    # Tap-to-ACK magic link -> closes the loop without any Twilio inbound config.
    ack_link = ""
    if base_url:
        ack_link = f"{base_url}/ack?study={quote(study_uid)}&r={quote(provider)}"

    sms_body = (
        f"🚨 CRITICAL RESULT (Tricorder)\n{imp['impression']}"
        + (f"\n\nReply ACK or tap to acknowledge: {ack_link}" if ack_link else "\n\nReply ACK to acknowledge.")
    )

    # Real outbound SMS if Twilio is configured; else the in-app phone panel shows it.
    delivery = send_sms(case["order"]["phone"], sms_body)

    alert = {
        "to": provider,
        "to_phone": target_number(case["order"]["phone"]),
        "level": crit["level"],
        "fracture_type": crit["fracture_type"],
        "confidence": crit["confidence"],
        "key_slice": crit["key_slice"],
        "body": imp["impression"],
        "ack_link": ack_link,
    }
    result["paged"] = True
    result["alert"] = alert
    result["sms"] = {"channel": "twilio" if sms_configured() else "in-app", **delivery}

    record_event(store, study_uid, {
        "type": "paged",
        "to": provider,
        "to_phone": alert["to_phone"],
        "level": crit["level"],
        "confidence": crit["confidence"],
        "channel": "sms",
        "sms_sent": bool(delivery.get("sent")),
        "sms_sid": delivery.get("sid"),
    })
    result["timeline"] = get_timeline(store, study_uid)
    return result


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
        # Derive the public base URL for the tap-to-ACK link from the request.
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        proto = self.headers.get("X-Forwarded-Proto") or ("http" if host.startswith("localhost") else "https")
        base_url = os.getenv("PUBLIC_BASE_URL", "").strip() or (f"{proto}://{host}" if host else "")

        try:
            store = self.context.agent.store
            result = run_pipeline(store, study_uid, base_url=base_url)
            status = 404 if result.get("error") else 200
            logger.log(f"analyze study={study_uid} paged={result.get('paged')} "
                       f"source={result.get('impression_source')}")
            self._write_json(status, result)
        except Exception as e:
            logger.error(f"analyze failed study={study_uid}: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            self._write_json(500, {"error": "analyze failed", "detail": str(e)})
