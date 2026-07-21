"""Reusable interactive input collection for every level and algorithm."""

from __future__ import annotations

from collections.abc import Callable, Sequence


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise ValueError("value must be a positive integer")
    return value


def prompt_choice(label: str, choices: Sequence[str], default: str, *, input_fn: Callable[[str], str] = input) -> str:
    raw = input_fn(f"{label} {list(choices)} [{default}]: ").strip()
    selected = raw or default
    if selected not in choices:
        raise ValueError(f"{label} must be one of: {', '.join(choices)}")
    return selected


def prompt_positive(label: str, default: int, *, input_fn: Callable[[str], str] = input) -> int:
    raw = input_fn(f"{label} [{default}]: ").strip()
    return default if not raw else positive_int(raw)
