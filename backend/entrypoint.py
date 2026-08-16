"""Render entrypoint for Truth Checker.

Loads the production FastAPI application from main.py, removes the root
StaticFiles catch-all, and explicitly guarantees the two analysis POST routes
are registered before installing the GET-only frontend fallback.
"""
from __future__ import annotations

import os
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.routing import Mount

import main as _main

app = _main.app

# Remove the root frontend Mount inherited from main.py. Starlette Mount("/")
# can otherwise turn an unmatched POST /api/... into 405 before the intended
# API handler gets a chance to process it.
app.router.routes[:] = [
    route
    for route in app.router.routes
    if not (
        isinstance(route, Mount)
        and getattr(route, "path", None) == "/"
        and getattr(route, "name", None) == "frontend"
    )
]


def _remove_path(path: str) -> None:
    app.router.routes[:] = [
        route for route in app.router.routes
        if getattr(route, "path", None) != path
    ]


# Re-register the production analysis handlers explicitly. This makes the
# Render entrypoint independent from any route-order manipulation performed by
# demo wrappers and guarantees POST is part of the active route table.
_remove_path("/api/analyze")
_remove_path("/api/analyze/stream")

app.add_api_route(
    "/api/analyze",
    _main.analyze,
    methods=["POST"],
    response_model=_main.AnalyzeResponse,
)
app.add_api_route(
    "/api/analyze/stream",
    _main.analyze_stream,
    methods=["POST"],
)

FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

# Frontend fallback is GET-only and is registered LAST. Therefore it can serve
# the SPA and static assets but cannot ever intercept POST /api/* requests.
if os.path.isdir(FRONTEND_DIR):

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_fallback(path: str = ""):
        root = FRONTEND_DIR
        requested = os.path.abspath(os.path.join(root, path))

        if requested != root and not requested.startswith(root + os.sep):
            raise HTTPException(404, "Not found")

        if path and os.path.isfile(requested):
            return FileResponse(requested)

        index = os.path.join(root, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)

        raise HTTPException(404, "Frontend not found")

print("[TruthChecker] Render entrypoint loaded")
print("[TruthChecker] Explicit POST analysis routes registered")
print("[TruthChecker] Frontend fallback registered as GET-only")
