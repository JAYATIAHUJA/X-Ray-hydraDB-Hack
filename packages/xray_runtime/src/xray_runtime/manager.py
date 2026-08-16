from __future__ import annotations

import argparse
import json
import secrets
import shutil
import stat
import subprocess
from pathlib import Path

from .models import GraphRuntimeHandle, GraphRuntimeSpec, RenderedRuntime, manifest_hash


class RuntimeCollisionError(ValueError):
    """Raised when two runtime specs would alias graph state."""


class RuntimeManifestError(ValueError):
    """Raised when a runtime handle or manifest fails validation."""


class GraphRuntimeManager:
    def __init__(
        self,
        *,
        runtime_root: Path = Path("infra/runtime"),
        compose_files: tuple[Path, ...] = (Path("compose.yaml"), Path("compose.test.yaml")),
    ) -> None:
        self.runtime_root = runtime_root
        self.compose_files = compose_files
        self._reserved_projects: dict[str, str] = {}
        self._reserved_prefixes: dict[tuple[str, str, str], str] = {}

    def render(self, spec: GraphRuntimeSpec) -> RenderedRuntime:
        runtime_dir = self.runtime_root / spec.runtime_id
        return RenderedRuntime(
            spec=spec,
            runtime_dir=runtime_dir,
            env_file=runtime_dir / "compose.env",
            graph_data_path=f"{spec.bucket_name}/{spec.object_prefix}/{spec.graph_namespace}/{spec.graph_id}",
            compose_files=self.compose_files,
        )

    def reserve(self, spec: GraphRuntimeSpec) -> RenderedRuntime:
        rendered = self.render(spec)
        project_owner = self._reserved_projects.get(spec.compose_project)
        if project_owner is not None and project_owner != spec.runtime_id:
            raise RuntimeCollisionError("compose project is already reserved")

        graph_key = (spec.bucket_name, spec.object_prefix, spec.graph_id)
        graph_owner = self._reserved_prefixes.get(graph_key)
        if graph_owner is not None and graph_owner != spec.runtime_id:
            raise RuntimeCollisionError("graph object state is already reserved")

        self._reserved_projects[spec.compose_project] = spec.runtime_id
        self._reserved_prefixes[graph_key] = spec.runtime_id
        return rendered

    def prepare(self, spec: GraphRuntimeSpec) -> GraphRuntimeHandle:
        rendered = self.reserve(spec)
        rendered.runtime_dir.mkdir(parents=True, exist_ok=False)
        (rendered.runtime_dir / ".xray-runtime").write_text(spec.runtime_id, encoding="utf-8")
        hydra_token = secrets.token_urlsafe(48)
        minio_user = f"xray-{spec.runtime_id}"
        minio_password = secrets.token_urlsafe(48)
        self._write_secret(rendered.runtime_dir / "hydra-auth-token", hydra_token)
        self._write_secret(rendered.runtime_dir / "minio-root-user", minio_user)
        self._write_secret(rendered.runtime_dir / "minio-root-password", minio_password)
        self._write_env(rendered, minio_user, minio_password)
        return self._write_manifest(rendered)

    def start(self, spec: GraphRuntimeSpec) -> GraphRuntimeHandle:
        handle = self.prepare(spec)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(handle.env_file),
            "-p",
            handle.compose_project,
        ]
        for compose_file in self.compose_files:
            command.extend(("-f", str(compose_file)))
        command.extend(("--profile", "core", "up", "-d", "--wait"))
        subprocess.run(command, check=True)
        return handle

    def verify(self, handle: GraphRuntimeHandle) -> None:
        sentinel = handle.runtime_dir / ".xray-runtime"
        if not sentinel.exists() or sentinel.read_text(encoding="utf-8") != handle.runtime_id:
            raise RuntimeManifestError("runtime sentinel mismatch")
        manifest_path = handle.runtime_dir / "runtime-manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_hash(payload) != handle.manifest_sha256:
            raise RuntimeManifestError("runtime manifest hash mismatch")

    def stop(self, handle: GraphRuntimeHandle, *, remove_volumes: bool = False) -> None:
        self.verify(handle)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(handle.env_file),
            "-p",
            handle.compose_project,
        ]
        for compose_file in self.compose_files:
            command.extend(("-f", str(compose_file)))
        command.append("down")
        if remove_volumes:
            command.append("--volumes")
        subprocess.run(command, check=True)

    def _write_secret(self, path: Path, value: str) -> None:
        path.write_text(f"{value}\n", encoding="utf-8", newline="\n")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def _write_env(self, rendered: RenderedRuntime, access_key: str, secret_key: str) -> None:
        spec = rendered.spec
        hydra_image = _locked_hydra_image()
        minio_image = _locked_image("minio")
        values = {
            "XRAY_RUNTIME_ID": spec.runtime_id,
            "XRAY_TENANT_ID": spec.tenant_id,
            "XRAY_BUCKET_NAME": spec.bucket_name,
            "XRAY_GRAPH_NAMESPACE": spec.graph_namespace,
            "XRAY_GRAPH_ID": spec.graph_id,
            "XRAY_GRAPH_DATABASE": spec.graph_database,
            "XRAY_OBJECT_PREFIX": spec.object_prefix,
            "XRAY_GRAPH_DATA_PATH": rendered.graph_data_path,
            "XRAY_COMPOSE_PROJECT": spec.compose_project,
            "XRAY_BOLT_PORT": str(spec.bolt_port),
            "XRAY_HTTP_PORT": str(spec.http_port),
            "XRAY_ADMIN_PORT": str(spec.admin_port),
            "XRAY_INDEXER_ADMIN_PORT": str(spec.indexer_admin_port),
            "XRAY_MINIO_API_PORT": str(spec.minio_api_port),
            "XRAY_MINIO_CONSOLE_PORT": str(spec.minio_console_port),
            "XRAY_RUNTIME_DIR": rendered.runtime_dir.as_posix(),
            "XRAY_HYDRA_IMAGE": hydra_image,
            "XRAY_MINIO_IMAGE": minio_image,
            "AWS_ACCESS_KEY_ID": access_key,
            "AWS_SECRET_ACCESS_KEY": secret_key,
        }
        rendered.env_file.write_text(
            "".join(f"{key}={value}\n" for key, value in values.items()),
            encoding="utf-8",
            newline="\n",
        )
        rendered.env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def _write_manifest(self, rendered: RenderedRuntime) -> GraphRuntimeHandle:
        spec = rendered.spec
        image_digests = {"hydradb": _locked_hydra_image(), "minio": _locked_image("minio")}
        payload: dict[str, object] = {
            "runtime_id": spec.runtime_id,
            "tenant_id": spec.tenant_id,
            "compose_project": spec.compose_project,
            "runtime_dir": str(rendered.runtime_dir),
            "env_file": str(rendered.env_file),
            "bolt_endpoint": f"bolt://127.0.0.1:{spec.bolt_port}",
            "http_endpoint": f"http://127.0.0.1:{spec.http_port}",
            "admin_endpoint": f"http://127.0.0.1:{spec.admin_port}",
            "indexer_admin_endpoint": f"http://127.0.0.1:{spec.indexer_admin_port}",
            "image_digests": image_digests,
        }
        payload["manifest_sha256"] = manifest_hash(payload)
        manifest_path = rendered.runtime_dir / "runtime-manifest.json"
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return GraphRuntimeHandle.model_validate(payload)


def _load_handle(runtime_root: Path, runtime_id: str) -> GraphRuntimeHandle:
    return GraphRuntimeHandle.from_manifest(runtime_root / runtime_id / "runtime-manifest.json")


def _locked_hydra_image(lock_path: Path = Path("infra/runtime-images.lock")) -> str:
    return _locked_image("hydradb", lock_path)


def _locked_image(name: str, lock_path: Path = Path("infra/runtime-images.lock")) -> str:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    image = payload["images"][name]
    return f"{image['repository']}@{image['digest']}"


def _default_spec(runtime_id: str) -> GraphRuntimeSpec:
    return GraphRuntimeSpec(
        runtime_id=runtime_id,
        tenant_id="tenant-a",
        bucket_name="xray-demo",
        graph_namespace="xray",
        graph_id=runtime_id,
        graph_database="xray",
        object_prefix=f"tenant-a/{runtime_id}",
        compose_project=f"xray-{runtime_id}",
        bolt_port=17687,
        http_port=18443,
        admin_port=19090,
        indexer_admin_port=19091,
        minio_api_port=19000,
        minio_console_port=19001,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start")
    start.add_argument("--runtime-id", required=True)
    start.add_argument("--runtime-root", default="infra/runtime")
    start.add_argument("--tenant-id", default="tenant-a")
    start.add_argument("--bucket-name", default="xray-demo")
    start.add_argument("--graph-namespace", default="xray")
    start.add_argument("--graph-id")
    start.add_argument("--graph-database", default="xray")
    start.add_argument("--object-prefix")
    start.add_argument("--compose-project")
    start.add_argument("--bolt-port", type=int, default=17687)
    start.add_argument("--http-port", type=int, default=18443)
    start.add_argument("--admin-port", type=int, default=19090)
    start.add_argument("--indexer-admin-port", type=int, default=19091)
    start.add_argument("--minio-api-port", type=int, default=19000)
    start.add_argument("--minio-console-port", type=int, default=19001)
    stop = subcommands.add_parser("stop")
    stop.add_argument("--runtime-id", required=True)
    stop.add_argument("--runtime-root", default="infra/runtime")
    stop.add_argument("--remove-volumes", action="store_true")
    stop.add_argument("--purge-local", action="store_true")
    args = parser.parse_args()

    if args.command == "start":
        runtime_root = Path(args.runtime_root)
        defaults = _default_spec(args.runtime_id)
        spec = GraphRuntimeSpec(
            runtime_id=args.runtime_id,
            tenant_id=args.tenant_id,
            bucket_name=args.bucket_name,
            graph_namespace=args.graph_namespace,
            graph_id=args.graph_id or defaults.graph_id,
            graph_database=args.graph_database,
            object_prefix=args.object_prefix or defaults.object_prefix,
            compose_project=args.compose_project or defaults.compose_project,
            bolt_port=args.bolt_port,
            http_port=args.http_port,
            admin_port=args.admin_port,
            indexer_admin_port=args.indexer_admin_port,
            minio_api_port=args.minio_api_port,
            minio_console_port=args.minio_console_port,
        )
        handle = GraphRuntimeManager(runtime_root=runtime_root).start(spec)
        print(handle.model_dump_json(indent=2))
    elif args.command == "stop":
        runtime_root = Path(args.runtime_root)
        handle = _load_handle(runtime_root, args.runtime_id)
        manager = GraphRuntimeManager(runtime_root=runtime_root)
        manager.stop(handle, remove_volumes=args.remove_volumes)
        if args.purge_local:
            manager.verify(handle)
            shutil.rmtree(handle.runtime_dir)


if __name__ == "__main__":
    main()


__all__ = [
    "GraphRuntimeManager",
    "RuntimeCollisionError",
    "RuntimeManifestError",
]
