"""Trawl browser/proxy fallback client."""

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
    """Fetch a page through Trawl's browser-backed scrape API."""
    service = os.getenv("TRAWL_URL")
    if not service:
        return None

    payload = {
        "url": url,
        "maxTimeout": 60000,
        "skipHttp": True,
    }

    if referer:
        payload["headers"] = {"Referer": referer}

    try:
        response = requests.post(
            f"{service.rstrip('/')}/scrape",
            json=payload,
            timeout=90,
        )
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
            return None

        blocked_markers = (
            "attention required",
            "just a moment",
            "verify you are human",
        )

        if any(marker in html.lower() for marker in blocked_markers):
            logging.warning("Trawl returned Cloudflare/challenge HTML")
            return None

        cookies = {
            item.get("name"): item.get("value")
            for item in data.get("cookies", [])
            if item.get("name") and item.get("value") is not None
        }

        return ScrapedResponse(
            data.get("url") or url,
            html.encode(),
            cookies,
            data.get("userAgent"),
        )

    except Exception as exc:
        logging.warning(
            "Trawl scrape failed: type=%s error=%s url=%s",
            type(exc).__name__,
            exc,
            url,
        )
        return None


def download(
    url: str,
    referer: str | None = None,
    cookies: dict[str, str] | None = None,
    timeout: int = 180,
) -> requests.Response | None:
    """
    Download a resource through Trawl's MITM proxy.

    TRAWL_PROXY should normally be:
        http://127.0.0.1:8192
    """
    proxy = os.getenv("TRAWL_PROXY")
    if not proxy:
        return None

    proxies = {
        "http": proxy,
        "https": proxy,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    if referer:
        headers["Referer"] = referer

    try:
        response = requests.get(
            url,
            headers=headers,
            cookies=cookies or {},
            proxies=proxies,
            timeout=timeout,
            stream=True,
            verify=False,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (response.headers.get("Content-Type") or "").lower()

        logging.info(
            "Trawl download: status=%s type=%s size=%s url=%s",
            response.status_code,
            content_type,
            response.headers.get("Content-Length", "?"),
            response.url,
        )

        return response

    except Exception as exc:
        logging.warning(
            "Trawl download failed: type=%s error=%s url=%s",
            type(exc).__name__,
            exc,
            url,
        )
        return None
