from xray_analytics.questions import EvidenceDecision, OntologyAnswer
from xray_analytics.verdicts import decide_question_verdict


def _answer(**overrides: object) -> OntologyAnswer:
    base: dict[str, object] = {
        "question": "Who owns network?",
        "intent": "owner",
        "status": "answered",
        "answer": "Bridge Ops",
        "subject_key": "module:network",
        "person_keys": ("person:bridge",),
        "evidence_ids": ("ev-1",),
        "paths": (("person:bridge", "module:network"),),
        "confidence": 90,
        "answer_kind": "direct",
        "reasoning": ("matched owner edge",),
        "limitations": (),
    }
    base.update(overrides)
    return OntologyAnswer(**base)  # type: ignore[arg-type]


def _conflict(*, selected: bool) -> EvidenceDecision:
    return EvidenceDecision(
        person_key="person:a",
        source_type="jira",
        source_record_id="J-1",
        authority="codeowners",
        observed_epoch=1,
        valid_from_epoch=None,
        valid_until_epoch=None,
        confidence=80,
        selected=selected,
        reason="test",
    )


def test_supported_when_answered() -> None:
    assert decide_question_verdict(_answer()) == "SUPPORTED"


def test_not_found() -> None:
    assert (
        decide_question_verdict(
            _answer(status="not_found", answer_kind="abstention", evidence_ids=(), paths=())
        )
        == "NOT_FOUND"
    )


def test_unknown_on_unsupported() -> None:
    assert (
        decide_question_verdict(
            _answer(status="unsupported", intent="unsupported", answer_kind="unsupported")
        )
        == "UNKNOWN"
    )


def test_disputed_when_no_selected_conflict() -> None:
    verdict = decide_question_verdict(
        _answer(status="no_answer", answer_kind="abstention"),
        conflicts=(_conflict(selected=False), _conflict(selected=False)),
    )
    assert verdict == "DISPUTED"
