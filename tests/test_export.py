from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.export_inorganicengineering import (
    DEFAULT_DATABASE,
    DEFAULT_PROFILE,
    build_files,
    export,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InorganicEngineeringExportTest(unittest.TestCase):
    def test_export_is_byte_for_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            export(DEFAULT_DATABASE, DEFAULT_PROFILE, first)
            export(DEFAULT_DATABASE, DEFAULT_PROFILE, second)
            self.assertEqual(digest(first), digest(second))

    def test_export_has_complete_bootstrap_families(self) -> None:
        files = build_files(DEFAULT_DATABASE, DEFAULT_PROFILE)
        paths = set(files)
        self.assertEqual(59, len(paths))
        self.assertEqual(
            16,
            sum("/elements/" in path for path in paths),
        )
        self.assertEqual(
            25,
            sum("/species/" in path for path in paths),
        )
        self.assertEqual(
            12,
            sum("/minerals/" in path for path in paths),
        )
        self.assertEqual(
            1,
            sum("/materials/" in path for path in paths),
        )
        self.assertEqual(
            3,
            sum("/recipe/" in path for path in paths),
        )

    def test_manifest_authenticates_every_payload_file(self) -> None:
        files = build_files(DEFAULT_DATABASE, DEFAULT_PROFILE)
        manifest = json.loads(files["universe-db-export.json"])
        authenticated = manifest["files"]
        self.assertEqual(set(files) - {"universe-db-export.json"}, set(authenticated))
        for path, expected in authenticated.items():
            self.assertEqual(hashlib.sha256(files[path]).hexdigest(), expected)
        self.assertEqual(digest(DEFAULT_DATABASE), manifest["source_database_sha256"])
        self.assertEqual(digest(DEFAULT_PROFILE), manifest["profile_sha256"])

    def test_exported_contract_is_explicit_and_exact(self) -> None:
        files = build_files(DEFAULT_DATABASE, DEFAULT_PROFILE)
        pack = json.loads(files["pack.mcmeta"])
        self.assertEqual(48, pack["pack"]["pack_format"])

        copper = json.loads(
            files[
                "data/inorganicengineering/inorganicengineering/"
                "elements/copper.json"
            ]
        )
        self.assertEqual(63_546_000, copper["atomic_mass_micrograms_per_mole"])

        cathode = json.loads(
            files[
                "data/inorganicengineering/inorganicengineering/"
                "materials/cathode_copper.json"
            ]
        )
        self.assertEqual(
            {"inorganicengineering:copper": 1_000_000},
            cathode["composition_parts_per_million"],
        )

        roasting = json.loads(
            files[
                "data/inorganicengineering/recipe/"
                "thermal_processing/chalcopyrite_roasting.json"
            ]
        )
        self.assertEqual(1, roasting["schema_version"])
        self.assertEqual("inorganicengineering:thermal_processing", roasting["type"])
        self.assertEqual(
            [4, 13],
            [row["micromoles"] for row in roasting["definition"]["inputs"]],
        )

    def test_zip_uses_stable_metadata_and_uncompressed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "export.zip"
            export(DEFAULT_DATABASE, DEFAULT_PROFILE, output)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(sorted(names), names)
                self.assertTrue(names)
                for info in archive.infolist():
                    self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
                    self.assertEqual(zipfile.ZIP_STORED, info.compress_type)


if __name__ == "__main__":
    unittest.main()
