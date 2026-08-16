"""Presentation wrapper for Truth Checker.

Start with `uvicorn main_demo:app ...` and set TRUTHCHECKER_DEMO=true to use
controlled presentation results. With the variable false, the normal application
routes remain active. The demo responses are explicitly marked demo_mode=True
in metadata so they cannot be mistaken for real evidence in stored payloads.
"""
from __future__ import annotations

import os
import time
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

import main as real_main
from app.services import demo_mode

app = real_main.app


def _remove_analysis_routes() -> None:
    app.router.routes[:] = [
        route for route in app.router.routes
        if getattr(route, "path", None) not in {"/api/analyze", "/api/analyze/stream"}
    ]


def _demo_enabled() -> bool:
    return demo_mode.is_enabled()


if _demo_enabled():
    _remove_analysis_routes()

    @app.post("/api/analyze", response_model=real_main.AnalyzeResponse)
    def demo_analyze(req: real_main.AnalyzeRequest, user=Depends(real_main.current_user)):
        if req.type != "image" and not req.content.strip():
            raise HTTPException(400, "content field empty")
        result = demo_mode.analyze(req.content, req.language)
        # Keep the authenticated presentation flow, but never call Gemini.
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

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-TruthChecker-Demo": "true"})


@app.get("/api/demo/status")
def demo_status():
    return {"enabled": _demo_enabled(), "presentation_mode": _demo_enabled()}
