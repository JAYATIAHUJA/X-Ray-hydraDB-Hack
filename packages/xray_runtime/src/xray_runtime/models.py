from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
OBJECT_PREFIX = re.compile(r"^[a-z0-9][a-z0-9./-]*[a-z0-9]$")

type Port = Annotated[int, Field(strict=True, ge=1024, le=65535)]


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class GraphRuntimeSpec(RuntimeModel):
    runtime_id: str
    tenant_id: str
    bucket_name: str
    graph_namespace: str
    graph_id: str
    graph_database: str
    object_prefix: str
    compose_project: str
    bolt_port: Port
    http_port: Port
    admin_port: Port
    indexer_admin_port: Port
    minio_api_port: Port
    minio_console_port: Port

    @field_validator(
        "runtime_id",
        "tenant_id",
        "bucket_name",
        "graph_namespace",
        "graph_id",
        "graph_database",
        "compose_project",
    )
    @classmethod
    def validate_safe_name(cls, value: str) -> str:
        if SAFE_NAME.fullmatch(value) is None:
            raise ValueError("value must be lowercase DNS-safe")
        if value in {"default", "latest", "active", "old", "green"}:
            raise ValueError("reserved runtime identifier")
        return value

    @field_validator("object_prefix")
    @classmethod
    def validate_object_prefix(cls, value: str) -> str:
        if (
            OBJECT_PREFIX.fullmatch(value) is None
            or ".." in value
            or "//" in value
            or value.startswith("/")
            or value.endswith("/")
            or "\\" in value
        ):
            raise ValueError("object_prefix must be normalized and relative")
        return value

    @model_validator(mode="after")
    def validate_unique_ports(self) -> Self:
        ports = (
            self.bolt_port,
            self.http_port,
            self.admin_port,
            self.indexer_admin_port,
            self.minio_api_port,
            self.minio_console_port,
        )
        if len(ports) != len(set(ports)):
            raise ValueError("runtime ports must be unique")
        return self


class RenderedRuntime(RuntimeModel):
    spec: GraphRuntimeSpec
    runtime_dir: Path
    env_file: Path
    graph_data_path: str
    compose_files: tuple[Path, ...]


class GraphRuntimeHandle(RuntimeModel):
    runtime_id: str
    tenant_id: str
    compose_project: str
    runtime_dir: Path
    env_file: Path
    manifest_sha256: str
    bolt_endpoint: str
    http_endpoint: str
    admin_endpoint: str
    indexer_admin_endpoint: str
    image_digests: dict[str, str]

    @classmethod
    def from_manifest(cls, path: Path) -> GraphRuntimeHandle:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(payload)


def manifest_hash(payload: dict[str, object]) -> str:
    without_hash = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    encoded = json.dumps(without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "GraphRuntimeHandle",
    "GraphRuntimeSpec",
    "RenderedRuntime",
    "manifest_hash",
]
