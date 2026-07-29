---
name: refactor-batch-landing
description: Autonomously land a reviewed refactor candidate list (e.g. from an architecture report) as auditable commits, using fresh writer agents and a batch review. Requires the Matt Pocock skills family (codebase-design, implement, tdd, code-review, to-spec, to-tickets, grill-with-docs). Use when the user authorizes landing an entire reviewed candidate batch — 全做、按顺序落地, "land the whole list". Not for single ad-hoc refactors or unreviewed ideas.
---

# Refactor Batch Landing

Land a candidate list as auditable commits. The main-session **supervisor** holds only state, authorization, and evidence; implementation happens in fresh subagent contexts. The list is an **idea queue**, not a spec: "do them all / your call" authorizes ordering, splitting, merging, shrinking, rejecting, and deferring within the list — never out-of-list features, deliberate behavior changes, or releases nobody named.

> **Dependency**: orchestrates the [Matt Pocock skills](https://github.com/mattpocock/skills) — `/codebase-design`, `/implement`, `/tdd`, `/code-review`, `/to-spec`, `/to-tickets`, `/grill-with-docs`. Install that family first.

## Setup

Read repository instructions and candidate sources; confirm a safe branch/worktree; pin `batch_base = HEAD`. Create a **batch ledger** (the repository's configured tracker, else an out-of-repo workfiles directory such as `~/.local/share/agent-workfiles/<repo>/tracker/<batch-slug>/batch.md` — never committed) with one row per source: state `queued | landed | rejected | deferred | blocked`, dependencies, commits, verification, deviations, and the user's authorization (scope and release). Splits and merges stay traceable via `derived_from`/`sources` notes; a source counts as landed only when all work derived from it has landed. Only the supervisor writes the ledger.

## Triage and order

Triage the whole list before writing code, delegating reads to parallel subagents when they save main context: per candidate, decide keep/reject/defer on evidence, note dependencies and rough size. Invalid premises → `rejected`; payoff contingent on future needs → `deferred` with a written trigger. Order by dependencies; when a blocker is rejected or deferred, re-check its dependents. After batch authorization, dispositions and ordering need no further confirmation.

## Landing loop

One writer at a time on a shared checkout; parallelize only with isolated worktrees and non-overlapping ownership.

- **Fits one fresh context** → dispatch a fresh writer with a self-contained packet (goal, evidence, baseline behavior, seams, acceptance commands); it runs `/implement` (with `/tdd` and `/code-review` internally) and commits — `/codebase-design` first when the interface or test seam is undecided.
- **Too big for one context** → a fresh planning agent runs `/codebase-design`, `/to-spec`, and `/to-tickets` into tracer-bullet tickets with blocking edges (expand–contract for wide refactors); then one fresh writer per unblocked ticket. Batch authorization covers `/to-spec` seam confirmation and `/to-tickets` quizzes — the supervisor adjudicates on evidence; only product intent unanswerable from code, tests, docs, or ADRs goes back to the user via `/grill-with-docs`.

Before committing, the writer must pass targeted tests, the full suite, existing guard scripts, and byte-for-byte comparison on any output promised unchanged — green tests never substitute for the byte gate. Writers return only commits, verification, review results, and deviations; the supervisor verifies commits, working tree, and source mapping before updating the ledger.

## Failure

- A failed gate freezes new work: one fresh repair attempt per falsifiable root cause, rerunning every gate plus `/code-review` on the fix. Two failed rounds → `blocked`; no third.
- A writer leaving dirty state or no commit → a repair agent takes over; never reset or overwrite unknown changes.
- Subagents unavailable → record the packet in the ledger and mark `blocked`; the main session never takes over implementation.
- `blocked` freezes batch review, delivery, and release; changing a blocked item's disposition is the user's call alone. Escalate with evidence and concrete options (re-scope, defer, reject).

## Batch review and delivery

When every source is landed/rejected/deferred and nothing is blocked, run `/code-review` over `batch_base...HEAD` plus the full suite — the batch's **only** full-range discovery pass. A finding blocks delivery only when the batch diff introduced the defect or a gate the batch promised fails; defects already present at `batch_base`, and hardening beyond what the landed candidates promised, are **new candidates**: record them with severity in the ledger for a future authorization and keep delivering. Route blocking findings to writers under the Failure rules; a rerun verifies prior findings closed and reviews only the repair diffs — never a fresh full-range discovery. Release only on a recorded release authorization, executing exactly the repository's documented release action; otherwise stop at local commits. Report per source: disposition, commits, verification, deviations, delivery state, and any recorded follow-up candidates.

## Escalation

Ask the user only for: a deliberate user-visible behavior change, scope beyond the list, an unauthorized destructive or external action, product questions evidence cannot settle, or a batch frozen on `blocked`. Everything else is the supervisor's decision — keep going. Never force code changes to complete a batch.
