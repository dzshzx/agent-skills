"""File inventory and Git evidence for the two live-check stages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode()


def snapshot(repo: Path) -> dict:
    files = {}
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in names + [d for d in dirs if (Path(root) / d).is_symlink()]:
            path = Path(root) / name
            relative = path.relative_to(repo).as_posix()
            if path.is_symlink():
                files[relative] = ["symlink", os.readlink(path)]
            else:
                files[relative] = ["file", hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode & 0o777]
    return {"files": files, "head": git(repo, "rev-parse", "HEAD").strip(),
            "status": git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")}


def check(repo: Path, before: dict, allowed: set[str]) -> list[str]:
    after = snapshot(repo)
    errors = []
    changed = {p for p in before["files"].keys() | after["files"].keys()
               if before["files"].get(p) != after["files"].get(p)}
    if changed - allowed:
        errors.append(f"protected inventory/content changed: {sorted(changed - allowed)}")
    if not allowed:
        for field in ("head", "status"):
            if before[field] != after[field]:
                errors.append(f"repository {field} changed")
    else:
        if protected_status(before["status"], allowed) != protected_status(after["status"], allowed):
            errors.append("protected Git status changed")
        base = before["head"]
        if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD"], capture_output=True).returncode:
            errors.append("baseline HEAD is no longer an ancestor")
        else:
            for commit in git(repo, "rev-list", f"{base}..HEAD").splitlines():
                # Each commit, including all merge-parent diffs: net reverts cannot hide writes.
                paths = set(git(repo, "diff-tree", "--root", "-m", "--no-commit-id", "--name-only", "-r", "-z", commit).split("\0")) - {""}
                if paths - allowed:
                    errors.append(f"commit {commit} touched protected paths: {sorted(paths - allowed)}")
    return errors


def protected_status(status: str, allowed: set[str]) -> list[str]:
    records = iter(status.split("\0"))
    protected = []
    for record in records:
        if not record:
            continue
        paths = [record[3:]]
        if "R" in record[:2] or "C" in record[:2]:
            paths.append(next(records))
        if any(path not in allowed for path in paths):
            protected.append(record + "\0" + "\0".join(paths[1:]))
    return sorted(protected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "check"))
    parser.add_argument("repo", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--allow", action="append", default=[])
    args = parser.parse_args()
    if args.action == "snapshot":
        args.baseline.write_text(json.dumps(snapshot(args.repo), indent=2) + "\n")
        return 0
    errors = check(args.repo, json.loads(args.baseline.read_text()), set(args.allow))
    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
