from __future__ import annotations

from typing import Protocol

from .models import EvidenceRecord


class EvidenceRepository(Protocol):
    def get(self, evidence_id: str) -> EvidenceRecord | None: ...

    def list(self) -> tuple[EvidenceRecord, ...]: ...

    def limitations(self) -> tuple[str, ...]: ...


__all__ = ["EvidenceRepository"]
