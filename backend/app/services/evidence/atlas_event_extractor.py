"""Conservative, deterministic candidate extraction from the approved NRSC Atlas.

This module does NOT verify events, geocode locations, infer missing dates,
label non-events, or calculate model accuracy. It only extracts two explicitly
dated Uttarakhand/Himalaya event descriptions and the raw Uttarakhand aggregate
inventory context from the already-downloaded Phase-2 text cache.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
DOCUMENT_ID = "nrsc_landslide_atlas_2023"
SOURCE_ID = "nrsc_landslide_atlas"
CACHE_DIR = PACKAGE_DIR / ".cache" / "documents"
TEXT_PATH = CACHE_DIR / f"{DOCUMENT_ID}.txt"
METADATA_PATH = CACHE_DIR / f"{DOCUMENT_ID}.json"
OUTPUT_DIR = CACHE_DIR / "extractions"

MAX_INPUT_CHARS = 300_000
MAX_PAGE_COUNT = 120

PAGE_MARKER_RE = re.compile(r"(?m)^--- PAGE (\d+) ---\s*$")

MONTHS = (
    "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    "Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
RAUNTHI_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({MONTHS})\s+(20\d{{2}})\b", re.IGNORECASE
)
KEDARNATH_RANGE_RE = re.compile(
    rf"\b(\d{{1,2}})\s*[-–—]\s*(\d{{1,2}})\s+({MONTHS})\s+(20\d{{2}})\b",
    re.IGNORECASE,
)


@dataclass
class EventCandidate:
    candidate_id: str
    event_name: str
    event_type: str
    event_date_start: str | None
    event_date_end: str | None
    place_name: str | None
    state: str | None
    district: str | None
    pdf_page_number: int
    figure_number: int | None
    source_id: str
    source_document_id: str
    source_document_sha256: str
    evidence_excerpt: str
    extraction_method: str = "deterministic_phrase_and_date_match"
    review_status: str = "needs_human_review"
    verification_status: str = "not_verified"
    may_be_used_for_model_validation: bool = False


def _load_approved_input() -> tuple[str, dict[str, Any]]:
    if not TEXT_PATH.is_file():
        raise FileNotFoundError(
            f"Phase-2 extracted text not found: {TEXT_PATH}. "
            "Run the approved Phase-2 NRSC Atlas document reader first."
        )
    if not METADATA_PATH.is_file():
        raise FileNotFoundError(
            f"Phase-2 document metadata not found: {METADATA_PATH}. "
            "Re-run the Phase-2 document reader to create metadata."
        )

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if metadata.get("document_id") != DOCUMENT_ID:
        raise ValueError("Cached metadata document_id does not match the approved NRSC Atlas.")
    if metadata.get("source_id") != SOURCE_ID:
        raise ValueError("Cached metadata source_id does not match the approved NRSC source.")
    if metadata.get("status") not in {"ok", "cached"}:
        raise ValueError(
            f"Phase-2 document extraction status is not usable: {metadata.get('status')}"
        )
    if not str(metadata.get("url", "")).lower().startswith("https://www.nrsc.gov.in/"):
        raise ValueError("Cached document URL is not the expected HTTPS NRSC URL.")
    if not metadata.get("sha256"):
        raise ValueError("Phase-2 metadata has no source PDF SHA-256 fingerprint.")

    text = TEXT_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Extracted NRSC Atlas text is empty.")
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(f"Extracted text exceeds the {MAX_INPUT_CHARS:,}-character safety limit.")

    return text, metadata


def _split_pages(text: str) -> list[tuple[int, str]]:
    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        raise ValueError("No Phase-2 '--- PAGE N ---' markers found in extracted text.")
    if len(matches) > MAX_PAGE_COUNT:
        raise ValueError(f"Extracted text contains more than {MAX_PAGE_COUNT} page markers.")

    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_number = int(match.group(1))
        page_text = text[start:end].strip()
        if page_text:
            pages.append((page_number, page_text))
    return pages


def _clean_excerpt(value: str, max_chars: int = 1_100) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_chars:
        value = value[: max_chars - 1].rstrip() + "…"
    return value


def _excerpt_around(text: str, phrase: str, radius: int = 480) -> str:
    match = re.search(re.escape(phrase), text, flags=re.IGNORECASE)
    if not match:
        return _clean_excerpt(text)
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return _clean_excerpt(text[start:end])


def _figure_number(page_text: str) -> int | None:
    match = re.search(r"\bFigure\s+(\d+)\s*\.", page_text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _event_date(day: str, month: str, year: str) -> str:
    parsed = datetime.strptime(f"{day} {month[:3].title()} {year}", "%d %b %Y")
    return parsed.date().isoformat()


def _extract_candidates(pages: list[tuple[int, str]], pdf_sha256: str) -> list[EventCandidate]:
    candidates: list[EventCandidate] = []

    for page_number, page_text in pages:
        lower = page_text.casefold()

        # NRSC Figure 4/5 narrative explicitly describes Raunthi Gad rock fall
        # and debris flow, with the event date 7 Feb 2021. Do not infer a district.
        if "raunthi gad" in lower and "landslide" in lower:
            date_match = RAUNTHI_DATE_RE.search(page_text)
            if date_match:
                day, month, year = date_match.groups()
                event_date = _event_date(day, month, year)
                candidates.append(
                    EventCandidate(
                        candidate_id="nrsc_atlas_raunthi_gad_2021",
                        event_name="Raunthi Gad landslide",
                        event_type="rock_fall_and_debris_flow_as_described_by_source",
                        event_date_start=event_date,
                        event_date_end=event_date,
                        place_name="Raunthi Gad",
                        state=None,
                        district=None,
                        pdf_page_number=page_number,
                        figure_number=_figure_number(page_text),
                        source_id=SOURCE_ID,
                        source_document_id=DOCUMENT_ID,
                        source_document_sha256=pdf_sha256,
                        evidence_excerpt=_excerpt_around(page_text, "Raunthi Gad"),
                    )
                )

        # NRSC Figure 6 explicitly places the event around Kedarnath in
        # Uttarakhand and dates the event to 16-17 June 2013.
        if "kedarnath" in lower and "uttarakhand" in lower and "landslide" in lower:
            date_match = KEDARNATH_RANGE_RE.search(page_text)
            if date_match:
                day_start, day_end, month, year = date_match.groups()
                candidates.append(
                    EventCandidate(
                        candidate_id="nrsc_atlas_kedarnath_2013",
                        event_name="Kedarnath landslide and related flood disaster",
                        event_type="reactivated_landslide_with_related_flash_flood_as_described_by_source",
                        event_date_start=_event_date(day_start, month, year),
                        event_date_end=_event_date(day_end, month, year),
                        place_name="Kedarnath valley / town",
                        state="Uttarakhand",
                        district=None,
                        pdf_page_number=page_number,
                        figure_number=_figure_number(page_text),
                        source_id=SOURCE_ID,
                        source_document_id=DOCUMENT_ID,
                        source_document_sha256=pdf_sha256,
                        evidence_excerpt=_excerpt_around(page_text, "Kedarnath"),
                    )
                )

    # Avoid accidental duplicates if the same figure text occurs twice in extraction.
    unique: dict[str, EventCandidate] = {}
    for candidate in candidates:
        unique[candidate.candidate_id] = candidate
    return list(unique.values())


def _extract_inventory_context(pages: list[tuple[int, str]], pdf_sha256: str) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for page_number, page_text in pages:
        lower = page_text.casefold()
        if "uttarakhand" not in lower:
            continue
        if "table 2" not in lower and "landslides inventory database of india" not in lower:
            continue
        contexts.append(
            {
                "context_id": "nrsc_atlas_uttarakhand_inventory_table_2",
                "context_type": "state_level_aggregate_inventory_summary",
                "state": "Uttarakhand",
                "pdf_page_number": page_number,
                "source_id": SOURCE_ID,
                "source_document_id": DOCUMENT_ID,
                "source_document_sha256": pdf_sha256,
                "raw_excerpt": _excerpt_around(page_text, "Uttarakhand", radius=1_000),
                "numeric_fields_parsed": False,
                "individual_events_created": False,
                "review_status": "manual_table_review_required",
                "note": (
                    "This is an aggregate state-level table row, not a list of individual events. "
                    "Do not expand its counts into event records or use it as event-level labels."
                ),
            }
        )
    return contexts


def extract_nrsc_atlas_candidates(*, write_outputs: bool = True) -> dict[str, Any]:
    """Create review-only candidate references from the locally cached NRSC Atlas text."""
    text, metadata = _load_approved_input()
    pages = _split_pages(text)
    candidates = _extract_candidates(pages, str(metadata["sha256"]))
    inventory_contexts = _extract_inventory_context(pages, str(metadata["sha256"]))

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": SOURCE_ID,
        "source_document_id": DOCUMENT_ID,
        "source_title": metadata.get("title"),
        "source_url": metadata.get("url"),
        "source_document_sha256": metadata.get("sha256"),
        "coverage_period_description": metadata.get("coverage_period"),
        "extraction_method": "deterministic_phrase_and_date_match; no OCR or AI inference",
        "pdf_pages_available": metadata.get("pages_total"),
        "pdf_pages_processed_by_phase2": metadata.get("pages_processed"),
        "text_pages_parsed": len(pages),
        "candidate_reference_count": len(candidates),
        "aggregate_context_count": len(inventory_contexts),
        "candidates": [asdict(item) for item in candidates],
        "aggregate_contexts": inventory_contexts,
        "verification": {
            "status": "not_performed",
            "independent_corroboration": "not_performed",
            "model_accuracy": "not_evaluated",
            "eligible_for_training_or_model_validation": False,
        },
        "limitations": [
            "Extracted entries are source references requiring human review, not verified ground-truth event labels.",
            "No district is inferred when the source excerpt does not explicitly name one.",
            "The aggregate Uttarakhand inventory table is retained as context and is not expanded into individual events.",
            "The NRSC Atlas is historical (1998-2022 coverage as described by NRSC), not a live warning feed.",
            "The extractor only recognises a small set of explicitly described event phrases; zero results would not mean zero historical landslides.",
        ],
    }

    json_path = OUTPUT_DIR / f"{DOCUMENT_ID}_candidate_references.json"
    csv_path = OUTPUT_DIR / f"{DOCUMENT_ID}_candidate_references.csv"

    fieldnames = [
        "candidate_id",
        "event_name",
        "event_type",
        "event_date_start",
        "event_date_end",
        "place_name",
        "state",
        "district",
        "pdf_page_number",
        "figure_number",
        "source_id",
        "source_document_id",
        "source_document_sha256",
        "extraction_method",
        "review_status",
        "verification_status",
        "may_be_used_for_model_validation",
        "evidence_excerpt",
    ]
    if write_outputs:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for item in candidates:
                writer.writerow(asdict(item))

    result["output_json_path"] = str(json_path) if write_outputs else None
    result["output_csv_path"] = str(csv_path) if write_outputs else None
    return result
