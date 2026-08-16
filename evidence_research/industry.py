from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndustryRequest:
    question: str
    industry: str | None = None
    region: str | None = None
    time_range: str | None = None
    companies: list[str] = field(default_factory=list)


DEFAULT_DIMENSIONS = (
    "market size and growth",
    "competitive landscape",
    "technology and product trends",
    "regulation and policy",
    "key risks and uncertainties",
)


def build_industry_prompt(request: IndustryRequest) -> str:
    constraints = [
        f"Industry: {request.industry}" if request.industry else None,
        f"Region: {request.region}" if request.region else None,
        f"Time range: {request.time_range}" if request.time_range else None,
        f"Companies: {', '.join(request.companies)}" if request.companies else None,
    ]
    constraints = [item for item in constraints if item]
    parts = [request.question]
    if constraints:
        parts.append("Research constraints:\n" + "\n".join(constraints))
    parts.append("Unless excluded, cover:\n" + "\n".join(f"- {item}" for item in DEFAULT_DIMENSIONS))
    parts.append(
        "Prefer primary, regulator, official, academic, and reputable media sources. "
        "Preserve conflicting evidence."
    )
    return "\n\n".join(parts)
