"""Vendored Redux/Rx import shim.

The vendored copies keep the distro packages independent from pip. They are
inserted at the front of ``sys.path`` so ``redux`` imports resolve to the
vendored version even when another one is installed system-wide.
"""

from __future__ import annotations

import os
import sys

_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from redux import (  # noqa: E402,F401
    create_action, create_feature_module, create_store,
)

__all__ = [
    "create_action", "create_feature_module", "create_store",
]
