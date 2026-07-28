#!/usr/bin/env python3
"""Print a compact coverage report for a built database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3


QUERIES = {
    "particles": "SELECT count(*) FROM particle",
    "elements": "SELECT count(*) FROM element",
    "nuclides": "SELECT count(*) FROM nuclide",
    "chemical species": "SELECT count(*) FROM chemical_species",
    "molecular graphs": "SELECT count(*) FROM molecule",
    "materials": "SELECT count(*) FROM material",
    "crystal structures": "SELECT count(*) FROM crystal_structure",
    "mixtures": "SELECT count(*) FROM mixture",
    "reactions": "SELECT count(*) FROM reaction",
    "dissociations": "SELECT count(*) FROM dissociation",
    "spectra": "SELECT count(*) FROM spectrum",
    "spectral points": "SELECT count(*) FROM spectrum_point",
    "nuclear channels": "SELECT count(*) FROM nuclear_channel",
    "cross-section points": "SELECT count(*) FROM nuclear_cross_section_point",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    with sqlite3.connect(arguments.database) as connection:
        for label, query in QUERIES.items():
            count = connection.execute(query).fetchone()[0]
            print(f"{label:24} {count:8d}")
