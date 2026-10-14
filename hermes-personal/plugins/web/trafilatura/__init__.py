"""Local trafilatura web_extract backend (user plugin)."""
from __future__ import annotations

from .provider import TrafilaturaWebProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(TrafilaturaWebProvider())
