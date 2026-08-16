"""Presentation wrapper for Truth Checker.

The production app remains in backend/main.py. When TRUTHCHECKER_DEMO=true,
this wrapper replaces only the analysis endpoints with controlled presentation
scenarios. Demo responses are explicitly marked in metadata.
"""
from __future__ import annotations

import time
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
import main as real_main
from app.services import demo_mode

app = real_main.app
DEMO_ENABLED = demo_mode.is_enabled()

# Starlette matches routes in list order. main.py mounts the frontend at "/",
# which is a catch-all Mount. Because this wrapper imports main.py and then adds
# routes, the safest approach is to move ALL catch-all mounts to the end first.
# This avoids relying on the internal Mount class name or on insertion details.

def _move_frontend_mounts_to_end() -> None:
    routes = list(app.router.routes)
    mounts = [
        route for route in routes
        if getattr(route, "path", None) == "/"
        and getattr(route, "name", None) == "frontend"
    ]
    if not mounts:
        return
    non_mounts = [route for route in routes if route not in mounts]
    app.router.routes[:] = non_mounts + mounts


def _add_api_route(path, endpoint, **kwargs):
    """Add an API route and guarantee it stays before the frontend mount."""
    _move_frontend_mounts_to_end()
    app.add_api_route(path, endpoint, **kwargs)
    _move_frontend_mounts_to_end()


# Remove production analysis handlers in demo mode before adding the demo ones.
# The production routes are already before the frontend mount, but removing
# them makes the replacement deterministic and prevents duplicate matches.
if DEMO_ENABLED:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) not in {
            "/api/analyze",
            "/api/analyze/stream",
        }
    ]


def demo_status():
    return {
        "enabled": DEMO_ENABLED,
        "presentation_mode": DEMO_ENABLED,
        "module": "main_demo",
    }


_add_api_route(
    "/api/demo/status",
    demo_status,
    methods=["GET"],
    include_in_schema=False,
)

if DEMO_ENABLED:

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

    _add_api_route(
        "/api/analyze",
        demo_analyze,
        methods=["POST"],
        response_model=real_main.AnalyzeResponse,
    )
    _add_api_route(
        "/api/analyze/stream",
        demo_analyze_stream,
        methods=["POST"],
    )

# Final safety pass: API routes must precede the frontend catch-all.
_move_frontend_mounts_to_end()

print(f"[TruthChecker] main_demo loaded; TRUTHCHECKER_DEMO={DEMO_ENABLED}")
