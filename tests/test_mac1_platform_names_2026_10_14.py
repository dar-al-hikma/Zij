"""The program reads only platform names that Linux, macOS and Windows all have.

The suite runs on Linux, so a module attribute that Linux has and macOS or
Windows lacks passes every test here and stops the frozen app at its start
on the other platform: ``errno.EDEADLOCK``, an alias Linux and Windows keep
and macOS does not, ended the desktop app two seconds after its start on
every Mac.

* The engine is imported in a fresh interpreter whose ``errno`` has no
  ``EDEADLOCK``, as macOS's has not; it must import, with the lock's
  refusals the four it names.
* Every ``errno`` name read by a module the frozen app ships is in a short
  allowlist of names present on all three platforms, each with its value
  there. Every value is the one the platform's own header line gives, as
  tests/fixtures/errno_header_lines.json holds those lines; and the build
  machines run this file before they build, so each checks its own column
  against its own ``errno``.
"""

from __future__ import annotations

import ast
import errno
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import shipped_modules

ROOT = Path(__file__).resolve().parent.parent
HEADER_LINES = ROOT / "tests" / "fixtures" / "errno_header_lines.json"
TIMEOUT = 300


# ---------------------------------------------------------------------------
# The engine imports where errno has no EDEADLOCK.

_IMPORT_WITHOUT_EDEADLOCK = r"""
import sys, errno, json
assert "engine" not in sys.modules, "the engine was imported before errno lost EDEADLOCK"
if hasattr(errno, "EDEADLOCK"):
    del errno.EDEADLOCK
import engine
print("ERRNO " + json.dumps({
    "edeadlock_present": hasattr(errno, "EDEADLOCK"),
    "refusals": sorted(engine._LOCK_REFUSALS),
    "edeadlk": errno.EDEADLK,
}))
"""


def test_engine_imports_where_errno_has_no_EDEADLOCK(tmp_path):
    """macOS's errno has no EDEADLOCK: the engine imports without it, and
    the lock still counts EDEADLK among a held lock's refusals."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONSTARTUP"}
    env["PYTHONPATH"] = str(ROOT)
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    done = subprocess.run([sys.executable, "-c", _IMPORT_WITHOUT_EDEADLOCK], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, done.stderr[-3000:]
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("ERRNO ")]
    assert line, (done.stdout[-2000:], done.stderr[-2000:])
    seen = json.loads(line[-1][len("ERRNO "):])
    # The import ran without the name: else this test proves nothing.
    assert seen["edeadlock_present"] is False, seen
    assert seen["edeadlk"] in seen["refusals"], seen
    assert seen["refusals"] == sorted({errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, errno.EDEADLK}), seen


# ---------------------------------------------------------------------------
# Every errno name the shipped modules read is one all three platforms have.

# Each name with its value on (Linux, macOS, Windows). Python's errno module
# adds a name only where the C library defines it (CPython
# Modules/errnomodule.c: "#ifdef EDEADLK / add_errcode("EDEADLK", EDEADLK,
# ...)"), so a name is present on a platform when that platform's errno.h
# defines it. The defining lines, with their sources, are in
# tests/fixtures/errno_header_lines.json, and every cell here is held to them.
# EWOULDBLOCK on Windows: errnomodule.c undefines the C runtime's 140 and adds
# "EWOULDBLOCK" as WSAEWOULDBLOCK (10035) instead.
ERRNO_ON_ALL_THREE = {
    "EPERM": (1, 1, 1),
    "ENOENT": (2, 2, 2),
    "EAGAIN": (11, 35, 11),
    "EACCES": (13, 13, 13),
    "EEXIST": (17, 17, 17),
    "ENOTDIR": (20, 20, 20),
    "EINVAL": (22, 22, 22),
    "EFBIG": (27, 27, 27),
    "EROFS": (30, 30, 30),
    "EDEADLK": (35, 11, 36),
    "EWOULDBLOCK": (11, 35, 10035),
}
_PLATFORM_COLUMN = {"linux": 0, "darwin": 1, "win32": 2}
_FIXTURE_COLUMN = {"linux": 0, "macos": 1, "windows": 2}

# Attributes of the errno module that are no error name and exist everywhere.
_ERRNO_TABLES = {"errorcode"}


def _shipped_files():
    """(name, path) for every Python file the frozen app carries, as the build
    finds them (tests/shipped_modules.py): a package folder's every file."""
    out = []
    for name in shipped_modules.shipped_modules(ROOT):
        if name.endswith("/"):
            out += [(str(p.relative_to(ROOT)), p) for p in sorted((ROOT / name).rglob("*.py"))]
        else:
            out.append((name, ROOT / name))
    return out


def _errno_reads(path):
    """(name, line) for every errno name `path` reads: ``errno.NAME`` under
    whatever name the module is bound to (``from socket import errno as x``
    binds it too, and so does an assignment of the module, ``_e = errno``, or
    of ``importlib.import_module("errno")``), ``from errno import NAME``, ``getattr(errno, "NAME")``
    without a default, and ``mod.errno.NAME`` through another imported
    module's ``errno`` (``socket.errno``). A
    ``getattr(errno, <a name not written out>)`` without a default is
    (None, line): nothing can tell which name it reads. ``errno.errorcode``
    is no error name and is let through."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound, modules = set(), set()
    reads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bound.update(a.asname or a.name for a in node.names if a.name == "errno")
            modules.update(a.asname or a.name.split(".")[0] for a in node.names if a.name != "errno")
        elif isinstance(node, ast.ImportFrom) and node.module == "errno":
            reads.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from socket import errno [as x]`: the name is the errno module
            bound.update(a.asname or a.name for a in node.names if a.name == "errno")

    def is_errno(node):
        return (isinstance(node, ast.Name) and node.id in bound
                or isinstance(node, ast.Attribute) and node.attr == "errno"
                and isinstance(node.value, ast.Name) and node.value.id in modules
                or isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "errno"
                and getattr(node.func, "attr", getattr(node.func, "id", None)) in ("import_module", "__import__")
                or isinstance(node, ast.Subscript) and ast.unparse(node.value) == "sys.modules"
                and isinstance(node.slice, ast.Constant) and node.slice.value == "errno")

    # a name assigned the module (`_e = errno`, `_e = importlib.import_module("errno")`,
    # and a name assigned from such a name) is the module too, to a fixed point
    while True:
        before = len(bound)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None \
                    and is_errno(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                bound.update(t.id for t in targets if isinstance(t, ast.Name))
        if len(bound) == before:
            break

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and is_errno(node.value):
            reads.append((node.attr, node.lineno))
        elif (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr" and len(node.args) == 2
              and not node.keywords and is_errno(node.args[0])):
            name = node.args[1]
            literal = isinstance(name, ast.Constant) and isinstance(name.value, str)
            reads.append((name.value if literal else None, node.lineno))
    return [(name, line) for name, line in reads if name not in _ERRNO_TABLES]


def test_the_shipped_modules_are_found_as_the_build_finds_them():
    """The four the app is made of today, and every module the list names,
    are among the files the scan reads; each is a file of the tree."""
    shipped = [name for name, _ in _shipped_files()]
    floor = {"desktop_launcher.py", "app.py", "engine.py", "glyph_font.py"}
    floor |= set(shipped_modules.source_list.names(ROOT))
    assert floor <= set(shipped), sorted(floor - set(shipped))
    missing = [name for name, path in _shipped_files() if not path.is_file()]
    assert not missing, f"the build ships {missing}, not in the repository"


def test_every_errno_name_read_is_on_linux_macos_and_windows():
    refused = []
    every = set()
    for name, path in _shipped_files():
        for attr, line in _errno_reads(path):
            if attr is None:
                refused.append(f"{name} reads errno through getattr at line {line} with a name not written "
                               f"out and no default, so no check can tell whether all three platforms have it.")
                continue
            every.add(attr)
            if attr not in ERRNO_ON_ALL_THREE:
                refused.append(f"{name} reads errno.{attr} at line {line}, a name not in the allowlist of errno "
                               f"names that Linux, macOS and Windows all define; find it in each platform's "
                               f"errno.h (or guard the read) before adding it.")
    assert not refused, "\n".join(refused)
    assert "EDEADLK" in every, sorted(every)
    stale = sorted(set(ERRNO_ON_ALL_THREE) - every)
    assert not stale, f"the allowlist names {stale}, which no shipped module reads any more: take them out"


@pytest.mark.parametrize("source,reads", [
    ("import errno\nx = errno.EDEADLK\n", [("EDEADLK", 2)]),
    ("import socket\nx = socket.errno.EDEADLOCK\n", [("EDEADLOCK", 2)]),
    ("import errno\nname = 'EDEAD' + 'LOCK'\nx = getattr(errno, name)\n", [(None, 3)]),
    ("import errno\nx = getattr(errno, 'EDEADLOCK', None)\n", []),
    ("import errno\nx = errno.errorcode[35]\n", []),
    ("def f(exc):\n    return exc.errno.real\n", []),
    ("from socket import errno as x\ny = x.EDEADLOCK\n", [("EDEADLOCK", 2)]),
    ("from socket import errno\ny = errno.EDEADLOCK\n", [("EDEADLOCK", 2)]),
    ("from os import errno as x\ny = getattr(x, 'EDEADLOCK')\n", [("EDEADLOCK", 2)]),
    ("from socket import errno as x\ny = x.errorcode[35]\n", []),
    ("import errno\n_e = errno\nx = _e.EDEADLOCK\n", [("EDEADLOCK", 3)]),
    ("import errno\n_e = errno\n_f = _e\ndef f(exc):\n    return exc.errno == _f.EDEADLOCK\n", [("EDEADLOCK", 5)]),
    ("import importlib\n_e = importlib.import_module('errno')\nx = _e.EDEADLOCK\n", [("EDEADLOCK", 3)]),
    ("_e = __import__('errno')\nx = getattr(_e, 'EDEADLOCK')\n", [("EDEADLOCK", 2)]),
    ("import sys\n_e = sys.modules['errno']\nx = _e.EDEADLOCK\n", [("EDEADLOCK", 3)]),
    ("import importlib\nx = importlib.import_module('errno').EDEADLOCK\n", [("EDEADLOCK", 2)]),
])
def test_the_scan_reads_each_route_to_an_errno_name(tmp_path, source, reads):
    """A read through another module's errno, by its attribute or by a name
    `from <module> import errno` binds, and a getattr whose name is not
    written out are caught; a getattr with a default (it cannot fail), the
    errorcode table and an exception's errno number are not reads of a name."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    assert _errno_reads(path) == reads


def _cells_off_here(module, column):
    """Every allowlist cell of `column` that `module`'s values differ from,
    as a sentence; a name `module` lacks is one too."""
    off = []
    for name, cells in ERRNO_ON_ALL_THREE.items():
        value = getattr(module, name, None)
        if value is None:
            off.append(f"errno has no {name} on this platform; the allowlist gives {cells[column]}.")
        elif value != cells[column]:
            off.append(f"errno.{name} is {value} on this platform; the allowlist gives {cells[column]}.")
    return off


def test_the_allowlist_values_are_this_platforms():
    """The table's column for the platform the suite runs on is the
    errno module's own values here."""
    column = _PLATFORM_COLUMN.get(sys.platform)
    assert column is not None, f"no column for {sys.platform}"
    assert _cells_off_here(errno, column) == []


# ---------------------------------------------------------------------------
# Every cell is the value its platform's header line gives.

_DEFINE = re.compile(r"\s*#\s*define\s+(\w+)\s+(.+?)\s*(?:/\*.*)?$")
_UNDEF = re.compile(r"\s*#\s*undef\s+(\w+)\s*$")
_ADD = re.compile(r'\s*add_errcode\("(\w+)",\s*(\w+),')
_SKIP = re.compile(r"\s*#\s*(?:ifdef|ifndef|else|endif)\b")


def _value(expr, macros):
    """The integer a macro body names: a number (an L suffix allowed), a
    macro already defined, or a sum of those in parentheses."""
    tokens = re.findall(r"\d+L?|\w+|[()+]", expr)
    if "".join(tokens) != re.sub(r"\s+", "", expr):
        raise ValueError(f"not a macro body this reads: {expr!r}")
    text = " ".join(str(macros[t]) if t in macros else t.rstrip("L") if t[0].isdigit() else t for t in tokens)
    tree = ast.parse(text, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.Add, ast.Constant)
    if not all(isinstance(n, allowed) for n in ast.walk(tree)):
        raise ValueError(f"not a macro body this reads: {expr!r} ({text!r})")
    return eval(compile(tree, "<macro>", "eval"))


def _header_values(lines):
    """name -> value, as the lines define it read in order: `#define`,
    `#undef`, and CPython's `add_errcode("NAME", MACRO, ...)`, which gives
    the Python name the macro's value. Any other kind of line is an error."""
    macros, added = {}, {}
    for entry in lines:
        text = entry["text"]
        if m := _DEFINE.match(text):
            macros[m[1]] = _value(m[2], macros)
        elif m := _UNDEF.match(text):
            macros.pop(m[1], None)
        elif m := _ADD.match(text):
            added[m[1]] = macros[m[2]]
        elif not _SKIP.match(text):
            raise ValueError(f"{entry['source']}:{entry['line']}: not a line this reads: {text!r}")
    return {**macros, **added}


def _header_mismatches(allowlist, fixture):
    """Every allowlist name without its three platforms' lines, and every
    cell its platform's lines give otherwise, as sentences. A platform's
    lines are read together, in the fixture's order, so that an alias
    (EWOULDBLOCK as EAGAIN) finds the name it stands for."""
    off = []
    values = {platform: _header_values([e for lines in fixture["names"].values() for e in lines.get(platform, [])])
              for platform in _FIXTURE_COLUMN}
    for name, cells in allowlist.items():
        platforms = fixture["names"].get(name, {})
        for platform, column in _FIXTURE_COLUMN.items():
            lines = platforms.get(platform) or []
            for entry in lines:
                assert entry["source"] in fixture["sources"], entry
            defines = [e for e in lines if re.search(rf'(?:define\s+{name}\b|add_errcode\("{name}")', e["text"])]
            if not defines:
                off.append(f"{name}: no {platform} line defines it; cite the header line before listing it.")
                continue
            given = values[platform].get(name)
            if given != cells[column]:
                off.append(f"{name}: the allowlist gives {cells[column]} on {platform}, its header lines {given}.")
    return off


def _fixture():
    return json.loads(HEADER_LINES.read_text(encoding="utf-8"))


def test_every_allowlist_cell_is_its_platforms_header_line():
    fixture = _fixture()
    assert _header_mismatches(ERRNO_ON_ALL_THREE, fixture) == []
    sources = fixture["sources"]
    assert len(sources) == 6, sorted(sources)
    for key, source in sources.items():
        assert re.fullmatch(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/[\w.-]+/\S+", source["url"]), key
        assert "/main/" not in source["url"] and "/master/" not in source["url"], (key, "a tag, not a branch")
        assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), key
    assert sorted(fixture["names"]) == sorted(ERRNO_ON_ALL_THREE), "one entry per allowlist name, no more"


@pytest.mark.parametrize("name,cells,expected", [
    ("EDEADLOCK", (35, 35, 36), "EDEADLOCK: no linux line defines it"),
    ("EWOULDBLOCK", (11, 35, 140), "EWOULDBLOCK: the allowlist gives 140 on windows, its header lines 10035."),
    ("EDEADLK", (35, 35, 36), "EDEADLK: the allowlist gives 35 on macos, its header lines 11."),
])
def test_a_cell_its_header_line_does_not_give_is_caught(name, cells, expected):
    """A name listed with no line for a platform, or a cell its line does not
    give (the C runtime's EWOULDBLOCK, which Python does not use; Linux's
    EDEADLK written into the macOS column), fails the check above."""
    off = _header_mismatches({**ERRNO_ON_ALL_THREE, name: cells}, _fixture())
    assert [o for o in off if o.startswith(expected)], off


# ---------------------------------------------------------------------------
# The build machines' own check: `python tests/<this file>` before PyInstaller.

def main():
    """Each allowlist cell for this platform against this interpreter's own
    errno, then the engine imported: a name the platform lacks, a wrong cell
    or an engine that does not import stops the build before it starts."""
    column = _PLATFORM_COLUMN.get(sys.platform)
    if column is None:
        print(f"no allowlist column for {sys.platform}", file=sys.stderr)
        return 1
    off = _cells_off_here(errno, column)
    if off:
        print("\n".join(off), file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT))
    import engine
    print(f"{len(ERRNO_ON_ALL_THREE)} errno names as listed for {sys.platform}; "
          f"the engine imports, its lock refusing on {sorted(engine._LOCK_REFUSALS)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
