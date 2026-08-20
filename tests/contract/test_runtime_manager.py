from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from xray_runtime import GraphRuntimeManager, GraphRuntimeSpec
from xray_runtime.manager import RuntimeManifestError


def spec(**updates: object) -> GraphRuntimeSpec:
    values = {
        "runtime_id": "runtime-demo",
        "tenant_id": "tenant-a",
        "bucket_name": "xray-demo",
        "graph_namespace": "xray",
        "graph_id": "graph-demo",
        "graph_database": "xray",
        "object_prefix": "tenant-a/runtime-demo",
        "compose_project": "xray-runtime-demo",
        "bolt_port": 17687,
        "http_port": 18443,
        "admin_port": 19090,
        "indexer_admin_port": 19091,
        "minio_api_port": 19000,
        "minio_console_port": 19001,
    }
    values.update(updates)
    return GraphRuntimeSpec.model_validate(values)


@pytest.mark.parametrize(
    "updates",
    [
        {"runtime_id": "Bad_Name"},
        {"object_prefix": "../escape"},
        {"object_prefix": "tenant-a//bad"},
        {"bolt_port": 80},
        {"http_port": 17687},
    ],
)
def test_runtime_spec_rejects_unsafe_values(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        spec(**updates)


def test_prepare_writes_manifest_env_and_secret_files(tmp_path: Path) -> None:
    manager = GraphRuntimeManager(runtime_root=tmp_path)
    handle = manager.prepare(spec())

    assert handle.runtime_dir == tmp_path / "runtime-demo"
    assert handle.env_file.exists()
    assert (handle.runtime_dir / "hydra-auth-token").read_text(encoding="utf-8").strip()
    assert (handle.runtime_dir / "minio-root-user").read_text(encoding="utf-8").strip()
    assert (handle.runtime_dir / "minio-root-password").read_text(encoding="utf-8").strip()
    # HydraDB containers run as UID 10001; secrets must be other-readable on Linux.
    for name in ("hydra-auth-token", "minio-root-user", "minio-root-password"):
        mode = (handle.runtime_dir / name).stat().st_mode & 0o777
        assert mode & 0o004, f"{name} must be other-readable, got {mode:o}"
    env_text = handle.env_file.read_text(encoding="utf-8")
    assert "XRAY_RUNTIME_ID=runtime-demo" in env_text
    assert "XRAY_COMPOSE_PROJECT=xray-runtime-demo" in env_text
    assert "XRAY_GRAPH_DATA_PATH=xray-demo/tenant-a/runtime-demo/xray/graph-demo" in env_text
    manager.verify(handle)


def test_manifest_hash_fails_closed_on_tampering(tmp_path: Path) -> None:
    manager = GraphRuntimeManager(runtime_root=tmp_path)
    handle = manager.prepare(spec())
    manifest_path = handle.runtime_dir / "runtime-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["compose_project"] = "xray-other"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeManifestError):
        manager.verify(handle)
