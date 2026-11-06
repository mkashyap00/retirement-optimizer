"""Shared pytest configuration and fixtures for the retirement-optimizer test suite."""

import pytest


@pytest.fixture(autouse=True)
def _reports_to_tmp(tmp_path, monkeypatch):
    """Redirect server-side report auto-saves to a temp dir during tests.

    Without this, every optimize call in the integration suite would write
    CSV/PDF/XLSX files into the real reports/ directory.
    """
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))


def pytest_addoption(parser):
    parser.addoption(
        "--regen-golden",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of comparing against them.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with -m 'not slow')")
