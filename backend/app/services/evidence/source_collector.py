"""Bounded, read-only fetcher for the exact URLs in source_registry.

Phase 1 deliberately does not crawl links, submit forms, download PDFs, or
accept arbitrary user-supplied URLs. It only fetches allowlisted HTML landing
pages so source reachability and page metadata can be inspected safely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .source_registry import get_source, is_allowed_https_url


CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 12_000
MAX_REDIRECTS = 3
USER_AGENT = "UttarakhandDisasterIntelligencePlatform/1.0 (official-source-check; read-only)"


class _VisibleTextParser(HTMLParser):
    """Small stdlib HTML parser that ignores scripts, styles and hidden UI code."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.text_parts = []
        self.description: Optional[str] = None
        self._inside_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attributes = {key.lower(): value for key, value in attrs if key}

        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._inside_title = True
        elif tag == "meta":
            name = (attributes.get("name") or "").lower()
            if name == "description" and attributes.get("content"):
                self.description = attributes["content"].strip()[:1000]

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._inside_title:
            self.title_parts.append(value)
        else:
            self.text_parts.append(value)

    def result(self) -> Dict[str, str]:
        return {
            "title": " ".join(self.title_parts).strip()[:500],
            "description": self.description or "",
            "text": " ".join(self.text_parts).strip()[:MAX_TEXT_CHARS],
        }


def _new_session() -> requests.Session:
    retry = Retry(
        total=1,
        connect=1,
        read=0,
        status=1,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        }
    )
    session.mount("https://", adapter)
    return session


def _read_limited_body(response: requests.Response) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise ValueError("Source page exceeds the configured 2 MB size limit.")
        except ValueError as exc:
            if "size limit" in str(exc):
                raise

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=16 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError("Source page exceeded the configured 2 MB size limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def collect_source_page(source_id: str) -> Dict[str, Any]:
    """Fetch one registered official landing page and return a bounded summary."""
    source = get_source(source_id)
    fetched_at = datetime.now(timezone.utc).isoformat()
    current_url = source.url
    session = _new_session()

    base_result: Dict[str, Any] = {
        "source_id": source.source_id,
        "source_name": source.name,
        "authority_tier": source.authority_tier,
        "evidence_role": source.evidence_role,
        "data_scope": source.data_scope,
        "status": "error",
        "http_status": None,
        "content_type": None,
        "requested_url": source.url,
        "final_url": None,
        "title": "",
        "description": "",
        "text_excerpt": "",
        "text_characters": 0,
        "fetched_at": fetched_at,
        "error": None,
        "notes": source.notes,
    }

    try:
        for redirect_number in range(MAX_REDIRECTS + 1):
            if not is_allowed_https_url(current_url, source.allowed_domains):
                raise ValueError("Blocked URL: redirect target is outside the HTTPS source allowlist.")

            response = session.get(
                current_url,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                allow_redirects=False,
                stream=True,
            )

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("Source returned a redirect without a Location header.")
                if redirect_number >= MAX_REDIRECTS:
                    raise ValueError("Source exceeded the maximum redirect count.")
                current_url = urljoin(current_url, location)
                continue

            base_result["http_status"] = response.status_code
            base_result["final_url"] = current_url
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            base_result["content_type"] = content_type or None

            if response.status_code == 429:
                response.close()
                base_result["status"] = "rate_limited"
                base_result["error"] = "Source returned HTTP 429; no repeated request was made."
                return base_result

            response.raise_for_status()

            if content_type in ("application/pdf", "application/octet-stream"):
                response.close()
                base_result["status"] = "document_detected_not_downloaded"
                base_result["error"] = (
                    "A document response was detected. PDF/document extraction is a later phase; "
                    "Phase 1 does not download or parse documents."
                )
                return base_result

            if content_type not in ("text/html", "application/xhtml+xml"):
                response.close()
                base_result["status"] = "unsupported_content_type"
                base_result["error"] = f"Expected HTML, received: {content_type or 'unknown'}"
                return base_result

            body = _read_limited_body(response)
            encoding = response.encoding or "utf-8"
            html = body.decode(encoding, errors="replace")
            parser = _VisibleTextParser()
            parser.feed(html)
            parser.close()
            extracted = parser.result()

            base_result.update(
                {
                    "status": "ok",
                    "title": extracted["title"],
                    "description": extracted["description"],
                    "text_excerpt": extracted["text"],
                    "text_characters": len(extracted["text"]),
                }
            )
            response.close()
            return base_result

        raise ValueError("Source redirect processing ended unexpectedly.")

    except requests.RequestException as exc:
        base_result["status"] = "error"
        base_result["error"] = f"HTTP request failed: {type(exc).__name__}: {exc}"
        return base_result
    except (UnicodeError, ValueError) as exc:
        base_result["status"] = "error"
        base_result["error"] = str(exc)
        return base_result
    finally:
        session.close()


def collect_all_source_pages() -> Dict[str, Any]:
    """Check the curated sources sequentially to avoid burst traffic."""
    results = [collect_source_page(source_id) for source_id in (
        "gsi_bhusanket",
        "gsi_landslide_hazard",
        "nrsc_landslide_atlas",
        "bhuvan_landslide_inventory",
    )]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(results),
        "results": results,
        "scope_notice": (
            "Phase 1 checks only the exact allowlisted public landing pages. "
            "It does not crawl articles, scrape arbitrary links, download PDFs, "
            "or assert that a source contains a confirmed landslide event."
        ),
    }
