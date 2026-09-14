# Lesson 15 plan — Continuous integration with GitHub Actions (opens Arc 3)

Scope: `NOTES.md`'s lesson 15, the first lesson of Arc 3 (infra/deployment), opened after a tech-stack audit
identified GitHub Actions as the lowest-effort unused item from the original stack — both test suites already
exist and pass; this wires them into CI, it doesn't build anything new.

Investigated before planning, not assumed: `backend/tests/conftest.py` documents that tests run on the host
against `localhost` Postgres, never inside a container — the exact shape a CI job naturally provides via a
service-container sidecar. No test needs real secrets — every provider HTTP call in `test_providers.py` is
`respx`-mocked, and `config.py`'s `finnhub_api_key`/`sec_edgar_user_agent` defaults are sufficient otherwise.
`dbmate` has no version pin anywhere in this repo currently (confirmed via `which`/`--version` — `2.35.1`
locally, installed via Homebrew, not recorded in any tracked file). `frontend/package.json` has no `engines`
field pinning a Node version.

## Decisions confirmed with the user (2026-09-14)

1. **Full lesson ceremony** — a numbered lesson (15), a lesson HTML file, this plan doc, opening a new Arc 3 in
   `NOTES.md` — not just a bare config change. GitHub Actions is a genuine original "insider stack" item (per
   the `nvidia-vulnops-portfolio-stack` project memory), same category as ARQ or SQLAlchemy, not devops
   config to slip in unremarked.

## What gets built

**One workflow, three independent jobs**, all triggered on every push and PR (no path-based conditionals —
matches this project's own "personal-project scale, don't pre-optimize" instinct, same reasoning ADR 0003 used
to skip caching logic):

**1. `frontend-tests`** — no services needed (every frontend test already mocks its network boundary via
`vi.stubGlobal`/`vi.mock`, confirmed by re-reading `search.test.ts`/`SearchPage.test.tsx`). Node 24 (matching
`Dockerfile`'s `FROM node:24-alpine AS frontend-build` exactly, not an arbitrary different version):
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 24, cache: npm, cache-dependency-path: frontend/package-lock.json }
- run: npm ci
  working-directory: frontend
- run: npm run typecheck && npm run test && npm run build
  working-directory: frontend
```

**2. `backend-tests`** — a Postgres service container pinned to `postgres:17-alpine` (matching
`docker-compose.yml`'s real `db` service exactly), `ticker`/`ticker`/`ticker_test` to match
`conftest.py`'s own documented default connection string with zero env-var overrides needed, `dbmate` 2.35.1
installed via its published Linux release binary, then:
```yaml
services:
  postgres:
    image: postgres:17-alpine
    env: { POSTGRES_USER: ticker, POSTGRES_PASSWORD: ticker, POSTGRES_DB: ticker_test }
    ports: ["5432:5432"]
    options: >-
      --health-cmd pg_isready --health-interval 5s --health-timeout 3s --health-retries 10
steps:
  - uses: astral-sh/setup-uv@v4
  - run: curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/download/v2.35.1/dbmate-linux-amd64 && chmod +x /usr/local/bin/dbmate
  - run: dbmate --url "postgres://ticker:ticker@localhost:5432/ticker_test?sslmode=disable" up
  - run: uv run pytest
    working-directory: backend
```

**3. `docker-build`** — `docker build .`, validating the real multi-stage build (ADR 0001) still succeeds. No
services needed; not pushed anywhere — no registry target exists yet, this is a build-succeeds check only.

**Deliberately out of scope, named explicitly rather than silently skipped:**
- No linter/formatter wiring — none exists on either side of this repo yet; introducing one is its own
  decision (which linter, what rules), not a CI-wiring task.
- No live end-to-end smoke test (bringing up all 5 compose services, hitting a real `/api/search`) — would need
  a real Finnhub key as a GitHub secret and meaningfully more complexity. The existing mocked suites are this
  pass's actual regression coverage.
- No branch protection rule requiring the workflow to pass — a separate, small decision; proposing to watch it
  run green a few times first before wiring that up.

## Verification

1. `frontend-tests` first — fastest to get green, no environment-mismatch risk (no external services).
2. `backend-tests` — watch it actually run green on GitHub's runners, not just trust the YAML looks right
   locally; a service-container Postgres genuinely behaves differently from a docker-compose one in some
   details (startup timing, networking) worth seeing for real.
3. `docker-build` — confirms the real Dockerfile still builds in CI's environment.
4. Optional: a README status badge once there's a real workflow run to link to.

## Open items

None outstanding — the one flagged item (full lesson ceremony vs. bare config) was resolved with the user.
