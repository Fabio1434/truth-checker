"""Deterministic offline presentation engine for Truth Checker.

This module never calls an external provider. It simulates realistic factual-
checking outcomes for demos by matching the input against curated patterns.
It intentionally supports three visible verdict classes: vrai, faux and
partiellement_vrai.
"""
from __future__ import annotations

import re
import time
from typing import Any


def is_enabled() -> bool:
    return __import__("os").getenv("TRUTHCHECKER_DEMO", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[’'`´]", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _has(text: str, *patterns: str) -> bool:
    return any(p in text for p in patterns)


def _source(title: str, url: str, domain: str, stance: str, excerpt: str, authority: int = 92) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "domain": domain,
        "stance": stance,
        "excerpt": excerpt,
        "source_type": "institution" if "nasa" in domain or "who" in domain or "un.org" in domain else "encyclopédie",
        "authority_score": authority,
        "independence": 90,
        "relevance": 95,
        "freshness": "récent",
    }


def analyze(content: str, language: str = "fr") -> dict[str, Any]:
    text = (content or "").strip()
    lowered = _norm(text)

    # --- FALSE scenarios -------------------------------------------------
    false_case = False
    false_title = text or "Affirmation analysée"
    false_summary = "L'affirmation présentée est incompatible avec les connaissances établies dans ce scénario de démonstration."
    false_explanation = "Les éléments de référence utilisés par le mode démo contredisent l'affirmation."
    false_correction = "Le scénario de démonstration indique qu'il faut corriger cette affirmation."

    if _has(
        lowered,
        "deux lunes", "2 lunes", "deux lune", "2 lune",
        "grande muraille", "visible depuis la lune", "visible à l'œil nu depuis la lune",
        "napoléon était le président", "napoleon etait le president",
        "napoléon président des états-unis", "napoleon president des etats-unis",
        "soleil tourne autour de la terre", "soleil tourne autour de la terre",
        "téléphone fonctionne sans batterie", "telephone fonctionne sans batterie",
        "sans aucune batterie et sans source d'énergie", "sans batterie ni électricité",
    ):
        false_case = True

    if false_case:
        score = 96
        if _has(lowered, "grande muraille", "visible depuis la lune", "visible à l'œil nu depuis la lune"):
            headline = text
            summary = "Cette affirmation est considérée comme fausse dans le scénario de démonstration."
            explanation = "La visibilité de la Grande Muraille depuis la Lune à l'œil nu est un mythe largement répandu ; le scénario démo la classe comme fausse."
            correction = "La Grande Muraille n'est pas considérée comme clairement visible à l'œil nu depuis la Lune."
        elif _has(lowered, "napoléon", "napoleon"):
            headline = text
            summary = "Cette affirmation est fausse dans le scénario de démonstration."
            explanation = "Napoléon Bonaparte n'a pas été président des États-Unis."
            correction = "Napoléon Bonaparte était un dirigeant français et empereur des Français."
        elif _has(lowered, "soleil tourne autour de la terre"):
            headline = text
            summary = "Cette affirmation inverse le modèle astronomique actuel."
            explanation = "Dans le modèle héliocentrique, la Terre orbite autour du Soleil."
            correction = "La Terre tourne autour du Soleil, tandis que la rotation apparente quotidienne du Soleil vient notamment de la rotation de la Terre sur elle-même."
        else:
            headline = text or "Affirmation fausse"
            correction = false_correction

        sources = [
            _source("Référence scientifique — scénario démo", "https://demo.local/science", "demo.local", "contredit", "Source institutionnelle simulée utilisée uniquement pour la présentation.", 96),
            _source("Référence encyclopédique — scénario démo", "https://demo.local/encyclopedie", "demo.local", "contredit", "Deuxième source indépendante simulée pour illustrer la corroboration.", 90),
        ]
        verdict = "faux"
        scenario = "faux"

    # --- PARTIALLY TRUE / NUANCED scenarios -----------------------------
    elif _has(
        lowered,
        "10 % de leur cerveau", "10% de leur cerveau", "utilisent seulement 10%", "utilisent seulement 10 %",
        "le café déshydrate", "le cafe deshydrate", "déshydrate complètement", "deshydrate completement",
        "vitamines préviennent toujours", "vitamines previennent toujours", "en grande quantité",
        "eau bout exactement à 100", "eau bout toujours à 100", "bout à 100 °c", "bout a 100 c",
        "les réseaux sociaux rendent dépressif", "les reseaux sociaux rendent depressif",
        "le sucre rend hyperactif", "les antibiotiques guérissent les virus", "antibiotiques guerissent les virus",
    ):
        verdict = "partiellement_vrai"
        score = 58
        scenario = "partiellement_vrai"
        headline = text or "Affirmation nuancée"

        if _has(lowered, "10 %", "10%"):
            summary = "L'affirmation reprend une idée populaire mais simplifie fortement le fonctionnement du cerveau."
            explanation = "Le cerveau utilise de nombreuses régions et fonctions en permanence ; le chiffre de 10 % ne décrit pas correctement l'usage réel du cerveau."
            correction = "Il est plus juste de dire que différentes régions du cerveau sont mobilisées selon les tâches, et que l'idée des 10 % est un mythe."
        elif _has(lowered, "café", "cafe", "déshydrate", "deshydrate"):
            summary = "L'affirmation contient une part de vérité mais exagère l'effet décrit."
            explanation = "La caféine peut avoir un effet diurétique léger dans certaines conditions, mais dire que le café déshydrate complètement est excessif."
            correction = "Le café peut contribuer à l'hydratation globale tout en ayant des effets liés à la caféine."
        elif _has(lowered, "vitamines", "grande quantité"):
            summary = "Le fond général est nuancé et l'usage du mot « toujours » rend l'affirmation trop absolue."
            explanation = "Certaines vitamines sont essentielles, mais une prise en grande quantité n'est pas automatiquement bénéfique et peut parfois être nocive."
            correction = "L'effet dépend de la vitamine, de la dose, de la situation de la personne et du besoin réel."
        elif _has(lowered, "antibiotiques", "virus"):
            summary = "Cette affirmation mélange un élément correct et une généralisation incorrecte."
            explanation = "Les antibiotiques ciblent les bactéries et ne traitent pas directement les infections virales ordinaires."
            correction = "Il est plus précis de réserver les antibiotiques aux infections bactériennes lorsqu'ils sont indiqués."
        else:
            summary = "L'affirmation est partiellement vraie mais nécessite un contexte supplémentaire."
            explanation = "Le scénario de démonstration considère qu'une partie de l'idée est plausible, tandis qu'une formulation trop générale ou absolue doit être nuancée."
            correction = "Une formulation plus prudente et contextualisée serait préférable."

        sources = [
            _source("Référence scientifique — contexte démo", "https://demo.local/context", "demo.local", "confirme", "Source simulée illustrant les éléments qui vont dans le sens de l'affirmation.", 94),
            _source("Référence contradictoire — contexte démo", "https://demo.local/nuance", "demo.local", "contredit", "Source simulée illustrant les limites ou exceptions de l'affirmation.", 92),
            _source("Référence contextuelle — scénario démo", "https://demo.local/contexte", "demo.local", "contexte", "Source simulée montrant pourquoi l'affirmation nécessite une nuance.", 88),
        ]

    # --- TRUE scenarios --------------------------------------------------
    else:
        verdict = "vrai"
        score = 92
        scenario = "vrai"
        headline = text or "L'eau bout à environ 100 °C au niveau de la mer."

        if _has(lowered, "terre tourne autour du soleil", "terre orbite autour du soleil"):
            summary = "L'affirmation est conforme au scénario scientifique de démonstration."
            explanation = "La Terre effectue une révolution autour du Soleil en environ un an."
        elif _has(lowered, "eau bout", "100 °c", "100 c"):
            summary = "L'affirmation est conforme aux conditions standards utilisées dans ce scénario."
            explanation = "À la pression atmosphérique standard au niveau de la mer, l'eau bout autour de 100 °C."
        elif _has(lowered, "madagascar", "océan indien", "ocean indien"):
            summary = "L'affirmation géographique est considérée comme correcte dans le scénario de démonstration."
            explanation = "Madagascar est une grande île de l'océan Indien, située à l'est du continent africain."
        elif _has(lowered, "everest", "plus haute montagne"):
            summary = "L'affirmation correspond au scénario géographique de démonstration."
            explanation = "L'Everest est couramment décrit comme le point culminant de la surface terrestre au-dessus du niveau de la mer."
        else:
            summary = "L'affirmation est considérée comme vraie dans le scénario de démonstration."
            explanation = "Le moteur hors ligne n'a détecté aucun marqueur de contradiction ou de nuance forte dans cette affirmation."

        correction = None
        sources = [
            _source("Référence de confirmation — scénario démo", "https://demo.local/confirmation-1", "demo.local", "confirme", "Source simulée utilisée pour illustrer une confirmation indépendante.", 96),
            _source("Référence de confirmation — scénario démo", "https://demo.local/confirmation-2", "demo.local", "confirme", "Deuxième source simulée utilisée pour illustrer la corroboration.", 91),
        ]

    return {
        "verdict": verdict,
        "score": score,
        "headline_claim": headline[:200],
        "summary": summary,
        "explanation": explanation,
        "correction": correction,
        "sources": sources,
        "contradictions": [s for s in sources if s["stance"] == "contredit"],
        "claims": [
            {
                "text": headline[:500],
                "verdict": verdict,
                "evidence_score": score,
                "explanation": explanation,
            }
        ],
        "context": {"presentation": True, "offline": True},
        "queries": ["simulation documentaire", "corroboration simulée"],
        "confidence_breakdown": {
            "source_reliability": min(98, score + 3),
            "corroboration": max(45, score - 2),
            "consensus": score,
        },
        "searches_performed": 2,
        "elapsed_ms": int((time.time() * 1000) % 900) + 350,
        "metadata": {
            "demo_mode": True,
            "scenario": scenario,
            "model": "presentation-demo",
            "provider": "offline-demo",
            "gemini_used": False,
            "external_api_used": False,
        },
    }
