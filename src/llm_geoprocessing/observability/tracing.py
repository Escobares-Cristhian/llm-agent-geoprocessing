from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


def traceable(name: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    try:
        from langsmith import traceable as langsmith_traceable

        return cast(Callable[[Callable[P, R]], Callable[P, R]], langsmith_traceable(name=name))
    except Exception:
        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            return func

        return decorator
