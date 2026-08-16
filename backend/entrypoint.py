"""Dedicated Render entrypoint for Truth Checker.

This module builds a clean FastAPI application around the production handlers
from main.py. It deliberately does not use a catch-all frontend route: the
frontend files are exposed through explicit GET routes so they can never
shadow POST /api/* endpoints.
"""
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.responses import FileResponse

import main as _main

# Reuse the production application middleware, models, auth dependencies and
# handler functions, but create a clean router table for Render.
app = FastAPI(title=_main.app.title, version=_main.app.version)

for middleware in _main.app.user_middleware:
    app.user_middleware.append(middleware)
app.middleware_stack = app.build_middleware_stack()

# Import the production routes by re-registering the handler callables that
# the frontend actually needs. API routes are intentionally registered before
# any frontend routes.

@app.get("/api/health")
def health():
    return _main.health()

@app.post("/api/auth/register")
def register(req: _main.RegisterRequest):
    return _main.register(req)

@app.post("/api/auth/login")
def login(req: _main.LoginRequest):
    return _main.login(req)

@app.get("/api/auth/me")
def me(user=_main.Depends(_main.current_user)):
    return _main.me(user)

@app.get("/api/auth/usage")
def usage(user=_main.Depends(_main.current_user)):
    return _main.usage(user)

@app.get("/api/history")
def history(user=_main.Depends(_main.current_user)):
    return _main.history(user)

@app.post("/api/analyze", response_model=_main.AnalyzeResponse)
def analyze(req: _main.AnalyzeRequest, user=_main.Depends(_main.current_user)):
    return _main.analyze(req, user)

@app.post("/api/analyze/stream")
def analyze_stream(req: _main.AnalyzeRequest, user=_main.Depends(_main.current_user)):
    return _main.analyze_stream(req, user)

@app.get("/api/debug/routes", include_in_schema=False)
def debug_routes():
    return [
        {
            "index": i,
            "path": getattr(route, "path", None),
            "methods": sorted(getattr(route, "methods", set()) or []),
            "name": getattr(route, "name", ""),
            "type": route.__class__.__name__,
        }
        for i, route in enumerate(app.router.routes)
        if getattr(route, "path", None)
    ]

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# Explicit GET-only frontend routes. No catch-all route is used.
if os.path.isdir(FRONTEND_DIR):

    @app.get("/", include_in_schema=False)
    async def frontend_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/app.js", include_in_schema=False)
    async def frontend_app_js():
        return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))

    @app.get("/styles.css", include_in_schema=False)
    async def frontend_styles():
        return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"))

    # Common static assets referenced by the current frontend.
    @app.get("/favicon.ico", include_in_schema=False)
    async def frontend_favicon():
        path = os.path.join(FRONTEND_DIR, "favicon.ico")
        return FileResponse(path) if os.path.isfile(path) else FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

print("[TruthChecker] Render entrypoint loaded")
print("[TruthChecker] Clean API router created")
print("[TruthChecker] POST /api/analyze registered")
print("[TruthChecker] POST /api/analyze/stream registered")
print("[TruthChecker] Explicit GET-only frontend routes registered")
