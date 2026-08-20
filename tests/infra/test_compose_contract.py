from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from xray_runtime import GraphRuntimeManager, GraphRuntimeSpec, RuntimeCollisionError


def load_compose() -> dict[str, object]:
    return yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))


def locked_hydra_image() -> str:
    lock = yaml.safe_load(Path("infra/runtime-images.lock").read_text(encoding="utf-8"))
    hydra = lock["images"]["hydradb"]
    return f"{hydra['repository']}@{hydra['digest']}"


def locked_image(name: str) -> str:
    lock = yaml.safe_load(Path("infra/runtime-images.lock").read_text(encoding="utf-8"))
    image = lock["images"][name]
    return f"{image['repository']}@{image['digest']}"


def runtime_spec(
    runtime_id: str,
    *,
    project: str,
    object_prefix: str,
    ports: tuple[int, int, int, int, int, int],
) -> GraphRuntimeSpec:
    return GraphRuntimeSpec(
        runtime_id=runtime_id,
        tenant_id="tenant-a",
        bucket_name="xray-demo",
        graph_namespace="xray",
        graph_id=runtime_id,
        graph_database="xray",
        object_prefix=object_prefix,
        compose_project=project,
        bolt_port=ports[0],
        http_port=ports[1],
        admin_port=ports[2],
        indexer_admin_port=ports[3],
        minio_api_port=ports[4],
        minio_console_port=ports[5],
    )


def test_hydradb_is_immutable_and_stack_safe() -> None:
    compose = load_compose()
    services = compose["services"]
    hydra = services["hydradb"]
    secrets_init = services["hydra-secrets-init"]

    assert services["minio"]["image"] == "${XRAY_MINIO_IMAGE}"
    assert hydra["image"] == "${XRAY_HYDRA_IMAGE}"
    assert services["hydradb-indexer"]["image"] == "${XRAY_HYDRA_IMAGE}"
    assert locked_hydra_image().startswith("ghcr.io/hydra-db/hydradb@sha256:")
    assert locked_image("minio").startswith("minio/minio@sha256:")
    assert hydra["environment"]["RUST_MIN_STACK"] == "33554432"
    assert {"minio", "minio-init", "hydra-secrets-init", "hydradb", "hydradb-indexer"} <= set(
        services
    )
    assert secrets_init["user"] == "0:0"
    assert hydra["environment"]["GRAPH_AUTH_TOKEN_FILE"] == (
        "/var/run/hydra-secrets/hydra-auth-token"
    )
    assert "hydra-auth-token-data:/var/run/hydra-secrets:ro" in hydra["volumes"]
    assert "secrets" not in hydra
    assert "${XRAY_HYDRA_IMAGE}" in {
        service["image"] for service in services.values() if "image" in service
    }
    assert services["hydradb-indexer"]["entrypoint"] == ["/usr/local/bin/graph-indexer"]
    for published in hydra["ports"]:
        assert published.startswith("127.0.0.1:")
    for published in services["hydradb-indexer"]["ports"]:
        assert published.startswith("127.0.0.1:")
    for published in services["minio"]["ports"]:
        assert published.startswith("127.0.0.1:")


def test_runtime_specs_cannot_alias_graph_state(tmp_path: Path) -> None:
    old = runtime_spec(
        "runtime-old",
        project="xray-old",
        object_prefix="tenant-a/old",
        ports=(17687, 18443, 19090, 19091, 19000, 19001),
    )
    green = runtime_spec(
        "runtime-green",
        project="xray-green",
        object_prefix="tenant-a/green",
        ports=(27687, 28443, 29090, 29091, 29000, 29001),
    )
    manager = GraphRuntimeManager(runtime_root=tmp_path)

    assert manager.render(old).graph_data_path != manager.render(green).graph_data_path
    manager.reserve(old)
    manager.reserve(green)
    with pytest.raises(RuntimeCollisionError):
        manager.reserve(old.model_copy(update={"compose_project": "xray-green"}))
    with pytest.raises(RuntimeCollisionError):
        manager.reserve(
            green.model_copy(
                update={
                    "runtime_id": "runtime-third",
                    "compose_project": "xray-third",
                    "object_prefix": "tenant-a/old",
                    "graph_id": "runtime-old",
                }
            )
        )
