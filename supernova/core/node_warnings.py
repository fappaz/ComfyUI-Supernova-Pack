"""Run node logic without failing the node: collect logged warnings and fall back on errors."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)
# Parent logger of all modules in this package, whatever name ComfyUI loads it under.
_PACKAGE_LOGGER = logging.getLogger(__name__.rpartition(".")[0])


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord):
        self.messages.append(record.getMessage())


def run_with_warnings(name: str, fn: Callable[[], T], fallback: Callable[[], T]) -> tuple[T, list[str]]:
    """Call fn(), returning (result, warnings logged meanwhile). Never raises: on an unexpected
    error the error is logged and fallback() is returned instead."""
    handler = _Collect()
    _PACKAGE_LOGGER.addHandler(handler)
    try:
        return fn(), handler.messages
    except Exception as e:
        logger.exception("%s failed: %s", name, e)
        return fallback(), handler.messages
    finally:
        _PACKAGE_LOGGER.removeHandler(handler)
