"""Question verdicts — SourceTruce-style gate, reimplemented for X-Ray answers.

Order: unresolved conflict → DISPUTED; answered → SUPPORTED; not_found → NOT_FOUND;
otherwise UNKNOWN (including unsupported / incomplete abstention).

Inspired by danielAsaboro/sourcetruce (MIT); see ATTRIBUTION.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from xray_analytics.questions import EvidenceDecision, OntologyAnswer

Verdict = Literal["SUPPORTED", "DISPUTED", "NOT_FOUND", "UNKNOWN"]


def decide_question_verdict(
    answer: OntologyAnswer,
    *,
    conflicts: Sequence[EvidenceDecision] | None = None,
) -> Verdict:
    """Map an ontology answer (+ conflicts) to a single display verdict."""
    rows = tuple(conflicts if conflicts is not None else answer.conflicts)
    if rows:
        selected = sum(1 for row in rows if row.selected)
        rejected = sum(1 for row in rows if not row.selected)
        # Competing claims with no trusted winner.
        if selected == 0 and rejected >= 2:
            return "DISPUTED"
        # Competing claims still open (multiple selected / ambiguous).
        if selected > 1 and rejected == 0 and answer.status != "answered":
            return "DISPUTED"

    if answer.status == "answered":
        return "SUPPORTED"
    if answer.status == "not_found":
        return "NOT_FOUND"
    if answer.status in {"no_answer", "unsupported"} or answer.answer_kind in {
        "abstention",
        "unsupported",
    }:
        return "UNKNOWN"
    return "UNKNOWN"


__all__ = ["Verdict", "decide_question_verdict"]
