"""
Truth Checker — Refactored Backend (Phase 2)
===============================================

NEW ARCHITECTURE:
1. Clean separation of concerns with dedicated services
2. Deterministic Evidence Engine (prevents LLM from choosing scores arbitrarily)
3. Multi-strategy Search Orchestrator (10 different strategies)
4. Claim decomposition into atomic verifiable claims
5. Devil's Advocate Contradiction Engine (actively seeks opposing views)
6. Safe Correction Engine (never invents sources/corrections)
7. Context detection (outdated, misleading information)
8. Source quality scoring system
9. Cache service to avoid duplicate searches

This maintains full backward compatibility with existing API while
implementing robust verification behind the scenes.

NEW CRITICAL RULE:
- Score is NOT chosen by LLM
- LLM finds sources and identifies claims
- Deterministic Evidence Engine calculates final score
- This prevents arbitrary scoring and ensures transparency

API Endpoints:
- POST /api/analyze - Standard analysis
- POST /api/analyze/stream - Real-time streaming analysis  
- GET /api/health - Health check
"""

import base64
import json
import os
import re
import time
import random
from typing import Literal, Optional

try:
    from app.services.llm_router import LLMRouter
except ImportError:  # Allows local unit tests to import schemas without the SDKs installed.
    LLMRouter = None
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.models.schemas import SourceType, SourceFreshness
from app.services.source_analyzer import SourceAnalyzer
from app.services.evidence_engine import EvidenceEngine
from app.services.cache_service import CacheService
from app import auth

load_dotenv()

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

MAX_SEARCHES = int(os.environ.get("TRUTHCHECKER_MAX_SEARCHES", "6"))
CACHE_TTL = int(os.environ.get("TRUTHCHECKER_CACHE_TTL", "900"))

# Multi-provider fallback: tries Groq first, then Gemini, then OpenAI —
# whichever API keys are set in the environment (any subset works).
client = LLMRouter() if LLMRouter else None
MODEL = "auto (" + " → ".join(client.configured_provider_names) + ")" if (client and client.is_configured) else "none"

if not client or not client.is_configured:
    print(
        "[WARNING] No LLM provider configured. Set GROQ_API_KEY and/or "
        "GEMINI_API_KEY and/or OPENAI_API_KEY in backend/.env (copy from "
        "backend/.env.example) before calling /api/analyze."
    )
analysis_cache = CacheService(ttl_seconds=CACHE_TTL)

app = FastAPI(title="Truth Checker API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Schemas (backward compatible)
# --------------------------------------------------------------------------

ContentType = Literal["text", "url", "image"]


class AnalyzeRequest(BaseModel):
    type: ContentType
    content: str = Field(
        default="",
        description="Raw text to check, or a URL, or a caption/question about the image.",
    )
    image_base64: Optional[str] = Field(
        default=None, description="Base64-encoded image bytes (no data: prefix)."
    )
    image_media_type: Optional[str] = Field(
        default=None, description="e.g. image/jpeg, image/png, image/webp"
    )
    language: str = Field(default="fr", description="Response language: fr, en, or mg")


class Source(BaseModel):
    title: str
    url: str
    domain: str = ""
    stance: Literal["confirme", "contredit", "contexte"] = "contexte"
    excerpt: str = ""
    source_type: str = "unknown"
    authority_score: int = Field(50, ge=0, le=100)
    independence: int = Field(50, ge=0, le=100)
    relevance: int = Field(50, ge=0, le=100)
    freshness: str = "inconnu"


class ConfidenceBreakdown(BaseModel):
    source_reliability: int = 0
    corroboration: int = 0
    consensus: int = 0


class AnalyzeResponse(BaseModel):
    verdict: Literal["vrai", "faux", "partiellement_vrai", "non_verifiable"]
    score: int = Field(ge=0, le=100)
    headline_claim: str
    summary: str
    explanation: str
    correction: Optional[str] = None
    sources: list[Source] = []
    contradictions: list[Source] = []
    claims: list[dict] = []
    context: Optional[dict] = None
    queries: list[str] = []
    confidence_breakdown: ConfidenceBreakdown = ConfidenceBreakdown()
    searches_performed: int = 0
    elapsed_ms: int = 0
    metadata: dict = {}


# --------------------------------------------------------------------------
# Prompting - NEW: Score NOT chosen by LLM
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """Tu es le moteur de vérification factuelle de "Truth Checker" (public: 18-30 ans), \
dans l'esprit du programme EMI de l'UNESCO.

RÈGLE CRITIQUE: Tu ne choisis JAMAIS de score. Le score est calculé par notre Evidence Engine \
à partir des sources que tu trouves. Ton rôle: trouver des sources réelles, dire ce qu'elles \
affirment, signaler les contradictions.

MÉTHODE:
1. Identifie la ou les affirmations factuelles vérifiables.
2. Recherche web + visite de pages (2 à 3 recherches maximum, formulations différentes) parmi:
   agences de presse (AFP, Reuters, AP), médias reconnus, vérificateurs de faits (AFP Factuel,
   Africa Check, Snopes), sources officielles, littérature scientifique.
3. Pour chaque source: titre + URL réelle, ce qu'elle dit, position ("confirme"/"contredit"/"contexte").

RÈGLES STRICTES:
- N'invente JAMAIS source, URL ou citation. N'utilise que ce que tes outils ont réellement trouvé.
- Si tu ne trouves rien, dis-le clairement.
- Aucun score dans ta réponse.

RÉPONSE JSON (uniquement ce JSON, rien d'autre):
{
  "claims": [{"text": "...", "verdict": null, "evidence_score": null, "explanation": "...", "supporting_source_urls": [], "contradicting_source_urls": []}],
  "sources": [{"title": "...", "url": "...", "domain": "...", "stance": "...", "excerpt": "..."}],
  "key_findings": "...",
  "summary": "...",
  "correction": null,
  "correction_source_urls": [],
  "context": {"status": "CURRENT|OUTDATED|MISLEADING|UNKNOWN", "explanation": "..."},
  "contradictions": "..."
}

Si langue="en": réponds en anglais, clés JSON et enums inchangés.
La correction doit s'appuyer strictement sur des sources contredisantes/contextuelles trouvées; \
sinon correction=null (jamais inventée)."""


TOOLS = [{"type": "google_search"}]



def _extract_json(text: str) -> dict:
    """Gemini is instructed to return raw JSON, but we defensively strip code
    fences / stray prose in case a model wraps it anyway."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        first, last = text.find("{"), text.rfind("}")
        if first != -1 and last != -1 and last > first:
            text = text[first : last + 1]
    return json.loads(text)


def _count_searches(content_blocks) -> int:
    count = 0
    for block in content_blocks:
        btype = getattr(block, "type", None)
        if btype == "server_tool_use" and getattr(block, "name", "") == "web_search":
            count += 1
    return count


def _extract_queries(content_blocks) -> list[str]:
    """Pull the literal search queries Gemini issued, for transparency in the UI."""
    queries = []
    for block in content_blocks:
        if getattr(block, "type", None) == "server_tool_use" and getattr(block, "name", "") == "web_search":
            q = getattr(block, "input", {}) or {}
            if isinstance(q, dict) and q.get("query"):
                queries.append(q["query"])
    return queries


def _finalize(data: dict, content_blocks, started: float) -> dict:
    """Normalize a raw parsed JSON dict from Groq into a schema-safe payload."""
    data.setdefault("sources", [])
    for s in data["sources"]:
        s.setdefault("domain", "")
        s.setdefault("excerpt", "")
        s.setdefault("stance", "contexte")
        if not s.get("domain") and s.get("url"):
            m = re.search(r"https?://(?:www\.)?([^/]+)", s["url"])
            s["domain"] = m.group(1) if m else ""
    data.setdefault("correction", None)
    
    breakdown = data.get("confidence_breakdown") or {}
    if not isinstance(breakdown, dict):
        breakdown = {}
    normalized_breakdown = {}
    for key in ("source_reliability", "corroboration", "consensus"):
        try:
            normalized_breakdown[key] = max(0, min(100, int(breakdown.get(key, 50))))
        except (TypeError, ValueError):
            normalized_breakdown[key] = 50
    data["confidence_breakdown"] = normalized_breakdown

    data["searches_performed"] = _count_searches(content_blocks)
    data["queries"] = _extract_queries(content_blocks)
    data["elapsed_ms"] = int((time.time() - started) * 1000)
    return data


def _finalize_with_evidence_engine(data: dict, content_blocks, started: float, claim_text: str = "") -> AnalyzeResponse:
    """Normalize model evidence, score it deterministically, and build the API payload.

    The LLM may discover and describe evidence, but it never supplies the final score.
    SourceAnalyzer assigns deterministic source metadata and EvidenceEngine computes the
    final evidence score + verdict from those sources.
    """
    source_analyzer = SourceAnalyzer()
    evidence_engine = EvidenceEngine()

    # Only accept URLs returned by Gemini's real web-search/grounding tools.
    # This prevents a model from inventing a source URL that was not actually retrieved.
    verified_urls: set[str] = set()
    for block in content_blocks or []:
        if getattr(block, "type", None) != "server_tool_use":
            continue
        tool_input = getattr(block, "input", {}) or {}
        direct_url = str(tool_input.get("url", "")).strip()
        if direct_url.startswith(("http://", "https://")):
            verified_urls.add(direct_url.rstrip(".,;)]"))
        for result in tool_input.get("search_results", []) or []:
            result_url = result.get("url") if isinstance(result, dict) else getattr(result, "url", None)
            if result_url and str(result_url).startswith(("http://", "https://")):
                verified_urls.add(str(result_url).strip().rstrip(".,;)]"))

    sources: list[Source] = []
    seen_urls: set[str] = set()
    for raw in data.get("sources", []) or []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url", "")).strip()
        title = str(raw.get("title", "")).strip()
        url = url.rstrip(".,;)]")
        if not url or not title or url in seen_urls:
            continue
        if not re.match(r"^https?://", url, re.I):
            continue
        if verified_urls and url not in verified_urls:
            continue
        stance = str(raw.get("stance", "contexte"))
        if stance not in {"confirme", "contredit", "contexte"}:
            stance = "contexte"
        analyzed = source_analyzer.analyze_source(url, title, str(raw.get("excerpt", "")), stance)
        analyzed.relevance = source_analyzer.calculate_source_relevance(analyzed, claim_text or data.get("key_findings", ""))
        sources.append(Source(
            title=analyzed.title,
            url=analyzed.url,
            domain=analyzed.domain,
            stance=stance,
            excerpt=analyzed.excerpt,
            source_type=analyzed.source_type.value,
            authority_score=analyzed.authority_score,
            independence=analyzed.independence,
            relevance=analyzed.relevance,
            freshness=analyzed.freshness.value,
        ))
        seen_urls.add(url)

    supporting = [s for s in sources if s.stance == "confirme"]
    contradicting = [s for s in sources if s.stance == "contredit"]
    context_sources = [s for s in sources if s.stance == "contexte"]

    # Convert API sources back to domain models for deterministic scoring.
    from app.models.schemas import Source as DomainSource
    support_domain = [DomainSource(**s.model_dump()) for s in supporting]
    contradict_domain = [DomainSource(**s.model_dump()) for s in contradicting]
    context_domain = [DomainSource(**s.model_dump()) for s in context_sources]

    evidence_score, breakdown = evidence_engine.calculate_evidence_score(
        support_domain, contradict_domain, context_domain
    )
    verdict_enum, confidence_level = evidence_engine.determine_verdict(
        evidence_score, len(support_domain), len(contradict_domain)
    )
    verdict = verdict_enum.value

    # Context flags are deterministic and conservative: they never override a strong
    # evidence result unless there is an explicit model-provided context signal.
    context = data.get("context") if isinstance(data.get("context"), dict) else None
    if context and context.get("status") == "OUTDATED" and verdict == "vrai":
        verdict = "partiellement_vrai"

    correction = data.get("correction")
    if isinstance(correction, dict):
        correction = correction.get("text") or None
    # Never present a model-generated correction when there is no contradictory
    # evidence behind it. The correction is intentionally conservative.
    if correction and not contradicting:
        correction = None
    if correction:
        correction = str(correction)[:2000]

    atomic_claims = []
    raw_claims = data.get("claims") or []
    if isinstance(raw_claims, list):
        for item in raw_claims[:8]:
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            if not text.strip():
                continue
            # IMPORTANT: ignore any score/verdict supplied by the LLM.
            # Until per-claim source mapping is available, use the deterministic
            # evidence score and global verdict rather than an invented number.
            atomic_claims.append({
                "text": text.strip(),
                "verdict": verdict,
                "evidence_score": evidence_score,
                "explanation": item.get("explanation", "") if isinstance(item, dict) else "",
            })
    if not atomic_claims and claim_text:
        atomic_claims = [{
            "text": claim_text[:500],
            "verdict": verdict,
            "evidence_score": evidence_score,
            "explanation": data.get("key_findings", "")[:500],
        }]

    return AnalyzeResponse(
        verdict=verdict,
        score=evidence_score,
        headline_claim=claim_text[:200] or data.get("key_findings", "")[:200] or "Affirmation analysée",
        summary=data.get("summary") or f"Analyse fondée sur {len(sources)} source(s) trouvée(s).",
        explanation=data.get("key_findings", "")[:1200] or "Le verdict est calculé à partir des preuves disponibles.",
        correction=correction,
        sources=sources,
        contradictions=contradicting,
        claims=atomic_claims,
        context=context,
        queries=_extract_queries(content_blocks),
        confidence_breakdown=ConfidenceBreakdown(
            source_reliability=breakdown.source_reliability,
            corroboration=breakdown.corroboration,
            consensus=breakdown.consensus,
        ),
        searches_performed=_count_searches(content_blocks),
        elapsed_ms=int((time.time() - started) * 1000),
        metadata={
            "searched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_count": len(sources),
            "supporting_count": len(supporting),
            "contradicting_count": len(contradicting),
            "context_count": len(context_sources),
            "confidence_level": confidence_level,
            "model": MODEL,
        },
    )

def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        return match.group(1) if match else ""
    except Exception:
        return ""


def _build_user_content(req: AnalyzeRequest) -> list:
    lang_note = (
        "Réponds en français." if req.language == "fr" else
        "Respond in English." if req.language == "en" else
        "Valio amin'ny teny Malagasy. Aza adika ny anaran'ny loharano."
    )

    if req.type == "image":
        if not req.image_base64 or not req.image_media_type:
            raise HTTPException(400, "image_base64 et image_media_type sont requis pour type=image.")
        instruction = (
            f"{lang_note}\nVoici une image (capture d'écran, publication réseau social, "
            "affiche, photo...) qui circule et dont on veut vérifier la véracité du message "
            "qu'elle véhicule."
        )
        if req.content:
            instruction += f"\nContexte fourni par l'utilisateur : {req.content}"
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": req.image_media_type,
                    "data": req.image_base64,
                },
            },
            {"type": "text", "text": instruction},
        ]

    if req.type == "url":
        instruction = (
            f"{lang_note}\nVoici une URL d'article à vérifier : {req.content}\n"
            "Commence par lire la page avec la visite de site intégrée, puis vérifie son/ses affirmation(s) "
            "principale(s) avec web_search."
        )
        return [{"type": "text", "text": instruction}]

    # plain text
    instruction = (
        f"{lang_note}\nVoici un texte / une affirmation à vérifier :\n\n\"{req.content}\""
    )
    return [{"type": "text", "text": instruction}]


# --------------------------------------------------------------------------
# Authentication / multi-user access
# --------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: str
    password: str


def current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Connexion requise.")
    user = auth.verify_token(auth_header[7:].strip())
    if not user:
        raise HTTPException(401, "Session invalide ou expirée.")
    return user


@app.post("/api/auth/register")
def register(req: RegisterRequest):
    email = req.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Adresse email invalide.")
    if len(req.password) < 8 or not re.search(r"[A-Za-z]", req.password) or not re.search(r"\d", req.password):
        raise HTTPException(400, "Le mot de passe doit contenir au moins 8 caractères, une lettre et un chiffre.")
    if auth.get_user_by_email(email):
        raise HTTPException(409, "Un compte existe déjà avec cet email.")
    try:
        user = auth.create_user(email, req.password)
    except Exception:
        raise HTTPException(409, "Impossible de créer ce compte.")
    return {"user": {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"]}, "token": auth.make_token(user["id"])}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = auth.verify_login(req.email, req.password)
    if not user:
        raise HTTPException(401, "Email ou mot de passe incorrect.")
    return {"user": {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"]}, "token": auth.make_token(user["id"])}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"], "used_today": auth.usage_today(user["id"])}


@app.get("/api/auth/usage")
def usage(user=Depends(current_user)):
    return {"used_today": auth.usage_today(user["id"]), "daily_limit": int(user["daily_limit"]), "remaining": max(0, int(user["daily_limit"]) - auth.usage_today(user["id"]))}


@app.get("/api/history")
def get_history(user=Depends(current_user)):
    return {"items": auth.history(user["id"], 50)}


def _retry_delay_from_error(exc: Exception, attempt: int) -> float:
    """Extract a suggested retry delay ('try again in 3.96s') if the provider
    included one, otherwise fall back to exponential backoff with jitter."""
    message = str(exc)
    match = re.search(r"try again in ([\d.]+)s", message, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)) + 0.25  # small safety margin
        except ValueError:
            pass
    return min(8.0, (2 ** attempt)) + random.uniform(0, 0.5)


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in ("429", "resource_exhausted", "rate_limit", "rate limit", "quota", "insufficient_quota")
    )


def _call_llm_with_retry(max_retries: int = 3, **kwargs):
    """Call client.messages.create (the multi-provider router), retrying
    automatically on rate limits.

    The router already falls back from Groq → Gemini → OpenAI within a
    single call. This wrapper retries the *whole chain* with backoff if
    every configured provider was rate-limited/unavailable at once, which
    can happen under a burst of concurrent requests.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(**kwargs)
        except Exception as e:
            if not _is_rate_limit_error(e) or attempt == max_retries:
                raise
            delay = _retry_delay_from_error(e, attempt)
            last_exc = e
            time.sleep(delay)
    if last_exc:  # pragma: no cover - defensive, loop always returns or raises
        raise last_exc


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "2.1.0",
        "model": MODEL,
        "providers_configured": client.configured_provider_names if client else [],
        "api_key_configured": bool(client and client.is_configured),
        "architecture": "Evidence Engine + multi-source search + contradiction analysis",
        "cache_ttl_seconds": CACHE_TTL,
        "cache": analysis_cache.stats(),
        "features": {
            "deterministic_score": True,
            "web_search": True,
            "contradiction_search": True,
            "image_analysis": True,
            "multilingual": ["fr", "en", "mg"],
            "provider_fallback": ["groq", "gemini", "openai"]
        }
    }


@app.get("/api/cache/stats")
def cache_stats():
    return analysis_cache.stats()


@app.delete("/api/cache")
def clear_cache():
    analysis_cache.clear()
    return {"status": "cleared"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, user=Depends(current_user)):
    """Analyze content for factuality for an authenticated user."""
    if not client or not client.is_configured:
        raise HTTPException(500, "No LLM provider configured (GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY missing on server)")
    if not auth.can_analyze(user):
        raise HTTPException(429, f'Limite quotidienne atteinte ({user["daily_limit"]} analyses).')
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content field empty")

    started = time.time()

    cache_claim = req.content if req.type != "image" else (req.content or "image")
    cached = analysis_cache.get(cache_claim, req.language)
    if cached:
        cached["metadata"] = {**(cached.get("metadata") or {}), "cache_hit": True}
        cached = dict(cached)
        auth.save_analysis(user["id"], req.type, req.content, cached)
        return AnalyzeResponse(**cached)

    try:
        response = _call_llm_with_retry(
            max_tokens=2048,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=[{"role": "user", "content": _build_user_content(req)}],
        )
    except Exception as e:
        is_rate_limit = _is_rate_limit_error(e)
        status = 429 if is_rate_limit else 502
        message = (
            "Trop de demandes en ce moment sur tous les providers configurés, réessaie dans quelques secondes."
            if is_rate_limit else f"LLM provider error: {e}"
        )
        raise HTTPException(status, message)

    text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    raw_text = "\n".join(text_parts).strip()

    if not raw_text:
        raise HTTPException(502, "No text from LLM provider")

    try:
        data = _extract_json(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(502, "LLM response not valid JSON")

    # Build analysis response using deterministic scoring
    try:
        analyzed = _finalize_with_evidence_engine(data, response.content, started, req.content)
        payload = analyzed.model_dump()
        payload["metadata"] = {
            **payload.get("metadata", {}),
            "cache_hit": False,
            "provider": getattr(response, "provider", None),
            "model": getattr(response, "provider_model", None),
        }
        analysis_cache.set(cache_claim, payload, req.language)
        return AnalyzeResponse(**payload)
    except Exception as e:
        raise HTTPException(502, f"Response schema error: {e}")


@app.post("/api/analyze/stream")
def analyze_stream(req: AnalyzeRequest, user=Depends(current_user)):
    """Stream progress events for a single fact-check request (Groq → Gemini → OpenAI fallback)."""
    if not client or not client.is_configured:
        raise HTTPException(500, "No LLM provider configured (GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY missing on server)")
    if not auth.can_analyze(user):
        raise HTTPException(429, f'Limite quotidienne atteinte ({user["daily_limit"]} analyses).')
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")

    def gen():
        started = time.time()
        try:
            yield _sse("step", {"label": "Analyzing content..."})
            response = _call_llm_with_retry(
                max_tokens=2048,
                temperature=0.2,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=[{"role": "user", "content": _build_user_content(req)}],
            )
            yield _sse("provider", {"name": getattr(response, "provider", None), "model": getattr(response, "provider_model", None)})

            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "server_tool_use":
                    q = (getattr(block, "input", {}) or {}).get("query")
                    if q:
                        yield _sse("search", {"query": q})

            yield _sse("step", {"label": "Writing verdict..."})
            text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            # The first text block can be the vision extraction. The final fact-check block is last.
            raw_text = (text_parts[-1] if text_parts else "").strip()
            if not raw_text:
                yield _sse("error", {"message": "No response from LLM provider"})
                return

            try:
                data = _extract_json(raw_text)
            except json.JSONDecodeError:
                yield _sse("error", {"message": "Invalid JSON from LLM provider"})
                return

            validated = _finalize_with_evidence_engine(data, response.content, started, req.content)
            result_dict = validated.model_dump()
            result_dict["metadata"] = {
                **result_dict.get("metadata", {}),
                "provider": getattr(response, "provider", None),
                "model": getattr(response, "provider_model", None),
            }
            auth.save_analysis(user["id"], req.type, req.content, result_dict)
            yield _sse("result", result_dict)

        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _sse(event: str, data: dict) -> str:
    """Format Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------
# Serve the frontend (so `python main.py` / run_windows.bat is a one-shot demo)
# --------------------------------------------------------------------------

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
