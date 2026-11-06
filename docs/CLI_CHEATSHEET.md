# CLI Cheatsheet

All commands run from the project root: `~/projects/retirement-optimizer`

## Stop servers

```bash
# Kill backend + frontend
pkill -f uvicorn; pkill -f next-server

# Nuclear: kill anything on specific ports
fuser -k 8000/tcp 3005/tcp

# Check what's running on your ports
ss -tlnp | grep -E ':8000|:3005'
```

## Database

> **Stop the backend first.** DuckDB holds an exclusive file lock while
> uvicorn is running — you'll get an IO error if you don't.

```bash
# Purge all rows, keep schema (tables stay, data goes)
.venv/bin/python scripts/db_purge.py --yes

# Full reset: drop tables + recreate schema
.venv/bin/python scripts/db_reset.py --yes

# Interactive (asks for confirmation)
.venv/bin/python scripts/db_reset.py
```

## Start servers

```bash
# Production mode on port 3005 (builds frontend first)
PORT=3005 bash scripts/start.sh

# Dev mode with hot-reload on port 3005
PORT=3005 bash scripts/dev.sh

# Default ports (backend 8000, frontend 3000)
bash scripts/start.sh
```

## Common workflows

### Full reset & restart

```bash
pkill -f uvicorn; pkill -f next-server
.venv/bin/python scripts/db_reset.py --yes
PORT=3005 bash scripts/start.sh
```

### Quick purge (keep schema, just wipe data)

```bash
pkill -f uvicorn; pkill -f next-server
.venv/bin/python scripts/db_purge.py --yes
PORT=3005 bash scripts/start.sh
```

### Clear browser draft

Run in the browser console (DevTools → Console):

```js
localStorage.removeItem("wizard-draft")
location.reload()
```

The wizard persists form inputs in localStorage. A DB reset does not
clear them — this does. Drafts also auto-expire after 24 hours.

## Tests

```bash
# Backend (pytest, ~470 tests, ~90s)
.venv/bin/python -m pytest backend/tests -q

# Frontend (jest, ~170 tests, ~4s)
cd frontend && npx jest

# Regenerate golden test file after optimizer changes
.venv/bin/python -m pytest backend/tests/integration/test_golden_standard_household.py --regen-golden -q
```

## Diagnostics

```bash
# Python & DuckDB versions (for reproducibility)
.venv/bin/python -c "import sys,duckdb; print(sys.version); print(duckdb.__version__)"

# Current git commit
git rev-parse --short HEAD

# API health check
curl -s http://localhost:8000/docs | head -1
```
