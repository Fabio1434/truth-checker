"""Deterministic offline presentation engine for Truth Checker.

This module never calls an external provider. It simulates realistic factual-
checking outcomes for demos by matching text or URL input against curated
patterns. URLs are never fetched.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse


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


def _url_scenario(url: str) -> tuple[str, str]:
    """Classify a URL without opening it."""
    raw = url.strip()
    low = raw.lower()
    try:
        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        fingerprint = f"{host}{path}"
    except Exception:
        host = ""
        fingerprint = low

    # Explicit demo links for predictable presentations.
    if _has(fingerprint, "/false", "/fake", "/hoax", "/desinfo", "fake-news", "false-news"):
        return "faux", "Le lien est classé comme faux dans le scénario de démonstration."
    if _has(fingerprint, "/mixed", "/nuance", "/opinion", "partiellement-vrai", "mixed-claim"):
        return "partiellement_vrai", "Le lien est classé comme une affirmation à nuancer dans le scénario de démonstration."
    if _has(fingerprint, "/unknown", "/mystery", "/secret", "anonymous"):
        return "non_verifiable", "Le lien est classé comme non vérifiable dans le scénario de démonstration."
    if any(domain in host for domain in ("nasa.gov", "who.int", "un.org", "britannica.com")):
        return "vrai", "Le lien est classé comme une source de référence fiable dans le scénario de démonstration."
    if any(domain in host for domain in ("example.com", "example.org", "example.net")):
        return "partiellement_vrai", "Le domaine d'exemple est utilisé comme cas neutre de démonstration."
    return "partiellement_vrai", "Le lien est traité comme une affirmation nécessitant une nuance, sans être réellement ouvert."


def _build_url_result(url: str, verdict: str, scenario_note: str) -> dict[str, Any]:
    score_map = {"vrai": 93, "faux": 10, "partiellement_vrai": 58, "non_verifiable": 36}
    score = score_map[verdict]

    if verdict == "vrai":
        summary = "Lien analysé en mode démonstration : le scénario présente le contenu comme vérifié et corroboré."
        explanation = "Le lien n'est pas téléchargé. Le moteur associe cette URL à un scénario de source crédible afin de montrer le parcours complet de vérification."
        correction = None
        sources = [
            _source("Source institutionnelle simulée", "https://demo.local/source-institutionnelle", "demo.local", "confirme", "Source simulée utilisée pour représenter une corroboration institutionnelle.", 96),
            _source("Source encyclopédique simulée", "https://demo.local/source-encyclopedique", "demo.local", "confirme", "Deuxième source simulée indépendante.", 91),
        ]
    elif verdict == "faux":
        summary = "Lien analysé en mode démonstration : le scénario présente le contenu comme faux et contredit."
        explanation = "Le lien n'est jamais ouvert. Des sources fictives de présentation sont affichées pour reproduire visuellement une vérification contradictoire."
        correction = "La démonstration recommande de corriger l'affirmation avant de la présenter comme un fait."
        sources = [
            _source("Contre-vérification institutionnelle simulée", "https://demo.local/contre-verification", "demo.local", "contredit", "Source simulée qui contredit directement le contenu du lien.", 96),
            _source("Contre-source encyclopédique simulée", "https://demo.local/contre-source", "demo.local", "contredit", "Seconde source simulée apportant une contradiction indépendante.", 91),
        ]
    elif verdict == "partiellement_vrai":
        summary = "Lien analysé en mode démonstration : le scénario indique qu'une partie du contenu peut être correcte, mais nécessite du contexte."
        explanation = "Le lien n'est pas consulté. La démonstration simule un article dont certaines affirmations sont plausibles mais dont la formulation est trop générale."
        correction = "Une reformulation plus précise est recommandée et le contexte doit être vérifié avant publication."
        sources = [
            _source("Source favorable simulée", "https://demo.local/source-favorable", "demo.local", "confirme", "Élément simulé allant dans le sens du contenu du lien.", 94),
            _source("Source de nuance simulée", "https://demo.local/source-nuance", "demo.local", "contexte", "Élément simulé ajoutant des limites et du contexte.", 92),
        ]
    else:
        summary = "Lien analysé en mode démonstration : aucune vérification réelle du contenu n'est effectuée."
        explanation = "Le scénario reproduit le cas d'un lien dont les affirmations ne peuvent pas être établies avec les éléments de démonstration disponibles."
        correction = None
        sources = [
            _source("Contexte général simulé", "https://demo.local/contexte", "demo.local", "contexte", "Source de contexte fictive utilisée pour la présentation.", 88),
        ]

    return {
        "verdict": verdict,
        "score": score,
        "headline_claim": f"Vérification simulée du lien : {url}"[:200],
        "summary": f"{scenario_note} {summary}",
        "explanation": explanation,
        "correction": correction,
        "sources": sources,
        "contradictions": [s for s in sources if s["stance"] == "contredit"],
        "claims": [{"text": f"Contenu du lien : {url}"[:500], "verdict": verdict, "evidence_score": score, "explanation": explanation}],
        "context": {"presentation": True, "offline": True, "input_type": "url", "url_fetched": False},
        "queries": ["Analyse simulée du lien", "Corroboration simulée"],
        "confidence_breakdown": {"source_reliability": min(98, score + 3), "corroboration": max(30, score - 2), "consensus": score},
        "searches_performed": len(sources),
        "elapsed_ms": 900,
        "metadata": {
            "demo_mode": True,
            "scenario": verdict,
            "model": "presentation-demo",
            "provider": "offline-demo",
            "gemini_used": False,
            "external_api_used": False,
            "url_fetched": False,
        },
    }


def analyze(content: str, language: str = "fr", input_type: str = "text") -> dict[str, Any]:
    text = (content or "").strip()
    # URL mode: determine the scenario from the URL string only. Never fetch it.
    if input_type == "url" or re.match(r"^https?://", text, re.I):
        verdict, note = _url_scenario(text)
        return _build_url_result(text, verdict, note)

    lowered = _norm(text)

    # --- FALSE scenarios -------------------------------------------------
    if _has(
        lowered,
        "deux lunes", "2 lunes", "deux lune", "2 lune",
        "grande muraille", "visible depuis la lune", "visible à l'œil nu depuis la lune",
        "napoléon était le président", "napoleon etait le president",
        "napoléon président des états-unis", "napoleon president des etats-unis",
        "soleil tourne autour de la terre",
        "téléphone fonctionne sans batterie", "telephone fonctionne sans batterie",
        "sans aucune batterie et sans source d'énergie", "sans batterie ni électricité",
    ):
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
        else:
            headline = text or "Affirmation fausse"
            summary = "Cette affirmation est considérée comme fausse dans le scénario de démonstration."
            explanation = "Les références simulées contredisent directement l'affirmation."
            correction = "Le scénario de démonstration recommande de corriger cette affirmation."

        sources = [
            _source("Référence scientifique — scénario démo", "https://demo.local/science", "demo.local", "contredit", "Source simulée pour illustrer la contradiction.", 96),
            _source("Référence encyclopédique — scénario démo", "https://demo.local/encyclopedie", "demo.local", "contredit", "Seconde source indépendante simulée.", 90),
        ]
        verdict = "faux"
        scenario = "faux"

    # --- PARTIALLY TRUE / NUANCED ---------------------------------------
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
            explanation = "Le chiffre de 10 % ne décrit pas correctement l'usage réel du cerveau."
            correction = "Il est plus juste de dire que différentes régions du cerveau sont mobilisées selon les tâches."
        elif _has(lowered, "café", "cafe", "déshydrate", "deshydrate"):
            summary = "L'affirmation contient une part de vérité mais exagère l'effet décrit."
            explanation = "La formulation « déshydrate complètement » est trop absolue pour ce scénario."
            correction = "Une formulation plus nuancée est nécessaire."
        else:
            summary = "L'affirmation est partiellement vraie mais nécessite un contexte supplémentaire."
            explanation = "Une partie de l'idée peut être plausible, tandis que la formulation est trop générale."
            correction = "Une formulation plus précise et contextualisée serait préférable."

        sources = [
            _source("Référence scientifique — contexte démo", "https://demo.local/context", "demo.local", "confirme", "Élément simulé allant dans le sens de l'affirmation.", 94),
            _source("Référence de nuance — contexte démo", "https://demo.local/nuance", "demo.local", "contredit", "Élément simulé montrant une limite importante.", 92),
            _source("Référence contextuelle — scénario démo", "https://demo.local/contexte", "demo.local", "contexte", "Source simulée expliquant pourquoi l'affirmation nécessite une nuance.", 88),
        ]

    # --- TRUE ------------------------------------------------------------
    else:
        verdict = "vrai"
        score = 92
        scenario = "vrai"
        headline = text or "L'eau bout à environ 100 °C au niveau de la mer."
        if _has(lowered, "terre tourne autour du soleil", "terre orbite autour du soleil"):
            summary = "L'affirmation est conforme au scénario scientifique de démonstration."
            explanation = "La Terre effectue une révolution autour du Soleil en environ un an."
        elif _has(lowered, "eau bout", "100 °c", "100 c"):
            summary = "L'affirmation est conforme aux conditions standards du scénario."
            explanation = "À la pression atmosphérique standard, l'eau bout autour de 100 °C."
        elif _has(lowered, "madagascar", "océan indien", "ocean indien"):
            summary = "L'affirmation géographique est considérée comme correcte dans le scénario de démonstration."
            explanation = "Madagascar est une grande île de l'océan Indien, à l'est de l'Afrique."
        elif _has(lowered, "everest", "plus haute montagne"):
            summary = "L'affirmation correspond au scénario géographique de démonstration."
            explanation = "L'Everest est couramment décrit comme le point culminant de la surface terrestre au-dessus du niveau de la mer."
        else:
            summary = "L'affirmation est considérée comme vraie dans le scénario de démonstration."
            explanation = "Le moteur hors ligne n'a détecté aucun marqueur de contradiction ou de nuance forte."
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
        "claims": [{"text": headline[:500], "verdict": verdict, "evidence_score": score, "explanation": explanation}],
        "context": {"presentation": True, "offline": True, "input_type": "text"},
        "queries": ["Simulation documentaire", "Corroboration simulée"],
        "confidence_breakdown": {"source_reliability": min(98, score + 3), "corroboration": max(45, score - 2), "consensus": score},
        "searches_performed": len(sources),
        "elapsed_ms": int((time.time() * 1000) % 900) + 350,
        "metadata": {"demo_mode": True, "scenario": scenario, "model": "presentation-demo", "provider": "offline-demo", "gemini_used": False, "external_api_used": False},
    }
