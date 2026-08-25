---
description: Create a phase-level master spec and phase branch for Audience Match
argument-hint: "Phase number and phase name, e.g. 1 segmenter-agent"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(git:*)
---

You are a senior AI architect spinning up a new development phase for the
Audience Match multi-agent platform. Always follow the rules in `CLAUDE.md`
and the phase definitions in `Audience_Match_Implementation_Blueprint.md`.

A **master spec** covers an entire phase (e.g. Phase 1 — Segmenter Agent).
It does not contain implementation detail — it defines scope, dependencies,
contracts, evaluation gates, and the checklist of features that will each
get their own spec via `/create-feature-spec`. Nothing in this phase should
be implemented directly from the master spec; every feature needs its own
spec first.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status`. If anything is uncommitted, unstaged, or untracked, stop
and tell the user to commit or stash before proceeding. Do not continue
until clean.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:

1. `phase_number` — zero-padded to 2 digits: `1` → `01`, `12` → `12`
2. `phase_title` — human readable, Title Case (e.g. "Segmenter Agent")
3. `phase_slug` — kebab-case, a-z/0-9/- only, max 40 chars (e.g. `segmenter-agent`)
4. `branch_name` — `phase/<phase_number>-<phase_slug>` (e.g. `phase/01-segmenter-agent`)

If these can't be inferred confidently, ask the user before proceeding.

## Step 3 — Validate against the blueprint
Read `Audience_Match_Implementation_Blueprint.md`. Confirm `phase_number`
corresponds to a real phase (0–15) and that `phase_title`/`phase_slug`
reasonably match that phase's name in the blueprint (e.g. phase 1 should
be Segmenter-related, not Aggregator-related). If there's a mismatch, warn
the user and ask them to confirm before continuing — don't silently rename
their input to match the blueprint.

## Step 4 — Enforce build order (critical — do not skip)
Per `CLAUDE.md` §2, phases have a required build order:
`0 → 1 (Segmenter) → 2 (RAG) → 3 (Aggregator) → 6/7 (Memory/Guardrails, can
parallel) → 4 (Supervisor) → 5 (Campaign Briefing) → 8+ (cross-cutting)`.

- If `phase_number` is `00`, skip this check.
- Otherwise, determine the phase(s) that must precede it per the blueprint's
  build order (not just phase_number - 1 — Phase 4 depends on 1, 2, and 3
  being complete, not on Phase 3 alone; Phase 5 depends on 1, 2, 3, and
  ideally 4).
- For each prerequisite phase, check `.claude/specs/Phase<NN>/master.md`
  exists and its **Definition of Done** section is fully checked off.
- If any prerequisite is missing or incomplete, **stop** and tell the user
  exactly which phase(s) are blocking, and why (quote the relevant build
  order rule from CLAUDE.md §2). Do not create the spec. The user must
  either complete the prerequisite or explicitly override — if they
  explicitly say to proceed anyway, note the override at the top of the
  spec under a "⚠️ Build Order Override" heading with their stated reason.

## Step 5 — Check branch name is not taken
Run `git branch -a`. If `branch_name` is taken, append `-01`, `-02`, etc.

## Step 6 — Switch to main and pull latest
```
git checkout main
git pull origin main
```

## Step 7 — Create and switch to the phase branch
```
git checkout -b <branch_name>
```

## Step 8 — Research before writing
Read, in this order:
- `CLAUDE.md` — non-negotiable rules, repo structure, agent contract pattern
- `Audience_Match_Implementation_Blueprint.md` — the section for this exact phase
- `.claude/specs/**/master.md` — all prior master specs, to understand what
  contracts, storage, and infra already exist and avoid redefining them
- `.claude/specs/**/feature*.md` — skim titles only, to avoid scope overlap
- Relevant existing code under `app/` for this phase's agent(s), if any
  already exists

## Step 9 — Write the master spec
Generate the spec with this exact structure:

---
```markdown
# Master Spec — Phase <phase_number>: <phase_title>

## Status
`Not Started` | `In Progress` | `Complete` — update as work progresses.

## Overview
2–3 sentences: what this phase delivers, and why it sits at this point in
the build order (reference CLAUDE.md §2 / blueprint sequencing rationale).

## Position in Build Order
- **Depends on (must be complete):** [list phases + one-line reason each]
- **Blocks (cannot start until this is done):** [list phases that depend on this one]

## Scope
Bullet list of everything in scope for this phase, drawn from the blueprint
section for this phase. This list becomes the checklist of features that
will each get a `/create-feature-spec`.

## Out of Scope
Explicitly list anything adjacent that is NOT part of this phase, to
prevent scope creep into later phases.

## Agent / Module Contracts Touched
For each agent or module this phase creates or modifies:
- Agent/module name
- New or changed Pydantic schemas (name only at this level — detail lives
  in feature specs)
- Whether this is a new agent (needs full `AgentInput`/`AgentOutput` pair
  per CLAUDE.md §5) or a modification to an existing one

## Data & Storage Touched
- **Pinecone:** namespaces created/used, embedding model, dimension
- **PostgreSQL:** tables created/modified, and whether the read-only role
  (`app_readonly`) needs updated grants
- **DynamoDB:** tables/keys created or used
- **S3:** buckets/prefixes involved

## LLM Usage in This Phase
Table of task → model tier, to be registered in `app/llm/model_router.py`
`ROUTING_TABLE` (per CLAUDE.md §4 rule 2):

| Task | Model tier | Notes |
|---|---|---|
| ... | haiku / sonnet | ... |

## Guardrails Required
Which items from `CLAUDE.md` §6 checklist apply to this phase, and any
phase-specific additions (e.g. SQL guard is Aggregator-specific).

## Evaluation Requirements
- Golden dataset file(s) to be created/extended:
  `eval/golden_datasets/<name>_eval.jsonl`
- Minimum case count for this phase (per blueprint §12.1 sizing guidance)
- Metrics and **gating thresholds** that must pass in CI before phase is
  considered done (pull exact numbers from CLAUDE.md §7 table if this
  phase's agent is listed there; otherwise define new ones consistent with
  the blueprint's Definition of Done for this phase)

## Observability Requirements
- LangSmith tags this phase's chains must set (`agent`, `prompt_version`, etc.)
- Any new cost-tracking or alerting needs specific to this phase

## Feature Specs Index
_Populated automatically by `/create-feature-spec` as features are created.
Do not edit manually._

| # | Feature | Spec file | Status |
|---|---|---|---|
| _(none yet)_ | | | |

## Definition of Done (Phase Gate)
Copy the exact gate from `Audience_Match_Implementation_Blueprint.md` §21
for this phase, expressed as a checked/unchecked list. This is what Step 4
of future master-spec runs will check before allowing dependent phases to start.

- [ ] All features in Scope above have specs and are implemented
- [ ] [phase-specific quantitative gate(s) from the blueprint]
- [ ] Eval script(s) passing at the threshold(s) defined above
- [ ] Guardrail adversarial tests passing (if applicable to this phase)
- [ ] No unresolved items in Risk Register (blueprint §22) attributable to this phase
```
---

## Step 10 — Save the spec
Create the directory if needed and save to:
`.claude/specs/Phase<phase_number>/master.md`

## Step 11 — Report to the user
Print a short summary in this exact format:
```
Phase:      <phase_number> — <phase_title>
Branch:     <branch_name>
Spec file:  .claude/specs/Phase<phase_number>/master.md
Depends on: <list, or "none">
```

Then tell the user:
"Review the master spec, then run `/create-feature-spec` for each item in
the Scope section — one feature spec per item, in the order that makes
sense given their internal dependencies. Do not begin implementation from
the master spec directly."

Do not print the full spec in chat unless explicitly asked.