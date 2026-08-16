import asyncio

import pytest

from evidence_research.providers import OpenAIJsonModel, ProviderError, _with_retries


def test_retryable_provider_error_is_retried() -> None:
    attempts = 0

    async def flaky_operation() -> dict[str, bool]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ProviderError(
                provider="fake",
                kind="unavailable",
                message="temporary failure",
                retryable=True,
            )
        return {"ok": True}

    result = asyncio.run(
        _with_retries(
            flaky_operation,
            provider="fake",
            max_retries=2,
            retry_base_delay=0,
        )
    )

    assert result == {"ok": True}
    assert attempts == 3


def test_non_retryable_provider_error_is_not_retried() -> None:
    attempts = 0

    async def invalid_operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ProviderError(
            provider="fake",
            kind="bad_response",
            message="invalid request",
        )

    with pytest.raises(ProviderError, match="bad_response"):
        asyncio.run(
            _with_retries(
                invalid_operation,
                provider="fake",
                max_retries=3,
                retry_base_delay=0,
            )
        )
    assert attempts == 1


def test_openai_rate_limit_error_is_classified_as_retryable() -> None:
    class RateLimitError(Exception):
        status_code = 429

    error = OpenAIJsonModel._classify_error(RateLimitError("slow down"))

    assert error.kind == "rate_limit"
    assert error.retryable is True
