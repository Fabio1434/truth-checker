"""Application package initialization.

Keep production defaults conservative for the Gemini API.  Flash-Lite supports
Google Search grounding, URL Context and structured output while being designed
for high-frequency workloads.

An explicit TRUTHCHECKER_MODEL environment variable still takes precedence.
"""

import os

# Only provide a default here; an explicit Render/local environment variable wins.
os.environ.setdefault("TRUTHCHECKER_MODEL", "gemini-2.5-flash-lite")
