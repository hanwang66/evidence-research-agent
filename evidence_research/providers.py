from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """A normalized provider failure safe to classify at the API boundary."""

    def __init__(
        self,
        *,
        provider: str,
        kind: str,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(f"{provider} {kind}: {message}")


async def _with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    provider: str,
    max_retries: int,
    retry_base_delay: float,
) -> T:
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except ProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            await asyncio.sleep(retry_base_delay * (2**attempt))
    raise AssertionError("retry loop must return or raise")


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[dict[str, object]]: ...


class JsonModel(Protocol):
    async def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]: ...


class FirecrawlSearchProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.firecrawl.dev",
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_base_delay = max(0.0, retry_base_delay)

    async def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        import httpx

        async def request() -> list[dict[str, object]]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
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
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    provider="firecrawl",
                    kind="timeout",
                    message=str(exc),
                    retryable=True,
                ) from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    kind, retryable = "rate_limit", True
                elif status_code == 408 or status_code >= 500:
                    kind, retryable = "unavailable", True
                else:
                    kind, retryable = "bad_response", False
                raise ProviderError(
                    provider="firecrawl",
                    kind=kind,
                    message=f"HTTP {status_code}",
                    retryable=retryable,
                    status_code=status_code,
                ) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    provider="firecrawl",
                    kind="unavailable",
                    message=str(exc),
                    retryable=True,
                ) from exc
            except ValueError as exc:
                raise ProviderError(
                    provider="firecrawl",
                    kind="invalid_payload",
                    message="response was not valid JSON",
                ) from exc

            if not isinstance(payload, dict):
                raise ProviderError(
                    provider="firecrawl",
                    kind="invalid_payload",
                    message="response root must be an object",
                )
            data = payload.get("data") or payload.get("results") or []
            if not isinstance(data, list):
                raise ProviderError(
                    provider="firecrawl",
                    kind="invalid_payload",
                    message="results must be an array",
                )
            if not all(isinstance(item, dict) for item in data):
                raise ProviderError(
                    provider="firecrawl",
                    kind="invalid_payload",
                    message="every result must be an object",
                )
            return data

        return await _with_retries(
            request,
            provider="firecrawl",
            max_retries=self.max_retries,
            retry_base_delay=self.retry_base_delay,
        )


class OpenAIJsonModel:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
    ) -> None:
        from openai import AsyncOpenAI

        self.model = model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_base_delay = max(0.0, retry_base_delay)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)

    async def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        async def request() -> dict[str, Any]:
            import json

            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.timeout,
                )
            except TimeoutError as exc:
                raise ProviderError(
                    provider="openai",
                    kind="timeout",
                    message="model request timed out",
                    retryable=True,
                ) from exc
            except Exception as exc:
                raise self._classify_error(exc) from exc

            try:
                content = response.choices[0].message.content or "{}"
            except (AttributeError, IndexError, TypeError) as exc:
                raise ProviderError(
                    provider="openai",
                    kind="invalid_payload",
                    message="model response did not contain a completion",
                ) from exc
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    provider="openai",
                    kind="invalid_payload",
                    message="model response was not valid JSON",
                    retryable=True,
                ) from exc
            if not isinstance(parsed, dict):
                raise ProviderError(
                    provider="openai",
                    kind="invalid_payload",
                    message="model JSON root must be an object",
                )
            return parsed

        return await _with_retries(
            request,
            provider="openai",
            max_retries=self.max_retries,
            retry_base_delay=self.retry_base_delay,
        )

    @staticmethod
    def _classify_error(error: Exception) -> ProviderError:
        status_code = getattr(error, "status_code", None)
        error_name = type(error).__name__
        if error_name in {"APITimeoutError", "TimeoutError"}:
            return ProviderError(provider="openai", kind="timeout", message=str(error), retryable=True)
        if error_name == "RateLimitError" or status_code == 429:
            return ProviderError(
                provider="openai",
                kind="rate_limit",
                message=str(error),
                retryable=True,
                status_code=status_code,
            )
        if error_name in {"APIConnectionError", "InternalServerError"} or (
            isinstance(status_code, int) and status_code >= 500
        ):
            return ProviderError(
                provider="openai",
                kind="unavailable",
                message=str(error),
                retryable=True,
                status_code=status_code,
            )
        return ProviderError(
            provider="openai",
            kind="bad_response",
            message=str(error),
            status_code=status_code if isinstance(status_code, int) else None,
        )


def providers_from_env() -> tuple[FirecrawlSearchProvider, OpenAIJsonModel]:
    firecrawl_key = os.environ.get("FIRECRAWL_KEY")
    openai_key = os.environ.get("OPENAI_KEY")
    if not firecrawl_key or not openai_key:
        raise RuntimeError("FIRECRAWL_KEY and OPENAI_KEY are required")
    timeout = _env_float("PROVIDER_TIMEOUT_SECONDS", 30.0)
    max_retries = _env_int("PROVIDER_MAX_RETRIES", 2)
    retry_base_delay = _env_float("PROVIDER_RETRY_BASE_DELAY", 0.5)
    return (
        FirecrawlSearchProvider(
            firecrawl_key,
            os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
            timeout=timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
        ),
        OpenAIJsonModel(
            openai_key,
            os.environ.get("CUSTOM_MODEL", "gpt-4o-mini"),
            os.environ.get("OPENAI_ENDPOINT"),
            timeout=_env_float("MODEL_TIMEOUT_SECONDS", 60.0),
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
        ),
    )


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name, str(default))))
    except ValueError:
        return default
