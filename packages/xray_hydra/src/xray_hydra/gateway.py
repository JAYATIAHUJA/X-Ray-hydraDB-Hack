from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from xray_core.models import QuerySpec, WriteBatchSpec


class DriverLike(Protocol):
    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> object: ...


class SessionLike(Protocol):
    def run(self, query: str, parameters: dict[str, object]) -> Iterable[object]: ...


@runtime_checkable
class SessionDriverLike(Protocol):
    def session(self) -> AbstractContextManager[SessionLike]: ...


class GatewayError(RuntimeError):
    """Raised when a HydraDB response cannot be normalized safely."""


class HydraGateway:
    """Thin, transport-agnostic wrapper over a Bolt driver.

    HydraDB rejects explicit transactions, so every statement runs as an
    auto-commit ``session.run`` (see docs/cypher-compat-verified.md). The gateway
    only normalizes result rows; query construction lives in ``cypher.py``.
    """

    def __init__(self, driver: DriverLike) -> None:
        self.driver = driver

    def run(self, query: QuerySpec) -> list[dict[str, object]]:
        return _execute(self.driver, query.statement, dict(query.parameters))

    def run_batch(self, batch: WriteBatchSpec) -> list[dict[str, object]]:
        return _execute(
            self.driver,
            batch.statement,
            {"rows": [dict(row) for row in batch.rows]},
        )

    def close(self) -> None:
        close = getattr(self.driver, "close", None)
        if callable(close):
            close()


def _records(result: object) -> list[dict[str, object]]:
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, list):
        raise GatewayError("driver returned an unsupported result shape")
    rows: list[dict[str, object]] = []
    for row in result:
        if isinstance(row, dict):
            rows.append(row)
        elif hasattr(row, "data"):
            data = row.data()
            if not isinstance(data, dict):
                raise GatewayError("driver row data() did not return a mapping")
            rows.append(data)
        else:
            raise GatewayError("driver row is not mapping-like")
    return rows


def _execute(
    driver: DriverLike,
    statement: str,
    parameters: dict[str, object],
) -> list[dict[str, object]]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            if isinstance(driver, SessionDriverLike):
                with driver.session() as session:
                    result = session.run(statement, parameters)
                    return _records(list(result))
            return _records(driver.execute_query(statement, parameters_=parameters))
        except Exception as exc:
            last_error = exc
            if attempt == 1 or not _is_retryable(exc):
                raise
    assert last_error is not None
    raise last_error


def _is_retryable(error: Exception) -> bool:
    """Retry transient Bolt failures once; the next session gets a fresh connection."""
    return type(error).__name__ in {"ServiceUnavailable", "SessionExpired"}


__all__ = ["GatewayError", "HydraGateway"]
