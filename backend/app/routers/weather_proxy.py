
"""
Shared weather proxy for the Disaster Intelligence Platform.

Endpoint:
    GET /api/weather/forecast

Uses the central shared Open-Meteo client for:
- Cache
- Identical request coalescing
- Provider-wide 429 cooldown
- Bounded retries
- Real stale-cache fallback

Response contract:
- Single coordinate: dictionary with _platform_weather metadata.
- Multiple coordinates: original list response.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..services.weather.client import (
    fetch_json,
    get_provider_cooldown_remaining,
)

router = APIRouter(tags=["Weather Proxy"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _clean_csv(value: str) -> str:
    """Normalize comma-separated coordinates to four decimal places."""
    parts = [
        part.strip()
        for part in str(value).split(",")
        if part.strip()
    ]

    if not parts:
        raise ValueError("At least one coordinate is required.")

    numbers = []

    for part in parts:
        try:
            number = float(part)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid coordinate: {part}"
            ) from exc

        if not -180.0 <= number <= 180.0:
            raise ValueError(
                f"Coordinate out of range: {part}"
            )

        numbers.append(f"{number:.4f}")

    return ",".join(numbers)


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
    past_days: int = Query(1, ge=0, le=7),
    forecast_days: int = Query(2, ge=1, le=16),
    timezone_name: str = Query(
        "Asia/Kolkata",
        alias="timezone",
    ),
):
    # -----------------------------------------
    # Validate and normalize coordinates
    # -----------------------------------------

    try:
        lat = _clean_csv(latitude)
        lon = _clean_csv(longitude)

        if any(
            not -90.0 <= float(value) <= 90.0
            for value in lat.split(",")
        ):
            raise ValueError(
                "Latitude values must be between -90 and 90."
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid coordinates: {exc}",
        ) from exc

    if len(lat.split(",")) != len(lon.split(",")):
        raise HTTPException(
            status_code=400,
            detail=(
                "latitude and longitude must contain "
                "the same number of values."
            ),
        )

    # -----------------------------------------
    # Preserve existing Open-Meteo parameters
    # -----------------------------------------

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "current": current or (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "hourly": hourly or (
            "rain,precipitation,precipitation_probability"
        ),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": timezone_name,
    }

    # -----------------------------------------
    # Fetch through the shared client
    # -----------------------------------------

    try:
        payload, metadata = await asyncio.to_thread(
            fetch_json,
            OPEN_METEO_URL,
            params,
        )

    except Exception as exc:
        print("Shared weather client error:", repr(exc))

        remaining = get_provider_cooldown_remaining()

        headers = (
            {"Retry-After": str(max(1, remaining))}
            if remaining > 0
            else None
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Live weather provider is temporarily unavailable: "
                f"{exc}"
            ),
            headers=headers,
        ) from exc

    # -----------------------------------------
    # Platform metadata
    # -----------------------------------------

    platform_meta = {
        "source": metadata.get("source", "unknown"),
        "cache_age_seconds": metadata.get(
            "cache_age_seconds",
            0,
        ),
        "fetched_at": metadata.get("fetched_at"),
    }

    # -----------------------------------------
    # Preserve existing response contract
    # -----------------------------------------

    if isinstance(payload, dict):
        result = dict(payload)
        result["_platform_weather"] = platform_meta
        return result

    if isinstance(payload, list):
        return payload

    raise HTTPException(
        status_code=502,
        detail="Unexpected weather response format.",
    )
