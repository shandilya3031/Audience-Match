from typing import Any

ROUTING_TABLE: dict[str, Any] = {}


def get_model_for_task(task_name: str) -> Any:
    """Look up the model registered for a task name.

    Raises KeyError if the task hasn't been registered — call sites must
    register a ROUTING_TABLE entry before use (CLAUDE.md §4 rule 2).
    """
    if task_name not in ROUTING_TABLE:
        raise KeyError(
            f"No model registered for task '{task_name}' in ROUTING_TABLE. "
            "Register it in app/llm/model_router.py before adding this call site."
        )
    return ROUTING_TABLE[task_name]
