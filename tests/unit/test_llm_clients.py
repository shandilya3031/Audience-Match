from pathlib import Path

import pytest

from app.llm.model_router import get_model_for_task

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILE = REPO_ROOT / "app" / "llm" / "llm_clients.py"


def test_chatgroq_only_instantiated_in_llm_clients():
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path == ALLOWED_FILE:
            continue
        if "ChatGroq(" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"ChatGroq() instantiated outside app/llm/llm_clients.py: {offenders}"
    )


def test_get_model_for_task_raises_for_unregistered_task():
    with pytest.raises(KeyError):
        get_model_for_task("nonexistent_task")
