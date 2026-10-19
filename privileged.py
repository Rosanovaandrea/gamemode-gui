#!/usr/bin/env python3
"""Compatibility entry point for the privileged helper."""

from __future__ import annotations

import sys

from services.privileged_helper import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
