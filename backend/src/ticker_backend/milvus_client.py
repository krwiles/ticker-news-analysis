"""Milvus connection setup — see docs/specs/0002-daily-story-grouping.md.

Standalone Milvus (docker-compose.yml), not Milvus Lite — deliberate, for
hands-on scalability exposure per the spec's own reasoning. No collection
schema for real headline embeddings lives here yet — that depends on
OpenAI's embedding dimension, not chosen until lesson 18. This lesson only
proves the connection itself works.
"""

from pymilvus import MilvusClient

from ticker_backend.config import settings

# Created once, at import time -- same reasoning as db.py's `engine`: a
# connection belongs to the app's whole lifetime, not to any one call.
#
# Worth flagging for lesson 18/19, not solved here: MilvusClient's methods
# are synchronous (blocking gRPC), while the code that will eventually call
# this (the ARQ job in providers.py) is fully async. Calling it directly
# inside an `async def` would block the event loop for that call's
# duration -- the same CPU-bound-work-in-an-async-job concern lesson 8
# named, needing the same run_in_executor treatment if it turns out to
# matter at real call volume.
milvus_client = MilvusClient(uri=settings.milvus_uri)
