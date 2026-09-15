# OpenAI's embeddings API generates Story-matching vectors, not Cohere or a local model

ADR 0006's grouping mechanism needs a way to turn a headline's text (`title` + `summary`, when present — see
spec 0002) into a vector for similarity comparison. Real options exist across a genuine cost/latency/complexity
spread, researched directly rather than assumed.

Decision: OpenAI's embeddings API.

## Considered options

- **Cohere's embed API**: comparable per-token pricing to OpenAI, but its trial API key is capped at 5
  calls/min and explicitly not intended for production use — a real constraint on this project's own batch
  fetch pattern, not just a inconvenience. Would need a paid key to use seriously.
- **A local model** (`sentence-transformers`, run in-process): zero per-call cost, no external API or secret to
  manage, lowest latency (no network hop). Rejected because its inference is CPU-bound and synchronous, while
  the code that will call it — `fetch_and_persist_headlines`, the existing ARQ job — is fully async. Calling it
  directly would block the event loop for that call's duration, needing an explicit thread-pool-executor
  workaround (`run_in_executor`) — a pattern this project named as a real gap (lesson 8) but has never actually
  built. A legitimate way to finally build that pattern, but a real cost, not a free lunch.
- **OpenAI's embeddings API** (chosen): a genuine async HTTP call, the same integration shape
  `providers.py`'s existing EDGAR/Finnhub calls already use — fits directly into the job's existing
  `asyncio.gather` pattern with zero new async-handling complexity. Cost is negligible at this project's
  volume (~$0.02–0.04/month at realistic headline volume, per direct research, not a guess). Also sets up
  shared infrastructure (API client, secret management) a likely future sentiment-analysis spec will reuse.

## Consequences

- A third external network dependency (alongside EDGAR, Finnhub) now sits inside the fetch job's existing
  timeout budget (`job_timeout_seconds`, ADR 0004) — worth verifying live once real embedding latency exists to
  measure, not assumed fine in advance.
- `OPENAI_API_KEY` joins `FINNHUB_API_KEY` as a required secret for the app to fully function.
- The CPU-bound-work-off-the-event-loop pattern (`run_in_executor`) stays unbuilt by this decision — a
  deliberate deferral, not a closed door, if a future feature needs it for a genuinely CPU-bound task.
