# Usage report

Run `python3 scripts/usage_report.py --sessions <rollout-directory> --thread <id> --json <output.json>`
from this skill directory. Descendants are included. Optional `--since` and
`--until` take timezone-qualified ISO timestamps (inclusive/exclusive).
Omit `--thread` for all observed threads within the time range.
Archived logs can be included by repeating `--sessions`.

The report reads existing local JSONL; it makes no model or network requests.
Thread and response IDs deduplicate copies; legacy token-count events without
response IDs use cumulative usage snapshots as a documented fallback.
Inherited rows before `subagent_history_start_ordinal` are excluded.
Missing boundary ordinals fail closed. Request counts from token-count events
are observed completed responses, not every HTTP attempt or failed request.
Unrecorded retries, tier and resume markers remain unknown.

Per-thread output includes role, actual model/effort/tier observations, first
and peak request input, cached input, output, continuation calls, turn starts,
compactions, elapsed time and rate-limit snapshots. Reasoning tokens are already
part of output and are not added again. First input includes system/project and
task context as well as any inherited history; parent totals include its own work
as well as coordination. Neither is a pure measure of delegation overhead.

Optional `--prices prices.json` accepts:

```json
{"as_of":"YYYY-MM-DD","currency":"USD","source":"price source URL or receipt",
 "rates":[{"model":"model-id","service_tier":"priority",
 "input_per_million":0,"cached_input_per_million":0,"output_per_million":0}]}
```

Supply verified prices for the actual model, date and service tier. Zero is only
an example, not a price recommendation. Missing model/tier/rates yield an unknown
cost, never an assumed default. Cache-write usage without separate pricing also
leaves cost unknown. A partially priced report exposes a known subtotal but
leaves the total unknown. Rate-limit percentages describe observed account
snapshots only; they cannot yield exact per-agent subscription quota shares.
