"""Explicitly approved public documents for the evidence pipeline.

Only document IDs declared here may be downloaded by document_reader.py.
Do not add arbitrary URLs supplied by users or discovered on unrelated pages.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class ApprovedDocument:
    document_id: str
    source_id: str
    title: str
    url: str
    allowed_domains: Tuple[str, ...]
    document_type: str
    coverage_period: str
    notes: str


APPROVED_DOCUMENTS: Dict[str, ApprovedDocument] = {
    "nrsc_landslide_atlas_2023": ApprovedDocument(
        document_id="nrsc_landslide_atlas_2023",
        source_id="nrsc_landslide_atlas",
        title="Landslides Atlas of India (updated 25 August 2023)",
        url=(
            "https://www.nrsc.gov.in/nrscnew/assets/pdf/atlas/landslide/"
            "Landslides_Atlas_of_India_Updated_25Aug2023.pdf"
        ),
        allowed_domains=("nrsc.gov.in",),
        document_type="historical_landslide_atlas_pdf",
        coverage_period="1998-2022 (as described by NRSC landing page)",
        notes=(
            "Historical atlas/reference, not a live alert feed. NRSC describes "
            "seasonal, event-based and route-wise inventories. The atlas PDF is "
            "large; download only when explicitly requested by the CLI command. "
            "Extracted text must be reviewed and normalized before it can become "
            "a structured event record."
        ),
    ),
}


def get_approved_document(document_id: str) -> ApprovedDocument:
    """Return one explicitly registered document; reject unknown IDs."""
    try:
        return APPROVED_DOCUMENTS[document_id]
    except KeyError as exc:
        raise ValueError(f"Unknown approved document_id: {document_id}") from exc


def list_approved_documents():
    """Return safe metadata only; never trigger a network request."""
    return [
        {
            "document_id": item.document_id,
            "source_id": item.source_id,
            "title": item.title,
            "url": item.url,
            "document_type": item.document_type,
            "coverage_period": item.coverage_period,
            "notes": item.notes,
        }
        for item in APPROVED_DOCUMENTS.values()
    ]
