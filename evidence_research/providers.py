from __future__ import annotations

import os
from typing import Any, Protocol


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[dict[str, object]]: ...


class JsonModel(Protocol):
    async def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]: ...


class FirecrawlSearchProvider:
    def __init__(self, api_key: str, base_url: str = "https://api.firecrawl.dev") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/search",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "query": query,
                    "limit": limit,
                    "scrapeOptions": {"formats": ["markdown"]},
                },
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or payload.get("results") or []
            return data if isinstance(data, list) else []


class OpenAIJsonModel:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        import json

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}


def providers_from_env() -> tuple[FirecrawlSearchProvider, OpenAIJsonModel]:
    firecrawl_key = os.environ.get("FIRECRAWL_KEY")
    openai_key = os.environ.get("OPENAI_KEY")
    if not firecrawl_key or not openai_key:
        raise RuntimeError("FIRECRAWL_KEY and OPENAI_KEY are required")
    return (
        FirecrawlSearchProvider(
            firecrawl_key, os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
        ),
        OpenAIJsonModel(
            openai_key,
            os.environ.get("CUSTOM_MODEL", "gpt-4o-mini"),
            os.environ.get("OPENAI_ENDPOINT"),
        ),
    )
