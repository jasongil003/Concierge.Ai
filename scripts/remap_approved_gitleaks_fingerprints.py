#!/usr/bin/env python3
"""Remap existing, reviewed synthetic Gitleaks fingerprints after an offline history rewrite.

This does not introduce suppressions or change any shared repository history.
It modifies only the ignore file in a disposable checkout of a sanitized mirror.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT_RE = re.compile(r"^([0-9a-f]{40})(:.+)$")
NULL_SHA = "0" * 40


def load_commit_map(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].split() != ["old", "new"]:
        raise ValueError("Expected git-filter-repo commit-map header.")
    mapping: dict[str, str] = {}
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 2 or not all(SHA_RE.fullmatch(value) for value in fields):
            raise ValueError("Malformed git-filter-repo commit-map row.")
        mapping[fields[0]] = fields[1]
    if not mapping:
        raise ValueError("The filtered repository has no commit mappings.")
    return mapping


def remap_approved_fingerprints(ignore_path: Path, mapping: dict[str, str]) -> tuple[int, int, int]:
    old_text = ignore_path.read_text(encoding="utf-8")
    rewritten_lines: list[str] = []
    remapped = removed = unchanged = 0
    for line in old_text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        match = FINGERPRINT_RE.fullmatch(body)
        if not match:
            rewritten_lines.append(line)
            continue
        original_sha, suffix = match.groups()
        mapped_sha = mapping.get(original_sha, original_sha)
        if mapped_sha == NULL_SHA:
            # An already-approved synthetic fingerprint whose introducing commit disappeared.
            removed += 1
            continue
        if mapped_sha != original_sha:
            remapped += 1
        else:
            unchanged += 1
        rewritten_lines.append(mapped_sha + suffix + ending)
    new_text = "".join(rewritten_lines)
    if new_text != old_text:
        ignore_path.write_text(new_text, encoding="utf-8")
    return remapped, removed, unchanged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit_map", type=Path, help="Mirror/filter-repo/commit-map")
    parser.add_argument("ignore_file", type=Path, help="Disposable checkout/.gitleaksignore")
    args = parser.parse_args()
    remapped, removed, unchanged = remap_approved_fingerprints(
        args.ignore_file, load_commit_map(args.commit_map)
    )
    print(
        "Existing approved Gitleaks fingerprint remap: "
        f"{remapped} remapped, {removed} unreachable, {unchanged} unchanged. "
        "No new fingerprint exceptions created."
    )


if __name__ == "__main__":
    main()
