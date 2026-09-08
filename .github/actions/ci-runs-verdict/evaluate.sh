#!/usr/bin/env bash
set -euo pipefail

# Single source of truth for "is the ci.yml evidence for a sha green".
# promote.yml consumes it in require mode (poll until concluded, hard-fail on
# anything but success); release.yml consumes it in report mode (single query,
# never fails the step — any verdict but "green" makes the caller rerun the
# full local gate). Ported verbatim from dzshzx/dingtalk-automation.

sha="${EVIDENCE_SHA:?}"
repository="${REPOSITORY:?}"
wait_seconds="${WAIT_SECONDS:-0}"
poll_seconds="${POLL_SECONDS:-20}"
max_age_hours="${MAX_AGE_HOURS:-}"
mode="${MODE:-require}"

emit() {
  local verdict="$1" detail="$2"
  echo "verdict: ${verdict} — ${detail}"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "verdict=${verdict}" >> "$GITHUB_OUTPUT"
  fi
  if [[ "$mode" == "require" && "$verdict" != "green" ]]; then
    exit 1
  fi
  exit 0
}

deadline=$(( SECONDS + wait_seconds ))
while :; do
  # One line per ci.yml run for this sha: "<status> <conclusion>
  # <run_started_at> <url>"; conclusion is the literal "null" until status is
  # "completed". Freshness keys on run_started_at, not updated_at — the latter
  # is bumped by unrelated record mutations and would err toward judging old
  # evidence fresh.
  # Count every page as well: API truncation or a changing result set must
  # not turn incomplete evidence into permission to promote or reuse CI.
  if ! runs="$(gh api --paginate \
    "repos/${repository}/actions/workflows/ci.yml/runs?head_sha=${sha}&per_page=100" \
    --jq '"total \(.total_count)", (.workflow_runs[] | "\(.status) \(.conclusion) \(.run_started_at) \(.html_url) \(.id) \(.run_attempt)")')"; then
    emit query-error "querying ci.yml runs for ${sha} failed"
  fi
  pending=""
  latest_success_epoch=0
  expected_count=-1
  observed_count=0
  declare -A seen_runs=()
  while read -r status conclusion started url run_id attempt; do
    [[ -n "$status" ]] || continue
    if [[ "$status" == "total" ]]; then
      if ! [[ "$conclusion" =~ ^[0-9]+$ ]] ||
        (( expected_count >= 0 && expected_count != conclusion )); then
        emit query-error "CI result count changed or is invalid"
      fi
      expected_count="$conclusion"
      continue
    fi
    observed_count=$((observed_count + 1))
    if ! [[ "$run_id" =~ ^[1-9][0-9]*$ && "$attempt" =~ ^[1-9][0-9]*$ ]] ||
      [[ -n "${seen_runs[$run_id]:-}" ]]; then
      emit query-error "malformed or duplicated CI run identity"
    fi
    seen_runs[$run_id]=1
    if [[ "$status" != "completed" ]]; then
      pending="$status $url"
    elif [[ "$conclusion" != "success" ]]; then
      emit failed "a ci.yml run for ${sha} did not succeed (conclusion: '${conclusion}', run: ${url})"
    else
      if ! run_epoch="$(date -u -d "$started" +%s 2>/dev/null)"; then
        emit query-error "unparseable run_started_at '${started}' on ${url}"
      fi
      if (( run_epoch > latest_success_epoch )); then
        latest_success_epoch="$run_epoch"
      fi
    fi
  done <<< "$runs"
  if (( expected_count < 0 || observed_count != expected_count )); then
    emit query-error "CI result set is incomplete (${observed_count}/${expected_count})"
  fi
  if (( observed_count > 0 )) && [[ -z "$pending" ]]; then
    break
  fi
  if (( SECONDS >= deadline )); then
    emit pending "not concluded after ${wait_seconds}s (last seen: ${pending:-no run registered})"
  fi
  echo "ci.yml for ${sha} is '${pending:-not registered yet}'; polling again in ${poll_seconds}s"
  sleep "$poll_seconds"
done

# The per-run evidence backing the verdict, for the workflow log (ADR-0038
# judges every run for the sha, not the latest one; ported from dingtalk-automation).
echo "concluded ci.yml runs for ${sha}:"
printf '%s\n' "$runs"

if [[ -n "$max_age_hours" ]]; then
  cutoff="$(date -u -d "-${max_age_hours} hours" +%s)"
  if (( latest_success_epoch < cutoff )); then
    emit stale "latest successful run started before the ${max_age_hours}h freshness window"
  fi
fi
emit green "every ci.yml run for ${sha} succeeded"
