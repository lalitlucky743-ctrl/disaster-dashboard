from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.services.alerts.normalizer import (
    is_uttarakhand_district,
    normalize_alert,
)


IMD_DISTRICT_WARNING_URL = "https://api.imd.gov.in/api/v1/districtwarning"


# NOTE: Verify against IMD API documentation / a real response.
WARNING_CODES = {
    "2": "Heavy Rain",
    "3": "Heavy Snow",
    "4": "Thunderstorm & Lightning / Squall",
    "5": "Hailstorm",
    "6": "Dust Storm",
    "7": "Dust Raising Winds",
    "8": "Strong Surface Winds",
    "9": "Heat Wave",
    "10": "Hot Day",
    "11": "Warm Night",
    "12": "Cold Wave",
    "13": "Cold Day",
    "14": "Ground Frost",
    "15": "Fog",
    "16": "Very Heavy Rain",
    "17": "Extremely Heavy Rain",
}


# IMD colour codes: 1=Green, 2=Yellow, 3=Orange, 4=Red
# Verify against a real API response before relying on this.
COLOR_SEVERITY = {
    "1": "Red",
    "2": "Orange",
    "3": "Yellow",
    "4": "Green",
}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _extract_records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("data", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    # Unknown shape: do NOT pretend it is "no alerts"
    raise ValueError(
        f"Unexpected IMD payload format: {type(payload).__name__}"
    )


def _warning_text(value: Any) -> list[str]:
    if value is None:
        return []

    text = str(value).strip()
    if not text:
        return []

    warnings = []
    for code in (c.strip() for c in text.split(",")):
        if not code or code == "1":  # 1 = no warning
            continue
        warning = WARNING_CODES.get(code)
        if warning:
            warnings.append(warning)

    return warnings


def _severity_from_color(color: Any) -> str:
    return COLOR_SEVERITY.get(str(color or "").strip(), "Unknown")


def _forecast_date(issue_date: str, day: int) -> str | None:
    """Return forecast date (ISO) only if issue date can be parsed."""
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(issue_date.strip(), fmt)
            return (parsed + timedelta(days=day - 1)).date().isoformat()
        except ValueError:
            continue
    return None


def _make_id(district: str, date_value: str, day: int, warning: str) -> str:
    raw = f"imd|{district}|{date_value}|day-{day}|{warning}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _get_first(record: dict, *keys: str) -> Any:
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return None


async def fetch_imd_district_warnings() -> list[dict]:
    """
    Fetch real district-wise warnings from IMD.

    No fallback data is returned. If IMD is unavailable or its format
    is not what we expect, an exception is raised so the router can
    report the source as "error" instead of a fake "ok".
    """

    async with httpx.AsyncClient(
        timeout=20.0,
        headers={
            "Accept": "application/json",
            "User-Agent": "Disaster-Intelligence-Platform/1.0",
        },
    ) as client:
        response = await client.get(IMD_DISTRICT_WARNING_URL)
        response.raise_for_status()
        payload = response.json()

    records = _extract_records(payload)

    if not records:
        raise ValueError("IMD returned zero district records")

    alerts: list[dict] = []
    uttarakhand_records = 0
    day_fields_seen = 0

    for record in records:
        district = _get_first(record, "District", "district")

        if not is_uttarakhand_district(district):
            continue

        uttarakhand_records += 1
        district = str(district).strip()

        issue_date = str(
            _get_first(record, "Date", "date", "UTC") or ""
        ).strip()

        for day in range(1, 6):
            warning_value = _get_first(
                record, f"Day_{day}", f"Day{day}_warning"
            )

            if warning_value is None:
                continue  # field absent for this day

            day_fields_seen += 1

            warnings = _warning_text(warning_value)
            if not warnings:
                continue

            color = _get_first(
                record, f"Day{day}_Color", f"Day{day}_color"
            )
            severity = _severity_from_color(color)

            forecast_date = (
                _forecast_date(issue_date, day) if issue_date else None
            )
            date_part = (
                f"Forecast date {forecast_date} (day {day})."
                if forecast_date
                else f"Forecast day {day}."
            )

            for warning in warnings:
                alerts.append(
                    normalize_alert(
                        alert_id=_make_id(
                            district, issue_date, day, warning
                        ),
                        title=warning,
                        description=(
                            f"IMD district warning for {district}. "
                            f"{date_part}"
                        ),
                        alert_type="IMD District Warning",
                        severity=severity,
                        district=district,
                        source="India Meteorological Department",
                        issued_at=issue_date or None,
                        valid_until=None,
                        official_url="https://mausam.imd.gov.in/",
                    )
                )

    if uttarakhand_records == 0:
        raise ValueError(
            "IMD data received but no Uttarakhand district matched "
            "(API format or district names may have changed)"
        )

    if day_fields_seen == 0:
        raise ValueError(
            "IMD Uttarakhand records found but no Day_N warning fields "
            "(API format may have changed)"
        )

    return alerts