"""
Sample cervical-spine CT studies for CritiCall.

Each case bundles the three things the closed-loop workflow needs:
  1. `detection`  -- what the fracture-detection model returns for this study.
                     Schema matches the RSNA 2022 Cervical Spine Fracture
                     Detection challenge: per-vertebra (C1-C7) probability +
                     an overall "patient_overall" probability, plus the slice
                     localization our pipeline adds on top.
  2. `order`      -- the imaging order / EHR metadata: who the patient is and,
                     critically, which ER physician ORDERED the scan (the person
                     CritiCall must reach and get an acknowledgment from).
  3. presentation -- patient demographics + indication shown on the dashboard.

This is the SAME shape a real model endpoint would emit, so cloud-functions/_detect.py
can swap this stub for a live GPU inference server by changing one env var.
"""

from __future__ import annotations

# C1-C7 is the label space of the RSNA challenge.
LEVELS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]

MODEL_NAME = "rsna2022-cspine-ensemble (1st place, Qishen Ha)"


def _vertebrae(probs: dict[str, float], flagged: str | None) -> list[dict]:
    """Build the per-vertebra probability list the model outputs."""
    return [
        {"level": lvl, "prob": round(probs.get(lvl, 0.03), 3), "flagged": lvl == flagged}
        for lvl in LEVELS
    ]


CASES: dict[str, dict] = {
    # ── Hero case: acute C2 fracture, high confidence -> pages ER ──
    "1.2.826.0.1.3680043.8.498.4471": {
        "study_uid": "1.2.826.0.1.3680043.8.498.4471",
        "accession": "CT-4471",
        "patient": {"name": "Robert Delgado", "age": 58, "sex": "M", "mrn": "MRN-4471882"},
        "indication": "High-speed MVC, neck pain, GCS 14. Rule out cervical spine fracture.",
        "acquired": "CT Cervical Spine w/o contrast · 220 axial slices · 0.6mm",
        "order": {
            "ordering_provider": "Dr. Marcus Chen",
            "role": "Emergency Medicine Attending",
            "phone": "+1 (415) 555-0142",
            "department": "Emergency Department",
            "pager": "ED-7781",
        },
        "detection": {
            "model": MODEL_NAME,
            "n_slices": 220,
            "patient_overall": 0.91,
            "vertebrae": _vertebrae(
                {"C1": 0.08, "C2": 0.87, "C3": 0.05, "C4": 0.03, "C5": 0.04, "C6": 0.03, "C7": 0.02},
                flagged="C2",
            ),
            "flagged_level": "C2",
            "fracture_type": "Type II odontoid fracture (dens)",
            "key_slice": 142,
            "slice_range": [136, 149],
            "inference_ms": 1840,
        },
    },
    # ── Alt case: C6 burst fracture ──
    "1.2.826.0.1.3680043.8.498.8823": {
        "study_uid": "1.2.826.0.1.3680043.8.498.8823",
        "accession": "CT-8823",
        "patient": {"name": "Alicia Fenn", "age": 34, "sex": "F", "mrn": "MRN-8823017"},
        "indication": "Fall from height ~4m, midline tenderness, arm paresthesia.",
        "acquired": "CT Cervical Spine w/o contrast · 240 axial slices · 0.6mm",
        "order": {
            "ordering_provider": "Dr. Priya Nair",
            "role": "Emergency Medicine Attending",
            "phone": "+1 (415) 555-0198",
            "department": "Emergency Department",
            "pager": "ED-7742",
        },
        "detection": {
            "model": MODEL_NAME,
            "n_slices": 240,
            "patient_overall": 0.83,
            "vertebrae": _vertebrae(
                {"C1": 0.02, "C2": 0.04, "C3": 0.05, "C4": 0.07, "C5": 0.11, "C6": 0.79, "C7": 0.14},
                flagged="C6",
            ),
            "flagged_level": "C6",
            "fracture_type": "C6 burst fracture with retropulsion",
            "key_slice": 168,
            "slice_range": [160, 175],
            "inference_ms": 2010,
        },
    },
    # ── Negative case: no fracture -> agent correctly does NOT page (no alert fatigue) ──
    "1.2.826.0.1.3680043.8.498.2290": {
        "study_uid": "1.2.826.0.1.3680043.8.498.2290",
        "accession": "CT-2290",
        "patient": {"name": "James Okoro", "age": 45, "sex": "M", "mrn": "MRN-2290551"},
        "indication": "Low-speed rear-end collision, mild neck stiffness, neuro intact.",
        "acquired": "CT Cervical Spine w/o contrast · 210 axial slices · 0.6mm",
        "order": {
            "ordering_provider": "Dr. Sofia Reyes",
            "role": "Emergency Medicine Attending",
            "phone": "+1 (415) 555-0176",
            "department": "Emergency Department",
            "pager": "ED-7719",
        },
        "detection": {
            "model": MODEL_NAME,
            "n_slices": 210,
            "patient_overall": 0.06,
            "vertebrae": _vertebrae(
                {"C1": 0.02, "C2": 0.03, "C3": 0.04, "C4": 0.03, "C5": 0.05, "C6": 0.04, "C7": 0.03},
                flagged=None,
            ),
            "flagged_level": None,
            "fracture_type": None,
            "key_slice": None,
            "slice_range": None,
            "inference_ms": 1770,
        },
    },
}

# Threshold above which a per-vertebra probability is treated as a positive
# finding that must be communicated to the ordering physician.
CRITICAL_THRESHOLD = 0.5


def list_cases() -> list[dict]:
    """Lightweight list for the study worklist on the dashboard."""
    out = []
    for c in CASES.values():
        det = c["detection"]
        out.append({
            "study_uid": c["study_uid"],
            "accession": c["accession"],
            "patient": c["patient"],
            "indication": c["indication"],
            "acquired": c["acquired"],
            "n_slices": det["n_slices"],
            "expected_positive": det["patient_overall"] >= CRITICAL_THRESHOLD,
        })
    return out


def get_case(study_uid: str) -> dict | None:
    return CASES.get(study_uid)
