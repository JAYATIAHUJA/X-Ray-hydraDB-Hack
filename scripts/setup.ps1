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
$envFile = "$runtimeDir/compose.env"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not ready. Start Docker Desktop and wait until 'docker info' succeeds."
}

uv sync --locked

if (Test-Path $envFile) {
    docker compose --env-file $envFile -p $Project -f compose.yaml -f compose.test.yaml --profile core up -d --wait
} else {
    uv run python -m xray_runtime.manager start --runtime-id $RuntimeId --compose-project $Project
}
if ($CoreOnly) {
    Write-Host "HydraDB runtime is live. Env file: $runtimeDir/compose.env"
    exit 0
}

$env:XRAY_HYDRA_URI = "bolt://127.0.0.1:17687"
$env:XRAY_HYDRA_USER = "neo4j"
$env:XRAY_HYDRA_PASSWORD = (Get-Content -Raw "$runtimeDir/hydra-auth-token").Trim()
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

$seed = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiPort/api/v1/hydra/seed-fixture"
if ($seed.status -ne "complete") {
    throw "HydraDB seed did not complete: $($seed.detail)"
}
$seed | ConvertTo-Json -Depth 8

uv run python scripts/verify_judge_demo.py --api-base "http://127.0.0.1:$ApiPort"
uv run python scripts/bench_judge_latency.py

npm ci
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
