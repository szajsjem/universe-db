import copy
import unittest

from scripts.discover_wikipedia_science_sources import (
    classify,
    collision_filter,
    filter_fingerprint,
)


class WikipediaScienceDiscoveryTests(unittest.TestCase):
    def test_title_topics_and_namespace_exclusions(self):
        self.assertEqual(classify("Isotopes of iron"), ["isotopes_nuclear"])
        self.assertIn("metals_alloys", classify("6061 aluminium alloy"))
        self.assertIn("ceramics_crystals", classify("Silicon nitride"))
        self.assertEqual(classify("Talk:Silicon nitride"), [])
        self.assertEqual(classify("Steel (film)"), [])
        self.assertEqual(classify("Unrelated title"), [])

    def test_fingerprint_is_order_independent_and_tracks_source_sets(self):
        self.assertEqual(
            filter_fingerprint({1, 2}, {3, 4}),
            filter_fingerprint({2, 1}, {4, 3}),
        )
        self.assertNotEqual(
            filter_fingerprint({1, 2}, {3, 4}),
            filter_fingerprint({1, 2}, {3, 5}),
        )
        self.assertNotEqual(filter_fingerprint({1}, {2}), filter_fingerprint({2}, {1}))

    def test_collision_pass_preserves_raw_counts_and_known_membership(self):
        def page(title, known=False):
            return {
                "title": title,
                "in_current_index": known,
                "in_chemistry_archive": False,
            }

        result = {
            "matches": [
                page("Steel guitar"),
                page("Silicon nitride"),
                page("Isotopes of iron", True),
            ],
            "counts": {"matching_entries": 3, "new_matching_entries": 2},
        }
        collision_filter(result)
        self.assertEqual(result["counts"]["matching_entries"], 3)
        self.assertEqual(result["counts"]["postfilter_matching_entries"], 2)
        self.assertEqual(result["counts"]["postfilter_new_matching_entries"], 1)
        self.assertEqual(result["counts"]["obvious_collision_entries_excluded"], 1)
        snapshot = copy.deepcopy(result)
        collision_filter(result)
        self.assertEqual(result, snapshot)

    def test_collision_pattern_change_invalidates_reuse(self):
        with self.assertRaisesRegex(ValueError, "Collision filter changed"):
            collision_filter({"collision_filter_pattern": "stale"})


if __name__ == "__main__":
    unittest.main()
