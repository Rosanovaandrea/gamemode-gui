"""Protocol implemented by every option control."""

from __future__ import annotations

from typing import Any, Protocol


class ValueControl(Protocol):
    """Uniform value interface of the option widgets."""

    def get_value(self) -> Any: ...
    def set_value(self, value: Any) -> None: ...
    def set_sensitive(self, sensitive: bool) -> None: ...
