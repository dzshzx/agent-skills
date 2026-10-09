#!/usr/bin/env bash
# Assertions: source SKILL.md is included verbatim and hashed in every input;
# each bounded CLI run exits 0 with successful terminal event and final answer;
# child resources match role config, explicit overrides and configured defaults;
# inherited messages before the child boundary match pre-spawn parent history;
# history inheritance is checked separately from resource selection;
# irreversible scenario spawns no children and attempts no publish/delete command.
# Unknown syntax/options or missing rollout evidence is UNVERIFIABLE.
# Uses a private test package and local bare remote; keeps inputs/logs in a temp dir.
# Usage: bash evals/live-check.sh [repo-dir] [--scenario inheritance|override|irreversible|all]
#        [--inheritance-fork all|N] [--skip-inheritance REASON]
# Default: three billed Codex runs, 180s each. Irreversible input limits shell syntax.
# Select historical scope from the rendered schema/host-policy intersection.
# Explicit skip records the gap and runs remaining scenarios; none is not inheritance.
# Exit 0: selected checks pass; 1: error/fixture change; 2: usage; 3: SKIP/UNVERIFIABLE.
# Green proves these assertions only, not general delegation quality or OS isolation.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec uv run --locked --project "$HERE/../../.." python "$HERE/live_check.py" "$@"
