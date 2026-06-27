from __future__ import annotations

import logging
import sys
from functools import lru_cache

from pythonjsonlogger import jsonlogger


_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(run_id)s %(thread_id)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    _configured = True


@lru_cache(maxsize=None)
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
