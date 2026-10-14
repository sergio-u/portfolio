"""Local trafilatura extract-only web provider.

Runs the bundled ``fetch_page.py`` through ``uv run`` (inline-declared dependency, cached
after the first call). Pages are fetched from this machine; no third-party scraping service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_SCRIPT = Path(__file__).with_name("fetch_page.py")
_PER_URL_TIMEOUT_S = 90  # first run resolves the uv environment
_MAX_CONCURRENCY = 4


def _uv() -> str | None:
    return shutil.which("uv") or next(
        (str(p) for p in (Path.home() / ".hermes/bin/uv", Path.home() / ".local/bin/uv") if p.exists()), None)


class TrafilaturaWebProvider(WebSearchProvider):
    @property
    def name(self) -> str:
        return "trafilatura"

    @property
    def display_name(self) -> str:
        return "Trafilatura (local)"

    def is_available(self) -> bool:
        return _SCRIPT.exists() and _uv() is not None

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    async def _one(self, uv: str, url: str, sem: asyncio.Semaphore) -> Dict[str, Any]:
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    uv, "run", "--quiet", "--script", str(_SCRIPT), url,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    out, err = await asyncio.wait_for(proc.communicate(), _PER_URL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return {"url": url, "title": "", "content": "", "raw_content": "",
                            "error": f"trafilatura timed out after {_PER_URL_TIMEOUT_S}s"}
                text = out.decode("utf-8", "replace").strip().splitlines()
                data = json.loads(text[-1]) if text else {}
                if not data:
                    tail = err.decode("utf-8", "replace").strip()[-400:]
                    return {"url": url, "title": "", "content": "", "raw_content": "",
                            "error": f"trafilatura produced no output (exit {proc.returncode}): {tail}"}
            except Exception as exc:  # noqa: BLE001
                return {"url": url, "title": "", "content": "", "raw_content": "", "error": f"{type(exc).__name__}: {exc}"}
        if data.get("error"):
            return {"url": url, "title": "", "content": "", "raw_content": "", "error": data["error"]}
        content = data.get("content", "")
        return {"url": data.get("url", url), "title": data.get("title", ""), "content": content,
                "raw_content": content, "metadata": {"extractor": "trafilatura", **(data.get("metadata") or {})}}

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        uv = _uv()
        if uv is None:
            return [{"url": u, "title": "", "content": "", "raw_content": "", "error": "uv not found"} for u in urls]
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        results = await asyncio.gather(*(self._one(uv, u, sem) for u in urls))
        logger.info("trafilatura extract: %d urls, %d ok", len(urls), sum(1 for r in results if not r.get("error")))
        return list(results)
