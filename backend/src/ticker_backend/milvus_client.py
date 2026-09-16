"""Milvus connection setup — see docs/specs/0002-daily-story-grouping.md.

Standalone Milvus (docker-compose.yml), not Milvus Lite — deliberate, for
hands-on scalability exposure per the spec's own reasoning. No collection
schema for real headline embeddings lives here yet — that depends on
OpenAI's embedding dimension, not chosen until lesson 18. This lesson only
proves the connection itself works.
"""

from pymilvus import MilvusClient

from ticker_backend.config import settings

# Created once, at import time -- same reasoning as db.py's `engine`.
# Flag for lesson 18/19: MilvusClient's methods are synchronous (blocking
# gRPC) against an async caller -- may need run_in_executor eventually.
milvus_client = MilvusClient(uri=settings.milvus_uri)
