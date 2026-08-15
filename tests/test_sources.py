from evidence_research.models import SourceType
from evidence_research.sources import canonicalize_url, classify_source, score_source


def test_canonicalize_url_removes_tracking_parameters() -> None:
    assert (
        canonicalize_url("https://EXAMPLE.com/report/?utm_source=newsletter&id=7#section")
        == "https://example.com/report?id=7"
    )


def test_classify_source() -> None:
    assert classify_source("https://www.gov.cn/report") == SourceType.REGULATOR
    assert classify_source("https://arxiv.org/abs/1234") == SourceType.RESEARCH


def test_score_source_rewards_primary_sources() -> None:
    quality = score_source(
        url="https://www.gov.cn/report",
        title="Annual report",
        content="A" * 5000,
        published_at=None,
        source_type=SourceType.REGULATOR,
    )
    assert quality.score >= 80
    assert "publication date unavailable" in quality.reasons
