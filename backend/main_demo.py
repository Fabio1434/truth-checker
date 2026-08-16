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

# Always expose a diagnostic endpoint so deployment can be verified without
# making an analysis request. Register it explicitly rather than relying on a
# decorator after route-list manipulation.
def demo_status():
    return {
        "enabled": DEMO_ENABLED,
        "presentation_mode": DEMO_ENABLED,
        "module": "main_demo",
    }

app.add_api_route("/api/demo/status", demo_status, methods=["GET"], include_in_schema=False)

if DEMO_ENABLED:
    # Remove the production analysis handlers so the existing frontend can keep
    # calling the same POST URLs while the presentation mode is enabled.
    app.router.routes[:] = [
        route for route in app.router.routes
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

print(f"[TruthChecker] main_demo loaded; TRUTHCHECKER_DEMO={DEMO_ENABLED}")
