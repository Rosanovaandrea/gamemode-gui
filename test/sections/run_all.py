"""Run every section integration test in this folder.

Usage: ``python3 test/sections/run_all.py``. Each test runs in its own process
(so one crash does not hide the others) and returns non-zero on failure.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    tests = sorted(name for name in os.listdir(HERE)
                   if name.startswith("test_") and name.endswith(".py"))
    failures = []
    for name in tests:
        print(f"\n=== {name} ===", flush=True)
        result = subprocess.run([sys.executable, os.path.join(HERE, name)])
        if result.returncode != 0:
            failures.append(name)
    print(flush=True)
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print(f"all {len(tests)} section tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
