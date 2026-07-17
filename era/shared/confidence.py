"""
Single source of truth for evidence/recommendation confidence ranking.

Previously this table and the effective_confidence() function were
copy-pasted independently in:
  - era/evidence_reliability.py      (was MISSING the "SUPPORTED" label)
  - era/sensitivity/contribution_analyzer.py
  - era/recommendation/recommendation_evaluator.py

Because evidence_reliability.py's copy silently mapped an unrecognized
label to rank 0 (UNSUPPORTED) via dict.get(item, 0), the same input could
produce different confidence output depending on which copy of the
function ran. All three modules now import from here instead.

Note: era/calibration_engine.py's STATUS_ORDER is a *different* concept
(a weight-calibration state ladder: PLACEHOLDER -> ESTIMATED -> VALIDATED
-> VERIFIED) and intentionally does not include SUPPORTED/PARTIAL/DRAFT/
UNSUPPORTED, which aren't valid calibration states. It is left untouched.
"""

CONFIDENCE_ORDER = {
    "UNSUPPORTED": 0,
    "PLACEHOLDER": 1,
    "DRAFT": 1,
    "ESTIMATED": 2,
    "PARTIAL": 2,
    "VALIDATED": 3,
    "VERIFIED": 4,
    "SUPPORTED": 4,
}


def effective_confidence(*labels: str) -> str:
    """Return the weakest (lowest-ranked) confidence label among the inputs.

    Unrecognized labels rank as UNSUPPORTED (0), same as no labels at all.
    """
    if not labels:
        return "UNSUPPORTED"
    normalized = [str(label).upper() for label in labels]
    return min(normalized, key=lambda item: CONFIDENCE_ORDER.get(item, 0))
