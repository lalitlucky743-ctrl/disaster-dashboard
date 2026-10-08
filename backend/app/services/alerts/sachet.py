"""
SACHET - Uttarakhand Official Disaster Alerts

Source: SACHET / NDMA, Uttarakhand RSS feed

- No hardcoded/default alerts
- No fake fallback data
- Only data received from SACHET is returned
- Expired alerts are filtered out (when `expires` is parseable)
"""

from __future__ import annotations

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx


logger = logging.getLogger(__name__)

SOURCE_NAME = "SACHET / NDMA"

SACHET_UTTARAKHAND_RSS_URL = (
    "https://sachet.ndma.gov.in/cap_public_website/rss/rss_uttarakhand.xml"
)

# Cache of the last REAL response from SACHET (not fake data)
_cached_xml: bytes | None = None
_cached_etag: str | None = None
_cached_fetched_at: float | None = None   # when we last got a 200
_cached_checked_at: float | None = None   # when server last confirmed (200/304)


# ==========================================================
# HELPERS
# ==========================================================

def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _strip_namespace(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_text(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}

    for child in element.iter():
        if _strip_namespace(child.tag).lower() in wanted:
            if child.text and child.text.strip():
                return child.text.strip()

    return None


def _is_expired(expires: str | None) -> bool:
    """True only if `expires` is clearly in the past.
    If it is missing or cannot be parsed, we do NOT drop the alert."""
    if not expires:
        return False

    try:
        dt = datetime.fromisoformat(expires.strip().replace("Z", "+00:00"))
    except ValueError:
        return False

    if dt.tzinfo is None:
        return False

    return dt < datetime.now(timezone.utc)


def _error(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "source": SOURCE_NAME,
        "source_type": "official",
        "source_url": SACHET_UTTARAKHAND_RSS_URL,
        "alerts": [],
        "message": message,
    }


# ==========================================================
# RSS PARSER
# ==========================================================

def _parse_rss(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)

    # A valid XML that is not a feed must not look like "no alerts"
    if _strip_namespace(root.tag).lower() not in {"rss", "feed", "rdf"}:
        raise ValueError(
            f"Unexpected root element: {_strip_namespace(root.tag)}"
        )

    alerts: list[dict[str, Any]] = []

    items = [
        el for el in root.iter()
        if _strip_namespace(el.tag).lower() in {"item", "entry"}
    ]

    for item in items:
        title = _find_text(item, "title")
        description = _find_text(item, "description", "summary")
        link = _find_text(item, "link")
        guid = _find_text(item, "guid", "identifier", "id")
        pub_date = _find_text(item, "pubDate", "published", "sent")
        event = _find_text(item, "event")

        if not title and not description and not event:
            continue

        expires = _find_text(item, "expires")

        identifier = guid or link
        if not identifier:
            raw = f"sachet|{title}|{pub_date}"
            identifier = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

        alerts.append(
            {
                "source": SOURCE_NAME,
                "source_type": "official",
                "title": title,
                "description": description,
                "event": event,
                "area": _find_text(item, "area", "areaDesc"),
                "severity": _find_text(item, "severity"),
                "urgency": _find_text(item, "urgency"),
                "certainty": _find_text(item, "certainty"),
                "category": _find_text(item, "category"),
                "effective": _find_text(item, "effective"),
                "onset": _find_text(item, "onset"),
                "expires": expires,
                "published": pub_date,
                "link": link,
                "identifier": identifier,
            }
        )

    return alerts


def _build_success(status: str, xml_bytes: bytes) -> dict[str, Any]:
    """Parse XML and drop clearly-expired alerts. May raise."""
    parsed = _parse_rss(xml_bytes)
    active = [a for a in parsed if not _is_expired(a.get("expires"))]

    return {
        "status": status,
        "source": SOURCE_NAME,
        "source_type": "official",
        "source_url": SACHET_UTTARAKHAND_RSS_URL,
        "alerts": active,
        "count": len(active),
        "expired_filtered": len(parsed) - len(active),
        "last_fetched": _iso(_cached_fetched_at),
        "last_checked": _iso(_cached_checked_at),
        "etag": _cached_etag,
    }


# ==========================================================
# FETCH
# ==========================================================

async def fetch_sachet_alerts() -> dict[str, Any]:
    """
    200 -> parse new XML, update cache
    304 -> re-use cached real XML (expired alerts still filtered)
    else -> status "error" with a reason
    """

    global _cached_xml, _cached_etag, _cached_fetched_at, _cached_checked_at

    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "User-Agent": "Disaster-Intelligence-Platform/1.0",
    }

    if _cached_etag and _cached_xml:
        headers["If-None-Match"] = _cached_etag

    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True
        ) as client:
            response = await client.get(
                SACHET_UTTARAKHAND_RSS_URL, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.error("SACHET request failed: %s", exc)
        return _error(f"SACHET feed is currently unavailable: {exc}")

    # ---------------- 304 ----------------
    if response.status_code == 304:
        if not _cached_xml:
            return _error("SACHET returned 304 but no cached feed is available.")

        try:
            result = _build_success("not_modified", _cached_xml)
        except (ET.ParseError, ValueError) as exc:
            logger.error("Cached SACHET XML invalid: %s", exc)
            return _error("Cached SACHET XML is invalid.")

        _cached_checked_at = time.time()
        result["last_checked"] = _iso(_cached_checked_at)
        return result

    # ---------------- non-200 ----------------
    if response.status_code != 200:
        logger.error("SACHET returned HTTP %s", response.status_code)
        return _error(f"SACHET returned HTTP {response.status_code}.")

    # ---------------- 200 ----------------
    xml_bytes = response.content

    if not xml_bytes.strip():
        return _error("SACHET returned an empty feed.")

    # Parse BEFORE touching the cache
    try:
        _parse_rss(xml_bytes)
    except (ET.ParseError, ValueError) as exc:
        logger.error("SACHET XML parsing failed: %s", exc)
        return _error(f"SACHET returned an invalid feed: {exc}")

    now = time.time()
    _cached_xml = xml_bytes
    _cached_fetched_at = now
    _cached_checked_at = now
    _cached_etag = response.headers.get("ETag")  # None if not provided

    return _build_success("updated", xml_bytes)
