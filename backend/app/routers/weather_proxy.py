"""
Backend weather proxy/cache for the Disaster Intelligence Platform.

Frontend endpoint:
    GET /api/weather/forecast

main.py mounts this router with:
    prefix="/api/weather"

Requirements:
    pip install httpx
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query


# ============================================================
# ROUTER
# ============================================================

# IMPORTANT:
# main.py already mounts this router with:
#
# app.include_router(
#     weather_proxy.router,
#     prefix="/api/weather",
# )
#
# Therefore there is NO prefix here.
router = APIRouter(tags=["Weather Proxy"])


# ============================================================
# OPEN-METEO
# ============================================================

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


# ============================================================
# CACHE SETTINGS
# ============================================================

# Fresh real weather cache for 5 minutes.
CACHE_TTL_SECONDS = 300

# Previously successful real data can be served for up to
# 30 minutes if Open-Meteo temporarily fails.
#
# IMPORTANT:
# No fake/default weather is ever generated.
STALE_IF_ERROR_SECONDS = 1800

REQUEST_TIMEOUT_SECONDS = 20.0


# ============================================================
# IN-MEMORY CACHE
# ============================================================

# key -> {
#     "saved_at": float,
#     "payload": dict
# }
_cache: dict[str, dict[str, Any]] = {}


# ============================================================
# REQUEST COALESCING
# ============================================================

# If multiple frontend requests for exactly the same coordinates
# arrive together, they share one Open-Meteo request.
_inflight: dict[str, asyncio.Task] = {}


# ============================================================
# COORDINATE CLEANING
# ============================================================

def _clean_csv(value: str) -> str:
    parts = [
        part.strip()
        for part in str(value).split(",")
        if part.strip()
    ]

    if not parts:
        raise ValueError("At least one coordinate is required.")

    numbers: list[str] = []

    for part in parts:
        try:
            number = float(part)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid coordinate: {part}"
            ) from exc

        numbers.append(f"{number:.4f}")

    return ",".join(numbers)


# ============================================================
# CACHE KEY
# ============================================================

def _cache_key(
    latitude: str,
    longitude: str,
    current: str | None,
    hourly: str | None,
    past_days: int,
    forecast_days: int,
    timezone: str,
) -> str:

    return "|".join(
        [
            latitude,
            longitude,
            current or "",
            hourly or "",
            str(past_days),
            str(forecast_days),
            timezone,
        ]
    )


# ============================================================
# OPEN-METEO REQUEST
# ============================================================

async def _fetch_open_meteo(
    params: dict[str, Any],
) -> dict[str, Any] | list[Any]:

    timeout = httpx.Timeout(
        REQUEST_TIMEOUT_SECONDS
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Uttarakhand-Disaster-"
                "Intelligence-Platform/1.0"
            ),
        },
    ) as client:

        response = await client.get(
            OPEN_METEO_URL,
            params=params,
        )

        # ----------------------------------------------------
        # Debug information
        # ----------------------------------------------------

        print(
            "🌦️ Open-Meteo status:",
            response.status_code,
        )

        print(
            "🌦️ Open-Meteo content-type:",
            response.headers.get("content-type"),
        )

        # ----------------------------------------------------
        # Rate limit
        # ----------------------------------------------------

        if response.status_code == 429:

            retry_after = response.headers.get(
                "Retry-After"
            )

            suffix = (
                f" Retry-After={retry_after}s."
                if retry_after
                else ""
            )

            raise RuntimeError(
                "Open-Meteo rate limited (429)."
                + suffix
            )

        # ----------------------------------------------------
        # Other HTTP errors
        # ----------------------------------------------------

        response.raise_for_status()

        # ----------------------------------------------------
        # Parse JSON
        # ----------------------------------------------------

        try:
            payload = response.json()

        except Exception as exc:

            print(
                "❌ Open-Meteo JSON parsing failed:",
                repr(exc),
            )

            print(
                "❌ Open-Meteo response preview:",
                response.text[:2000],
            )

            raise RuntimeError(
                "Open-Meteo returned invalid JSON."
            ) from exc

        # ----------------------------------------------------
        # Debug response type
        # ----------------------------------------------------

        print(
            "🌦️ Open-Meteo response type:",
            type(payload).__name__,
        )

        print(
            "🌦️ Open-Meteo response preview:",
            str(payload)[:2000],
        )

        # ----------------------------------------------------
        # Validate response
        # ----------------------------------------------------

        if not isinstance(payload, (dict, list)):

            raise RuntimeError(
                "Open-Meteo returned an invalid response "
                f"type: {type(payload).__name__}"
            )

        return payload


# ============================================================
# CACHE / FETCH
# ============================================================

async def _get_or_fetch(
    key: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any] | list[Any], str, int]:

    now = time.time()

    # --------------------------------------------------------
    # 1. Fresh cache
    # --------------------------------------------------------

    cached = _cache.get(key)

    if cached:

        age = now - float(
            cached["saved_at"]
        )

        if age <= CACHE_TTL_SECONDS:

            return (
                cached["payload"],
                "cache",
                int(age),
            )

    # --------------------------------------------------------
    # 2. Request coalescing
    # --------------------------------------------------------

    task = _inflight.get(key)

    if task is None:

        task = asyncio.create_task(
            _fetch_open_meteo(params)
        )

        _inflight[key] = task
        owner = True

    else:

        owner = False

    # --------------------------------------------------------
    # 3. Wait for provider
    # --------------------------------------------------------

    try:

        payload = await task

        # Only the request owner writes the cache.
        if owner:

            _cache[key] = {
                "saved_at": time.time(),
                "payload": payload,
            }

        return (
            payload,
            "live",
            0,
        )

    # --------------------------------------------------------
    # 4. Provider failure
    # --------------------------------------------------------

    except Exception:

        if cached:

            age = now - float(
                cached["saved_at"]
            )

            if age <= STALE_IF_ERROR_SECONDS:

                print(
                    "⚠️ Open-Meteo failed; "
                    "serving previous REAL weather cache."
                )

                return (
                    cached["payload"],
                    "stale-cache",
                    int(age),
                )

        raise

    # --------------------------------------------------------
    # 5. Remove completed request
    # --------------------------------------------------------

    finally:

        if owner:
            _inflight.pop(key, None)


# ============================================================
# WEATHER ENDPOINT
# ============================================================

@router.get("/forecast")
async def forecast(
    latitude: str = Query(
        ...,
        description="Comma-separated latitude values",
    ),
    longitude: str = Query(
        ...,
        description="Comma-separated longitude values",
    ),
    current: str | None = Query(None),
    hourly: str | None = Query(None),
    past_days: int = Query(
        1,
        ge=0,
        le=7,
    ),
    forecast_days: int = Query(
        2,
        ge=1,
        le=16,
    ),
    timezone: str = Query(
        "Asia/Kolkata"
    ),
):

    # ========================================================
    # Validate coordinates
    # ========================================================

    try:

        lat = _clean_csv(latitude)
        lon = _clean_csv(longitude)

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=f"Invalid coordinates: {exc}",
        ) from exc

    # ========================================================
    # Latitude / longitude count
    # ========================================================

    if len(lat.split(",")) != len(
        lon.split(",")
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "latitude and longitude must contain "
                "the same number of values."
            ),
        )

    # ========================================================
    # Open-Meteo parameters
    # ========================================================

    params: dict[str, Any] = {

        "latitude": lat,

        "longitude": lon,

        "current": (
            current
            or (
                "temperature_2m,"
                "relative_humidity_2m,"
                "precipitation,"
                "rain,"
                "weather_code,"
                "wind_speed_10m"
            )
        ),

        "hourly": (
            hourly
            or (
                "rain,"
                "precipitation,"
                "precipitation_probability"
            )
        ),

        "past_days": past_days,

        "forecast_days": forecast_days,

        "timezone": timezone,
    }

    # ========================================================
    # Cache key
    # ========================================================

    key = _cache_key(
        lat,
        lon,
        params["current"],
        params["hourly"],
        past_days,
        forecast_days,
        timezone,
    )

    # ========================================================
    # Fetch / cache
    # ========================================================

    try:

        payload, source, age = await _get_or_fetch(
            key,
            params,
        )

    except Exception as exc:

        print(
            "❌ Weather provider error:",
            repr(exc),
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Live weather provider is temporarily "
                f"unavailable: {exc}"
            ),
        ) from exc

    # ========================================================
    # Preserve Open-Meteo response
    # ========================================================

    # Open-Meteo can return either:
    #
    # - dict for one location
    # - list for multiple locations
    #
    # Do not modify the actual weather structure.

    # ========================================================
# Preserve Open-Meteo response
# ========================================================

    # ========================================================
    # Preserve Open-Meteo response
    # ========================================================

    platform_meta = {
        "source": source,
        "cache_age_seconds": age,
        "fetched_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
    }

    # --------------------------------------------------------
    # Single location
    # --------------------------------------------------------

    if isinstance(payload, dict):
        result = dict(payload)

        result["_platform_weather"] = platform_meta

        return result

    # --------------------------------------------------------
    # Multiple locations
    # --------------------------------------------------------
    #
    # Open-Meteo returns a LIST when multiple coordinates
    # are requested.
    #
    # Frontend already expects:
    #
    # Array.isArray(weatherPayload)
    #
    # Therefore return the list directly.
    #

    if isinstance(payload, list):
        return payload

    # --------------------------------------------------------
    # Unexpected response
    # --------------------------------------------------------

    raise HTTPException(
        status_code=502,
        detail="Unexpected weather response format.",
    )