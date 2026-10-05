#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["semver==3.1.0"]
#
# [tool.uv]
# exclude-newer = "1 day"
# ///
"""Print and verify a release version plan (baseline -> target) from remote tags."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from urllib.parse import urlparse

import semver


NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


class PlanError(RuntimeError):
    """A version plan cannot be proven safe."""


Version = semver.Version


def parse_version(value: str) -> Version:
    """Parse a release version: strict X.Y.Z, no prefix, pre-release or build."""
    try:
        version = Version.parse(value)
    except (TypeError, ValueError):
        raise PlanError(f"invalid SemVer version: {value!r}") from None
    if version.prerelease is not None or version.build is not None:
        raise PlanError(f"invalid SemVer version: {value!r}")
    return version


def is_release_version(value: str) -> bool:
    try:
        parse_version(value)
    except PlanError:
        return False
    return True


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], check=False, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit {result.returncode}"
        )
        raise PlanError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def normalize_repository(remote_url: str) -> str:
    value = remote_url.strip()
    if re.match(r"^[^/@:]+@[^/:]+:", value):
        path = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https", "ssh", "git"} or not parsed.path:
            raise PlanError(
                f"origin URL does not identify an owner/repository: {value!r}"
            )
        path = parsed.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        raise PlanError(f"origin URL does not identify an owner/repository: {value!r}")
    return "/".join(parts).casefold()


def parse_targets(values: list[str]) -> dict[str, Version]:
    if not values:
        raise PlanError(
            "the version plan is incomplete: at least one --target is required"
        )
    targets: dict[str, Version] = {}
    for value in values:
        namespace, separator, version_text = value.partition("=")
        if not separator or NAMESPACE_RE.fullmatch(namespace) is None:
            raise PlanError(f"invalid target {value!r}; expected namespace=X.Y.Z")
        if namespace in targets:
            raise PlanError(f"duplicate version namespace: {namespace!r}")
        targets[namespace] = parse_version(version_text)
    return targets


def remote_tag_names(remote: str) -> set[str]:
    output = git("ls-remote", "--tags", "--refs", remote)
    names: set[str] = set()
    for line in output.splitlines():
        fields = line.split("\t", 1)
        if len(fields) != 2 or not fields[1].startswith("refs/tags/"):
            raise PlanError(f"unexpected git ls-remote output: {line!r}")
        names.add(fields[1].removeprefix("refs/tags/"))
    return names


def build_plan(
    repository: str,
    targets: dict[str, Version],
    tag_names: set[str],
    excluded_tag_names: set[str] | None = None,
) -> dict[str, object]:
    excluded_tag_names = set(excluded_tag_names or set())
    for namespace, target in targets.items():
        tag_name = f"{namespace}{target}"
        if tag_name in tag_names and tag_name not in excluded_tag_names:
            raise PlanError(
                f"tag {tag_name!r} is already published; published tags are not moved "
                "or reused, use the next patch"
            )
    excluded_tag_names.update(
        f"{namespace}{target}" for namespace, target in targets.items()
    )
    versions: list[dict[str, str]] = []
    for namespace, target in sorted(targets.items()):
        candidates: list[Version] = []
        for tag_name in tag_names:
            if tag_name in excluded_tag_names or not tag_name.startswith(namespace):
                continue
            suffix = tag_name[len(namespace) :]
            if is_release_version(suffix):
                candidates.append(parse_version(suffix))
        if not candidates:
            raise PlanError(
                f"baseline for namespace {namespace!r} is unknown after excluding the current tag"
            )
        baseline = max(candidates)
        if target < baseline:
            raise PlanError(
                f"downgrade is not allowed for {namespace!r}: {baseline} -> {target}"
            )
        versions.append(
            {"namespace": namespace, "baseline": str(baseline), "target": str(target)}
        )
    return {"schema": 1, "repository": repository, "versions": versions}


def canonical_json(plan: dict[str, object]) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_plan(args: argparse.Namespace) -> dict[str, object]:
    expected_repository = normalize_repository(f"https://github.com/{args.repository}")
    actual_repository = normalize_repository(
        git("config", "--get", f"remote.{args.remote}.url")
    )
    if actual_repository != expected_repository:
        raise PlanError(
            f"origin repository mismatch: expected {expected_repository!r}, found {actual_repository!r}"
        )
    targets = parse_targets(args.target)
    excluded = set()
    if args.command == "verify" and args.tag_ref:
        excluded.add(args.tag_ref.removeprefix("refs/tags/"))
    return build_plan(
        expected_repository, targets, remote_tag_names(args.remote), excluded
    )


def verify_annotated(tag_ref: str) -> None:
    if git("cat-file", "-t", tag_ref).strip() != "tag":
        raise PlanError(f"release tag must be annotated: {tag_ref}")


def verify_tag_target(tag_ref: str, plan: dict[str, object]) -> None:
    tag_name = tag_ref.removeprefix("refs/tags/")
    planned_tags = {
        f"{item['namespace']}{item['target']}"
        for item in plan["versions"]  # type: ignore[index]
    }
    if tag_name not in planned_tags:
        raise PlanError(f"tag {tag_name!r} is absent from the current version plan")


def print_plan(plan: dict[str, object]) -> None:
    for item in plan["versions"]:  # type: ignore[union-attr]
        print(f"{item['namespace']}: {item['baseline']} -> {item['target']}")
    print(f"Canonical-Version-Plan: {canonical_json(plan)}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "verify"))
    result.add_argument("--repository", required=True, help="expected owner/repository")
    result.add_argument("--remote", default="origin")
    result.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="NAMESPACE=X.Y.Z",
        help="complete target version set; repeat for independent namespaces",
    )
    result.add_argument("--tag-ref", help="annotated release tag ref to verify")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        plan = load_plan(args)
        print_plan(plan)
        if args.command == "plan":
            if args.tag_ref:
                raise PlanError("plan is read-only and does not accept --tag-ref")
            return 0

        if not args.tag_ref:
            raise PlanError("verify requires --tag-ref")
        verify_tag_target(args.tag_ref, plan)
        verify_annotated(args.tag_ref)
        print("Version plan verified.")
        return 0
    except PlanError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
