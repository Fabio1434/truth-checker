"""
Truth Checker — Refactored Backend (Phase 2)
===============================================

Truth Checker backend with Gemini grounding and deterministic evidence scoring.
"""

import base64
import json
import os
import re
import time
from typing import Literal, Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("TRUTHCHECKER_MODEL", "gemini-2.5-flash-lite")
MAX_SEARCHES = int(os.environ.get("TRUTHCHECKER_MAX_SEARCHES", "6"))
CACHE_TTL = int(os.environ.get("TRUTHCHECKER_CACHE_TTL", "900"))
MAX_TEXT_CHARS = int(os.environ.get("TRUTHCHECKER_MAX_TEXT_CHARS", "20000"))
APP_VERSION = "2026.08.16.4"

if not GEMINI_API_KEY:
    print("[WARNING] GEMINI_API_KEY is not set.")

client = genai.Client(api_key=GEMINI_API_KEY) if (GEMINI_API_KEY and genai) else None
analysis_cache = CacheService(ttl_seconds=CACHE_TTL)

app = FastAPI(title="Truth Checker API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def version_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-TruthChecker-Version"] = APP_VERSION
    return response


ContentType = Literal["text", "url", "image"]


class AnalyzeRequest(BaseModel):
    type: ContentType
    content: str = Field(default="", description="Raw text, URL, or image caption.")
    image_base64: Optional[str] = None
    image_media_type: Optional[str] = None
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


SYSTEM_PROMPT = """Tu es le moteur de vérification factuelle de Truth Checker.

CRITICAL RULE - SCORE NOT BY LLM:
Tu ne dois PAS choisir un score arbitraire. Le score sera calculé par notre Evidence Engine.
Ton rôle est de trouver des sources réelles, identifier les affirmations et signaler les contradictions.

MÉTHODE:
1. Identifie les affirmations factuelles vérifiables.
2. Utilise Google Search et, si nécessaire, URL Context.
3. Fais au moins 2 recherches avec formulations différentes.
4. Pour chaque source: titre, URL réelle, contenu pertinent et position confirme/contredit/contexte.

RÈGLES:
- N'invente JAMAIS une source, URL ou citation.
- Si tu ne trouves rien, dis-le clairement.
- Ne fournis jamais de score global.

RÉPONSE JSON:
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

La correction doit être strictement fondée sur les sources trouvées.
"""


def _grounding_info(response) -> tuple[set[str], list[str]]:
    verified_urls: set[str] = set()
    queries: list[str] = []
    try:
        candidate = (getattr(response, "candidates", None) or [None])[0]
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata:
            raw_queries = getattr(metadata, "web_search_queries", None) or getattr(metadata, "webSearchQueries", None) or []
            queries.extend(str(q) for q in raw_queries if q)
            chunks = getattr(metadata, "grounding_chunks", None) or getattr(metadata, "groundingChunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web is None and isinstance(chunk, dict):
                    web = chunk.get("web")
                if web is None:
                    continue
                uri = getattr(web, "uri", None) if not isinstance(web, dict) else web.get("uri")
                if uri and str(uri).startswith(("http://", "https://")):
                    verified_urls.add(str(uri).strip().rstrip(".,;)]"))
    except Exception as exc:
        print(f"[WARNING] Could not extract grounding metadata: {exc}")
    return verified_urls, queries


def _count_searches(response) -> int:
    return len(_grounding_info(response)[1])


def _extract_queries(response) -> list[str]:
    return _grounding_info(response)[1]


def _extract_domain(url: str) -> str:
    try:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        return match.group(1) if match else ""
    except Exception:
        return ""


def _build_gemini_contents(req: AnalyzeRequest):
    lang_note = "Réponds en français." if req.language == "fr" else "Respond in English." if req.language == "en" else "Valio amin'ny teny Malagasy."
    if req.type == "image":
        if not req.image_base64 or not req.image_media_type:
            raise HTTPException(400, "image_base64 et image_media_type sont requis pour type=image.")
        try:
            image_data = base64.b64decode(req.image_base64, validate=True)
        except Exception:
            raise HTTPException(400, "image_base64 invalide.")
        if len(image_data) > 6 * 1024 * 1024:
            raise HTTPException(413, "Image trop volumineuse. Veuillez utiliser une image de moins de 6 Mo.")
        instruction = f"{lang_note}\nVoici une image à vérifier."
        if req.content:
            instruction += f"\nContexte fourni : {req.content[:MAX_TEXT_CHARS]}"
        return [types.Part.from_bytes(data=image_data, mime_type=req.image_media_type), instruction]
    if req.type == "url":
        return f"{lang_note}\nVoici une URL d'article à vérifier : {req.content}\nUtilise URL Context puis Google Search pour vérifier les affirmations avec plusieurs sources indépendantes."
    return f'{lang_note}\nVoici un texte / une affirmation à vérifier :\n\n"{req.content[:MAX_TEXT_CHARS]}"'


def _gemini_config(req: AnalyzeRequest):
    tool_list = [{"google_search": {}}]
    if req.type == "url":
        tool_list.insert(0, {"url_context": {}})
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=2048,
        tools=tool_list,
    )


def _gemini_generate(req: AnalyzeRequest):
    contents = _build_gemini_contents(req)
    response = client.models.generate_content(model=MODEL, contents=contents, config=_gemini_config(req))
    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise ValueError("Gemini returned no text")
    return response, raw_text


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


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "model": MODEL,
        "api_key_configured": bool(GEMINI_API_KEY),
        "analysis_quota_enforced": False,
        "max_text_chars": MAX_TEXT_CHARS,
        "max_output_tokens": 2048,
        "architecture": "Evidence Engine + Gemini grounding",
        "cache_ttl_seconds": CACHE_TTL,
        "cache": analysis_cache.stats(),
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user=Depends(current_user)):
    if not client:
        raise HTTPException(500, "GEMINI_API_KEY missing on server")
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content field empty")
    started = time.time()
    cache_claim = req.content if req.type != "image" else (req.content or "image")
    cached = analysis_cache.get(cache_claim, req.language)
    if cached:
        cached["metadata"] = {**(cached.get("metadata") or {}), "cache_hit": True, "app_version": APP_VERSION}
        auth.save_analysis(user["id"], req.type, req.content, cached)
        return AnalyzeResponse(**cached)
    try:
        response, raw_text = _gemini_generate(req)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Gemini error] {e}")
        raise HTTPException(502, f"Gemini API error: {e}")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            first, last = raw_text.find("{"), raw_text.rfind("}")
            if first < 0 or last <= first:
                raise ValueError("No JSON object found")
            data = json.loads(raw_text[first:last + 1])
        except Exception as e:
            raise HTTPException(502, f"Gemini response not valid JSON: {e}")
    try:
        analyzed = _finalize_with_evidence_engine(data, response, started, req.content)
        payload = analyzed.model_dump()
        payload["metadata"] = {**payload.get("metadata", {}), "cache_hit": False, "app_version": APP_VERSION}
        analysis_cache.set(cache_claim, payload, req.language)
        return AnalyzeResponse(**payload)
    except Exception as e:
        raise HTTPException(502, f"Response schema error: {e}")


@app.post("/api/analyze/stream")
def analyze_stream(req: AnalyzeRequest, user=Depends(current_user)):
    if not client:
        raise HTTPException(500, "GEMINI_API_KEY missing on server")
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")
    def gen():
        started = time.time()
        try:
            yield _sse("step", {"label": "Analyzing content..."})
            response, raw_text = _gemini_generate(req)
            _, queries = _grounding_info(response)
            for q in queries:
                yield _sse("search", {"query": q})
            yield _sse("step", {"label": "Writing verdict..."})
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                first, last = raw_text.find("{"), raw_text.rfind("}")
                if first < 0 or last <= first:
                    yield _sse("error", {"message": "Invalid JSON from Gemini"})
                    return
                data = json.loads(raw_text[first:last + 1])
            validated = _finalize_with_evidence_engine(data, response, started, req.content)
            result_dict = validated.model_dump()
            result_dict["metadata"] = {**result_dict.get("metadata", {}), "app_version": APP_VERSION}
            auth.save_analysis(user["id"], req.type, req.content, result_dict)
            yield _sse("result", result_dict)
        except Exception as e:
            print(f"[stream error] {e}")
            yield _sse("error", {"message": f"Gemini API error: {e}"})
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# Keep the existing evidence finalizer used by the project.
# It is defined above this section in the production file.

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
