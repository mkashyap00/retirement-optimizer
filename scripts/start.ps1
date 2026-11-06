# start.ps1 — one-command launcher for Retirement Optimizer (Windows / PowerShell)
# Usage:  .\scripts\start.ps1
# Requires: Python 3.12+, Node 20+
#
# If you see "running scripts is disabled on this system", run this once in an
# elevated PowerShell window:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# ── Ports ────────────────────────────────────────────────────────────────────
# Override the frontend port if 3000 is taken:  $env:PORT=3005; .\scripts\start.ps1
# The backend CORS origin is kept in sync automatically via FRONTEND_ORIGINS.
$FrontendPort = if ($env:PORT) { $env:PORT } else { "3000" }
$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$env:FRONTEND_ORIGINS = "http://localhost:$FrontendPort"

# ── Network exposure ────────────────────────────────────────────────────────
# The API has no authentication, so both servers listen on this machine only.
# $env:BIND_HOST="0.0.0.0" exposes every household to anyone who can reach the
# port — do that only on a network you trust completely.
$BindHost = if ($env:BIND_HOST) { $env:BIND_HOST } else { "127.0.0.1" }

# ── Python virtual environment ───────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
}

& ".venv\Scripts\Activate.ps1"

# Install backend if package is not importable
$null = python -c "import src.api.app" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend (pip install -e .)..."
    pip install -e . --quiet
}

# ── Frontend dependencies ────────────────────────────────────────────────────
# Also when the lockfile is newer than what npm last installed: otherwise a
# dependency upgrade pulled from git never reaches an existing checkout.
$installed = "frontend\node_modules\.package-lock.json"
if (-not (Test-Path "frontend\node_modules") -or -not (Test-Path $installed) -or
    (Get-Item "frontend\package-lock.json").LastWriteTime -gt (Get-Item $installed).LastWriteTime) {
    Write-Host "Installing frontend dependencies (npm ci)..."
    npm ci --prefix frontend --silent
}

# ── Launch servers ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting backend  -> http://localhost:$BackendPort"
$BackendJob = Start-Job -ScriptBlock {
    Set-Location $using:RepoRoot
    & ".venv\Scripts\Activate.ps1"
    $env:FRONTEND_ORIGINS = "http://localhost:$($using:FrontendPort)"
    uvicorn src.api.app:create_app --factory --port $using:BackendPort --host $using:BindHost
}

Write-Host "Building frontend (production mode)..."
Remove-Item -Path "$RepoRoot\frontend\.next" -Recurse -Force -ErrorAction SilentlyContinue
npm run build --prefix frontend --silent

Write-Host "Starting frontend -> http://localhost:$FrontendPort"
$FrontendJob = Start-Job -ScriptBlock {
    Set-Location "$using:RepoRoot\frontend"
    npm run start -- -p $using:FrontendPort -H $using:BindHost
}

Write-Host ""
Write-Host "Both servers are running."
Write-Host "  API docs : http://localhost:$BackendPort/docs"
Write-Host "  App      : http://localhost:$FrontendPort"
Write-Host ""
Write-Host "Press Ctrl+C to stop."

try {
    while ($true) {
        Start-Sleep -Seconds 2
        Receive-Job $BackendJob, $FrontendJob -ErrorAction SilentlyContinue | Write-Host
    }
} finally {
    Stop-Job $BackendJob, $FrontendJob -ErrorAction SilentlyContinue
    Remove-Job $BackendJob, $FrontendJob -ErrorAction SilentlyContinue
    Write-Host "Servers stopped."
}
