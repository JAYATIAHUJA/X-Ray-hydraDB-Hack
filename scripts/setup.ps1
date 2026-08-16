param(
    [switch]$CoreOnly,
    [string]$RuntimeId = "runtime-demo",
    [string]$Project = "xray-runtime-demo",
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$startedAt = Get-Date
$runtimeDir = "infra/runtime/$RuntimeId"

uv run python -m xray_runtime.manager start --runtime-id $RuntimeId --compose-project $Project
uv sync

if ($CoreOnly) {
    Write-Host "HydraDB runtime is live. Env file: $runtimeDir/compose.env"
    exit 0
}

$env:XRAY_HYDRA_URI = "bolt://127.0.0.1:17687"
$env:XRAY_HYDRA_DATABASE = "xray"
$env:VITE_XRAY_API_BASE_URL = "http://127.0.0.1:$ApiPort"

$api = Start-Process -FilePath "uv" `
    -ArgumentList @("run", "uvicorn", "xray_api.app:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -RedirectStandardOutput "$runtimeDir/api.log" `
    -RedirectStandardError "$runtimeDir/api.err.log" `
    -PassThru `
    -WindowStyle Hidden
$api.Id | Set-Content -Encoding ascii "$runtimeDir/api.pid"

$deadline = (Get-Date).AddSeconds(90)
do {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 2 | Out-Null
        break
    } catch {
        Start-Sleep -Seconds 1
    }
} while ((Get-Date) -lt $deadline)

if ((Get-Date) -ge $deadline) {
    throw "timed out waiting for API health"
}

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiPort/api/v1/hydra/seed-fixture" | ConvertTo-Json -Depth 8

npm install
$web = Start-Process -FilePath "npm" `
    -ArgumentList @("run", "dev", "--", "--port", "$WebPort") `
    -RedirectStandardOutput "$runtimeDir/web.log" `
    -RedirectStandardError "$runtimeDir/web.err.log" `
    -PassThru `
    -WindowStyle Hidden
$web.Id | Set-Content -Encoding ascii "$runtimeDir/web.pid"

$elapsed = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
Write-Host "X-Ray is running in ${elapsed}s"
Write-Host "API: http://127.0.0.1:$ApiPort/api/v1/health"
Write-Host "Web: http://127.0.0.1:$WebPort"
Write-Host "Teardown: scripts/teardown.ps1 -RuntimeId $RuntimeId"
