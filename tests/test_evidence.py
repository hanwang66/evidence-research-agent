import asyncio

from evidence_research.evidence import extract_evidence, quote_supported, verify_claims
from evidence_research.models import Claim, ClaimStatus, Evidence, SourceDocument, SourceQuality, SourceType


class EvidenceModel:
    async def generate_json(self, *, system: str, prompt: str) -> dict[str, object]:
        source_id = prompt.split('<source id="', 1)[1].split('"', 1)[0]
        return {
            "claims": [
                {
                    "text": "Revenue increased.",
                    "evidence": [
                        {"sourceId": source_id, "quote": "Revenue increased by 20 percent."},
                        {"sourceId": source_id, "quote": "This quote was invented."},
                    ],
                }
            ]
        }


class InvalidVerificationModel:
    async def generate_json(self, *, system: str, prompt: str) -> dict[str, object]:
        claim_id = prompt.split('<claim id="', 1)[1].split('"', 1)[0]
        return {"verifications": [{"claimId": claim_id, "verdict": "not-a-status", "confidence": "NaN"}]}


def _source() -> SourceDocument:
    return SourceDocument(
        id="src-1",
        url="https://example.com/report",
        canonical_url="https://example.com/report",
        content="Revenue increased by 20 percent.",
        source_type=SourceType.OFFICIAL,
        fetched_at="2025-01-01T00:00:00+00:00",
        quality=SourceQuality(0.8, 0.9, 0.7, 0.8, 80),
    )


def test_quote_supported_normalises_whitespace() -> None:
    assert quote_supported(
        quote="Revenue increased\nby 20 percent.",
        content="Revenue increased by 20 percent.",
    )
    assert not quote_supported(quote="Revenue decreased.", content=_source().content)


def test_extract_evidence_rejects_quotes_missing_from_source() -> None:
    claims, evidence = asyncio.run(
        extract_evidence(query="revenue", sources=[_source()], model=EvidenceModel())
    )

    assert len(claims) == 1
    assert len(evidence) == 1
    assert claims[0].evidence_ids == [evidence[0].id]


def test_verify_claims_never_accepts_invalid_model_status() -> None:
    claim = Claim(
        id="claim-1",
        text="Revenue increased.",
        category="growth",
        importance="high",
        evidence_ids=["evidence-1"],
    )
    evidence = Evidence(
        id="evidence-1",
        source_id="src-1",
        quote="Revenue increased by 20 percent.",
        stance="supports",
        relevance_score=1.0,
    )

    result = asyncio.run(
        verify_claims(
            claims=[claim], evidence=[evidence], sources=[_source()], model=InvalidVerificationModel()
        )
    )

    assert result[0].status == ClaimStatus.UNVERIFIED
    assert result[0].confidence == 0.0


def test_verify_claims_cannot_verify_claim_without_evidence() -> None:
    claim = Claim(
        id="claim-1",
        text="Revenue increased.",
        category="growth",
        importance="high",
        evidence_ids=[],
    )

    result = asyncio.run(
        verify_claims(claims=[claim], evidence=[], sources=[_source()], model=InvalidVerificationModel())
    )

    assert result[0].status == ClaimStatus.UNVERIFIED
    assert result[0].confidence == 0.0
