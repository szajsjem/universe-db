#!/usr/bin/env python3
"""Download a pinned full English Wikipedia article dump and multistream index.

Uses curl for resumable transfers. Keeps upstream metadata, verifies byte counts,
and checks upstream MD5 when published; always records local SHA-256 digests.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

BASE = "https://dumps.wikimedia.org"


def fetch(url, path, resume=False):
    command = ["curl.exe" if __import__('os').name == 'nt' else "curl", "--fail", "--location",
               "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60"]
    if resume:
        command += ["--continue-at", "-"]
    # Restart curl for each retry so it recalculates the resume offset from the
    # bytes actually saved, including after receive errors (curl exit 56).
    for attempt in range(12):
        try:
            subprocess.run(command + ["--output", str(path), url], check=True)
            return
        except subprocess.CalledProcessError as error:
            if error.returncode not in {5, 6, 7, 18, 28, 35, 52, 55, 56, 92} or attempt == 11:
                raise
            saved = path.stat().st_size if path.exists() else 0
            print(f"Transfer interrupted (curl {error.returncode}); retry {attempt + 1}/11 from {saved:,} bytes", flush=True)
            time.sleep(min(5 * (attempt + 1), 30))


def digest(path, algorithm):
    result = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("C:/datasets/wikipedia"))
    parser.add_argument("--date", help="YYYYMMDD; default newest completed article dump")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    fetch(BASE + "/enwiki/", args.output / "releases.html")
    dates = sorted(set(re.findall(r'href="(\d{8})/"', (args.output / "releases.html").read_text())), reverse=True)
    if args.date:
        if not re.fullmatch(r"\d{8}", args.date):
            parser.error("--date must be YYYYMMDD")
        dates = [args.date]
    selected = None
    for date in dates:
        fetch(f"{BASE}/enwiki/{date}/dumpstatus.json", args.output / "dumpstatus.json")
        metadata = json.loads((args.output / "dumpstatus.json").read_text())
        job = metadata.get("jobs", {}).get("articlesmultistreamdumprecombine", {})
        if job.get("status") == "done":
            selected = date, job["files"]
            break
    if selected is None:
        raise RuntimeError("No completed full article dump found for the requested date. Run without --date to select the newest available completed release; existing partial files are retained.")
    date, files = selected
    print(f"Selected newest completed release: {date}", flush=True)
    directory = args.output / date
    directory.mkdir(exist_ok=True)
    (directory / "dumpstatus.json").write_text(json.dumps(metadata, indent=2))
    fetch(f"{BASE}/enwiki/{date}/enwiki-{date}-md5sums.txt", directory / "upstream-md5sums.txt")
    checksums = dict((name, checksum) for checksum, name in re.findall(r"([0-9a-f]{32})\s+(\S+)", (directory / "upstream-md5sums.txt").read_text()))
    report = {"date": date, "source": f"{BASE}/enwiki/{date}/", "license": "CC-BY-SA-4.0", "files": [], "status": "downloading"}
    status = directory / "download-status.json"
    status.write_text(json.dumps(report, indent=2))
    for name, info in files.items():
        if not name.endswith(("-multistream.xml.bz2", "-multistream-index.txt.bz2")):
            continue
        target = directory / name
        partial = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {name}: {info['size']:,} bytes", flush=True)
        if not target.exists():
            if not partial.exists() or partial.stat().st_size < info["size"]:
                fetch(BASE + info["url"], partial, resume=True)
            if partial.stat().st_size != info["size"]:
                raise RuntimeError(f"Size mismatch for {name}")
            partial.replace(target)
        if target.stat().st_size != info["size"]:
            raise RuntimeError(f"Size mismatch for {name}")
        expected = info.get("md5") or checksums.get(name)
        if expected and digest(target, "md5") != expected:
            raise RuntimeError(f"Upstream checksum mismatch for {name}")
        report["files"].append({"name": name, "bytes": info["size"], "sha256": digest(target, "sha256"), "upstream_md5_verified": bool(expected)})
        status.write_text(json.dumps(report, indent=2))
    if len(report["files"]) != 2:
        raise RuntimeError("Dump must include articles and multistream index")
    report.update(status="completed", completed_at=datetime.now(timezone.utc).isoformat(),
                  upstream_checksums_complete=all(item["upstream_md5_verified"] for item in report["files"]))
    status.write_text(json.dumps(report, indent=2))
    print(f"Completed: {directory}", flush=True)


if __name__ == "__main__":
    main()
