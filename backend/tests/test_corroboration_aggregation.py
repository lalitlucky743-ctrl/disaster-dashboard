import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.evidence import corroboration_engine as engine


class TestCorroborationAggregation(unittest.TestCase):

    candidate_id = "nrsc_atlas_kedarnath_2013"

    def setUp(self):
        rule = engine.CANDIDATE_RULES[self.candidate_id]

        self.source_roles = {
            source_id: engine.SOURCES[source_id].evidence_role
            for source_id in rule.source_ids
        }

        self.claim_source_ids = [
            source_id
            for source_id, role in self.source_roles.items()
            if role == "claim_check"
        ]

        self.context_source_ids = [
            source_id
            for source_id, role in self.source_roles.items()
            if role == "context_only"
        ]

        self.assertTrue(self.claim_source_ids)
        self.assertTrue(self.context_source_ids)

    def make_evidence(self, source_id, mode):
        role = self.source_roles[source_id]

        if role == "context_only":
            return {
                "source_id": source_id,
                "evidence_role": role,
                "match_status": (
                    "context_only_match"
                    if mode != "no_context"
                    else "no_match"
                ),
                "matching_signals": {
                    "place_match": mode != "no_match",
                    "date_match": mode != "no_match",
                    "district_match": False,
                    "event_context_match": mode != "no_match",
                    "specific_claim_complete": False,
                },
            }

        if mode in ("no_match", "context_only"):
            return {
                "source_id": source_id,
                "evidence_role": role,
                "match_status": "no_match",
                "matching_signals": {
                    "place_match": False,
                    "date_match": False,
                    "district_match": False,
                    "event_context_match": False,
                    "specific_claim_complete": False,
                },
            }

        strong = mode == "strong"

        return {
            "source_id": source_id,
            "evidence_role": role,
            "match_status": (
                "strong_reference_match"
                if strong
                else "partial_context_match"
            ),
            "matching_signals": {
                "place_match": True,
                "date_match": True,
                "district_match": True,
                "event_context_match": True,
                "specific_claim_complete": strong,
            },
        }

    def run_aggregation(self, mode):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_path = temp / "phase3_input.json"
            output_path = temp / "corroboration_output.json"

            input_path.write_text(
                json.dumps({
                    "candidates": [{
                        "candidate_id": self.candidate_id,
                        "event_name": "Kedarnath 2013",
                    }]
                }),
                encoding="utf-8",
            )

            def fake_fetch(source_id, refresh=False):
                return {"source_id": source_id}

            def fake_match(candidate_id, source_data):
                return self.make_evidence(
                    source_data["source_id"],
                    mode,
                )

            with (
                patch.object(
                    engine,
                    "fetch_and_extract_source",
                    side_effect=fake_fetch,
                ),
                patch.object(
                    engine,
                    "_match_one_candidate",
                    side_effect=fake_match,
                ),
            ):
                summary, result = engine.corroborate_candidates(
                    input_path=input_path,
                    output_path=output_path,
                )

            self.assertTrue(output_path.exists())

            saved_result = json.loads(
                output_path.read_text(encoding="utf-8")
            )

            self.assertEqual(
                saved_result["candidate_count"],
                1,
            )

            return summary, result

    def test_context_only_is_excluded_from_claim_check_count(self):
        summary, result = self.run_aggregation("partial")

        candidate = result["candidates"][0]

        self.assertEqual(
            candidate["matching_claim_check_source_count"],
            len(self.claim_source_ids),
        )
        self.assertEqual(
            candidate["matching_official_source_count"],
            len(self.claim_source_ids),
        )
        self.assertEqual(
            candidate["matching_context_only_source_count"],
            len(self.context_source_ids),
        )
        self.assertEqual(
            candidate["matching_specific_claim_source_count"],
            0,
        )

        self.assertEqual(
            candidate["corroboration_status"],
            "single_source_partial_context_match",
        )

        self.assertEqual(
            summary["candidate_statuses"][0][
                "matching_context_only_source_count"
            ],
            len(self.context_source_ids),
        )

    def test_context_only_alone_never_counts_as_claim_evidence(self):
        summary, result = self.run_aggregation("context_only")

        candidate = result["candidates"][0]

        self.assertEqual(
            candidate["matching_claim_check_source_count"],
            0,
        )
        self.assertEqual(
            candidate["matching_official_source_count"],
            0,
        )
        self.assertEqual(
            candidate["matching_specific_claim_source_count"],
            0,
        )
        self.assertEqual(
            candidate["matching_context_only_source_count"],
            len(self.context_source_ids),
        )

        self.assertEqual(
            candidate["corroboration_status"],
            "context_only_documentary_context_match",
        )

    def test_specific_claim_count_requires_complete_strong_match(self):
        summary, result = self.run_aggregation("strong")

        candidate = result["candidates"][0]

        self.assertEqual(
            candidate["matching_claim_check_source_count"],
            len(self.claim_source_ids),
        )
        self.assertEqual(
            candidate["matching_specific_claim_source_count"],
            len(self.claim_source_ids),
        )

        self.assertEqual(
            candidate["matching_context_only_source_count"],
            len(self.context_source_ids),
        )

        self.assertEqual(
            candidate["corroboration_status"],
            "single_source_strong_reference_match",
        )

    def test_no_result_can_be_promoted_to_verified_or_model_validation(self):
        _, result = self.run_aggregation("strong")

        candidate = result["candidates"][0]

        self.assertEqual(
            candidate["verification_status"],
            "not_verified",
        )
        self.assertFalse(
            candidate["specific_sub_event_claim_verified"]
        )
        self.assertFalse(
            candidate["may_be_used_for_model_validation"]
        )
        self.assertEqual(
            candidate["model_accuracy"],
            "not_evaluated",
        )
        self.assertEqual(
            candidate["review_status"],
            "needs_human_review",
        )

        self.assertFalse(
            result["eligible_for_training_or_model_validation"]
        )
        self.assertEqual(
            result["verification_status"],
            "not_verified",
        )
        self.assertEqual(
            result["model_accuracy"],
            "not_evaluated",
        )


if __name__ == "__main__":
    unittest.main()
