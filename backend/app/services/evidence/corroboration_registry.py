
"""Exact allowlist for Phase-4 official-source corroboration.

This module deliberately contains fixed URLs and fixed candidate rules.
It does not discover arbitrary links or crawl the open web.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_name: str
    url: str
    kind: str  # "html" or "pdf"
    allowed_hosts: Tuple[str, ...]
    publisher: str
    publication_date: str
    max_bytes: int
    independence_note: str
    evidence_role: str = "claim_check"


@dataclass(frozen=True)
class CandidateRule:
    candidate_id: str
    source_ids: Tuple[str, ...]
    place_aliases: Tuple[str, ...]
    date_phrases: Tuple[str, ...]
    district_phrases: Tuple[str, ...]
    event_phrases: Tuple[str, ...]
    specific_claim_groups: Tuple[Tuple[str, ...], ...]
    min_date_matches: int = 1


SOURCES = {
    "pib_gsi_chamoli_2021": SourceSpec(
        source_id="pib_gsi_chamoli_2021",
        source_name="GSI technical findings republished by Press Information Bureau",
        url="https://www.pib.gov.in/PressReleasePage.aspx?PRID=1730923&lang=2&reg=48",
        kind="html",
        allowed_hosts=("www.pib.gov.in", "pib.gov.in"),
        publisher="Ministry of Mines / Geological Survey of India (hosted by PIB)",
        publication_date="2021-06-28",
        max_bytes=6 * 1024 * 1024,
        independence_note=(
            "Different technical agency from the NRSC/ISRO Atlas; the page "
            "publishes GSI field-team findings. One source alone is not a "
            "multi-source verification."
        ),
        evidence_role="claim_check",
    ),


    "nidm_india_disaster_report_2013": SourceSpec(
        source_id="nidm_india_disaster_report_2013",
        source_name="India Disaster Report 2013",
        url="https://nidm.mha.gov.in/PDF/pubs/India%20Disaster%20Report%202013.pdf",
        kind="pdf",
        allowed_hosts=("nidm.mha.gov.in",),
        publisher="National Institute of Disaster Management, Ministry of Home Affairs",
        publication_date="2014",
        max_bytes=24 * 1024 * 1024,
        independence_note=(
            "Government disaster-management report distinct from the NRSC/ISRO "
            "Atlas. It provides event context; it does not reproduce every "
            "specific sub-event claim in the Atlas."
        ),
        evidence_role="claim_check",
    ),


    "pib_culture_kedarnath_2013": SourceSpec(
        source_id="pib_culture_kedarnath_2013",
        source_name="Kedarnath restoration and flash-flood context",
        url="https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=100700",
        kind="html",
        allowed_hosts=("www.pib.gov.in", "pib.gov.in"),
        publisher="Ministry of Culture, Government of India (hosted by PIB)",
        publication_date="2013-11-19",
        max_bytes=6 * 1024 * 1024,
        independence_note=(
            "Government ministry press release providing broad Kedarnath "
            "flood and restoration context only. It does not independently "
            "confirm the artificial-embankment breach or specific landslide claim."
        ),
        evidence_role="context_only",
    ),
}


CANDIDATE_RULES = {
    "nrsc_atlas_raunthi_gad_2021": CandidateRule(
        candidate_id="nrsc_atlas_raunthi_gad_2021",
        source_ids=("pib_gsi_chamoli_2021",),
        place_aliases=("raunthi garh", "raunthi gad"),
        date_phrases=(
            "7 february 2021",
            "february 7 2021",
            "07.02.2021",
        ),
        district_phrases=(
            "chamoli district",
            "district of chamoli",
        ),
        event_phrases=(
            "avalanche",
            "debris flow",
            "landslide",
            "rock mass",
        ),
        specific_claim_groups=(
            ("avalanche", "rock mass"),
            ("debris flow",),
        ),
        min_date_matches=1,
    ),

    "nrsc_atlas_kedarnath_2013": CandidateRule(
        candidate_id="nrsc_atlas_kedarnath_2013",
        source_ids=(
            "nidm_india_disaster_report_2013",
            "pib_culture_kedarnath_2013",
        ),
        place_aliases=(
            "kedarnath valley",
            "kedarnath town",
            "kedarnath shrine",
            "kedarnath",
        ),
        date_phrases=(
            "16 june 2013",
            "17 june 2013",
        ),
        district_phrases=(
            "rudraprayag district",
            "district of rudraprayag",
        ),
        event_phrases=(
            "landslide",
            "landslides",
            "flash flood",
            "flash floods",
            "toe erosion",
        ),
        specific_claim_groups=(
            ("reactivated landslide",),
            ("artificial embankment",),
            ("breached", "breach"),
        ),
        min_date_matches=2,
    ),
}


def list_sources():
    """Return safe, serializable source metadata without network calls."""
    return [
        {
            "source_id": spec.source_id,
            "source_name": spec.source_name,
            "url": spec.url,
            "kind": spec.kind,
            "publisher": spec.publisher,
            "publication_date": spec.publication_date,
            "max_bytes": spec.max_bytes,
            "evidence_role": spec.evidence_role,
        }
        for spec in SOURCES.values()
    ]


def list_candidate_rules():
    return [
        {
            "candidate_id": rule.candidate_id,
            "source_ids": list(rule.source_ids),
            "place_aliases": list(rule.place_aliases),
            "date_phrases": list(rule.date_phrases),
            "district_phrases": list(rule.district_phrases),
            "event_phrases": list(rule.event_phrases),
        }
        for rule in CANDIDATE_RULES.values()
    ]
