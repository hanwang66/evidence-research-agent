from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import SourceDocument, SourceQuality, SourceType

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

OFFICIAL_DOMAINS = {
    "gov",
    "gov.cn",
    "gov.uk",
    "europa.eu",
    "sec.gov",
    "who.int",
    "worldbank.org",
    "stats.gov.cn",
    "caam.org.cn",
}
RESEARCH_DOMAINS = {"arxiv.org", "doi.org", "nature.com", "sciencedirect.com"}
MEDIA_DOMAINS = {
    "reuters.com",
    "ft.com",
    "bloomberg.com",
    "nytimes.com",
    "wsj.com",
    "theguardian.com",
}


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def canonicalize_url(raw_url: str) -> str:
    try:
        parts = urlsplit(raw_url.strip())
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                path,
                urlencode(query),
                "",
            )
        )
    except ValueError:
        return raw_url.strip()


def _matches_domain(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")


def classify_source(url: str) -> SourceType:
    hostname = urlsplit(url).hostname or ""
    hostname = hostname.lower()
    if any(_matches_domain(hostname, domain) for domain in OFFICIAL_DOMAINS):
        return SourceType.REGULATOR if "gov" in hostname or hostname == "sec.gov" else SourceType.OFFICIAL
    if any(_matches_domain(hostname, domain) for domain in RESEARCH_DOMAINS):
        return SourceType.RESEARCH
    if any(_matches_domain(hostname, domain) for domain in MEDIA_DOMAINS):
        return SourceType.MEDIA
    if hostname.endswith((".edu", ".edu.cn")):
        return SourceType.RESEARCH
    return SourceType.UNKNOWN


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def score_source(
    *,
    url: str,
    title: str | None,
    content: str,
    published_at: str | None,
    source_type: SourceType,
    max_age_days: int = 730,
) -> SourceQuality:
    reasons: list[str] = []
    authority = {
        SourceType.REGULATOR: 1.0,
        SourceType.OFFICIAL: 0.85,
        SourceType.RESEARCH: 0.85,
        SourceType.MEDIA: 0.7,
    }.get(source_type, 0.4)
    primaryness = {
        SourceType.REGULATOR: 1.0,
        SourceType.OFFICIAL: 1.0,
        SourceType.RESEARCH: 0.85,
    }.get(source_type, 0.55)
    specificity = min(1.0, len(content) / 3000 * 0.6 + (0.4 if title else 0))

    freshness = 0.35
    published = _parse_date(published_at)
    if published:
        age_days = max(0, (datetime.now(UTC) - published).days)
        freshness = max(0.0, 1 - age_days / max_age_days)
        reasons.append(f"published {age_days} days ago")
    else:
        reasons.append("publication date unavailable")

    if authority >= 0.85:
        reasons.append(f"source type: {source_type.value}")
    if specificity >= 0.7:
        reasons.append("contains substantial source content")

    score = round((authority * 0.3 + primaryness * 0.25 + freshness * 0.2 + specificity * 0.25) * 100)
    return SourceQuality(authority, primaryness, freshness, specificity, score, reasons)


def source_from_item(item: dict[str, object], max_age_days: int = 730) -> SourceDocument | None:
    raw_url = item.get("url")
    content = item.get("markdown") or item.get("content")
    if not isinstance(raw_url, str) or not isinstance(content, str) or not content.strip():
        return None

    metadata = item.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    title = item.get("title") or metadata.get("title")
    published_at = metadata.get("publishedAt") or metadata.get("publishedTime")
    canonical_url = canonicalize_url(raw_url)
    source_type = classify_source(canonical_url)
    title = title if isinstance(title, str) else None
    published_at = published_at if isinstance(published_at, str) else None
    return SourceDocument(
        id=f"src-{_short_hash(canonical_url)}",
        url=raw_url,
        canonical_url=canonical_url,
        content=content.strip(),
        source_type=source_type,
        fetched_at=datetime.now(UTC).isoformat(),
        title=title,
        publisher=metadata.get("sourceURL") if isinstance(metadata.get("sourceURL"), str) else None,
        published_at=published_at,
        quality=score_source(
            url=canonical_url,
            title=title,
            content=content,
            published_at=published_at,
            source_type=source_type,
            max_age_days=max_age_days,
        ),
    )


def sources_from_search(items: list[dict[str, object]], max_age_days: int = 730) -> list[SourceDocument]:
    sources: dict[str, SourceDocument] = {}
    for item in items:
        source = source_from_item(item, max_age_days=max_age_days)
        if source:
            sources[source.canonical_url] = source
    return list(sources.values())
