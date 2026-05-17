# intelligence/llm.py
from __future__ import annotations

import asyncio
import os
from typing import Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI


class LLMClient(Protocol):
    async def complete(self, *, prompt: str, max_tokens: int, timeout: float) -> str: ...


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic, model: str):
        self._client = client
        self._model = model

    async def complete(self, *, prompt: str, max_tokens: int, timeout: float) -> str:
        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, TimeoutError):
            raise RuntimeError("LLM call timed out")
        return resp.content[0].text


class OpenAICompatibleLLM:
    def __init__(self, client: AsyncOpenAI, model: str):
        self._client = client
        self._model = model

    async def complete(self, *, prompt: str, max_tokens: int, timeout: float) -> str:
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, TimeoutError):
            raise RuntimeError("LLM call timed out")
        return resp.choices[0].message.content or ""


def build_llm_client(llm_cfg: dict) -> LLMClient:
    provider = (llm_cfg.get("provider") or "claude").lower()

    if provider == "openrouter":
        or_cfg = llm_cfg.get("openrouter") or {}
        api_key = or_cfg.get("api_key") or os.environ.get("OPENROUTER_API_KEY", "")
        base_url = or_cfg.get("base_url") or "https://openrouter.ai/api/v1"
        model = or_cfg.get("model") or "anthropic/claude-sonnet-4"
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        return OpenAICompatibleLLM(
            AsyncOpenAI(api_key=api_key, base_url=base_url), model=model
        )

    if provider == "openai":
        api_key = llm_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        model = llm_cfg.get("model") or "gpt-4o-mini"
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAICompatibleLLM(AsyncOpenAI(api_key=api_key), model=model)

    # claude (default)
    api_key = llm_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = llm_cfg.get("model") or "claude-sonnet-4-20250514"
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return AnthropicLLM(AsyncAnthropic(api_key=api_key), model=model)
