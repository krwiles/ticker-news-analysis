# Plan 0033 — a secret scanner in the pre-commit hook and CI

Not a lesson, no spec/ADR — same "infra, not user-facing behavior" reasoning as plan 0015's CI setup.
Picks up the idea flagged in `NOTES.md` (2026-09-21): the repo is public, and going forward (OAuth
client secret, session-signing key) more sensitive values are coming than the two API keys today.

## Tool choice: Gitleaks, not TruffleHog

Researched rather than assumed. Gitleaks is regex-based (matches known secret *shapes*), fully
offline, and has a maintained GitHub Action with SARIF output and TOML-based allowlisting —
well-suited to a fast, blocking local hook plus a CI backstop. TruffleHog's differentiator is live
credential verification (confirms a found secret still works), which needs network calls per scan
and is aimed at cutting triage volume on noisy repos with many findings — not this project's shape
(two keys today, a handful more coming). One tool, not both, matches ADR 0003's own
don't-pre-optimize-at-personal-project-scale precedent.

## Baseline

Ran `gitleaks detect --source . --log-opts="--all"` (full history, all 87 commits) before wiring
anything blocking: **zero leaks, zero false positives** — including against `.env.example`'s
placeholders and the test suite's `"test-key-not-real"` strings scattered through `monkeypatch`
calls, none of which match a real provider key's shape. No `.gitleaks.toml` allowlist file needed
yet; add one only if a real false positive shows up (same "don't build it until it's needed"
instinct as plan 0015's "no linter yet").

## What gets built

- **`.githooks/pre-commit`**: a second blocking step, `gitleaks protect --staged --no-banner`,
  scanning only staged changes (fast, matches `check_comment_length.py`'s own scope).
- **`.github/workflows/ci.yml`**: a new `secret-scan` job using `gitleaks/gitleaks-action@v2`
  (the maintained action) against the full checked-out history on every push/PR — the backstop for
  anyone who hasn't run `git config core.hooksPath .githooks` locally.
- **`README.md`**: `gitleaks` added to the prerequisites table (`brew install gitleaks` on macOS,
  matching `dbmate`'s own entry) and to the "Optional: development setup" section alongside the
  existing hook line.

## Deliberately out of scope

- No `.gitleaks.toml` (see Baseline above).
- No rewriting git history — nothing found to remove; if a real key is ever committed, the fix is
  revoking it in the provider's dashboard, not rewriting a public repo's history (NOTES.md already
  says this).
- No branch-protection rule requiring the new CI job to pass — same reasoning plan 0015 gave for not
  wiring that up immediately: watch it run green for real first.

## Verification

1. Local hook: stage a fake-looking secret (a throwaway file, never committed), confirm
   `gitleaks protect --staged` catches it and the commit is blocked; remove it, confirm a clean
   commit goes through.
2. CI: push and watch the new `secret-scan` job run green on GitHub's runners for real, same
   "watch it run, don't just trust the YAML" discipline plan 0015 used for `backend-tests`.

## What actually happened

Built as planned. One real finding during verification, not anticipated: a first attempt to verify
the hook used a synthetic OpenAI-shaped key (`sk-proj-<random>`) and gitleaks correctly did **not**
flag it — its `openai-api-key` rule requires the real format's embedded `T3BlbkFJ` marker (base64 for
"OpenAI"), which a merely `sk-`-prefixed random string doesn't have. Confirmed the tool actually works
with a Finnhub-shaped fake instead (`FINNHUB_API_KEY=...`) — gitleaks ships a dedicated
`finnhub-access-token` rule, and it caught it immediately (blocked, exit 1); removing it let a clean
commit through.

Also caught, live: the first verification attempt was committed directly to `main` instead of a
branch — a real process mistake, not a tool one. Reverted (`git revert`, not a history rewrite) rather
than force-cleaned, since a hard reset was correctly refused as an irreversible local operation;
local `main` now carries two extra no-op commits (the mistake + its revert) that `origin/main`
doesn't have, to be reconciled the next time local `main` syncs with a merged PR.

CI: `secret-scan` job added to `ci.yml` using `gitleaks/gitleaks-action@v2` against full history
(`fetch-depth: 0`) — not yet watched running green on GitHub's own runners (that happens once this
branch is pushed and opened as a PR, same as plan 0015's own verification step 2).
