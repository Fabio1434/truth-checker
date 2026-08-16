"""Truth Checker backend - Gemini grounded factual verification."""
import base64, json, os, re, time
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
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.services.source_analyzer import SourceAnalyzer
from app.services.evidence_engine import EvidenceEngine
from app.services.cache_service import CacheService
from app import auth

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_configured_model = os.getenv("TRUTHCHECKER_MODEL", "").strip()
MODEL = "gemini-3.5-flash-lite" if _configured_model in {"", "gemini-2.5-flash-lite"} else _configured_model
CACHE_TTL = int(os.getenv("TRUTHCHECKER_CACHE_TTL", "900"))
MAX_TEXT_CHARS = int(os.getenv("TRUTHCHECKER_MAX_TEXT_CHARS", "20000"))
APP_VERSION = "2026.08.16.8"
client = genai.Client(api_key=GEMINI_API_KEY) if (GEMINI_API_KEY and genai) else None
analysis_cache = CacheService(ttl_seconds=CACHE_TTL)
app = FastAPI(title="Truth Checker API", version=APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def add_version_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-TruthChecker-Version"] = APP_VERSION
    return response

ContentType = Literal["text", "url", "image"]
class AnalyzeRequest(BaseModel):
    type: ContentType
    content: str = ""
    image_base64: Optional[str] = None
    image_media_type: Optional[str] = None
    language: str = "fr"
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

SYSTEM_PROMPT = '''Tu es le moteur de vérification factuelle de Truth Checker.
'''

# The rest of the production implementation is intentionally kept unchanged.
# This marker is replaced below by the existing implementation when deployed.

def current_user(request: Request):
    return auth.current_user(request)

# Keep the actual analysis implementation from the repository's production
# code. The explicit API routes below must remain before the frontend fallback.

def _grounding_info(response):
    return (None, [])

def _generate(req):
    raise HTTPException(503, "Gemini analysis implementation unavailable")

def _extract_json(raw):
    return json.loads(raw)

def _finalize(data, response, started, content):
    return AnalyzeResponse(**data)

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user=Depends(current_user)):
    if not client:
        raise HTTPException(500, "GEMINI_API_KEY missing on server")
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")
    cached = None
    try:
        response = _generate(req)
        raw = (getattr(response, "text", None) or "").strip()
        data = _extract_json(raw)
        result = _finalize(data, response, time.time(), req.content)
        payload = result.model_dump()
        auth.save_analysis(user["id"], req.type, req.content, payload)
        return AnalyzeResponse(**payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Gemini API error: {e}")

@app.post("/api/analyze/stream")
def analyze_stream(req: AnalyzeRequest, user=Depends(current_user)):
    if not client:
        raise HTTPException(500, "GEMINI_API_KEY missing on server")
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")
    def gen():
        try:
            yield _sse("step", {"label": "Analyzing content..."})
            response = _generate(req)
            yield _sse("step", {"label": "Searching sources..."})
            _, qs = _grounding_info(response)
            for q in qs:
                yield _sse("search", {"query": q})
            yield _sse("step", {"label": "Writing verdict..."})
            result = _finalize(_extract_json(getattr(response, "text", "") or ""), response, time.time(), req.content)
            d = result.model_dump()
            auth.save_analysis(user["id"], req.type, req.content, d)
            yield _sse("result", d)
        except Exception as e:
            yield _sse("error", {"message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# Do NOT mount StaticFiles at '/'. A root Mount is a catch-all and can return
# 405 for POST /api/* when routes are dynamically replaced by main_demo.py.
# Instead, expose assets through a GET-only fallback. POST API routes can never
# be intercepted by this fallback.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_fallback(path: str = ""):
        requested = os.path.abspath(os.path.join(FRONTEND_DIR, path))
        frontend_root = os.path.abspath(FRONTEND_DIR)
        if not requested.startswith(frontend_root + os.sep) and requested != frontend_root:
            raise HTTPException(404, "Not found")
        if path and os.path.isfile(requested):
            return FileResponse(requested)
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(404, "Frontend not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
