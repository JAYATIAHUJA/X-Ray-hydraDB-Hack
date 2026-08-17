from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
DATASET_ID = "xray-synth-500"
START_EPOCH = 1_735_689_600

# Index of the planted Ghost: a senior IC in the first team, deliberately *not*
# the top of the reporting chain, so structural rank and formal rank diverge.
BROKER_INDEX = 7

# role_rank follows the build spec §3.1: 0=unknown, 1=IC, 2=senior, 3=lead,
# 4=manager, 5=director, 6=VP+. Higher is more senior.
ROLE_VP = 6
ROLE_MANAGER = 4
ROLE_LEAD = 3
ROLE_SENIOR = 2
ROLE_IC = 1

TEAM_NAMES = [
    "payments",
    "ledger",
    "identity",
    "platform",
    "data",
    "mobile",
    "growth",
    "infra",
    "security",
    "support-tools",
]

MODULE_NAMES = [
    "payments-api",
    "checkout-web",
    "refunds-worker",
    "invoice-service",
    "ledger-core",
    "ledger-worker",
    "reconciliation",
    "tax-engine",
    "identity-api",
    "auth-gateway",
    "session-store",
    "user-profile",
    "platform-sdk",
    "event-bus",
    "job-scheduler",
    "config-service",
    "data-pipeline",
    "warehouse-sync",
    "metrics-collector",
    "report-builder",
    "mobile-ios",
    "mobile-android",
    "push-service",
    "deeplink-router",
    "growth-experiments",
    "referral-service",
    "email-campaigns",
    "onboarding-flow",
    "infra-terraform",
    "k8s-operators",
    "ci-runners",
    "artifact-registry",
    "secrets-manager",
    "audit-sink",
    "policy-engine",
    "vuln-scanner",
    "support-console",
    "ticket-router",
    "kb-search",
    "macro-engine",
]

FIRST_NAMES = [
    "Jon",
    "Omar",
    "Lena",
    "Theo",
    "Nina",
    "Sam",
    "Ines",
    "Priya",
    "Maya",
    "Alex",
    "Ravi",
    "Zoe",
    "Kwame",
    "Hana",
    "Luca",
    "Aisha",
    "Mateo",
    "Yuki",
    "Tariq",
    "Elena",
    "Femi",
    "Sofia",
    "Daniel",
    "Amara",
    "Noah",
    "Ingrid",
    "Arjun",
    "Chloe",
    "Diego",
    "Mei",
    "Kofi",
    "Sara",
    "Ivan",
    "Leila",
    "Ben",
    "Rosa",
    "Kenji",
    "Nadia",
    "Tom",
    "Anika",
]

LAST_NAMES = [
    "Bell",
    "Haddad",
    "Park",
    "Brooks",
    "Okafor",
    "Wu",
    "Costa",
    "Nair",
    "Chen",
    "Rivera",
    "Shah",
    "Meyer",
    "Mensah",
    "Sato",
    "Ricci",
    "Khan",
    "Alvarez",
    "Tanaka",
    "Rahman",
    "Petrov",
    "Adeyemi",
    "Moreau",
    "Kim",
    "Nwosu",
    "Fischer",
    "Larsen",
    "Iyer",
    "Dubois",
    "Silva",
    "Lin",
    "Boateng",
    "Haddadi",
    "Volkov",
    "Farah",
    "Novak",
    "Rossi",
    "Ito",
    "Osman",
    "Walsh",
    "Bose",
]


def _display_name(index: int) -> str:
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    last = LAST_NAMES[(index // len(FIRST_NAMES) + index) % len(LAST_NAMES)]
    return f"{first} {last}"


def _role_rank(index: int) -> int:
    if index == 0:
        return ROLE_VP
    if index % 50 == 0:
        return ROLE_MANAGER
    if index == BROKER_INDEX:
        return ROLE_SENIOR
    if index % 25 == 12:
        return ROLE_LEAD
    return ROLE_SENIOR if index % 3 == 0 else ROLE_IC


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    people = [f"p{index:04d}" for index in range(args.people)]
    modules = [
        MODULE_NAMES[index] if index < len(MODULE_NAMES) else f"module-{index:02d}"
        for index in range(args.modules)
    ]
    teams = [
        TEAM_NAMES[index] if index < len(TEAM_NAMES) else f"team-{index:02d}"
        for index in range(args.teams)
    ]
    broker = people[min(BROKER_INDEX, len(people) - 1)]

    directory = _directory_records(people, teams)
    events = [
        *_communication_records(people, teams, broker),
        *_gap_artifacts(modules),
    ]
    git_facts = [
        *_module_records(modules),
        *_ownership_records(modules, people, args.teams),
        *_dependency_records(modules),
    ]
    ground_truth = _ground_truth(broker, modules)
    manifest = _manifest(
        output_dir=output_dir,
        directory=directory,
        events=events,
        git_facts=git_facts,
        ground_truth=ground_truth,
    )

    _write_json(output_dir / "directory.json", directory)
    _write_json(output_dir / "events.json", events)
    _write_json(output_dir / "git_facts.json", git_facts)
    _write_json(output_dir / "ground_truth.json", ground_truth)
    _write_json(output_dir / "manifest.json", manifest)
    print(f"Wrote {DATASET_ID} fixture to {output_dir}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the labelled 500-person X-Ray corpus.")
    parser.add_argument("--output", default=f"data/fixtures/{DATASET_ID}")
    parser.add_argument("--people", type=int, default=500)
    parser.add_argument("--modules", type=int, default=40)
    parser.add_argument("--teams", type=int, default=10)
    return parser.parse_args()


def _directory_records(
    people: list[str],
    teams: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for team in teams:
        records.append(
            _record(
                source="synth-directory",
                external_id=team,
                kind="directory_team",
                subjects=[f"team:{team}"],
                metadata={
                    "canonical_key": f"team:{team}",
                    "display_name": team.replace("-", " ").title(),
                },
            )
        )

    for index, person in enumerate(people):
        team = teams[min(index // 50, len(teams) - 1)]
        if index == 0:
            manager = None
        elif index % 50 == 0:
            manager = people[0]
        else:
            manager = people[(index // 50) * 50]
        role_rank = _role_rank(index)
        records.append(
            _record(
                source="synth-directory",
                external_id=person,
                kind="directory_person",
                subjects=[f"person:{person}"],
                metadata=_without_none(
                    {
                        "display_name": _display_name(index),
                        "manager_external_id": manager,
                        "role_rank": role_rank,
                        "team_key": f"team:{team}",
                    }
                ),
            )
        )
    return records


def _module_owner(people: list[str], module_index: int, team_count: int) -> str:
    team_index = module_index % team_count
    return people[(team_index * 50) + 10 + (module_index % 20)]


def _communication_records(
    people: list[str],
    teams: list[str],
    broker: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    # Negative control: owners of *coordinated* dependencies talk to each other
    # directly, so only the planted faultlines lack a short communication path.
    for source, target, weight in COORDINATED_DEPENDENCY_INDICES:
        owner_a = _module_owner(people, source, len(teams))
        owner_b = _module_owner(people, target, len(teams))
        records.append(_communication(owner_a, owner_b, weight, f"coordinated-{owner_a}-{owner_b}"))
    for team_index, _team in enumerate(teams):
        start = team_index * 50
        team_people = people[start : start + 50]
        hub = team_people[0]
        if hub != broker:
            records.append(_communication(hub, broker, 12, f"bridge-{hub}-{broker}"))
        for offset, person in enumerate(team_people[1:], start=1):
            records.append(_communication(hub, person, 3 + (offset % 5), f"hub-{hub}-{person}"))
            if offset < len(team_people) - 1 and offset % 2 == 0:
                records.append(
                    _communication(person, team_people[offset + 1], 1, f"local-{person}")
                )
    return records


def _module_records(modules: list[str]) -> list[dict[str, Any]]:
    return [
        _record(
            source="synth-git-facts",
            external_id=f"module-{module}",
            kind="module",
            subjects=[f"module:{module}"],
            metadata={
                "canonical_key": f"module:{module}",
                "criticality": round(1.0 - (index * 0.01), 2),
                "module_name": module,
                "repo": "synth-monorepo",
            },
        )
        for index, module in enumerate(modules)
    ]


def _ownership_records(
    modules: list[str],
    people: list[str],
    team_count: int,
) -> list[dict[str, Any]]:
    records = []
    for index, module in enumerate(modules):
        owner = _module_owner(people, index, team_count)
        records.append(
            _record(
                source="synth-git-facts",
                external_id=f"authorship-{owner}-{module}",
                kind="authorship_aggregate",
                author_external_id=owner,
                subjects=[f"person:{owner}", f"module:{module}"],
                metadata={
                    "attributed_count": 30 + (index % 17),
                    "module_external_id": module,
                    "total_attributed_count": 34 + (index % 17),
                },
            )
        )
    return records


PLANTED_FAULTLINE_INDICES = [(0, 9, 41), (11, 28, 37), (22, 35, 31)]
COORDINATED_DEPENDENCY_INDICES = [(1, 2, 9), (12, 13, 8), (23, 24, 7), (34, 36, 6)]


def _dependency_records(modules: list[str]) -> list[dict[str, Any]]:
    planted = [
        (modules[source], modules[target], weight)
        for source, target, weight in PLANTED_FAULTLINE_INDICES
    ]
    coordinated = [
        (modules[source], modules[target], weight)
        for source, target, weight in COORDINATED_DEPENDENCY_INDICES
    ]
    return [
        _dependency(
            source,
            target,
            weight,
            "planted" if (source, target, weight) in planted else "background",
        )
        for source, target, weight in (*planted, *coordinated)
    ]


def _gap_artifacts(modules: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(5):
        owner = f"p{(index * 73) % 500:04d}"
        module = modules[index]
        records.append(
            _record(
                source="synth-events",
                external_id=f"gap-{index}-directive",
                kind="artifact",
                occurred_at_epoch=START_EPOCH + 10_000 + (index * 1_000),
                author_external_id=owner,
                subjects=[f"artifact:synth-gap-{index}-directive", f"module:{module}"],
                metadata={
                    "artifact_kind": "directive",
                    "canonical_key": f"artifact:synth-gap-{index}-directive",
                    "sequence_key": f"synth-gap-sequence-{index}",
                    "sequence_ordinal": 0,
                },
            )
        )
        records.append(
            _record(
                source="synth-events",
                external_id=f"gap-{index}-change",
                kind="artifact",
                occurred_at_epoch=START_EPOCH + 10_500 + (index * 1_000),
                author_external_id=owner,
                subjects=[f"artifact:synth-gap-{index}-change", f"module:{module}"],
                metadata={
                    "artifact_kind": "code_change",
                    "canonical_key": f"artifact:synth-gap-{index}-change",
                    "sequence_key": f"synth-gap-sequence-{index}",
                    "sequence_ordinal": 2,
                },
            )
        )
    return records


def _ground_truth(broker: str, modules: list[str]) -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "ghost_person_key": f"person:{broker}",
        "faultline_module_pairs": [
            [f"module:{modules[source]}", f"module:{modules[target]}"]
            for source, target, _weight in PLANTED_FAULTLINE_INDICES
        ],
        "gap_paths": [
            {
                "source_artifact_key": f"artifact:synth-gap-{index}-change",
                "target_artifact_key": f"artifact:synth-gap-{index}-directive",
                "phantom_key": f"artifact:synth-gap-{index}-approval",
            }
            for index in range(5)
        ],
        "planted_counts": {"faultlines": 3, "gaps": 5, "ghosts": 1},
    }


def _manifest(
    *,
    output_dir: Path,
    directory: list[dict[str, Any]],
    events: list[dict[str, Any]],
    git_facts: list[dict[str, Any]],
    ground_truth: dict[str, Any],
) -> dict[str, Any]:
    pending_files = {
        "directory.json": directory,
        "events.json": events,
        "git_facts.json": git_facts,
        "ground_truth.json": ground_truth,
    }
    descriptors = []
    for path, records in pending_files.items():
        payload = _json_bytes(records)
        descriptors.append(
            {
                "path": path,
                "source_type": path.removesuffix(".json"),
                "source_uri": f"fixture://{DATASET_ID}/{path}",
                "record_count": len(records) if isinstance(records, list) else 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "input_status": "complete",
            }
        )

    return {
        "dataset_id": DATASET_ID,
        "fixture_version": 1,
        "schema_version": "1.0.0",
        "created_at_epoch": START_EPOCH,
        "evidence_classes": ["observed", "inferred", "demo_ground_truth"],
        "source_files": descriptors[:3],
        "ground_truth_file": "ground_truth.json",
        "ground_truth_descriptor": {
            "evidence_class": "demo_ground_truth",
            "sha256": descriptors[3]["sha256"],
        },
        "sequence_contracts": _sequence_contracts(),
        "acceptance_labels": {
            "ghost_broker_key": f"person:{ground_truth['ghost_person_key'].split(':', 1)[1]}",
            "faultline_count": 3,
            "gap_count": 5,
        },
        "limitations": [
            "This is a labelled synthetic 500-person fixture, not a real-organization result.",
            "Absence does not establish deletion. The corpus is structurally incomplete at planted gap points.",
        ],
    }


def _sequence_contracts() -> list[dict[str, Any]]:
    contracts = []
    for index in range(5):
        contract = {
            "contract_id": f"contract:synth-gap-{index}:v1",
            "contract_kind": "contiguous_sequence",
            "sequence_key": f"synth-gap-sequence-{index}",
            "steps": [
                {
                    "ordinal": 0,
                    "canonical_key": f"artifact:synth-gap-{index}-directive",
                    "artifact_kind": "directive",
                    "required": True,
                },
                {
                    "ordinal": 1,
                    "canonical_key": f"artifact:synth-gap-{index}-approval",
                    "artifact_kind": "approval",
                    "earliest_epoch": START_EPOCH + 10_250 + (index * 1_000),
                    "required": True,
                },
                {
                    "ordinal": 2,
                    "canonical_key": f"artifact:synth-gap-{index}-change",
                    "artifact_kind": "code_change",
                    "required": True,
                },
            ],
            "source_uri": f"fixture://{DATASET_ID}/contracts/synth-gap-{index}",
            "limitations": ["Export filtering is an alternative explanation."],
        }
        contract["content_sha256"] = hashlib.sha256(_json_bytes(contract)).hexdigest()
        contracts.append(contract)
    return contracts


def _communication(sender: str, recipient: str, weight: int, external_id: str) -> dict[str, Any]:
    return _record(
        source="synth-events",
        external_id=f"comm-{external_id}",
        kind="communication_aggregate",
        occurred_at_epoch=START_EPOCH + weight,
        author_external_id=sender,
        subjects=[f"person:{sender}", f"person:{recipient}"],
        metadata={
            "first_epoch": START_EPOCH,
            "interaction_count": weight,
            "interaction_kind": "mention",
            "last_epoch": START_EPOCH + weight,
            "recipient_external_id": recipient,
            "sender_external_id": sender,
        },
    )


def _dependency(source: str, target: str, weight: int, label: str) -> dict[str, Any]:
    return _record(
        source="synth-git-facts",
        external_id=f"dependency-{source}-{target}-{label}",
        kind="dependency",
        occurred_at_epoch=START_EPOCH + 20_000 + weight,
        subjects=[f"module:{source}", f"module:{target}"],
        metadata={
            "dependency_kind": "explicit_reference",
            "source_module_external_id": source,
            "target_module_external_id": target,
            "weight": weight,
        },
    )


def _record(
    *,
    source: str,
    external_id: str,
    kind: str,
    subjects: list[str],
    metadata: dict[str, Any],
    occurred_at_epoch: int = START_EPOCH,
    author_external_id: str | None = None,
    parent_external_id: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "external_id": external_id,
        "kind": kind,
        "occurred_at_epoch": occurred_at_epoch,
        "author_external_id": author_external_id,
        "parent_external_id": parent_external_id,
        "subjects": subjects,
        "content_sha256": hashlib.sha256((content or "").encode("utf-8")).hexdigest(),
        "content": content,
        "metadata": metadata,
    }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


if __name__ == "__main__":
    raise SystemExit(main())
