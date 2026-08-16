"""Render entrypoint for Truth Checker."""
from __future__ import annotations

import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.routing import Mount

import main as _main

# Build the Render app from the production FastAPI app, but remove the root
# StaticFiles mount inherited from main.py. That mount is a catch-all and can
# return 405 for unmatched POST requests.
app = _main.app
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


# Remove any existing analysis routes and re-register them at the very start
# of Starlette's route table. This makes their precedence unambiguous.
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

# Move the two analysis routes to absolute first position.
analysis_routes = []
other_routes = []
for route in app.router.routes:
    if getattr(route, "path", None) in {"/api/analyze", "/api/analyze/stream"}:
        analysis_routes.append(route)
    else:
        other_routes.append(route)
app.router.routes[:] = analysis_routes + other_routes


@app.get("/api/debug/routes", include_in_schema=False)
def debug_routes():
    result = []
    for i, route in enumerate(app.router.routes):
        path = getattr(route, "path", None)
        methods = sorted(getattr(route, "methods", set()) or [])
        if path and (path.startswith("/api/") or path == "/"):
            result.append({
                "index": i,
                "path": path,
                "methods": methods,
                "name": getattr(route, "name", ""),
                "type": route.__class__.__name__,
            })
    return result


FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

# GET-only frontend fallback, registered after all API routes.
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
print("[TruthChecker] Explicit POST analysis routes registered first")
print("[TruthChecker] GET-only frontend fallback registered last")
