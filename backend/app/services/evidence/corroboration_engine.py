
"""Deterministic, allowlisted corroboration for Phase-3 event candidates.

Important:
- No arbitrary crawling or search-engine requests.
- Exact URLs and hostnames come only from corroboration_registry.py.
- Matching is performed within bounded text passages, not across an entire
  document. Signals from unrelated paragraphs cannot be combined.
- A match is not a verified ground-truth label.
- Human review is always required.
- This module never evaluates or changes ML model accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .corroboration_registry import (
    CANDIDATE_RULES,
    SOURCES,
    list_candidate_rules,
    list_sources,
)

EVIDENCE_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVIDENCE_DIR / ".cache" / "corroboration"
DOWNLOAD_DIR = CACHE_DIR / "downloads"

DEFAULT_INPUT = (
    EVIDENCE_DIR
    / ".cache"
    / "documents"
    / "extractions"
    / "nrsc_landslide_atlas_2023_candidate_references.json"
)
DEFAULT_OUTPUT = CACHE_DIR / "nrsc_atlas_2023_corroboration.json"

USER_AGENT = "Uttarakhand-Disaster-Intelligence-EvidenceReader/1.0"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 25
MAX_HTML_TEXT_CHARS = 500_000
MAX_PDF_PAGES = 180
MAX_EXCERPT_CHARS = 900

# A matching passage may contain adjacent sentences, but evidence from
# distant paragraphs must never be combined.
MAX_PASSAGE_CHARS = 2400


class _VisibleTextParser(HTMLParser):
    """Small standard-library HTML text extractor; no browser execution."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in ("script", "style", "noscript", "svg"):
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("script", "style", "noscript", "svg") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return

        clean = data.strip()
        if not clean:
            return

        self.parts.append(clean + " ")

        if self._in_title:
            self.title_parts.append(clean)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _normalise(value: str) -> str:
    value = html.unescape(str(value or "")).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _contains_phrase(normalised_text: str, phrase: str) -> bool:
    target = _normalise(phrase)

    if not target:
        return False

    return f" {target} " in f" {normalised_text} "


def _safe_host(url: str, allowed_hosts) -> bool:
    parsed = urlparse(url)

    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower()
        in {host.lower() for host in allowed_hosts}
    )


def _split_passages(text: str):
    """Split extracted source text into conservative evidence passages.

    HTML extraction preserves paragraph breaks. PDF extraction can contain
    line breaks inside paragraphs, so short lines are joined where possible.
    Empty lines and sentence boundaries provide additional separation.
    """

    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")

    raw_blocks = re.split(r"\n\s*\n+", text)
    passages = []

    for block in raw_blocks:
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if not lines:
            continue

        joined = " ".join(lines)
        joined = re.sub(r"\s+", " ", joined).strip()

        if not joined:
            continue

        # Split unusually long blocks at sentence boundaries. This prevents
        # a large extracted block from silently becoming whole-document match.
        if len(joined) > MAX_PASSAGE_CHARS:
            sentences = re.split(r"(?<=[.!?])\s+", joined)
            current = ""

            for sentence in sentences:
                sentence = sentence.strip()

                if not sentence:
                    continue

                if current and len(current) + len(sentence) + 1 > MAX_PASSAGE_CHARS:
                    passages.append(current)
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()

            if current:
                passages.append(current)
        else:
            passages.append(joined)

    return passages


def _extract_html(payload: bytes):
    decoded = payload.decode("utf-8", errors="replace")
    parser = _VisibleTextParser()
    parser.feed(decoded)

    # Preserve block boundaries. Do not collapse all paragraphs into one.
    visible = "".join(parser.parts).strip()
    title = " ".join(parser.title_parts).strip()

    if len(visible) > MAX_HTML_TEXT_CHARS:
        visible = visible[:MAX_HTML_TEXT_CHARS]

    return title, [{"page_number": None, "text": visible}]


def _extract_pdf(payload: bytes):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF corroboration. "
            "Install it in the backend venv."
        ) from exc

    reader = PdfReader(io.BytesIO(payload), strict=False)

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise RuntimeError(
                "PDF is encrypted and cannot be read."
            ) from exc

    pages = []
    total_chars = 0

    for index, page in enumerate(
        reader.pages[:MAX_PDF_PAGES],
        start=1,
    ):
        text = page.extract_text() or ""

        if text.strip():
            pages.append({
                "page_number": index,
                "text": text,
            })
            total_chars += len(text)

        if total_chars >= 1_000_000:
            break

    return {
        "pages_total": len(reader.pages),
        "pages_processed": min(len(reader.pages), MAX_PDF_PAGES),
        "pages": pages,
        "text_characters": total_chars,
    }


def _download_source(source, refresh=False):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    extension = ".pdf" if source.kind == "pdf" else ".html"
    cache_path = DOWNLOAD_DIR / f"{source.source_id}{extension}"

    if cache_path.exists() and not refresh:
        payload = cache_path.read_bytes()

        if len(payload) > source.max_bytes:
            cache_path.unlink(missing_ok=True)
        else:
            return payload, True, None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/pdf,text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"
        ),
    }

    try:
        with requests.get(
            source.url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            stream=True,
            allow_redirects=True,
        ) as response:

            if not _safe_host(response.url, source.allowed_hosts):
                raise ValueError(
                    "Redirected to a non-allowlisted host: "
                    f"{urlparse(response.url).hostname}"
                )

            if response.status_code == 429:
                raise RuntimeError(
                    "HTTP 429 rate limited; no automatic retry performed."
                )

            response.raise_for_status()

            content_type = (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )

            if source.kind == "pdf" and content_type != "application/pdf":
                raise ValueError(
                    "Expected application/pdf, received "
                    f"{content_type or 'unknown'}."
                )

            if source.kind == "html" and content_type not in (
                "text/html",
                "application/xhtml+xml",
            ):
                raise ValueError(
                    "Expected HTML content, received "
                    f"{content_type or 'unknown'}."
                )

            declared = response.headers.get("content-length")

            if declared:
                try:
                    if int(declared) > source.max_bytes:
                        raise ValueError(
                            "Source document exceeds the configured size limit."
                        )
                except ValueError as exc:
                    if "size limit" in str(exc):
                        raise

            chunks = []
            total = 0

            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue

                total += len(chunk)

                if total > source.max_bytes:
                    raise ValueError(
                        "Source document exceeded the configured size limit."
                    )

                chunks.append(chunk)

            payload = b"".join(chunks)
            cache_path.write_bytes(payload)

            meta = {
                "http_status": response.status_code,
                "content_type": content_type,
                "final_url": response.url,
            }

            return payload, False, meta

    except (requests.RequestException, socket.timeout) as exc:
        raise RuntimeError(
            f"Source request failed: {type(exc).__name__}: {exc}"
        ) from exc


def fetch_and_extract_source(source_id: str, refresh=False):
    source = SOURCES.get(source_id)

    if source is None:
        raise ValueError(f"Unknown source_id: {source_id}")

    payload, cached, response_meta = _download_source(
        source,
        refresh=refresh,
    )

    digest = hashlib.sha256(payload).hexdigest()

    if source.kind == "html":
        title, pages = _extract_html(payload)
        text_characters = sum(len(page["text"]) for page in pages)
        page_total = None
        page_processed = None
    else:
        extracted = _extract_pdf(payload)
        title = source.source_name
        pages = extracted["pages"]
        text_characters = extracted["text_characters"]
        page_total = extracted["pages_total"]
        page_processed = extracted["pages_processed"]

    return {
        "source_id": source.source_id,
        "source_name": source.source_name,
        "publisher": source.publisher,
        "publication_date": source.publication_date,
        "url": source.url,
        "final_url": (response_meta or {}).get("final_url", source.url),
        "kind": source.kind,
        "status": "ok",
        "cached": cached,
        "http_status": (response_meta or {}).get("http_status"),
        "content_type": (response_meta or {}).get(
            "content_type",
            "application/pdf" if source.kind == "pdf" else "text/html",
        ),
        "bytes_downloaded": len(payload),
        "sha256": digest,
        "title": title,
        "pages_total": page_total,
        "pages_processed": page_processed,
        "text_characters": text_characters,
        "pages": pages,
        "fetched_at": _utc_now(),
        "independence_note": source.independence_note,
        "evidence_role": source.evidence_role,
        "error": None,
    }


def _match_passage(rule, passage):
    """Evaluate all candidate signals inside one passage only."""

    normalized = _normalise(passage)

    place_hits = [
        phrase for phrase in rule.place_aliases
        if _contains_phrase(normalized, phrase)
    ]

    date_hits = [
        phrase for phrase in rule.date_phrases
        if _contains_phrase(normalized, phrase)
    ]

    district_hits = [
        phrase for phrase in rule.district_phrases
        if _contains_phrase(normalized, phrase)
    ]

    event_hits = [
        phrase for phrase in rule.event_phrases
        if _contains_phrase(normalized, phrase)
    ]

    specific_group_hits = []

    for group in rule.specific_claim_groups:
        found = [
            phrase for phrase in group
            if _contains_phrase(normalized, phrase)
        ]

        specific_group_hits.append({
            "required_any_of": list(group),
            "matched": bool(found),
            "matched_phrases": found,
        })

    return {
        "place_hits": place_hits,
        "date_hits": date_hits,
        "district_hits": district_hits,
        "event_hits": event_hits,
        "specific_group_hits": specific_group_hits,
        "place_match": bool(place_hits),
        "date_match": len(date_hits) >= rule.min_date_matches,
        "district_match": bool(district_hits),
        "event_context_match": bool(event_hits),
    }


def _match_one_candidate(candidate_id: str, source_data: dict):
    rule = CANDIDATE_RULES[candidate_id]
    pages = source_data.get("pages", [])

    evidence_role = source_data.get("evidence_role", "claim_check")

    if evidence_role not in ("claim_check", "context_only"):
        raise ValueError(f"Unsupported evidence role: {evidence_role}")

    # Every match is evaluated within one bounded passage.
    passage_records = []

    for page in pages:
        page_text = page.get("text", "")
        page_number = page.get("page_number")

        for passage in _split_passages(page_text):
            signals = _match_passage(rule, passage)

            passage_records.append({
                "page_number": page_number,
                "text": passage,
                "signals": signals,
            })

    # Passage-level diagnostics. These are unions for reporting only.
    # They are NEVER used to construct a match across different passages.
    place_hits = sorted({
        phrase
        for item in passage_records
        for phrase in item["signals"]["place_hits"]
    })

    date_hits = sorted({
        phrase
        for item in passage_records
        for phrase in item["signals"]["date_hits"]
    })

    district_hits = sorted({
        phrase
        for item in passage_records
        for phrase in item["signals"]["district_hits"]
    })

    event_hits = sorted({
        phrase
        for item in passage_records
        for phrase in item["signals"]["event_hits"]
    })

    # A coherent core passage must contain place, date, district and event
    # context together. Separate passages cannot satisfy this requirement.
    core_passages = [
        item for item in passage_records
        if (
            item["signals"]["place_match"]
            and item["signals"]["date_match"]
            and item["signals"]["district_match"]
            and item["signals"]["event_context_match"]
        )
    ]

    # Technical claim groups must all match within the SAME core passage.
    specific_passages = []

    for item in core_passages:
        groups = item["signals"]["specific_group_hits"]

        if groups and all(group["matched"] for group in groups):
            specific_passages.append(item)

    # Context-only sources are never eligible for specific technical claims.
    specific_claim_complete = (
        evidence_role == "claim_check"
        and bool(specific_passages)
    )

    if evidence_role == "context_only":
        context_passages = [
            item for item in passage_records
            if (
                item["signals"]["place_match"]
                and item["signals"]["date_match"]
                and item["signals"]["event_context_match"]
            )
        ]

        match_status = (
            "context_only_match"
            if context_passages
            else "no_match"
        )

        selected_passages = context_passages

    elif specific_claim_complete:
        match_status = "strong_reference_match"
        selected_passages = specific_passages

    elif core_passages:
        match_status = "partial_context_match"
        selected_passages = core_passages

    else:
        # Keep partial diagnostic passages visible, but do not call them
        # corroboration matches.
        selected_passages = [
            item for item in passage_records
            if (
                item["signals"]["place_match"]
                and (
                    item["signals"]["date_match"]
                    or item["signals"]["event_context_match"]
                )
            )
        ]

        match_status = "no_match"

    # Only passages that actually support the selected result are cited.
    matched_pages = []
    excerpts = []

    for item in selected_passages:
        page_number = item["page_number"]

        if (
            page_number is not None
            and page_number not in matched_pages
        ):
            matched_pages.append(page_number)

        excerpt = item["text"][:MAX_EXCERPT_CHARS].strip()

        if excerpt and excerpt not in excerpts and len(excerpts) < 2:
            excerpts.append(excerpt)

    # Detailed signal summary is taken from the selected coherent passage.
    # If no passage matched, report the strongest individual passage only
    # for diagnostics; it cannot change match_status.
    diagnostic_pool = selected_passages or passage_records

    diagnostic = (
        max(
            diagnostic_pool,
            key=lambda item: (
                int(item["signals"]["place_match"])
                + int(item["signals"]["date_match"])
                + int(item["signals"]["district_match"])
                + int(item["signals"]["event_context_match"])
            ),
        )
        if diagnostic_pool
        else None
    )

    diagnostic_signals = (
        diagnostic["signals"]
        if diagnostic
        else {
            "place_hits": [],
            "date_hits": [],
            "district_hits": [],
            "event_hits": [],
            "specific_group_hits": [
                {
                    "required_any_of": list(group),
                    "matched": False,
                    "matched_phrases": [],
                }
                for group in rule.specific_claim_groups
            ],
            "place_match": False,
            "date_match": False,
            "district_match": False,
            "event_context_match": False,
        }
    )

    # Report whether the signals are found anywhere, separately from the
    # coherent passage result. This makes split-signal cases transparent.
    signals_found_anywhere = {
        "place_match": bool(place_hits),
        "date_match": len(date_hits) >= rule.min_date_matches,
        "district_match": bool(district_hits),
        "event_context_match": bool(event_hits),
    }

    return {
        "source_id": source_data["source_id"],
        "source_name": source_data["source_name"],
        "publisher": source_data["publisher"],
        "publication_date": source_data["publication_date"],
        "url": source_data["url"],
        "final_url": source_data.get("final_url"),
        "source_sha256": source_data["sha256"],
        "source_cached": source_data["cached"],
        "source_pages": matched_pages,
        "evidence_role": evidence_role,
        "matching_signals": {
            "place_match": diagnostic_signals["place_match"],
            "matched_place_aliases": diagnostic_signals["place_hits"],
            "date_match": diagnostic_signals["date_match"],
            "matched_date_phrases": diagnostic_signals["date_hits"],
            "district_match": diagnostic_signals["district_match"],
            "matched_district_phrases": diagnostic_signals["district_hits"],
            "event_context_match": diagnostic_signals["event_context_match"],
            "matched_event_phrases": diagnostic_signals["event_hits"],
            "specific_claim_complete": specific_claim_complete,
            "specific_claim_groups": (
                diagnostic_signals["specific_group_hits"]
            ),
            "signals_found_anywhere": signals_found_anywhere,
            "coherent_core_passage_count": len(core_passages),
            "specific_claim_passage_count": len(specific_passages),
        },
        "match_status": match_status,
        "evidence_excerpts": excerpts,
        "independence_note": source_data["independence_note"],
        "source_text_characters": source_data["text_characters"],
    }


def corroborate_candidates(
    input_path=None,
    output_path=None,
    refresh=False,
    candidate_id=None,
):
    input_path = Path(input_path) if input_path else DEFAULT_INPUT
    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT

    if not input_path.exists():
        raise FileNotFoundError(
            f"Phase-3 candidate JSON not found: {input_path}"
        )

    phase3 = json.loads(input_path.read_text(encoding="utf-8"))
    candidates = phase3.get("candidates")

    if not isinstance(candidates, list):
        raise ValueError(
            "Phase-3 JSON must contain a 'candidates' array."
        )

    if candidate_id:
        candidates = [
            item for item in candidates
            if item.get("candidate_id") == candidate_id
        ]

        if not candidates:
            raise ValueError(
                f"Candidate not found in input JSON: {candidate_id}"
            )

    source_cache = {}
    source_errors = []
    required_source_ids = []

    for candidate in candidates:
        cid = candidate.get("candidate_id")
        rule = CANDIDATE_RULES.get(cid)

        if rule:
            for source_id in rule.source_ids:
                if source_id not in required_source_ids:
                    required_source_ids.append(source_id)

    for source_id in required_source_ids:
        try:
            source_cache[source_id] = fetch_and_extract_source(
                source_id,
                refresh=refresh,
            )
        except Exception as exc:
            source_errors.append({
                "source_id": source_id,
                "status": "source_unavailable",
                "error": f"{type(exc).__name__}: {exc}",
                "checked_at": _utc_now(),
            })

    candidate_results = []

    for candidate in candidates:
        cid = candidate.get("candidate_id")
        rule = CANDIDATE_RULES.get(cid)

        if rule is None:
            candidate_results.append({
                "candidate_id": cid,
                "event_name": candidate.get("event_name"),
                "corroboration_status": "no_rule_configured",
                "evidence_records": [],
                "review_status": "needs_human_review",
                "verification_status": "not_verified",
                "may_be_used_for_model_validation": False,
                "model_accuracy": "not_evaluated",
            })
            continue

        evidence_records = []

        for source_id in rule.source_ids:
            source_data = source_cache.get(source_id)

            if source_data is None:
                error_item = next(
                    (
                        item for item in source_errors
                        if item["source_id"] == source_id
                    ),
                    None,
                )

                evidence_records.append({
                    "source_id": source_id,
                    "match_status": "source_unavailable",
                    "error": (
                        error_item["error"]
                        if error_item
                        else "Source unavailable."
                    ),
                })
                continue

            evidence_records.append(
                _match_one_candidate(cid, source_data)
            )

        context_only_matches = [
            item for item in evidence_records
            if (
                item.get("evidence_role") == "context_only"
                and item.get("match_status") == "context_only_match"
            )
        ]


        # Claim-check sources only.
        # Passage-level matching is already enforced by _match_one_candidate().
        # Do not require optional diagnostic metadata such as
        # coherent_core_passage_count here.
        claim_check_matches = [
            item for item in evidence_records
            if (
                item.get("evidence_role", "claim_check") == "claim_check"
                and item.get("match_status") in (
                    "strong_reference_match",
                    "partial_context_match",
                )
                and all(
                    item.get("matching_signals", {}).get(signal) is True
                    for signal in (
                        "place_match",
                        "date_match",
                        "district_match",
                        "event_context_match",
                    )
                )
            )
        ]

        # A specific claim requires a strong match and all configured
        # specific-claim groups must already have passed in the engine.
        specific_claim_matches = [
            item for item in claim_check_matches
            if (
                item.get("match_status") == "strong_reference_match"
                and item.get("matching_signals", {}).get(
                    "specific_claim_complete"
                ) is True
            )
        ]


        if len(specific_claim_matches) >= 2:
            status = "multi_source_strong_reference_match"
        elif specific_claim_matches:
            status = "single_source_strong_reference_match"
        elif claim_check_matches:
            status = "single_source_partial_context_match"
        elif context_only_matches:
            status = "context_only_documentary_context_match"
        elif any(
            item.get("match_status") == "source_unavailable"
            for item in evidence_records
        ):
            status = "source_unavailable"
        else:
            status = "no_independent_match"

        candidate_results.append({
            "candidate_id": cid,
            "event_name": candidate.get("event_name"),
            "original_candidate": candidate,
            "corroboration_status": status,
            "matching_official_source_count": len(claim_check_matches),
            "matching_context_only_source_count": len(context_only_matches),
            "matching_claim_check_source_count": len(claim_check_matches),
            "matching_specific_claim_source_count": len(
                specific_claim_matches
            ),
            "evidence_records": evidence_records,
            "review_status": "needs_human_review",
            "verification_status": "not_verified",
            "specific_sub_event_claim_verified": False,
            "may_be_used_for_model_validation": False,
            "model_accuracy": "not_evaluated",
            "decision_note": (
                "Source matches are documentary corroboration only. "
                "A human reviewer must inspect the cited passage and source. "
                "No record is promoted to ground truth by this process."
            ),
        })

    result = {
        "generated_at": _utc_now(),
        "phase3_input": str(input_path),
        "candidate_count": len(candidate_results),
        "source_count": len(source_cache) + len(source_errors),
        "sources": [
            {
                key: value
                for key, value in source.items()
                if key != "pages"
            }
            for source in source_cache.values()
        ] + source_errors,
        "candidates": candidate_results,
        "global_status": "documentary_corroboration_only",
        "human_review_required": True,
        "verification_status": "not_verified",
        "model_accuracy": "not_evaluated",
        "eligible_for_training_or_model_validation": False,
        "limitations": [
            "Only exact allowlisted official source URLs are fetched.",
            "No arbitrary crawling, search-engine discovery, or AI inference is performed.",
            "Evidence signals from separate passages are never combined into a match.",
            "A source match does not establish that an event is a model prediction hit.",
            "Context-only sources are excluded from claim-check and specific-claim counts.",
            "The Kedarnath artificial-embankment sub-event requires separate documentary support and human review.",
            "One source match is not independent multi-source verification.",
            "No candidate is eligible for training or model validation until separate human review and a defined ground-truth process.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "status": "ok",
        "candidate_count": len(candidate_results),
        "source_count": result["source_count"],
        "candidate_statuses": [
            {
                "candidate_id": item["candidate_id"],
                "corroboration_status": item["corroboration_status"],
                "matching_official_source_count": item.get(
                    "matching_official_source_count",
                    0,
                ),
                "matching_context_only_source_count": item.get(
                    "matching_context_only_source_count",
                    0,
                ),
                "matching_specific_claim_source_count": item.get(
                    "matching_specific_claim_source_count",
                    0,
                ),
                "verification_status": item["verification_status"],
                "may_be_used_for_model_validation": item[
                    "may_be_used_for_model_validation"
                ],
            }
            for item in candidate_results
        ],
        "source_errors": source_errors,
        "output_path": str(output_path),
        "human_review_required": True,
        "model_accuracy": "not_evaluated",
        "eligible_for_training_or_model_validation": False,
    }

    return summary, result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Corroborate Phase-3 event candidates against exact "
            "allowlisted official sources."
        )
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List approved sources and rules; no network.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Fetch allowlisted sources and write corroboration JSON.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh cached source documents.",
    )
    parser.add_argument(
        "--candidate",
        help="Process only one candidate ID.",
    )
    parser.add_argument(
        "--input",
        help="Phase-3 candidate JSON path.",
    )
    parser.add_argument(
        "--output",
        help="Corroboration output JSON path.",
    )

    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps({
            "sources": list_sources(),
            "candidate_rules": list_candidate_rules(),
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.run:
        parser.error("Specify --list or --run.")

    summary, _ = corroborate_candidates(
        input_path=args.input,
        output_path=args.output,
        refresh=args.refresh,
        candidate_id=args.candidate,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
