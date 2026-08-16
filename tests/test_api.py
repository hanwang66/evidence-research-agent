import asyncio

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


class FakeAgent:
    def __init__(self, *, search: object, model: object) -> None:
        pass

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
