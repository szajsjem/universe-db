#!/usr/bin/env python3
"""Normalize and validate sentence-style Git commit messages."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


TRAILER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*:\s+\S.*$")


def _split_trailers(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return content and a final Git trailer paragraph, if present."""
    if not lines:
        return lines, []
    start = len(lines) - 1
    while start >= 0 and lines[start].strip():
        start -= 1
    candidate = lines[start + 1 :]
    if candidate and any(TRAILER_RE.match(line) for line in candidate):
        if all(TRAILER_RE.match(line) or line.startswith((" ", "\t")) for line in candidate):
            return lines[:start], candidate
    return lines, []


def _clean_paragraphs(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    blank = False
    for line in lines:
        line = line.rstrip()
        if not line:
            blank = bool(cleaned)
        else:
            if blank:
                cleaned.append("")
            cleaned.append(line)
            blank = False
    return cleaned


def normalize(message: str) -> str:
    lines = message.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""

    subject = " ".join(lines[0].split())
    if subject and subject[0].isalpha():
        subject = subject[0].upper() + subject[1:]
    subject = subject.rstrip(".!?")

    content, trailers = _split_trailers(lines[1:])
    body = _clean_paragraphs(content)
    result = [subject]
    if body:
        result.extend(["", *body])
    if trailers:
        result.extend(["", *trailers])
    return "\n".join(result) + "\n"


def validation_errors(message: str) -> list[str]:
    lines = message.splitlines()
    if not lines or not lines[0].strip():
        return ["subject must not be empty"]
    subject = lines[0]
    errors: list[str] = []
    if len(subject) > 72:
        errors.append("subject must be at most 72 characters")
    if subject[0].isalpha() and not subject[0].isupper():
        errors.append("subject must start with a capital letter")
    if subject.endswith((".", "!", "?")):
        errors.append("subject must not end with punctuation")
    if len(lines) > 1 and lines[1] != "":
        errors.append("subject must be followed by a blank line")
    content, _ = _split_trailers(lines[1:])
    if any(TRAILER_RE.match(line) for line in content):
        errors.append("trailers must be in a final paragraph separated from the body")
    return errors


def check_message(message: str) -> list[str]:
    normalized = normalize(message)
    errors = validation_errors(normalized)
    if message != normalized:
        errors.insert(0, "message is not normalized")
    return errors


def messages_in_range(revision_range: str) -> list[tuple[str, str]]:
    try:
        hashes = subprocess.run(
            ["git", "rev-list", "--reverse", revision_range],
            check=True, text=True, capture_output=True,
        ).stdout.splitlines()
        return [
            (
                commit,
                subprocess.run(
                    ["git", "cat-file", "commit", commit],
                    check=True, text=True, capture_output=True,
                ).stdout.partition("\n\n")[2],
            )
            for commit in hashes
        ]
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise RuntimeError(detail) from exc


def _report(label: str, errors: list[str]) -> None:
    for error in errors:
        print(f"{label}: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="message file (default: stdin)")
    parser.add_argument("--check", action="store_true", help="validate without writing output")
    parser.add_argument("--rev-range", help="check every commit in a Git revision range")
    args = parser.parse_args(argv)
    if args.rev_range:
        if args.file:
            parser.error("a file cannot be combined with --rev-range")
        try:
            commits = messages_in_range(args.rev_range)
        except RuntimeError as exc:
            print(f"git revision error: {exc}", file=sys.stderr)
            return 2
        failed = False
        for commit, message in commits:
            errors = check_message(message)
            if errors:
                _report(commit, errors)
                failed = True
        return 1 if failed else 0

    message = Path(args.file).read_text() if args.file else sys.stdin.read()
    if args.check:
        errors = check_message(message)
        _report(args.file or "stdin", errors)
        return 1 if errors else 0
    normalized = normalize(message)
    errors = validation_errors(normalized)
    if errors:
        _report(args.file or "stdin", errors)
        return 1
    sys.stdout.write(normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
