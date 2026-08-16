"""Presentation wrapper for Truth Checker.

The production app remains in backend/main.py. When TRUTHCHECKER_DEMO=true,
this wrapper replaces only the analysis endpoints with controlled presentation
scenarios. Demo responses are explicitly marked in metadata.
"""
from __future__ import annotations

import os
import time
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
import main as real_main
from app.services import demo_mode

app = real_main.app
DEMO_ENABLED = demo_mode.is_enabled()
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# main.py mounts StaticFiles at "/". When this wrapper replaces routes after
# importing main.py, that Mount can consume POST /api/* and return 405 because
# StaticFiles only handles GET/HEAD. Remove the root Mount completely here and
# replace it with a GET-only fallback after all API routes.
app.router.routes[:] = [
    route
    for route in app.router.routes
    if not (
        getattr(route, "path", None) == "/"
        and route.__class__.__name__ == "Mount"
    )
]


def demo_status():
    return {
        "enabled": DEMO_ENABLED,
        "presentation_mode": DEMO_ENABLED,
        "module": "main_demo",
    }


# Remove production analysis handlers in demo mode so there is exactly one
# handler for each analysis endpoint.
if DEMO_ENABLED:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) not in {
            "/api/analyze",
            "/api/analyze/stream",
        }
    ]


def demo_analyze(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content field empty")
    result = demo_mode.analyze(req.content, req.language)
    result["metadata"] = {
        **result.get("metadata", {}),
        "demo_mode": True,
        "user_id": user["id"],
    }
    return real_main.AnalyzeResponse(**result)


def demo_analyze_stream(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
    if req.type != "image" and not req.content.strip():
        raise HTTPException(400, "content empty")

    def gen():
        steps = [
            "Analyzing content...",
            "Identifying claims...",
            "Searching sources...",
            "Comparing evidence...",
            "Calculating confidence...",
        ]
        for label in steps:
            yield real_main._sse("step", {"label": label})
            time.sleep(0.35)
        result = demo_mode.analyze(req.content, req.language)
        result["metadata"] = {
            **result.get("metadata", {}),
            "demo_mode": True,
            "user_id": user["id"],
        }
        yield real_main._sse("result", result)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-TruthChecker-Demo": "true",
        },
    )


# Register all API routes while no root catch-all exists.
app.add_api_route(
    "/api/demo/status",
    demo_status,
    methods=["GET"],
    include_in_schema=False,
)

if DEMO_ENABLED:
    app.add_api_route(
        "/api/analyze",
        demo_analyze,
        methods=["POST"],
        response_model=real_main.AnalyzeResponse,
    )
    app.add_api_route(
        "/api/analyze/stream",
        demo_analyze_stream,
        methods=["POST"],
    )


# Frontend fallback is deliberately GET-only and is registered LAST. It can
# serve /, /app.js, /styles.css, etc., but can never intercept POST /api/*.
if os.path.isdir(FRONTEND_DIR):
    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_fallback(path: str = ""):
        root = os.path.abspath(FRONTEND_DIR)
        requested = os.path.abspath(os.path.join(root, path))
        if requested != root and not requested.startswith(root + os.sep):
            raise HTTPException(404, "Not found")
        if path and os.path.isfile(requested):
            return FileResponse(requested)
        index = os.path.join(root, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(404, "Frontend not found")

print(f"[TruthChecker] main_demo loaded; TRUTHCHECKER_DEMO={DEMO_ENABLED}")
