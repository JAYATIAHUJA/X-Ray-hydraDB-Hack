param(
    [string]$RuntimeId = "runtime-demo",
    [switch]$RemoveVolumes
)

$ErrorActionPreference = "Stop"
$runtimeDir = "infra/runtime/$RuntimeId"

foreach ($name in @("api", "web")) {
    $pidFile = "$runtimeDir/$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile -Raw)
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $pidFile -Force
    }
}

if ($RemoveVolumes) {
    uv run python -m xray_runtime.manager stop --runtime-id $RuntimeId --remove-volumes
} else {
    uv run python -m xray_runtime.manager stop --runtime-id $RuntimeId
}
