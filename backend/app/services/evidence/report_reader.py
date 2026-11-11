
"""Safe read-only access to the latest official evidence report."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EVIDENCE_DIR = Path(__file__).resolve().parent

REPORT_PATH = (
    EVIDENCE_DIR
    / ".cache"
    / "corroboration"
    / "nrsc_atlas_2023_corroboration.json"
)

SNAPSHOT_PATH = (
    EVIDENCE_DIR
    / "reports"
    / "nrsc_atlas_2023_corroboration.json"
)


def _text(value: Any, limit: int = 2000):
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    return value[:limit]


def _safe_url(value: Any):
    if not isinstance(value, str):
        return None

    parsed = urlparse(value)

    if parsed.scheme != "https" or not parsed.netloc:
        return None

    return value[:1000]


def _safe_string_list(value: Any, limit: int = 10):
    if not isinstance(value, list):
        return []

    return [
        _text(item, 500)
        for item in value[:limit]
        if isinstance(item, str)
    ]


def _safe_matching_signals(value: Any):
    if not isinstance(value, dict):
        return {}

    allowed_fields = (
        "place_match",
        "matched_place_aliases",
        "date_match",
        "matched_date_phrases",
        "district_match",
        "matched_district_phrases",
        "event_context_match",
        "matched_event_phrases",
        "specific_claim_complete",
        "specific_claim_groups",
        "signals_found_anywhere",
        "coherent_core_passage_count",
        "specific_claim_passage_count",
    )

    result = {}

    for field in allowed_fields:
        item = value.get(field)

        if isinstance(item, bool) or isinstance(item, (int, float)):
            result[field] = item
        elif isinstance(item, list):
            if field == "specific_claim_groups":
                groups = []

                for group in item[:20]:
                    if not isinstance(group, dict):
                        continue

                    groups.append({
                        "required_any_of": _safe_string_list(
                            group.get("required_any_of")
                        ),
                        "matched": bool(group.get("matched", False)),
                        "matched_phrases": _safe_string_list(
                            group.get("matched_phrases")
                        ),
                    })

                result[field] = groups
            else:
                result[field] = _safe_string_list(item)
        elif isinstance(item, dict) and field == "signals_found_anywhere":
            result[field] = {
                key: bool(item.get(key))
                for key in (
                    "place_match",
                    "date_match",
                    "district_match",
                    "event_context_match",
                )
            }

    return result


def _safe_source(source: Any):
    if not isinstance(source, dict):
        return None

    return {
        "source_id": _text(source.get("source_id"), 150),
        "source_name": _text(source.get("source_name"), 300),
        "publisher": _text(source.get("publisher"), 300),
        "publication_date": _text(source.get("publication_date"), 50),
        "url": _safe_url(source.get("url")),
        "kind": _text(source.get("kind"), 20),
        "status": _text(source.get("status"), 50),
        "evidence_role": _text(source.get("evidence_role"), 50),
        "title": _text(source.get("title"), 300),
        "pages_total": source.get("pages_total"),
        "pages_processed": source.get("pages_processed"),
        "fetched_at": _text(source.get("fetched_at"), 80),
    }


def _safe_evidence_record(record: Any):
    if not isinstance(record, dict):
        return None

    excerpts = record.get("evidence_excerpts")
    if not isinstance(excerpts, list):
        excerpts = []

    return {
        "source_id": _text(record.get("source_id"), 150),
        "source_name": _text(record.get("source_name"), 300),
        "publisher": _text(record.get("publisher"), 300),
        "publication_date": _text(record.get("publication_date"), 50),
        "url": _safe_url(record.get("url")),
        "evidence_role": _text(record.get("evidence_role"), 50),
        "match_status": _text(record.get("match_status"), 80),
        "matching_signals": _safe_matching_signals(
            record.get("matching_signals")
        ),
        "evidence_excerpts": [
            _text(item, 2000)
            for item in excerpts[:3]
            if isinstance(item, str)
        ],
    }


def _safe_candidate(candidate: Any):
    if not isinstance(candidate, dict):
        return None

    original = candidate.get("original_candidate")
    if not isinstance(original, dict):
        original = {}

    evidence_records = candidate.get("evidence_records")
    if not isinstance(evidence_records, list):
        evidence_records = []

    return {
        "candidate_id": _text(candidate.get("candidate_id"), 150),
        "event_name": _text(candidate.get("event_name"), 300),
        "event_type": _text(original.get("event_type"), 150),
        "event_date_start": _text(original.get("event_date_start"), 30),
        "event_date_end": _text(original.get("event_date_end"), 30),
        "place_name": _text(original.get("place_name"), 200),
        "state": _text(original.get("state"), 100),
        "district": _text(original.get("district"), 100),
        "source_document_id": _text(
            original.get("source_document_id"), 150
        ),
        "pdf_page_number": original.get("pdf_page_number"),
        "figure_number": original.get("figure_number"),
        "evidence_excerpt": _text(
            original.get("evidence_excerpt"), 3000
        ),
        "corroboration_status": _text(
            candidate.get("corroboration_status"), 100
        ),
        "matching_official_source_count": candidate.get(
            "matching_official_source_count", 0
        ),
        "matching_claim_check_source_count": candidate.get(
            "matching_claim_check_source_count", 0
        ),
        "matching_context_only_source_count": candidate.get(
            "matching_context_only_source_count", 0
        ),
        "matching_specific_claim_source_count": candidate.get(
            "matching_specific_claim_source_count", 0
        ),
        "evidence_records": [
            safe_record
            for record in evidence_records[:20]
            if (safe_record := _safe_evidence_record(record))
        ],
        "review_status": _text(candidate.get("review_status"), 80),
        "verification_status": _text(
            candidate.get("verification_status"), 80
        ),
        "specific_sub_event_claim_verified": bool(
            candidate.get("specific_sub_event_claim_verified", False)
        ),
        "may_be_used_for_model_validation": bool(
            candidate.get("may_be_used_for_model_validation", False)
        ),
        "model_accuracy": _text(candidate.get("model_accuracy"), 80),
        "decision_note": _text(candidate.get("decision_note"), 1500),
    }


def _safe_snapshot_candidate(candidate):
    if not isinstance(candidate, dict):
        return None

    evidence_records = candidate.get("evidence_records")
    if not isinstance(evidence_records, list):
        evidence_records = []

    def safe_number(value):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    return {
        "candidate_id": _text(candidate.get("candidate_id"), 150),
        "event_name": _text(candidate.get("event_name"), 300),
        "event_type": _text(candidate.get("event_type"), 150),
        "event_date_start": _text(candidate.get("event_date_start"), 30),
        "event_date_end": _text(candidate.get("event_date_end"), 30),
        "place_name": _text(candidate.get("place_name"), 200),
        "state": _text(candidate.get("state"), 100),
        "district": _text(candidate.get("district"), 100),
        "source_document_id": _text(candidate.get("source_document_id"), 150),
        "pdf_page_number": safe_number(candidate.get("pdf_page_number")),
        "figure_number": safe_number(candidate.get("figure_number")),
        "evidence_excerpt": _text(candidate.get("evidence_excerpt"), 3000),
        "corroboration_status": _text(candidate.get("corroboration_status"), 100),
        "matching_official_source_count": safe_number(
            candidate.get("matching_official_source_count")
        ) or 0,
        "matching_claim_check_source_count": safe_number(
            candidate.get("matching_claim_check_source_count")
        ) or 0,
        "matching_context_only_source_count": safe_number(
            candidate.get("matching_context_only_source_count")
        ) or 0,
        "matching_specific_claim_source_count": safe_number(
            candidate.get("matching_specific_claim_source_count")
        ) or 0,
        "evidence_records": [
            safe
            for record in evidence_records[:20]
            if (safe := _safe_evidence_record(record))
        ],
        "review_status": _text(candidate.get("review_status"), 80),
        "verification_status": _text(candidate.get("verification_status"), 80),
        "specific_sub_event_claim_verified": (
            candidate.get("specific_sub_event_claim_verified") is True
        ),
        "may_be_used_for_model_validation": (
            candidate.get("may_be_used_for_model_validation") is True
        ),
        "model_accuracy": _text(candidate.get("model_accuracy"), 80),
        "decision_note": _text(candidate.get("decision_note"), 1500),
    }


def read_latest_evidence_report(path=None):
    """Read cache report locally, or sanitized snapshot on deployment."""

    if path is None:
        if REPORT_PATH.is_file():
            selected_path = REPORT_PATH
        elif SNAPSHOT_PATH.is_file():
            selected_path = SNAPSHOT_PATH
        else:
            raise FileNotFoundError("Evidence report is not available")
    else:
        selected_path = Path(path)

    is_snapshot = (
        selected_path.resolve() == SNAPSHOT_PATH.resolve()
    )

    if not selected_path.is_file():
        raise FileNotFoundError("Evidence report is not available")

    try:
        report = json.loads(
            selected_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Evidence report could not be read") from exc

    if not isinstance(report, dict):
        raise ValueError("Evidence report has an invalid structure")

    sources = report.get("sources")
    candidates = report.get("candidates")

    if not isinstance(sources, list) or not isinstance(candidates, list):
        raise ValueError("Evidence report is missing required collections")

    if is_snapshot and report.get("available") is not True:
        raise ValueError("Sanitized evidence snapshot is invalid")

    if is_snapshot:
        safe_sources = [
            safe
            for source in sources
            if (safe := _safe_source(source))
        ]
        safe_candidates = [
            safe
            for candidate in candidates
            if (safe := _safe_snapshot_candidate(candidate))
        ]
    else:
        safe_sources = [
            safe
            for source in sources
            if (safe := _safe_source(source))
        ]
        safe_candidates = [
            safe
            for candidate in candidates
            if (safe := _safe_candidate(candidate))
        ]

    return {
        "available": True,
        "generated_at": _text(report.get("generated_at"), 80),
        "candidate_count": len(safe_candidates),
        "source_count": len(safe_sources),
        "global_status": _text(report.get("global_status"), 80),
        "human_review_required": (
            report.get("human_review_required") is True
        ),
        "verification_status": _text(
            report.get("verification_status"), 80
        ),
        "model_accuracy": _text(report.get("model_accuracy"), 80),
        "eligible_for_training_or_model_validation": (
            report.get("eligible_for_training_or_model_validation") is True
        ),
        "sources": safe_sources,
        "candidates": safe_candidates,
        "limitations": _safe_string_list(
            report.get("limitations"), limit=30
        ),
    }