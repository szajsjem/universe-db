#!/usr/bin/env python3
"""Create a bounded, revision-pinned Wikipedia chemistry source ZIP.

The complete English Wikipedia article dump is larger than this repository is
intended to vendor. This downloader instead walks selected scientific
categories, fetches current wikitext revisions through the MediaWiki Action
API, and writes a self-describing ZIP suitable for sequential parsing.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_ROOTS = (
    "Category:Chemical elements",
    "Category:Isotopes",
    "Category:Chemical compounds",
    "Category:Chemical reactions",
    "Category:Nuclear physics",
    "Category:Spectroscopy",
    "Category:Materials science",
)
USER_AGENT = (
    "universe-db-wikipedia-snapshot/1.0 "
    "(https://github.com/szajsjem/universe-db; scientific data staging)"
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def api_get(
    parameters: dict[str, str],
    *,
    retries: int,
    timeout: int,
    delay: float,
) -> dict:
    query = {
        "format": "json",
        "formatversion": "2",
        "maxlag": "5",
        **parameters,
    }
    url = API_URL + "?" + urllib.parse.urlencode(query)
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
            if "error" in payload:
                code = payload["error"].get("code", "unknown")
                if code == "maxlag" and attempt < retries:
                    time.sleep(min(2**attempt, 30))
                    continue
                raise RuntimeError(f"MediaWiki API error {code}: {payload['error']}")
            if delay:
                time.sleep(delay)
            return payload
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == retries:
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"MediaWiki API HTTP {error.code}: {detail}"
                ) from error
        except urllib.error.URLError as error:
            if attempt == retries:
                raise RuntimeError(f"MediaWiki API request failed: {error}") from error
        time.sleep(min(2**attempt, 30))
    raise AssertionError("unreachable")


def category_members(
    category: str,
    *,
    retries: int,
    timeout: int,
    delay: float,
) -> list[dict]:
    members: list[dict] = []
    continuation: str | None = None
    while True:
        parameters = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "page|subcat",
            "cmprop": "ids|title|type",
            "cmlimit": "500",
        }
        if continuation:
            parameters["cmcontinue"] = continuation
        payload = api_get(
            parameters,
            retries=retries,
            timeout=timeout,
            delay=delay,
        )
        members.extend(payload.get("query", {}).get("categorymembers", []))
        continuation = payload.get("continue", {}).get("cmcontinue")
        if continuation is None:
            return members


def discover_pages(
    roots: tuple[str, ...],
    *,
    max_depth: int,
    per_root: int,
    max_pages: int,
    retries: int,
    timeout: int,
    delay: float,
) -> dict[int, dict]:
    discovered: dict[int, dict] = {}
    for root in roots:
        root_pages = 0
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        visited_categories: set[str] = set()
        while queue and root_pages < per_root and len(discovered) < max_pages:
            category, depth = queue.popleft()
            if category in visited_categories:
                continue
            visited_categories.add(category)
            print(f"discover {root}: {category} (depth {depth})", flush=True)
            members = category_members(
                category,
                retries=retries,
                timeout=timeout,
                delay=delay,
            )
            pages = sorted(
                (member for member in members if member.get("type") == "page"),
                key=lambda member: (member["title"].casefold(), member["pageid"]),
            )
            for member in pages:
                page_id = int(member["pageid"])
                record = discovered.setdefault(
                    page_id,
                    {
                        "page_id": page_id,
                        "title": member["title"],
                        "roots": set(),
                        "discovered_in": set(),
                    },
                )
                if root not in record["roots"]:
                    record["roots"].add(root)
                    root_pages += 1
                record["discovered_in"].add(category)
                if root_pages >= per_root or len(discovered) >= max_pages:
                    break
            if depth >= max_depth:
                continue
            subcategories = sorted(
                (
                    member["title"]
                    for member in members
                    if member.get("type") == "subcat"
                ),
                key=str.casefold,
            )
            queue.extend((subcategory, depth + 1) for subcategory in subcategories)
    return discovered


def chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch_pages(
    discovered: dict[int, dict],
    *,
    retries: int,
    timeout: int,
    delay: float,
) -> list[dict]:
    pages: list[dict] = []
    ordered_ids = [
        row["page_id"]
        for row in sorted(
            discovered.values(),
            key=lambda row: (row["title"].casefold(), row["page_id"]),
        )
    ]
    for batch_index, page_ids in enumerate(chunks(ordered_ids, 20), start=1):
        print(
            f"fetch revisions {batch_index}/{(len(ordered_ids) + 19) // 20}",
            flush=True,
        )
        payload = api_get(
            {
                "action": "query",
                "prop": "info|revisions",
                "pageids": "|".join(str(value) for value in page_ids),
                "inprop": "url",
                "rvprop": "ids|timestamp|sha1|content",
                "rvslots": "main",
            },
            retries=retries,
            timeout=timeout,
            delay=delay,
        )
        by_id = {
            int(page["pageid"]): page
            for page in payload.get("query", {}).get("pages", [])
            if "pageid" in page and "missing" not in page
        }
        for page_id in page_ids:
            source = by_id.get(page_id)
            if not source or not source.get("revisions"):
                continue
            revision = source["revisions"][0]
            content = revision.get("slots", {}).get("main", {}).get("content")
            if content is None:
                continue
            discovery = discovered[page_id]
            pages.append(
                {
                    "canonical_url": source.get(
                        "canonicalurl",
                        "https://en.wikipedia.org/?curid=" + str(page_id),
                    ),
                    "content_model": revision.get("slots", {})
                    .get("main", {})
                    .get("contentmodel"),
                    "discovered_in": sorted(discovery["discovered_in"]),
                    "page_id": page_id,
                    "parent_revision_id": revision.get("parentid"),
                    "revision_id": int(revision["revid"]),
                    "revision_sha1": revision.get("sha1"),
                    "revision_timestamp": revision["timestamp"],
                    "revision_url": (
                        "https://en.wikipedia.org/w/index.php?oldid="
                        + str(revision["revid"])
                    ),
                    "roots": sorted(discovery["roots"]),
                    "title": source["title"],
                    "wikitext": content,
                }
            )
    return pages


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def render_archive(
    destination: Path,
    pages: list[dict],
    *,
    roots: tuple[str, ...],
    max_depth: int,
    per_root: int,
    max_pages: int,
    retrieved_at: str,
) -> dict:
    encoded_pages: list[tuple[str, bytes, dict]] = []
    page_manifest: list[dict] = []
    for sequence, page in enumerate(
        sorted(pages, key=lambda row: (row["title"].casefold(), row["page_id"]))
    ):
        filename = f"pages/{sequence:06d}-{page['page_id']}.json"
        raw = (
            json.dumps(page, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        encoded_pages.append((filename, raw, page))
        page_manifest.append(
            {
                "content_sha256": digest(raw),
                "filename": filename,
                "page_id": page["page_id"],
                "revision_id": page["revision_id"],
                "revision_timestamp": page["revision_timestamp"],
                "revision_url": page["revision_url"],
                "roots": page["roots"],
                "title": page["title"],
                "wikitext_chars": len(page["wikitext"]),
            }
        )
    manifest = {
        "api_url": API_URL,
        "archive_format": "universe-db-wikipedia-category-snapshot-v1",
        "category_depth": max_depth,
        "license": {
            "name": "Creative Commons Attribution-ShareAlike 4.0 International",
            "spdx_id": "CC-BY-SA-4.0",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "attribution": (
                "Each page retains its permanent revision URL. Wikipedia "
                "revision histories identify individual contributors."
            ),
        },
        "max_pages": max_pages,
        "page_count": len(page_manifest),
        "pages": page_manifest,
        "per_root_page_limit": per_root,
        "retrieved_at": retrieved_at,
        "roots": list(roots),
        "source_project": "English Wikipedia",
        "source_terms_url": (
            "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
        ),
    }
    manifest_raw = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        archive.writestr(zip_info("manifest.json"), manifest_raw)
        for filename, raw, _ in encoded_pages:
            archive.writestr(zip_info(filename), raw)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "sources"
            / f"wikipedia-chemistry-category-snapshot-{date.today().isoformat()}.zip"
        ),
    )
    parser.add_argument(
        "--roots",
        default="|".join(DEFAULT_ROOTS),
        help="category roots separated by |",
    )
    parser.add_argument("--category-depth", type=int, default=1)
    parser.add_argument("--per-root-pages", type=int, default=180)
    parser.add_argument("--max-pages", type=int, default=1260)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = tuple(value.strip() for value in args.roots.split("|") if value.strip())
    if not roots:
        raise SystemExit("at least one category root is required")
    if (
        args.category_depth < 0
        or args.per_root_pages <= 0
        or args.max_pages <= 0
        or args.delay < 0
    ):
        raise SystemExit("depth, page limits, and delay must be non-negative")
    if args.output.exists() and not args.force:
        raise SystemExit(f"{args.output} already exists; use --force to replace it")

    retrieved_at = utc_now()
    discovered = discover_pages(
        roots,
        max_depth=args.category_depth,
        per_root=args.per_root_pages,
        max_pages=args.max_pages,
        retries=args.retries,
        timeout=args.timeout,
        delay=args.delay,
    )
    pages = fetch_pages(
        discovered,
        retries=args.retries,
        timeout=args.timeout,
        delay=args.delay,
    )
    manifest = render_archive(
        args.output,
        pages,
        roots=roots,
        max_depth=args.category_depth,
        per_root=args.per_root_pages,
        max_pages=args.max_pages,
        retrieved_at=retrieved_at,
    )
    print(
        f"wrote {args.output} with {manifest['page_count']} pages "
        f"({args.output.stat().st_size} bytes, sha256 {digest(args.output.read_bytes())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
