import asyncio
import re

from evidence_research.models import ClaimStatus
from evidence_research.research import DeepResearchAgent


class FakeSearch:
    async def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        return [
            {
                "url": "https://www.gov.cn/industry/report?utm_source=test",
                "title": "Industry report",
                "markdown": "The market grew by 20 percent in 2024.",
                "metadata": {"publishedAt": "2024-12-01T00:00:00Z"},
            }
        ]


class FakeModel:
    async def generate_json(self, *, system: str, prompt: str) -> dict[str, object]:
        if "Generate at most" in prompt:
            return {"queries": [{"query": "industry growth 2024", "researchGoal": "growth"}]}
        if "Extract at most" in prompt:
            source_id = re.search(r'<source id="([^"]+)"', prompt).group(1)
            return {
                "claims": [
                    {
                        "text": "The market grew by 20 percent in 2024.",
                        "category": "growth",
                        "importance": "high",
                        "evidence": [
                            {
                                "sourceId": source_id,
                                "quote": "The market grew by 20 percent in 2024.",
                                "stance": "supports",
                                "relevanceScore": 1,
                            }
                        ],
                    }
                ]
            }
        if "follow-up" in system:
            return {"questions": []}
        claim_id = re.search(r'<claim id="([^"]+)"', prompt).group(1)
        return {
            "verifications": [
                {
                    "claimId": claim_id,
                    "verdict": "verified",
                    "confidence": 0.95,
                    "rationale": "The quote directly supports the claim.",
                }
            ]
        }


def test_research_pipeline_builds_verified_claims() -> None:
    result = asyncio.run(
        DeepResearchAgent(search=FakeSearch(), model=FakeModel()).research(
            query="What happened to market growth?", breadth=1, depth=1
        )
    )
    assert len(result.sources) == 1
    assert len(result.evidence) == 1
    assert result.claims[0].status == ClaimStatus.VERIFIED
    assert result.claims[0].confidence == 0.95
