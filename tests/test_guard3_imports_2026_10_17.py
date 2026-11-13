"""A module loaded by a route no reading can name is refused or marked.

* The shipped-module inventory (tests/shipped_modules.py) refuses each route it
  does not follow, each by itself, and lets through what only looks like one.
* The split census (tests/split_census.py) gives a "<dynamic module>" row for a
  module it cannot name, and the census test marks it unless DYNAMIC_MODULES
  lists it: a test that loads the engine by a variable and replaces `swe`
  through it fails the census as one that names the engine does.
* The resolver both share with the errno scan (tests/name_bindings.py)
  settles each binding form it follows, alone.
"""
from __future__ import annotations

import ast

import pytest

import name_bindings
import shipped_modules
import split_census
import test_split_astro_2026_10_14 as split_astro

DYNAMIC = "<dynamic module>"
# Written out here, not read from the module: a name dropped there is a case that fails here.
ROUTES = ("machinery", "SourceFileLoader", "SourcelessFileLoader", "ExtensionFileLoader", "find_spec",
          "load_module", "exec_module", "module_from_spec", "spec_from_loader", "meta_path")


def _tree(tmp_path, engine_source):
    (tmp_path / "engine.py").write_text(engine_source, encoding="utf-8")
    (tmp_path / "planted.py").write_text("X = 1\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- the inventory

@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("how", ["attribute", "name", "string", "import"])
def test_each_route_the_inventory_does_not_follow_is_refused_by_itself(tmp_path, route, how):
    """Each by its own name, alone, so a refusal dropped for one is seen."""
    source = {"attribute": f"import planted\nX = planted.{route}\n",
              "name": f"import planted\nX = {route}\n",
              "string": f"import planted\nX = getattr(planted, {route!r})\n",
              "import": f"import planted\nfrom planted import {route}\n"}[how]
    with pytest.raises(shipped_modules.UnreadableImport):
        shipped_modules.program_modules(_tree(tmp_path, source), ["engine.py"])


@pytest.mark.parametrize("source", [
    "exec('import planted')\n",
    "eval(\"__import__('planted')\")\n",
    "C = compile('import planted', 'x', 'exec')\n",
    "run = exec\n",
    "import builtins\nbuiltins.eval('1')\n",
    "import builtins as b\nb.compile('1', 'x', 'eval')\n",
    # A bare name is refused whatever binds it: in a class, a parameter, a function, an `except`, at module level.
    "class C:\n    exec = None\nexec('import planted')\n",
    "def f(exec=None):\n    pass\nexec('import planted')\n",
    "def g():\n    eval = 1\neval(\"__import__('planted')\")\n",
    "try:\n    pass\nexcept Exception as exec:\n    pass\nexec('import planted')\n",
    "exec = exec\nexec('import planted')\n",
    "def f(exec=exec):\n    exec('import planted')\n",
    # Before, beside or after a module-level binding.
    "C = compile('import planted', 'x', 'exec')\nfrom re import compile\n",
    "if X:\n    from re import compile\nC = compile('import planted', 'x', 'exec')\n",
    "from re import compile\ndel compile\nC = compile('import planted', 'x', 'exec')\n",
    "from re import compile\nfrom builtins import *\nC = compile('import planted', 'x', 'exec')\n",
    "from re import compile\ndef f():\n    global compile\n    compile = None\n"
    "C = compile('import planted', 'x', 'exec')\n",
    # After one: a definition, an import, an assignment. Nor does such a binding stand at the use where the file
    # empties its own namespace or runs a function's code under other globals.
    "def compile(x):\n    return x\nC = compile('1')\n",
    "from re import compile\nR = compile('x')\n",
    "import re\ncompile = re.compile\nR = compile('x')\n",
    "exec = print\nglobals().pop('exec')\nexec('import planted')\n",
    "exec = print\ndel globals()['exec']\nexec('import planted')\n",
    "import sys\nexec = print\ndelattr(sys.modules[__name__], 'exec')\nexec('import planted')\n",
    "def eval(s):\n    pass\nvars().pop('eval')\neval(\"__import__('planted')\")\n",
    "exec = print\nglobals().__delitem__('exec')\nexec('import planted')\n",
    "exec = print\nglobals().clear()\nexec('import planted')\n",
    "from re import compile\nlocals().pop('compile')\nC = compile('import planted', 'x', 'exec')\n",
    "import sys\nfrom re import compile\nsys.modules[__name__].__dict__.pop('compile')\n"
    "C = compile('import planted', 'x', 'exec')\n",
    "import types\nexec = print\ndef f():\n    exec('import planted')\ntypes.FunctionType(f.__code__, {})()\n",
])
def test_code_run_from_a_string_is_refused(tmp_path, source):
    with pytest.raises(shipped_modules.UnreadableImport):
        shipped_modules.program_modules(_tree(tmp_path, "import planted\n" + source), ["engine.py"])


@pytest.mark.parametrize("source", [
    "import re\nR = re.compile('x')\n",
    "def f(exc):\n    return getattr(exc, 'errno', None)\n",
    "def f(table, key):\n    return getattr(table, key)\n",
    "import os\nH = os.environ.get(K)\nV = vars(os)[K]\nW = os.__dict__.get(K)\n",
    # The allowlist's own: builtins by a written attribute or name, and an object's own namespace.
    "import builtins\nB = builtins.len\nfrom builtins import len as L\n",
    "import json\nD = json.__dict__['dumps']\n",
    "class C:\n    def __init__(self, name, value):\n        self.__dict__[name] = value\n",
    "import json\nJ = getattr(json, 'decoder')\nK = vars(json)['dumps']\n",
])
def test_what_only_looks_like_a_route_is_not_refused(tmp_path, source):
    """compile as another object's attribute, builtins by a written attribute, a
    lookup on anything but the import machinery."""
    tree = _tree(tmp_path, "import planted\n" + source)
    assert shipped_modules.program_modules(tree, ["engine.py"]) == ["engine.py", "planted.py"]


def test_the_program_reads_as_it_did():
    """Nothing the program writes today is refused, and the modules the app is
    made of are found."""
    found = shipped_modules.shipped_modules(split_astro.EXECUTABLE_DIR)
    assert {"app.py", "engine.py", "ephemeris.py", "time_zones.py", "desktop_launcher.py",
            "glyph_font.py"} <= set(found), found


# ---------------------------------------------------------------- the census

LOADS = [
    "import importlib\nNAME = 'engine'\nR = importlib.import_module(NAME)\nR.swe = None\n",
    "import importlib\nR = importlib.import_module('eng' + 'ine')\nR.swe = None\n",
    "import importlib\nR = importlib.import_module(name=NAME)\nR.swe = None\n",
    "import sys\nR = sys.modules[NAME]\nR.swe = None\n",
    "import sys\nR = sys.modules.get(NAME)\nR.swe = None\n",
    "R = __import__(NAME)\nR.swe = None\n",
    "from unittest import mock\nP = mock.patch(M + '.swe', None)\n",
    "from unittest import mock\nP = mock.patch(f'{M}.swe', None)\n",
    "from unittest.mock import patch\nP = patch(target=M + '.swe', new=None)\n",
    "import importlib\nR = getattr(importlib, 'import_' + 'module')('engine')\nR.swe = None\n",
    "import importlib\nR = vars(importlib)['import_' + 'module']('engine')\nR.swe = None\n",
    "import builtins\nR = builtins.__dict__[K]('engine')\nR.swe = None\n",
    "from importlib import import_module as load\nR = load(NAME)\nR.swe = None\n",
    "import importlib\nload = getattr(importlib, 'import_module')\nR = load('engine')\nR.swe = None\n",
    "import importlib\nload = vars(importlib)['import_module']\nR = load('engine')\nR.swe = None\n",
    "import importlib\ndef _tool(name):\n    return importlib.import_module(name)\nR = _tool(NAME)\nR.swe = None\n",
    # pytest's string form, a computed patch.multiple target, and a built key on builtins' or importlib's namespace.
    "def test_x(monkeypatch):\n    monkeypatch.setattr(M + '.swe', None)\n",
    "def test_x(monkeypatch):\n    monkeypatch.setattr(f'{M}.swe', None, raising=False)\n",
    "def test_x(monkeypatch):\n    monkeypatch.setattr(target=M + '.swe', name=None)\n",
    "def test_x(monkeypatch):\n    monkeypatch.delattr(M + '.swe')\n",
    "def test_x(monkeypatch, a):\n    monkeypatch.setattr(*a)\n",
    "def test_x(monkeypatch, k):\n    monkeypatch.delattr(**k)\n",
    # The patch family by one rule: a target the census cannot name, in every member.
    "from unittest import mock\nP = mock.patch.dict(M + '.__dict__', {'swe': None})\n",
    "from unittest import mock\nP = mock.patch.dict(f'{M}.__dict__', values={'swe': None})\n",
    "from unittest import mock\nP = mock.patch.dict(in_dict=D, values={'swe': None})\n",
    "from unittest import mock\nP = mock.patch.dict(D, {'swe': None})\n",
    "from unittest import mock\nP = mock.patch.dict(**K)\n",
    "from unittest import mock\nP = mock.patch.object(get(M), 'swe', None)\n",
    "from unittest import mock\nP = mock.patch.object(D, 'swe', None)\n",
    "from unittest import mock\nP = mock.patch.object(target=R if X else None, attribute='swe')\n",
    "from unittest import mock\nP = mock.patch.multiple(target=M, swe=None)\n",
    "from unittest import mock\nP = mock.patch(*A)\n",
    "def test_x(monkeypatch):\n    monkeypatch.setattr(get(M), 'swe', None)\n",
    "def test_x(monkeypatch):\n    monkeypatch.setitem(vars(get(M)), 'swe', None)\n",
    "def test_x(monkeypatch):\n    monkeypatch.delitem(get(M).__dict__, 'swe')\n",
    "import operator\noperator.setitem(vars(get(M)), 'swe', None)\n",
    "setattr(get(M), 'swe', None)\n",
    "delattr(get(M), 'swe')\n",
    # The family through a name bound to a member.
    "from unittest.mock import patch as p\nP = p(M + '.swe', None)\n",
    "from unittest.mock import patch as p\nP = p.object(D, 'swe', None)\n",
    "from unittest import mock\npo = mock.patch.dict\nP = po(M + '.__dict__', {'swe': None})\n",
    "def test_x(monkeypatch):\n    s = monkeypatch.setattr\n    s(M + '.swe', None)\n",
    "from unittest import mock\np = getattr(mock, 'patch')\nP = p(M + '.swe', None)\n",
    "from unittest import mock\nP = (p := mock.patch)(M + '.swe', None)\n",
    "from unittest import mock\np, q = mock.patch, None\nP = p(M + '.swe', None)\n",
    "from unittest import mock\ndef f(p=mock.patch):\n    return p(M + '.swe', None)\n",
    "import operator\nfrom unittest import mock\nP = operator.attrgetter('patch.dict')(mock)(M, {'swe': None})\n",
    "from operator import setitem as put\nput(vars(get(M)), 'swe', None)\n",
    "import pytest\nwith pytest.MonkeyPatch.context() as mp:\n    mp.delattr(M + '.swe', raising=False)\n",
    "from unittest import mock\nP = mock.patch.multiple(M, swe=None)\n",
    "from unittest import mock\nP = mock.patch.multiple(M + '', swe=None)\n",
    "R = __builtins__['__imp' + 'ort__'](NAME)\nR.swe = None\n",
    "R = __builtins__.get(K)('engine')\nR.swe = None\n",
    "import importlib\nR = vars(importlib).get('import_' + 'module')('engine')\nR.swe = None\n",
    "import builtins\nR = builtins.__dict__.get(K)('engine')\nR.swe = None\n",    # The import machinery reached through another module or a name the resolver settles.
    "from pkgutil import importlib as I\nR = I.__dict__[K]('engine')\nR.swe = None\n",
    "import reprlib\nR = vars(reprlib.builtins)[K](NAME)\nR.swe = None\n",
    "import builtins\nb = builtins\nR = getattr(b, K)('engine')\nR.swe = None\n",
    "import importlib\nd = vars(importlib)\nR = d[K]('engine')\nR.swe = None\n",
]


# The module object fetched by a name not written out, then patched: bound anywhere in the file, through any
# binding the shared resolver follows, sys.modules under any name or copied. (A fetch from sys.modules is a row of
# its own too, at its line: these ask only for the row at the patch.)
FETCHED = [
    "import app as t\ndef test_x(monkeypatch):\n    R = getattr(t, M)\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t\nR = vars(t)[M]\ndef test_x(monkeypatch):\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t\ndef test_x(monkeypatch):\n    monkeypatch.setattr(vars(t)[M], 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    R = dict(sys.modules)[M]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    R = next(m for n, m in sys.modules.items() if n == M)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    R = sys.modules.copy().get(M)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    R = vars(sys)['modules'][M]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    for n, m in sys.modules.items():\n        if n == M:\n"
    "            monkeypatch.setattr(m, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    S = sys.modules\n    R = S[M]\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    S = dict(sys.modules)\n    R = S[M]\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    S = sys.modules.copy()\n    R = S.get(M)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "from sys import modules\ndef test_x(monkeypatch):\n    R = modules[M]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "from sys import modules as mm\ndef test_x(monkeypatch):\n    R = mm.get(M)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    m = sys\n    R = m.modules[M]\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import os\ndef test_x(monkeypatch):\n    R = os.sys.modules[M]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import sys\ndef test_x(monkeypatch):\n    R = {**sys.modules}[M]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t\ndef test_x(monkeypatch):\n    R = getattr(t, M)\n    Q = R\n"
    "    monkeypatch.setattr(Q, 'swe', None)\n",
    "import app as t\ndef test_y(monkeypatch, R=getattr(t, M)):\n    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t\nga = getattr\ndef test_x(monkeypatch):\n    R = ga(t, M)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t, operator\ndef test_x(monkeypatch):\n    R = operator.attrgetter(M)(t)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
    "import app as t, functools\ndef test_x(monkeypatch):\n    R = functools.reduce(getattr, [M], t)\n"
    "    monkeypatch.setattr(R, 'swe', None)\n",
]


@pytest.mark.parametrize("planted", FETCHED)
def test_a_patch_target_fetched_by_a_name_not_written_out_is_a_row(planted):
    """The row stands at the patch, the call that replaces something through what was fetched."""
    tree = ast.parse(planted)
    rows = split_census.sites(tree)                        # settles the file's names first
    patch = max(n.lineno for n in ast.walk(tree) if split_census.family_target(n) is not None)
    assert any(row[2] == DYNAMIC and row[0] == patch for row in rows), rows


@pytest.mark.parametrize("planted", LOADS)
def test_a_module_the_census_cannot_name_is_a_row(planted):
    rows = [row for row in split_census.sites(ast.parse(planted)) if row[2] == DYNAMIC]
    assert len(rows) == 1, split_census.sites(ast.parse(planted))


@pytest.mark.parametrize("planted, expected", [
    ("import sys\nR = sys.modules[__name__]\nR.FIX = 1\n", []),
    ("def f(patch):\n    patch()\n", []),
    ("import importlib\nR = importlib.import_module('ephemeris')\nR.swe = None\n", []),
    ("import importlib\ndef _tool(name):\n    return importlib.import_module(name)\nR = _tool('engine')\n"
     "R.swe = None\n", [(5, "assignment", "swe")]),
    ("import importlib\ndef _tool(name):\n    return importlib.import_module(name)\nR = _tool('mutation_scan')\n", []),
    # (one line each where a target is written out: a longer string that says so is a script the census reads)
    ("monkeypatch.setattr('engine.swe', None)", [(1, "monkeypatch.setattr", "swe")]),
    ("monkeypatch.delattr('engine.swe', raising=False)", [(1, "monkeypatch.delattr", "swe")]),
    ("def test_x(monkeypatch):\n    monkeypatch.setattr('ephemeris.swe', None)\n"
     "    monkeypatch.delattr('os.sep')\n", []),
    ("def test_x(monkeypatch, obj, name):\n    monkeypatch.setattr(obj, name, None)\n"
     "    monkeypatch.delattr(obj, name)\n    setattr(obj, name, None)\n    delattr(obj, name)\n", []),
    ("from unittest import mock\nP = mock.patch.multiple('engine', swe=None, create=True)\n"
     "Q = mock.patch.multiple(engine, _EPHEMERIS_FOLDER='/x')\n",
     [(2, "mock.patch.multiple", "swe"), (3, "mock.patch.multiple", "_EPHEMERIS_FOLDER")]),
    ("from unittest import mock\nP = mock.patch.multiple('ephemeris', swe=None)\n", []),
    ("import importlib\nR = vars(importlib).get('reload')\nB = __builtins__['len']\n", []),
    ("import os\nfrom unittest import mock\nP = mock.patch.dict(os.environ, {'A': '1'})\n", []),
    ("import sys\nfrom unittest import mock\nP = mock.patch.dict(sys.modules, {'x': None})\n"
     "Q = mock.patch.object(sys, 'argv', [])\nmock.patch.stopall()\n", []),
    ("import importlib\nfrom unittest import mock\n"
     "P = mock.patch.object(importlib.import_module('ephemeris'), 'swe', None)\n", []),
    ("monkeypatch.setattr(engine['_RUN'], 'X', 1)", []),
    ("mock.patch.object(engine.swe, 'calc', None)", []),
    ("mock.patch.dict('engine.__dict__', values={'swe': None})", [(1, "mock.patch.dict", "swe")]),
    # The member left unread, by the docstring: the object form given a bare variable the census does not resolve.
    ("def test_x(monkeypatch, module):\n    monkeypatch.setattr(module, 'X', 1)\n    setattr(module, 'Y', 2)\n", []),
    # An alias read as the member it names (one line each: see above).
    ("from unittest.mock import patch as p; P = p('engine.swe', None)", [(1, "unittest.mock.patch", "swe")]),
    ("P = getattr(mock, 'patch')('engine.swe', None)", [(1, "mock.patch", "swe")]),
    ("import app; monkeypatch.setattr(app.engine, 'swe', None)", [(1, "monkeypatch.setattr", "swe")]),
    ("import importlib\nR = getattr(importlib, 'import_module')('engine')\nR.swe = None\n", [(3, "assignment", "swe")]),
    ("s = monkeypatch.setattr; s('engine.swe', None)", [(1, "monkeypatch.setattr", "swe")]),
    # sys.modules patched by its key, and objects fetched by a written name: nothing computed.
    ("import sys\ndef test_x(monkeypatch, fake):\n    monkeypatch.setitem(sys.modules, 'x', fake)\n"
     "    R = sys.modules['json']\n    monkeypatch.setattr(R, 'dumps', None)\n", []),
    ("import json\ndef test_x(monkeypatch):\n    R = getattr(json, 'decoder')\n"
     "    monkeypatch.setattr(R, 'X', 1)\n", []),
])
def test_a_module_the_census_can_name_is_read_as_it_is(planted, expected):
    """The file's own module, a call with no module at all, a written-out name,
    and a function that hands its name on to a loader, called with a literal:
    read, not marked; the engine loaded through that function is the engine."""
    assert split_census.sites(ast.parse(planted)) == expected


# The engine bound by a form only the shared resolver follows, then patched as an object: the engine, a site.
ENGINE_BOUND = [
    "E, n = sys.modules['engine'], 1\nP = mock.patch.object(E, 'swe', None)\n",
    "for E in (sys.modules['engine'],):\n    P = mock.patch.object(E, 'swe', None)\n",
    "with contextlib.nullcontext(sys.modules['engine']) as E:\n    P = mock.patch.object(E, 'swe', None)\n",
    "E, n = app.engine, 1\nP = mock.patch.object(E, 'swe', None)\n",
]


@pytest.mark.parametrize("planted", ENGINE_BOUND)
def test_the_engine_bound_by_unpacking_a_for_or_a_with_is_the_engine(planted):
    source = "import app, contextlib, sys\nfrom unittest import mock\n" + planted
    assert split_census.sites(ast.parse(source)) == [(4, "mock.patch.object", "swe")]


@pytest.mark.parametrize("planted", [
    "R, n = sys.modules['engine'], 1\nP = mock.patch.object(R, 'swe', None)\n",
    "for R in (sys.modules['engine'],):\n    pass\nP = mock.patch.object(R, 'swe', None)\n",
    "with contextlib.nullcontext(app.engine) as R:\n    pass\nP = mock.patch.object(R, 'swe', None)\n",
    "(R := sys.modules['engine'])\nP = mock.patch.object(R, 'swe', None)\n",
    "def f(R=sys.modules['engine']):\n    P = mock.patch.object(R, 'swe', None)\n",
    "def g():\n    global R\n    R = sys.modules['engine']\nP = mock.patch.object(R, 'swe', None)\n",
    "[0 for R in (sys.modules['engine'],)]\nP = mock.patch.object(R, 'swe', None)\n",
])
def test_a_name_no_convention_gives_the_engine_bound_by_any_listed_form_is_the_engine(planted):
    tree = ast.parse("import app, contextlib, sys\nfrom unittest import mock\n" + planted)
    patch = max(n.lineno for n in ast.walk(tree) if split_census.family_target(n) is not None)
    assert split_census.sites(tree) == [(patch, "mock.patch.object", "swe")]


def test_a_name_the_scope_binds_to_a_module_and_the_file_to_the_engine_is_a_row():
    """The scope's own reading wins (json there), but the name is not let through
    as settled: what it holds depends on which binding ran."""
    source = ("import json, sys\nfrom unittest import mock\nR, n = sys.modules['engine'], 1\n"
              "def f():\n    R = json\n    return mock.patch.object(R, 'swe', None)\n")
    assert split_census.sites(ast.parse(source)) == [(6, "mock.patch.object", DYNAMIC)]


def test_a_name_a_function_binds_to_something_else_is_not_the_engine_there():
    source = ("import sys\nfrom unittest import mock\nR = sys.modules['engine']\n"
              "def f():\n    R = object()\n    return mock.patch.object(R, 'swe', None)\n")
    assert not any(row[2] == "swe" for row in split_census.sites(ast.parse(source)))


def test_a_module_not_the_engine_bound_by_unpacking_is_no_site():
    source = "import json\nfrom unittest import mock\nE, n = json, 1\nP = mock.patch.object(E, 'swe', None)\n"
    assert split_census.sites(ast.parse(source)) == []


@pytest.mark.parametrize("body", [
    "    R = importlib.import_module(NAME)\n    monkeypatch.setattr(R, 'swe', None)\n",
    "    monkeypatch.setattr(NAME + '.swe', None)\n",
    "    from unittest import mock\n    mock.patch.dict(NAME + '.__dict__', {'swe': None}).start()\n",
    "    import sys\n    R = dict(sys.modules)[NAME]\n    monkeypatch.setattr(R, 'swe', None)\n",
    "    from unittest.mock import patch as p\n    p.dict(NAME + '.__dict__', {'swe': None}).start()\n",
    "    import sys\n    R, n = sys.modules['engine'], 1\n    monkeypatch.setattr(R, 'swe', None)\n",
    "    import sys\n    for R in (sys.modules['engine'],):\n        monkeypatch.setattr(R, 'swe', None)\n",
])
def test_a_test_that_loads_the_engine_by_a_variable_and_replaces_swe_fails_the_census(tmp_path, body):
    """End to end: the plant among the real tests, through the census test itself."""
    plant = tmp_path / "test_zz_planted_census.py"
    plant.write_text("import importlib\n\nNAME = 'engine'\n\n\ndef test_x(monkeypatch):\n" + body,
                     encoding="utf-8")
    real_paths = split_astro._paths()
    split_astro.test_no_site_replaces_through_the_engine_a_name_a_new_module_binds_or_reads(
        split_census.census(real_paths))                                        # premise: clean without it
    census = split_census.census(real_paths + [plant])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(split_astro, "_paths", lambda: real_paths + [plant])        # the plant's key is read too
        with pytest.raises(AssertionError, match="test_zz_planted_census.py"):
            split_astro.test_no_site_replaces_through_the_engine_a_name_a_new_module_binds_or_reads(census)


# ---------------------------------------------------------------- the shared resolver alone

@pytest.mark.parametrize("source, expected", [
    # imports, a module imported from another module among them
    ("import importlib as X\n", {"importlib"}),
    ("import os.path as X\n", {"os.path"}),
    ("from unittest.mock import patch as X\n", {"unittest.mock.patch"}),
    ("from pkgutil import importlib as X\n", {"importlib"}),
    ("from sys import modules as X\n", {"sys.modules"}),
    # assignment of every kind
    ("import sys\nX = sys\n", {"sys"}),
    ("import sys\nX: object = sys\n", {"sys"}),
    ("import sys\nX = sys\nX += 1\n", {"sys", "?X"}),
    ("import sys, json\nX, Y = sys, json\n", {"sys"}),
    ("import sys, json\n[Y, X] = [json, sys]\n", {"sys"}),
    ("import sys\n(X := sys)\n", {"sys"}),
    ("import sys, json\nfor X in (sys, json):\n    pass\n", {"sys", "json"}),
    ("import sys\nfor X in [sys]:\n    pass\n", {"sys"}),
    ("import sys\nfor X in sys.argv:\n    pass\n", {"?X"}),
    ("import contextlib, sys\nwith contextlib.nullcontext(sys) as X:\n    pass\n", {"sys"}),
    ("with open('f') as X:\n    pass\n", {"?X"}),
    ("import sys\ndef f(X=sys):\n    pass\n", {"sys"}),
    ("import sys\ndef f(*, X=sys):\n    pass\n", {"sys"}),
    ("import sys\nf = lambda X=sys: X\n", {"sys"}),
    ("import sys\ndef f():\n    global X\n    X = sys\n", {"sys"}),
    ("import sys\ndef f():\n    X = None\n    def g():\n        nonlocal X\n        X = sys\n", {"sys", "?X"}),
    # an attribute of a resolved module, the modules the scans ask about taken as themselves
    ("import reprlib\nX = reprlib.builtins\n", {"builtins"}),
    ("import json\nX = json.__builtins__\n", {"builtins.__dict__"}),
    ("import os\nX = os.sys.modules\n", {"sys.modules"}),
    ("import socket\nX = socket.errno\n", {"errno"}),
    ("X = __builtins__\n", {"builtins.__dict__"}),
    # getattr, attrgetter, namespaces and lookups by a written name
    ("import json\nX = getattr(json, 'decoder')\n", {"json.decoder"}),
    ("import json\nX = getattr(json, 'decoder', None)\n", {"json.decoder"}),
    ("import json, operator\nX = operator.attrgetter('decoder.JSONDecoder')(json)\n", {"json.decoder.JSONDecoder"}),
    ("import json\nX = vars(json)\n", {"json.__dict__"}),
    ("import json\nX = json.__dict__['dumps']\n", {"json.dumps"}),
    ("import json\nX = vars(json).get('dumps')\n", {"json.dumps"}),
    ("import sys\nX = sys.modules['json']\n", {"json"}),
    ("import sys\nX = sys.modules.get('json', None)\n", {"json"}),
    ("import sys, json\nX = (json, sys)[1]\n", {"sys"}),
    ("import builtins\nX = vars(builtins)['__imp' 'ort__']\n", {"builtins.__import__"}),
    # copies: the same keys, marked
    ("import sys\nX = dict(sys.modules)\n", {"sys.modules~"}),
    ("import sys\nX = sys.modules.copy()\n", {"sys.modules~"}),
    ("import sys\nX = {**sys.modules}\n", {"sys.modules~"}),
    ("import sys\nX = dict(sys.modules)['json']\n", {"json"}),
    # callables under another name
    ("X = getattr\n", {"builtins.getattr"}),
    ("from unittest import mock\nX = getattr(mock, 'patch')\n", {"unittest.mock.patch"}),
    ("from unittest import mock\n(X := mock.patch)\n", {"unittest.mock.patch"}),
    ("def f(monkeypatch):\n    X = monkeypatch.setattr\n", {"?monkeypatch.setattr"}),
    # loads by a written name
    ("import importlib\nX = importlib.import_module('os.path')\n", {"os.path"}),
    ("X = __import__('os.path')\n", {"os"}),
    ("import json, sys\nX = json if C else sys\n", {"json", "sys"}),
    ("import json\nX = None or json\n", {"json"}),
    # what it cannot settle
    ("def f(X):\n    pass\n", {"?X"}),
    ("import json\nX = getattr(json, NAME)\n", {"?X"}),
    ("X = globals()[NAME]\n", {"?X"}),
    ("X = make()\n", {"?X"}),
    ("X = Y = None\nX = X.a\n", {"?X"}),
])
def test_the_shared_resolver_settles_each_binding_form(source, expected):
    bindings = name_bindings.Bindings(ast.parse(source))
    assert bindings.paths(ast.Name(id="X", ctx=ast.Load())) == expected
