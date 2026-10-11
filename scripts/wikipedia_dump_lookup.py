"""Bounded random access to selected pages in a verified multistream dump."""

from __future__ import annotations

import bz2
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


class WikipediaDump:
    def __init__(self, directory: Path, page_ids: set[int], cache: Path):
        status = json.loads((directory / "download-status.json").read_text())
        if status.get("status") != "completed" or not status.get(
            "upstream_checksums_complete"
        ):
            raise ValueError(
                "Full Wikipedia dump must have completed upstream checksum verification"
            )
        articles = next(
            item
            for item in status["files"]
            if item["name"].endswith("-multistream.xml.bz2")
        )
        index = next(
            item
            for item in status["files"]
            if item["name"].endswith("-multistream-index.txt.bz2")
        )
        self.articles = directory / articles["name"]
        self.index = directory / index["name"]
        for path, item in ((self.articles, articles), (self.index, index)):
            if path.stat().st_size != item["bytes"]:
                raise ValueError(f"Verified dump file has changed size: {path}")
        self.date = status["date"]
        self.fingerprint = {
            "articles_sha256": articles["sha256"],
            "index_sha256": index["sha256"],
            "page_ids_sha256": hashlib.sha256(
                json.dumps(sorted(page_ids)).encode()
            ).hexdigest(),
        }
        if cache.exists():
            stored = json.loads(cache.read_text())
            if stored.get("fingerprint") == self.fingerprint:
                self.pages = {int(key): value for key, value in stored["pages"].items()}
                print(
                    f"Full Wikipedia lookup: {len(self.pages)}/{len(page_ids)} source pages indexed (cached)",
                    flush=True,
                )
                return
        self.pages = {}
        print(
            f"Indexing {len(page_ids)} source page IDs in full Wikipedia dump {self.date}",
            flush=True,
        )
        with bz2.open(self.index, "rt", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                offset, page_id, title = line.rstrip("\n").split(":", 2)
                page_id = int(page_id)
                if page_id in page_ids:
                    self.pages[page_id] = {"offset": int(offset), "title": title}
                if number % 2_000_000 == 0:
                    print(
                        f"  indexed {number:,} entries; found {len(self.pages)} source pages",
                        flush=True,
                    )
        cache.parent.mkdir(parents=True, exist_ok=True)
        staged = cache.with_suffix(".tmp")
        staged.write_text(
            json.dumps({"fingerprint": self.fingerprint, "pages": self.pages}),
            encoding="utf-8",
        )
        staged.replace(cache)
        print(
            f"Full Wikipedia lookup: {len(self.pages)}/{len(page_ids)} source pages indexed",
            flush=True,
        )

    def read(self, page_id: int, query: str, offset: int | None = None) -> dict:
        entry = self.pages.get(page_id)
        if entry is None:
            return {
                "found": False,
                "page_id": page_id,
                "dump_date": self.date,
                "reason": "Source page ID is absent from the downloaded article index",
            }
        decompressor = bz2.BZ2Decompressor()
        parts = []
        expanded = 0
        with self.articles.open("rb") as handle:
            handle.seek(entry["offset"])
            for _ in range(256):
                block = handle.read(64 * 1024)
                if not block:
                    break
                decoded = decompressor.decompress(
                    block, max_length=64 * 1024 * 1024 - expanded + 1
                )
                parts.append(decoded)
                expanded += len(decoded)
                if expanded > 64 * 1024 * 1024:
                    raise ValueError(
                        "Wikipedia multistream block exceeds bounded lookup size"
                    )
                if decompressor.eof:
                    break
            if not decompressor.eof:
                raise ValueError(
                    "Wikipedia multistream block is truncated or exceeds bounded lookup size"
                )
        document = b"".join(parts).decode("utf-8")
        for match in re.finditer(r"<page>.*?</page>", document, re.DOTALL):
            page = ET.fromstring(match.group())
            if page.findtext("id") != str(page_id):
                continue
            revision = page.find("revision")
            if revision is None:
                raise ValueError("Wikipedia page has no revision")
            text = revision.findtext("text") or ""
            if offset is None:
                terms = [
                    term.casefold()
                    for term in re.findall(r"\w+", query)
                    if len(term) > 1
                ]
                positions = [text.casefold().find(term) for term in terms]
                positions = [position for position in positions if position >= 0]
                offset = max(0, min(positions) - 500) if positions else 0
            if not 0 <= offset <= len(text):
                raise ValueError("Excerpt offset is outside the page")
            revision_id = revision.findtext("id")
            return {
                "found": True,
                "title": page.findtext("title"),
                "page_id": page_id,
                "revision_id": revision_id,
                "dump_date": self.date,
                "dump_sha256": self.fingerprint["articles_sha256"],
                "source_url": "https://en.wikipedia.org/w/index.php?oldid="
                + str(revision_id),
                "excerpt_start": offset,
                "excerpt": text[offset : offset + 8000],
                "document_chars": len(text),
                "next_offset": min(len(text), offset + 8000),
            }
        raise ValueError("Indexed page was not found in its compressed stream")
