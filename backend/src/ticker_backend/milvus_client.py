"""Milvus connection + the `story_primaries` collection -- see
docs/specs/0002-daily-story-grouping.md and
docs/adr/0011-milvus-story-collection-design.md.

Standalone Milvus (docker-compose.yml), not Milvus Lite -- deliberate, for
hands-on scalability exposure per the spec's own reasoning.
"""

from pymilvus import DataType, MilvusClient

from ticker_backend.config import settings

# One row per Story, not per Headline -- holds only the founding member's
# (the matching-representative's) vector, per ADR 0011. `day` is a plain
# ISO date string (Milvus has no native calendar-day type), matching this
# project's Eastern-day definition (CONTEXT.md's `Today` entry).
STORY_PRIMARIES_COLLECTION = "story_primaries"
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small, confirmed live in lesson 18

_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """Lazy, not eager at import time -- `MilvusClient.__init__` itself
    opens a real connection (unlike `create_async_engine`, which only
    prepares a pool), so importing this module must not require Milvus to
    be reachable. `providers.py` (which `worker.py` needs) importing this
    unconditionally is exactly why: tests run on the host, where the
    `milvus` hostname only resolves inside the docker network. Connects on
    first real use instead, cached after that for the process's lifetime.
    """
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient(uri=settings.milvus_uri)
    return _milvus_client


def ensure_story_primaries_collection() -> None:
    """Creates `story_primaries` if it doesn't already exist -- idempotent,
    safe to call on every worker startup rather than needing a one-time
    migration step of its own."""
    client = get_milvus_client()
    if client.has_collection(STORY_PRIMARIES_COLLECTION):
        return

    # Define the collection's shape: a Story's id as primary key, ticker/day
    # as scalar filters (spec 0002's "same day, same ticker only" scoping),
    # and the founding headline's embedding vector.
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="story_id", datatype=DataType.VARCHAR, max_length=36, is_primary=True)
    schema.add_field(field_name="ticker", datatype=DataType.VARCHAR, max_length=16)
    schema.add_field(field_name="day", datatype=DataType.VARCHAR, max_length=10)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIMENSIONS)

    # AUTOINDEX, not a tuned IVF/HNSW index -- same reasoning ADR 0008 used
    # to skip partitioning: this project's real scale doesn't need it.
    # COSINE, not L2/IP -- OpenAI's embeddings are already normalized, so
    # cosine similarity is the standard, readable choice (confirmed via
    # direct research, not assumed).
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="COSINE")

    client.create_collection(
        collection_name=STORY_PRIMARIES_COLLECTION,
        schema=schema,
        index_params=index_params,
    )
