"""Types used by this module."""

from __future__ import annotations

from typing import Any, Protocol

from .metablock import MetaBlock


class MetaBlockFixture(Protocol):
    """MetaBlock fixture type."""
    def __call__(self, step: int | None = ..., timeout: int = ...) -> MetaBlock:
        ...

"""MetaData fixture type."""
MetaDataFixture = dict[str, Any]
