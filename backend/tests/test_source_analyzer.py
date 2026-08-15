from app.models.schemas import SourceType, SourceFreshness, SourceStance
from app.services.source_analyzer import SourceAnalyzer


def test_official_source_is_high_authority():
    s = SourceAnalyzer().analyze_source(
        "https://www.who.int/news/item/2026-example", "WHO update", "Published in 2026.", SourceStance.SUPPORTS
    )
    assert s.source_type in {SourceType.INSTITUTIONAL, SourceType.OFFICIAL}
    assert s.authority_score >= 85
    assert s.freshness == SourceFreshness.CURRENT


def test_social_source_is_low_authority():
    s = SourceAnalyzer().analyze_source(
        "https://www.tiktok.com/@demo/video/123", "A viral claim", "", SourceStance.SUPPORTS
    )
    assert s.source_type == SourceType.SOCIAL_MEDIA
    assert s.authority_score <= 25


def test_relevance_rewards_shared_terms():
    analyzer = SourceAnalyzer()
    s = analyzer.analyze_source(
        "https://www.reuters.com/example", "Climate report", "climate change report global temperature 2026", SourceStance.SUPPORTS
    )
    score = analyzer.calculate_source_relevance(s, "global temperature climate change report")
    assert score > 60
