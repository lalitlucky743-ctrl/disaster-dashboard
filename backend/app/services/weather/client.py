
"""Shared Open-Meteo client for the disaster intelligence platform.

Features:
- Thread-safe in-memory response cache.
- Identical-request coalescing.
- Shared provider cooldown after HTTP 429.
- Bounded retries for transient 5xx errors only.
- Real stale-cache fallback; never fabricates weather data.
"""

import copy
import json
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

CACHE_TTL_SECONDS = 300
STALE_IF_ERROR_SECONDS = 1800
REQUEST_TIMEOUT = (3, 12)
DEFAULT_RETRY_AFTER_SECONDS = 60

_USER_AGENT = "Uttarakhand-Disaster-Intelligence-Platform/1.0"

_lock = threading.RLock()
_network_slots = threading.BoundedSemaphore(2)
_thread_local = threading.local()

_cache = {}
_inflight = {}
_provider_cooldown_until = 0.0


class OpenMeteoUnavailable(RuntimeError):
    """Raised when real Open-Meteo data cannot be obtained."""


def _request_key(url, params):
    """Build a deterministic key from the complete request."""
    normalized = json.dumps(
        {
            "url": url,
            "params": params,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return normalized


def _get_session():
    """Return one HTTP session per worker thread."""
    session = getattr(_thread_local, "session", None)

    if session is None:
        retry = Retry(
            total=1,
            connect=1,
            read=1,
            status=1,
            backoff_factor=0.3,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=False,
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=4,
            pool_maxsize=4,
        )

        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        })

        _thread_local.session = session

    return session


def _parse_retry_after(value):
    if not value:
        return DEFAULT_RETRY_AFTER_SECONDS

    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        pass

    try:
        retry_time = parsedate_to_datetime(value)

        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=timezone.utc)

        seconds = (
            retry_time - datetime.now(timezone.utc)
        ).total_seconds()

        return max(1.0, seconds)

    except (TypeError, ValueError, OverflowError):
        return DEFAULT_RETRY_AFTER_SECONDS


def _check_cooldown():
    with _lock:
        remaining = _provider_cooldown_until - time.monotonic()

    if remaining > 0:
        raise OpenMeteoUnavailable(
            f"Open-Meteo provider cooldown active; "
            f"retry after approximately {int(remaining)} seconds."
        )


def _fetch_from_provider(url, params):
    global _provider_cooldown_until

    with _network_slots:
        _check_cooldown()

        response = _get_session().get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 429:
            retry_after = _parse_retry_after(
                response.headers.get("Retry-After")
            )

            with _lock:
                _provider_cooldown_until = max(
                    _provider_cooldown_until,
                    time.monotonic() + retry_after,
                )

            raise OpenMeteoUnavailable(
                f"Open-Meteo rate limit reached. "
                f"Retry after approximately {int(retry_after)} seconds."
            )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, (dict, list)):
            raise OpenMeteoUnavailable(
        "Open-Meteo returned an unexpected response format."
    )

        return payload


def _cached_result(entry, source):
    age = max(0, int(time.time() - entry["saved_at"]))

    return copy.deepcopy(entry["payload"]), {
        "source": source,
        "cache_age_seconds": age,
        "fetched_at": entry["fetched_at"],
    }


def fetch_json(
    url,
    params,
    *,
    cache_ttl=CACHE_TTL_SECONDS,
    stale_if_error=STALE_IF_ERROR_SECONDS,
):
    """Fetch real JSON with shared cache and provider protection.

    Returns:
        (payload, metadata)

    metadata.source is one of:
        live, cache, stale-cache
    """

    key = _request_key(url, params)

    while True:
        now = time.time()

        with _lock:
            entry = _cache.get(key)

            if entry:
                age = now - entry["saved_at"]

                if age <= cache_ttl:
                    return _cached_result(entry, "cache")

            event = _inflight.get(key)

            if event is None:
                event = threading.Event()
                _inflight[key] = event
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            if not event.wait(timeout=45):
                raise OpenMeteoUnavailable(
                    "Timed out waiting for an identical weather request."
                )
            continue

        try:
            payload = _fetch_from_provider(url, params)

            entry = {
                "saved_at": time.time(),
                "fetched_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "payload": copy.deepcopy(payload),
            }

            with _lock:
                _cache[key] = entry

            return _cached_result(entry, "live")

        except Exception as exc:
            with _lock:
                stale_entry = _cache.get(key)

            if stale_entry:
                age = time.time() - stale_entry["saved_at"]

                if age <= cache_ttl + stale_if_error:
                    return _cached_result(
                        stale_entry,
                        "stale-cache",
                    )

            raise OpenMeteoUnavailable(
                f"Unable to obtain real Open-Meteo data: {exc}"
            ) from exc

        finally:
            with _lock:
                current_event = _inflight.pop(key, None)

                if current_event is not None:
                    current_event.set()


def get_provider_cooldown_remaining():
    """Return remaining provider cooldown seconds."""
    with _lock:
        return max(
            0,
            int(_provider_cooldown_until - time.monotonic()),
        )
