"""Unit tests for the LLM narrative feature (TDD — written before implementation).

These tests are designed to pass WITHOUT the ``anthropic`` package installed.
All Anthropic-network calls are replaced by :class:`FakeClient`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.reports.llm_client import FakeClient, LLMClient  # noqa: F401
from src.reports.llm_narrative import build_prompt, generate_narrative

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_POLICY = {
    "policy_id": "fill_22",
    "lifetime_taxes_nominal": 420_000,
    "lifetime_taxes_pv": 310_000,
    "terminal_estate": 1_200_000,
    "success_probability": 0.92,
    "score": 0.85,
    "total_conversions": 90_000,
    "projected_future_marginal_rate": 0.28,
}

_YEAR_ROW = {
    "year": 2026,
    "age_self": 66,
    "conversion": 30_000,
    "total_tax": 12_000,
    "marginal_rate": 0.22,
    "net_spendable": 68_000,
    "balance_taxable": 100_000,
    "balance_traditional": 750_000,
    "balance_roth": 50_000,
}

_RESULT = {
    "winning_policy": _POLICY,
    "yearly_plan": [_YEAR_ROW],
    "warnings": ["Watch IRMAA tier in 2027"],
}


# ---------------------------------------------------------------------------
# FakeClient — verbatim passthrough
# ---------------------------------------------------------------------------


class TestFakeClient:
    def test_returns_canned_string(self) -> None:
        client = FakeClient("hello world")
        assert client.complete("sys", "usr") == "hello world"

    def test_records_last_system(self) -> None:
        client = FakeClient("x")
        client.complete("my system", "my user")
        assert client.last_system == "my system"

    def test_records_last_user(self) -> None:
        client = FakeClient("x")
        client.complete("my system", "my user")
        assert client.last_user == "my user"

    def test_fake_satisfies_protocol(self) -> None:
        client = FakeClient("x")
        assert isinstance(client, LLMClient)


# ---------------------------------------------------------------------------
# generate_narrative — prompt content checks
# ---------------------------------------------------------------------------


class TestGenerateNarrative:
    def test_returns_canned_text_verbatim(self) -> None:
        fake = FakeClient("Here is your plan summary.")
        result = generate_narrative(_RESULT, fake)
        assert result == "Here is your plan summary."

    def test_prompt_contains_lifetime_taxes_nominal(self) -> None:
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        assert "420,000" in fake.last_user  # type: ignore[arg-type]

    def test_prompt_contains_terminal_estate(self) -> None:
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        assert "1,200,000" in fake.last_user  # type: ignore[arg-type]

    def test_prompt_contains_year_row(self) -> None:
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        # Year column
        assert "2026" in fake.last_user  # type: ignore[arg-type]

    def test_prompt_contains_conversion_figure(self) -> None:
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        assert "30,000" in fake.last_user  # type: ignore[arg-type]

    def test_prompt_does_not_contain_birth(self) -> None:
        """Birth dates must never appear in the LLM prompt."""
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        assert "birth" not in (fake.last_user or "").lower()

    def test_warnings_flow_into_prompt_verbatim(self) -> None:
        """Verify warnings (first-party template strings) appear verbatim in prompt."""
        warning_text = "Watch IRMAA tier in 2027"
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        # Warning fixture string must appear in the captured prompt
        assert warning_text in (fake.last_user or "")
        # Verify that "birth" (PII) does not appear anywhere in the prompt
        assert "birth" not in (fake.last_user or "").lower()

    def test_system_prompt_default_contract(self, monkeypatch) -> None:
        """The default prompt must pin the two safety rules: numbers are
        ground truth (never computed by the model) and no investment advice."""
        monkeypatch.delenv("LLM_SYSTEM_PROMPT_FILE", raising=False)
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        system = fake.last_system or ""
        assert "only the numbers provided" in system
        assert "Do not give investment advice" in system

    def test_prompt_contains_warnings(self) -> None:
        fake = FakeClient("")
        generate_narrative(_RESULT, fake)
        assert "Watch IRMAA tier in 2027" in (fake.last_user or "")

    def test_empty_warnings_shows_none(self) -> None:
        result_no_warn = {**_RESULT, "warnings": []}
        fake = FakeClient("")
        generate_narrative(result_no_warn, fake)
        assert "None" in (fake.last_user or "")


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/narrative — API endpoint
# ---------------------------------------------------------------------------



class TestNarrativeEndpointNoKey:
    def test_returns_501_when_no_llm_configured(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.post("/runs/any-run-id/narrative")
        assert resp.status_code == 501
        assert "ANTHROPIC_API_KEY or LLM_BASE_URL" in resp.json()["detail"]


class TestNarrativeEndpointWithKey:
    def test_returns_404_for_missing_run(self, monkeypatch) -> None:
        import src.api.endpoints.reports as reports_mod

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: FakeClient("text"))
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.post("/runs/nonexistent-id/narrative")
        assert resp.status_code == 404

    def test_returns_narrative_for_existing_run(self, monkeypatch) -> None:
        import src.api.endpoints.reports as reports_mod

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake = FakeClient("Great strategy!")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: fake)

        app = create_app(":memory:")
        with TestClient(app) as c:
            # Seed a household + run
            payload = {
                "household": {
                    "filing_status": "single",
                    "self_birth_date": "1962-06-01",
                    "state": "TX",
                },
                "accounts": [
                    {"account_type": "traditional", "owner": "self", "balance": 400_000.0},
                ],
                "income": [],
                "settings": {
                    "required_spending": 50_000.0,
                    "ss_pia_self": 1800.0,
                },
                "constraints": {
                    "irmaa_policy": "soft",
                    "conversion_window": "anytime",
                },
            }
            hh_id = c.post("/households", json=payload).json()["household_id"]
            run_id = c.post(
                "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 1}
            ).json()["run_id"]

            resp = c.post(f"/runs/{run_id}/narrative")

        assert resp.status_code == 200
        assert resp.json()["narrative"] == "Great strategy!"


# ---------------------------------------------------------------------------
# GET /health — llm flag
# ---------------------------------------------------------------------------


class TestLoadEnv:
    """.env must reach the backend, or LLM_BASE_URL never arrives and the
    AI-summary button stays hidden despite a configured .env."""

    def test_load_env_populates_llm_base_url_from_file(self, tmp_path) -> None:
        from src.api import app as app_module

        # Snapshot/restore by hand: monkeypatch.delenv does NOT track a key
        # that was absent, so load_dotenv's new value would otherwise leak
        # into later tests.
        original = os.environ.pop("LLM_BASE_URL", None)
        try:
            env_file = tmp_path / ".env"
            env_file.write_text("LLM_BASE_URL=http://localhost:8080/v1\n")

            app_module._load_env(env_file)

            assert os.environ["LLM_BASE_URL"] == "http://localhost:8080/v1"
        finally:
            if original is None:
                os.environ.pop("LLM_BASE_URL", None)
            else:
                os.environ["LLM_BASE_URL"] = original

    def test_load_env_does_not_override_explicit_env(
        self, tmp_path, monkeypatch
    ) -> None:
        from src.api import app as app_module

        monkeypatch.setenv("LLM_BASE_URL", "http://explicit:9000/v1")
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_BASE_URL=http://from-file:8080/v1\n")

        app_module._load_env(env_file)

        # Explicitly exported env wins over the file (override=False).
        assert os.environ["LLM_BASE_URL"] == "http://explicit:9000/v1"


class TestHealthLlmFlag:
    def test_health_llm_false_when_key_absent(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["llm"] is False

    def test_health_llm_true_when_key_present(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["llm"] is True

    def test_health_still_returns_status_ok(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# OpenAI-compatible client (local LLMs: llama.cpp, LM Studio, Ollama, vLLM)
# ---------------------------------------------------------------------------


class TestOpenAICompatibleClient:
    def _client_with_transport(self, handler):
        import httpx
        from src.reports.llm_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            base_url="http://localhost:8080/v1",
            api_key="local",
            model="emma-4-E4B-it-Q8_0.gguf",
            transport=httpx.MockTransport(handler),
        )

    def test_posts_chat_completion_and_parses_content(self) -> None:
        import httpx

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = _json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "advisor text"}}]},
            )

        client = self._client_with_transport(handler)
        out = client.complete(system="sys prompt", user="user prompt")

        assert out == "advisor text"
        assert captured["url"] == "http://localhost:8080/v1/chat/completions"
        assert captured["auth"] == "Bearer local"
        assert captured["body"]["model"] == "emma-4-E4B-it-Q8_0.gguf"
        assert captured["body"]["messages"][0] == {
            "role": "system",
            "content": "sys prompt",
        }
        assert captured["body"]["messages"][1]["role"] == "user"

    def test_http_error_raises_runtime_error(self) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="model exploded")

        client = self._client_with_transport(handler)
        with pytest.raises(RuntimeError, match="500"):
            client.complete(system="s", user="u")


class TestClientFactorySelection:
    def test_llm_base_url_selects_openai_compatible(self, monkeypatch) -> None:
        import src.api.endpoints.reports as reports_mod
        from src.reports.llm_client import OpenAICompatibleClient

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.setenv("LLM_MODEL", "local-model")
        client = reports_mod.get_llm_client()
        assert isinstance(client, OpenAICompatibleClient)


class TestNarrativeEndpointLocalLlm:
    def test_local_llm_config_enables_endpoint_without_anthropic_key(
        self, monkeypatch
    ) -> None:
        import src.api.endpoints.reports as reports_mod

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: FakeClient("hi"))
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.post("/runs/nonexistent-id/narrative")
        # 404 (run missing), NOT 501 (feature disabled)
        assert resp.status_code == 404

    def test_health_llm_true_with_base_url_only(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
        app = create_app(":memory:")
        with TestClient(app) as c:
            resp = c.get("/health")
        assert resp.json()["llm"] is True


# ---------------------------------------------------------------------------
# Advisor report: system prompt file, persistence, PDF commentary
# ---------------------------------------------------------------------------

_SEED_PAYLOAD = {
    "household": {
        "filing_status": "single",
        "self_birth_date": "1962-06-01",
        "state": "TX",
    },
    "accounts": [
        {"account_type": "traditional", "owner": "self", "balance": 400_000.0},
    ],
    "income": [],
    "settings": {"required_spending": 50_000.0, "ss_pia_self": 1800.0},
    "constraints": {"irmaa_policy": "soft", "conversion_window": "anytime"},
}


def _seed_run(c: TestClient) -> str:
    hh_id = c.post("/households", json=_SEED_PAYLOAD).json()["household_id"]
    return c.post(
        "/optimize", json={"household_id": hh_id, "monte_carlo_runs": 1}
    ).json()["run_id"]


class TestAdvisorReport:
    def test_system_prompt_file_overrides_default(self, monkeypatch, tmp_path) -> None:
        import src.api.endpoints.reports as reports_mod

        prompt_file = tmp_path / "advisor.md"
        prompt_file.write_text("You are a fee-only fiduciary advisor writing a report.")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("LLM_SYSTEM_PROMPT_FILE", str(prompt_file))
        fake = FakeClient("report body")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: fake)

        app = create_app(":memory:")
        with TestClient(app) as c:
            run_id = _seed_run(c)
            c.post(f"/runs/{run_id}/narrative")

        assert fake.last_system == "You are a fee-only fiduciary advisor writing a report."

    def test_prompt_includes_inputs_and_alternatives(self, monkeypatch) -> None:
        import src.api.endpoints.reports as reports_mod

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake = FakeClient("report body")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: fake)

        app = create_app(":memory:")
        with TestClient(app) as c:
            run_id = _seed_run(c)
            c.post(f"/runs/{run_id}/narrative")

        user = fake.last_user or ""
        assert "single" in user           # filing status from the snapshot
        assert "$50,000" in user          # required spending
        assert "Alternative strategies" in user

    def test_narrative_persisted_and_in_pdf(self, monkeypatch) -> None:
        import src.api.endpoints.reports as reports_mod

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake = FakeClient("A disciplined, tax-aware drawdown plan.")
        monkeypatch.setattr(reports_mod, "get_llm_client", lambda: fake)

        app = create_app(":memory:")
        with TestClient(app) as c:
            run_id = _seed_run(c)
            c.post(f"/runs/{run_id}/narrative")
            pdf = c.get(f"/runs/{run_id}/report.pdf").content

        from tests.unit.test_pdf_export import _pdf_text

        text = _pdf_text(pdf)
        assert "Advisor Commentary" in text
        assert "disciplined, tax-aware drawdown plan" in text

    def test_pdf_has_no_commentary_before_generation(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        app = create_app(":memory:")
        with TestClient(app) as c:
            run_id = _seed_run(c)
            pdf = c.get(f"/runs/{run_id}/report.pdf").content

        from tests.unit.test_pdf_export import _pdf_text

        assert "Advisor Commentary" not in _pdf_text(pdf)


# ---------------------------------------------------------------------------
# Local-LLM client: installable, closes its connection, fails legibly
# ---------------------------------------------------------------------------


def test_httpx_is_a_runtime_dependency():
    """The local-LLM client imports httpx, and the guide promises local models
    need no extra package -- so a base install must bring it, not only the
    dev extra."""
    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parents[3] / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    assert any(d.split(">")[0].split("=")[0].strip() == "httpx" for d in deps), deps


def _closing_transport(handler):
    """A MockTransport that records whether its client was closed."""
    import httpx

    class _Closing(httpx.MockTransport):
        closed = False

        def close(self):
            self.closed = True

    return _Closing(handler)


def test_the_local_client_closes_its_connection():
    import httpx
    from src.reports.llm_client import OpenAICompatibleClient

    transport = _closing_transport(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "ok"}}]}))
    client = OpenAICompatibleClient(base_url="http://localhost:8080/v1",
                                    transport=transport)
    assert client.complete(system="s", user="u") == "ok"
    assert transport.closed


def test_an_unreachable_local_endpoint_names_the_url():
    import httpx
    from src.reports.llm_client import OpenAICompatibleClient

    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = OpenAICompatibleClient(base_url="http://localhost:8080/v1",
                                    transport=httpx.MockTransport(refuse))
    with pytest.raises(RuntimeError, match="localhost:8080"):
        client.complete(system="s", user="u")


class _FailingClient:
    def complete(self, system, user):
        raise RuntimeError("Could not reach the LLM at http://localhost:8080/v1")


def test_a_provider_failure_is_a_502_with_the_reason(monkeypatch):
    """Not a bare 500: the user needs to know the model, not the app, failed."""
    import src.api.endpoints.reports as reports_mod

    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setattr(reports_mod, "get_llm_client", lambda: _FailingClient())
    app = create_app(":memory:")
    with TestClient(app, raise_server_exceptions=False) as c:
        hh_id = c.post("/households", json={
            "household": {"filing_status": "single", "self_birth_date": "1962-06-01",
                          "state": "TX"},
            "accounts": [{"account_type": "traditional", "owner": "self",
                          "balance": 400_000.0}],
            "income": [],
            "settings": {"required_spending": 50_000.0, "ss_pia_self": 1800.0},
        }).json()["household_id"]
        run_id = c.post("/optimize", json={"household_id": hh_id,
                                           "monte_carlo_runs": 0}).json()["run_id"]
        resp = c.post(f"/runs/{run_id}/narrative")
    assert resp.status_code == 502
    assert "localhost:8080" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# build_prompt — a claim-age search: entered vs recommended ages, and the
# basis of every figure
# ---------------------------------------------------------------------------

_SCORE = 5_898_802.0


def _joint_result() -> dict:
    def alt(age_spouse: int, diff: float, verdict: str) -> dict:
        return {
            "policy_id": "fill_12_annual", "key": f"fill_12_annual@69-{age_spouse}",
            "claim_age_self": 69, "claim_age_spouse": age_spouse,
            "score": _SCORE - diff, "monte_carlo_paths": 300,
            "lifetime_taxes_delta": 2_500.0, "terminal_estate_delta": -6_400.0,
            "success_probability_delta": 0.0,
            "paired": {"verdict": verdict, "mean_difference": diff},
        }

    def base(policy_id: str, s: int, p: int, score: float) -> dict:
        return {"key": f"{policy_id}@{s}-{p}", "policy_id": policy_id,
                "claim_age_self": s, "claim_age_spouse": p, "score": score,
                "success_probability": 1.0}

    winner = {"key": "fill_12_annual@69-68", "policy_id": "fill_12_annual",
              "claim_age_self": 69, "claim_age_spouse": 68, "score": _SCORE,
              "conversion_stop_year": 2038}
    return {
        "objective": "pv_estate_minus_weighted_shortfall",
        "monte_carlo_runs": 300,
        "claim_ages": {"self": 69, "spouse": 68},
        "winning_policy": {**_POLICY, "policy_id": "fill_12_annual", "score": _SCORE,
                           "key": winner["key"], "claim_age_self": 69,
                           "claim_age_spouse": 68, "monte_carlo_paths": 300,
                           "year0_conversion": 103_000},
        "joint_winner": winner,
        "yearly_plan": [_YEAR_ROW],
        "alternative_policies": [alt(67, 3_867.0, "equivalent"),
                                 alt(66, 9_000.0, "unresolved")],
        "warnings": [],
        "search": {
            "mode": "joint",
            "baselines": {
                "entered_no_conversion": base("none", 65, 63, 5_405_983.0),
                "entered_best_conversion": base("fill_12_annual", 65, 63, 5_710_417.0),
                "winner_ages_no_conversion": base("none", 69, 68, 5_578_176.0),
            },
            "comparisons": {"fill_12_annual@65-63": {"verdict": "winner"}},
        },
    }


_JOINT_INPUTS = {
    "household": {"filing_status": "joint", "self_birth_date": "1964-01-01",
                  "state": "CA", "nickname": "Our plan"},
    "settings": {"required_spending": 90_000, "ss_claim_age_self": 65,
                 "ss_claim_age_spouse": 63},
}


class TestJointSearchPrompt:
    def _prompt(self) -> str:
        from src.reports.llm_narrative import build_prompt

        return build_prompt(_joint_result(), _JOINT_INPUTS)

    def test_entered_and_recommended_ages_are_separate(self) -> None:
        user = self._prompt()
        assert "claim ages entered: You 65 · Spouse 63" in user
        assert "claim ages recommended: You 69 · Spouse 68" in user

    def test_the_modeled_score_is_sent_with_its_basis(self) -> None:
        user = self._prompt()
        assert "average across 300 market scenarios" in user
        assert "$5,898,802" in user

    def test_steady_return_figures_are_labelled(self) -> None:
        user = self._prompt()
        assert "steady-return projection" in user
        assert "Projected estate at the end of the plan: $1,200,000" in user

    def test_alternatives_with_the_same_strategy_differ_by_ages(self) -> None:
        user = self._prompt()
        assert "You 69 · Spouse 67: modeled score -3,867" in user
        assert "Practically equivalent" in user
        assert "You 69 · Spouse 66: modeled score -9,000" in user
        assert "Too close to distinguish" in user

    def test_the_comparison_with_the_entered_ages_is_sent(self) -> None:
        user = self._prompt()
        assert "Your entered ages, best conversions" in user
        assert "You 65 · Spouse 63): modeled score $5,710,417, -188,385" in user
        assert "Recommendation ahead" in user

    def test_no_personal_details(self) -> None:
        user = self._prompt()
        for leaked in ("1964", "CA", "Our plan", "birth"):
            assert leaked not in user


def test_prompt_lists_gains_already_realized():
    inputs = {**_JOINT_INPUTS, "capital_gains": {
        "tax_year": 2026, "short_term": -4000.0, "long_term": 25000.0,
        "carryover_short_term": 1500.0, "carryover_long_term": 0.0,
    }}
    prompt = build_prompt(_joint_result(), inputs)
    assert ("Capital gains already realized in 2026 (net; negative = loss): "
            "short-term -$4,000, long-term $25,000") in prompt
    assert "Capital loss carried into 2026: short-term $1,500, long-term $0" in prompt
