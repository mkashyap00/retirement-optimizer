# API CRUD Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four review findings in the FastAPI CRUD layer: DB lifespan teardown, transactional writes, PUT route, and deprecation-warning noise.

**Architecture:** All changes are within the existing FastAPI + DuckDB stack. The lifespan pattern moves DB connect/close into FastAPI's startup/shutdown. Transactions use explicit `BEGIN`/`COMMIT`/`ROLLBACK` via the existing `db.execute` wrapper. PUT is a transactional replace (delete-then-reinsert children).

**Tech Stack:** FastAPI 0.115+, DuckDB 1.0+, Pydantic v2, pytest 8+

## Global Constraints

- Python 3.11+
- All tests pass via `pytest backend/tests/integration/test_api_crud.py -q` with **zero warnings**
- `ruff check backend/` must pass
- Single commit: `fix(api): lifespan teardown, transactional writes, PUT route`

---

### Task 1: DB lifespan teardown in app.py

**Files:**
- Modify: `backend/src/api/app.py`

**Interfaces:**
- Produces: `create_app(db_path) -> FastAPI` — same signature, now uses `lifespan` parameter; `app.state.db` is set during startup and closed during shutdown

- [ ] **Step 1: Rewrite app.py with lifespan**

Replace the current `create_app` body. Move `db = Database(db_path); db.connect(); app.state.db = db` into an `asynccontextmanager` lifespan that yields and then calls `app.state.db.close()`.

- [ ] **Step 2: Verify existing tests still pass**

Run: `source .venv/bin/activate && pytest backend/tests/integration/test_api_crud.py -q`

---

### Task 2: Transactional CREATE in households.py

**Files:**
- Modify: `backend/src/api/endpoints/households.py` (`create_household` function only)

**Interfaces:**
- Same POST behaviour; on any INSERT failure → 500 HTTPException, DB state is clean (no orphan rows)

- [ ] **Step 1: Wrap INSERTs in BEGIN/COMMIT/ROLLBACK**

Inside `create_household`, wrap all five `db.execute(...)` calls in `try: db.execute("BEGIN TRANSACTION") ... db.execute("COMMIT") except Exception as exc: db.execute("ROLLBACK"); raise HTTPException(500)`.

- [ ] **Step 2: Run tests**

Run: `source .venv/bin/activate && pytest backend/tests/integration/test_api_crud.py -q`

---

### Task 3: PUT /households/{id} route

**Files:**
- Modify: `backend/src/api/endpoints/households.py` (add `update_household` function)

**Interfaces:**
- `PUT /households/{household_id}` accepts `HouseholdPayload`, returns `{"household_id": id}` 200, or 404 if missing; transactional replace (delete child rows, UPDATE household row + `updated_at`, re-insert accounts/income/settings)

- [ ] **Step 1: Add PUT handler**

After the existing GET handler, add `@router.put("/{household_id}")` that: (a) 404 if id missing, (b) BEGIN TRANSACTION, (c) DELETE runs/settings/income_sources/accounts for that id, (d) UPDATE households row, (e) INSERT accounts/income/settings from payload, (f) COMMIT; ROLLBACK + HTTPException 500 on any error.

- [ ] **Step 2: Run tests**

Run: `source .venv/bin/activate && pytest backend/tests/integration/test_api_crud.py -q`

---

### Task 4: Filter deprecation warning in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add filterwarnings**

In `[tool.pytest.ini_options]`, add:
```toml
filterwarnings = [
    "ignore:Using `httpx` with `starlette\\.testclient` is deprecated"
]
```

- [ ] **Step 2: Verify zero warnings**

Run: `source .venv/bin/activate && pytest backend/tests/integration/test_api_crud.py -q`
Expected: N passed, **no warnings summary**.

---

### Task 5: Add new tests (TDD for PUT and transaction)

**Files:**
- Modify: `backend/tests/integration/test_api_crud.py`

- [ ] **Step 1: Add PUT roundtrip test**

```python
def test_put_roundtrip_updates_fields_and_no_duplicate_rows(client):
    resp = client.post("/households", json=_PAYLOAD)
    hh_id = resp.json()["household_id"]
    import copy
    updated = copy.deepcopy(_PAYLOAD)
    updated["settings"]["required_spending"] = 90000.0
    updated["accounts"].append({"account_type": "roth", "owner": "self", "balance": 50000.0})
    put_resp = client.put(f"/households/{hh_id}", json=updated)
    assert put_resp.status_code == 200
    assert put_resp.json() == {"household_id": hh_id}
    body = client.get(f"/households/{hh_id}").json()
    assert body["settings"]["required_spending"] == pytest.approx(90000.0)
    assert len(body["accounts"]) == 4
```

- [ ] **Step 2: Add PUT missing id test**

```python
def test_put_missing_household_returns_404(client):
    resp = client.put("/households/00000000-0000-0000-0000-000000000000", json=_PAYLOAD)
    assert resp.status_code == 404
```

- [ ] **Step 3: Add transaction rollback test**

```python
def test_create_transaction_rolls_back_on_settings_failure(monkeypatch):
    from src.api.app import create_app
    from src.data.database import Database
    app = create_app(":memory:")
    original_execute = Database.execute
    def failing_execute(self, sql, params=None):
        if "INSERT INTO settings" in sql:
            raise RuntimeError("simulated settings failure")
        return original_execute(self, sql, params)
    monkeypatch.setattr(Database, "execute", failing_execute)
    with TestClient(app) as c:
        resp = c.post("/households", json=_PAYLOAD)
        assert resp.status_code == 500
        items = c.get("/households").json()
        assert items == []
```

- [ ] **Step 4: Run all tests — verify pass + zero warnings**

Run: `source .venv/bin/activate && pytest backend/tests/integration/test_api_crud.py -q`
Expected: 12 passed, 0 warnings.

- [ ] **Step 5: Run full suite + ruff**

Run: `source .venv/bin/activate && pytest -q && ruff check backend/`
Expected: all pass, 0 warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/src/api/app.py backend/src/api/endpoints/households.py backend/tests/integration/test_api_crud.py pyproject.toml
git commit -m "fix(api): lifespan teardown, transactional writes, PUT route"
```
