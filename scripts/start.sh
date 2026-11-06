#!/usr/bin/env bash
# start.sh — one-command launcher for Retirement Optimizer
# Usage:  bash scripts/start.sh
# Requires: Python 3.12+, Node 20+
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Ports ────────────────────────────────────────────────────────────────────
# Override the frontend port if 3000 is taken:  PORT=3005 bash scripts/start.sh
# The backend CORS origin is kept in sync automatically via FRONTEND_ORIGINS.
FRONTEND_PORT="${PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_ORIGINS="http://localhost:${FRONTEND_PORT}"

# ── Network exposure ────────────────────────────────────────────────────────
# The API has no authentication, so both servers listen on this machine only.
# BIND_HOST=0.0.0.0 exposes every household to anyone who can reach the port —
# do that only on a network you trust completely.
BIND_HOST="${BIND_HOST:-127.0.0.1}"

# ── Port guard ───────────────────────────────────────────────────────────────
# A process already listening on our ports means a STALE server would keep
# answering requests with old code while the new one dies with EADDRINUSE —
# the single most confusing failure mode this project has had. Refuse loudly.
for entry in "$BACKEND_PORT backend" "$FRONTEND_PORT frontend"; do
  port="${entry%% *}"; name="${entry##* }"
  holder="$(ss -tlnp 2>/dev/null | grep ":${port} " || true)"
  if [ -n "$holder" ]; then
    echo ""
    echo "ERROR: port ${port} (${name}) is already in use:"
    echo "  ${holder}"
    echo "A previously started server is still running — it would keep serving"
    echo "OLD code. Stop it first (kill <pid>), or choose another port:"
    echo "  PORT=3005 bash scripts/start.sh"
    exit 1
  fi
done

# ── Python virtual environment ───────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install backend if egg-link is absent (i.e., first run or after clean)
if ! python -c "import src.api.app" 2>/dev/null; then
  echo "Installing backend (pip install -e .)..."
  pip install -e . --quiet
fi

# ── Frontend dependencies ────────────────────────────────────────────────────
# Also when the lockfile is newer than what npm last installed: otherwise a
# dependency upgrade pulled from git never reaches an existing checkout.
if [ ! -d "frontend/node_modules" ] \
   || [ "frontend/package-lock.json" -nt "frontend/node_modules/.package-lock.json" ]; then
  echo "Installing frontend dependencies (npm ci)..."
  npm ci --prefix frontend --silent
fi

# ── Launch servers ───────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "Shutting down servers..."
  # Default-empty: the trap also runs when the frontend BUILD fails, at which
  # point FRONTEND_PID was never assigned. Under `set -u` a bare $FRONTEND_PID
  # aborts the trap with "unbound variable", which both hides the real build
  # error and leaves the backend running.
  kill ${BACKEND_PID:-} ${FRONTEND_PID:-} 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "Starting backend  → http://localhost:${BACKEND_PORT}"
uvicorn src.api.app:create_app --factory --port "$BACKEND_PORT" --host "$BIND_HOST" &
BACKEND_PID=$!

echo "Building frontend (production mode)..."
rm -rf frontend/.next
npm run build --prefix frontend --silent

echo "Starting frontend → http://localhost:${FRONTEND_PORT}"
npm run start --prefix frontend -- -p "$FRONTEND_PORT" -H "$BIND_HOST" &
FRONTEND_PID=$!

echo ""
echo "Both servers are running."
echo "  API docs : http://localhost:${BACKEND_PORT}/docs"
echo "  App      : http://localhost:${FRONTEND_PORT}"
echo ""
echo "Press Ctrl+C to stop."
wait
