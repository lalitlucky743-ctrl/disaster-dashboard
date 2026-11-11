"""Bounded downloader and text-only PDF reader for approved documents.

Safety properties:
- accepts an approved document ID, never an arbitrary URL;
- HTTPS and hostname allowlist are checked for every redirect;
- bounded connect/read timeouts, redirects, bytes, pages and extracted text;
- no automatic OCR, form submission, arbitrary crawling or event verification;
- documents are cached locally under this package's .cache directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .approved_documents import get_approved_document

CONNECT_TIMEOUT_SECONDS = 6
READ_TIMEOUT_SECONDS = 25
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_PDF_PAGES = 120
MAX_EXTRACTED_CHARS = 300_000
CHUNK_SIZE = 64 * 1024
USER_AGENT = (
    "UttarakhandDisasterIntelligencePlatform/1.0 "
    "(official-document-reader; read-only)"
)
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "documents"


def _is_allowed_https_url(url: str, allowed_domains: tuple[str, ...]) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        return any(
            host == domain or host.endswith("." + domain)
            for domain in allowed_domains
        )
    except (TypeError, ValueError):
        return False


def _new_session() -> requests.Session:
    # One bounded retry for transient connection errors only. HTTP 429 is not retried.
    retry = Retry(
        total=1,
        connect=1,
        read=0,
        status=0,
        backoff_factor=0.5,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=2,
        pool_maxsize=2,
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        }
    )
    session.mount("https://", adapter)
    return session


def _download_to_cache(document_id: str, url: str, allowed_domains: tuple[str, ...], target: Path) -> Dict[str, Any]:
    current_url = url
    session = _new_session()
    total_bytes = 0
    digest = hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{document_id}_",
            suffix=".part",
            dir=str(target.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)

        with temp_path.open("wb") as output:
            for redirect_number in range(MAX_REDIRECTS + 1):
                if not _is_allowed_https_url(current_url, allowed_domains):
                    raise ValueError(
                        "Blocked document URL: redirect target is outside the HTTPS allowlist."
                    )

                response = session.get(
                    current_url,
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    allow_redirects=False,
                    stream=True,
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        raise ValueError("Document source returned a redirect without Location.")
                    if redirect_number >= MAX_REDIRECTS:
                        raise ValueError("Document source exceeded maximum redirect count.")
                    current_url = urljoin(current_url, location)
                    continue

                if response.status_code == 429:
                    response.close()
                    return {
                        "status": "rate_limited",
                        "http_status": 429,
                        "error": "Source returned HTTP 429; no repeated request was made.",
                        "final_url": current_url,
                    }

                response.raise_for_status()
                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if content_type not in ("application/pdf", "application/octet-stream"):
                    response.close()
                    return {
                        "status": "not_pdf",
                        "http_status": response.status_code,
                        "content_type": content_type or None,
                        "error": f"Expected PDF content, received {content_type or 'unknown'}.",
                        "final_url": current_url,
                    }

                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = None
                    if declared_size is not None and declared_size > MAX_DOCUMENT_BYTES:
                        response.close()
                        return {
                            "status": "too_large",
                            "http_status": response.status_code,
                            "error": (
                                f"Document declares {declared_size} bytes; "
                                f"limit is {MAX_DOCUMENT_BYTES} bytes."
                            ),
                            "final_url": current_url,
                        }

                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > MAX_DOCUMENT_BYTES:
                        response.close()
                        return {
                            "status": "too_large",
                            "http_status": response.status_code,
                            "error": f"Document exceeded {MAX_DOCUMENT_BYTES} byte limit.",
                            "final_url": current_url,
                        }
                    digest.update(chunk)
                    output.write(chunk)

                response.close()
                break
            else:
                raise ValueError("Document redirect processing ended unexpectedly.")

        with temp_path.open("rb") as check_file:
            signature = check_file.read(5)
        if signature != b"%PDF-":
            return {
                "status": "not_pdf",
                "http_status": 200,
                "error": "Response did not begin with a valid PDF signature.",
                "final_url": current_url,
            }

        os.replace(temp_path, target)
        temp_path = None
        return {
            "status": "downloaded",
            "http_status": 200,
            "content_type": "application/pdf",
            "final_url": current_url,
            "bytes_downloaded": total_bytes,
            "sha256": digest.hexdigest(),
            "cached_path": str(target),
        }
    finally:
        session.close()
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def read_approved_pdf(document_id: str) -> Dict[str, Any]:
    """Download/cache and extract bounded text from an approved PDF ID."""
    document = get_approved_document(document_id)
    fetched_at = datetime.now(timezone.utc).isoformat()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = CACHE_DIR / f"{document.document_id}.pdf"
    text_path = CACHE_DIR / f"{document.document_id}.txt"
    metadata_path = CACHE_DIR / f"{document.document_id}.json"

    base: Dict[str, Any] = {
        "document_id": document.document_id,
        "source_id": document.source_id,
        "title": document.title,
        "url": document.url,
        "document_type": document.document_type,
        "coverage_period": document.coverage_period,
        "fetched_at": fetched_at,
        "status": "error",
        "cached": pdf_path.exists(),
        "bytes_downloaded": None,
        "sha256": None,
        "pages_total": None,
        "pages_processed": 0,
        "text_characters": 0,
        "text_path": None,
        "text_preview": "",
        "extraction_method": "pypdf text extraction only; no OCR",
        "event_verification": "not_performed",
        "error": None,
        "notes": document.notes,
    }

    if not pdf_path.exists():
        try:
            download_result = _download_to_cache(
                document.document_id,
                document.url,
                document.allowed_domains,
                pdf_path,
            )
        except requests.RequestException as exc:
            base["error"] = f"Download failed: {type(exc).__name__}: {exc}"
            return base
        except (OSError, ValueError) as exc:
            base["error"] = str(exc)
            return base

        if download_result.get("status") != "downloaded":
            base.update(download_result)
            return base
        base.update(download_result)
    else:
        try:
            file_size = pdf_path.stat().st_size
            if file_size > MAX_DOCUMENT_BYTES:
                base.update(
                    {
                        "status": "too_large",
                        "error": f"Cached document exceeds {MAX_DOCUMENT_BYTES} byte limit.",
                    }
                )
                return base
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            base["bytes_downloaded"] = file_size
            base["sha256"] = digest
            base["status"] = "cached"
        except OSError as exc:
            base["error"] = f"Could not read cached document: {exc}"
            return base

    try:
        from pypdf import PdfReader
    except ImportError:
        base.update(
            {
                "status": "parser_missing",
                "error": "Install the optional PDF parser with: python -m pip install pypdf",
            }
        )
        return base

    try:
        reader = PdfReader(str(pdf_path), strict=False)
        pages_total = len(reader.pages)
        pages_to_process = min(pages_total, MAX_PDF_PAGES)
        pieces = []
        total_chars = 0

        for page_number in range(pages_to_process):
            page_text = reader.pages[page_number].extract_text() or ""
            page_text = page_text.strip()
            if not page_text:
                continue
            remaining = MAX_EXTRACTED_CHARS - total_chars
            if remaining <= 0:
                break
            page_text = page_text[:remaining]
            pieces.append(f"\n\n--- PAGE {page_number + 1} ---\n{page_text}")
            total_chars += len(page_text)

        extracted_text = "".join(pieces).strip()
        if extracted_text:
            text_path.write_text(extracted_text, encoding="utf-8")
            base["text_path"] = str(text_path)
            base["text_preview"] = extracted_text[:1200]

        base.update(
            {
                "status": "ok" if extracted_text else "no_extractable_text",
                "pages_total": pages_total,
                "pages_processed": pages_to_process,
                "text_characters": len(extracted_text),
                "error": None if extracted_text else (
                    "No selectable text was extracted from the processed pages. "
                    "No OCR was attempted; this may be a scanned or image-heavy PDF."
                ),
            }
        )

        metadata_path.write_text(
            json.dumps(
                {
                    key: value
                    for key, value in base.items()
                    if key != "text_preview"
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return base
    except Exception as exc:
        base.update(
            {
                "status": "parse_error",
                "error": f"PDF text extraction failed: {type(exc).__name__}: {exc}",
            }
        )
        return base
