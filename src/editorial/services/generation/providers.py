from __future__ import annotations

from abc import ABC, abstractmethod
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
        seed = prompt.split("Источники:")[-1].strip()
        lines = [line.strip("- ").strip() for line in seed.splitlines() if line.strip()]
        joined = " ".join(lines[:3]).strip()
        if not joined:
            joined = "студенческая жизнь и повседневные вопросы"

        return [
            f"Вопрос дня: кто сталкивался с такой ситуацией — {joined[:180]}?",
            f"Тема для обсуждения: что вы думаете про {joined[:160]}? Интересно собрать мнения без срача.",
            f"Повод поговорить: как вы обычно решаете такие истории — {joined[:170]}?",
        ][:count]


class OpenRouterGenerationProvider(BaseGenerationProvider):
    name = "openrouter"

    async def generate_variants(self, prompt: str, count: int) -> list[str]:
        if not settings.generation_openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        payload = {
            "model": settings.generation_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты помогаешь редактору студенческих Telegram-каналов. "
                        "Сделай мягкие безопасные форматы постов: question, topic_digest, motive_post. "
                        "Не придумывай фейковые признания и не выдавай вымышленные истории за реальные."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
        }
        headers = {
            "Authorization": f"Bearer {settings.generation_openrouter_api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{settings.generation_openrouter_base_url}/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                message = data["choices"][0]["message"]["content"]

        variants = [item.strip() for item in re.split(r"\n+\d+[.)]\s*", message) if item.strip()]
        if not variants:
            variants = [message.strip()]
        return variants[:count]

