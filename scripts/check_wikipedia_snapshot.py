#!/usr/bin/env python3
"""Verify the checked-in Wikipedia chemistry snapshot and all page digests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = (
    ROOT
    / "sources"
    / "wikipedia-chemistry-category-snapshot-2026-07-29.zip"
)
EXPECTED_SHA256 = (
    "c1b4db37964c497f901343c706019324eac204af2973b9aaff71c24f781cdf29"
)
EXPECTED_PAGE_COUNT = 1239
EXPECTED_FORMAT = "universe-db-wikipedia-category-snapshot-v1"
KIWIX_ARCHIVE = ROOT / "sources" / "wikipedia_en_chemistry_mini_2026-07.zim"
KIWIX_SHA256 = (
    "0a7f1e35b1f0deee19c68014421754ce42310bcf6cd8e8d3f01fad25a5ab6144"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    kiwix_digest = sha256(KIWIX_ARCHIVE.read_bytes())
    if kiwix_digest != KIWIX_SHA256:
        raise SystemExit(
            f"{KIWIX_ARCHIVE.name}: expected sha256 {KIWIX_SHA256}, "
            f"got {kiwix_digest}"
        )

    archive_raw = ARCHIVE.read_bytes()
    actual_digest = sha256(archive_raw)
    if actual_digest != EXPECTED_SHA256:
        raise SystemExit(
            f"{ARCHIVE.name}: expected sha256 {EXPECTED_SHA256}, "
            f"got {actual_digest}"
        )

    with zipfile.ZipFile(ARCHIVE) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("archive_format") != EXPECTED_FORMAT:
            raise SystemExit("Wikipedia archive format mismatch")
        if manifest.get("page_count") != EXPECTED_PAGE_COUNT:
            raise SystemExit("Wikipedia archive page count mismatch")
        if len(manifest.get("pages", [])) != EXPECTED_PAGE_COUNT:
            raise SystemExit("Wikipedia manifest entry count mismatch")
        if manifest.get("license", {}).get("spdx_id") != "CC-BY-SA-4.0":
            raise SystemExit("Wikipedia archive license metadata mismatch")

        expected_names = {"manifest.json"}
        for page in manifest["pages"]:
            filename = page["filename"]
            expected_names.add(filename)
            raw = archive.read(filename)
            if sha256(raw) != page["content_sha256"]:
                raise SystemExit(f"{filename}: content digest mismatch")
            payload = json.loads(raw)
            if (
                payload.get("page_id") != page["page_id"]
                or payload.get("revision_id") != page["revision_id"]
                or payload.get("revision_url") != page["revision_url"]
            ):
                raise SystemExit(f"{filename}: revision identity mismatch")

        if set(archive.namelist()) != expected_names:
            raise SystemExit("Wikipedia archive contains unmanifested entries")

    print(
        f"{ARCHIVE.name}: {EXPECTED_PAGE_COUNT} revision-pinned pages, "
        f"sha256 {actual_digest}"
    )
    print(f"{KIWIX_ARCHIVE.name}: upstream Kiwix release, sha256 {kiwix_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
