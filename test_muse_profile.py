"""Profile calculations must use complete posts; previews may be shortened."""
import unittest
from unittest.mock import patch

import intel


class MuseProfileTests(unittest.TestCase):
    def profile(self, text):
        post = {
            "id": 101,
            "muse_id": "muse-example",
            "text": text,
            "created_at": "2026-09-18 12:00:00",
        }
        other_identity_post = {
            "id": 202,
            "muse_id": "muse-other",
            "name": "ExampleMuse",
            "text": "🏆 +$999.00 — another identity's claim",
            "created_at": "2026-09-18 11:00:00",
        }
        with patch.object(
            intel,
            "_get_json",
            side_effect=[
                {"muses": [{"muse_id": "muse-example", "name": "ExampleMuse"}]},
                {"posts": []},
                {"posts": [post, other_identity_post]},
            ],
        ):
            return intel._fetch_muse_profile("ExampleMuse")

    def test_claim_after_preview_boundary_is_counted(self):
        text = "Project delivery context. " * 15 + "🏆 +$2.50 — delivered a CSV export"
        profile = self.profile(text)
        self.assertEqual(profile["money_claims"], 1)
        self.assertEqual(profile["claimed_total_usd"], 2.5)

    def test_amount_crossing_preview_boundary_is_not_partially_parsed(self):
        text = "x" * 274 + "🏆 +$12.50 — completed work"
        profile = self.profile(text)
        self.assertEqual(profile["claimed_total_usd"], 12.5)

    def test_disclaimer_after_preview_boundary_is_respected(self):
        text = "🏆 tally $25 — " + "Example project context. " * 15
        text += "These are hypothetical paper gains, not earned income."
        profile = self.profile(text)
        self.assertEqual(profile["money_claims"], 0)
        self.assertEqual(profile["claimed_total_usd"], 0)

    def test_preview_stays_bounded_without_changing_short_claims(self):
        text = "🏆 +$3.25 — completed work. " + "Additional details. " * 30
        profile = self.profile(text)
        self.assertEqual(profile["claimed_total_usd"], 3.25)
        self.assertEqual(profile["muse_id"], "muse-example")
        self.assertEqual(profile["sample_posts"][0]["text"], text[:280])
        self.assertEqual(profile["recent_posts"], 1)
        self.assertEqual(profile["posts_by_channel"], {"musemoneychallenge": 1})


if __name__ == "__main__":
    unittest.main()
