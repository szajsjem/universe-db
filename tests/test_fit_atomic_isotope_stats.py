import unittest

from scripts.fit_atomic_isotope_stats import (
    complete_branches,
    fit_model,
    lifetime_training,
    predict,
)


def row(z, n, value=100, stable=None, kind="point", estimated=False, branches=None):
    return {
        "z": z,
        "n": n,
        "a": z + n,
        "state_index": 0,
        "stability": stable,
        "half_life": {
            "value": {"numerator": str(value), "denominator": "1"},
            "value_kind": kind,
            "estimated": estimated,
        },
        "branches": branches,
        "sources": [],
    }


class AtomicIsotopeStatsTests(unittest.TestCase):
    def test_exclusive_exact_branch_admission(self):
        self.assertIsNotNone(complete_branches("A=25;EC=75", 10, 20))
        for text in [
            "A=25;EC=70",
            "A=100;B+ ?",
            "B-=100;B-n=2",
            "A<100",
            "A=100#",
            "IT=100",
        ]:
            self.assertIsNone(complete_branches(text, 10, 20))
        self.assertIn(
            "beta_plus_or_electron_capture", complete_branches("B+=100", 10, 20)
        )

    def test_source_stable_bounds_and_estimates(self):
        records = [
            row(10, 10, stable="stable"),
            row(10, 11, kind="bound"),
            row(10, 12, estimated=True),
        ]
        self.assertFalse(any(map(lifetime_training, records)))
        model = fit_model(records, validate=False)
        self.assertIsNone(predict(model, 10, 10)["half_life"])
        self.assertEqual(predict(model, 10, 11)["half_life"]["value_kind"], "bound")

    def test_neutral_and_state_identifiability(self):
        model = fit_model([row(10, 10)], validate=False)
        for args in [(10, 10, 9), (10, 10, 10, 1), (True, 10, 1)]:
            with self.assertRaises(ValueError):
                predict(model, *args)
        self.assertEqual(predict(model, 30, 30)["status"], "outside_training_domain")

    def test_local_fit_has_no_self_neighbor_and_unavailable_gamma(self):
        records = [
            row(z, n, 100, branches=complete_branches("A=100", z, z + n))
            for z, n in [(9, 10), (11, 10), (10, 9), (10, 11), (10, 10)]
        ]
        model = fit_model(records, validate=False)
        result = predict(model, 10, 10, use_known=False)
        self.assertAlmostEqual(result["half_life"]["seconds"], 100)
        self.assertAlmostEqual(sum(result["decay_probabilities"].values()), 1)
        self.assertIsNone(result["gamma_probability"])
        self.assertTrue(
            all(
                (r["z"], r["n"]) != (10, 10)
                for r in result["neighbor_trace"]["half_life"]
            )
        )

    def test_known_missing_statistics_preserve_source_reference(self):
        records = [
            row(z, n, branches=complete_branches("A=100", z, z + n))
            for z, n in [(9, 10), (11, 10), (10, 9), (10, 11)]
        ]
        known = row(10, 10, kind="bound")
        records.append(known)
        model = fit_model(records, validate=False)
        result = predict(model, 10, 10, approximate_missing=True)
        self.assertEqual(result["half_life"], known["half_life"])
        self.assertIsNone(result["missing_stat_approximations"]["half_life"])
        self.assertEqual(
            result["missing_stat_approximations"]["decay_probabilities"], {"alpha": 1.0}
        )
        known["stability"] = "stable"
        result = predict(
            fit_model(records, validate=False), 10, 10, approximate_missing=True
        )
        self.assertIsNone(result["half_life"])
        self.assertIsNone(result["missing_stat_approximations"]["half_life"])

    def test_evidence_gate_and_invalid_training_vectors(self):
        with self.assertRaises(ValueError):
            fit_model([row(10, 10)], {"review_status": "pending_human_review"})
        for invalid in [
            row(10, 10, value=0),
            row(10, 10, branches={"alpha": {"numerator": "2", "denominator": "1"}}),
        ]:
            with self.assertRaises(ValueError):
                fit_model([invalid], validate=False)
        self.assertIsNone(complete_branches("B+=50;EC=50", 10, 20))

    def test_holdout_excludes_identities_and_elements(self):
        records = [row(z, n) for z in range(8, 14) for n in range(8, 14)]
        model = fit_model(records)
        for split, report in model["validation"].items():
            self.assertEqual(report["heldout_count"], len(report["heldout_identities"]))
            self.assertNotEqual(
                report["training_records_sha256"], model["records_sha256"]
            )
            if split == "leave_element_out":
                self.assertTrue(
                    all(z % 5 == 0 for z, n in report["heldout_identities"])
                )
        self.assertGreater(
            model["validation"]["coordinate_holdout"]["lifetime_predicted_count"], 0
        )


if __name__ == "__main__":
    unittest.main()
