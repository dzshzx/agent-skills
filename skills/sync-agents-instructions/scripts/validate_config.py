#!/usr/bin/env python3
"""Validate a sync-agents-instructions machine config against the schema in SKILL.md.

Usage: validate_config.py [--schema-only] [CONFIG]
  CONFIG defaults to $XDG_CONFIG_HOME/agent-instructions/sync-config.toml
  (~/.config when XDG_CONFIG_HOME is unset).
  --schema-only skips the filesystem checks (referenced files must exist).
  Machine paths may use ~ and $VAR; both are expanded before checking.

Exit 0: valid. Exit 1: errors, one per line on stderr. Exit 2: usage or unreadable config.
"""

from __future__ import annotations

import os
import posixpath
import sys
import tomllib
from pathlib import Path

LOAD_MODES = {"always", "on-demand"}
ALWAYS_LOAD_MODES = {"native", "mandatory-entry-read"}
TOP_LEVEL = {"workspace", "shared_sources", "agents", "repository_exclusions"}
WORKSPACE_REQUIRED = {"project_globs"}
WORKSPACE_OPTIONAL = {"off_limits"}
SHARED_SOURCE_KEYS = {"path", "role", "domain", "load"}
AGENT_REQUIRED = {"name", "entry_file", "project_instruction_file", "always_load_mode"}
AGENT_OPTIONAL = {"agent_specific_file", "skill_dirs", "runtime_constructs", "readonly_project_surfaces"}
EXCLUSION_KEYS = {"glob", "reason"}


def default_config() -> Path:
    home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(home) / "agent-instructions" / "sync-config.toml"


def normalize_machine_path(value: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(value)))


def normalize_repo_path(value: str) -> str:
    return posixpath.normpath(value)


class Checker:
    def __init__(self, data: dict, check_paths: bool) -> None:
        self.data = data
        self.check_paths = check_paths
        self.errors: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    # --- generic field helpers -------------------------------------------------

    def table(self, where: str, value: object, required: set[str], optional: set[str] = frozenset()) -> dict:
        if not isinstance(value, dict):
            self.error(where, "must be a table")
            return {}
        for key in sorted(set(value) - required - optional):
            self.error(where, f"unknown key {key!r}")
        for key in sorted(required - set(value)):
            self.error(where, f"missing required key {key!r}")
        return value

    def string(self, where: str, value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            self.error(where, "must be a non-empty string")
            return None
        return value

    def string_list(self, where: str, value: object, allow_empty: bool) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            self.error(where, "must be a list of non-empty strings")
            return []
        if not value and not allow_empty:
            self.error(where, "must not be empty")
        return value

    def file_exists(self, where: str, value: str) -> None:
        if self.check_paths and not Path(normalize_machine_path(value)).is_file():
            self.error(where, f"file not found: {value}")

    def array_of_tables(self, key: str, required: bool) -> list[dict]:
        value = self.data.get(key)
        if value is None:
            if required:
                self.error(key, "missing required array of tables")
            return []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            self.error(key, "must be an array of tables ([[...]])")
            return []
        if required and not value:
            self.error(key, "must contain at least one entry")
        return value

    # --- sections ----------------------------------------------------------------

    def run(self) -> list[str]:
        self.table("(top level)", self.data, {"workspace", "shared_sources", "agents"}, TOP_LEVEL)
        self.workspace()
        self.shared_sources()
        self.agents()
        self.repository_exclusions()
        return self.errors

    def workspace(self) -> None:
        ws = self.table("workspace", self.data.get("workspace"), WORKSPACE_REQUIRED, WORKSPACE_OPTIONAL)
        if "project_globs" in ws:
            self.string_list("workspace.project_globs", ws["project_globs"], allow_empty=False)
        if "off_limits" in ws:
            self.string_list("workspace.off_limits", ws["off_limits"], allow_empty=True)

    def shared_sources(self) -> None:
        seen: dict[str, str] = {}
        for index, entry in enumerate(self.array_of_tables("shared_sources", required=True)):
            where = f"shared_sources[{index}]"
            entry = self.table(where, entry, SHARED_SOURCE_KEYS)
            for key in ("role", "domain"):
                if key in entry:
                    self.string(f"{where}.{key}", entry[key])
            if "load" in entry and entry["load"] not in LOAD_MODES:
                self.error(f"{where}.load", f"must be one of {sorted(LOAD_MODES)}")
            path = self.string(f"{where}.path", entry.get("path")) if "path" in entry else None
            if path is None:
                continue
            normalized = normalize_machine_path(path)
            if normalized in seen:
                self.error(f"{where}.path", f"normalizes to the same file as {seen[normalized]}")
            seen[normalized] = where
            self.file_exists(f"{where}.path", path)

    def agents(self) -> None:
        agents = self.array_of_tables("agents", required=True)
        names: dict[str, str] = {}
        entries: dict[str, str] = {}
        owners: dict[str, str] = {}
        readonly: list[tuple[str, str, str]] = []
        for index, entry in enumerate(agents):
            where = f"agents[{index}]"
            entry = self.table(where, entry, AGENT_REQUIRED, AGENT_OPTIONAL)
            name = self.string(f"{where}.name", entry["name"]) if "name" in entry else None
            if name is not None:
                if name in names:
                    self.error(f"{where}.name", f"duplicates {names[name]}")
                else:
                    names[name] = where = f"agents[{name}]"
            if "entry_file" in entry and (entry_file := self.string(f"{where}.entry_file", entry["entry_file"])):
                normalized = normalize_machine_path(entry_file)
                if normalized in entries:
                    self.error(f"{where}.entry_file", f"normalizes to the same owner as {entries[normalized]}")
                entries[normalized] = where
                self.file_exists(f"{where}.entry_file", entry_file)
            if "project_instruction_file" in entry:
                owner = self.owner_surface(where, entry["project_instruction_file"])
                if owner is not None:
                    if owner in owners:
                        self.error(f"{where}.project_instruction_file", f"normalizes to the same owner as {owners[owner]}")
                    owners[owner] = where
            if "always_load_mode" in entry and entry["always_load_mode"] not in ALWAYS_LOAD_MODES:
                self.error(f"{where}.always_load_mode", f"must be one of {sorted(ALWAYS_LOAD_MODES)}")
            if "agent_specific_file" in entry and (specific := self.string(f"{where}.agent_specific_file", entry["agent_specific_file"])):
                self.file_exists(f"{where}.agent_specific_file", specific)
            for key in ("skill_dirs", "runtime_constructs"):
                if key in entry:
                    self.string_list(f"{where}.{key}", entry[key], allow_empty=True)
            if "readonly_project_surfaces" in entry:
                field = f"{where}.readonly_project_surfaces"
                seen_readonly: set[str] = set()
                for surface in self.string_list(field, entry["readonly_project_surfaces"], allow_empty=True):
                    normalized = self.repo_surface(field, surface)
                    if normalized is None:
                        continue
                    if normalized in seen_readonly:
                        self.error(field, f"{surface!r} is listed more than once")
                    seen_readonly.add(normalized)
                    readonly.append((where, surface, normalized))
        for where, surface, normalized in readonly:
            owner = owners.get(normalized)
            if owner is None:
                self.error(f"{where}.readonly_project_surfaces", f"{surface!r} is not another configured agent's project_instruction_file")
            elif owner == where:
                self.error(f"{where}.readonly_project_surfaces", f"{surface!r} is this agent's own surface")

    def owner_surface(self, where: str, value: object) -> str | None:
        return self.repo_surface(f"{where}.project_instruction_file", value)

    def repo_surface(self, field: str, value: object) -> str | None:
        """Validate one repo-relative surface path; return its normalized form or None."""
        surface = self.string(field, value)
        if surface is None:
            return None
        if surface.startswith(("/", "~")) or ":" in surface.split("/", 1)[0]:
            self.error(field, "must be repo-relative, not absolute or ~-based")
            return None
        if "\\" in surface:
            self.error(field, "must use / separators")
            return None
        if surface.endswith("/"):
            self.error(field, "must name a file, not a directory")
            return None
        normalized = normalize_repo_path(surface)
        if normalized == "." or normalized.startswith("../"):
            self.error(field, "must stay inside the repository")
            return None
        return normalized

    def repository_exclusions(self) -> None:
        for index, entry in enumerate(self.array_of_tables("repository_exclusions", required=False)):
            where = f"repository_exclusions[{index}]"
            entry = self.table(where, entry, EXCLUSION_KEYS)
            for key in EXCLUSION_KEYS & set(entry):
                self.string(f"{where}.{key}", entry[key])


def main(argv: list[str]) -> int:
    check_paths = True
    args = list(argv)
    if "--schema-only" in args:
        check_paths = False
        args.remove("--schema-only")
    if len(args) > 1 or any(arg.startswith("-") for arg in args):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    config = Path(args[0]) if args else default_config()
    try:
        with open(config, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"ERROR: {config}: {error}", file=sys.stderr)
        return 2

    errors = Checker(data, check_paths).run()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    agents = ", ".join(agent.get("name", "?") for agent in data.get("agents", []))
    print(f"OK: {config}: {len(data.get('agents', []))} agents ({agents}), {len(data.get('shared_sources', []))} shared sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
