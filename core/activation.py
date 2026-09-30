"""Activation flags management.

For every option in the table there is a boolean that says whether that
option should be *written* to ``gamemode.ini``. Flags live only in memory
during a session and are reconstructed by reading the existing file: if a
key is present, the flag is ``True``, otherwise ``False``.

The GUI sets a flag to ``True`` automatically when the user edits a value,
but the user can also explicitly disable an option via the "Includi"
checkbox.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .options_table import OPTIONS
from . import ini_util


class ActivationManager:
    def __init__(self) -> None:
        self._flags: Dict[str, bool] = {}

    # -- basic API -------------------------------------------------------
    def set_flag(self, option_id: str, enabled: bool) -> None:
        self._flags[option_id] = enabled

    def get_flag(self, option_id: str) -> bool:
        return self._flags.get(option_id, False)

    def enable(self, option_id: str) -> None:
        self.set_flag(option_id, True)

    def take_snapshot(self) -> Dict[str, bool]:
        return dict(self._flags)

    # -- reconstruction ---------------------------------------------------
    @staticmethod
    def _parse_scalar(kind: str, raw_list: List[str]):
        """Convert the raw list of string values into a typed value."""
        if not raw_list:
            return None
        raw = raw_list[-1] if len(raw_list) == 1 else ",".join(raw_list)
        if kind == "int":
            try:
                return int(raw)
            except ValueError:
                return None
        if kind == "float":
            try:
                return float(raw)
            except ValueError:
                return None
        if kind == "bool":
            return raw.strip() not in ("0", "false", "no")
        # string / choice
        return raw

    def rebuild_from_parsed(self, parsed) -> Dict[str, object]:
        """Rebuild flags (and return values) from a parsed INI structure.

        ``parsed`` is the dict returned by :func:`ini_util.parse`.
        """
        from .options_table import OPTIONS as OPTIONS_TABLE

        values: Dict[str, object] = {}
        for spec in OPTIONS_TABLE:
            section_data = parsed.get(spec.section, {})
            raw_values = section_data.get(spec.key)

            if raw_values:
                self._flags[spec.id] = True
                if spec.type == "list":
                    values[spec.id] = [v.strip() for v in raw_values if v.strip()]
                else:
                    values[spec.id] = self._parse_scalar(spec.type, raw_values)
            else:
                self._flags[spec.id] = False
                values[spec.id] = spec.default

        # Defaults for the keys the file does not mention (flag False).
        return values

    def rebuild_from_file(self, path: Optional[str]) -> Dict[str, object]:
        """Load flags/values from an existing file, or from defaults."""
        if path is not None and __import__("os").path.isfile(path):
            parsed = ini_util.parse_file(path)
            return self.rebuild_from_parsed(parsed)

        self._flags = {}
        from .options_table import OPTIONS as OPTIONS_TABLE
        values = {spec.id: spec.default for spec in OPTIONS_TABLE}
        for spec in OPTIONS_TABLE:
            self._flags[spec.id] = False
        return values