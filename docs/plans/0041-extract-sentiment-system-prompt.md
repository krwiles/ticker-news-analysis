# Extract the sentiment system prompt into Settings

Not a planned lesson, no spec/ADR (implementation detail, same shape as plan 0039). Picks up the idea noted
2026-09-21 in `NOTES.md`: `sentiment.py`'s `_SENTIMENT_SYSTEM_PROMPT` was a hardcoded module string; the idea
left open whether to move it to `Settings` (env-configurable) or an external file.

## Decision: `Settings`, not an external file

Chosen for consistency with how every other piece of runtime-tunable, non-secret config already works in this
project (`config.py`'s `Settings` class, `pydantic-settings`, `.env`) — an external file would need its own
loading/reload logic for no real benefit here, since changing the prompt already only needs an env var change
and a container restart, not an image rebuild. That's what "without a code change/redeploy" in the original idea
meant in practice.

## Change

- `config.py`: new `sentiment_system_prompt: str` field on `Settings`, default set to the exact prior text.
- `sentiment.py`: `_SENTIMENT_SYSTEM_PROMPT` module constant removed; `get_sentiment` reads
  `settings.sentiment_system_prompt` instead.

## Tests

`test_sentiment.py`: `test_get_sentiment_sends_the_configurable_system_prompt` monkeypatches
`settings.sentiment_system_prompt` to a marker value and asserts the actual HTTP request body sent to OpenAI
carries it — proves the value flows through, not just that the field exists. Deliberate-break check (swapped the
real usage for a hardcoded string): the new test failed for exactly that reason, then reverted.

## Verification

124/124 backend tests, zero regressions. Live-verified against the real running stack: the rebuilt `worker`
container's default matches the original prompt text, and a one-off `docker compose run -e
SENTIMENT_SYSTEM_PROMPT=...` overrides it with no code change and no image rebuild.

## What actually happened during execution

Built exactly as scoped — no surprises. TDD followed: the new test failed with `AttributeError` (field didn't
exist yet) before the `Settings` field was added, then passed once both the field and the `sentiment.py` call
site were updated.
