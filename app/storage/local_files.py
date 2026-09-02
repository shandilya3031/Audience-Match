from pathlib import Path

from app.config import settings


def raw_documents_path(filename: str) -> Path:
    directory = Path(settings.raw_documents_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename


def raw_customer_data_path(filename: str) -> Path:
    directory = Path(settings.raw_customer_data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename
