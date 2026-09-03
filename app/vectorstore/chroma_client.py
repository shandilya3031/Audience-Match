from functools import lru_cache

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

KNOWLEDGE_BASE = "knowledge_base"
CLUSTER_PROFILES = "cluster_profiles"
SCHEMA_METADATA = "schema_metadata"

_VALID_COLLECTIONS = {KNOWLEDGE_BASE, CLUSTER_PROFILES, SCHEMA_METADATA}


@lru_cache(maxsize=1)
def _embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model_name)


def get_collection(name: str) -> Chroma:
    """Open (creating if needed) a local Chroma collection persisted to
    settings.chroma_persist_directory. name must be one of KNOWLEDGE_BASE,
    CLUSTER_PROFILES, SCHEMA_METADATA."""
    if name not in _VALID_COLLECTIONS:
        raise ValueError(
            f"Unknown collection '{name}'; must be one of {sorted(_VALID_COLLECTIONS)}"
        )
    return Chroma(
        collection_name=name,
        embedding_function=_embeddings(),
        persist_directory=settings.chroma_persist_directory,
    )
