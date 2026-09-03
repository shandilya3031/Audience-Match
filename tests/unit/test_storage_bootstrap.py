import pytest

from app.storage.local_files import raw_customer_data_path, raw_documents_path
from app.vectorstore.chroma_client import (
    CLUSTER_PROFILES,
    KNOWLEDGE_BASE,
    SCHEMA_METADATA,
    get_collection,
)


@pytest.mark.parametrize("name", [KNOWLEDGE_BASE, CLUSTER_PROFILES, SCHEMA_METADATA])
def test_get_collection_opens_each_valid_collection(name):
    collection = get_collection(name)
    assert collection is not None


def test_get_collection_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_collection("not_a_real_collection")


def test_raw_documents_path_creates_directory(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "raw_documents_dir", str(tmp_path / "docs"))
    path = raw_documents_path("example.pdf")
    assert path.parent.is_dir()
    assert path.name == "example.pdf"


def test_raw_customer_data_path_creates_directory(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "raw_customer_data_dir", str(tmp_path / "customer-data"))
    path = raw_customer_data_path("customers.csv")
    assert path.parent.is_dir()
    assert path.name == "customers.csv"
