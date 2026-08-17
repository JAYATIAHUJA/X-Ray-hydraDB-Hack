from __future__ import annotations

from xray_hydra import HydraGateway, edge_upsert_batch


class FakeDriver:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append((query_, parameters_))
        return self.responses.pop(0)


def test_run_batch_sends_rows_as_one_parameter() -> None:
    driver = FakeDriver([[{"count": 2}]])
    gateway = HydraGateway(driver)
    batch = edge_upsert_batch(
        "COMMUNICATES",
        (
            {
                "id": 7,
                "source_id": 1,
                "target_id": 2,
                "canonical_key": "communicates:a:b:aggregate",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
            {
                "id": 8,
                "source_id": 2,
                "target_id": 3,
                "canonical_key": "communicates:b:c:aggregate",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
        ),
        source_label="Person",
        target_label="Person",
    )

    assert gateway.run_batch(batch) == [{"count": 2}]
    assert driver.calls[0][1] == {"rows": [dict(row) for row in batch.rows]}
