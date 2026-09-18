"""Milvus connection + the `story_primaries` collection -- see
docs/specs/0002-daily-story-grouping.md and
docs/adr/0011-milvus-story-collection-design.md.

Standalone Milvus (docker-compose.yml), not Milvus Lite -- deliberate, for
hands-on scalability exposure per the spec's own reasoning.
"""

from pymilvus import DataType, MilvusClient

from ticker_backend.config import settings

# One row per Story (the founding member's vector only) -- see ADR 0011.
STORY_PRIMARIES_COLLECTION = "story_primaries"
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small, confirmed live in lesson 18

_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """Lazy, not eager -- MilvusClient's constructor opens a real
    connection, so building it at import time would require Milvus to be
    reachable. Connects on first real use, cached after that."""
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient(uri=settings.milvus_uri)
    return _milvus_client


def ensure_story_primaries_collection(client: MilvusClient | None = None) -> None:
    """Creates `story_primaries` if it doesn't already exist -- idempotent,
    safe to call on every worker startup. `client` is injectable (ADR
    0012), defaulting to the real get_milvus_client()."""
    client = client or get_milvus_client()
    # Already exists -- nothing to do, idempotent no-op.
    if client.has_collection(STORY_PRIMARIES_COLLECTION):
        return

    # story_id primary key, ticker/day scalar filters, the embedding vector.
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="story_id", datatype=DataType.VARCHAR, max_length=36, is_primary=True)
    schema.add_field(field_name="ticker", datatype=DataType.VARCHAR, max_length=16)
    schema.add_field(field_name="day", datatype=DataType.VARCHAR, max_length=10)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIMENSIONS)

    # AUTOINDEX + cosine similarity on the embedding field -- see ADR 0011.
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="COSINE")

    # Create the collection with the schema + index defined above.
    client.create_collection(
        collection_name=STORY_PRIMARIES_COLLECTION,
        schema=schema,
        index_params=index_params,
    )
