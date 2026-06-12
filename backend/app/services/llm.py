from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


class LLMProvider:
    name = "offline"

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    def complete_json_sync(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "mode": self.name,
            "summary": "同步模式下使用离线兜底结果。",
        }


class OfflineProvider(LLMProvider):
    name = "offline"

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "mode": "offline",
            "summary": "当前使用离线规则引擎。配置 LLM_PROVIDER=openai 后可切换到真实模型。",
        }

    def complete_json_sync(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "mode": "offline",
            "summary": "当前使用离线规则引擎。配置 LLM_PROVIDER=openai 后可切换到真实模型。",
        }


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.last_error: str | None = None

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            result = await self.primary.complete_json(system_prompt, user_prompt)
            self.name = self.primary.name
            self.last_error = None
            return result
        except Exception as exc:
            self.name = f"{self.primary.name}->fallback:{self.fallback.name}"
            self.last_error = str(exc)
            return await self.fallback.complete_json(system_prompt, user_prompt)

    def complete_json_sync(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            result = self.primary.complete_json_sync(system_prompt, user_prompt)
            self.name = self.primary.name
            self.last_error = None
            return result
        except Exception as exc:
            self.name = f"{self.primary.name}->fallback:{self.fallback.name}"
            self.last_error = str(exc)
            return self.fallback.complete_json_sync(system_prompt, user_prompt)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise RuntimeError("openai package is required for OpenAI-compatible provider") from exc
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def complete_json_sync(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url)
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider.lower() == "openai" and settings.openai_api_key:
        try:
            return FallbackLLMProvider(OpenAICompatibleProvider(), OfflineProvider())
        except Exception:
            return OfflineProvider()
    return OfflineProvider()
