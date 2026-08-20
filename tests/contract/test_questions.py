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


def test_answers_reverse_dependency_impact_with_multi_hop_evidence() -> None:
    answer = answer_ontology_question(
        demo_bundle(), "Which services are affected if ledger-worker changes?"
    )

    assert answer.status == "answered"
    assert answer.intent == "dependency_impact"
    assert answer.answer_kind == "multi_hop"
    assert answer.subject_key == "module:ledger-worker"
    assert any("module:payments-api" in path for path in answer.paths)
    assert answer.evidence_ids
    assert answer.reasoning


def test_missing_approval_abstains_and_explains_export_uncertainty() -> None:
    answer = answer_ontology_question(demo_bundle(), "Who approved the refund limit change?")

    assert answer.status == "no_answer"
    assert answer.intent == "approval"
    assert answer.answer_kind == "abstention"
    assert "Not enough evidence" in answer.answer
    assert any("Absence" in limitation for limitation in answer.limitations)


def test_current_owner_resolves_and_discloses_conflicting_records() -> None:
    answer = answer_ontology_question(
        demo_bundle(),
        "Who owns payments-api now, and why did an older Jira record say Alex?",
    )

    assert answer.status == "answered"
    assert answer.person_keys == ("person:maya-chen",)
    assert len(answer.conflicts) == 2
    assert next(item for item in answer.conflicts if item.selected).source_record_id == (
        "CODEOWNERS-payments-api"
    )
    assert any("validity window ended" in item.reason for item in answer.conflicts)
    assert answer.trust_explanation is not None
