import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException

from evidence_research import api
from evidence_research.models import (
    Claim,
    ClaimStatus,
    Evidence,
    ResearchResult,
    SourceDocument,
    SourceQuality,
    SourceType,
)
from evidence_research.providers import ProviderError
from evidence_research.research import ResearchBudget, ResearchBudgetExceeded
from evidence_research.storage import TaskStateStore


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        api.app.state,
        "task_store",
        TaskStateStore(tmp_path / "research.db"),
        raising=False,
    )


class FakeAgent:
    def __init__(
        self,
        *,
        search: object,
        model: object,
        concurrency: int,
        budget: ResearchBudget,
    ) -> None:
        self.model = model
        self.budget = budget

    async def research(self, *, query: str, breadth: int, depth: int) -> ResearchResult:
        source = SourceDocument(
            id="src-1",
            url="https://example.com/report",
            canonical_url="https://example.com/report",
            content="Revenue increased 20 percent in 2024.",
            source_type=SourceType.OFFICIAL,
            fetched_at="2025-01-01T00:00:00+00:00",
            quality=SourceQuality(0.8, 0.9, 0.7, 0.8, 80),
        )
        evidence = Evidence(
            id="evidence-1",
            source_id=source.id,
            quote=source.content,
            stance="supports",
            relevance_score=1.0,
        )
        claim = Claim(
            id="claim-1",
            text="Revenue increased.",
            category="growth",
            importance="high",
            evidence_ids=[evidence.id],
            status=ClaimStatus.VERIFIED,
            confidence=0.9,
        )
        return ResearchResult(sources=[source], evidence=[evidence], claims=[claim])


async def fake_report(**kwargs: object) -> str:
    return "Revenue increased. [C1]"


def test_research_endpoint_returns_evaluation(monkeypatch) -> None:
    monkeypatch.setattr(api, "providers_from_env", lambda: (object(), object()))
    monkeypatch.setattr(api, "DeepResearchAgent", FakeAgent)
    monkeypatch.setattr(api, "write_report", fake_report)

    response = asyncio.run(api.research(api.ResearchRequest(query="What changed?")))

    assert response["evaluation"]["passed"] is True
    assert response["evaluation"]["citation_coverage"] == 1.0
    assert response["budget"]["model_calls"] == 0


def test_research_endpoint_maps_provider_timeout(monkeypatch) -> None:
    async def fail(_request: api.ResearchRequest) -> dict[str, object]:
        raise ProviderError(
            provider="firecrawl",
            kind="timeout",
            message="request timed out",
            retryable=True,
        )

    monkeypatch.setattr(api, "_execute", fail)

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.research(api.ResearchRequest(query="What changed?")))

    assert error.value.status_code == 504
    assert error.value.detail == {
        "error": "provider_error",
        "provider": "firecrawl",
        "kind": "timeout",
    }


def test_research_endpoint_maps_budget_exhaustion(monkeypatch) -> None:
    async def fail(_request: api.ResearchRequest) -> dict[str, object]:
        raise ResearchBudgetExceeded(resource="model_calls", limit=1, used=1)

    monkeypatch.setattr(api, "_execute", fail)

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.research(api.ResearchRequest(query="What changed?")))

    assert error.value.status_code == 429
    assert error.value.detail == {
        "error": "research_budget_exceeded",
        "resource": "model_calls",
        "limit": 1,
        "used": 1,
    }


def test_research_endpoint_persists_and_caches_completed_result(monkeypatch) -> None:
    calls = 0

    async def execute(_request: api.ResearchRequest) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"report": "cached report", "claims": [], "evidence": [], "sources": []}

    monkeypatch.setattr(api, "_execute", execute)
    request = api.ResearchRequest(query="What changed?")

    first = asyncio.run(api.research(request))
    second = asyncio.run(api.research(request))

    assert calls == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert first["task_id"] == second["task_id"]
    assert second["report"] == "cached report"


def test_background_research_job_is_completed_and_queryable(monkeypatch) -> None:
    async def execute(_request: api.ResearchRequest) -> dict[str, object]:
        return {"report": "background report", "claims": []}

    monkeypatch.setattr(api, "_execute", execute)
    background_tasks = BackgroundTasks()

    accepted = asyncio.run(api.create_research_job(api.ResearchRequest(query="Run later"), background_tasks))
    asyncio.run(background_tasks())
    completed = asyncio.run(api.get_research_job(str(accepted["task_id"])))

    assert accepted["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["result"] == {"report": "background report", "claims": []}


def test_background_research_job_records_failure(monkeypatch) -> None:
    async def fail(_request: api.ResearchRequest) -> dict[str, object]:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(api, "_execute", fail)
    background_tasks = BackgroundTasks()
    accepted = asyncio.run(api.create_research_job(api.ResearchRequest(query="Will fail"), background_tasks))
    asyncio.run(background_tasks())
    failed = asyncio.run(api.get_research_job(str(accepted["task_id"])))

    assert failed["status"] == "failed"
    assert failed["error"] == "model unavailable"


def test_background_research_job_reuses_active_duplicate() -> None:
    first_tasks = BackgroundTasks()
    second_tasks = BackgroundTasks()
    request = api.ResearchRequest(query="Duplicate job")

    first = asyncio.run(api.create_research_job(request, first_tasks))
    second = asyncio.run(api.create_research_job(request, second_tasks))

    assert first["task_id"] == second["task_id"]
    assert second["status"] == "queued"
