#!/usr/bin/env python3
"""Convert the legacy XML catalogs to gettext PO and compile them to MO.

Usage:
    python3 scripts/locales.py convert [XML_DIR] [PO_DIR]
    python3 scripts/locales.py compile [LOCALE_DIR]
    python3 scripts/locales.py check [LOCALE_DIR]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_LOCALE = os.path.join(ROOT, "data", "locale")
DOMAIN = "gamemode-gui"


def _po_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\t", "\\t"))


def _catalog(path: str) -> tuple[dict[str, str], str, str]:
    root = ET.parse(path).getroot()
    entries = {
        entry.get("id"): (entry.text or "")
        for entry in root.findall("entry")
        if entry.get("id")
    }
    return entries, root.get("name", ""), (root.get("lang") or "").lower()


def convert(xml_dir: str = DEFAULT_LOCALE, po_dir: str = DEFAULT_LOCALE) -> None:
    names = {}
    for name in sorted(os.listdir(xml_dir)):
        if not name.endswith(".xml"):
            continue
        code = name[:-4]
        entries, label, _ = _catalog(os.path.join(xml_dir, name))
        names[code] = label or code.upper()
        lines = [
            'msgid ""',
            'msgstr ""',
            f'"Language: {code}\\n"',
            '"MIME-Version: 1.0\\n"',
            '"Content-Type: text/plain; charset=UTF-8\\n"',
            '"Content-Transfer-Encoding: 8bit\\n"',
            '"Project-Id-Version: gamemode-gui 1.0.0\\n"',
            '"PO-Revision-Date: 2026-10-19 00:00+0000\\n"',
            '"Last-Translator: GameMode GUI contributors\\n"',
            '"Language-Team: GameMode GUI contributors\\n"',
            f'"Language-Name: {_po_escape(label)}\\n"',
            "",
        ]
        for key, text in entries.items():
            lines += [f'msgid "{_po_escape(key)}"', f'msgstr "{_po_escape(text)}"', ""]
        with open(os.path.join(po_dir, f"{code}.po"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    with open(os.path.join(po_dir, "languages.json"), "w", encoding="utf-8") as handle:
        json.dump(names, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _mo_path(locale_dir: str, code: str) -> str:
    return os.path.join(locale_dir, code, "LC_MESSAGES", f"{DOMAIN}.mo")


def compile_catalogs(locale_dir: str = DEFAULT_LOCALE) -> None:
    for name in sorted(os.listdir(locale_dir)):
        if not name.endswith(".po"):
            continue
        code = name[:-3]
        target = _mo_path(locale_dir, code)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        subprocess.run(["msgfmt", "--check", "-o", target,
                        os.path.join(locale_dir, name)], check=True)


def check(locale_dir: str = DEFAULT_LOCALE) -> int:
    failed = 0
    for name in sorted(os.listdir(locale_dir)):
        if not name.endswith(".po"):
            continue
        code = name[:-3]
        source = os.path.join(locale_dir, name)
        target = _mo_path(locale_dir, code)
        with tempfile.NamedTemporaryFile(suffix=".mo", delete=False) as handle:
            generated = handle.name
        try:
            result = subprocess.run(["msgfmt", "--check", "-o", generated, source])
            if result.returncode != 0:
                failed += 1
            elif not os.path.isfile(target):
                print(f"missing MO: {target}")
                failed += 1
            elif open(generated, "rb").read() != open(target, "rb").read():
                print(f"stale MO: {target}")
                failed += 1
        finally:
            os.remove(generated)
    return failed


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    args = argv[2:]
    if command == "convert":
        convert(*args)
    elif command == "compile":
        compile_catalogs(*args)
    elif command == "check":
        return check(*args)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
