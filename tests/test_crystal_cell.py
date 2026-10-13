import copy
import unittest
from fractions import Fraction
from pathlib import Path

from scripts.crystal_cell import (
    apply_operation,
    audit_database,
    audit_structure,
    cif_operations,
    parse_operation,
)


def sample():
    return {
        "id": "fcc-cu",
        "formula": "Cu",
        "cell_formula_units": 4,
        "site_convention": "asymmetric_unit",
        "temperature_k": "293",
        "symmetry_operations": [
            "x,y,z",
            "x,1/2+y,1/2+z",
            "1/2+x,y,1/2+z",
            "1/2+x,1/2+y,z",
        ],
        "sites": [
            {
                "label": "Cu",
                "element": "Cu",
                "x": "0",
                "y": "0",
                "z": "0",
                "occupancy": "1",
                "multiplicity": 4,
            }
        ],
        "lattice_parameters": {
            key: {
                "value": "4" if key in "abc" else "90",
                "unit": "angstrom" if key in "abc" else "deg",
            }
            for key in ("a", "b", "c", "alpha", "beta", "gamma")
        },
    }


class CrystalCellTests(unittest.TestCase):
    def test_exact_wrap_and_parser_guards(self):
        self.assertEqual(
            apply_operation(
                parse_operation("1/2-x,y-x,-z"),
                (Fraction(3, 4), Fraction(0), Fraction(-1)),
            ),
            (Fraction(3, 4), Fraction(1, 4), Fraction(0)),
        )
        for operation in (
            "__import__('os'),y,z",
            "x*x,y,z",
            "x/2,y,z",
            "2x,y,z",
            "x,y",
            "x,y,0",
            "x+1/0,y,z",
        ):
            with self.assertRaises((ValueError, ZeroDivisionError)):
                parse_operation(operation)

    def test_conservation_and_density(self):
        row = audit_structure(
            sample(), masses={"Cu": {"value": "63.546", "source": "test reference"}}
        )
        self.assertEqual(row["cell_composition"], {"Cu": "4"})
        self.assertTrue(row["formula_z_matches"])
        self.assertEqual(len(row["expanded_sites"]), 4)
        self.assertAlmostEqual(row["density"]["value"], 6.595038479599395, places=8)
        self.assertEqual(row["density"]["provenance_class"], "modeled")
        self.assertEqual(row["review_status"], "pending_human_review")

    def test_unknowns_and_conflicts_block_density(self):
        structure = sample()
        structure["sites"][0]["occupancy"] = None
        result = audit_structure(structure)
        self.assertIsNone(result["cell_composition"])
        self.assertIsNone(result["density"])
        structure = sample()
        structure["cell_formula_units"] = 2
        result = audit_structure(
            structure, masses={"Cu": {"value": "63", "source": "ref"}}
        )
        self.assertFalse(result["formula_z_matches"])
        self.assertIsNone(result["density"])
        structure = sample()
        structure["sites"].append(copy.deepcopy(structure["sites"][0]))
        result = audit_structure(structure)
        self.assertTrue(
            any("occupancy exceeds" in conflict for conflict in result["conflicts"])
        )

    def test_isotope_masses_are_not_mass_numbers(self):
        structure = sample()
        structure.update(formula="D", cell_formula_units=4)
        structure["sites"][0].update(element="H", isotope_mass_number=2)
        result = audit_structure(
            structure, masses={"H": {"value": "1", "source": "ref"}}
        )
        self.assertEqual(result["cell_composition"], {"H-2": "4"})
        self.assertTrue(result["formula_z_matches"])
        self.assertIsNone(result["density"])
        result = audit_structure(
            structure, masses={"H-2": {"value": "2.014", "source": "isotope reference"}}
        )
        self.assertIsNotNone(result["density"])
        self.assertEqual(result["density"]["mass_inputs"]["H-2"]["value"], "2.014")

    def test_heavy_water_formula_requires_deuterium(self):
        row = sample()
        row.update(formula="D2O", cell_formula_units=1, site_convention="full_cell")
        row["sites"] = [
            {
                "label": "D1",
                "element": "H",
                "isotope_mass_number": 2,
                "x": "0",
                "y": "0",
                "z": "0",
                "occupancy": "1",
            },
            {
                "label": "D2",
                "element": "H",
                "isotope_mass_number": 2,
                "x": "1/4",
                "y": "0",
                "z": "0",
                "occupancy": "1",
            },
            {
                "label": "O",
                "element": "O",
                "x": "1/2",
                "y": "0",
                "z": "0",
                "occupancy": "1",
            },
        ]
        self.assertTrue(audit_structure(row)["formula_z_matches"])
        row["sites"][0]["isotope_mass_number"] = 1
        self.assertFalse(audit_structure(row)["formula_z_matches"])

    def test_cif_loop_and_missing_operations(self):
        self.assertEqual(
            cif_operations(
                "loop_\n_space_group_symop_id\n_space_group_symop_operation_xyz\n1 'x,y,z'\n2 '-x,-y,-z'\n_cell_length_a 4"
            ),
            ["x,y,z", "-x,-y,-z"],
        )
        row = sample()
        row.pop("symmetry_operations")
        self.assertIsNone(audit_structure(row)["cell_composition"])

    def test_repository_audit_deterministic_read_only(self):
        path = Path(__file__).resolve().parents[1] / "crystals.db"
        if not path.exists():
            self.skipTest("optional crystal evidence not built")
        before = path.read_bytes()
        first = audit_database(path)
        self.assertEqual(first, audit_database(path))
        self.assertEqual(before, path.read_bytes())
        self.assertGreater(first["summary"]["structures"], 0)


if __name__ == "__main__":
    unittest.main()
