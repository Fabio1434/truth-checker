"""Application package initialization.

Production defaults are intentionally conservative for Gemini API usage.
Flash-Lite supports Google Search grounding, URL Context and structured output
and is designed for high-frequency workloads.

Set TRUTHCHECKER_USE_LITE=0 if you explicitly want another model through
TRUTHCHECKER_MODEL.
"""

import os

USE_LITE = os.getenv("TRUTHCHECKER_USE_LITE", "1").strip().lower() not in {"0", "false", "no", "off"}

if USE_LITE:
    # This deliberately overrides an old `gemini-2.5-flash` deployment setting
    # so an existing Render environment benefits from the lower-cost/high-volume
    # model without requiring a manual migration first.
    os.environ["TRUTHCHECKER_MODEL"] = "gemini-2.5-flash-lite"
else:
    os.environ.setdefault("TRUTHCHECKER_MODEL", "gemini-2.5-flash")
