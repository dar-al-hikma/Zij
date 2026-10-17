"""A module loaded through another name for an import function is still found.

The shipped-module inventory (tests/shipped_modules.py) and the split census
(tests/split_census.py) read imports by `ast`. Each followed `import_module` and
`__import__` only under those names; a call through a name bound to either
(`load = importlib.import_module`, `from importlib import import_module as load`)
went unread. The inventory now follows such a name, and refuses a load it cannot
name; the census reads a call through one as the import it is. So too a call
whose callee is an expression holding a loader, a walrus among them
(`(f := importlib.import_module)('x')`). A walrus that binds a loader and hands it
on (`map(f := importlib.import_module, ['x'])`) is refused, as a loader passed on
by name is.
"""
from __future__ import annotations

import ast

import pytest

import shipped_modules
import split_census

ALIASED = [
    "from importlib import import_module as load\nM = load('planted')\n",
    "import importlib\nimp = importlib.import_module\nM = imp('planted')\n",
    "import importlib\nimp = importlib.import_module\nagain = imp\n\n\ndef later():\n    return again('planted')\n",
    "load = __import__\nM = load('planted')\n",
    "from builtins import __import__ as load\nM = load('planted')\n",
    "import importlib as il\n\n\ndef later():\n    return il.import_module('planted')\n",
    "import importlib\nM = (f := importlib.import_module)('planted')\n",
    "from importlib import import_module as load\nM = (g := load)('planted')\n",
    "import importlib\nM = (f := importlib.import_module)('planted')\nN = f('planted')\n",
    "import importlib\n(f := importlib.import_module)\nM = f('planted')\n",
    "import importlib\nif (f := importlib.import_module):\n    M = f('planted')\n",
]


def _tree(tmp_path, engine_source):
    (tmp_path / "engine.py").write_text(engine_source, encoding="utf-8")
    (tmp_path / "planted.py").write_text("X = 1\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("engine_source", ALIASED)
def test_a_module_loaded_through_an_alias_is_in_the_inventory(tmp_path, engine_source):
    tree = _tree(tmp_path, engine_source)
    assert shipped_modules.program_modules(tree, ["engine.py"]) == ["engine.py", "planted.py"]


@pytest.mark.parametrize("engine_source", [
    "import importlib\nname = 'plan' + 'ted'\nM = importlib.import_module(name)\n",
    "from importlib import import_module as load\nM = load(NAME)\n",
    "import importlib\nM = list(map(importlib.import_module, ['planted']))\n",
    "import importlib\nM = getattr(importlib, 'import_module')('planted')\n",
    "import runpy\nM = runpy.run_path('planted.py')\n",
    "import importlib.util\nS = importlib.util.spec_from_file_location('p', 'planted.py')\n",
    "import importlib\nM = (f := importlib.import_module)(NAME)\n",
    "import importlib\nM = (f := importlib.import_module)()\n",
    "import importlib\nM = (None or importlib.import_module)('planted')\n",
    "import importlib\nM = [importlib.import_module][0]('planted')\n",
    "import importlib\nM = list(map(f := importlib.import_module, ['planted']))\n",
    "import importlib\n\n\ndef g(h):\n    return h('planted')\n\n\nM = g(f := importlib.import_module)\n",
    "from importlib import import_module as load\nM = list(map(f := load, ['planted']))\n",
    "import importlib\nx = (f := importlib.import_module)\nM = x('planted')\n",
    "import importlib\nM = (g := (f := importlib.import_module))('json')\nN = g('planted')\n",
    "import importlib\n\n\ndef k():\n    return (f := importlib.import_module)\n\n\nM = k()('planted')\n",
])
def test_a_load_the_inventory_cannot_name_is_refused(tmp_path, engine_source):
    tree = _tree(tmp_path, engine_source)
    with pytest.raises(shipped_modules.UnreadableImport):
        shipped_modules.program_modules(tree, ["engine.py"])


@pytest.mark.parametrize("engine_source", [
    "import importlib\nF = getattr(importlib.import_module('planted'), 'f')(NAME)\n",
    "import importlib\nF = (importlib.import_module('planted') or None).f(NAME)\n",
])
def test_a_call_on_what_a_loader_returned_is_no_loader_call(tmp_path, engine_source):
    """A callee that holds a loader only as a call of its own is read for that call,
    and the outer call, whatever its argument, is not taken for a load."""
    tree = _tree(tmp_path, engine_source)
    assert shipped_modules.program_modules(tree, ["engine.py"]) == ["engine.py", "planted.py"]


def test_the_honest_imports_still_arrive(tmp_path):
    """The forms the program writes today, unchanged: a plain import, a from-import,
    a literal import_module, the standard library's importlib.resources."""
    tree = _tree(tmp_path, "import planted\nimport importlib.resources\nfrom json import dumps\n"
                           "import importlib\nM = importlib.import_module('planted')\n"
                           "T = importlib.resources.files('tzdata')\n")
    assert shipped_modules.program_modules(tree, ["engine.py"]) == ["engine.py", "planted.py"]


@pytest.mark.parametrize("planted, expected", [
    ("from importlib import import_module as load\nm = load('engine')\nm._EPHEMERIS_FOLDER = '/x'\n",
     [(3, "store", "_EPHEMERIS_FOLDER")]),
    ("import importlib\nf = importlib.import_module\nm = f('engine')\nm._EPHEMERIS_FOLDER = '/x'\n",
     [(4, "store", "_EPHEMERIS_FOLDER")]),
    ("imp = __import__\nimp('engine')._DELTA_T_REFERENCE = 1\n", [(2, "store", "_DELTA_T_REFERENCE")]),
    ("def f():\n    from importlib import import_module as _l\n    return _l('engine')._EPHEMERIS_FOLDER\n",
     [(3, "load", "_EPHEMERIS_FOLDER")]),
    ("from importlib import import_module as load\nm = load('ephemeris')\nm._EPHEMERIS_FOLDER = '/x'\n", []),
    ("import importlib\n(f := importlib.import_module)('engine')._EPHEMERIS_FOLDER = '/x'\n",
     [(2, "store", "_EPHEMERIS_FOLDER")]),
    ("from importlib import import_module as load\nx = (g := load)('engine')._DELTA_T_REFERENCE\n",
     [(2, "load", "_DELTA_T_REFERENCE")]),
    ("import importlib\n(f := importlib.import_module)('ephemeris')._EPHEMERIS_FOLDER = '/x'\n", []),
])
def test_the_census_reads_an_engine_loaded_through_an_alias(planted, expected):
    assert split_census.rebound(ast.parse(planted)) == expected


@pytest.mark.parametrize("planted, line", [
    ("from importlib import import_module as load\nm = load('engine')\nm.SOMETHING = 1\n", 3),
    ("import importlib\n(f := importlib.import_module)('engine').SOMETHING = 1\n", 2),
])
def test_the_census_counts_a_replacement_through_an_alias(planted, line):
    assert split_census.sites(ast.parse(planted)) == [(line, "assignment", "SOMETHING")]
