---
description: Commit, push, open a PR into the parent phase branch, merge it, and clean up after a feature is complete
argument-hint: none — run from the feature branch you want to ship
allowed-tools: Read, Edit, Bash(git:*), Bash(gh:*)
---

You are shipping a completed feature for the Audience Match platform. This command
only ever operates on a `feature/<phase>-<n>-<slug>` branch and only ever merges into
that feature's **parent phase branch** (`phase/<phase>-<slug>`) — never directly into
`main`. Per CLAUDE.md, a phase branch only merges to `main` once every feature in that
phase's master spec is `Complete` and the phase's Definition of Done gate is met; that
is a separate, deliberate action, not something this command does automatically.

## Step 0 — Preflight checks

```bash
gh --version
gh auth status
```
If either fails, **stop** and say exactly:
"gh CLI is not installed or not authenticated. Install it and run `gh auth login`
before running /ship-feature."

```bash
git branch --show-current
```
Store as `CURRENT_BRANCH`. It must match `feature/<phase_number>-<feature_number>-<slug>`
(e.g. `feature/00-02-llm-clients`). If it doesn't — e.g. you're on `main` or a
`phase/*` branch — **stop** and say:
"/ship-feature must be run from a feature/* branch. Currently on `<CURRENT_BRANCH>`."

## Step 1 — Resolve the target phase branch

Extract `phase_number` from `CURRENT_BRANCH`. Run `git branch -a` and find the branch
matching `phase/<phase_number>-*` (check local first, then `remotes/origin/`). Store
as `TARGET_BRANCH`.

If no matching phase branch exists, **stop** — this is an inconsistent repo state
(the feature branch should never have been created without a parent phase branch).
Tell the user to investigate before proceeding.

## Step 2 — Locate and read the feature spec

Find `.claude/specs/Phase<phase_number>/feature<feature_number>-*.md` matching
`CURRENT_BRANCH`. If it doesn't exist, **stop** and tell the user to run
`/create-feature-spec` first — there is nothing to ship without a spec.

Read it fully: `Overview`, `Files to Create`, `Files to Modify`, and
`Definition of Done`.

## Step 3 — Confirm Definition of Done

Check whether every item in the spec's `Definition of Done` checklist is already
marked `[x]`.

- If any are unchecked, **stop** and ask the user to confirm those items are
  actually done (or finish/verify them first) before shipping. Do not assume.
- Once confirmed complete, if the spec's `Status` isn't already `Complete`, update it
  to `Complete`, and update this feature's row in the parent
  `.claude/specs/Phase<phase_number>/master.md` Feature Specs Index to `Complete`.
  These edits get included in the commit — do not skip this bookkeeping step.

## Step 4 — Review and stage changes

```bash
git status
```
Review the output carefully. Never run `git add -A` or `git add .` blindly — stage
the specific files that belong to this feature (source files, tests, the spec files
just updated). If anything unexpected or suspicious shows up (an untracked `.env`,
credentials, files unrelated to this feature), stop and flag it to the user rather
than staging it.

```bash
git add <specific files>
```

## Step 5 — Generate commit message

```bash
git diff --staged
git log <TARGET_BRANCH>..HEAD --oneline
```

Generate a Conventional Commit message from the diff and the feature spec's
Overview:
- `feat:` new feature, `fix:` bug fix, `chore:` config or tooling, `docs:` documentation only

Rules:
- Lowercase, no period at the end, under 72 characters
- Describes what's now possible, not what the code does
- Good: `feat: add LLM client wiring with sonnet/haiku/fallback routing`
- Bad: `feat: added ChatBedrock instantiation to bedrock_clients.py`

## Step 6 — Commit

```bash
git commit -m "<generated-message>"
```
Report: "✓ Committed — `<message>`"

## Step 7 — Push feature branch

```bash
git push -u origin CURRENT_BRANCH
```
Report: "✓ Pushed — `<CURRENT_BRANCH>`"

## Step 8 — Create PR into the phase branch

```bash
gh pr create --base "<TARGET_BRANCH>" --head "<CURRENT_BRANCH>" --title "<title>" --body "<body>"
```

Title: plain English feature name, no Conventional Commit prefix.
Example: "Add LLM client wiring"

Body:
```markdown
## What this PR does
<one paragraph from the spec's Overview section>

## Changes
<bullet list from the spec's Files to Create / Files to Modify, one line each>

## Definition of done
<copy the Definition of Done checklist from the spec, all items checked [x]>

## How to test
<concrete verification commands/steps from the spec — e.g. specific pytest
invocations, manual import/CLI checks called out in its Definition of Done or a
Verification section. Never invent generic or unrelated steps.>
```

Capture the PR URL/number from the command output.
Report: "✓ PR created — `<PR URL>`"

## Step 9 — Merge the PR

```bash
gh pr merge <PR_NUMBER_OR_URL> --squash --delete-branch
```
This squash-merges into `TARGET_BRANCH` and deletes the remote feature branch in one
step.

Report: "✓ PR merged into `<TARGET_BRANCH>`"
Report: "✓ Remote branch deleted"

## Step 10 — Local cleanup

```bash
git checkout <TARGET_BRANCH>
git pull origin <TARGET_BRANCH>
git branch -D <CURRENT_BRANCH>
```
Report: "✓ Switched to `<TARGET_BRANCH>` — up to date"
Report: "✓ Local branch deleted"

## Step 11 — Phase-completion check (informational only)

Read `.claude/specs/Phase<phase_number>/master.md`'s Feature Specs Index. If every
row is now `Complete`, print a note:
"All features in Phase <phase_number> are now Complete. Review its Definition of
Done gate in master.md — if satisfied, consider opening a PR from
`<TARGET_BRANCH>` into `main` to close out the phase."

Do **not** open or merge that PR automatically — closing out a phase into `main` is
a separate, deliberate action for the user to trigger.

## Final summary

Print:
```
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
/ship-feature complete
✓ Committed — <message>
✓ Pushed — <CURRENT_BRANCH>
✓ PR created and merged into <TARGET_BRANCH>
✓ Remote branch deleted
✓ Switched to <TARGET_BRANCH>
✓ Local branch deleted
Next: run /create-feature-spec for the next feature, or close out the
phase if this was the last one.
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```

## Rules
- Never commit directly to `main` or to any `phase/*` branch — this command only
  runs from a `feature/*` branch.
- Always merge into the feature's **parent phase branch**, never directly into `main`.
- Always use squash merge.
- Always delete both the remote and local feature branch after merge.
- Never mark a feature spec `Complete` if its Definition of Done isn't fully
  checked — confirm with the user first, don't assume.
- Never blindly `git add -A` / `git add .` — review `git status` and stage
  intentionally.
- If `gh` is not installed or not authenticated, stop and say so — do not attempt to
  work around it.
- If push fails due to no upstream, `git push -u origin CURRENT_BRANCH` (already the
  default in Step 7) resolves it.
- Never proceed to merge if PR creation fails.
