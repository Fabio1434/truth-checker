"""Presentation wrapper for Truth Checker.

This keeps the normal app and replaces only the two analysis routes when
TRUTHCHECKER_DEMO=true. Demo results are explicitly marked in metadata.
"""
from __future__ import annotations

import time
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
import main as real_main
from app.services import demo_mode

app = real_main.app


def _demo_enabled() -> bool:
    return demo_mode.is_enabled()


if _demo_enabled():
    # Remove the existing handlers before registering the demo handlers.
    app.router.routes[:] = [
        route for route in app.router.routes
        if getattr(route, "path", None) not in {"/api/analyze", "/api/analyze/stream"}
    ]

    @app.post("/api/analyze", response_model=real_main.AnalyzeResponse)
    def demo_analyze(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
        if req.type != "image" and not req.content.strip():
            raise HTTPException(400, "content field empty")
        result = demo_mode.analyze(req.content, req.language)
        result["metadata"] = {**result.get("metadata", {}), "demo_mode": True, "user_id": user["id"]}
        return real_main.AnalyzeResponse(**result)

    @app.post("/api/analyze/stream")
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
            result["metadata"] = {**result.get("metadata", {}), "demo_mode": True, "user_id": user["id"]}
            yield real_main._sse("result", result)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-TruthChecker-Demo": "true"},
        )


@app.get("/api/demo/status")
def demo_status():
    return {"enabled": _demo_enabled(), "presentation_mode": _demo_enabled()}
