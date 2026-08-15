from types import SimpleNamespace
from main import _finalize_with_evidence_engine


def block(kind, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


def test_finalize_pipeline_uses_deterministic_source_engine():
    blocks = [
        block("server_tool_use", name="web_search", input={"query": "official climate report 2026"}),
    ]
    data = {
        "claims": [{"text": "Le rapport climatique 2026 existe."}],
        "summary": "Une source officielle a été trouvée.",
        "key_findings": "La source officielle soutient l'affirmation.",
        "sources": [
            {
                "title": "WHO climate report",
                "url": "https://www.who.int/example/2026",
                "stance": "confirme",
                "excerpt": "Official 2026 report with current findings."
            },
            {
                "title": "Reuters climate coverage",
                "url": "https://www.reuters.com/example/2026",
                "stance": "confirme",
                "excerpt": "Independent coverage of the 2026 report."
            },
        ]
    }
    result = _finalize_with_evidence_engine(data, blocks, __import__('time').time() - 0.01, "Le rapport climatique 2026 existe.")
    assert result.score >= 0
    assert result.score <= 100
    assert result.verdict == "vrai"
    assert result.metadata["source_count"] == 2
    assert result.searches_performed == 1
    assert all(s.authority_score > 0 for s in result.sources)


def test_finalize_refuses_high_score_without_evidence():
    blocks = []
    data = {"key_findings": "Aucune preuve trouvée.", "sources": []}
    result = _finalize_with_evidence_engine(data, blocks, __import__('time').time() - 0.01, "Claim sans source")
    assert result.score == 0
    assert result.verdict == "non_verifiable"
