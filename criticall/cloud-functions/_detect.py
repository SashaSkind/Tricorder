"""
Fracture-detection tool -- the single seam between CritiCall and the model.

In production `MODEL_ENDPOINT` points at a GPU inference server (FastAPI +
PyTorch hosting the RSNA 2022 ensemble). The serverless EdgeOne runtime CANNOT
host a multi-GB GPU model itself, so the agent *calls* the model over HTTP.

For the hackathon build `MODEL_ENDPOINT` is unset, so we return the canned
same-schema output from _cases.py. Swapping stub -> real model is one env var;
nothing downstream (impression, paging, closed loop) changes.
"""

from __future__ import annotations

import os
import time

from _cases import get_case, CRITICAL_THRESHOLD

MODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT", "").strip()


def detect_fracture(study_uid: str) -> dict:
    """Run the cervical-spine fracture-detection model on a study.

    Returns the model's structured output plus a derived `critical` summary
    the workflow acts on.
    """
    started = time.time()

    if MODEL_ENDPOINT:
        # ── Real path: POST the study to the GPU inference server ──
        import httpx  # local import so the stub path has zero deps
        resp = httpx.post(
            f"{MODEL_ENDPOINT.rstrip('/')}/infer",
            json={"study_uid": study_uid},
            timeout=120.0,
        )
        resp.raise_for_status()
        detection = resp.json()
    else:
        # ── Hackathon path: canned real-schema output ──
        case = get_case(study_uid)
        if case is None:
            raise ValueError(f"Unknown study_uid: {study_uid}")
        detection = dict(case["detection"])

    return _summarize(detection, elapsed_ms=int((time.time() - started) * 1000))


def _summarize(detection: dict, elapsed_ms: int) -> dict:
    """Attach a `critical` verdict derived from the per-vertebra probabilities."""
    vertebrae = detection.get("vertebrae", [])
    top = max(vertebrae, key=lambda v: v["prob"], default=None)
    is_critical = bool(top) and top["prob"] >= CRITICAL_THRESHOLD

    detection["wall_ms"] = elapsed_ms
    detection["critical"] = {
        "is_critical": is_critical,
        "level": top["level"] if is_critical else None,
        "confidence": top["prob"] if is_critical else (top["prob"] if top else 0.0),
        "fracture_type": detection.get("fracture_type"),
        "key_slice": detection.get("key_slice"),
        "slice_range": detection.get("slice_range"),
        "threshold": CRITICAL_THRESHOLD,
    }
    return detection
