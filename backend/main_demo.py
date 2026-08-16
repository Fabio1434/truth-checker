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


def _add_api_route_before_frontend(path, endpoint, **kwargs):
    """Register an API route before the catch-all frontend mount.

    main.py mounts StaticFiles at '/' after defining its API routes. Routes
    added here after importing main.py would otherwise be appended after that
    catch-all mount, causing POST /api/* requests to return 405. Insert new
    routes immediately before the frontend Mount instead.
    """
    before = len(app.router.routes)
    app.add_api_route(path, endpoint, **kwargs)
    new_route = app.router.routes.pop()

    frontend_index = None
    for i, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == "/" and route.__class__.__name__ == "Mount":
            frontend_index = i
            break

    if frontend_index is None:
        app.router.routes.append(new_route)
    else:
        app.router.routes.insert(frontend_index, new_route)

    return new_route


# Diagnostic endpoint must also be placed before the frontend catch-all mount.
def demo_status():
    return {
        "enabled": DEMO_ENABLED,
        "presentation_mode": DEMO_ENABLED,
        "module": "main_demo",
    }


_add_api_route_before_frontend(
    "/api/demo/status",
    demo_status,
    methods=["GET"],
    include_in_schema=False,
)

if DEMO_ENABLED:
    # Remove the production analysis handlers. We will add the demo handlers
    # back in the same API section, before the frontend catch-all mount.
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) not in {"/api/analyze", "/api/analyze/stream"}
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

    _add_api_route_before_frontend(
        "/api/analyze",
        demo_analyze,
        methods=["POST"],
        response_model=real_main.AnalyzeResponse,
    )
    _add_api_route_before_frontend(
        "/api/analyze/stream",
        demo_analyze_stream,
        methods=["POST"],
    )

print(f"[TruthChecker] main_demo loaded; TRUTHCHECKER_DEMO={DEMO_ENABLED}")
