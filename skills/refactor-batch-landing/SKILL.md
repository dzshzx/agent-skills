---
name: refactor-batch-landing
description: Autonomously land a reviewed refactor batch with fresh planning, writer, and review agents. Requires the Matt Pocock skills family (codebase-design, implement, tdd, code-review, to-spec, to-tickets, grill-with-docs). Use when the user says 全做、直接做、按顺序落地, or requests batch refactoring.
---

# Refactor Batch Landing

Land a candidate list as auditable commits. The main-session **supervisor** holds only state, authorization, and evidence; all other work happens in fresh subagent contexts.

An architecture report is an **idea queue**, not a spec. "Do them all / go ahead / your call / I trust you" authorizes the agent to order, split, merge, shrink, reject, and defer within the list; it does not authorize out-of-list features, deliberate behavior changes, or releases nobody named.

> **Dependency**: this skill orchestrates the [Matt Pocock skills](https://github.com/mattpocock/skills) — `/codebase-design`, `/implement`, `/tdd`, `/code-review`, `/to-spec`, `/to-tickets`, `/grill-with-docs`. Install that family first; without it the planning and writer flows below have nothing to run.

## Matt flow

- Interface / test seam undecided → the planning agent uses `/codebase-design`; design-it-twice when several designs are reasonable.
- Single context (implementation plus verification fits in one fresh context) → a fresh writer uses `/implement`; it runs `/tdd` and `/code-review` internally and commits.
- Multi context (one fresh context cannot hold implementation plus verification) → the planning agent uses `/to-spec` and `/to-tickets` to produce tracer-bullet tickets with blocking edges; wide refactors use expand–contract. One fresh writer per frontier ticket.

Batch authorization covers `/to-spec`'s seam confirmation and `/to-tickets`' quiz: the planning agent proposes, the supervisor approves on evidence. Only when product intent cannot be derived from the authorization, code, tests, domain docs, or ADRs does the question go back to the user via `/grill-with-docs`.

## 1. Establish the control plane

1. Read repository instructions, candidate sources, and domain docs; confirm a safe branch/worktree and pin `batch_base = HEAD`.
2. Create the **batch ledger** in the configured tracker (per repository contracts such as `docs/agents/issue-tracker.md`); with no tracker, write it to an out-of-repo workfiles directory (e.g. `~/.local/share/agent-workfiles/<repo>/tracker/<batch-slug>/batch.md` — outside the repo, never committed). Store source IDs, states, dependencies, `derived_from` / `sources`, commits, verification, deviations, and user authorization (scope and release).
3. States are exactly `queued | planning | ready | landed | rejected | deferred | merged | blocked`. `merged` must point at a composite work item; `blocked` is nonterminal. Only the supervisor updates the ledger.

Done when: every source is in the ledger, `batch_base` resolves, and the checkout's provenance is known.

## 2. Autonomous audit and ordering

Dispatch independent read-only agents in parallel to audit non-overlapping candidates, returning friction, dependencies, payoff, behavior surface, tests, disposition, effort, and evidence paths.

The supervisor adjudicates the evidence and sets the accepted set, blocking edges, and order: accepted items go to `planning`; invalid premises → `rejected`; payoff that depends on future needs → `deferred` with a written trigger. The `frontier` is the set of `ready` work items whose blockers are all `landed`; when a blocker is rejected/deferred, re-audit its dependents first.

Merging candidates creates a composite work item with `sources=[source IDs]`, original rows marked `merged → composite`; split tickets each record `derived_from=<source ID>`. Every commit maps to a work item and its sources. A `merged` source is satisfied only once its composite is `landed`. After batch authorization, ordering needs no further confirmation.

Done when: every source has an evidence-backed disposition and the ledger can compute the frontier and source mapping.

## 3. Produce self-contained briefs

Pick the single-context or spec/tickets branch for the next `planning` item in order. The planning agent assembles decisions, artifacts, and the writer brief; it writes no production code.

A writer brief contains goal/evidence, HEAD, ownership, dependencies, behavior baseline, test seams, acceptance/verification commands, Matt skills, decision authority, and escalation conditions. The item becomes `ready` only when the supervisor accepts that the brief can be started without follow-up questions.

Done when: the ledger points at the needed artifacts and the brief is acceptable within one fresh context.

## 4. Writer loop

One writer at a time on a shared checkout; parallelize only with isolated worktrees, non-overlapping ownership, and a clear integration order. The brief states the writer is not the only agent and must not roll back others' changes.

The writer re-verifies premises and completes one work item with `/implement` and `/tdd` on the agreed seams; runs byte-for-byte comparison on outputs promised unchanged, targeted tests, the full suite, the repository's existing guard scripts, and smoke checks; then clears blocking findings via `/code-review` before committing. It returns only commit SHAs, verification, review, deviations, and artifact pointers.

The supervisor verifies commits, the working tree, ownership, and source mapping before updating the ledger. A candidate is `landed` only when all its tickets have landed and the candidate-level acceptance commands declared in the brief are green.

## 5. Self-repair

| Trigger | Supervisor action | Recovery condition |
|---|---|---|
| Premise invalid | `rejected`, or `deferred` with a trigger | Evidence in ledger |
| Test, byte-comparison, or review failure | Freeze the frontier; a diagnosis agent isolates one falsifiable root cause, a fresh writer fixes and reruns all Writer-loop gates | All gates green |
| Worker left dirty state / no commit | Freeze the frontier, a repair agent takes over; no reset, no overwriting unknown changes | Checkout explainable |
| Subagents unavailable | Store the brief in the ledger and hand it to a handoff-class skill or a user-opened fresh session; the main session does not take over implementation; with no handoff path, mark `blocked` | New context takes over |
| Repair without new evidence | Mark `blocked`, record failures/excluded hypotheses; freeze frontier, review, delivery, and release | Original gates recover, or the user explicitly re-scopes |

One root cause per loop; continue only on new evidence — new evidence = a new falsifiable root-cause hypothesis, or a previously unobserved failure fact. Two consecutive loops without gates turning green mark the work item `blocked`; no third loop. Changing a `blocked` item's disposition is the user's call alone; batch authorization does not cover it.

## 6. Batch review and delivery

Only when no `blocked` exists and every original source is `landed | rejected | deferred` (or its composite is `landed`) does the batch-level `/code-review` run over `batch_base...HEAD`. When `blocked` cannot recover autonomously, degrade to a terminal report: per-source status, evidence, and freeze reasons, with disposition options attached (re-scope the behavior change, `deferred`, `rejected`); batch review, delivery, and release stay frozen pending the user's ruling. Review Standards and each spec/ledger in parallel; factual findings go to writers, in-scope judgment calls are the supervisor's per goals, ADRs, and tests. Rerun review, the full suite, guards, and smoke until no blocking finding remains.

Release only when the batch review is green **and** the ledger records a release authorization, executing exactly the authorized release action per the repository's release docs and verifying the user-visible version; otherwise stop at local commits. Report per source: disposition, work-item/commit mapping, deviations, verification, and delivery state.

Done when: no `blocked`, source mapping closed, working tree explainable, batch review and verification green, delivery matches authorization.

## 🔴 ESCALATION GATE · STOP

Ask the user only when a deliberate user-visible behavior change is required, scope extends beyond the list, an unauthorized destructive/external action is needed, several product answers cannot be adjudicated by evidence, or the batch is frozen on `blocked` with no autonomous recovery path; everything else is the supervisor's decision — keep going.

## Guardrails

- The main session keeps only the ledger / summaries; deep reads, logs, and implementation stay in subagents.
- Shared checkouts write serially; parallelize only when isolated and ownership does not overlap.
- A failed byte gate goes to repair; green tests cannot substitute for it.
- Candidates without evidence at audit time go to rejected/deferred; failed repairs go to `blocked`, never unfrozen via deferred. Never force code changes to complete a batch.
