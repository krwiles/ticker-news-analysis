# Raw HTTP via `httpx`, not provider SDKs (Finnhub, OpenAI)

`providers.py` has never used an official client library for any external API, even where one exists
(Finnhub's, OpenAI's) — every provider call is a raw `httpx` request. Never explicitly decided in one place
until now; surfaced when planning lesson 18's OpenAI integration.

Decision: keep using raw `httpx` for every provider, including ones with an official SDK.

## Considered options

- **The official SDK per provider** (`finnhub-python`, `openai`): less boilerplate, provider-maintained retry/
  auth/parsing, typed responses. The default choice for most production systems.
- **Raw `httpx` for every provider** (chosen): `httpx` is explicitly named in `MISSION.md`'s own stack list —
  the point is hands-on fluency with a raw async HTTP client, not a provider's abstraction over one. SEC EDGAR
  has no official SDK at all, so raw HTTP is already forced for at least one provider; using SDKs for the
  others would leave `providers.py` with two different integration patterns for the same kind of call.

## Consequences

- Every provider function shares one shape (`client: httpx.AsyncClient` in, `ProviderFetchError` on failure, a
  normalized dict out) — true of `get_company`, `fetch_edgar_filings`, `fetch_finnhub_news`, and now
  `get_embeddings` (batched, per lesson 18's live latency finding — see ADR 0007's revised Consequences),
  specifically because none of them special-case a provider's own SDK conventions.
- `respx` (this project's test-mocking library) mocks at the `httpx` transport layer — one mocking strategy
  covers every provider test in `test_providers.py`. An SDK-based provider would need its own, different mocking
  approach, since most SDKs don't route through `httpx` internally.
- Real cost, not free: no provider-maintained retry/backoff, rate-limit handling, or typed responses — each
  provider function hand-rolls its own error handling and response parsing.
- Not a universal claim that raw HTTP beats SDKs — for a production system, the official SDK is often the more
  pragmatic choice. This is specific to what this project is for: EDGAR's forced constraint, the uniform-shape
  and `respx` payoffs above, and the project's repeated, explicit preference for learning depth over convenience
  (same reasoning behind ADR 0004's ARQ job and ADR 0005's real test suite).
