
import unittest

from app.services.evidence.corroboration_engine import _match_one_candidate
from app.services.evidence.corroboration_registry import SOURCES


def make_source(source_id, text):
    spec = SOURCES[source_id]
    return {
        "source_id": source_id,
        "source_name": spec.source_name,
        "publisher": spec.publisher,
        "publication_date": spec.publication_date,
        "url": spec.url,
        "final_url": spec.url,
        "sha256": "test-sha256",
        "cached": True,
        "independence_note": spec.independence_note,
        "evidence_role": spec.evidence_role,
        "text_characters": len(text),
        "pages": [{"page_number": 1, "text": text}],
    }


class CorroborationEngineTests(unittest.TestCase):

    def test_raunthi_matches_official_gsi_reference(self):
        text = (
            "On February 7, 2021, a flash flood event occurred in the "
            "Rishiganga and Dhauliganga valleys of Chamoli district, Uttarakhand. "
            "The event was initiated by a snow ice rock mass avalanche from "
            "the left valley wall of Raunthi Garh and generated a huge debris flow."
        )

        result = _match_one_candidate(
            "nrsc_atlas_raunthi_gad_2021",
            make_source("pib_gsi_chamoli_2021", text),
        )

        self.assertEqual(result["match_status"], "strong_reference_match")
        self.assertTrue(result["matching_signals"]["place_match"])
        self.assertTrue(result["matching_signals"]["date_match"])
        self.assertTrue(result["matching_signals"]["district_match"])
        self.assertTrue(result["matching_signals"]["event_context_match"])
        self.assertTrue(result["matching_signals"]["specific_claim_complete"])

    def test_kedarnath_is_partial_without_artificial_embankment_detail(self):
        text = (
            "The impact was most pronounced in the Mandakini valley of the "
            "Rudraprayag district. Flooding affected Kedarnath Shrine. "
            "The events occurred on 16 June 2013 and 17 June 2013. "
            "Toe erosion triggered landslides at a number of places."
        )

        result = _match_one_candidate(
            "nrsc_atlas_kedarnath_2013",
            make_source("nidm_india_disaster_report_2013", text),
        )

        self.assertEqual(result["match_status"], "partial_context_match")
        self.assertTrue(result["matching_signals"]["place_match"])
        self.assertTrue(result["matching_signals"]["date_match"])
        self.assertTrue(result["matching_signals"]["district_match"])
        self.assertTrue(result["matching_signals"]["event_context_match"])
        self.assertFalse(result["matching_signals"]["specific_claim_complete"])

    def test_unrelated_text_does_not_match(self):
        text = (
            "This annual report discusses general weather patterns in another region."
        )

        result = _match_one_candidate(
            "nrsc_atlas_raunthi_gad_2021",
            make_source("pib_gsi_chamoli_2021", text),
        )

        self.assertEqual(result["match_status"], "no_match")

    def test_kedarnath_requires_both_date_endpoints(self):
        text = (
            "Kedarnath Shrine, Rudraprayag district, experienced flash floods "
            "and landslides on 16 June 2013."
        )

        result = _match_one_candidate(
            "nrsc_atlas_kedarnath_2013",
            make_source("nidm_india_disaster_report_2013", text),
        )

        self.assertFalse(result["matching_signals"]["date_match"])
        self.assertEqual(result["match_status"], "no_match")

    def test_pib_culture_is_context_only_not_specific_claim_evidence(self):
        text = (
            "Kedarnath Shrine was affected by flash floods "
            "on 16 June 2013 and 17 June 2013. "
            "Restoration work included removal of debris."
        )

        result = _match_one_candidate(
            "nrsc_atlas_kedarnath_2013",
            make_source("pib_culture_kedarnath_2013", text),
        )

        self.assertEqual(result["evidence_role"], "context_only")
        self.assertEqual(result["match_status"], "context_only_match")
        self.assertTrue(result["matching_signals"]["place_match"])
        self.assertTrue(result["matching_signals"]["date_match"])
        self.assertTrue(result["matching_signals"]["event_context_match"])
        self.assertFalse(result["matching_signals"]["specific_claim_complete"])


if __name__ == "__main__":
    unittest.main()
