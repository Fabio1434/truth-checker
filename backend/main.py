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
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.services.source_analyzer import SourceAnalyzer
from app.services.evidence_engine import EvidenceEngine
from app.services.cache_service import CacheService
from app import auth

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Gemini 3.5 Flash-Lite is the production model for Truth Checker.
# Ignore the obsolete Gemini 2.5 Flash-Lite value if an old Render environment variable remains.
_configured_model = os.getenv("TRUTHCHECKER_MODEL", "").strip()
MODEL = "gemini-3.5-flash-lite" if _configured_model in {"", "gemini-2.5-flash-lite"} else _configured_model
CACHE_TTL = int(os.getenv("TRUTHCHECKER_CACHE_TTL", "900"))
MAX_TEXT_CHARS = int(os.getenv("TRUTHCHECKER_MAX_TEXT_CHARS", "20000"))
APP_VERSION = "2026.08.16.7"
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
Tu dois identifier les affirmations vérifiables, utiliser Google Search et, pour une URL, URL Context, puis trouver plusieurs sources fiables. N'invente jamais une source, une URL ou une citation. Ne choisis jamais de score global : le backend le calcule.
Retourne UNIQUEMENT un JSON avec: claims, sources, key_findings, summary, correction, correction_source_urls, context, contradictions. Chaque source doit avoir title,url,domain,stance,excerpt. Chaque claim doit avoir text, explanation, supporting_source_urls, contradicting_source_urls.'''

def _extract_json(text):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m: text = m.group(1)
    else:
        a,b=text.find("{"),text.rfind("}")
        if a >= 0 and b > a: text=text[a:b+1]
    return json.loads(text)

def _grounding_info(response):
    urls=set(); queries=[]
    try:
        c=(getattr(response,"candidates",None) or [None])[0]
        md=getattr(c,"grounding_metadata",None)
        if md:
            queries.extend(str(x) for x in (getattr(md,"web_search_queries",None) or getattr(md,"webSearchQueries",None) or []) if x)
            chunks=getattr(md,"grounding_chunks",None) or getattr(md,"groundingChunks",None) or []
            for ch in chunks:
                web=getattr(ch,"web",None) if not isinstance(ch,dict) else ch.get("web")
                if web is None: continue
                uri=getattr(web,"uri",None) if not isinstance(web,dict) else web.get("uri")
                if uri and str(uri).startswith(("http://","https://")): urls.add(str(uri).strip().rstrip(".,;)]"))
    except Exception as e: print(f"[grounding] {e}")
    return urls,queries

def _finalize(data,response,started,claim_text):
    analyzer=SourceAnalyzer(); engine=EvidenceEngine(); verified,queries=_grounding_info(response)
    sources=[]; seen=set()
    for raw in (data.get("sources") or []):
        if not isinstance(raw,dict): continue
        url=str(raw.get("url","")).strip().rstrip(".,;)]"); title=str(raw.get("title","")).strip()
        if not url or not title or url in seen or not re.match(r"^https?://",url,re.I): continue
        if verified and url not in verified: continue
        stance=str(raw.get("stance","contexte"))
        if stance not in {"confirme","contredit","contexte"}: stance="contexte"
        try:
            s=analyzer.analyze_source(url,title,str(raw.get("excerpt", "")),stance)
            s.relevance=analyzer.calculate_source_relevance(s,claim_text or data.get("key_findings", ""))
            sources.append(Source(title=s.title,url=s.url,domain=s.domain,stance=stance,excerpt=s.excerpt,source_type=s.source_type.value,authority_score=s.authority_score,independence=s.independence,relevance=s.relevance,freshness=s.freshness.value))
            seen.add(url)
        except Exception as e: print(f"[source] {e}")
    support=[s for s in sources if s.stance=="confirme"]; contra=[s for s in sources if s.stance=="contredit"]; context=[s for s in sources if s.stance=="contexte"]
    from app.models.schemas import Source as DomainSource
    score,breakdown=engine.calculate_evidence_score([DomainSource(**s.model_dump()) for s in support],[DomainSource(**s.model_dump()) for s in contra],[DomainSource(**s.model_dump()) for s in context])
    verdict_enum,confidence=engine.determine_verdict(score,len(support),len(contra)); verdict=verdict_enum.value
    correction=data.get("correction"); correction=correction.get("text") if isinstance(correction,dict) else correction
    if correction and not contra: correction=None
    claims=[]
    for item in (data.get("claims") or [])[:8]:
        if isinstance(item,dict) and str(item.get("text","")).strip():
            claims.append({"text":str(item["text"]).strip(),"verdict":verdict,"evidence_score":score,"explanation":str(item.get("explanation",""))[:1000]})
    if not claims and claim_text: claims=[{"text":claim_text[:500],"verdict":verdict,"evidence_score":score,"explanation":str(data.get("key_findings",""))[:500]}]
    return AnalyzeResponse(verdict=verdict,score=score,headline_claim=claim_text[:200] or str(data.get("key_findings",""))[:200] or "Affirmation analysée",summary=str(data.get("summary") or f"Analyse fondée sur {len(sources)} source(s)."),explanation=str(data.get("key_findings") or "Le verdict est calculé à partir des preuves disponibles.")[:1200],correction=str(correction)[:2000] if correction else None,sources=sources,contradictions=contra,claims=claims,context=data.get("context") if isinstance(data.get("context"),dict) else None,queries=queries,confidence_breakdown=ConfidenceBreakdown(source_reliability=breakdown.source_reliability,corroboration=breakdown.corroboration,consensus=breakdown.consensus),searches_performed=len(queries),elapsed_ms=int((time.time()-started)*1000),metadata={"searched_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"source_count":len(sources),"supporting_count":len(support),"contradicting_count":len(contra),"confidence_level":confidence,"model":MODEL,"app_version":APP_VERSION})

def _contents(req):
    lang="Réponds en français." if req.language=="fr" else "Respond in English." if req.language=="en" else "Valio amin'ny teny Malagasy."
    if req.type=="image":
        if not req.image_base64 or not req.image_media_type: raise HTTPException(400,"Image manquante.")
        try: data=base64.b64decode(req.image_base64,validate=True)
        except Exception: raise HTTPException(400,"image_base64 invalide.")
        if len(data)>6*1024*1024: raise HTTPException(413,"Image trop volumineuse (maximum 6 Mo).")
        return [types.Part.from_bytes(data=data,mime_type=req.image_media_type),f"{lang}\nVérifie le message porté par cette image. {req.content[:MAX_TEXT_CHARS]}"]
    if req.type=="url": return f"{lang}\nURL à vérifier: {req.content}\nLis-la avec URL Context puis vérifie ses affirmations avec Google Search et plusieurs sources indépendantes."
    return f'{lang}\nTexte à vérifier:\n\n"{req.content[:MAX_TEXT_CHARS]}"'

def _generate(req):
    tools=[{"google_search":{}}]
    if req.type=="url": tools.insert(0,{"url_context":{}})
    cfg=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,max_output_tokens=2048,tools=tools)
    return client.models.generate_content(model=MODEL,contents=_contents(req),config=cfg)

class RegisterRequest(BaseModel):
    email:str=Field(min_length=5,max_length=254); password:str=Field(min_length=8,max_length=128)
class LoginRequest(BaseModel):
    email:str; password:str

def current_user(request:Request):
    h=request.headers.get("Authorization","")
    if not h.startswith("Bearer "): raise HTTPException(401,"Connexion requise.")
    user=auth.verify_token(h[7:].strip())
    if not user: raise HTTPException(401,"Session invalide ou expirée.")
    return user

@app.get("/api/health")
def health():
    return {"status":"ok","version":APP_VERSION,"model":MODEL,"api_key_configured":bool(GEMINI_API_KEY),"analysis_quota_enforced":False,"max_text_chars":MAX_TEXT_CHARS,"max_output_tokens":2048}

@app.post("/api/auth/register")
def register(req:RegisterRequest):
    email=req.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",email): raise HTTPException(400,"Adresse email invalide.")
    if auth.get_user_by_email(email): raise HTTPException(409,"Un compte existe déjà avec cet email.")
    try: user=auth.create_user(email,req.password)
    except Exception: raise HTTPException(409,"Impossible de créer ce compte.")
    return {"user":{"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"]},"token":auth.make_token(user["id"])}

@app.post("/api/auth/login")
def login(req:LoginRequest):
    user=auth.verify_login(req.email,req.password)
    if not user: raise HTTPException(401,"Email ou mot de passe incorrect.")
    return {"user":{"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"]},"token":auth.make_token(user["id"])}

@app.get("/api/auth/me")
def me(user=Depends(current_user)): return {"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"],"used_today":auth.usage_today(user["id"])}
@app.get("/api/auth/usage")
def usage(user=Depends(current_user)): return {"used_today":auth.usage_today(user["id"]),"daily_limit":int(user["daily_limit"]),"remaining":max(0,int(user["daily_limit"])-auth.usage_today(user["id"]))}
@app.get("/api/history")
def history(user=Depends(current_user)): return {"items":auth.history(user["id"],50)}

@app.post("/api/analyze",response_model=AnalyzeResponse)
def analyze(req:AnalyzeRequest,user=Depends(current_user)):
    if not client: raise HTTPException(500,"GEMINI_API_KEY missing on server")
    if req.type!="image" and not req.content.strip(): raise HTTPException(400,"content field empty")
    started=time.time(); key=req.content if req.type!="image" else (req.content or "image")
    cached=analysis_cache.get(key,req.language)
    if cached:
        cached=dict(cached); cached["metadata"]={**cached.get("metadata",{}),"cache_hit":True,"app_version":APP_VERSION}; return AnalyzeResponse(**cached)
    try:
        response=_generate(req); raw=(getattr(response,"text",None) or "").strip()
    except HTTPException: raise
    except Exception as e:
        msg=str(e); print(f"[Gemini] {msg}")
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg: raise HTTPException(503,"Gemini est temporairement limité. Réessaie dans quelques secondes.",headers={"Retry-After":"10"})
        if "413" in msg or "request_too_large" in msg: raise HTTPException(413,"La requête envoyée à Gemini est trop volumineuse.")
        raise HTTPException(502,f"Gemini API error: {msg}")
    try: data=_extract_json(raw)
    except Exception as e: raise HTTPException(502,f"Gemini response not valid JSON: {e}")
    result=_finalize(data,response,started,req.content); payload=result.model_dump(); payload["metadata"]={**payload.get("metadata",{}),"cache_hit":False}; analysis_cache.set(key,payload,req.language); return AnalyzeResponse(**payload)

@app.post("/api/analyze/stream")
def analyze_stream(req:AnalyzeRequest,user=Depends(current_user)):
    if not client: raise HTTPException(500,"GEMINI_API_KEY missing on server")
    if req.type!="image" and not req.content.strip(): raise HTTPException(400,"content empty")
    def gen():
        try:
            yield _sse("step",{"label":"Analyzing content..."}); response=_generate(req); yield _sse("step",{"label":"Searching sources..."}); _,qs=_grounding_info(response)
            for q in qs: yield _sse("search",{"query":q})
            yield _sse("step",{"label":"Writing verdict..."}); result=_finalize(_extract_json(getattr(response,"text","") or ""),response,time.time(),req.content); d=result.model_dump(); auth.save_analysis(user["id"],req.type,req.content,d); yield _sse("result",d)
        except Exception as e:
            msg=str(e); yield _sse("error",{"message":msg})
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no-cache"})

def _sse(event,data): return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n"

FRONTEND_DIR=os.path.join(os.path.dirname(__file__),"..","frontend")
if os.path.isdir(FRONTEND_DIR): app.mount("/",StaticFiles(directory=FRONTEND_DIR,html=True),name="frontend")
if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app",host="0.0.0.0",port=int(os.getenv("PORT","8000")),reload=True)
