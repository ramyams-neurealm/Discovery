from typing import Any


def profile_tables(source_connection: Any, objects: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return table profiles and column profiles. Source access must be read-only."""
    raise NotImplementedError


def mask_sample(value: Any, classification: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= 2:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 2) + text[-1]
