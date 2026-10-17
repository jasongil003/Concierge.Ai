#!/usr/bin/env python3
"""Read-only reference preflight and fail-closed rewrite preservation gate.

Never reads file contents, rewrites history, changes refs, or prints credentials.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess


def git_read(repo, *arguments):
    result = subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def divergent_refs(rows):
    refs = {ref: oid for ref, oid in rows}
    collisions = []
    for ref, oid in refs.items():
        if ref.startswith("refs/heads/"):
            remote = "refs/remotes/origin/" + ref[len("refs/heads/"):]
            if remote in refs and refs[remote] != oid:
                collisions.append((ref, oid, remote, refs[remote]))
    return collisions


def destination_ref(ref):
    # filter-repo explicitly migrates origin tracking branches to local heads.
    # The preflight proves matching source aliases have identical tips.
    if ref.startswith("refs/remotes/origin/"):
        return "refs/heads/" + ref[len("refs/remotes/origin/"):]
    return ref


def preflight(repo):
    rows = [line.split() for line in git_read(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes/origin").splitlines()]
    collisions = divergent_refs(rows)
    if collisions:
        details = "\n".join(f"{local} {old} <> {remote} {new}" for local, old, remote, new in collisions)
        raise SystemExit("FAILED: divergent branch tips; no filtering allowed.\n" + details +
                         "\nCreate a fresh canonical mirror or preserve both histories under explicitly approved distinct branch names. Never overwrite/delete a competing tip automatically.")
    print("PASS: no divergent local/origin branch names.")


def snapshot(repo, output):
    rows = []
    for line in git_read(repo, "for-each-ref", "--format=%(refname) %(objectname) %(objecttype) %(symref)").splitlines():
        fields = line.split()
        ref, oid, kind = fields[:3]
        row = {"ref": ref, "oid": oid, "type": kind, "symref": fields[3] if len(fields) > 3 else ""}
        if ref == "refs/remotes/origin/HEAD":
            # Mirror clones materialize origin/HEAD as a plain commit alias of
            # the default branch rather than a symref. It is not published.
            row["exception"] = "default-branch alias; verify via the default branch destination"
        elif kind in {"commit", "tag"}:
            tip = git_read(repo, "rev-parse", ref + "^{commit}")
            row["tip"] = tip
            row["commits"] = git_read(repo, "rev-list", "--parents", tip).splitlines()
            row["count"] = len(row["commits"])
            row["destination"] = destination_ref(ref)
        if row["symref"]:
            row["exception"] = "symbolic alias; verify its target destination, not a separately published ref"
        elif kind == "tree" and ref.startswith("refs/codex/turn-diffs/"):
            row["exception"] = "local review tree omitted only from disposable mirror"
        rows.append(row)
    Path(output).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def verify(repo, ref_manifest, commit_manifest):
    repo, ref_manifest, commit_manifest = Path(repo), Path(ref_manifest), Path(commit_manifest)
    metadata = repo / "filter-repo"
    null_sha = "0" * 40
    sha_pattern = re.compile(r"^[0-9a-f]{40}$")


    def fail(message: str) -> None:
        raise SystemExit(f"FAILED: {message}. Do not publish this mirror.")


    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            fail(f"git {' '.join(arguments)} could not be verified")
        return result.stdout.strip()


    def read_map(path: Path, expected_header: list[str], row_size: int) -> list[list[str]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            fail(f"missing filter-repo map {path.name}")
        if not lines or lines[0].split() != expected_header:
            fail(f"unexpected {path.name} header")
        rows = []
        for line in lines[1:]:
            fields = line.split()
            if len(fields) != row_size:
                fail(f"malformed {path.name} row")
            rows.append(fields)
        return rows


    commit_map = {}
    for old, new in read_map(metadata / "commit-map", ["old", "new"], 2):
        if not sha_pattern.fullmatch(old) or not sha_pattern.fullmatch(new):
            fail("invalid hash in commit-map")
        if old in commit_map:
            fail("duplicate source commit in commit-map")
        commit_map[old] = new

    ref_map = {}
    for old, new, ref in read_map(metadata / "ref-map", ["old", "new", "ref"], 3):
        if not sha_pattern.fullmatch(old) or not sha_pattern.fullmatch(new):
            fail("invalid hash in ref-map")
        if ref in ref_map:
            fail("duplicate source ref in ref-map")
        ref_map[ref] = (old, new)

    source_refs = []
    for line in ref_manifest.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 5:
            fail("malformed source ref manifest")
        ref, object_type, old_tip, old_commit_tip, old_count = fields
        if not sha_pattern.fullmatch(old_tip) or not sha_pattern.fullmatch(old_commit_tip):
            fail(f"invalid source hash for {ref}")
        try:
            old_count_value = int(old_count)
        except ValueError:
            fail(f"invalid source commit count for {ref}")
        source_refs.append((ref, object_type, old_tip, old_commit_tip, old_count_value))

    commits_by_ref = {}
    for line in commit_manifest.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or not sha_pattern.fullmatch(fields[1]):
            fail("malformed source commit manifest")
        commits_by_ref.setdefault(fields[0], []).append(fields[1])

    inventory = json.loads((repo / "source-inventory.json").read_text(encoding="utf-8"))
    intended = {
        row["ref"]
        for row in inventory
        if not row.get("symref") and not row.get("exception") and row["type"] in {"commit", "tag"}
    }
    if intended != {row[0] for row in source_refs} or len(intended) != len(source_refs):
        fail("source manifest omitted or duplicated an intended inventory ref")
    expected_destinations = {destination_ref(ref) for ref in intended}
    actual_refs = set(git("for-each-ref", "--format=%(refname)").splitlines())
    if actual_refs != expected_destinations:
        fail("rewritten ref inventory differs from the documented destinations")

    for ref, _object_type, old_tip, old_commit_tip, old_count in source_refs:
        destination = destination_ref(ref)
        mapped_ref = ref_map.get(destination)
        if mapped_ref is None:
            fail(f"ref-map omitted source ref {ref}")
        mapped_old_tip, mapped_new_tip = mapped_ref
        if mapped_old_tip != old_tip:
            fail(f"ref-map source tip does not match {ref}")
        if mapped_new_tip == null_sha:
            fail(f"filter-repo removed source ref {ref}")

        actual_tip = git("rev-parse", "--verify", destination)
        if actual_tip != mapped_new_tip:
            fail(f"rewritten ref tip does not match ref-map for {ref}")

        mapped_commit_tip = commit_map.get(old_commit_tip)
        if mapped_commit_tip in (None, null_sha):
            fail(f"commit-map removed the source commit tip for {ref}")
        actual_commit_tip = git("rev-parse", "--verify", f"{destination}^{{commit}}")
        if actual_commit_tip != mapped_commit_tip:
            fail(f"rewritten commit tip does not match commit-map for {ref}")
        if git("cat-file", "-t", actual_tip) != _object_type:
            fail(f"rewritten object type changed for {ref}")

        mapped_history = set()
        source_history = commits_by_ref.get(ref, [])
        if len(source_history) != old_count:
            fail(f"source commit count changed while recording {ref}")
        for old_commit in source_history:
            new_commit = commit_map.get(old_commit)
            if new_commit is None:
                fail(f"commit-map omitted a source commit reachable from {ref}")
            if new_commit != null_sha:
                mapped_history.add(new_commit)
        if len(mapped_history) != old_count:
            fail(f"commit loss/collapse requires individual owner review for {ref}: source={old_count}, mapped={len(mapped_history)}")
        actual_history = set(git("rev-list", destination).splitlines())
        if actual_history != mapped_history:
            fail(f"rewritten reachable commit set differs from mapped source history for {ref}")
        rewritten_count = len(actual_history)
        if rewritten_count != len(mapped_history):
            fail(
                f"per-ref commit count mismatch for {ref}: source={old_count}, "
                f"mapped-survivors={len(mapped_history)}, rewritten={rewritten_count}"
            )
        print(
            f"PASS: {ref} -> {destination} tip preserved through ref-map; commits source={old_count}, "
            f"mapped survivors={len(mapped_history)}, rewritten={rewritten_count}"
        )

    checked = set()
    for row in inventory:
        for line in row.get("commits", []):
            old, *parents = line.split()
            if old in checked:
                continue
            checked.add(old)
            mapped = commit_map.get(old)
            if mapped in (None, null_sha) or any(commit_map.get(parent) in (None, null_sha) for parent in parents):
                fail(f"removed commit/parent requires individual owner review: {old}")
            actual_parents = git("show", "-s", "--format=%P", mapped).split()
            if actual_parents != [commit_map[parent] for parent in parents]:
                fail(f"parent/merge relationship changed for source commit {old}")
    print(f"PASS: ref-map, reachable commit sets and parent relationships verified for {len(source_refs)} refs / {len(checked)} commits.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("preflight")
    check.add_argument("repository", type=Path)
    snap = sub.add_parser("snapshot")
    snap.add_argument("repository", type=Path)
    snap.add_argument("output", type=Path)
    gate = sub.add_parser("verify")
    gate.add_argument("repository", type=Path)
    gate.add_argument("refs", type=Path)
    gate.add_argument("commits", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight(args.repository)
    elif args.command == "snapshot":
        snapshot(args.repository, args.output)
    else:
        verify(args.repository, args.refs, args.commits)


if __name__ == "__main__":
    main()
