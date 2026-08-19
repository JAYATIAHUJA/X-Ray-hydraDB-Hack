from __future__ import annotations

from xray_analytics import answer_ontology_question
from xray_api.dependencies import demo_bundle


def test_answers_module_owner_with_typed_path_and_evidence() -> None:
    answer = answer_ontology_question(demo_bundle(), "Who owns payments-api?")

    assert answer.status == "answered"
    assert answer.intent == "owner"
    assert answer.subject_key == "module:payments-api"
    assert answer.person_keys
    assert all(path[-1] == "module:payments-api" for path in answer.paths)
    assert answer.evidence_ids


def test_unsupported_question_is_explicit_instead_of_guessed() -> None:
    answer = answer_ontology_question(demo_bundle(), "Why is revenue down?")

    assert answer.status == "unsupported"
    assert answer.person_keys == ()
    assert answer.evidence_ids == ()
