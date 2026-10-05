#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic==2.13.5"]
#
# [tool.uv]
# exclude-newer = "1 day"
# ///
"""Validate a sync-agents-instructions machine config against the schema in SKILL.md.

Usage: validate_config.py [--schema-only] [CONFIG]
  CONFIG defaults to $XDG_CONFIG_HOME/agent-instructions/sync-config.toml
  (~/.config when XDG_CONFIG_HOME is unset).
  --schema-only skips the filesystem checks (referenced files must exist).
  Machine paths may use ~ and $VAR; both are expanded before checking.
  Every $VAR / ${VAR} in workspace.off_limits must be set and non-empty in both
  modes: an unexpanded or empty variable would silently void the restriction.

Exit 0: valid. Exit 1: errors, one per line on stderr. Exit 2: usage or unreadable config.
"""

import os
import posixpath
import re
import sys
import tomllib
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from pydantic_core import PydanticCustomError

LOAD_MODES = {"always", "on-demand"}
ALWAYS_LOAD_MODES = {"native", "mandatory-entry-read"}
# Variable syntax os.path.expandvars recognises on POSIX; an unterminated ${ is
# matched too, because expandvars leaves it literal.
ENV_REFERENCE = re.compile(r"\$(\w+|\{[^}]*\}?)", re.ASCII)


def default_config() -> Path:
    home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return Path(home) / "agent-instructions" / "sync-config.toml"


def normalize_machine_path(value: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(value)))


def normalize_repo_path(value: str) -> str:
    return posixpath.normpath(value)


# --- field types: every failure carries the final one-line message -------------


def fail(message: str) -> PydanticCustomError:
    return PydanticCustomError("config", message)


def non_empty_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fail("must be a non-empty string")
    return value


def string_list(allow_empty: bool):
    def check(value: object) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise fail("must be a list of non-empty strings")
        if not value and not allow_empty:
            raise fail("must not be empty")
        return value

    return BeforeValidator(check)


def one_of(choices: set[str]):
    def check(value: object) -> str:
        if not isinstance(value, str) or value not in choices:
            raise fail(f"must be one of {sorted(choices)}")
        return value

    return BeforeValidator(check)


def array_of_tables(required: bool):
    def check(value: object) -> list:
        if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value
        ):
            raise fail("must be an array of tables ([[...]])")
        if required and not value:
            raise fail("must contain at least one entry")
        return value

    return BeforeValidator(check)


def repo_surface(value: str) -> str:
    """Validate one repo-relative surface path (value is already a non-empty string)."""
    if value.startswith(("/", "~")) or ":" in value.split("/", 1)[0]:
        raise fail("must be repo-relative, not absolute or ~-based")
    if "\\" in value:
        raise fail("must use / separators")
    if value.endswith("/"):
        raise fail("must name a file, not a directory")
    normalized = normalize_repo_path(value)
    if normalized in {".", ".."} or normalized.startswith("../"):
        raise fail("must stay inside the repository")
    return value


def distinct_surfaces(values: list[str]) -> list[str]:
    seen: set[str] = set()
    for value in values:
        normalized = normalize_repo_path(value)
        if normalized in seen:
            raise fail(f"{value!r} is listed more than once")
        seen.add(normalized)
    return values


Text = Annotated[str, BeforeValidator(non_empty_string)]
Surface = Annotated[Text, AfterValidator(repo_surface)]


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Workspace(Table):
    project_globs: Annotated[list[str], string_list(allow_empty=False)]
    off_limits: Annotated[list[str], string_list(allow_empty=True)] = []

    @model_validator(mode="after")
    def off_limits_variables_expand(self, info: ValidationInfo) -> "Workspace":
        """Every $VAR / ${VAR} must expand to a non-empty value, else the rule is void."""
        report = info.context["report"]
        where = "workspace.off_limits"
        for value in self.off_limits:
            for match in ENV_REFERENCE.finditer(value):
                name = match.group(1)
                if name.startswith("{"):
                    if not name.endswith("}"):
                        report(
                            where,
                            f"{value!r} has an unterminated variable reference {match.group(0)}",
                        )
                        continue
                    name = name[1:-1]
                if name not in os.environ:
                    report(
                        where,
                        f"{value!r} references unset environment variable ${name}",
                    )
                elif not os.environ[name]:
                    report(
                        where,
                        f"{value!r} references empty environment variable ${name}",
                    )
        return self


class SharedSource(Table):
    path: Text
    role: Text
    domain: Text
    load: Annotated[str, one_of(LOAD_MODES)]


class Agent(Table):
    name: Text
    entry_file: Text
    project_instruction_file: Surface
    always_load_mode: Annotated[str, one_of(ALWAYS_LOAD_MODES)]
    agent_specific_file: Annotated[str | None, BeforeValidator(non_empty_string)] = None
    skill_dirs: Annotated[list[str], string_list(allow_empty=True)] = []
    runtime_constructs: Annotated[list[str], string_list(allow_empty=True)] = []
    readonly_project_surfaces: Annotated[
        list[Surface],
        BeforeValidator(string_list(allow_empty=True).func),
        AfterValidator(distinct_surfaces),
    ] = []


class RepositoryExclusion(Table):
    glob: Text
    reason: Text


class Config(Table):
    workspace: Workspace
    shared_sources: Annotated[list[SharedSource], array_of_tables(required=True)]
    agents: Annotated[list[Agent], array_of_tables(required=True)]
    repository_exclusions: Annotated[
        list[RepositoryExclusion], array_of_tables(required=False)
    ] = []

    @model_validator(mode="after")
    def cross_entry_rules(self, info: ValidationInfo) -> "Config":
        """Uniqueness, readonly-surface ownership and (unless schema-only) file existence."""
        report = info.context["report"]
        check_paths = info.context["check_paths"]

        def file_exists(where: str, value: str) -> None:
            if check_paths and not Path(normalize_machine_path(value)).is_file():
                report(where, f"file not found: {value}")

        seen: dict[str, str] = {}
        for index, source in enumerate(self.shared_sources):
            where = f"shared_sources[{index}]"
            normalized = normalize_machine_path(source.path)
            if normalized in seen:
                report(
                    f"{where}.path",
                    f"normalizes to the same file as {seen[normalized]}",
                )
            seen[normalized] = where
            file_exists(f"{where}.path", source.path)

        names: dict[str, str] = {}
        entries: dict[str, str] = {}
        owners: dict[str, str] = {}
        for index, agent in enumerate(self.agents):
            where = f"agents[{index}]"
            if agent.name in names:
                report(f"{where}.name", f"duplicates {names[agent.name]}")
            else:
                names[agent.name] = where = f"agents[{agent.name}]"
            normalized = normalize_machine_path(agent.entry_file)
            if normalized in entries:
                report(
                    f"{where}.entry_file",
                    f"normalizes to the same owner as {entries[normalized]}",
                )
            entries[normalized] = where
            file_exists(f"{where}.entry_file", agent.entry_file)
            owner = normalize_repo_path(agent.project_instruction_file)
            if owner in owners:
                report(
                    f"{where}.project_instruction_file",
                    f"normalizes to the same owner as {owners[owner]}",
                )
            owners[owner] = where
            if agent.agent_specific_file is not None:
                file_exists(f"{where}.agent_specific_file", agent.agent_specific_file)
        for index, agent in enumerate(self.agents):
            where = names.get(agent.name, f"agents[{index}]")
            for surface in agent.readonly_project_surfaces:
                owner = owners.get(normalize_repo_path(surface))
                if owner is None:
                    report(
                        f"{where}.readonly_project_surfaces",
                        f"{surface!r} is not another configured agent's project_instruction_file",
                    )
                elif owner == where:
                    report(
                        f"{where}.readonly_project_surfaces",
                        f"{surface!r} is this agent's own surface",
                    )
        return self


# --- error rendering -----------------------------------------------------------

STRING_LIST_FIELDS = {
    "project_globs",
    "off_limits",
    "skill_dirs",
    "runtime_constructs",
    "readonly_project_surfaces",
}


def render_location(data: object, loc: tuple) -> str:
    """('agents', 0, 'name') -> 'agents[codex].name' when that agent has a valid name."""
    parts: list[str] = []
    node = data
    for index, key in enumerate(loc):
        if isinstance(key, int):
            if index and loc[index - 1] in STRING_LIST_FIELDS:
                break  # a list item reports on its list field
            name = node[key].get("name") if isinstance(node, list) else None
            label = (
                name
                if loc[index - 1] == "agents" and isinstance(name, str) and name.strip()
                else key
            )
            parts[-1] += f"[{label}]"
        else:
            parts.append(str(key))
        try:
            node = node[key]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            node = None
    return ".".join(parts) or "(top level)"


class Checker:
    """Validate parsed TOML; run() returns 'where: message' strings, one per error."""

    def __init__(self, data: dict, check_paths: bool) -> None:
        self.data = data
        self.check_paths = check_paths
        self.errors: list[str] = []

    def report(self, where: str, message: str) -> None:
        line = f"{where}: {message}"
        if line not in self.errors:
            self.errors.append(line)

    def run(self) -> list[str]:
        if not isinstance(self.data, dict):
            self.report("(top level)", "must be a table")
            return self.errors
        try:
            Config.model_validate(
                self.data,
                context={"report": self.report, "check_paths": self.check_paths},
            )
        except ValidationError as error:
            for item in error.errors():
                loc = tuple(item["loc"])
                if item["type"] == "missing":
                    self.report(
                        render_location(self.data, loc[:-1]),
                        f"missing required key {loc[-1]!r}",
                    )
                elif item["type"] == "extra_forbidden":
                    self.report(
                        render_location(self.data, loc[:-1]),
                        f"unknown key {loc[-1]!r}",
                    )
                elif item["type"] in {
                    "model_type",
                    "model_attributes_type",
                    "dict_type",
                }:
                    self.report(render_location(self.data, loc), "must be a table")
                else:
                    self.report(render_location(self.data, loc), item["msg"])
        return self.errors


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
    print(
        f"OK: {config}: {len(data.get('agents', []))} agents ({agents}), {len(data.get('shared_sources', []))} shared sources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
