# Corrected: assumed concurrent job creation requires multiple worker processes

Proposing a new sentiment-analysis background job alongside the existing fetch job, the user stated as
settled fact: "we will need to build more than one worker to do these jobs that we are creating
concurrently." This is a real, specific misconception about ARQ's actual concurrency model, not a vague
worry — corrected by checking the real library and this project's own config: ARQ's default `max_jobs` is
10, and `WorkerSettings` (`worker.py`) never overrides it, so a single worker process already runs up to 10
jobs *concurrently*, interleaved via asyncio, exactly what async/await is for. No second worker container is
needed just because jobs are created around the same time. Presented with this, the user accepted the
correction immediately ("you're right").

**Implication for future teaching**: `MISSION.md` names "explain ARQ's job/cron model" as a stated success
criterion. This specific misconception — that jobs running "concurrently" implies needing multiple OS
processes/containers — is a natural one coming from a non-async-native background, and is likely to recur
whenever another concurrency topic comes up (e.g. distinguishing async concurrency within one process from
true parallelism across processes or machines). Worth explicitly re-surfacing `max_jobs` and the
async-vs-parallel distinction if a future lesson ever actually scales the worker fleet, rather than assuming
one correction has permanently settled it.
