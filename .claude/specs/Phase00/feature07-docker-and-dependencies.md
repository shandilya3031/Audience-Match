# Feature Spec — Phase 00.07: Docker & Dependencies

## Status
`Complete`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Packages the app into a multi-stage, non-root Docker image per blueprint
§16.2, and gets `docker build` succeeding — the last unstarted item in Phase
0's Scope, and a direct prerequisite of the phase's own Definition of Done
(`docker build` succeeds, container runs locally, `/health` returns 200).
`requirements.txt` itself already exists and is current (maintained
incrementally by every prior Phase 0 feature); this feature's only
dependency-related work is making sure it installs cleanly inside the image.

**Design note (three deviations from the blueprint's illustrative
§16.2 snippet, worked out here rather than copied verbatim):**
1. **Python version bumped to 3.13** (blueprint shows `python:3.11-slim`) —
   the actual dev `.venv` and every test run so far have been on Python
   3.13.5; matching that is safer than introducing an untested version in
   the one place it's never been verified.
2. **`curl` installed in the production stage** — `python:3.13-slim` doesn't
   include `curl` by default, but the blueprint's own `HEALTHCHECK` directive
   requires it. Without this the healthcheck would always fail.
3. **`CMD` uses `python -m uvicorn ...`** instead of bare `uvicorn` — the
   blueprint's production stage only copies `/usr/local/lib/python3.11`
   from the builder stage, not `/usr/local/bin`, so the `uvicorn` console
   script itself wouldn't exist in the final image. Invoking it as a module
   avoids needing to copy `/usr/local/bin` at all.
4. **CPU-only `torch` installed explicitly before `requirements.txt`**
   (discovered during the actual build, not anticipated when this spec was
   written) — the default Linux `torch` wheel pulls in the full NVIDIA CUDA
   toolkit as dependencies (2GB+ across several packages), which is dead
   weight: Groq handles all LLM inference remotely, the only local model is
   the CPU-run `sentence-transformers` embedding model from `00-04`.
   `pip install torch --index-url https://download.pytorch.org/whl/cpu` runs
   first so the later `pip install -r requirements.txt` is already satisfied
   for `torch` and never reaches for the GPU variant.
5. **Both pip install steps use a BuildKit cache mount on pip's own cache
   dir** (`RUN --mount=type=cache,target=/root/.cache/pip`, dropping
   `--no-cache-dir`) instead of the blueprint's plain `--no-cache-dir`
   install — downloaded wheels persist across separate `docker build`
   invocations even when a layer is invalidated/retried, since the mount
   isn't part of the image layer itself. Needed in practice: these installs
   are large (the CPU `torch` wheel alone is ~200MB) and the build was
   interrupted mid-download more than once during implementation.

**Current-state note:** `app/main.py`'s import chain (`routes_chat`,
`routes_health`) doesn't touch `app.config` yet — neither route module
imports it. That means the container can build and boot `/health` today
with **zero environment variables set**, no `.env` needed at runtime. This
will stop being true once a later phase wires config-dependent code (LLM
clients, DB, vectorstore) into `app.main`'s import path — worth knowing
going in, not a bug to fix now.

## Depends On
- `00-05-skeleton-fastapi-app` — supplies `app/main.py` and `/health`, what
  this feature's container-boot check actually exercises
- All other Phase 0 features indirectly, via `requirements.txt` — this
  feature packages whatever it currently contains, it doesn't add packages
  of its own

## Agent I/O Contract
No external contract — packaging/infra, not an agent boundary.

## LLM Call Sites
None.

## Data & Storage Changes
None — this feature doesn't touch Chroma, PostgreSQL, or local filesystem
storage. (It also does not wire Docker networking to the existing
`audience-match-postgres` container — see Out of Scope.)

## Guardrails Checklist
Not applicable — packaging/infra, no user-facing behavior change.

- [ ] Input filtering — N/A
- [ ] SQL guard — N/A
- [ ] Output is validated Pydantic, not raw text — N/A
- [ ] Citations/sources included for factual claims — N/A
- [ ] Similarity threshold check before generation — N/A
- [ ] Synchronous faithfulness/grounding check — N/A
- [ ] Adversarial test cases to add to `tests/e2e/` — N/A

## Golden Eval Cases to Add
No eval additions — non-agent-facing change.

## Files to Create

**`infra/docker/Dockerfile`**:
```dockerfile
FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim AS production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**`.dockerignore`** (repo root) — keeps the build context small and, most
importantly, guarantees `.env` and other local-only state never reach a
Docker layer even though `COPY . .` is otherwise broad:
```
.venv/
venv/
env/
.git/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
.env.*
!.env.example
data/
tests/
.claude/
```

## Files to Modify
None. `requirements.txt` is consumed as-is; nothing about this feature
requires changing it.

## New Dependencies
None — no new pip packages. (The image itself gains `curl` and `gcc`/`g++`
as OS-level packages, not Python dependencies.)

## Rules for Implementation
- **CLAUDE.md §4 rule 10** (no secrets in code): `.dockerignore` must
  exclude `.env` — verified as part of Definition of Done below, not just
  assumed from the `.dockerignore` file existing.
- **Blueprint §16.3**: "All [secrets] in GitHub Secrets → injected as ECS
  task environment variables at deploy time. Never in code, never in Docker
  layers." Not fully actionable yet (no CI/CD exists — that's Phase 12), but
  the `.dockerignore` exclusion is this feature's part of that guarantee.
- Repo structure placement: `infra/docker/Dockerfile`, matching the
  blueprint's own repo layout (§3) and this master spec's Scope wording.
- No raw `ChatGroq(...)` outside `app/llm/llm_clients.py` — unaffected,
  restated as a standing rule.

## Definition of Done
- [x] `docker build -f infra/docker/Dockerfile -t audience-match:local .`
      succeeds
- [x] `docker run -p 8000:8000 audience-match:local`, then `GET /health`
      against the mapped port returns `200` `{"status": "ok"}` — proof the
      container actually runs and serves traffic, not just that it built
- [x] The container runs as a non-root user (verify via
      `docker exec <container> whoami` → `appuser`, not `root`)
- [x] `.env` is confirmed absent inside the built image (e.g.
      `docker run --rm audience-match:local sh -c "test -f .env && echo FOUND || echo ABSENT"`
      → `ABSENT`) — concrete proof `.dockerignore` actually worked, not an
      assumption from the file existing
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check)

## Verification Record
Built and verified locally on 2026-09-03 (image built from the user's own
terminal after the tool-driven background build was repeatedly killed by
host memory pressure — see below):
- `docker build` — succeeded in 147.7s, all 19 steps, no cache misses on
  the OS-package layers
- `GET /health` → `200` `{"status":"ok"}`
- `docker exec <container> whoami` → `appuser`
- `.env`-absence check → `ABSENT`
- Final image size: **2.46GB** (`audience-match:local`) — expected, given
  `torch`/`transformers`/`chromadb`; no size reduction attempted, per Out
  of Scope

**Build-environment note:** the tool's own background-task execution path
could not get this build to complete — six consecutive attempts were
killed at inconsistent points (12s in, mid-download, one step from
finishing). Root-caused to host memory pressure, not the Dockerfile: the
dev machine had ~1.4GB free out of 15.67GB total at the time, with
Docker Desktop's WSL2 VM capped at 7.59GB competing for that headroom
against several other running processes. Under that little slack, a
`pip install` resolving `torch`/`transformers`/`chromadb` together is
memory-hungry enough during dependency resolution to trigger a kill —
consistent with the wildly inconsistent kill points observed (memory
pressure kills whenever a threshold is crossed, not at a deterministic
build step). The fix was operational, not a Dockerfile change: the user
ran the same build directly in their own terminal, which succeeded in
147.7s. No change was needed to `infra/docker/Dockerfile` or
`.dockerignore` as a result of this — both are exactly as designed.

## Out of Scope
- `docker-compose.yml` / wiring Docker networking between the app container
  and the existing `audience-match-postgres` container — not requested by
  the master spec's Scope wording (`requirements.txt` + `Dockerfile` only);
  `/health` doesn't need Postgres reachability to pass today (see
  Current-state note above)
- GitHub Actions / CI pipeline that actually runs `docker build` on every
  PR — Phase 12 (CI/CD Pipeline)
- Pushing the image to any registry (ECR, Docker Hub) — Phase 13
  (Deployment Architecture)
- Reducing image size (the ML dependencies — `torch`, `transformers`,
  `chromadb` — make this a large image; no attempt is made to slim that
  down here, e.g. via a CPU-only `torch` wheel or alternative embedding
  approach)
- Making `/health` do a deeper dependency check (DB/Chroma reachability) —
  already explicitly deferred in `feature05-skeleton-fastapi-app.md`
