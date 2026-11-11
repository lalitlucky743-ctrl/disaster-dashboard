"""Curated registry of public official landslide information pages.

Only URLs defined here may be fetched by the Phase-1 collector. These entries
are landing/catalog pages, not guaranteed machine-readable data APIs.
"""

from dataclasses import dataclass
from typing import Dict, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    name: str
    url: str
    allowed_domains: Tuple[str, ...]
    authority_tier: str
    evidence_role: str
    data_scope: str
    notes: str


OFFICIAL_SOURCES: Dict[str, SourceDefinition] = {
    "gsi_bhusanket": SourceDefinition(
        source_id="gsi_bhusanket",
        name="GSI Bhusanket Public Portal",
        url="https://bhusanket.gsi.gov.in/index.html",
        allowed_domains=("bhusanket.gsi.gov.in", "gsi.gov.in"),
        authority_tier="official_government",
        evidence_role="official_bulletin_and_inventory_catalog",
        data_scope="portal_landing_page",
        notes=(
            "Portal landing page advertises landslide forecast bulletins, "
            "susceptibility maps, impact-probability maps and field-validated "
            "inventory. This registry entry does not imply a public API."
        ),
    ),
    "gsi_landslide_hazard": SourceDefinition(
        source_id="gsi_landslide_hazard",
        name="Geological Survey of India Landslide Hazard",
        url="https://gsi.gov.in/landslide-hazard/",
        allowed_domains=("gsi.gov.in",),
        authority_tier="official_government",
        evidence_role="technical_reports_and_inventory_catalog",
        data_scope="catalog_and_report_search_page",
        notes=(
            "GSI describes its landslide inventory and report-search facility. "
            "The page is a catalog, not a confirmed bulk-download API."
        ),
    ),
    "nrsc_landslide_atlas": SourceDefinition(
        source_id="nrsc_landslide_atlas",
        name="NRSC Landslide Atlas",
        url="https://www.nrsc.gov.in/nrscnew/resources_atlas_landslide.php",
        allowed_domains=("nrsc.gov.in",),
        authority_tier="official_government",
        evidence_role="historical_landslide_inventory_reference",
        data_scope="historical_atlas_catalog",
        notes=(
            "NRSC describes an inventory mapped during 1998-2022, including "
            "seasonal, event-based and route-wise inventories. Use as "
            "historical reference; do not treat it as a live alert feed."
        ),
    ),
    "bhuvan_landslide_inventory": SourceDefinition(
        source_id="bhuvan_landslide_inventory",
        name="NRSC Bhuvan Landslide Inventory",
        url="https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/landslide/landslide.php",
        allowed_domains=("bhuvan-app1.nrsc.gov.in", "nrsc.gov.in"),
        authority_tier="official_government",
        evidence_role="geospatial_inventory_and_document_catalog",
        data_scope="inventory_map_and_document_catalog",
        notes=(
            "Bhuvan page presents inventory layers and related documents. "
            "Its page includes a limitation notice for satellite mapping, "
            "including resolution, cloud cover and shadow."
        ),
    ),
}


def get_source(source_id: str) -> SourceDefinition:
    """Return a registered source; reject unknown IDs rather than accepting URLs."""
    try:
        return OFFICIAL_SOURCES[source_id]
    except KeyError as exc:
        raise ValueError(f"Unknown official source_id: {source_id}") from exc


def is_allowed_https_url(url: str, allowed_domains: Tuple[str, ...]) -> bool:
    """Permit HTTPS URLs only when their hostname matches the source allowlist."""
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
