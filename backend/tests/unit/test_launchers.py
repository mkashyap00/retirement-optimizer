"""The launchers must not expose the unauthenticated API to the network.

Every endpoint — household reads and deletes, portfolio replacement, report
downloads — is unauthenticated, which is fine only while nothing but this
machine can reach it. CORS does not help: it constrains browsers, not curl.
So both servers bind to loopback unless the user opts out with BIND_HOST.
"""
import re
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
_LAUNCHERS = ["start.sh", "dev.sh", "start.ps1"]


def _lines(name: str) -> list[str]:
    return [
        ln for ln in (_SCRIPTS / name).read_text().splitlines()
        if not ln.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("name", _LAUNCHERS)
def test_backend_never_binds_all_interfaces_by_default(name):
    uvicorn = [ln for ln in _lines(name) if "uvicorn " in ln]
    assert uvicorn, f"{name} no longer starts uvicorn — update this test"
    for ln in uvicorn:
        assert "0.0.0.0" not in ln, ln
        assert re.search(r"--host\s+\S*BIND_?HOST", ln, re.I), ln


@pytest.mark.parametrize("name", _LAUNCHERS)
def test_frontend_binds_the_same_host(name):
    # `next start`/`next dev` listen on every interface unless given -H.
    npm = [ln for ln in _lines(name) if re.search(r"npm run (start|dev)", ln)]
    assert npm, f"{name} no longer starts the frontend — update this test"
    for ln in npm:
        assert re.search(r"-H\s+\S*BIND_?HOST", ln, re.I), ln


@pytest.mark.parametrize("name", _LAUNCHERS)
def test_bind_host_defaults_to_loopback(name):
    text = (_SCRIPTS / name).read_text()
    assert re.search(r"BIND_HOST.*127\.0\.0\.1", text), name


@pytest.mark.parametrize("name", _LAUNCHERS)
def test_frontend_dependencies_are_reinstalled_when_the_lockfile_changes(name):
    """Installing only when node_modules is missing left an existing checkout
    on its old packages after a pull: a dependency upgrade (a security fix,
    say) never reached anyone who had run the app before."""
    install = [ln for ln in _lines(name) if "npm install" in ln or "npm ci" in ln]
    assert install, f"{name} no longer installs frontend dependencies"
    text = "\n".join(_lines(name))
    # The condition compares the lockfile with what npm last installed.
    assert "package-lock.json" in text, name
    assert re.search(r"node_modules[/\\]\.package-lock\.json", text), name
