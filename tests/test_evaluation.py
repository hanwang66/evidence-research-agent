from evidence_research.evaluation import evaluate_result
from evidence_research.models import (
    Claim,
    ClaimStatus,
    Evidence,
    ResearchResult,
    SourceDocument,
    SourceQuality,
    SourceType,
)


def _source() -> SourceDocument:
    return SourceDocument(
        id="src-1",
        url="https://example.com/report",
        canonical_url="https://example.com/report",
        content="Revenue increased 20 percent in 2024.",
        source_type=SourceType.OFFICIAL,
        fetched_at="2025-01-01T00:00:00+00:00",
        quality=SourceQuality(0.8, 0.9, 0.7, 0.8, 80),
    )


def _result(*, quote: str = "Revenue increased 20 percent in 2024.") -> ResearchResult:
    source = _source()
    evidence = Evidence(
        id="evidence-1",
        source_id=source.id,
        quote=quote,
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


def test_evaluation_passes_when_citations_and_quotes_are_supported() -> None:
    metrics = evaluate_result(report="Revenue increased. [C1]", result=_result())

    assert metrics["citation_coverage"] == 1.0
    assert metrics["evidence_support_rate"] == 1.0
    assert metrics["important_claim_evidence_rate"] == 1.0
    assert metrics["average_source_quality"] == 80.0
    assert metrics["passed"] is True


def test_evaluation_rejects_unsupported_quotes() -> None:
    metrics = evaluate_result(report="Revenue increased. [C1]", result=_result(quote="Invented quote."))

    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_evidence_ids"] == ["evidence-1"]
    assert metrics["passed"] is False


def test_evaluation_rejects_important_claim_without_evidence() -> None:
    result = _result()
    result.claims[0] = Claim(**{**result.claims[0].__dict__, "evidence_ids": []})
    result.evidence = []

    metrics = evaluate_result(report="Revenue increased. [C1]", result=result)

    assert metrics["citation_coverage"] == 1.0
    assert metrics["important_claim_evidence_rate"] == 0.0
    assert metrics["missing_evidence_claim_ids"] == ["claim-1"]
    assert metrics["passed"] is False
