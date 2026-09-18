"""Optional Trawl client used by Actions jobs that provide the service."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import requests


@dataclass
class ScrapedResponse:
    url: str
    content: bytes
    cookies: dict[str, str]
    user_agent: str | None = None
    status_code: int = 200

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def fetch(url: str, referer: str | None = None) -> ScrapedResponse | None:
    """Return browser-rendered HTML when the optional local service is enabled."""
    service = os.getenv("TRAWL_URL")
    if not service:
        return None
    payload = {"url": url, "maxTimeout": 60000, "skipHttp": True}
    if referer:
        payload["headers"] = {"Referer": referer}
    try:
        response = requests.post(f"{service.rstrip('/')}/scrape", json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        html = data.get("html") or ""

        logging.info(
            "Trawl response: http=%s statusCode=%s tier=%s "
            "sessionCached=%s url=%s html_len=%s cookies=%s",
            response.status_code,
            data.get("statusCode"),
            data.get("tier"),
            data.get("sessionCached"),
            data.get("url") or url,
            len(html),
            len(data.get("cookies") or []),
        )

        if data.get("statusCode") != 200 or not html:
            logging.warning(
                "Trawl returned unusable response: statusCode=%s html_len=%s",
                data.get("statusCode"),
                len(html),
            )
            return None

        blocked_markers = ("attention required", "just a moment", "verify you are human")
        found_markers = [
            marker for marker in blocked_markers
            if marker in html.lower()
        ]

        if found_markers:
            logging.warning(
                "Trawl HTML still contains Cloudflare markers: %s",
                found_markers,
            )
            return None
        cookies = {
            item.get("name"): item.get("value")
            for item in data.get("cookies", [])
            if item.get("name") and item.get("value") is not None
        }
        return ScrapedResponse(url, html.encode(), cookies, data.get("userAgent"))
    except Exception as exc:
        logging.warning(
            "Trawl request failed: type=%s error=%s url=%s",
            type(exc).__name__,
            exc,
            url,
        )
        return None
