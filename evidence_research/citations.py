from __future__ import annotations

from .models import Claim, Evidence, SourceDocument


def citation_id(claim: Claim) -> str:
    return f"C{claim.id.removeprefix('claim-')[:14]}"


def audit_citations(report: str, claims: list[Claim]) -> dict[str, object]:
    important = [claim for claim in claims if claim.importance != "low"]
    missing = [claim.id for claim in important if f"[{citation_id(claim)}]" not in report]
    coverage = 1.0 if not important else 1 - len(missing) / len(important)
    return {"passed": not missing, "coverage": coverage, "missing_claim_ids": missing}


def evidence_graph_text(
    *, claims: list[Claim], evidence: list[Evidence], sources: list[SourceDocument]
) -> str:
    evidence_by_id = {item.id: item for item in evidence}
    source_by_id = {source.id: source for source in sources}
    lines = []
    for claim in claims:
        lines.append(
            f'<claim id="{claim.id}" status="{claim.status}" confidence="{claim.confidence}">{claim.text}'
        )
        for evidence_id in claim.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if not item:
                continue
            source = source_by_id.get(item.source_id)
            lines.append(
                f"[{citation_id(claim)}] {item.stance}; {source.canonical_url if source else item.source_id}; quote: {item.quote}"
            )
        lines.append("</claim>")
    return "\n".join(lines)
