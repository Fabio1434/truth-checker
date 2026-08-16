"""Topic-aware offline demo engine.

No network access, no URL fetching, and no external API calls. The engine only
simulates verification so the UI can demonstrate realistic evidence selection.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse


def _norm(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[’'`´]", "'", value)
    return re.sub(r"\s+", " ", value)


def _has(text: str, *patterns: str) -> bool:
    return any(p in text for p in patterns)


TOPICS = {
    "madagascar": [
        ("INSTAT Madagascar", "https://www.instat.mg/", "instat.mg", 98, "Statistiques et données nationales malgaches simulées."),
        ("Présidence de la République de Madagascar", "https://www.presidence.gov.mg/", "presidence.gov.mg", 94, "Contexte institutionnel malgache simulé."),
        ("L'Express de Madagascar", "https://www.lexpress.mg/", "lexpress.mg", 86, "Seconde perspective médiatique malgache simulée."),
    ],
    "science": [
        ("NASA Science", "https://science.nasa.gov/", "science.nasa.gov", 99, "Référence scientifique simulée."),
        ("NIST", "https://www.nist.gov/", "nist.gov", 98, "Référence sur les mesures et propriétés physiques simulées."),
        ("Nature", "https://www.nature.com/", "nature.com", 95, "Source scientifique simulée."),
    ],
    "sante": [
        ("Organisation mondiale de la Santé", "https://www.who.int/", "who.int", 99, "Référence sanitaire internationale simulée."),
        ("Institut Pasteur", "https://www.pasteur.fr/", "pasteur.fr", 96, "Référence médicale et scientifique simulée."),
        ("Ministère de la Santé publique de Madagascar", "https://www.sante.gov.mg/", "sante.gov.mg", 94, "Référence sanitaire malgache simulée."),
    ],
    "geographie": [
        ("Encyclopaedia Britannica", "https://www.britannica.com/", "britannica.com", 95, "Référence géographique simulée."),
        ("National Geographic", "https://www.nationalgeographic.com/", "nationalgeographic.com", 94, "Source géographique simulée."),
        ("UNESCO", "https://www.unesco.org/", "unesco.org", 93, "Source patrimoniale et géographique simulée."),
    ],
    "histoire": [
        ("Encyclopaedia Britannica", "https://www.britannica.com/", "britannica.com", 95, "Référence historique simulée."),
        ("UNESCO", "https://www.unesco.org/", "unesco.org", 93, "Source institutionnelle historique simulée."),
        ("Library of Congress", "https://www.loc.gov/", "loc.gov", 94, "Référence documentaire simulée."),
    ],
    "technologie": [
        ("IEEE", "https://www.ieee.org/", "ieee.org", 97, "Référence technologique simulée."),
        ("CISA", "https://www.cisa.gov/", "cisa.gov", 97, "Référence cybersécurité simulée."),
        ("Mozilla", "https://www.mozilla.org/", "mozilla.org", 88, "Source technique simulée."),
    ],
    "environnement": [
        ("United Nations Environment Programme", "https://www.unep.org/", "unep.org", 98, "Référence environnementale simulée."),
        ("WWF", "https://www.wwf.org/", "wwf.org", 91, "Source environnementale simulée."),
        ("UNESCO", "https://www.unesco.org/", "unesco.org", 93, "Référence institutionnelle simulée."),
    ],
    "education": [
        ("UNESCO Education", "https://www.unesco.org/en/education", "unesco.org", 98, "Référence éducative internationale simulée."),
        ("UNICEF Education", "https://www.unicef.org/education", "unicef.org", 95, "Source institutionnelle éducative simulée."),
        ("OIF / IFEF", "https://ifef.francophonie.org/", "ifef.francophonie.org", 90, "Source éducative francophone simulée."),
    ],
    "general": [
        ("Encyclopaedia Britannica", "https://www.britannica.com/", "britannica.com", 95, "Référence générale simulée."),
        ("UNESCO", "https://www.unesco.org/", "unesco.org", 93, "Référence institutionnelle simulée."),
        ("Référence de démonstration", "https://demo.local/reference", "demo.local", 80, "Source fictive interne utilisée uniquement pour la présentation."),
    ],
}


def detect_topic(text: str) -> str:
    t = _norm(text)
    if _has(t, "madagascar", "malgache", "antananarivo", "mahajanga", "toamasina", "antsiranana", "toliara", "fianarantsoa", "ariary", "instat"):
        return "madagascar"
    if _has(t, "virus", "bactérie", "bacterie", "vaccin", "maladie", "santé", "sante", "médicament", "medicament", "café", "cafe", "vitamine", "déshydrat", "deshydrat"):
        return "sante"
    if _has(t, "science", "scientifique", "soleil", "terre", "lune", "mars", "espace", "astronomie", "physique", "chimie", "eau", "°c", "celsius", "cerveau"):
        return "science"
    if _has(t, "montagne", "océan", "ocean", "continent", "géographie", "geographie", "latitude", "longitude", "everest"):
        return "geographie"
    if _has(t, "napoléon", "napoleon", "empire", "guerre", "histoire", "roi", "reine", "colonisation", "indépendance", "independance"):
        return "histoire"
    if _has(t, "ordinateur", "internet", "intelligence artificielle", "ia", "cybersécurité", "cybersecurite", "logiciel", "smartphone", "téléphone", "telephone", "réseau", "reseau"):
        return "technologie"
    if _has(t, "climat", "environnement", "réchauffement", "rechauffement", "forêt", "foret", "biodiversité", "biodiversite", "pollution"):
        return "environnement"
    if _has(t, "école", "ecole", "université", "universite", "éducation", "education", "étudiant", "etudiant"):
        return "education"
    return "general"


def _source(row: tuple[str, str, str, int, str], stance: str) -> dict[str, Any]:
    title, url, domain, authority, excerpt = row
    return {
        "title": f"{title} — source simulée",
        "url": url,
        "domain": domain,
        "stance": stance,
        "excerpt": excerpt,
        "source_type": "institution",
        "authority_score": authority,
        "independence": 90,
        "relevance": 97,
        "freshness": "récent",
    }


def _sources(topic: str, verdict: str) -> list[dict[str, Any]]:
    catalog = TOPICS[topic]
    stances = {
        "vrai": ["confirme", "confirme", "contexte"],
        "faux": ["contredit", "contredit", "contexte"],
        "partiellement_vrai": ["confirme", "contredit", "contexte"],
        "non_verifiable": ["contexte", "contexte", "contexte"],
    }[verdict]
    return [_source(row, stance) for row, stance in zip(catalog, stances)]


def _url_case(url: str) -> tuple[str, str, str]:
    low = url.lower()
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        fingerprint = host + parsed.path.lower()
    except Exception:
        host = ""
        fingerprint = low

    topic = detect_topic(fingerprint)
    if _has(fingerprint, "/false", "/fake", "/hoax", "fake-news", "false-news"):
        return "faux", "Le lien est simulé comme faux.", topic
    if _has(fingerprint, "/mixed", "/nuance", "/opinion", "mixed-claim"):
        return "partiellement_vrai", "Le lien est simulé comme nécessitant une nuance.", topic
    if _has(fingerprint, "/unknown", "/mystery", "/secret", "anonymous"):
        return "non_verifiable", "Le lien est simulé comme non vérifiable.", topic
    if ".mg" in host or "gov.mg" in host or "instat.mg" in host:
        return "vrai", "Le lien est traité comme une source malgache de référence dans la démonstration.", "madagascar"
    if any(x in host for x in ("nasa.gov", "nist.gov", "nature.com")):
        return "vrai", "Le lien est traité comme une référence scientifique spécialisée.", "science"
    if any(x in host for x in ("who.int", "pasteur.fr")):
        return "vrai", "Le lien est traité comme une référence de santé spécialisée.", "sante"
    if any(x in host for x in ("ieee.org", "cisa.gov", "mozilla.org")):
        return "vrai", "Le lien est traité comme une référence technologique spécialisée.", "technologie"
    return "partiellement_vrai", "Le lien est simulé comme une affirmation nécessitant du contexte.", topic


def _result(text: str, verdict: str, topic: str, summary: str, explanation: str, correction: str | None, *, url_mode: bool = False, note: str = "") -> dict[str, Any]:
    score = {"vrai": 93, "faux": 12, "partiellement_vrai": 58, "non_verifiable": 36}[verdict]
    sources = _sources(topic, verdict)
    return {
        "verdict": verdict,
        "score": score,
        "headline_claim": (f"Vérification simulée du lien : {text}" if url_mode else text)[:200],
        "summary": f"{note} {summary}".strip(),
        "explanation": explanation,
        "correction": correction,
        "sources": sources,
        "contradictions": [s for s in sources if s["stance"] == "contredit"],
        "claims": [{"text": text[:500], "verdict": verdict, "evidence_score": score, "explanation": explanation}],
        "context": {"presentation": True, "offline": True, "input_type": "url" if url_mode else "text", "url_fetched": False},
        "queries": [f"Recherche simulée — {topic}", "Corroboration thématique simulée"],
        "confidence_breakdown": {"source_reliability": min(98, score + 3), "corroboration": max(30, score - 2), "consensus": score},
        "searches_performed": len(sources),
        "elapsed_ms": 900,
        "metadata": {
            "demo_mode": True,
            "scenario": verdict,
            "topic": topic,
            "model": "presentation-demo",
            "provider": "offline-demo",
            "gemini_used": False,
            "external_api_used": False,
            "url_fetched": False,
            "sources_simulated": True,
        },
    }


def analyze(content: str, language: str = "fr", input_type: str = "text") -> dict[str, Any]:
    text = (content or "").strip()
    if input_type == "url" or re.match(r"^https?://", text, re.I):
        verdict, note, topic = _url_case(text)
        return _result(
            text, verdict, topic,
            "Parcours de vérification simulé hors ligne.",
            "L'URL n'est jamais téléchargée. Les sources sont choisies selon le domaine thématique afin de représenter une vérification cohérente.",
            "Une vérification réelle nécessiterait l'accès au contenu de la page." if verdict == "non_verifiable" else None,
            url_mode=True, note=note,
        )

    t = _norm(text)
    topic = detect_topic(t)

    if _has(t, "deux lunes", "2 lunes", "grande muraille", "visible depuis la lune", "napoléon était le président", "napoleon etait le president", "napoléon président des états-unis", "napoleon president des etats-unis", "soleil tourne autour de la terre", "téléphone fonctionne sans batterie", "telephone fonctionne sans batterie", "sans batterie ni électricité"):
        if _has(t, "napoléon", "napoleon"):
            explanation = "Napoléon Bonaparte n'a pas été président des États-Unis."
            correction = "Napoléon Bonaparte était un dirigeant français et empereur des Français."
            topic = "histoire"
        elif _has(t, "soleil tourne autour de la terre"):
            explanation = "Le modèle astronomique simulé indique que la Terre orbite autour du Soleil."
            correction = "La Terre tourne autour du Soleil ; sa rotation produit notamment le cycle jour-nuit."
            topic = "science"
        elif _has(t, "grande muraille"):
            explanation = "Le scénario démo classe comme fausse l'idée d'une visibilité claire de la Grande Muraille depuis la Lune à l'œil nu."
            correction = "Cette affirmation est présentée comme un mythe dans la démonstration."
            topic = "geographie"
        else:
            explanation = "Les sources thématiques simulées contredisent directement l'affirmation."
            correction = "Le scénario de démonstration recommande de corriger cette affirmation."
        return _result(text or "Affirmation fausse", "faux", topic, "Cette affirmation est classée comme fausse dans le scénario de démonstration.", explanation, correction)

    if _has(t, "10 % de leur cerveau", "10% de leur cerveau", "le café déshydrate", "le cafe deshydrate", "déshydrate complètement", "deshydrate completement", "vitamines préviennent toujours", "antibiotiques guérissent les virus", "antibiotiques guerissent les virus", "les réseaux sociaux rendent dépressif", "les reseaux sociaux rendent depressif", "eau bout exactement à 100", "eau bout toujours à 100"):
        if _has(t, "antibiotiques", "virus"):
            explanation = "Les antibiotiques ciblent les bactéries et ne traitent pas directement les infections virales ordinaires."
            topic = "sante"
        elif _has(t, "café", "cafe", "déshydrate", "deshydrate"):
            explanation = "L'affirmation contient un élément plausible mais exagère l'effet en utilisant une formulation absolue."
            topic = "sante"
        else:
            explanation = "Une partie de l'affirmation peut être correcte, mais sa formulation est trop générale ou absolue."
            if _has(t, "cerveau"):
                topic = "science"
        return _result(text or "Affirmation nuancée", "partiellement_vrai", topic, "Cette affirmation nécessite une nuance et du contexte.", explanation, "Une formulation plus précise et contextualisée serait préférable.")

    if _has(t, "madagascar", "malgache", "antananarivo", "océan indien", "ocean indien"):
        return _result(text, "vrai", "madagascar", "Cette affirmation est classée comme vraie dans le scénario local.", "Les sources malgaches simulées sont sélectionnées en priorité pour le sujet national.", None)
    if _has(t, "terre tourne autour du soleil", "terre orbite autour du soleil", "eau bout", "100 °c", "100 c", "lune", "mars", "astronomie"):
        return _result(text, "vrai", "science", "Cette affirmation est classée comme vraie dans le scénario scientifique.", "Les sources scientifiques simulées sont utilisées pour la corroboration.", None)
    if _has(t, "everest", "plus haute montagne", "continent", "océan", "ocean"):
        return _result(text, "vrai", "geographie", "Cette affirmation est classée comme vraie dans le scénario géographique.", "Les sources géographiques simulées sont utilisées pour la corroboration.", None)
    if _has(t, "ordinateur", "internet", "cybersécurité", "cybersecurite", "intelligence artificielle", "smartphone"):
        return _result(text, "vrai", "technologie", "Cette affirmation est classée comme vraie dans le scénario technologique.", "Les sources techniques simulées sont utilisées pour la corroboration.", None)

    return _result(
        text or "Affirmation analysée", "partiellement_vrai", topic,
        "Cette affirmation est classée comme nuancée dans le scénario de démonstration.",
        "Le moteur hors ligne choisit une conclusion prudente pour les sujets non préconfigurés et affiche des sources correspondant au thème détecté.",
        "Une vérification réelle nécessiterait des sources correspondant précisément à l'affirmation.",
    )
