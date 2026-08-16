from __future__ import annotations

from collections import Counter

from .citations import audit_citations
from .evidence import quote_supported
from .models import ClaimStatus, ResearchResult


def evaluate_result(*, report: str, result: ResearchResult) -> dict[str, object]:
    """Calculate deterministic reliability metrics for a research result.

    These metrics do not decide whether a conclusion is true in the real world.
    They measure contracts that this pipeline can verify locally: citations are
    present, quotes exist in fetched content, and claims have accepted evidence.
    """

    source_by_id = {source.id: source for source in result.sources}
    evidence_by_id = {item.id: item for item in result.evidence}

    supported_evidence_ids = {
        item.id
        for item in result.evidence
        if (source := source_by_id.get(item.source_id))
        and quote_supported(quote=item.quote, content=source.content)
    }
    unsupported_evidence_ids = [item.id for item in result.evidence if item.id not in supported_evidence_ids]

    important_claims = [claim for claim in result.claims if claim.importance != "low"]
    claims_with_supported_evidence = [
        claim
        for claim in result.claims
        if any(evidence_id in supported_evidence_ids for evidence_id in claim.evidence_ids)
    ]
    claims_without_evidence = [claim.id for claim in important_claims if not claim.evidence_ids]
    missing_evidence_claim_ids = [
        claim.id
        for claim in important_claims
        if not any(evidence_id in evidence_by_id for evidence_id in claim.evidence_ids)
    ]

    citation_audit = audit_citations(report, result.claims)
    status_counts = Counter(claim.status.value for claim in result.claims)
    source_scores = [source.quality.score for source in result.sources]

    evidence_count = len(result.evidence)
    claim_count = len(result.claims)
    evidence_support_rate = len(supported_evidence_ids) / evidence_count if evidence_count else 0.0
    important_claim_evidence_rate = (
        1.0
        if not important_claims
        else (len(important_claims) - len(missing_evidence_claim_ids)) / len(important_claims)
    )
    verification_rate = status_counts[ClaimStatus.VERIFIED.value] / claim_count if claim_count else 0.0
    orphan_evidence_ids = [
        evidence_id
        for evidence_id in evidence_by_id
        if not any(evidence_id in claim.evidence_ids for claim in result.claims)
    ]

    passed = bool(
        result.sources
        and result.claims
        and result.evidence
        and citation_audit["passed"]
        and evidence_support_rate == 1.0
        and important_claim_evidence_rate == 1.0
    )

    return {
        "claim_count": claim_count,
        "evidence_count": evidence_count,
        "source_count": len(result.sources),
        "citation_coverage": round(float(citation_audit["coverage"]), 4),
        "evidence_support_rate": round(evidence_support_rate, 4),
        "important_claim_evidence_rate": round(important_claim_evidence_rate, 4),
        "verification_rate": round(verification_rate, 4),
        "average_source_quality": round(sum(source_scores) / len(source_scores), 2) if source_scores else 0.0,
        "verified_claim_count": status_counts[ClaimStatus.VERIFIED.value],
        "partially_verified_claim_count": status_counts[ClaimStatus.PARTIALLY_VERIFIED.value],
        "contradicted_claim_count": status_counts[ClaimStatus.CONTRADICTED.value],
        "unverified_claim_count": status_counts[ClaimStatus.UNVERIFIED.value],
        "claims_with_supported_evidence": len(claims_with_supported_evidence),
        "claims_without_evidence": claims_without_evidence,
        "missing_evidence_claim_ids": missing_evidence_claim_ids,
        "unsupported_evidence_ids": unsupported_evidence_ids,
        "orphan_evidence_ids": orphan_evidence_ids,
        "citation_audit": citation_audit,
        "passed": passed,
    }
