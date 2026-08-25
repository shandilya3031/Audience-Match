---
description: Create a feature-level spec and feature branch within an Audience Match phase
argument-hint: "Phase number, feature number, feature name e.g. 1 2 clustering-pipeline"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(git:*)
---

You are a senior AI engineer breaking a phase down into an implementable
unit of work for the Audience Match multi-agent platform. Always follow
the rules in `CLAUDE.md`. A feature spec is the only document Claude
should ever implement directly from — it must be concrete enough to code
against without re-deriving decisions.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status`. If anything is uncommitted, unstaged, or untracked, stop
and tell the user to commit or stash before proceeding.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:

1. `phase_number` — zero-padded 2 digits
2. `feature_number` — zero-padded 2 digits, sequential within the phase
   (check existing files in `.claude/specs/Phase<phase_number>/` to find
   the next unused number if the user didn't specify one explicitly)
3. `feature_title` — Title Case (e.g. "Clustering Pipeline")
4. `feature_slug` — kebab-case, a-z/0-9/-, max 40 chars (e.g. `clustering-pipeline`)
5. `feature_branch` — `feature/<phase_number>-<feature_number>-<feature_slug>`
   (e.g. `feature/01-02-clustering-pipeline`)

If any of these can't be inferred confidently, ask before proceeding.

## Step 3 — Verify the phase master spec exists
Check `.claude/specs/Phase<phase_number>/master.md` exists. If it doesn't,
**stop** and tell the user to run `/create-master-spec <phase_number> ...`
first. Do not create a freestanding feature spec with no parent phase.

Read the master spec fully. Confirm `feature_title` corresponds to an item
in its **Scope** section (fuzzy match is fine — "Clustering" matching
"4 clustering algorithms" is expected). If it doesn't obviously map to
anything in Scope, ask the user to confirm this is intentional (net-new
scope not anticipated by the master spec) before continuing — note this
explicitly in the spec under "⚠️ Not in original phase scope" if confirmed.

## Step 4 — Get on the right branch
Determine the phase branch name from context (it should match the pattern
`phase/<phase_number>-*` — find it via `git branch -a` if not already
checked out).

- If the phase branch exists locally, check it out and pull.
- If it exists only on origin, check it out from there.
- If it doesn't exist at all, **stop** — the master spec step should have
  created it. Tell the user something is inconsistent and to investigate
  before proceeding.

```
git checkout <phase_branch>
git pull origin <phase_branch>
```

## Step 5 — Check feature branch name is not taken
Run `git branch -a`. If `feature_branch` is taken, append `-01`, `-02`, etc.

## Step 6 — Create the feature branch off the phase branch
```
git checkout -b <feature_branch>
```
This branches off the **phase branch**, not `main` — features within a
phase integrate against each other before the whole phase merges.

## Step 7 — Research before writing
Read, in this order:
- `.claude/specs/Phase<phase_number>/master.md` — the parent spec; scope,
  contracts, storage, eval thresholds, LLM routing table for this phase
- `CLAUDE.md` — non-negotiable rules (§4), agent contract pattern (§5),
  guardrail checklist (§6), eval format (§7), common playbooks (§8)
- `Audience_Match_Implementation_Blueprint.md` — the detailed subsection
  for this feature within the phase (e.g. §5.2 "Clustering Pipeline")
- Other feature specs already in `.claude/specs/Phase<phase_number>/` —
  avoid duplicating scope or contradicting decisions already made
- Existing relevant code under `app/agents/<agent>/`, `app/memory/`,
  `app/guardrails/`, etc. — don't redesign something already implemented

## Step 8 — Write the feature spec
Generate the spec with this exact structure:

---
```markdown
# Feature Spec — Phase <phase_number>.<feature_number>: <feature_title>

## Status
`Not Started` | `In Progress` | `Complete`

## Parent Phase
Phase <phase_number> — see `.claude/specs/Phase<phase_number>/master.md`

## Overview
1 paragraph: what this feature does, and how it fits into the parent
phase's scope.

## Depends On
Other features (within this phase or a completed prior phase) that must
exist first. State "None" if this is a leaf feature with no internal deps.

## Agent I/O Contract
If this feature creates or modifies an agent boundary, define the exact
Pydantic schema per `CLAUDE.md` §5 pattern:

```python
class <X>Input(BaseModel):
    ...

class <X>Output(BaseModel):
    ...
```

If this feature is internal to an agent and doesn't cross an agent
boundary, state "No external contract — internal to <agent> agent" and
instead describe the function signature(s) being introduced.

## LLM Call Sites
For every new LLM call this feature introduces:

| Call site (function) | Task name in ROUTING_TABLE | Model tier | Structured output schema |
|---|---|---|---|

State "None" if this feature makes no LLM calls.

## Data & Storage Changes
- **Pinecone:** namespace, metadata fields added/used, filter patterns
- **PostgreSQL:** exact table/column DDL if new, or query patterns if existing
- **DynamoDB:** key format (must follow `{user_id}_{module}_{session_id}`
  convention from `CLAUDE.md` §4 rule 7 if this touches memory), item shape
- **S3:** paths/triggers if applicable

State "None" for any that don't apply.

## Guardrails Checklist
Copy the relevant items from `CLAUDE.md` §6, mark which apply to this
specific feature, and note where each is implemented:

- [ ] Input filtering — applies? Where implemented?
- [ ] SQL guard — applies? (Aggregator features only)
- [ ] Output is validated Pydantic, not raw text
- [ ] Citations/sources included for factual claims
- [ ] Similarity threshold check before generation (RAG-adjacent features)
- [ ] Synchronous faithfulness/grounding check before returning to user
- [ ] Adversarial test cases to add to `tests/e2e/`

## Golden Eval Cases to Add
Per `CLAUDE.md` §7 format — specify how many cases, in which file, and
what they cover:

- File: `eval/golden_datasets/<module>_eval.jsonl`
- Count: [N] new cases
- Categories covered: [list]
- Example case (at least one fully written out):
```json
{
  "id": "<module>_0NN",
  "query": "...",
  "expected_answer_contains": ["..."],
  "expected_sources": ["..."],
  "category": "...",
  "difficulty": "simple|medium|complex",
  "module": "..."
}
```

State "No eval additions — non-agent-facing change" only if genuinely true
(e.g. pure infra/tooling work).

## Files to Create
Every new file, with a one-line purpose each.

## Files to Modify
Every existing file that changes, with a one-line description of the change.

## New Dependencies
New pip packages, if any. State "None" if not applicable.

## Rules for Implementation
Quote the specific numbered rules from `CLAUDE.md` §4 that apply to this
feature (not all 10 — only the relevant ones), plus any feature-specific
constraints. Always restate:
- No raw `ChatBedrock()` outside `app/llm/bedrock_clients.py`
- No LLM call without a `ROUTING_TABLE` entry
- No free-text agent-to-agent handoffs — Pydantic only
- [any others relevant to this feature, e.g. SQL/cache/memory rules]

## Definition of Done
A specific, testable checklist — each item verifiable by running code,
not by inspection alone:
- [ ] [concrete behavior 1, e.g. "given CSV X, clustering produces ≥4 stable clusters with ARI ≥0.75 across 5 reseeded runs"]
- [ ] [concrete behavior 2]
- [ ] New golden eval cases pass
- [ ] Relevant guardrail checklist items above are implemented and tested
- [ ] Unit/integration tests added and passing
- [ ] No `CLAUDE.md` §4 or §9 rule violations (self-check before marking complete)

## Out of Scope
What this feature deliberately does NOT cover, to keep it a clean unit of work.
```
---

## Step 9 — Save the spec
Create the directory if needed and save to:
`.claude/specs/Phase<phase_number>/feature<feature_number>-<feature_slug>.md`

## Step 10 — Update the parent master spec's index
Edit `.claude/specs/Phase<phase_number>/master.md` — append a row to the
**Feature Specs Index** table:

```
| <feature_number> | <feature_title> | feature<feature_number>-<feature_slug>.md | Not Started |
```

Do not modify anything else in the master spec.

## Step 11 — Report to the user
Print a short summary in this exact format:
```
Phase:     <phase_number>
Feature:   <phase_number>.<feature_number> — <feature_title>
Branch:    <feature_branch>
Spec file: .claude/specs/Phase<phase_number>/feature<feature_number>-<feature_slug>.md
Depends on: <list, or "none">
```

Then tell the user:
"Review the feature spec, then enter Plan Mode with Shift+Tab twice to
begin implementation. Do not implement anything not covered by this spec
without updating it first."

Do not print the full spec in chat unless explicitly asked.