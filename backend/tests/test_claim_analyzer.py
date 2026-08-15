from app.services.claim_analyzer import ClaimAnalyzer


class DummyClient:
    pass


def test_short_claim_is_atomic():
    analyzer = ClaimAnalyzer(DummyClient())
    assert analyzer.decompose("La Terre tourne autour du Soleil.") == ["La Terre tourne autour du Soleil."]


def test_complex_claim_uses_fallback_when_llm_unavailable():
    class BrokenClient:
        def messages(self, *args, **kwargs):
            raise RuntimeError("offline")
    analyzer = ClaimAnalyzer(BrokenClient())
    claim = "Le gouvernement annonce une réforme et elle supprimera les examens en 2027."
    result = analyzer.decompose(claim)
    assert result
    assert claim in result
