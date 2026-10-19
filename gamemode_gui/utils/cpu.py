"""CPU helper shared by the CPU section and the core-selection widget."""

from __future__ import annotations

from typing import List


def expand_cpu_list(text: str) -> List[int]:
    """Expand a Linux cpu-list (e.g. ``"0-3,8"``) into a sorted list of ints."""
    cores: List[int] = []
    for token in str(text).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, _, end = token.partition("-")
            try:
                cores.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                cores.append(int(token))
            except ValueError:
                pass
    return sorted(set(cores))
