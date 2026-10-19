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
COMMAND_CONVERT = "convert"
COMMAND_COMPILE = "compile"
COMMAND_CHECK = "check"
MSGFMT = "msgfmt"


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
    for name in (n for n in sorted(os.listdir(xml_dir)) if n.endswith(".xml")):
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
    for name in (n for n in sorted(os.listdir(locale_dir)) if n.endswith(".po")):
        code = name[:-3]
        target = _mo_path(locale_dir, code)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        subprocess.run([MSGFMT, "--check", "-o", target,
                        os.path.join(locale_dir, name)], check=True)


def check(locale_dir: str = DEFAULT_LOCALE) -> int:
    failed = 0
    for name in (n for n in sorted(os.listdir(locale_dir)) if n.endswith(".po")):
        code = name[:-3]
        source = os.path.join(locale_dir, name)
        target = _mo_path(locale_dir, code)
        with tempfile.NamedTemporaryFile(suffix=".mo", delete=False) as handle:
            generated = handle.name
        try:
            result = subprocess.run([MSGFMT, "--check", "-o", generated, source])
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
    command = argv[1] if len(argv) > 1 else COMMAND_CHECK
    args = argv[2:]
    match command:
        case _ if command == COMMAND_CONVERT:
            convert(*args)
        case _ if command == COMMAND_COMPILE:
            compile_catalogs(*args)
        case _ if command == COMMAND_CHECK:
            return check(*args)
        case _:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
