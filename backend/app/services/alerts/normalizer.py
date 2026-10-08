from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


# Canonical names of the 13 districts of Uttarakhand
UTTARAKHAND_DISTRICTS = {
    "Almora",
    "Bageshwar",
    "Chamoli",
    "Champawat",
    "Dehradun",
    "Haridwar",
    "Nainital",
    "Pauri Garhwal",
    "Pithoragarh",
    "Rudraprayag",
    "Tehri Garhwal",
    "Udham Singh Nagar",
    "Uttarkashi",
}

# Spelling variants -> canonical name (lowercase keys)
DISTRICT_ALIASES = {
    "hardwar": "Haridwar",
    "pauri": "Pauri Garhwal",
    "garhwal": "Pauri Garhwal",
    "tehri": "Tehri Garhwal",
    "tehri garwal": "Tehri Garhwal",
    "rudra prayag": "Rudraprayag",
    "us nagar": "Udham Singh Nagar",
    "u.s. nagar": "Udham Singh Nagar",
    "udhamsinghnagar": "Udham Singh Nagar",
    "udham singh nagar": "Udham Singh Nagar",
    "uttar kashi": "Uttarkashi",
    "dehra dun": "Dehradun",
    "bageshwar": "Bageshwar",
    "champawat": "Champawat",
}

VALID_SEVERITIES = {"Red", "Orange", "Yellow", "Green"}

_CANONICAL_LOOKUP = {name.lower(): name for name in UTTARAKHAND_DISTRICTS}


def _clean(value: Any) -> Optional[str]:
    """Trim, collapse spaces/hyphens, drop 'district' suffix."""
    if value is None:
        return None

    text = str(value).strip().lower()
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*district$", "", text).strip()

    return text or None


def _canonical_uttarakhand_district(value: Any) -> Optional[str]:
    """Return canonical Uttarakhand district name, or None if not a match."""
    cleaned = _clean(value)

    if not cleaned:
        return None

    if cleaned in _CANONICAL_LOOKUP:
        return _CANONICAL_LOOKUP[cleaned]

    return DISTRICT_ALIASES.get(cleaned)


def normalize_district(value: Any) -> Optional[str]:
    canonical = _canonical_uttarakhand_district(value)

    if canonical:
        return canonical

    # Not an Uttarakhand district: keep the original name, do not invent one
    if value is None:
        return None

    text = str(value).strip()

    return text.title() if text else None


def is_uttarakhand_district(value: Any) -> bool:
    return _canonical_uttarakhand_district(value) is not None


def normalize_severity(value: Any) -> str:
    if value is None:
        return "Unknown"

    text = str(value).strip().title()

    return text if text in VALID_SEVERITIES else "Unknown"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_alert(
    *,
    alert_id: str,
    title: str,
    description: str,
    alert_type: str,
    severity: str,
    district: Optional[str],
    source: str,
    issued_at: Optional[str] = None,
    valid_until: Optional[str] = None,
    official_url: Optional[str] = None,
) -> dict:

    normalized_district = normalize_district(district)

    # State is derived from the district, not hardcoded
    state = (
        "Uttarakhand"
        if is_uttarakhand_district(district)
        else None
    )

    return {
        "id": alert_id,
        "title": title,
        "description": description,
        "type": alert_type,
        "severity": normalize_severity(severity),
        "district": normalized_district,
        "state": state,
        "source": source,
        "issued_at": issued_at,
        "valid_until": valid_until,
        "official_url": official_url,
    }