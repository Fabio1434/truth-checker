"""Offline demo entrypoint for Truth Checker.
No external AI/search API is called. Analysis is simulated locally with topic-aware evidence sources.
"""
from __future__ import annotations
import os, time
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
import main as real_main
from app import auth
from app.services import topic_demo_engine

app = FastAPI(title="Truth Checker Demo API", version="offline-demo-2")

@app.post("/api/auth/register")
def register(req: real_main.RegisterRequest):
    email=req.email.strip().lower()
    if not real_main.re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",email): raise HTTPException(400,"Adresse email invalide.")
    if auth.get_user_by_email(email): raise HTTPException(409,"Un compte existe déjà avec cet email.")
    try: user=auth.create_user(email,req.password)
    except Exception: raise HTTPException(409,"Impossible de créer ce compte.")
    return {"user":{"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"]},"token":auth.make_token(user["id"])}

@app.post("/api/auth/login")
def login(req: real_main.LoginRequest):
    user=auth.verify_login(req.email,req.password)
    if not user: raise HTTPException(401,"Email ou mot de passe incorrect.")
    return {"user":{"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"]},"token":auth.make_token(user["id"])}

@app.get("/api/auth/me")
def me(user=Depends(real_main.current_user)): return {"id":user["id"],"email":user["email"],"plan":user["plan"],"daily_limit":user["daily_limit"],"used_today":auth.usage_today(user["id"])}
@app.get("/api/auth/usage")
def usage(user=Depends(real_main.current_user)):
    used=auth.usage_today(user["id"]); limit=int(user["daily_limit"])
    return {"used_today":used,"daily_limit":limit,"remaining":max(0,limit-used)}
@app.get("/api/history")
def history(user=Depends(real_main.current_user)): return {"items":auth.history(user["id"],50)}

def _demo_result(req: real_main.AnalyzeRequest, user: dict):
    if req.type!="image" and not req.content.strip(): raise HTTPException(400,"content field empty")
    result=topic_demo_engine.analyze(req.content,req.language,req.type)
    result["metadata"]={**result.get("metadata",{}),"demo_mode":True,"provider":"offline-demo","gemini_used":False,"external_api_used":False,"user_id":user["id"]}
    return result

@app.post("/api/analyze",response_model=real_main.AnalyzeResponse)
def analyze(req: real_main.AnalyzeRequest,user=Depends(real_main.current_user)): return real_main.AnalyzeResponse(**_demo_result(req,user))

@app.post("/api/analyze/stream")
def analyze_stream(req: real_main.AnalyzeRequest,user=Depends(real_main.current_user)):
    if req.type!="image" and not req.content.strip(): raise HTTPException(400,"content empty")
    def gen():
        first={"text":"Lecture du contenu...","url":"Simulation de lecture du lien...","image":"Simulation de lecture de l'image..."}.get(req.type,"Lecture du contenu...")
        yield real_main._sse("step",{"label":first}); time.sleep(0.25)
        for label in ("Identification des affirmations...","Sélection des sources thématiques...","Comparaison des preuves...","Calcul du niveau de confiance..."):
            yield real_main._sse("step",{"label":label}); time.sleep(0.25)
        yield real_main._sse("result",_demo_result(req,user))
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-TruthChecker-Demo":"true"})

@app.get("/api/health")
def health(): return {"status":"ok","mode":"offline-demo","provider":"offline-demo","gemini_used":False,"external_api_used":False}
@app.get("/api/demo/status")
def demo_status(): return {"enabled":True,"presentation_mode":True,"provider":"offline-demo","gemini_used":False,"external_api_used":False,"topic_aware_sources":True}
@app.get("/api/debug/routes",include_in_schema=False)
def debug_routes(): return {"analysis":[{"path":"/api/analyze","methods":["POST"],"provider":"offline-demo"},{"path":"/api/analyze/stream","methods":["POST"],"provider":"offline-demo"}],"gemini_used":False,"external_api_used":False,"topic_aware_sources":True}

FRONTEND_DIR=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","frontend"))
if os.path.isdir(FRONTEND_DIR):
    @app.get("/",include_in_schema=False)
    async def index(): return FileResponse(os.path.join(FRONTEND_DIR,"index.html"))
    @app.get("/app.js",include_in_schema=False)
    async def app_js(): return FileResponse(os.path.join(FRONTEND_DIR,"app.js"))
    @app.get("/styles.css",include_in_schema=False)
    async def styles(): return FileResponse(os.path.join(FRONTEND_DIR,"styles.css"))
    @app.get("/favicon.ico",include_in_schema=False)
    async def favicon():
        path=os.path.join(FRONTEND_DIR,"favicon.ico")
        return FileResponse(path) if os.path.isfile(path) else FileResponse(os.path.join(FRONTEND_DIR,"index.html"))

print("[TruthChecker] DEMO_MODE=offline-demo")
print("[TruthChecker] GEMINI calls disabled")
print("[TruthChecker] Topic-aware simulated evidence enabled")
print("[TruthChecker] POST /api/analyze -> offline demo")
print("[TruthChecker] POST /api/analyze/stream -> offline demo")
