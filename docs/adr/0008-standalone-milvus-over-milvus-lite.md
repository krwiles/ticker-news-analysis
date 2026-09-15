# Standalone Milvus, not Milvus Lite — chosen for deployment exposure, not data volume

This project's actual data volume (personal-scale headline embeddings) comfortably fits within Milvus Lite's
documented comfort zone (under ~1M vectors, per direct research) — by data-volume reasoning alone, Lite is the
objectively simpler, sufficient choice: `pip install pymilvus`, no separate server, no new containers.

Decision: standalone Milvus anyway (docker-compose, `etcd` + `MinIO` sidecars) — deliberately, for hands-on
exposure to a more production-shaped vector-database deployment, a real stated learning goal of this project
(`MISSION.md`), not because the workload needs it.

## Considered options

- **Milvus Lite** (embedded, no separate server): simplest, zero new containers — but teaches nothing about
  running Milvus as a real service, which is the actual point of this project existing.
- **Zilliz Cloud** (managed, permanent free tier — not a trial): zero local infrastructure at all, but also
  teaches nothing hands-on about self-hosting.
- **Standalone via docker-compose** (chosen): real infrastructure — two sidecar services, healthchecks, named
  volumes, a real resource footprint — genuine scalability/deployment exposure, at real setup cost.

## Consequences

- Real, non-trivial resource footprint — Milvus' own docs recommend 8GB+ RAM for standalone, on top of
  everything else already running locally (`db`, `redis`, `api`, `ui`, `worker`).
- Two new dependency services (`etcd`, `minio`) this app never talks to directly, existing purely to support
  `milvus` itself.
- This choice already cost something real, found live: the official reference deployment config had a broken
  image reference by the time it was actually used (MinIO archived its OSS edition and pulled `minio/minio`
  from Docker Hub entirely, lesson 16) — a cost Milvus Lite or Zilliz Cloud wouldn't have carried. Accepted
  anyway, and arguably itself an on-brand lesson about operating real infrastructure, not a reason to reverse
  the decision.
- Partitioning — Milvus' actual scalability feature — is named as a deliberate future option, not built now;
  plain scalar-field filtering is enough for this project's real scale. Standalone was chosen for the
  deployment exposure specifically, not because partitioning is needed yet either.
