import unittest

from app.services.evidence.atlas_event_extractor import (
    _extract_candidates,
    _extract_inventory_context,
    _split_pages,
)


class AtlasExtractorTests(unittest.TestCase):
    def test_kedarnath_candidate_keeps_explicit_date_and_state(self):
        text = """--- PAGE 25 ---
        Figure 16. Landslides around Kedarnath, Uttarakhand. During 16-17 June 2013,
        heavy rainfall caused flash floods and a large reactivated landslide.
        """
        pages = _split_pages(text)
        found = _extract_candidates(pages, "a" * 64)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].event_date_start, "2013-06-16")
        self.assertEqual(found[0].event_date_end, "2013-06-17")
        self.assertEqual(found[0].state, "Uttarakhand")
        self.assertIsNone(found[0].district)
        self.assertFalse(found[0].may_be_used_for_model_validation)

    def test_raunthi_candidate_does_not_guess_state_or_district(self):
        text = """--- PAGE 13 ---
        Figure 4. Damage caused by the Raunthi Gad landslide. Rock fall and
        debris flow (7 Feb 2021) was observed in the affected region.
        """
        pages = _split_pages(text)
        found = _extract_candidates(pages, "b" * 64)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].event_date_start, "2021-02-07")
        self.assertIsNone(found[0].state)
        self.assertIsNone(found[0].district)

    def test_aggregate_table_is_not_expanded_to_events(self):
        text = """--- PAGE 19 ---
        Table 2. Landslides inventory database of India. Uttarakhand 1593 455
        1419 / 1998 32 / 2003 11219
        """
        contexts = _extract_inventory_context(_split_pages(text), "c" * 64)
        self.assertEqual(len(contexts), 1)
        self.assertFalse(contexts[0]["individual_events_created"])
        self.assertFalse(contexts[0]["numeric_fields_parsed"])


if __name__ == "__main__":
    unittest.main()
