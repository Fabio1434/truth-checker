"""Render entrypoint that guarantees API routes are not shadowed by the frontend mount."""
from __future__ import annotations

import os
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.routing import Mount

import main as _main

app = _main.app

# main.py registers the API endpoints correctly, then mounts StaticFiles at '/'.
# Starlette's root Mount can answer unmatched POST requests with 405. Remove
# that catch-all mount in the Render entrypoint and replace it with a GET-only
# frontend fallback. This leaves every /api/* endpoint handled by FastAPI.
app.router.routes[:] = [
    route
    for route in app.router.routes
    if not (
        isinstance(route, Mount)
        and getattr(route, "path", None) == "/"
        and getattr(route, "name", None) == "frontend"
    )
]

FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

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
print("[TruthChecker] API analysis routes protected from frontend catch-all")
