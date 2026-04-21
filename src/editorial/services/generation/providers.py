from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import json
import re

import aiohttp

from src.editorial.config import settings


class BaseGenerationProvider(ABC):
    name: str

    @abstractmethod
    async def generate_variants(self, prompt: str, count: int) -> list[str]:
        raise NotImplementedError


class StubGenerationProvider(BaseGenerationProvider):
    name = "stub"

    async def generate_variants(self, prompt: str, count: int) -> list[str]:
        seed = prompt.split("Source messages:")[-1].strip()
        lines = [line.strip("- ").strip() for line in seed.splitlines() if line.strip()]
        joined = " ".join(lines[:3]).strip()
        if not joined:
            joined = "студенческая жизнь и повседневные вопросы"

        return [
            f"Кто уже сталкивался с похожей темой: {joined[:150]}? Подскажите, как лучше разобраться без лишней паники.",
            f"Есть тут люди, которые хорошо шарят в этой теме: {joined[:140]}? Поделитесь нормальным опытом или советом.",
            f"Как вы обычно решаете такие вопросы: {joined[:150]}? Интересно собрать спокойные варианты, без лишнего шума.",
        ][:count]


class OpenRouterGenerationProvider(BaseGenerationProvider):
    name = "openrouter"

    def __init__(self) -> None:
        self.last_model_name = settings.generation_model_name

    async def generate_variants(self, prompt: str, count: int) -> list[str]:
        if not settings.generation_openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        errors: list[str] = []
        for model_name in self._model_candidates():
            try:
                message = await self._request_model(model_name, prompt, count)
                variants = self._split_variants(message)
                if variants:
                    self.last_model_name = model_name
                    return variants[:count]
                errors.append(f"{model_name}: empty generated text")
            except RuntimeError as ex:
                errors.append(str(ex))

        error_tail = " | ".join(errors[-4:]) if errors else "no models tried"
        raise RuntimeError(f"OpenRouter generation failed: {error_tail}")

    def _model_candidates(self) -> list[str]:
        models = [settings.generation_model_name]
        models.extend(
            item.strip()
            for item in settings.generation_fallback_models.split(",")
            if item.strip()
        )
        return list(dict.fromkeys(models))

    async def _request_model(self, model_name: str, prompt: str, count: int) -> str:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior editor for anonymous Russian student Telegram channels. "
                        "Write only natural, idiomatic Russian drafts. Follow all constraints literally. "
                        "Never invent precise facts, locations, teachers, rooms, groups, dates, lost items, or personal incidents. "
                        "Do not encourage cheating or exam fraud. "
                        "Before answering, silently proofread every draft and rewrite anything that sounds machine-translated."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.55,
            "top_p": 0.9,
            "max_tokens": min(1600, max(500, count * 180)),
        }
        headers = {
            "Authorization": f"Bearer {settings.generation_openrouter_api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=180, sock_read=180)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{settings.generation_openrouter_base_url}/chat/completions",
                    headers=headers,
                    data=json.dumps(payload, ensure_ascii=False),
                    timeout=timeout,
                ) as response:
                    if response.status >= 400:
                        error_body = (await response.text()).strip()
                        hint = ""
                        if response.status == 404 and model_name.endswith(":free"):
                            hint = " The configured model may not exist on OpenRouter. Check EDITORIAL_GENERATION_MODEL."
                        raise RuntimeError(
                            f"OpenRouter error {response.status} for model "
                            f"{model_name}: {error_body[:700]}{hint}"
                        )
                    data = await response.json()
                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message") or {}
                    content = self._message_content_to_text(message.get("content"))
                    if not content:
                        finish_reason = choice.get("finish_reason")
                        raise RuntimeError(
                            f"OpenRouter returned empty content for model {model_name}"
                            f" (finish_reason={finish_reason})"
                        )
                    return content
        except asyncio.TimeoutError as ex:
            raise RuntimeError(
                f"OpenRouter request timed out after 180 seconds for model {model_name}"
            ) from ex
        except aiohttp.ClientConnectionError as ex:
            raise RuntimeError(
                f"OpenRouter connection error for model {model_name}: {ex}"
            ) from ex

    @staticmethod
    def _message_content_to_text(content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _split_variants(message: str | None) -> list[str]:
        message = (message or "").strip()
        if not message:
            return []

        numbered_pattern = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*])\s+")
        parts = numbered_pattern.split(message)
        if len(parts) > 1:
            return [part.strip(" -\n\t") for part in parts[1:] if part.strip(" -\n\t")]

        paragraphs = [part.strip(" -\n\t") for part in re.split(r"\n\s*\n", message) if part.strip()]
        if len(paragraphs) > 1:
            return paragraphs

        lines = [line.strip(" -\n\t") for line in message.splitlines() if line.strip()]
        return lines if len(lines) > 1 else [message]
