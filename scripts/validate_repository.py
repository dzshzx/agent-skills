#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["python-frontmatter==1.3.0"]
# ///
"""Validate the repository invariants required before publishing a skill tag.

Checks skill frontmatter, README inventory, machine-specific paths, relative
links, and the syntax of shipped shell / JSON / TOML files. Behavioural
verification of a skill is not done here: run its evals/live-check.sh or a
real headless harness before pushing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import frontmatter as frontmatter_lib
import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LINK_PATTERN = re.compile(r"\[[^]]*]\(([^)]+)\)")
README_SKILL_LINK_PATTERN = re.compile(r"\]\(skills/([^/)]+)/SKILL\.md\)")
MACHINE_HOME_PATTERN = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^/\\\s`]+")


def frontmatter(skill_file: Path) -> dict[str, str]:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("must start with YAML frontmatter")
    if "---" not in lines[1:]:
        raise ValueError("frontmatter is missing its closing delimiter")
    try:
        metadata = frontmatter_lib.loads(text).metadata
    except yaml.YAMLError as error:
        detail = " ".join(str(error).split())
        raise ValueError(f"invalid YAML frontmatter: {detail}") from error
    return {
        str(key): "" if value is None else " ".join(str(value).split())
        for key, value in metadata.items()
    }


def validate() -> list[str]:
    errors: list[str] = []
    skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    names = {path.name for path in skill_dirs}

    if not names:
        errors.append("skills/: no skill directories found")

    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_dir.relative_to(ROOT)}: missing SKILL.md")
            continue
        if not (skill_dir / "evals" / "live-check.sh").is_file():
            errors.append(
                f"{skill_dir.relative_to(ROOT)}: missing evals/live-check.sh "
                "(every skill ships a real-harness check; scripts/verify.sh runs it)"
            )

        try:
            fields = frontmatter(skill_file)
        except ValueError as error:
            errors.append(f"{skill_file.relative_to(ROOT)}: {error}")
            continue

        name = fields.get("name", "")
        description = fields.get("description", "")
        if name != skill_dir.name:
            errors.append(
                f"{skill_file.relative_to(ROOT)}: name {name!r} must match directory {skill_dir.name!r}"
            )
        if not NAME_PATTERN.fullmatch(name):
            errors.append(
                f"{skill_file.relative_to(ROOT)}: invalid skill name {name!r}"
            )
        if not description:
            errors.append(
                f"{skill_file.relative_to(ROOT)}: description must not be empty"
            )

        text = skill_file.read_text(encoding="utf-8")
        if match := MACHINE_HOME_PATTERN.search(text):
            errors.append(
                f"{skill_file.relative_to(ROOT)}: machine-specific home path {match.group(0)!r}"
            )

        for target in LINK_PATTERN.findall(text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (skill_dir / target).resolve().exists():
                errors.append(
                    f"{skill_file.relative_to(ROOT)}: missing relative link target {target!r}"
                )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documented = set(README_SKILL_LINK_PATTERN.findall(readme))
    for name in sorted(names - documented):
        errors.append(f"README.md: missing skill table link for {name!r}")
    for name in sorted(documented - names):
        errors.append(f"README.md: documents nonexistent skill {name!r}")

    errors.extend(validate_shipped_files())
    return errors


def validate_shipped_files() -> list[str]:
    """Syntax-check every shell, JSON and TOML file a skill ships."""
    errors: list[str] = []
    for script in sorted(SKILLS_DIR.rglob("*.sh")):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append(
                f"{script.relative_to(ROOT)}: bash -n failed: {result.stderr.strip()}"
            )
    for path in sorted(SKILLS_DIR.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {error}")
    for path in sorted(SKILLS_DIR.rglob("*.toml")):
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            errors.append(f"{path.relative_to(ROOT)}: invalid TOML: {error}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    count = sum(1 for path in SKILLS_DIR.iterdir() if path.is_dir())
    print(
        f"Validated {count} skills, README inventory, and shipped shell/JSON/TOML syntax."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
