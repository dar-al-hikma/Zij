"""The astronomical core out of engine.py, and nothing left unreached by the move.

ephemeris.py holds Swiss Ephemeris's private folder and its checks, the
library's one import, the thread guard, the Delta T check, the refusals and
their sentences, `swe`, the Moshier flag, the Streamlit cache clear beside the
flag it reads, and the civil calendar. time_zones.py holds the pinned zone
database's reset, the linked zones, the aliases, the named mean times, the
areas and stretches, NamedZoneRefusal and named_zone_state. Both are leaves:
neither imports the engine, and time_zones.py imports nothing of
ephemeris.py. engine.py takes both whole, `from ephemeris import *` and `from
time_zones import *` its first statements, and so re-exports every name they
bind but two: _EPHEMERIS_FOLDER and _DELTA_T_REFERENCE, which ephemeris.py
rebinds as it runs. Through the engine they would be the values they had at
the engine's import; they are read in ephemeris.py, and a read through the
engine fails instead.

The previous split's trap (tests/test_engine_split_2026_09_15.py: readings
assigned into a namespace no function read) is a test that replaces a name
in one module while the code that reads it lives in another. So:

* the census (tests/split_census.py): every site in the tests, and in every
  script a test hands to a subprocess, that replaces an attribute of the
  engine. A site that replaces a name either new module binds or reads -- the
  standard modules and names they read among them -- must replace it in that
  module instead, unless it is listed in ENGINE_OWN with why the engine's own
  binding is the one the test means. A site whose name is not written in it
  (a variable, a mapping not written out: the census's "<dynamic>") is marked
  too, unless DYNAMIC lists it with the names it takes and none of them moved;
* no read or write of a withheld name through the engine, in the program,
  the tests or their scripts;
* static: the leaves import neither the engine nor each other, ephemeris.py
  alone imports swisseph and engine.py imports it first, engine.py and app.py
  read no withheld name by its bare name, each module's __all__ is every name
  it binds but the withheld, and the moved code is pinned;
* dynamic, in fresh interpreters, each new module imported first: the names
  re-exported, `swe` one object, the star import's set, a reload of the
  engine that keeps the folder and the classes and does not empty
  Streamlit's caches again, and a reload and a fresh import of ephemeris.py
  that find the held folder and register no second exit hook;
* no test opens engine.py by name for a name that moved.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import subprocess
import symtable
import sys
from pathlib import Path

import pytest

import split_census
from conftest import EXECUTABLE_DIR, source_files

TESTS = Path(__file__).resolve().parent
NEW = ("ephemeris.py", "time_zones.py")
WITHHELD = split_census.WITHHELD
TIMEOUT = 300

# Sites that replace, through the engine, a name a new module reads, kept as
# they are: the code the test drives is the engine's own and reads the
# engine's binding. (file, name): why.
ENGINE_OWN = {
    ("test_sc2_saved_state_2026_10_07.py", "datetime"):
        "it freezes the clock of the engine's store code (_preserve_unreadable_store's copy name), which reads "
        "engine.datetime; named_zone_state's datetime is time_zones.py's and is not what the test drives",
}

# Sites on the engine whose name is not written in them ("<dynamic>"), kept:
# (file, the function holding the site, the site's line as written): (every
# name the site is handed, why). Any other such site is marked: nothing tells
# which names it replaces.
DYNAMIC = {
    ("test_b15_svg_xml_illegal_2026_10_11.py", "_page_svgs", "monkeypatch.setattr(module, fn, spy)"):
        (("generate_hybrid_svg", "generate_multiwheel_svg"), "the loop's own two names: the engine's wheel writers"),
    ("test_ks_store_and_preferences_locked_2026_10_06.py", "_signal_on_thread_lock",
     "monkeypatch.setattr(engine, name, _SignallingLock(real, waiting, then, on_wait, exempt), raising=False)"):
        (("_STORE_THREAD_LOCK", "_PREFERENCES_THREAD_LOCK"), "every caller hands one of the store's two thread locks"),
    ("test_ks_store_and_preferences_locked_2026_10_06.py", "_two_windows",
     "monkeypatch.setattr(engine, gate_name, held)"):
        (("write_saved_charts", "write_preferences"), "every caller hands one of the store's two writers"),
}

# What each new module adds to the text it took from engine.py: its docstring,
# these imports and its __all__ (the move's commit copied the rest byte for
# byte). MOVED_CODE pins the rest by ast.dump (comments aside): a later change
# to moved code updates its pin in the same commit and says why.
ADDED_IMPORTS = {"ephemeris.py": {"import streamlit as st", "import math"},
                 "time_zones.py": {"from datetime import datetime, timedelta, timezone", "import json", "import os",
                                   "import zoneinfo", "from zoneinfo import ZoneInfo, ZoneInfoNotFoundError",
                                   "import contextlib", "import sqlite3", "import unicodedata",
                                   "from pathlib import Path"}}
# ephemeris.py's pin moved when the exit's removal came to find the folder by
# its descriptor where another program moved it (_ephemeris_folder_where,
# ruling 183), and EphemerisRefused's docstring came to name app.py's catch at
# the import; and again when the removal's identity and rmdir came to be made
# through a descriptor on the path's parent (_ephemeris_folder_rmdir, ruling
# 188). time_zones.py's moved when its three outline tables left the
# code for a data file of their own (data/mean_time_outlines.json, read by
# _read_outline_tables, whose own imports json and os are): the names are
# bound from the file now, to the same values. It moved again when the
# pre-1970 windows came in beside LINKED_ZONES (PRE1970_WINDOWS, read by
# _pre1970_state from named_zone_state's linked branch, with timedelta), and
# civil_mean_time_label came to take a window's first moment written out.
# It moved once more when a clipped standard-time window's label came to open
# with its clock, St Thomas's start to follow an order, the AEF note to give
# La Nature's own dates, and four read statuses their reproductions' words.
# And when that label took one form for every such window, "The clock here
# was then {abbreviation}; ...". And when Amsterdam's 1909-1916 window came
# to carry its laws' words, "Amsterdam mean solar time", in place of IANA's
# AMT, in its label, its note and the comment over the labels. And when the
# atlas lookup came in from app.py (ruling 175 (7): _atlas_fold, _like_prefix
# and atlas_rows, the query of _atlas_matches, whose own imports contextlib,
# sqlite3 and unicodedata are), moved as text, app.py keeping the labels and
# the sentences. And when ATLAS1's rebuild brought the place's zone in
# (place_zone, read with the list data/place_zones.tsv and the area rules,
# with PlaceClockRefusal, its kinds 'clock_choice' and 'unsettled'), and the lookup
# came to open the atlas read-only through a file: URI (pathlib's Path). And
# when its fix round gave the five places no clock record settles area rules
# of their own ('golan', 'abu_musa', 'paracels'; ruling 198 (1)). And when its
# fix round 2 gave two more of the kind theirs ('dhekelia', 'kashmir'; ruling
# 202).
MOVED_CODE = {"ephemeris.py": "fe8d47b2cc8241222773ecf7cbae9a965ea7bdbefb0f052a8cff3281fcc97a06",
              "time_zones.py": "5d227bb9afb109d3512f10c1dc61fa07d8e92397a925a50cb68cdd35b55eea48"}


def _tree(name):
    return ast.parse((EXECUTABLE_DIR / name).read_text(encoding="utf-8"))


def _bound(tree):
    """Every name a module's top level binds, in order (a `del` unbinds)."""
    names = []
    for node in tree.body:
        found = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found = [node.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found = [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.If, ast.Try, ast.With, ast.For)):
            for sub in ast.walk(node):
                targets = sub.targets if isinstance(sub, ast.Assign) else (
                    [sub.target] if isinstance(sub, ast.AnnAssign) else [])
                for target in targets:
                    found += sorted(split_census._targets(target))
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                for n in split_census._targets(target):
                    if n in names:
                        names.remove(n)
        names += [n for n in found if n not in names]
    return [n for n in names if not n.startswith("__")]


def _reads(name):
    """Every global name a module's code reads (symtable: the module's own
    references and its functions' global ones)."""
    table = symtable.symtable((EXECUTABLE_DIR / name).read_text(encoding="utf-8"), name, "exec")
    out, stack = set(), [table]
    while stack:
        t = stack.pop()
        for sym in t.get_symbols():
            if sym.is_referenced() and (t.get_type() == symtable.SymbolTableType.MODULE or sym.is_global()):
                out.add(sym.get_name())
        stack.extend(t.get_children())
    return out - set(dir(builtins))


def _affected():
    """The names whose replacement through the engine a new module would not see."""
    out = set()
    for name in NEW:
        out |= set(_bound(_tree(name))) | _reads(name)
    return out


def _paths():
    return [p for p in sorted(TESTS.rglob("*.py")) if p.name not in ("split_census.py", Path(__file__).name)]


def _census():
    return split_census.census(_paths())


def _dynamic_key(paths, f, line, _texts={}):
    """A "<dynamic>" site's DYNAMIC key: its file, the innermost function
    holding it (or "<module>") and its line as written."""
    path = next(p for p in paths if p.name == f)
    if path not in _texts:
        text = path.read_text(encoding="utf-8")
        _texts[path] = (text.splitlines(), ast.parse(text))
    lines, tree = _texts[path]
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= node.end_lineno:
            if best is None or node.lineno > best.lineno:
                best = node
    return f, best.name if best else "<module>", lines[line - 1].strip()


def _marked(sites, paths, affected):
    """The census's sites the guard marks: a name a new module binds or reads,
    unless ENGINE_OWN keeps it; a "<dynamic>" one, unless DYNAMIC lists it
    with names none of which is such a name."""
    out = []
    for row in sites:
        f, line, _where, _form, name = row
        if name == "<dynamic>":
            listed = DYNAMIC.get(_dynamic_key(paths, f, line))
            if listed is None or set(listed[0]) & affected:
                out.append(row)
        elif name in affected and (f, name) not in ENGINE_OWN:
            out.append(row)
    return out


@pytest.fixture(scope="module")
def census():
    return _census()


# --- the census -------------------------------------------------------------------------------

def test_the_census_finds_the_sites_it_counts(census):
    """The census reaches what it must: replacement sites in test code and in
    scripts, read as Python, as a format template and by grep alike (each
    kind seen at least once), across the suite."""
    where = {w.split(" ")[0] for _f, _l, w, _form, _n in census["sites"]}
    assert where == {"code", "script"}, where
    assert len(census["sites"]) > 150 and len({f for f, *_ in census["sites"]}) > 40, len(census["sites"])
    methods = {how for per_file in census["methods"].values() for how in per_file}
    assert {"parsed", "formatted", "grepped"} <= methods, methods


def test_no_site_replaces_through_the_engine_a_name_a_new_module_binds_or_reads(census):
    """A test that replaces engine.X, where X is bound in or read by
    ephemeris.py or time_zones.py, no longer reaches the code that reads it
    there: it must replace the module's X (or be in ENGINE_OWN, with why)."""
    marked = _marked(census["sites"], _paths(), _affected())
    assert marked == [], marked


def test_every_site_kept_on_the_engine_is_still_there(census):
    """No stale entry: each ENGINE_OWN site is found, and its name is one a
    new module reads (else it needs no entry); each DYNAMIC site is still
    found as listed."""
    found = {(f, name) for f, _line, _where, _form, name in census["sites"]}
    affected = _affected()
    stale = [key for key in ENGINE_OWN if key not in found or key[1] not in affected]
    assert stale == [], stale
    paths = _paths()
    dynamic = {_dynamic_key(paths, f, line) for f, line, _where, _form, name in census["sites"] if name == "<dynamic>"}
    assert sorted(set(DYNAMIC) - dynamic) == [], sorted(set(DYNAMIC) - dynamic)


def test_nothing_reads_or_writes_a_withheld_name_through_the_engine(census):
    """In the tests and their scripts (the census), and in the program's own
    modules: no _EPHEMERIS_FOLDER or _DELTA_T_REFERENCE through the engine."""
    assert census["rebound"] == [], census["rebound"]
    program = [p for p in sorted(EXECUTABLE_DIR.glob("*.py"))]
    hits = [(p.name, row) for p in program for row in split_census.rebound(ast.parse(p.read_text(encoding="utf-8")))]
    assert hits == [], hits


@pytest.mark.parametrize("planted, expected", [
    ("import engine\nengine._EPHEMERIS_FOLDER = '/x'\n", [(2, "store", "_EPHEMERIS_FOLDER")]),
    ("def f(engine):\n    return engine['_DELTA_T_REFERENCE']\n", [(2, "item load", "_DELTA_T_REFERENCE")]),
    ("import importlib\nm = importlib.import_module('engine')\nprint(getattr(m, '_EPHEMERIS_FOLDER', None))\n",
     [(3, "getattr", "_EPHEMERIS_FOLDER")]),
    ("import ephemeris\nprint(ephemeris._EPHEMERIS_FOLDER)\n", []),
    ("engine = object()\nprint(engine._EPHEMERIS_FOLDER)\n", []),
])
def test_the_rebound_check_reads_each_shape(planted, expected):
    assert split_census.rebound(ast.parse(planted)) == expected


@pytest.mark.parametrize("script, expected", [
    ('code = r"""\nimport engine\nengine._EPHEMERIS_FOLDER = long\n"""\n', "parsed"),
    ('CHILD = """\nimport engine\nsys.path.insert(0, {repo!r})\nengine._EPHEMERIS_FOLDER\n""".format(repo=1)\n',
     "formatted"),
    ('BODY = r"""\n    if mode:\n        return\n    x = engine._EPHEMERIS_FOLDER\n"""\n', "parsed"),
    ('FRAG = "import engine\\nprint([engine._EPHEMERIS_FOLDER,"\n', "grepped"),
])
def test_a_script_handed_to_a_subprocess_is_read_and_its_reads_found(tmp_path, script, expected):
    """Each way of reading a script finds the read it holds."""
    path = tmp_path / "test_planted.py"
    path.write_text(script, encoding="utf-8")
    result = split_census.census([path])
    assert result["methods"] == {"test_planted.py": {expected: 1}}, result["methods"]
    assert [(row[2], row[4]) for row in result["rebound"]] == [(f"script ({expected})", "_EPHEMERIS_FOLDER")], result


def test_a_replacement_of_a_name_the_zones_read_is_marked():
    """The census's first finding at the move: test_linked_zones replaced the
    engine's ZoneInfo, which named_zone_state no longer reads."""
    planted = ("def test_x(engine, monkeypatch):\n"
               "    monkeypatch.setitem(engine, 'ZoneInfo', None)\n"
               "    import time_zones\n"
               "    monkeypatch.setattr(time_zones, 'ZoneInfo', None)\n")
    found = split_census.sites(ast.parse(planted))
    assert found == [(2, "monkeypatch.setitem", "ZoneInfo")], found
    assert "ZoneInfo" in _affected() and "tempfile" in _affected() and "named_zone_state" in _affected()


@pytest.mark.parametrize("planted, expected", [
    ("def test_x(engine, monkeypatch):\n"
     "    for name in ('CivilDate',):\n"
     "        monkeypatch.setattr(engine, name, None)\n", [(3, "monkeypatch.setattr", "<dynamic>")]),
    ("from unittest import mock\n"
     "import engine\n"
     "def test_x():\n"
     "    with mock.patch.dict(engine.__dict__, {'datetime': None}):\n"
     "        pass\n", [(4, "mock.patch.dict", "datetime")]),
    ("from unittest import mock\n"
     "import engine\n"
     "@mock.patch.dict(vars(engine), clear=True)\n"
     "def test_x():\n"
     "    pass\n", [(3, "mock.patch.dict", "<dynamic>")]),
    ("import engine\nvars(engine).update(swe=None)\n", [(2, "update", "swe")]),
    ("import engine\ndef f(saved):\n    engine.__dict__.update(saved)\n", [(3, "update", "<dynamic>")]),
    ("import engine\n"
     "def f(run):\n"
     "    run.__dict__.update({'x': 1})\n"
     "    engine['_RUN'].__dict__.update({'y': 2})\n", []),
])
def test_a_patched_dict_an_updated_namespace_and_a_name_not_written_are_sites_the_guard_marks(tmp_path, planted, expected):
    """mock.patch.dict and .update of the engine's namespace replace every
    name they write; a site whose name is a variable, or a mapping not
    written out, may replace any name, and is marked unless DYNAMIC lists
    it. (An update of something the engine holds is not a site.)"""
    assert split_census.sites(ast.parse(planted)) == expected
    path = tmp_path / "test_planted.py"
    path.write_text(planted, encoding="utf-8")
    marked = _marked(split_census.census([path])["sites"], [path], _affected())
    assert [(row[1], row[4]) for row in marked] == [(line, name) for line, _form, name in expected], marked


def test_the_handle_looks_the_library_s_function_up_at_each_call(monkeypatch):
    """`swe` runs whatever the library module holds at the moment of the call:
    a patch of the library made after a first call through the handle is
    what the next call runs (a handle that kept the function it first found
    would leave every later patch of swisseph dead), and its undo is too."""
    import ephemeris
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == 2451545.0   # the first call through the handle
    monkeypatch.setattr(ephemeris._swisseph, "julday", lambda *a, **k: ("patched", a))
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == ("patched", (2000, 1, 1, 12.0))
    monkeypatch.undo()
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == 2451545.0


def test_the_engine_a_fixture_hands_back_is_the_engine_where_the_test_takes_it():
    """A fixture returning the engine, or a tuple holding it (test_b15's
    `chart`), is the engine in the test that names it."""
    planted = ("import pytest\n"
               "def _made():\n"
               "    import engine as module\n"
               "    return module, 1\n"
               "@pytest.fixture\n"
               "def chart():\n"
               "    return _made()\n"
               "@pytest.fixture\n"
               "def eng_module():\n"
               "    import importlib\n"
               "    return importlib.import_module('engine')\n"
               "def test_x(chart, eng_module, monkeypatch):\n"
               "    module, data = chart\n"
               "    monkeypatch.setattr(module, 'ZoneInfo', None)\n"
               "    monkeypatch.setattr(data, 'x', None)\n"
               "    monkeypatch.setattr(eng_module, 'swe', None)\n")
    assert split_census.sites(ast.parse(planted)) == [(14, "monkeypatch.setattr", "ZoneInfo"),
                                                     (16, "monkeypatch.setattr", "swe")]


def test_a_name_a_function_binds_to_something_else_is_not_the_engine_there():
    planted = ("import sys\n"
               "def a():\n"
               "    module = sys.modules['engine']\n"
               "    module.x = 1\n"
               "def b(spec):\n"
               "    module = make(spec)\n"
               "    module.y = 2\n"
               "    return module\n"
               "def c(monkeypatch):\n"
               "    launcher = b(None)\n"
               "    monkeypatch.setattr(launcher, 'z', 3)\n")
    assert split_census.sites(ast.parse(planted)) == [(4, "assignment", "x")]


# --- static -----------------------------------------------------------------------------------

def _imported(tree):
    """Every module name a tree imports, anywhere in its code."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and split_census._dotted(node.func).split(".")[-1] in ("import_module", "__import__"):
            out.add(str(node.args[0].value).split(".")[0])
    return out


def test_the_new_modules_are_leaves():
    """Neither imports the engine (nor app.py); time_zones.py imports nothing
    of ephemeris.py, and ephemeris.py nothing of time_zones.py."""
    assert not _imported(_tree("ephemeris.py")) & {"engine", "app", "time_zones"}, _imported(_tree("ephemeris.py"))
    assert not _imported(_tree("time_zones.py")) & {"engine", "app", "ephemeris"}, _imported(_tree("time_zones.py"))


def test_ephemeris_py_alone_loads_the_library_and_the_engine_imports_it_first():
    program = {p.name: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(EXECUTABLE_DIR.glob("*.py"))}
    loaders = sorted(name for name, tree in program.items() if "swisseph" in _imported(tree))
    assert loaders == ["ephemeris.py"], loaders
    engine = program["engine.py"]
    body = engine.body[1:] if ast.get_docstring(engine) else engine.body
    assert [ast.unparse(n) for n in body[:2]] == ["from ephemeris import *", "from time_zones import *"], \
        [ast.unparse(n) for n in body[:3]]
    assert "ephemeris.py" in [p.name for p in source_files()] and "time_zones.py" in [p.name for p in source_files()]


def test_the_engine_and_the_app_read_no_withheld_name_by_its_bare_name():
    for name in ("engine.py", "app.py"):
        bare = [(node.lineno, node.id) for node in ast.walk(_tree(name))
                if isinstance(node, ast.Name) and node.id in WITHHELD]
        bare += [(node.lineno, n) for node in ast.walk(_tree(name)) if isinstance(node, (ast.Global, ast.Nonlocal))
                 for n in node.names if n in WITHHELD]
        assert bare == [], (name, bare)


@pytest.mark.parametrize("name", NEW)
def test_each_modules_all_is_every_name_it_binds_but_the_withheld(name):
    tree = _tree(name)
    alls = [n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["__all__"]]
    assert len(alls) == 1, alls
    listed = ast.literal_eval(alls[0].value)
    assert isinstance(listed, list) and len(listed) == len(set(listed)), listed
    expected = [n for n in _bound(tree) if n not in WITHHELD]
    assert sorted(listed) == sorted(expected), (sorted(set(expected) - set(listed)), sorted(set(listed) - set(expected)))
    assert not set(listed) & set(WITHHELD)


@pytest.mark.parametrize("name", NEW)
def test_the_moved_code_is_the_code_engine_py_held(name):
    """The moved code, by ast.dump (so comments aside): what the move's
    commit took from engine.py byte for byte, less only the module's
    docstring, its own imports and its __all__."""
    tree = _tree(name)
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    own = [ast.unparse(n) for n in body if ast.unparse(n) in ADDED_IMPORTS[name]]
    assert sorted(own) == sorted(ADDED_IMPORTS[name]), own
    moved = [n for n in body if ast.unparse(n) not in ADDED_IMPORTS[name]
             and not (isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["__all__"])]
    digest = hashlib.sha256("\n".join(ast.dump(n) for n in moved).encode("utf-8")).hexdigest()
    assert digest == MOVED_CODE[name], (name, digest)


def test_no_test_opens_engine_py_by_name_for_a_name_that_moved():
    """A scan of engine.py's text or tree by its name (ENGINE_PATH, a path
    ending "engine.py") for a name that now lives in a new module would read
    nothing, and pass or fail for that alone: such scans read the modules
    source_modules.txt names (conftest's source_files and engine_files)."""
    moved = set()
    for name in NEW:
        tree = _tree(name)
        moved |= {n for n in _bound(tree) if n not in _imported(tree) and n not in {"st", "datetime", "timezone",
                                                                                  "ZoneInfo", "ZoneInfoNotFoundError"}}
    import re
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, moved), key=len, reverse=True)) + r")\b")

    def opens_engine_by_name(fn):
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and n.id == "ENGINE_PATH":
                return True
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and isinstance(n.right, ast.Constant) \
                    and n.right.value == "engine.py":
                return True
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "open" \
                    and any(isinstance(a, ast.Constant) and str(a.value).endswith("engine.py") for a in n.args):
                return True
        return False

    def scans():
        for path in sorted(TESTS.glob("test_*.py")):
            for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and opens_engine_by_name(fn):
                    hits = sorted({m.group(1) for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                   and isinstance(n.value, str) for m in rx.finditer(n.value)})
                    if hits:
                        yield path.name, fn.name, hits

    scanning_for_moved_names = list(scans())
    assert not scanning_for_moved_names, scanning_for_moved_names


# --- dynamic ----------------------------------------------------------------------------------

def _run(code, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = str(EXECUTABLE_DIR)
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("OUT ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    return json.loads(lines[-1][len("OUT "):])


_LEAVES = r"""
import json, sys
which = sys.argv[1] if len(sys.argv) > 1 else None
out = {}
import time_zones
out["time_zones_alone"] = sorted(m for m in ("engine", "ephemeris", "swisseph", "app") if m in sys.modules)
import ephemeris
out["ephemeris_then"] = sorted(m for m in ("engine", "app") if m in sys.modules)
print("OUT " + json.dumps(out))
"""


def test_each_new_module_imports_alone_and_loads_nothing_of_the_engine(tmp_path):
    out = _run(_LEAVES, tmp_path)
    assert out == {"time_zones_alone": [], "ephemeris_then": []}, out


_REEXPORT = r"""
import atexit, importlib, json, sys
registered = []
_register = atexit.register
def watched(fn, *a, **k):
    if getattr(fn, "__name__", "") == "_ephemeris_folder_remove":
        registered.append(a[0])
    return _register(fn, *a, **k)
atexit.register = watched
import ephemeris
import time_zones
import engine
out = {}
missing = []
for module in (ephemeris, time_zones):
    for name in module.__all__:
        if getattr(engine, name, missing) is not getattr(module, name):
            missing.append(module.__name__ + "." + name)
out["not_re_exported"] = missing
out["withheld_in_engine"] = sorted(n for n in ("_EPHEMERIS_FOLDER", "_DELTA_T_REFERENCE") if n in vars(engine))
out["swe_one"] = engine.swe is ephemeris.swe and isinstance(engine.swe, ephemeris._SwissEphemeris)
namespace = {}
exec("from engine import *", namespace)
out["star"] = sorted(n for n in namespace if n != "__builtins__")
folder = ephemeris._EPHEMERIS_FOLDER
classes = ("EphemerisRefused", "EphemerisFolderRefused", "NamedZoneRefusal", "CivilDate", "CivilMoment",
           "_SwissEphemeris")
before = {name: getattr(engine, name) for name in classes}
engine = importlib.reload(engine)
out["engine_reload"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder,
                        "classes": [getattr(engine, name) is before[name] for name in classes],
                        "swe": engine.swe is ephemeris.swe}
held = ephemeris._EPHEMERIS_HELD
ephemeris = importlib.reload(ephemeris)
out["ephemeris_reload"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder, "held": ephemeris._EPHEMERIS_HELD is held}
del sys.modules["ephemeris"]
import ephemeris
out["ephemeris_fresh"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder, "held": ephemeris._EPHEMERIS_HELD is held}
out["registered"] = [r == folder for r in registered]
print("OUT " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def reexport(tmp_path_factory):
    return _run(_REEXPORT, tmp_path_factory.mktemp("reexport"))


def test_every_name_the_new_modules_export_is_the_engines_and_swe_is_one_object(reexport):
    assert reexport["not_re_exported"] == [] and reexport["swe_one"] is True, reexport
    assert reexport["withheld_in_engine"] == [], reexport["withheld_in_engine"]


def test_the_star_import_gives_the_engines_own_names_and_the_new_modules_less_the_withheld(reexport):
    """`from engine import *` (app.py's): the names engine.py binds, every
    name the new modules bind but the two withheld (the standard modules
    only they import, atexit, struct and tempfile, among them), and the
    module name `ephemeris` the star reader reads the folder through."""
    star = set(reexport["star"])
    engine_own = set(_bound(_tree("engine.py")))
    new = {n for name in NEW for n in _bound(_tree(name))}
    assert star == (engine_own | new) - set(WITHHELD), (sorted((engine_own | new) - set(WITHHELD) - star),
                                                         sorted(star - engine_own - new))
    assert {"atexit", "struct", "tempfile", "ephemeris", "swe", "named_zone_state", "CivilDate"} <= star
    assert not star & set(WITHHELD) and "time_zones" not in star


def test_a_reload_of_the_engine_keeps_the_folder_and_the_classes(reexport):
    assert reexport["engine_reload"] == {"folder": True, "classes": [True] * 6, "swe": True}, reexport["engine_reload"]


def test_a_reload_and_a_fresh_import_of_ephemeris_find_the_held_folder_and_register_no_second_hook(reexport):
    assert reexport["ephemeris_reload"] == reexport["ephemeris_fresh"] == {"folder": True, "held": True}, reexport
    assert reexport["registered"] == [True], reexport["registered"]


_CACHES = r"""
import importlib, json, sys, warnings
warnings.simplefilter("ignore")
import swisseph                                   # the library loaded before the folder: the flag is set
import streamlit as st
calls = []
@st.cache_data
def cached(x):
    calls.append(x)
    return x
out = []
cached(1); cached(1); out.append(len(calls))      # 1: cached
import ephemeris                                  # empties the caches, once
cached(1); out.append(len(calls))                 # 2
import engine                                     # does not
cached(1); out.append(len(calls))                 # 2
importlib.reload(engine)                          # nor does its reload
cached(1); out.append(len(calls))                 # 2
print("OUT " + json.dumps([out, ephemeris._EPHEMERIS_LOADED_FIRST]))
"""


def test_the_caches_are_emptied_once_when_ephemeris_loads_and_not_again_by_the_engine(tmp_path):
    """The cache clear moved with the flag it reads: importing ephemeris.py
    after swisseph empties Streamlit's caches once; importing the engine and
    reloading it do not empty them again."""
    counts, flag = _run(_CACHES, tmp_path)
    assert flag is True and counts == [1, 2, 2, 2], counts
