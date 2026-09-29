#!/usr/bin/env bash
# Deterministic regressions only: fixtures and fake CLIs; no model calls.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# Locks must match their manifests (repo environment and PEP 723 scripts).
uv lock --check --quiet
for script in scripts/*.py skills/*/scripts/*.py; do
  [ -f "$script.lock" ] && uv lock --check --quiet --script "$script"
done
uv run --locked python -m unittest discover -s scripts/tests -p 'test_*.py'
shopt -s nullglob
for eval_dir in skills/*/evals; do
  tests=("$eval_dir"/test_*.py)
  [ ${#tests[@]} -gt 0 ] || continue
  uv run --locked python -m unittest discover -s "$eval_dir" -p 'test_*.py'
done
