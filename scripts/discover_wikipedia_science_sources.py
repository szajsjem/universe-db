"""Offline, title-only discovery outside the chemistry archive; never verifies facts."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

if __package__:
    from .wikipedia_dump_lookup import WikipediaDump
else:
    from wikipedia_dump_lookup import WikipediaDump

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "metals_alloys": r"\b(?:alloy|alloys|steel|steels|stainless|inconel|monel|hastelloy|duralumin|brass|bronze|intermetallic|superalloy|metallurgy)\b|^Ti-6Al-4V$",
    "isotopes_nuclear": r"^Isotopes of |\b(?:nuclide|nuclides|isotope|isotopes|nuclear data|atomic mass evaluation|nuclear binding energy|evaluated nuclear|nuclear shell|nuclear mass)\b",
    "ceramics_crystals": r"\b(?:ceramic|ceramics|crystal structure|crystal system|crystallography|perovskite|spinel|wurtzite|carbide|nitride|zirconia|alumina|martensite|austenite|ferrite)\b",
    "physical_properties": r"\b(?:thermal conductivity|thermal diffusivity|heat capacity|electrical resistivity|elastic modulus|bulk modulus|shear modulus|young.s modulus|phase diagram|solid solution|calphad|thermodynamic database)\b",
}
EXCLUDE = re.compile(
    r"\b(?:disambiguation|film|album|song|novel|band|video game|football|basketball|baseball|cricket|rugby|municipality|village|county|township|station|railway|railroad|school|university|institute|company|corporation|software|programming|protocol|magazine|journal|award|medal|surname)\b",
    re.I,
)
PRIORITY = [
    "6061 aluminium alloy",
    "7075 aluminium alloy",
    "Ti-6Al-4V",
    "Inconel",
    "Monel",
    "Stainless steel",
    "Silicon carbide",
    "Silicon nitride",
    "Zirconium dioxide",
    "Aluminium oxide",
    "Wurtzite crystal structure",
    "Heusler alloy",
    "Isotopes of iron",
    "Atomic mass evaluation",
    "Evaluated Nuclear Data File",
    "Thermal diffusivity",
    "CALPHAD",
    "Nuclear Data Sheets",
]
COLLISIONS = re.compile(
    r"\b(?:guitar|instrument|instrumentalists|drums?|pan|bridge|castle|sculpture|"
    r"banner|rat|sky|caves|germs|pact|tariffs|strike|riot|newsreel|corp\.?|"
    r"limited|trust|authority|community|politician|actor|actress|writer|"
    r"singer|musician|cricketer|footballer|athlete|software|computing|"
    r"memory|boot|cent|missile)\b|, (?:New Jersey|Ohio|Pennsylvania|"
    r"New York|Texas)|^(?:Danielle|David|John|James|William|Henry|"
    r"Robert|Richard|Mark|Luc|Lord|Sir|George|Michael|Peter|Paul|"
    r"Thomas|Mary|Jane|Elizabeth)\b|^(?:Caress|Reinventing|Sapphire|"
    r"Albuquerque|Guns|Bethlehem|U\.S\.|US Steel|Union Carbide)\b",
    re.I,
)


def classify(title: str) -> list[str]:
    if ":" in title or EXCLUDE.search(title):
        return []
    return [
        name for name, pattern in PATTERNS.items() if re.search(pattern, title, re.I)
    ]


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def filter_fingerprint(archive_ids: set[int], current_ids: set[int]) -> str:
    """Fingerprint the first pass independently of the optional collision pass."""
    return hashlib.sha256(
        json.dumps(
            {
                "patterns": PATTERNS,
                "exclude": EXCLUDE.pattern,
                "archive_ids": sorted(archive_ids),
                "current_ids": sorted(current_ids),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def collision_filter(result: dict) -> None:
    """Keep original counters; expose separate, idempotent postfilter counters."""
    if "collision_filter_pattern" in result:
        if result["collision_filter_pattern"] != COLLISIONS.pattern:
            raise ValueError("Collision filter changed; rerun full inventory")
        return
    rejected = [p for p in result["matches"] if COLLISIONS.search(p["title"])]
    result["collision_filter_pattern"] = COLLISIONS.pattern
    result["collision_filter_sha256"] = hashlib.sha256(
        COLLISIONS.pattern.encode()
    ).hexdigest()
    result["obvious_collision_titles_excluded"] = rejected
    result["matches"] = [
        p for p in result["matches"] if not COLLISIONS.search(p["title"])
    ]
    result["counts"]["postfilter_matching_entries"] = len(result["matches"])
    result["counts"]["postfilter_new_matching_entries"] = sum(
        not p["in_current_index"] and not p["in_chemistry_archive"]
        for p in result["matches"]
    )
    result["counts"]["obvious_collision_entries_excluded"] = len(rejected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump", type=Path, default=Path("C:/datasets/wikipedia/20260901")
    )
    parser.add_argument(
        "--current-index",
        type=Path,
        default=ROOT / ".build/wikipedia-full-source-index.json",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/wiki-subagents/full-rest.json"
    )
    parser.add_argument("--reuse-inventory", action="store_true")
    parser.add_argument("--read-priority", action="store_true")
    args = parser.parse_args()
    status = json.loads((args.dump / "download-status.json").read_text())
    if status.get("status") != "completed" or not status.get(
        "upstream_checksums_complete"
    ):
        raise ValueError("Require a completed checksum-verified local dump")
    current = json.loads(args.current_index.read_text())["pages"]
    current_ids = set(map(int, current))
    archive = ROOT / "sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip"
    with zipfile.ZipFile(archive) as handle:
        manifest = json.loads(handle.read("manifest.json"))
    archive_ids = {int(p["page_id"]) for p in manifest["pages"]}
    index_info = next(
        f for f in status["files"] if f["name"].endswith("-index.txt.bz2")
    )
    index = args.dump / index_info["name"]
    if index.stat().st_size != index_info["bytes"]:
        raise ValueError("Index size differs from verified download")
    signature = filter_fingerprint(archive_ids, current_ids)
    if args.reuse_inventory:
        result = json.loads(args.output.read_text(encoding="utf-8"))
        if (
            result["filter_sha256"] != signature
            or result["index_sha256"] != index_info["sha256"]
        ):
            raise ValueError("Inventory fingerprint mismatch")
    else:
        counts = Counter()
        matches = []
        result = {
            "status": "scanning",
            "dump_date": status["date"],
            "index_sha256": index_info["sha256"],
            "filter_sha256": signature,
            "discovery_only": True,
            "current_source_page_count": len(current_ids),
            "chemistry_archive_page_count": len(archive_ids),
            "patterns": PATTERNS,
            "exclude_pattern": EXCLUDE.pattern,
        }
        with bz2.open(index, "rt", encoding="utf-8") as handle:
            for line in handle:
                offset, page_id, title = line.rstrip("\n").split(":", 2)
                counts["index_entries"] += 1
                if ":" in title:
                    counts["colon_title_excluded"] += 1
                    continue
                counts["colon_free_entries"] += 1
                topics = classify(title)
                if topics:
                    page_id = int(page_id)
                    known = page_id in current_ids or page_id in archive_ids
                    counts["matching_entries"] += 1
                    counts[
                        "known_matching_entries" if known else "new_matching_entries"
                    ] += 1
                    for topic in topics:
                        counts[topic] += 1
                    matches.append(
                        {
                            "page_id": page_id,
                            "offset": int(offset),
                            "title": title,
                            "topics": topics,
                            "in_current_index": page_id in current_ids,
                            "in_chemistry_archive": page_id in archive_ids,
                        }
                    )
                if counts["index_entries"] % 2_000_000 == 0:
                    result.update(counts=dict(counts), matches=matches)
                    save(args.output, result)
                    print(
                        f"Scanned {counts['index_entries']:,}; {counts['new_matching_entries']:,} new title matches",
                        flush=True,
                    )
        result.update(
            status="inventory_completed", counts=dict(counts), matches=matches
        )
        save(args.output, result)
    # A separate conservative collision pass retains raw counters for audit.
    collision_filter(result)
    save(args.output, result)
    if args.read_priority:
        selected = [
            p
            for p in result["matches"]
            if p["title"] in PRIORITY
            and not p["in_current_index"]
            and not p["in_chemistry_archive"]
        ]
        # Reuse offsets already scanned; the standard reader validates stream/page identity.
        ids = {p["page_id"] for p in selected}
        articles_info = next(
            f for f in status["files"] if f["name"].endswith("-multistream.xml.bz2")
        )
        fingerprint = {
            "articles_sha256": articles_info["sha256"],
            "index_sha256": index_info["sha256"],
            "page_ids_sha256": hashlib.sha256(
                json.dumps(sorted(ids)).encode()
            ).hexdigest(),
        }
        cache = args.output.with_name("full-rest.lookup.json")
        save(
            cache,
            {
                "fingerprint": fingerprint,
                "pages": {
                    p["page_id"]: {"offset": p["offset"], "title": p["title"]}
                    for p in selected
                },
            },
        )
        reader = WikipediaDump(args.dump, ids, cache)
        reads = []
        for p in selected:
            first = reader.read(p["page_id"], "", offset=0)
            sections = [first]
            # Bounded whole text reads of only selected priority pages, capped at 512 KB/article.
            while (
                sections[-1]["next_offset"] < first["document_chars"]
                and len(sections) < 64
            ):
                sections.append(
                    reader.read(p["page_id"], "", offset=sections[-1]["next_offset"])
                )
            content = "".join(s["excerpt"] for s in sections)
            citations = []
            for m in re.finditer(r"https?://[^\s<>|}\]\"']+", content):
                url = m.group().rstrip(".,;")
                if not any(c["url"] == url for c in citations):
                    citations.append(
                        {
                            "url": url,
                            "context": content[max(0, m.start() - 160) : m.end() + 160],
                        }
                    )
            reads.append(
                {
                    **p,
                    "dump_date": reader.date,
                    "revision_id": first["revision_id"],
                    "revision_url": first["source_url"],
                    "document_chars": first["document_chars"],
                    "read_chars": len(content),
                    "redirect": content.lstrip().lower().startswith("#redirect"),
                    "wikitext": content,
                    "citation_leads": citations,
                    "content_verification": "local article read; citations are unverified discovery leads",
                }
            )
            save(
                args.output.with_name("full-rest.reads.json"),
                {
                    "license": "CC-BY-SA-4.0; Wikipedia excerpts/text separate from MIT code",
                    "dump_date": reader.date,
                    "pages": reads,
                },
            )
            print(
                f"Read {p['title']}: {len(content):,} chars, {len(citations)} URL leads",
                flush=True,
            )
        result["priority_pages_read"] = len(reads)
        save(args.output, result)


if __name__ == "__main__":
    main()
