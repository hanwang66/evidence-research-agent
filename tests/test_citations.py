from evidence_research.citations import audit_citations, citation_id
from evidence_research.models import Claim


def test_citation_audit_requires_important_claims() -> None:
    claim = Claim(
        id="claim-market-growth",
        text="The market grew year over year.",
        category="growth",
        importance="high",
        evidence_ids=["evidence-1"],
    )
    assert citation_id(claim) == "Cmarket-growth"
    assert audit_citations("The market grew. [Cmarket-growth]", [claim]) == {
        "passed": True,
        "coverage": 1.0,
        "missing_claim_ids": [],
    }


def test_citation_audit_reports_missing_claims() -> None:
    claim = Claim(
        id="claim-market-growth",
        text="The market grew year over year.",
        category="growth",
        importance="high",
        evidence_ids=[],
    )
    audit = audit_citations("The market grew.", [claim])
    assert audit["passed"] is False
    assert audit["coverage"] == 0.0
    assert audit["missing_claim_ids"] == [claim.id]
