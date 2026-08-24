#!/usr/bin/env python3
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


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LINK_PATTERN = re.compile(r"\[[^]]*]\(([^)]+)\)")
README_SKILL_LINK_PATTERN = re.compile(r"\]\(skills/([^/)]+)/SKILL\.md\)")
MACHINE_HOME_PATTERN = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^/\\\s`]+")


def frontmatter(skill_file: Path) -> dict[str, str]:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("must start with YAML frontmatter")

    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("frontmatter is missing its closing delimiter") from error

    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in lines[1:end]:
        if line.startswith((" ", "\t")):
            if current_key is not None:
                fields[current_key] = f"{fields[current_key]} {line.strip()}".strip()
            continue

        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)", line)
        if match is None:
            raise ValueError(f"unsupported frontmatter line: {line!r}")
        current_key, value = match.groups()
        fields[current_key] = "" if value in {">", ">-", "|", "|-"} else value.strip()

    return fields


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
            errors.append(f"{skill_file.relative_to(ROOT)}: invalid skill name {name!r}")
        if not description:
            errors.append(f"{skill_file.relative_to(ROOT)}: description must not be empty")

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
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"{script.relative_to(ROOT)}: bash -n failed: {result.stderr.strip()}")
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
    print(f"Validated {count} skills, README inventory, and shipped shell/JSON/TOML syntax.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
