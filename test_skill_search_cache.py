"""Regression coverage for query-specific search caching; no paid calls."""
import unittest
from unittest.mock import patch

import intel


CATALOG = {
    "items": [
        {"slug": "alpha", "name": "Alpha", "description": "First tool"},
        {"slug": "beta", "name": "Beta", "description": "Second tool"},
    ]
}


class SkillSearchCacheTests(unittest.TestCase):
    def setUp(self):
        intel._cache.clear()
        patcher = patch.object(intel, "_get_json", return_value=CATALOG)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(intel._cache.clear)

    def test_distinct_queries_sharing_a_long_prefix_have_separate_results(self):
        prefix = "zzzz " * 12
        first = intel.get_skill_search(prefix + "alpha")
        second = intel.get_skill_search(prefix + "beta")
        first_again = intel.get_skill_search(prefix + "alpha")
        self.assertEqual([item["slug"] for item in first], ["alpha"])
        self.assertEqual([item["slug"] for item in second], ["beta"])
        self.assertEqual(first_again, first)
        self.assertEqual(self.fetch.call_count, 2)

    def test_case_and_outer_whitespace_share_a_cache_entry(self):
        first = intel.get_skill_search("  ALPHA  ")
        second = intel.get_skill_search("alpha")
        self.assertEqual([item["slug"] for item in first], ["alpha"])
        self.assertEqual(second, first)
        self.fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
