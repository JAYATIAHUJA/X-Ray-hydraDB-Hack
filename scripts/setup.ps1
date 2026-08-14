param(
    [switch]$CoreOnly,
    [Parameter(Mandatory=$true)][string]$RuntimeId,
    [Parameter(Mandatory=$true)][string]$Project,
    [string]$TenantId = "demo",
    [string]$BucketName = "xray-demo",
    [string]$GraphNamespace = "xray",
    [string]$GraphId = "xray-demo",
    [string]$GraphDatabase = "xray",
    [string]$ObjectPrefix = "demo/xray-demo",
    [int]$BoltPort = 17687,
    [int]$HttpPort = 18443,
    [int]$AdminPort = 19090,
    [int]$IndexerAdminPort = 19091,
    [int]$MinioApiPort = 19000,
    [int]$MinioConsolePort = 19001
)

$ErrorActionPreference = "Stop"

@"
from pathlib import Path
from xray_runtime import GraphRuntimeManager, GraphRuntimeSpec

spec = GraphRuntimeSpec(
    runtime_id="$RuntimeId",
    tenant_id="$TenantId",
    bucket_name="$BucketName",
    graph_namespace="$GraphNamespace",
    graph_id="$GraphId",
    graph_database="$GraphDatabase",
    object_prefix="$ObjectPrefix",
    compose_project="$Project",
    bolt_port=$BoltPort,
    http_port=$HttpPort,
    admin_port=$AdminPort,
    indexer_admin_port=$IndexerAdminPort,
    minio_api_port=$MinioApiPort,
    minio_console_port=$MinioConsolePort,
)
handle = GraphRuntimeManager(runtime_root=Path("infra/runtime")).prepare(spec)
print(handle.env_file)
"@ | uv run python -

if ($CoreOnly) {
    Write-Host "Runtime prepared for core profile: $RuntimeId"
}
