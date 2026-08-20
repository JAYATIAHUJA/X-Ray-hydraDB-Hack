from __future__ import annotations

import re
from dataclasses import dataclass

from xray_core.models import CanonicalBundle, NodeRow


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


_QUESTION_PATTERNS = (
    (
        "dependency_impact",
        re.compile(
            r"^(?:which|what)\s+(?:teams|services|modules)\s+(?:are\s+)?(?:affected|impacted)\s+if\s+(.+?)\s+changes\??$",
            re.I,
        ),
    ),
    ("approval", re.compile(r"^who\s+approved\s+(.+?)\??$", re.I)),
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
    matches: list[tuple[str, tuple[str, ...], tuple[str, ...], int]] = []
    if intent in {"owner", "author"}:
        rel_type = "OWNS" if intent == "owner" else "AUTHORED"
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
    findings: list[tuple[str, str, tuple[str, ...], int]] = []
    for dependency in bundle.edges:
        if dependency.rel_type != "DEPENDS_ON" or dependency.target_id != subject.id:
            continue
        dependent = nodes[dependency.source_id]
        owners = [edge for edge in owner_edges if edge.target_id == dependent.id]
        owners.sort(key=lambda edge: (-_edge_confidence(edge), edge.canonical_key))
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


def _edge_confidence(edge: object) -> int:
    properties = getattr(edge, "properties")
    confidence = properties.get("confidence", getattr(edge, "confidence"))
    return confidence if type(confidence) is int else getattr(edge, "confidence")


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


__all__ = ["OntologyAnswer", "answer_ontology_question"]
