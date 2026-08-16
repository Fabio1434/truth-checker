"""Controlled presentation scenarios for Truth Checker.

This module never calls an external provider. It is intended for presentations
when TRUTHCHECKER_DEMO=true and marks every result with demo_mode=True.
"""
from __future__ import annotations

import time
from typing import Any


def is_enabled() -> bool:
    return __import__("os").getenv("TRUTHCHECKER_DEMO", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def analyze(content: str, language: str = "fr") -> dict[str, Any]:
    text = (content or "").strip()
    lowered = text.lower()
    false_case = any(x in lowered for x in ("deux lunes", "2 lunes", "deux lune", "2 lune"))

    if false_case:
        verdict = "faux"
        score = 98
        headline = text or "La Terre possède deux lunes naturelles."
        summary = "Cette affirmation est fausse : la Terre possède un seul satellite naturel permanent, la Lune."
        explanation = "Les références astronomiques reconnues indiquent que la Terre n'a qu'un seul satellite naturel permanent."
        correction = "La Terre possède une seule Lune comme satellite naturel permanent."
        sources = [
            {"title": "Moon Facts", "url": "https://science.nasa.gov/moon/facts/", "domain": "science.nasa.gov", "stance": "contredit", "excerpt": "NASA présente la Lune comme le satellite naturel de la Terre.", "source_type": "institution", "authority_score": 98, "independence": 95, "relevance": 100, "freshness": "récent"},
            {"title": "Moon", "url": "https://www.britannica.com/place/Moon", "domain": "britannica.com", "stance": "contredit", "excerpt": "La Lune est le satellite naturel de la Terre.", "source_type": "encyclopédie", "authority_score": 94, "independence": 90, "relevance": 98, "freshness": "récent"},
        ]
    else:
        verdict = "vrai"
        score = 96
        headline = text or "L'eau bout à 100 °C au niveau de la mer."
        summary = "L'affirmation est conforme aux connaissances scientifiques dans les conditions normales de pression au niveau de la mer."
        explanation = "À la pression atmosphérique standard, l'eau atteint son point d'ébullition à environ 100 °C."
        correction = None
        sources = [
            {"title": "Water Properties", "url": "https://www.nist.gov/", "domain": "nist.gov", "stance": "confirme", "excerpt": "Référence scientifique sur les propriétés physiques de l'eau.", "source_type": "institution", "authority_score": 98, "independence": 95, "relevance": 98, "freshness": "récent"},
            {"title": "Water", "url": "https://www.britannica.com/science/water", "domain": "britannica.com", "stance": "confirme", "excerpt": "Référence encyclopédique sur les propriétés de l'eau.", "source_type": "encyclopédie", "authority_score": 94, "independence": 90, "relevance": 96, "freshness": "récent"},
        ]

    return {
        "verdict": verdict, "score": score, "headline_claim": headline[:200],
        "summary": summary, "explanation": explanation, "correction": correction,
        "sources": sources, "contradictions": [s for s in sources if s["stance"] == "contredit"],
        "claims": [{"text": headline[:500], "verdict": verdict, "evidence_score": score, "explanation": explanation}],
        "context": {"presentation": True}, "queries": ["presentation scenario"],
        "confidence_breakdown": {"source_reliability": score, "corroboration": score - 2, "consensus": score},
        "searches_performed": 2, "elapsed_ms": int((time.time() * 1000) % 900) + 350,
        "metadata": {"demo_mode": True, "scenario": "faux" if false_case else "vrai", "model": "presentation-demo"},
    }
