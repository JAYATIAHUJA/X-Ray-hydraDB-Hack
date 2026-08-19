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


_QUESTION_PATTERNS = (
    ("owner", re.compile(r"^who\s+(?:owns|is responsible for)\s+(.+?)\??$", re.I)),
    ("author", re.compile(r"^who\s+(?:authored|wrote|created)\s+(.+?)\??$", re.I)),
    ("reviewer", re.compile(r"^who\s+(?:reviewed|replied to)\s+(.+?)\??$", re.I)),
)


def answer_ontology_question(bundle: CanonicalBundle, question: str) -> OntologyAnswer:
    normalized = " ".join(question.strip().split())
    for intent, pattern in _QUESTION_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match is not None:
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
        )

    matches.sort(key=lambda item: (-item[3], item[0], item[1]))
    person_keys = tuple(dict.fromkeys(match[0] for match in matches))
    names = [_display_name(_node_by_key(bundle, key)) for key in person_keys]
    verb = {"owner": "owns", "author": "authored", "reviewer": "reviewed"}[intent]
    return OntologyAnswer(
        question=question,
        intent=intent,
        status="answered",
        answer=f"{', '.join(names)} {verb} { _display_name(subject) }.",
        subject_key=subject.canonical_key,
        person_keys=person_keys,
        evidence_ids=tuple(sorted({item for match in matches for item in match[2]})),
        paths=tuple(match[1] for match in matches),
        confidence=min(match[3] for match in matches),
    )


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
            *(str(value) for key, value in node.properties.items() if key in {"display_name", "name", "title", "subject"}),
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
