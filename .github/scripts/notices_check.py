#!/usr/bin/env python3
"""Read a built bundle's native libraries against its THIRD_PARTY_NOTICES.txt.

Every native library in the bundle must be credited, so that one nobody has
credited stops the build rather than shipping quietly. A library is credited when:

- a distribution installed in the environment that built the bundle lists it in
  its RECORD, and that distribution has its section in the notices; or
- the notices name its file, outside the distributions' own sections (a package's
  licence text that happens to mention a file credits nothing); or
- it is the Python runtime's own or the program's own starter, as RUNTIME_S and OWN say.

The step runs where the build ran, so what is installed is what was built with;
PyInstaller carries only some distributions' metadata into a bundle, so the
bundle's own RECORD files would not do. It also fails on the PostgreSQL client
library and on Qt's SQL drivers, which no route may bring back, credited or not.

    python .github/scripts/notices_check.py dist/Zij        # Windows
    python .github/scripts/notices_check.py dist/Zij.app    # macOS

It reads files and starts nothing. It exits 0 when every library is credited and
1, naming each fault, when one is not. Standard library only.
"""
from __future__ import annotations

import os
import re
import sys
from importlib import metadata
from pathlib import Path

NOTICES = "THIRD_PARTY_NOTICES.txt"
RULE = "#" * 78
NATIVE_NAME = re.compile(r"(?i)\.(?:dll|pyd|so|dylib)$|\.so\.\d")
MACH_O = {bytes.fromhex(magic) for magic in ("cffaedfe", "cefaedfe", "feedfacf", "feedface", "cafebabe", "bebafeca")}
# The program's own starter, PyInstaller's bootloader with the program's archive, at the
# one place each system's bundle holds it.
OWN = {"Zij.exe", "MacOS/Zij"}
# The Python runtime's own files, which stand under Python's section: the runtime
# itself, and the extension modules of its standard library.
RUNTIME_S = re.compile(r"python3\d*\.dll|Python\.framework/Versions/[^/]+/Python")
LIB_DYNLOAD = re.compile(r"python3\.\d+/lib-dynload/(\w+)\.cpython-\d+-darwin\.so")
TEST_MODULE = re.compile(r"_test\w*")   # the standard library's, which sys.stdlib_module_names leaves out
# Neither ships, whatever the notices say: nothing in the program reads PostgreSQL.
NEVER = re.compile(r"(?i)(?:^|/)(?:libpq[^/]*|sqldrivers)(?:/|$)")
# The program's own data: named files are still read by their names, never opened.
NOT_OPENED = re.compile(r"data/|atlas\.db$")


def _is_native_by_its_head(path: Path) -> bool:
    with open(path, "rb") as f:
        head = f.read(64)
        if head[:4] in MACH_O:
            return True
        if head[:2] != b"MZ" or len(head) < 64:
            return False
        f.seek(int.from_bytes(head[60:64], "little"))
        return f.read(4) == b"PE\0\0"


def _places(bundle: Path) -> tuple[bool, Path, Path]:
    """Whether the bundle is the Windows form, where its walk starts and where its notices are."""
    if (bundle / "_internal").is_dir():
        return True, bundle, bundle / "_internal" / NOTICES
    return False, bundle / "Contents", bundle / "Contents" / "Resources" / NOTICES


def _relative(path: Path, start: Path) -> str:
    """A bundled file's path as a RECORD would give it: without the bundle's own folders
    and, on macOS, with the dot PyInstaller writes as __dot__ in a folder's name."""
    rel = path.relative_to(start).as_posix()
    rel = re.sub(r"^(?:_internal|Frameworks|Resources)/", "", rel)
    return rel.replace("__dot__", ".")


def native_files(bundle: Path) -> list[str]:
    """Every native library and executable in the bundle but the program's starter, by its path
    as a RECORD would give it. A link is passed over: what it points to is read where it stands."""
    _windows, start, _notices = _places(bundle)
    found = set()
    for folder, _dirs, files in os.walk(start):
        for name in files:
            path = Path(folder) / name
            if path.is_symlink() or path.relative_to(start).as_posix() in OWN:
                continue
            rel = _relative(path, start)
            if NATIVE_NAME.search(name) or (not NOT_OPENED.match(rel) and _is_native_by_its_head(path)):
                found.add(rel)
    return sorted(found)


def _is_runtime_s(rel: str, stdlib: frozenset[str]) -> bool:
    if RUNTIME_S.fullmatch(rel):
        return True
    dynload = LIB_DYNLOAD.fullmatch(rel)
    stem, dot, kind = rel.partition(".")
    if dynload:
        stem = dynload[1]
    elif dot != "." or kind.lower() != "pyd":
        return False
    return stem in stdlib or bool(TEST_MODULE.fullmatch(stem))


def installed() -> dict[str, list[str]]:
    """Each installed distribution, as its section's heading gives it, with what its RECORD lists."""
    return {f"{dist.metadata['Name']} {dist.version}": [str(f) for f in dist.files or ()]
            for dist in metadata.distributions() if dist.metadata["Name"]}


def _sections(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split(RULE + "\n")


def _named(name: str, text: str, windows: bool) -> bool:
    file = re.escape(name.rsplit("/", 1)[-1])
    return bool(re.search(rf"(?<![\w.-]){file}(?![\w-]|\.\w)", text, re.IGNORECASE if windows else 0))


def faults(bundle: Path, distributions: dict[str, list[str]] | None = None) -> list[str]:
    """What is uncredited in the bundle; nothing, when every native library is credited."""
    distributions = installed() if distributions is None else distributions
    windows, _start, notices = _places(bundle)
    if not notices.is_file():
        return [f"{bundle} holds no {NOTICES}"]
    natives = native_files(bundle)
    if not natives:
        return [f"{bundle} holds no native library: it is not a built bundle"]
    sections = _sections(notices.read_text(encoding="utf-8", errors="replace"))
    heads = {section.split("\n", 1)[0] for section in sections}
    credit = "\n".join(section for section in sections if section.split("\n", 1)[0] not in distributions)
    fold = str.lower if windows else str
    listed: dict[str, list[str]] = {}
    for head, paths in distributions.items():
        for path in paths:
            listed.setdefault(fold(path), []).append(head)
    stdlib = frozenset(sys.stdlib_module_names)
    found = []
    for rel in natives:
        owners = listed.get(fold(rel), ())
        if NEVER.search(rel):
            found.append(f"{rel} is in the bundle: PostgreSQL's client and Qt's SQL drivers do not ship")
        elif _is_runtime_s(rel, stdlib):
            continue
        elif owners:
            if not heads.intersection(owners):
                found.append(f"{rel} is listed by {', '.join(owners)}, which has no section in {NOTICES}")
        elif not _named(rel, credit, windows):
            found.append(f"{rel} is listed by no distribution's RECORD and named nowhere in {NOTICES}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    found = faults(Path(argv[1]))
    for fault in found:
        print(f"notices_check: {fault}", file=sys.stderr)
    if not found:
        print(f"notices_check: all {len(native_files(Path(argv[1])))} native files in {argv[1]} are credited")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
