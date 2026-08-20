from __future__ import annotations

import re
from dataclasses import dataclass

from xray_core.models import CanonicalBundle, EdgeRow, EvidenceRecord, NodeRow


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    person_key: str
    source_type: str
    source_record_id: str
    authority: str
    observed_epoch: int
    valid_from_epoch: int | None
    valid_until_epoch: int | None
    confidence: int
    selected: bool
    reason: str


@dataclass(frozen=True, slots=True)
class OntologyAnswer:
    question: str
    intent: str
    status: str
    answer: str
    subject_key: str | None
    person_keys: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    paths: tuple[tuple[str, ...], ...]
    confidence: int | None
    answer_kind: str
    reasoning: tuple[str, ...]
    limitations: tuple[str, ...]
    conflicts: tuple[EvidenceDecision, ...] = ()
    trust_explanation: str | None = None


_QUESTION_PATTERNS = (
    (
        "dependency_impact",
        re.compile(
            r"^(?:which|what)\s+(?:teams|services|modules)\s+(?:are\s+)?(?:affected|impacted)\s+if\s+(.+?)\s+changes\??$",
            re.I,
        ),
    ),
    ("approval", re.compile(r"^who\s+approved\s+(.+?)\??$", re.I)),
    (
        "owner",
        re.compile(
            r"^who\s+(?:owns|is responsible for)\s+(.+?)\s+now(?:,?\s+and\s+why\s+did\s+.+)?\??$",
            re.I,
        ),
    ),
    ("owner", re.compile(r"^who\s+(?:owns|is responsible for)\s+(.+?)\??$", re.I)),
    ("author", re.compile(r"^who\s+(?:authored|wrote|created)\s+(.+?)\??$", re.I)),
    ("reviewer", re.compile(r"^who\s+(?:reviewed|replied to)\s+(.+?)\??$", re.I)),
)


def answer_ontology_question(bundle: CanonicalBundle, question: str) -> OntologyAnswer:
    normalized = " ".join(question.strip().split())
    for intent, pattern in _QUESTION_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match is not None:
            if intent == "dependency_impact":
                return _answer_dependency_impact(bundle, normalized, match.group(1))
            if intent == "approval":
                return _answer_approval(bundle, normalized, match.group(1))
            return _answer(bundle, normalized, intent, match.group(1))
    return OntologyAnswer(
        question=normalized,
        intent="unsupported",
        status="unsupported",
        answer=(
            "Supported questions ask who owns a module, who authored an artifact, "
            "or who reviewed/replied to an artifact."
        ),
        subject_key=None,
        person_keys=(),
        evidence_ids=(),
        paths=(),
        confidence=None,
        answer_kind="unsupported",
        reasoning=(),
        limitations=("No answer was inferred outside the supported deterministic intents.",),
    )


def _answer(
    bundle: CanonicalBundle, question: str, intent: str, subject_text: str
) -> OntologyAnswer:
    subject = _match_subject(bundle, subject_text, intent)
    if subject is None:
        return OntologyAnswer(
            question=question,
            intent=intent,
            status="not_found",
            answer=f"No matching {('module' if intent == 'owner' else 'artifact')} was found.",
            subject_key=None,
            person_keys=(),
            evidence_ids=(),
            paths=(),
            confidence=None,
            answer_kind="abstention",
            reasoning=("No canonical subject matched the requested name.",),
            limitations=("The supplied corpus may use another name or omit the subject.",),
        )

    nodes = {node.id: node for node in bundle.nodes}
    if intent == "owner":
        return _answer_owner(bundle, question, subject, nodes)
    matches: list[tuple[str, tuple[str, ...], tuple[str, ...], int]] = []
    if intent == "author":
        rel_type = "AUTHORED"
        for edge in bundle.edges:
            if edge.rel_type == rel_type and edge.target_id == subject.id:
                person = nodes[edge.source_id]
                confidence = edge.properties.get("confidence", edge.confidence)
                matches.append(
                    (
                        person.canonical_key,
                        (person.canonical_key, subject.canonical_key),
                        edge.evidence_ids,
                        confidence if type(confidence) is int else edge.confidence,
                    )
                )
    else:
        reply_ids = {
            edge.source_id: edge
            for edge in bundle.edges
            if edge.rel_type == "REPLIES_TO" and edge.target_id == subject.id
        }
        for edge in bundle.edges:
            if edge.rel_type != "AUTHORED" or edge.target_id not in reply_ids:
                continue
            person = nodes[edge.source_id]
            reply = nodes[edge.target_id]
            reply_edge = reply_ids[edge.target_id]
            matches.append(
                (
                    person.canonical_key,
                    (person.canonical_key, reply.canonical_key, subject.canonical_key),
                    tuple(sorted((*edge.evidence_ids, *reply_edge.evidence_ids))),
                    min(edge.confidence, reply_edge.confidence),
                )
            )

    if not matches:
        return OntologyAnswer(
            question=question,
            intent=intent,
            status="no_answer",
            answer=f"The graph contains {subject.canonical_key}, but no supported evidence answers this question.",
            subject_key=subject.canonical_key,
            person_keys=(),
            evidence_ids=(),
            paths=(),
            confidence=None,
            answer_kind="abstention",
            reasoning=("The subject exists, but no supported typed edge carries the requested fact.",),
            limitations=("Missing evidence is not proof that the event never occurred.",),
        )

    matches.sort(key=lambda item: (-item[3], item[0], item[1]))
    person_keys = tuple(dict.fromkeys(match[0] for match in matches))
    names = [_display_name(_node_by_key(bundle, key)) for key in person_keys]
    verb = {"owner": "owns", "author": "authored", "reviewer": "reviewed"}[intent]
    return OntologyAnswer(
        question=question,
        intent=intent,
        status="answered",
        answer=f"{', '.join(names)} {verb} {_display_name(subject)}.",
        subject_key=subject.canonical_key,
        person_keys=person_keys,
        evidence_ids=tuple(sorted({item for match in matches for item in match[2]})),
        paths=tuple(match[1] for match in matches),
        confidence=min(match[3] for match in matches),
        answer_kind="direct",
        reasoning=(
            f"Matched {_display_name(subject)} to {subject.canonical_key}.",
            f"Followed typed {('OWNS' if intent == 'owner' else 'AUTHORED' if intent == 'author' else 'REPLIES_TO')} evidence edges.",
            "Returned only people attached to supporting evidence IDs.",
        ),
        limitations=("The answer is limited to the active evidence snapshot.",),
    )


def _answer_owner(
    bundle: CanonicalBundle,
    question: str,
    subject: NodeRow,
    nodes: dict[int, NodeRow],
) -> OntologyAnswer:
    owner_edges = [
        edge for edge in bundle.edges if edge.rel_type == "OWNS" and edge.target_id == subject.id
    ]
    if not owner_edges:
        return OntologyAnswer(
            question=question, intent="owner", status="no_answer",
            answer=f"The graph contains {subject.canonical_key}, but has no ownership evidence.",
            subject_key=subject.canonical_key, person_keys=(), evidence_ids=(), paths=(),
            confidence=None, answer_kind="abstention",
            reasoning=("No typed OWNS edge exists for the matched module.",),
            limitations=("Missing ownership evidence is not proof that the module has no owner.",),
        )

    snapshot_epoch = max(
        (record.observed_epoch for record in bundle.evidence),
        default=0,
    )
    ranked = sorted(owner_edges, key=lambda edge: _owner_sort_key(edge, snapshot_epoch))
    selected = ranked[0]
    selected_person = nodes[selected.source_id]
    evidence_by_id = {record.evidence_id: record for record in bundle.evidence}
    decisions = tuple(
        _ownership_decision(edge, selected, snapshot_epoch, nodes, evidence_by_id)
        for edge in ranked
    )
    explicit = tuple(item for item in decisions if item.authority != "inferred_authorship")
    conflicts = explicit if len({item.person_key for item in explicit}) > 1 else ()
    selected_decision = decisions[0]
    trust_explanation = (
        f"Selected {selected_decision.source_type}:{selected_decision.source_record_id} "
        f"because it is active in the snapshot and has authority rank "
        f"{_int_property(selected, 'authority_rank', 0)}."
    )
    return OntologyAnswer(
        question=question,
        intent="owner",
        status="answered",
        answer=f"{_display_name(selected_person)} currently owns {_display_name(subject)}.",
        subject_key=subject.canonical_key,
        person_keys=(selected_person.canonical_key,),
        evidence_ids=tuple(sorted({item for edge in ranked for item in edge.evidence_ids})),
        paths=((selected_person.canonical_key, subject.canonical_key),),
        confidence=_edge_confidence(selected),
        answer_kind="direct",
        reasoning=(
            f"Matched {_display_name(subject)} to {subject.canonical_key}.",
            "Compared every typed OWNS assertion against the snapshot time.",
            "Ranked active records by declared source authority, observation time, then confidence.",
        ),
        limitations=(
            "Authority ranks are explicit product policy and should be configured per organization.",
            "The answer is limited to the active evidence snapshot.",
        ),
        conflicts=conflicts,
        trust_explanation=trust_explanation,
    )


def _owner_sort_key(edge: EdgeRow, snapshot_epoch: int) -> tuple[int, int, int, int, str]:
    valid_from = _optional_int_property(edge, "valid_from_epoch")
    valid_until = _optional_int_property(edge, "valid_until_epoch")
    active = (valid_from is None or valid_from <= snapshot_epoch) and (
        valid_until is None or valid_until >= snapshot_epoch
    )
    return (
        0 if active else 1,
        -_int_property(edge, "authority_rank", 0),
        -_int_property(edge, "observed_epoch", 0),
        -_edge_confidence(edge),
        edge.canonical_key,
    )


def _ownership_decision(
    edge: EdgeRow,
    selected: EdgeRow,
    snapshot_epoch: int,
    nodes: dict[int, NodeRow],
    evidence_by_id: dict[str, EvidenceRecord],
) -> EvidenceDecision:
    evidence = next((evidence_by_id[item] for item in edge.evidence_ids if item in evidence_by_id), None)
    source_type = str(getattr(evidence, "source_type", "derived"))
    source_record_id = str(getattr(evidence, "source_record_id", edge.canonical_key))
    valid_from = _optional_int_property(edge, "valid_from_epoch")
    valid_until = _optional_int_property(edge, "valid_until_epoch")
    active = (valid_from is None or valid_from <= snapshot_epoch) and (
        valid_until is None or valid_until >= snapshot_epoch
    )
    is_selected = edge.id == selected.id
    if is_selected:
        reason = "Selected: active record with the strongest declared authority."
    elif not active:
        reason = "Not selected: its validity window ended before the active snapshot."
    else:
        reason = "Not selected: a higher-authority active record exists."
    return EvidenceDecision(
        person_key=nodes[edge.source_id].canonical_key,
        source_type=source_type,
        source_record_id=source_record_id,
        authority=str(edge.properties.get("authority", "inferred_authorship")),
        observed_epoch=_int_property(edge, "observed_epoch", int(getattr(evidence, "observed_epoch", 0))),
        valid_from_epoch=valid_from,
        valid_until_epoch=valid_until,
        confidence=_edge_confidence(edge),
        selected=is_selected,
        reason=reason,
    )


def _answer_dependency_impact(
    bundle: CanonicalBundle, question: str, subject_text: str
) -> OntologyAnswer:
    subject = _match_subject(bundle, subject_text, "owner")
    if subject is None:
        return OntologyAnswer(
            question=question, intent="dependency_impact", status="not_found",
            answer="No matching module was found.", subject_key=None, person_keys=(),
            evidence_ids=(), paths=(), confidence=None, answer_kind="abstention",
            reasoning=("No canonical module matched the requested name.",),
            limitations=("The module may use another name or be outside the supplied exports.",),
        )
    nodes = {node.id: node for node in bundle.nodes}
    owner_edges = [edge for edge in bundle.edges if edge.rel_type == "OWNS"]
    snapshot_epoch = max((record.observed_epoch for record in bundle.evidence), default=0)
    findings: list[tuple[str, str, tuple[str, ...], int]] = []
    for dependency in bundle.edges:
        if dependency.rel_type != "DEPENDS_ON" or dependency.target_id != subject.id:
            continue
        dependent = nodes[dependency.source_id]
        owners = [edge for edge in owner_edges if edge.target_id == dependent.id]
        owners.sort(key=lambda edge: _owner_sort_key(edge, snapshot_epoch))
        if owners:
            owner = nodes[owners[0].source_id]
            findings.append((dependent.canonical_key, owner.canonical_key, tuple(sorted({*dependency.evidence_ids, *owners[0].evidence_ids})), min(dependency.confidence, _edge_confidence(owners[0]))))
        else:
            findings.append((dependent.canonical_key, "", dependency.evidence_ids, dependency.confidence))
    if not findings:
        return OntologyAnswer(
            question=question, intent="dependency_impact", status="no_answer",
            answer=f"Not enough evidence to identify modules affected by {_display_name(subject)}.",
            subject_key=subject.canonical_key, person_keys=(), evidence_ids=(), paths=(),
            confidence=None, answer_kind="abstention",
            reasoning=("No incoming DEPENDS_ON edge was present for the requested module.",),
            limitations=("Absence from the graph may reflect export or module-mapping coverage.",),
        )
    findings.sort(key=lambda item: item[0])
    people = tuple(dict.fromkeys(item[1] for item in findings if item[1]))
    modules = ", ".join(_display_name(_node_by_key(bundle, item[0])) for item in findings)
    return OntologyAnswer(
        question=question, intent="dependency_impact", status="answered",
        answer=f"{modules} {'depends' if len(findings) == 1 else 'depend'} on {_display_name(subject)} and may be affected.",
        subject_key=subject.canonical_key, person_keys=people,
        evidence_ids=tuple(sorted({evidence_id for item in findings for evidence_id in item[2]})),
        paths=tuple((subject.canonical_key, item[0], item[1]) if item[1] else (subject.canonical_key, item[0]) for item in findings),
        confidence=min(item[3] for item in findings), answer_kind="multi_hop",
        reasoning=(
            f"Matched {_display_name(subject)} to {subject.canonical_key}.",
            "Traversed incoming DEPENDS_ON relationships to dependent modules.",
            "Joined each dependent module to its highest-confidence OWNS edge.",
        ),
        limitations=("Impact means graph reachability, not proof that a change will cause an incident.",),
    )


def _answer_approval(bundle: CanonicalBundle, question: str, subject_text: str) -> OntologyAnswer:
    needle = _normalize_lookup(subject_text)
    artifacts = [node for node in bundle.nodes if node.label in {"Artifact", "Phantom"} and (needle in _normalize_lookup(node.canonical_key) or _normalize_lookup(node.canonical_key) in needle)]
    phantom = next(
        (
            node
            for node in bundle.nodes
            if node.label == "Phantom"
            and str(node.properties.get("expected_kind", "")).casefold() == "approval"
        ),
        None,
    )
    subject = min(artifacts, key=lambda node: node.canonical_key) if artifacts else phantom
    if subject is None:
        return OntologyAnswer(
            question=question, intent="approval", status="not_found",
            answer="Not enough evidence to answer who approved this change.", subject_key=None,
            person_keys=(), evidence_ids=(), paths=(), confidence=None,
            answer_kind="abstention", reasoning=("No approval artifact matched the question.",),
            limitations=("Missing evidence is not proof that approval did not occur.",),
        )
    evidence_ids = subject.evidence_ids
    return OntologyAnswer(
        question=question, intent="approval", status="no_answer",
        answer="Not enough evidence to answer. The expected approval record is absent from the supplied corpus.",
        subject_key=subject.canonical_key, person_keys=(), evidence_ids=evidence_ids,
        paths=((subject.canonical_key,),), confidence=None, answer_kind="abstention",
        reasoning=("The workflow expects an approval artifact.", "The active graph contains a Phantom placeholder instead of an observed approval record.", "X-Ray refuses to infer an approver without source evidence."),
        limitations=("The export boundary is an alternative explanation for the missing record.", "Absence does not establish deletion or process failure."),
    )


def _edge_confidence(edge: EdgeRow) -> int:
    return _int_property(edge, "confidence", edge.confidence)


def _int_property(edge: EdgeRow, key: str, default: int) -> int:
    value = edge.properties.get(key, default)
    return value if type(value) is int else default


def _optional_int_property(edge: EdgeRow, key: str) -> int | None:
    value = edge.properties.get(key)
    return value if type(value) is int else None


def _match_subject(bundle: CanonicalBundle, text: str, intent: str) -> NodeRow | None:
    wanted_label = "Module" if intent == "owner" else "Artifact"
    needle = _normalize_lookup(text)
    candidates = []
    for node in bundle.nodes:
        if node.label != wanted_label:
            continue
        values = {
            node.canonical_key,
            node.canonical_key.split(":", 1)[-1],
            *(
                str(value)
                for key, value in node.properties.items()
                if key in {"display_name", "name", "title", "subject"}
            ),
        }
        if needle in {_normalize_lookup(value) for value in values}:
            candidates.append(node)
    return min(candidates, key=lambda node: node.canonical_key) if candidates else None


def _normalize_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _display_name(node: NodeRow) -> str:
    for key in ("display_name", "title", "subject", "name"):
        value = node.properties.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return node.canonical_key.split(":", 1)[-1]


def _node_by_key(bundle: CanonicalBundle, key: str) -> NodeRow:
    return next(node for node in bundle.nodes if node.canonical_key == key)


__all__ = ["EvidenceDecision", "OntologyAnswer", "answer_ontology_question"]
