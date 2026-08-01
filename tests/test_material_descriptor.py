from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_db import build
from scripts.describe_material import FormulaParser, MaterialModel, load_query


class MaterialDescriptorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.db"
        build(cls.database)
        cls.model = MaterialModel.load(cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_formula_parser_handles_groups_and_hydrates(self) -> None:
        parser = FormulaParser({"Al", "Ca", "H", "O", "S"})
        self.assertEqual({"Al": 2, "O": 12, "S": 3}, parser.parse("Al2(SO4)3"))
        self.assertEqual(
            {"Ca": 1, "H": 4, "O": 6, "S": 1},
            parser.parse("CaSO4·2H2O"),
        )

    def test_external_composition_retrieves_reviewed_analogy(self) -> None:
        query = load_query(
            self.database,
            "siliceous iron oxide concentrate",
            ["Fe2O3=0.85", "SiO2=0.15"],
            "mass_fraction",
        )
        result = self.model.describe(query)
        self.assertEqual("unreviewed_material_model_output", result["result_kind"])
        self.assertEqual("ore", result["inference"]["predicted_material_kind"])
        self.assertEqual(
            "material:hematite_ore",
            result["inference"]["neighbors"][0]["material_id"],
        )
        self.assertEqual(64, len(result["model"]["database_sha256"]))
        self.assertIn("not a reviewed identity", result["description"])

    def test_out_of_domain_composition_abstains(self) -> None:
        query = load_query(
            self.database,
            "helium matrix",
            ["He"],
            "unspecified",
        )
        result = self.model.describe(query)
        self.assertEqual("out_of_domain", result["inference"]["applicability"])
        self.assertIsNone(result["inference"]["predicted_material_kind"])
        self.assertEqual(0, result["inference"]["closest_similarity"])

    def test_holdout_benchmark_is_leakage_controlled_and_honest(self) -> None:
        result = self.model.evaluate()
        holdout = result["holdout"]
        self.assertEqual(15, holdout["total"])
        self.assertEqual(1.0, result["sanity_check"]["accuracy"])
        self.assertEqual(
            "the query material is excluded before IDF fitting and neighbor search",
            result["method"]["leakage_control"],
        )
        for row in holdout["rows"]:
            self.assertNotEqual(row["material_id"], row["closest_material_id"])
        self.assertLessEqual(
            holdout["accuracy"], holdout["majority_class_baseline_accuracy"]
        )
        self.assertLess(holdout["macro_recall"], 1.0)

    def test_model_output_is_deterministic(self) -> None:
        query = load_query(
            self.database,
            "test material",
            ["CaCO3", "SiO2"],
            "unspecified",
        )
        first = json.dumps(self.model.describe(query), sort_keys=True)
        second = json.dumps(self.model.describe(query), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
