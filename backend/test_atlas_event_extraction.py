"""Manual Phase-3 extraction test for the cached, approved NRSC Atlas text.

Run from backend folder:
    python -m test_atlas_event_extraction --extract
    python -m test_atlas_event_extraction --summary

This module reads the local Phase-2 text cache only; it makes no network calls.
"""

from __future__ import annotations

import argparse
import json

from app.services.evidence.atlas_event_extractor import extract_nrsc_atlas_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract review-only event references from the cached NRSC Atlas text."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--extract", action="store_true", help="Extract and save candidate references.")
    group.add_argument("--summary", action="store_true", help="Run extraction and print summary without writing output files.")
    args = parser.parse_args()

    try:
        result = extract_nrsc_atlas_candidates(write_outputs=not args.summary)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1

    if args.summary:
        summary = {
            "status": "ok",
            "candidate_reference_count": result["candidate_reference_count"],
            "aggregate_context_count": result["aggregate_context_count"],
            "verification": result["verification"],
            "output_json_path": result["output_json_path"],
            "output_csv_path": result["output_csv_path"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    # Default is the same as --extract, intentionally local-only.
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
