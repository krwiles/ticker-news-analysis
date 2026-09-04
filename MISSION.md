# Mission: The ticker-news-analysis tech stack

## Why
Build genuine, hands-on fluency with a specific tech stack (Python/FastAPI/SQLAlchemy/Postgres, Redis+ARQ, React/TypeScript/React Router/Tailwind/Webpack, Docker, Milvus) by actually building a real stock-ticker news app with it — not by copying boilerplate. The stack was sourced from a specific NVIDIA job listing so the learning has a concrete target: being able to speak to and work confidently in this exact combination of tools, e.g. in an interview or on the job.

## Success looks like
- Can explain why the walking skeleton runs one image in three modes (`ui`/`api`/`worker`) and can extend it correctly
- Can write a new FastAPI endpoint plus a SQLAlchemy model plus a migration, end to end, without copy-pasting from the existing code
- Can build a new React component/page using React Router conventions, translating cleanly from Angular concepts rather than memorizing React syntax by rote
- Can explain ARQ's job/cron model and add a new background job correctly
- Can explain how docker-compose wires the five services together (networking, healthchecks, env vars) and modify the compose file confidently

## Constraints
- Learner has an Angular background (fluent with Angular 21 conventions: standalone components, signals, the `@if`/`@for` control-flow syntax, zoneless change detection). Teach React *against* that — map to the nearest current Angular concept rather than starting from zero or reaching for outdated Angular idioms (NgModules, heavy RxJS) the learner may not even use anymore.
- Learning happens alongside active build sessions on the real project — this isn't a separate isolated study track. Lessons should stay tied to what's actually in the repo, not generic tutorials.

## Out of scope (for now)
- Kubernetes, OpenShift, ArgoCD, Vault — deferred project-wide, see `nvidia-vulnops-portfolio-stack` project memory
- Milvus / vector search — no container for it yet, comes with the embedding-dedup feature later
- Kaizen UI (NVIDIA's design system) — not wired in yet, skeleton uses plain Tailwind
- The actual news/ticker domain model (entities, workflows) — the `grill-with-docs` domain-modeling round for that hasn't happened yet; this workspace teaches the *technology*, not the *product*
