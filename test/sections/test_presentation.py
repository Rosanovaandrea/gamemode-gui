"""Integration tests for the Presentation section (stateless).

Happy path: the shipped ``presentation.json`` loads with its blocks. Failure
paths: a missing or broken file yields an empty presentation instead of an error.
"""

import os

import _testkit
WORK_DIR = _testkit.isolate()

from sections.presentation.core import PRESENTATION, load_presentation  # noqa: E402


def main():
    # --- happy path: the shipped file
    _testkit.check("the real presentation has blocks", len(PRESENTATION.blocks) > 0)
    _testkit.check("it includes a warning block",
                   any(block.warning for block in PRESENTATION.blocks))

    # --- failure paths: a missing and a broken file
    missing = load_presentation(os.path.join(WORK_DIR, "does-not-exist.json"))
    _testkit.equal("missing file yields no blocks", len(missing.blocks), 0)
    _testkit.equal("missing file keeps the fallback title",
                   missing.title_id, "presentation.title")

    broken_path = os.path.join(WORK_DIR, "broken.json")
    with open(broken_path, "w", encoding="utf-8") as handle:
        handle.write("{ this is not json")
    broken = load_presentation(broken_path)
    _testkit.equal("broken file yields no blocks", len(broken.blocks), 0)

    _testkit.finish()


if __name__ == "__main__":
    main()
