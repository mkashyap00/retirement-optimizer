"""LLM client abstraction for optional narrative generation.

Usage without the ``llm`` extra (no anthropic package installed) is fully
supported — :class:`AnthropicClient` raises :exc:`ImportError` at
``__init__`` time, not at import time of this module.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface every LLM back-end must satisfy."""

    def complete(self, system: str, user: str) -> str:
        """Return the model completion as a plain string."""
        ...


class AnthropicClient:
    """Thin wrapper around the anthropic SDK.

    The SDK is imported lazily so that importing this module does not
    require the ``llm`` extra to be installed.  If the package is missing,
    an informative :exc:`ImportError` is raised at construction time.
    """

    def __init__(self) -> None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The 'anthropic' package is not installed. "
                'Install the optional dependency with: pip install -e ".[llm]"'
            ) from exc

        self._client = _anthropic.Anthropic()
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-fable-5")

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text


class OpenAICompatibleClient:
    """Client for any OpenAI-compatible /v1 endpoint (llama.cpp server,
    LM Studio, Ollama, vLLM, ...) — the standard surface local LLMs expose.

    Uses httpx directly (a runtime dependency), so local models need no
    extra package. Each request opens and closes its own connection: a
    narrative is one call, seconds to minutes apart.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "local",
        model: str = "local-model",
        timeout: float = 180.0,
        transport=None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        import httpx

        try:
            with httpx.Client(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    json={
                        "model": self._model,
                        "max_tokens": 4000,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
        except httpx.HTTPError as exc:
            # Connection refused, timeout, DNS: almost always the local server
            # is not running or LLM_BASE_URL is wrong. Say which URL.
            raise RuntimeError(
                f"Could not reach the LLM at {self._base_url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise RuntimeError(
                f"LLM endpoint returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()["choices"][0]["message"]["content"]


class FakeClient:
    """Test double that records call arguments and returns a canned response."""

    def __init__(self, canned: str) -> None:
        self._canned = canned
        self.last_system: str | None = None
        self.last_user: str | None = None

    def complete(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return self._canned
