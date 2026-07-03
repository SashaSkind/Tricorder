"""
Plain-English critical impression generator.

Takes the model's structured finding and produces the 2-3 sentence, ER-facing
message a busy attending can read in three seconds -- the "tell the doctor in
plain text what it could be" step.

Uses the EdgeOne AI Gateway (OpenAI-compatible Chat Completions) when
AI_GATEWAY_API_KEY is configured; otherwise falls back to a strong clinical
template so the demo NEVER breaks.
"""

from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_KEY = os.getenv("AI_GATEWAY_API_KEY", "").strip()
BASE_URL = os.getenv("AI_GATEWAY_BASE_URL", "https://ai-gateway.edgeone.link/v1").strip()
MODEL = os.getenv("AI_GATEWAY_MODEL", "@makers/deepseek-v4-flash").strip()

SYSTEM = (
    "You are a radiology critical-results assistant. Given a cervical-spine CT "
    "AI finding, write a SINGLE concise alert (2-3 sentences, <60 words) for the "
    "ordering ER physician. Plain clinical English, no markdown. State the level, "
    "suspected fracture, confidence, and the key axial slice. End with one "
    "recommended immediate action. Do not hedge with disclaimers."
)


def generate_impression(case: dict, detection: dict) -> dict:
    """Return {'impression': str, 'source': 'llm'|'template'}."""
    crit = detection["critical"]
    template = _template(case, detection)

    if not API_KEY:
        return {"impression": template, "source": "template"}

    try:
        import httpx
        prompt = {
            "patient": case["patient"],
            "indication": case["indication"],
            "level": crit["level"],
            "fracture_type": crit["fracture_type"],
            "confidence": crit["confidence"],
            "key_slice": crit["key_slice"],
            "slice_range": crit["slice_range"],
            "total_slices": detection["n_slices"],
        }
        resp = httpx.post(
            f"{BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                "temperature": 0.2,
                "stream": False,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        if text:
            return {"impression": text, "source": "llm"}
    except Exception:
        pass

    return {"impression": template, "source": "template"}


def _template(case: dict, detection: dict) -> str:
    """Deterministic clinical fallback -- always safe to show."""
    crit = detection["critical"]
    p = case["patient"]
    pct = round(crit["confidence"] * 100)
    return (
        f"CRITICAL: AI-flagged {crit['fracture_type']} at {crit['level']} in "
        f"{p['age']}{p['sex']} ({p['name']}), {pct}% confidence, best seen on axial "
        f"slice {crit['key_slice']} of {detection['n_slices']}. "
        f"Recommend cervical immobilization and immediate neurosurgery consult; "
        f"confirm on dedicated review before clearing the collar."
    )
