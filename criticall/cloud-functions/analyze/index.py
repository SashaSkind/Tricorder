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

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger      # noqa: E402
from _cases import get_case            # noqa: E402
from _detect import detect_fracture    # noqa: E402
from _impression import generate_impression  # noqa: E402
from _audit import record_event, get_timeline  # noqa: E402

logger = create_logger("analyze")


def _read_body(rfile, headers) -> dict:
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


def run_pipeline(store, study_uid: str) -> dict:
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

    alert = {
        "to": case["order"]["ordering_provider"],
        "to_phone": case["order"]["phone"],
        "level": crit["level"],
        "fracture_type": crit["fracture_type"],
        "confidence": crit["confidence"],
        "key_slice": crit["key_slice"],
        "body": imp["impression"],
    }
    result["paged"] = True
    result["alert"] = alert

    record_event(store, study_uid, {
        "type": "paged",
        "to": alert["to"],
        "to_phone": alert["to_phone"],
        "level": crit["level"],
        "confidence": crit["confidence"],
        "channel": "sms",
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
        try:
            store = self.context.agent.store
            result = run_pipeline(store, study_uid)
            status = 404 if result.get("error") else 200
            logger.log(f"analyze study={study_uid} paged={result.get('paged')} "
                       f"source={result.get('impression_source')}")
            self._write_json(status, result)
        except Exception as e:
            logger.error(f"analyze failed study={study_uid}: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            self._write_json(500, {"error": "analyze failed", "detail": str(e)})
