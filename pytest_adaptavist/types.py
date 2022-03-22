"""Types used by this module."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from .metablock import MetaBlock


class MetaBlockFixture(Protocol):
    """MetaBlock fixture type."""

    def __call__(self, step: int | None = ..., timeout: int = ..., action_on_timeout: MetaBlock.Action = ..., message_on_timeout: str = ...) -> MetaBlock:
        ...


MetaDataFixture = Dict[str, Any]
