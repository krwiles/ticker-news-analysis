# Independently reasoned through ARQ's fleet-level (not per-instance) liveness limitation

Given the mechanics of ARQ's cron-job dedup (only one worker claims each scheduled tick) and Redis `SET`
overwriting a single key, the user correctly predicted — unprompted, before being told — that scaling to
multiple workers would still produce only one heartbeat key, and that this means the existing `/health` design
can only ever answer "is at least one worker alive," not "are all N workers alive." This is a non-obvious
distinction (fleet-level vs. instance-level liveness) that most people conflate. Future lessons on
worker/orchestration topics can build directly on this — no need to re-explain why a shared cron heartbeat
doesn't give per-instance visibility, or that per-instance liveness is usually the orchestrator's job
(Docker/Kubernetes), not something to reinvent at the application level.
