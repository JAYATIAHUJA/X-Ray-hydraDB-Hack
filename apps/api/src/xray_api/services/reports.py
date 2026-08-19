from __future__ import annotations

from collections.abc import Mapping, Sequence

from xray_core.models import CanonicalBundle


def render_risk_report(
    bundle: CanonicalBundle,
    snapshot_id: str,
    *,
    ghosts: Sequence[Mapping[str, object]],
    faultlines: Sequence[Mapping[str, object]],
    gaps: Sequence[Mapping[str, object]],
) -> str:
    """Render enriched findings as a portable, evidence-aware Markdown report."""
    lines = [
        f"# X-Ray Risk Report: {bundle.dataset_id}",
        "",
        "Structural position, not performance. Absence in the corpus does not establish deletion.",
        f"Snapshot: `{snapshot_id}` · {len(bundle.evidence)} evidence records.",
        "",
        "## Ghost",
    ]
    if ghosts:
        ghost = ghosts[0]
        lines.extend(
            [
                f"- **{ghost['display_name']}**: structural rank #{ghost['structural_rank']}, formal rank #{ghost['formal_rank']}, rank gap {ghost['rank_gap']}.",
                f"  - Method: `{ghost['centrality_method']}`; communication degree {ghost['communication_degree']}.",
                "  - Action: review team-level handoff and backup coverage; do not interpret this rank as individual performance.",
                *_evidence_lines(ghost.get("evidence")),
            ]
        )
    else:
        lines.append("- No Ghost finding available.")
    lines.extend(["", "## Faultlines"])
    for finding in faultlines:
        lines.extend(
            [
                f"- `{finding['source_module_key']}` -> `{finding['target_module_key']}`; owners `{finding['source_owner_key']}` / `{finding['target_owner_key']}`; tier `{finding['tier']}`, severity {finding['severity']}.",
                f"  - Ownership evidence shares: {finding['source_owner_confidence']}% / {finding['target_owner_confidence']}%; dependency weight {finding['dependency_weight']}.",
                "  - Action: validate ownership with the team, then create or confirm a coordination path between module maintainers.",
                *_evidence_lines(finding.get("evidence")),
            ]
        )
    lines.extend(["", "## Gaps"])
    for finding in gaps:
        lines.extend(
            [
                f"- `{finding['phantom_key']}` ({finding['expected_kind']}, {finding['reason']}); absence does not establish deletion.",
                f"  - Window position: `{finding['window_position']}`; inferred epoch {finding['inferred_epoch']}.",
                "  - Action: ask the record owner whether the expected step exists outside this export before treating it as a process gap.",
                *_evidence_lines(finding.get("evidence")),
            ]
        )
    lines.extend(["", "## Limitations", *[f"- {item}" for item in bundle.limitations]])
    return "\n".join(lines) + "\n"


def _evidence_lines(records: object) -> list[str]:
    if not isinstance(records, (list, tuple)) or not records:
        return ["  - Evidence: none attached; treat this finding as unsupported."]
    lines = []
    for record in records:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("evidence_id", "unknown"))
        content_sha256 = str(record.get("content_sha256", "unknown"))
        confidence = record.get("confidence", "unknown")
        lines.append(
            f"  - Evidence: `{evidence_id}` · SHA-256 `{content_sha256}` · record confidence {confidence}%."
        )
    return lines or ["  - Evidence: none attached; treat this finding as unsupported."]


__all__ = ["render_risk_report"]
