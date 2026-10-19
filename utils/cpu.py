"""CPU helper shared by the CPU section and the core-selection widget."""

from __future__ import annotations

from typing import List


def _parse_token(token: str) -> List[int]:
    """Parse one cpu-list token (``3`` or ``0-3``); invalid tokens are ignored."""
    try:
        if "-" in token:
            start, _, end = token.partition("-")
            return list(range(int(start), int(end) + 1))
        return [int(token)]
    except ValueError:
        return []


def expand_cpu_list(text: str) -> List[int]:
    """Expand a Linux cpu-list (e.g. ``"0-3,8"``) into a sorted list of ints."""
    cores: List[int] = []
    for token in str(text).split(","):
        token = token.strip()
        if token:
            cores.extend(_parse_token(token))
    return sorted(set(cores))
