"""The program reads only platform names that Linux, macOS and Windows all have.

The suite runs on Linux, so a module attribute that Linux has and macOS or
Windows lacks passes every test here and stops the frozen app at its start
on the other platform: ``errno.EDEADLOCK``, an alias Linux and Windows keep
and macOS does not, ended the desktop app two seconds after its start on
every Mac.

* The engine is imported in a fresh interpreter whose ``errno`` has no
  ``EDEADLOCK``, as macOS's has not; it must import, with the lock's
  refusals the four it names.
* A module the frozen app ships reads ``errno`` only by ``import errno`` and
  ``errno.NAME``, ``from errno import NAME`` or ``getattr(errno, "NAME")``
  (with or without a default), and its ``errorcode`` table only by number;
  every other use of the module the scan sees (another name for it, the
  module reached through a loader, another module or anything not a name,
  ``getattr(x, "errno")`` with no default) is refused with its line, since
  no reading can tell which names it reads (``_errno_reads`` lists each form,
  and what is left unread: an object's ``errno`` attribute, read plainly or
  with a default, through a name the shared resolver of tests/name_bindings.py
  cannot settle, a parameter without a default or a name bound by a form the
  resolver does not list). Every name read
  so, but one a default guards, is in a short
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

import name_bindings
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
    """(name, line) for every errno name `path` reads, and (None, line) for every
    use of the errno module, and every reach for an object's ``errno`` attribute,
    that is not one of the forms below.

    Read: ``errno.NAME`` under the name ``import errno`` binds, ``from errno import
    NAME`` and ``getattr(errno, "NAME")``; ``getattr(errno, "NAME", default)`` cannot
    fail and is no read. ``errorcode``, the table from number to name, is no error
    name and is let through only as a lookup by number, ``errno.errorcode[n]`` or
    ``errno.errorcode.get(n)``; any other use of it (``from errno import
    errorcode``, ``getattr(errno, "errorcode")``, its ``items()``) is refused, so no
    name is read back out of it. An object's ``errno`` attribute (an exception's
    number) is let through as ``x.errno``, ``getattr(x, "errno", default)`` or
    ``hasattr(x, "errno")`` where ``x`` is a name, or a chain of attributes on one,
    that the shared resolver (tests/name_bindings.py) cannot settle: a parameter
    without a default, a function's result, an exception caught.

    Refused: ``import errno as x``; the name ``errno`` anywhere else (bound,
    passed, returned, held in a container, a default, ``vars(errno)``, ``getattr``
    under another name or with a name not written out); the string ``"errno"``
    anywhere else (``import_module("errno")``, ``sys.modules["errno"]``,
    ``globals()["errno"]``, ``getattr(x, "errno")`` with no default, whatever
    ``x`` is); an ``errno`` attribute of a module an import binds (``from socket
    import errno``, ``socket.errno``, ``getattr(socket, "errno", None)``), of a
    name the resolver settles through any binding it follows (``s = socket``,
    ``(s := socket)``, unpacking, a ``for`` over a written tuple, ``with
    nullcontext(socket) as s``, a parameter's default) or of anything not a name
    (``import_module("socket").errno``, ``sys.modules["socket"].errno``). An
    alias another module makes is refused where it is made.

    Not read: the errno module reached as an object's ``errno`` attribute, as
    ``x.errno`` or with a default, through a name the resolver cannot settle (a
    parameter without a default handed ``socket``, a function's result), or
    through a name bound by a form the resolver does not list: a starred name in
    unpacking (``s, *_ = socket, 1``), a match pattern (``case s``, and ``case
    object(errno=e)``, which writes no ``errno`` attribute at all), a dict
    written out (``s = {"k": socket}["k"]``, ``for s in {socket: 1}``), a class
    attribute (``class K: s = socket``, then ``K.s.errno``), a value given by
    keyword (``nullcontext(enter_result=socket)``, ``__import__(name="socket")``);
    a module or name built at run time from pieces; and code run from a string,
    which the inventory of shipped modules refuses where exec, eval or compile is
    written as a bare name, and the import audit (tests/import_audit.py) refuses
    where it is called from a file the frozen app carries on a path the audit runs
    (``print.__self__.exec(...)``). No run-time check covers the errno names read
    by these forms: the question is which names every platform's branch reads, and
    a run takes its own platform's branch alone. Each remains a limit of this
    reading."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bindings = name_bindings.Bindings(tree)
    modules = set()
    reads, refused = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "errno" and a.asname not in (None, "errno"):
                    refused.append(node.lineno)
                elif a.name != "errno":
                    modules.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module == "errno":
            reads.extend((a.name, node.lineno) for a in node.names if a.name not in _ERRNO_TABLES)
            if any(a.name in _ERRNO_TABLES for a in node.names):
                refused.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            modules.update(a.asname or a.name for a in node.names)
            if any(a.name == "errno" for a in node.names):
                refused.append(node.lineno)
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def is_getattr(call, n):
        return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "getattr"
                and len(call.args) == n and not call.keywords)

    def literal(node):
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    def an_object(node):
        """A name, or attributes on one, that no import binds and the shared resolver
        cannot settle: what the scan cannot type."""
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id not in modules and node.id != "errno" \
            and all(name_bindings.opaque(p) for p in bindings.paths(node))

    def looked_up_by_number(table):
        """``errno.errorcode[n]`` or ``errno.errorcode.get(n[, default])``."""
        parent = parents.get(id(table))
        if isinstance(parent, ast.Subscript) and parent.value is table:
            return True
        call = parents.get(id(parent))
        return (isinstance(parent, ast.Attribute) and parent.attr == "get" and isinstance(call, ast.Call)
                and call.func is parent and len(call.args) in (1, 2) and not call.keywords)

    allowed = set()                      # the `errno` names and "errno" strings a read form holds
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "errno" \
                and isinstance(node.ctx, ast.Load) \
                and (node.attr not in _ERRNO_TABLES or looked_up_by_number(node)):
            allowed.add(id(node.value))
            reads.append((node.attr, node.lineno))
        elif (is_getattr(node, 2) or is_getattr(node, 3)) and isinstance(node.args[0], ast.Name) \
                and node.args[0].id == "errno" and literal(node.args[1]) and node.args[1].value not in _ERRNO_TABLES:
            allowed.add(id(node.args[0]))
            if len(node.args) == 2:
                reads.append((node.args[1].value, node.lineno))
        elif (is_getattr(node, 3) or isinstance(node, ast.Call) and getattr(node.func, "id", None) == "hasattr"
              and len(node.args) == 2) and literal(node.args[1]) and node.args[1].value == "errno" \
                and an_object(node.args[0]):
            allowed.add(id(node.args[1]))        # an exception's errno number, not the module
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "errno" and id(node) not in allowed \
                or isinstance(node, ast.Constant) and node.value == "errno" and id(node) not in allowed \
                or isinstance(node, ast.Attribute) and node.attr == "errno" and not an_object(node.value):
            refused.append(node.lineno)
    out = [(name, line) for name, line in reads if name not in _ERRNO_TABLES]
    return sorted(set(out + [(None, line) for line in refused]), key=lambda r: (r[1], r[0] or ""))


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
                refused.append(f"{name} uses errno at line {line} other than as errno.NAME, from errno import "
                               f"NAME or getattr(errno, 'NAME'), so no check can tell which names it reads, or "
                               f"whether all three platforms have them.")
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
    ("import errno\nname = 'EDEAD' + 'LOCK'\nx = getattr(errno, name)\n", [(None, 3)]),
    ("import errno\nx = getattr(errno, 'EDEADLOCK', None)\n", []),
    ("import errno\nx = getattr(errno, 'EDEAD' 'LOCK')\n", [("EDEADLOCK", 2)]),
    ("import errno\nx = errno.errorcode[35]\n", []),
    ("import errno\nx = errno.__dict__['EDEADLOCK']\n", [("__dict__", 2)]),
    ("from errno import EDEADLOCK as E\nx = E\n", [("EDEADLOCK", 1)]),
    ("def f(exc):\n    return exc.errno.real\n", []),
    ("def f(exc):\n    return getattr(exc, 'errno', None)\n", []),
    # Through another module, or a name other than its own: refused where it is bound or read.
    ("import socket\nx = socket.errno.EDEADLOCK\n", [(None, 2)]),
    ("from socket import errno as x\ny = x.EDEADLOCK\n", [(None, 1)]),
    ("from socket import errno\ny = errno.EDEADLOCK\n", [(None, 1), ("EDEADLOCK", 2)]),
    ("from os import errno as x\ny = getattr(x, 'EDEADLOCK')\n", [(None, 1)]),
    ("from socket import errno as x\ny = x.errorcode[35]\n", [(None, 1)]),
    ("import errno as e\nx = e.EDEADLOCK\n", [(None, 1)]),
    ("import socket\nx = getattr(socket, 'errno').EDEADLOCK\n", [(None, 2)]),
    ("import errno\n_e = errno\nx = _e.EDEADLOCK\n", [(None, 2)]),
    ("import errno\n_e = errno\n_f = _e\ndef f(exc):\n    return exc.errno == _f.EDEADLOCK\n", [(None, 2)]),
    ("import importlib\n_e = importlib.import_module('errno')\nx = _e.EDEADLOCK\n", [(None, 2)]),
    ("_e = __import__('errno')\nx = getattr(_e, 'EDEADLOCK')\n", [(None, 1)]),
    ("import sys\n_e = sys.modules['errno']\nx = _e.EDEADLOCK\n", [(None, 2)]),
    ("import importlib\nx = importlib.import_module('errno').EDEADLOCK\n", [(None, 2)]),
    # The deeper routes: each refused with its line.
    ("import errno\n_e, _n = errno, 1\nx = _e.EDEADLOCK\n", [(None, 2)]),
    ("import errno\nfor _e in (errno,):\n    x = _e.EDEADLOCK\n", [(None, 2)]),
    ("import errno\ndef f(e=errno):\n    return e.EDEADLOCK\n", [(None, 2)]),
    ("import errno\ndef g():\n    return errno\nx = g().EDEADLOCK\n", [(None, 3)]),
    ("import errno\ng = lambda: errno\nx = g().EDEADLOCK\n", [(None, 2)]),
    ("import errno\nclass C:\n    e = errno\nx = C.e.EDEADLOCK\n", [(None, 3)]),
    ("import errno\nx = {'e': errno}['e'].EDEADLOCK\n", [(None, 2)]),
    ("import errno\nx = [errno][0].EDEADLOCK\n", [(None, 2)]),
    ("import errno\n_e = errno if True else None\nx = _e.EDEADLOCK\n", [(None, 2)]),
    ("import contextlib, errno\nwith contextlib.nullcontext(errno) as e:\n    x = e.EDEADLOCK\n", [(None, 2)]),
    ("import errno\nx = globals()['errno'].EDEADLOCK\n", [(None, 2)]),
    ("import sys\nx = sys.modules.get('errno').EDEADLOCK\n", [(None, 2)]),
    ("import importlib\nload = importlib.import_module\nx = load('errno').EDEADLOCK\n", [(None, 3)]),
    ("from importlib import import_module as load\nx = load('errno').EDEADLOCK\n", [(None, 2)]),
    ("import errno\nx = vars(errno)['EDEADLOCK']\n", [(None, 2)]),
    ("import errno\nga = getattr\nx = ga(errno, 'EDEADLOCK')\n", [(None, 3)]),
    ("import builtins, errno\nx = builtins.getattr(errno, 'EDEADLOCK')\n", [(None, 2)]),
    ("import errno, operator\nx = operator.attrgetter('EDEADLOCK')(errno)\n", [(None, 2)]),
    ("import errno\nx = hasattr(errno, 'EDEADLOCK') and errno.EDEADLOCK\n", [(None, 2), ("EDEADLOCK", 2)]),
    # The module as another object's errno attribute, by getattr with no default or off anything not a name.
    ("import importlib\nx = getattr(importlib.import_module('socket'), 'errno').EDEADLOCK\n", [(None, 2)]),
    ("import sys\nx = getattr(sys.modules['socket'], 'errno').EDEADLOCK\n", [(None, 2)]),
    ("def f(m):\n    return getattr(m, 'errno').EDEADLOCK\n", [(None, 2)]),
    ("import importlib\nx = importlib.import_module('socket').errno.EDEADLOCK\n", [(None, 2)]),
    ("import sys\nx = sys.modules['socket'].errno.EDEADLOCK\n", [(None, 2)]),
    ("import importlib\nx = getattr(importlib.import_module('socket'), 'errno', None)\n", [(None, 2)]),
    ("import os\nx = os.path.errno\n", [(None, 2)]),
    # The errorcode table other than looked up by number: a name read back out of it.
    ("import errno\nx = {v: k for k, v in errno.errorcode.items()}['EDEADLOCK']\n", [(None, 2)]),
    ("from errno import errorcode\nx = {v: k for k, v in errorcode.items()}['EDEADLOCK']\n", [(None, 1)]),
    ("import errno\nx = getattr(errno, 'errorcode')\n", [(None, 2)]),
    ("import errno\nx = getattr(errno, 'errorcode', {})\n", [(None, 2)]),
    ("import errno\nx = list(errno.errorcode)\n", [(None, 2)]),
    ("import errno\nt = errno.errorcode\nx = t[35]\n", [(None, 2)]),
    # What stays let through: a lookup by number, an object's errno number, and the door a name leaves.
    ("import errno\nx = errno.errorcode.get(35, '?')\n", []),
    ("def f(exc):\n    return hasattr(exc, 'errno') and exc.errno\n", []),
    ("def f(self):\n    return self.exc.errno\n", []),
    ("def f(m):\n    return getattr(m, 'errno', None).EDEADLOCK\n", []),
    # The module's errno attribute through a name the shared resolver settles: refused where it is read.
    ("import socket\ns = socket\nx = s.errno.EDEADLOCK\n", [(None, 3)]),
    ("import socket\n(s := socket)\nx = s.errno.EDEADLOCK\n", [(None, 3)]),
    ("import socket\ns, n = socket, 1\nx = getattr(s, 'errno', None)\n", [(None, 3)]),
    ("import socket\nfor s in (socket,):\n    x = s.errno.EDEADLOCK\n", [(None, 3)]),
    ("import contextlib, socket\nwith contextlib.nullcontext(socket) as s:\n    x = s.errno.EDEADLOCK\n",
     [(None, 3)]),
    ("import socket\ndef f(s=socket):\n    return s.errno.EDEADLOCK\n", [(None, 3)]),
    ("from pkgutil import importlib as I\nx = I.import_module('socket').errno.EDEADLOCK\n", [(None, 2)]),
    ("import reprlib\nb = reprlib.builtins\nx = b.getattr(b.__import__('socket'), 'errno', 0)\n", [(None, 3)]),
    ("import sys\nS = dict(sys.modules)\ns = S['socket']\nx = s.errno.EDEADLOCK\n", [(None, 4)]),
    ("from sys import modules\ns = modules.get('socket')\nx = getattr(s, 'errno', None)\n", [(None, 3)]),
])
def test_the_scan_reads_each_route_to_an_errno_name(tmp_path, source, reads):
    """``errno.NAME``, ``from errno import NAME`` and ``getattr(errno, "NAME")``
    are read (a getattr with a default cannot fail and is no read; nor is a
    lookup by number in the errorcode table, nor an exception's errno number);
    every other form ``_errno_reads`` names is refused with its line (None), and
    an object's errno attribute through a name it cannot type is let through."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    assert _errno_reads(path) == reads


def test_an_alias_another_shipped_module_makes_is_refused_where_it_is_made(tmp_path):
    """`from helper import _e` then `_e.EDEADLOCK`: the module that binds `_e`
    to errno is shipped too, and its binding is refused."""
    (tmp_path / "engine.py").write_text("from helper import _e\nx = _e.EDEADLOCK\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("import errno\n_e = errno\n", encoding="utf-8")
    names = shipped_modules.program_modules(tmp_path, ["engine.py"])
    assert names == ["engine.py", "helper.py"], names
    assert {name: _errno_reads(tmp_path / name) for name in names} == {"engine.py": [], "helper.py": [(None, 2)]}


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
