#!/usr/bin/env python3
"""Read a build's archive listing for the program's wheel module.

wheel.py's name is also a package's, and setuptools holds a copy of that package
at setuptools/_vendor/wheel/. Should PyInstaller ever take that copy for the name,
the pictures would fail at their first import and nothing would say why. So
wheel must stand in the archive as a module, with nothing inside it, and
setuptools' copy must not stand there at all.

The listing is what this prints, with PyInstaller's own tool:

    pyi-archive_viewer --list --recursive dist/Zij/Zij.exe > listing.txt
    python .github/scripts/archive_check.py listing.txt

It exits 0 when the listing passes and 1, naming each fault, when it does not.
"""
from __future__ import annotations

import ast
import re
import sys

MODULE = 0   # the tool's typecode for a module; a package's is 1
THE_PROGRAM_S = "wheel"
SETUPTOOLS_COPY = "setuptools._vendor.wheel"
_SECTION = re.compile(r"^Contents of .* \((PKG/CArchive|PYZ)\):$")
_PKG_ROW = re.compile(r"^ \d+, \d+, \d+, \d+, (?:'.'|\".\"), (?P<name>'.*'|\".*\")$")
_PYZ_ROW = re.compile(r"^ (?P<typecode>\d+), \d+, \d+, (?P<name>'.*'|\".*\")$")


def _inside(name: str, parent: str) -> bool:
    return name == parent or name.startswith(parent + ".")


def read_listing(text: str) -> tuple[dict[str, int], set[str]]:
    """The listing's PYZ entries, name to typecode, and every name it lists under the other sections."""
    modules: dict[str, int] = {}
    others: set[str] = set()
    section = None
    for line in text.splitlines():
        heading = _SECTION.match(line)
        if heading:
            section = heading.group(1)
        elif section == "PYZ" and (row := _PYZ_ROW.match(line)):
            modules[ast.literal_eval(row["name"])] = int(row["typecode"])
        elif section == "PKG/CArchive" and (row := _PKG_ROW.match(line)):
            others.add(ast.literal_eval(row["name"]))
    return modules, others


def faults(text: str) -> list[str]:
    """What is wrong with the listing; nothing, when wheel is the program's module."""
    modules, others = read_listing(text)
    if not modules:
        return ["the listing holds no PYZ entries: it is not a recursive listing of a built program"]
    found = []
    if THE_PROGRAM_S not in modules:
        found.append(f"{THE_PROGRAM_S} is not in the archive")
    elif modules[THE_PROGRAM_S] != MODULE:
        found.append(f"{THE_PROGRAM_S} has typecode {modules[THE_PROGRAM_S]}, not a module's {MODULE}")
    found += [f"{name} is in the archive: {THE_PROGRAM_S} is a package there"
              for name in sorted(modules) if name.startswith(THE_PROGRAM_S + ".")]
    found += [f"{name} is in the archive: setuptools' copy was collected"
              for name in sorted(set(modules) | others) if _inside(name, SETUPTOOLS_COPY)]
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        found = faults(f.read())
    for fault in found:
        print(f"archive_check: {fault}", file=sys.stderr)
    if not found:
        print(f"archive_check: {THE_PROGRAM_S} is a module and {SETUPTOOLS_COPY} is absent")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
