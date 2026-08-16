"""Fully offline presentation entrypoint for Truth Checker."""
from __future__ import annotations

import os
import time
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.services import demo_mode
from app import auth
import main as real_main

app = FastAPI(title="Truth Checker Demo API", version="demo-offline-2")

# Authentication endpoints reuse only the local auth database/token logic.
@app.post("/api/auth/register")
def register(req: real_main.RegisterRequest):
    email = req.email.strip().lower()
    if not real_main.re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Adresse email invalide.")
    if auth.get_user_by_email(email):
        raise HTTPException(409, "Un compte existe déjà avec cet email.")
    try:
        user = auth.create_user(email, req.password)
    except Exception:
        raise HTTPException(409, "Impossible de créer ce compte.")
    return {"user": {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"]}, "token": auth.make_token(user["id"])}

@app.post("/api/auth/login")
def login(req: real_main.LoginRequest):
    user = auth.verify_login(req.email, req.password)
    if not user:
        raise HTTPException(401, "Email ou mot de passe incorrect.")
    return {"user": {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"]}, "token": auth.make_token(user["id"])}

@app.get("/api/auth/me")
def me(user=Depends(real_main.current_user)):
    return {"id": user["id"], "email": user["email"], "plan": user["plan"], "daily_limit": user["daily_limit"], "used_today": auth.usage_today(user["id"])}

@app.get("/api/auth/usage")
def usage(user=Depends(real_main.current_user)):
    used = auth.usage_today(user["id"])
    return {"used_today": used, "daily_limit": int(user["daily_limit"]), "remaining": max(0, int(user["daily_limit"]) - used)}

@app.get("/api/history")
def history(user=Depends(real_main.current_user)):
    return {"items": auth.history(user["id"], 50)}

@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "offline-demo", "gemini_used": False, "model": "offline-demo"}

# The demo is intentionally deterministic and local. The input is used to
# select realistic presentation scenarios without calling any external model.

def _demo_result(req: real_main.AnalyzeRequest, user: dict):
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content field empty")
    result = demo_mode.analyze(req.content, req.language)
    result["metadata"] = {
        **result.get("metadata", {}),
        "demo_mode": True,
        "provider": "offline-demo",
        "gemini_used": False,
        "user_id": user["id"],
    }
    return result

@app.post("/api/analyze", response_model=real_main.AnalyzeResponse)
def analyze(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
    return real_main.AnalyzeResponse(**_demo_result(req, user))

@app.post("/api/analyze/stream")
def analyze_stream(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")

    def gen():
        for label in [
            "Analyzing content...",
            "Identifying claims...",
            "Searching demo evidence...",
            "Comparing evidence...",
            "Calculating confidence...",
        ]:
            yield real_main._sse("step", {"label": label})
            time.sleep(0.25)
        yield real_main._sse("result", _demo_result(req, user))

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-TruthChecker-Demo": "true"})

@app.get("/api/demo/status")
def demo_status():
    return {"enabled": True, "presentation_mode": True, "provider": "offline-demo", "gemini_used": False}

@app.get("/api/debug/routes")
def debug_routes():
    return {"analysis": [{"path": "/api/analyze", "methods": ["POST"], "provider": "offline-demo"}, {"path": "/api/analyze/stream", "methods": ["POST"], "provider": "offline-demo"}], "gemini_used": False}

# Serve the existing frontend using GET only.
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(FRONTEND_DIR):
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{asset:path}", include_in_schema=False)
    async def assets(asset: str):
        requested = os.path.abspath(os.path.join(FRONTEND_DIR, asset))
        if not requested.startswith(FRONTEND_DIR + os.sep):
            raise HTTPException(404, "Not found")
        if os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

print("[TruthChecker] DEMO_MODE=offline-demo")
print("[TruthChecker] GEMINI calls disabled")
print("[TruthChecker] POST /api/analyze -> offline demo")
print("[TruthChecker] POST /api/analyze/stream -> offline demo")
