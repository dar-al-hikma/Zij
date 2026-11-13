"""Run-time checks beside the static scans: the tripwire on the engine's
namespace, and the import audit of the program.

The scans read code: the census (tests/split_census.py) every site that
replaces an attribute of the engine, the inventory (tests/shipped_modules.py)
every import of the program. A spelling the reading does not follow escapes
them. These check what happens instead:

* **The tripwire** (tests/conftest.py, judged by tests/engine_tripwire.py):
  every change to the engine's watched namespace while the suite runs, by any
  route, with its site (an engine imported afresh within a test is watched
  from the next test's start, and a change made from a frame of a program file
  is taken as the program's); the split guard's rule applied to it; and every
  replacement seen asked of the census. Each throwaway suite here is a copy of the
  harness with a stand-in program of four small modules, so the run is wired
  as the suite is, and a planted test shows what is seen.
* **The import audit** (tests/import_audit.py, run in a fresh interpreter):
  an audit hook installed before the program's first import, the launcher
  imported and every page rendered through AppTest; every module of the
  repository loaded must be one the frozen app carries, and no exec, eval or
  compile may be called from one of its files. It sees only the paths that
  run; the inventory still answers for the rest.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import conftest
import engine_tripwire
import shipped_modules

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
HARNESS = ("conftest.py", "corpus_paths.py", "skip_guard.py", "source_list.py", "engine_tripwire.py",
           "split_census.py", "name_bindings.py", "test_split_astro_2026_10_14.py")
SUMMARY = re.compile(r"^ENGINE TRIPWIRE: (\d+) replacement\(s\) of the engine seen at (\d+) site\(s\) in (\d+) "
                     r"test\(s\) of (\d+) test report\(s\); (\d+) problem\(s\)$", re.M)
QUIET = re.compile(r"^ENGINE TRIPWIRE: nothing replaced in the engine in (\d+) test report\(s\)$", re.M)
CHECKED = re.compile(r"^SKIP GUARD: \d+ skip\(s\) checked$", re.M)

# The stand-in program: the engine takes six split-out modules whole, as the real one does, three first and
# three last. `swe`, `named_zone_state` and `load_saved_charts` are names a split-out module binds;
# `_EPHEMERIS_FOLDER` and `DATA_DIR_ERROR` are withheld (not exported); OWN is the engine's own. wheel.py and
# export_html.py hold markup.py's `_esc_text` by their import.
PROGRAM = {
    "ephemeris.py": "swe = object()\n_EPHEMERIS_FOLDER = '/nowhere'\n__all__ = ['swe']\n",
    "time_zones.py": "def named_zone_state():\n    return None\n\n__all__ = ['named_zone_state']\n",
    "user_data.py": "DATA_DIR_ERROR = None\n\ndef load_saved_charts():\n    return []\n\n"
                    "__all__ = ['load_saved_charts']\n",
    "markup.py": "def _esc_text(s):\n    return s\n\n__all__ = ['_esc_text']\n",
    "wheel.py": "from markup import _esc_text\n\ndef generate_hybrid_svg():\n    return _esc_text('')\n\n"
                "__all__ = ['_esc_text', 'generate_hybrid_svg']\n",
    "export_html.py": "from markup import _esc_text\n\ndef analysis_html():\n    return _esc_text('')\n\n"
                      "__all__ = ['_esc_text', 'analysis_html']\n",
    "engine.py": "from ephemeris import *\nfrom time_zones import *\nfrom user_data import *\n\n"
                 "class UnresolvedResult:\n    pass\n\nOWN = 1\nOTHER = 2\n\ndef bump():\n    global OWN\n"
                 "    OWN += 1\n\nfrom markup import *\nfrom wheel import *\nfrom export_html import *\n",
}


def clone(tmp_path, files, harness_from=TESTS):
    """A copy of the harness under `tmp_path`, with the stand-in program and `files` planted."""
    root = tmp_path / "clone"
    (root / "tests").mkdir(parents=True)
    for name in HARNESS:
        shutil.copy(harness_from / name, root / "tests" / name)
    shutil.copy(ROOT / "pytest.ini", root / "pytest.ini")
    for rel, source in {**PROGRAM, **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(source, encoding="utf-8")
    return root


def run(root, *args, timeout=300):
    scratch = root.parent / "scratch"
    for name in ("home", "xdg", "appdata", "tmp"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_ADDOPTS", "PYTHONPATH", "PYTEST_CURRENT_TEST", conftest.HARNESS_MARK)
           and not k.startswith("PYTEST_XDIST_")}
    env.update(HOME=str(scratch / "home"), XDG_DATA_HOME=str(scratch / "xdg"), APPDATA=str(scratch / "appdata"),
               TMPDIR=str(scratch / "tmp"), CORPUS_DIR=str(root.parent / "no-corpus"))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                       capture_output=True, text=True, cwd=root, env=env, timeout=timeout)
    return r, r.stdout + r.stderr


def summary(output):
    m = SUMMARY.search(output)
    assert m, output
    return tuple(int(g) for g in m.groups())


def problems(output):
    """The lines under the tripwire's "<n> problem(s):" heading."""
    lines, out = output.splitlines(), []
    for n, ln in enumerate(lines):
        if re.match(r"^ENGINE TRIPWIRE: \d+ problem\(s\):$", ln):
            for item in lines[n + 1:]:
                if not item.startswith("  "):
                    break
                out.append(item.strip())
    return out


IMPORTS = "import sys\nimport json\nfrom unittest import mock\n\nimport pytest\n\nimport engine\n\n\n"

# ------------------------------------------------------------------ the tripwire: honest spellings

HONEST = IMPORTS + '''\
def test_setattr(monkeypatch):
    monkeypatch.setattr(engine, "OWN", 5)


def test_item_of_the_namespace(monkeypatch):
    monkeypatch.setitem(vars(engine), "OTHER", 6)


def test_assignment_restored():
    old = engine.OWN
    engine.OWN = 7
    engine.OWN = old


def test_patch_object():
    with mock.patch.object(engine, "OTHER", 8):
        pass


@mock.patch.object(engine, "OWN", 9)
def test_decorated():
    pass


def test_patch_dict():
    with mock.patch.dict(engine.__dict__, {"OTHER": 10}):
        pass


def test_patch_multiple():
    with mock.patch.multiple(engine, OWN=11, OTHER=12):
        pass


def test_two_replacements_of_one_name(monkeypatch):
    monkeypatch.setattr(engine, "OWN", 20)
    monkeypatch.setattr(engine, "OWN", 21)


def test_the_engines_own_rebinding_is_not_a_replacement():
    engine.bump()


def test_a_name_in_a_split_out_module_replaced_there(monkeypatch):
    import ephemeris
    monkeypatch.setattr(ephemeris, "swe", None)
'''


def test_the_honest_spellings_are_seen_found_in_the_census_and_pass(tmp_path):
    """Every form that replaces the engine's own names, each seen (ten
    replacements, patch.multiple's two names at one line; the restore of the
    assignment and every undo not counted, nor the undo of two setattr calls
    on one name, which passes through the first's value), each found in the
    census, nothing failed; the engine's own rebinding and a replacement in a
    split-out module are not replacements of the engine."""
    root = clone(tmp_path, {"tests/test_plant.py": HONEST})
    r, out = run(root, "tests/test_plant.py")
    assert r.returncode == 0, out
    seen, sites, tests, _reports, bad = summary(out)
    assert (seen, sites, tests, bad) == (10, 10, 8, 0), out


@pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["one process", "two workers"])
def test_the_same_under_xdist_workers_record_and_the_controller_judges(tmp_path, workers):
    root = clone(tmp_path, {"tests/test_plant.py": HONEST})
    r, out = run(root, "tests/test_plant.py", *workers)
    assert r.returncode == 0, out
    assert summary(out)[:3] == (10, 10, 8) and summary(out)[4] == 0, out
    assert len(SUMMARY.findall(out)) == 1 and len(CHECKED.findall(out)) == 1, out


# ------------------------------------------------------------------ the tripwire: the plants

# Each plant marks its site's line "# site" (a decorator's: "# site, outside the test's frames", whose problem
# names no line) and gives the problems it must raise beside the census's own, and the name it replaces in the
# engine; the census's problem is expected exactly where the static census has no row for that name at that line.
SPLIT = "replaces engine.{name}, a name {module} binds or reads"
LOST = "replaces engine.{name}, a site the static census does not find in that file"
CLEAR = "clears the engine's namespace"
CLEAR_LOST = "clears the engine's namespace, a site the static census does not find in that file"
EPH, TZ, UD = "ephemeris.py", "time_zones.py", "user_data.py"
PLANTS = {
    # A plain rebinding, in a test function, of a name the census's resolver settles as the engine.
    "a plain rebinding": ("def test_x():\n    E = json\n    E, n = sys.modules['engine'], 1\n    E.swe = None  # site\n",
                          [SPLIT.format(name="swe", module=EPH)], "swe"),
    "an item of vars()": ("def test_x():\n    vars(engine)['swe'] = None  # site\n",
                          [SPLIT.format(name="swe", module=EPH)], "swe"),
    "patch.dict, undone inside the test": (
        "def test_x():\n    with mock.patch.dict(engine.__dict__, {'named_zone_state': None}):  # site\n        pass\n",
        [SPLIT.format(name="named_zone_state", module=TZ)], "named_zone_state"),
    "a decorator under another name": (
        "from unittest.mock import patch as p\n\n\n@p.object(engine, 'load_saved_charts', None)"
        "  # site, outside the test's frames\ndef test_x():\n    pass\n",
        [SPLIT.format(name="load_saved_charts", module=UD)], "load_saved_charts"),
    "nested, inside pytest.raises": (
        "def test_x():\n    def inner():\n        setattr(engine, 'swe', None)  # site\n        raise ValueError\n"
        "    with pytest.raises(ValueError):\n        inner()\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a write of a withheld name": (
        "def test_x(monkeypatch):\n    monkeypatch.setattr(engine, '_EPHEMERIS_FOLDER', '/x', raising=False)  # site\n",
        # monkeypatch reads the old value first (getattr with a default): a read of the withheld name too
        ["writes the withheld name engine._EPHEMERIS_FOLDER", "reads the withheld name engine._EPHEMERIS_FOLDER",
         SPLIT.format(name="_EPHEMERIS_FOLDER", module=EPH)], "_EPHEMERIS_FOLDER"),
    "a read of a withheld name": ("def test_x():\n    assert getattr(engine, 'DATA_DIR_ERROR', None) is None  # site\n",
                                  ["reads the withheld name engine.DATA_DIR_ERROR"], None),
    "a read through the engine of a name replaced in its module": (
        "def test_x(monkeypatch):\n    import ephemeris\n    monkeypatch.setattr(ephemeris, 'swe', None)\n"
        "    assert engine.swe is not None  # site\n",
        ["reads engine.swe after replacing swe in a split-out module"], None),
    "a name never written out": (
        "def test_x(monkeypatch):\n    name = ''.join(['s', 'w', 'e'])\n    t = sys.modules['engine']\n"
        "    monkeypatch.setattr(t, name, None)  # site\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a star import": ("from sys import *\n\n\ndef test_x():\n    modules['engine'].swe = None  # site\n",
                      [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a match pattern's capture": (
        "def test_x():\n    match sys:\n        case object(modules=S):\n            S['engine'].swe = None  # site\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a match pattern holding the patcher": (
        "def test_x():\n    match mock.patch:\n        case p:\n            with p('engine.swe', None):  # site\n"
        "                pass\n", [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a fetch method": ("import operator\n\n\ndef test_x():\n    name = 'en' + 'gine'\n"
                       "    operator.getitem(sys.modules, name).swe = None  # site\n",
                       [SPLIT.format(name="swe", module=EPH)], "swe"),
    "starred unpacking": ("def test_x():\n    p, *_ = mock.patch, 1\n    with p('engine.swe', None):  # site\n        pass\n",
                          [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a class attribute holding the patcher": (
        "class K:\n    p = mock.patch\n\n\ndef test_x():\n    with K.p('engine.swe', None):  # site\n        pass\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a dict holding the patcher": ("def test_x():\n    with {'k': mock.patch}['k']('engine.swe', None):  # site\n"
                                   "        pass\n", [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a keyword's value": ("import contextlib\n\n\ndef test_x():\n"
                          "    with contextlib.nullcontext(enter_result=mock.patch) as p:\n"
                          "        with p('engine.swe', None):  # site\n            pass\n",
                          [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a wrapped patching function": ("import functools\n\n\ndef test_x(monkeypatch):\n"
                                    "    functools.partial(monkeypatch.setattr, engine)('swe', None)  # site\n",
                                    [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a name in globals() never written out": ("def test_x():\n    n = 'eng' + 'ine'\n    globals()[n].swe = None  # site\n",
                                              [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a parameter without a default": ("def _h(t):\n    t.swe = None  # site\n\n\ndef test_x():\n    _h(engine)\n",
                                      [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a loader through importlib's namespace handed to a call": (
        "import importlib\n\n\ndef test_x():\n"
        "    dict.get(vars(importlib), 'import_' + 'module')('engine').swe = None  # site\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a match on a lookup not written out": (
        "def test_x():\n    match getattr(sys, 'mod' + 'ules'):\n        case R:\n"
        "            R['engine'].swe = None  # site\n", [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a loader from builtins' namespace by operator.itemgetter": (
        "import operator\n\n\ndef test_x():\n"
        "    operator.itemgetter('__imp' + 'ort__')(__builtins__)('engine').swe = None  # site\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a patching function handed in": ("def _h(patch):\n    patch(engine, 'swe', None)  # site\n\n\n"
                                      "def test_x(monkeypatch):\n    _h(monkeypatch.setattr)\n",
                                      [SPLIT.format(name="swe", module=EPH)], "swe"),
    "__getattribute__": ("def test_x():\n    sys.__getattribute__('mod' + 'ules')['engine'].swe = None  # site\n",
                         [SPLIT.format(name="swe", module=EPH)], "swe"),
    "setdefault": ("def test_x():\n    vars(sys).setdefault('mod' + 'ules')['engine'].swe = None  # site\n",
                   [SPLIT.format(name="swe", module=EPH)], "swe"),
    "getattr_static": ("import inspect\n\n\ndef test_x():\n"
                       "    inspect.getattr_static(sys, 'mod' + 'ules')['engine'].swe = None  # site\n",
                       [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a ChainMap lookup": ("import collections\n\n\ndef test_x():\n"
                          "    collections.ChainMap(vars(sys))['mod' + 'ules']['engine'].swe = None  # site\n",
                          [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a writing ChainMap view": (
        "import collections\n\n\ndef test_x():\n    collections.ChainMap(vars(engine))['swe'] = None  # site\n",
        [SPLIT.format(name="swe", module=EPH)], "swe"),
    "a clear held across the test": (
        "@mock.patch.dict(vars(engine), clear=True)  # site, outside the test's frames\ndef test_x():\n    pass\n",
        [CLEAR], "*"),
    "a clear with values, inside the test": (
        "def test_x():\n    with mock.patch.dict(engine.__dict__, {'OWN': 3}, clear=True):  # site\n        pass\n",
        [CLEAR], "*"),
    "at collection, outside any test": ("engine.swe = None  # site\n\n\ndef test_x():\n    pass\n",
                                        [SPLIT.format(name="swe", module=EPH)], "swe"),
}


def _site(body):
    """(the site's line, whether the problem names it)."""
    source = IMPORTS + body
    for n, ln in enumerate(source.splitlines(), 1):
        if ln.endswith("# site"):
            return n, True
        if ln.endswith("# site, outside the test's frames"):
            return n, False
    raise AssertionError("no site marked")


def expected_problems(body, expected, name):
    """The plant's problems, each as its line starts: the census's among them
    where the static census has no row for `name` at the site's line."""
    import ast

    import split_census

    line, named = _site(body)
    rows = split_census.sites(ast.parse(IMPORTS + body))
    row_name = "<dynamic>" if name == "*" else name
    lost = name is not None and not any(r[0] == line and r[2] == row_name for r in rows)
    where = f"test_plant.py:{line}" if named else "test_plant.py"
    lost_line = CLEAR_LOST if name == "*" else LOST.format(name=name)
    return [f"{where}: {why}" for why in expected + ([lost_line] if lost else [])], lost


def test_the_census_reads_some_plants_and_not_others():
    """The plants are worth the run: the census misses the site of every form
    named as one of its known limits, and reads the plain ones."""
    lost = {plant for plant, (body, expected, name) in PLANTS.items() if expected_problems(body, expected, name)[1]}
    assert {"a star import", "a match pattern's capture", "a match pattern holding the patcher", "starred unpacking",
            "a class attribute holding the patcher", "a dict holding the patcher", "a keyword's value",
            "a wrapped patching function", "a writing ChainMap view", "a plain rebinding",
            "a name never written out", "a fetch method", "a name in globals() never written out",
            "a parameter without a default", "a loader through importlib's namespace handed to a call",
            "a match on a lookup not written out", "__getattribute__", "setdefault", "getattr_static",
            "a ChainMap lookup", "a loader from builtins' namespace by operator.itemgetter",
            "a patching function handed in"} <= lost, sorted(lost)
    assert not {"an item of vars()", "patch.dict, undone inside the test", "a decorator under another name",
                "nested, inside pytest.raises", "at collection, outside any test", "a clear held across the test",
                "a clear with values, inside the test"} & lost, sorted(lost)


@pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["one process", "two workers"])
@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_each_plant_fails_the_run_naming_its_site(tmp_path, plant, workers):
    body, expected, name = PLANTS[plant]
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py", *workers)
    assert r.returncode == 1, out
    found = problems(out)
    wanted = expected_problems(body, expected, name)[0]
    missing = [start for start in wanted if not any(p.startswith(start) for p in found)]
    assert wanted and missing == [] and len(found) == len(wanted), (missing, out)
    assert len(CHECKED.findall(out)) == 1, out


def test_one_value_patched_by_two_decorators_is_judged_at_each(tmp_path):
    """A value a test's site gave a name is let through again only from
    monkeypatch's undo: a second decorator patching the same object is a
    replacement of its own."""
    body = ("@mock.patch.object(engine, 'swe', None)\ndef test_a():\n    pass\n\n\n"
            "@mock.patch.object(engine, 'swe', None)\ndef test_b():\n    pass\n")
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py")
    assert r.returncode == 1 and summary(out)[:3] == (2, 1, 2), out
    assert problems(out) == ["test_plant.py: replaces engine.swe, a name ephemeris.py binds or reads: the replacement "
                             "does not reach it there (replace it in ephemeris.py, or keep it in its ENGINE_OWN with "
                             "why) (tests/test_plant.py::test_a, and 1 more)"], out


def test_the_census_check_names_a_site_the_census_lost(tmp_path):
    """A census that stops reading one honest form: the run names each of its sites."""
    root = clone(tmp_path, {"tests/test_plant.py": HONEST})
    census = root / "tests" / "split_census.py"
    text = census.read_text(encoding="utf-8")
    lost = text.replace('out.append((t.lineno, "del" if isinstance(t.ctx, ast.Del) else "assignment", t.attr))',
                        "pass")
    assert lost != text
    census.write_text(lost, encoding="utf-8")
    r, out = run(root, "tests/test_plant.py")
    assert r.returncode == 1, out
    line = next(n for n, ln in enumerate(HONEST.splitlines(), 1) if ln.strip() == "engine.OWN = 7")
    assert problems(out) == [f"test_plant.py:{line}: replaces engine.OWN, a site the static census does not find "
                             "in that file (tests/test_plant.py::test_assignment_restored)"], out


# ------------------------------------------------------------------ the tripwire: the grid

def test_a_run_that_touches_nothing_passes_and_says_so(tmp_path):
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + "def test_x():\n    assert engine.OWN == 1\n"})
    r, out = run(root, "tests/test_plant.py")
    assert r.returncode == 0 and QUIET.search(out).group(1) == "3", out


@pytest.mark.parametrize("k", ["nothing_by_this_name", "test_setatr"], ids=["selects nothing", "mistyped"])
def test_a_filter_that_selects_nothing_keeps_pytests_status(tmp_path, k):
    root = clone(tmp_path, {"tests/test_plant.py": HONEST})
    r, out = run(root, "tests/test_plant.py", "-k", k)
    assert r.returncode == 5 and QUIET.search(out).group(1) == "0", out


def test_a_filter_judges_what_ran(tmp_path):
    root = clone(tmp_path, {"tests/test_plant.py": HONEST + "\n\n" + PLANTS["an item of vars()"][0]})
    r, out = run(root, "tests/test_plant.py", "-k", "setattr")
    assert r.returncode == 0 and summary(out)[:3] == (1, 1, 1), out
    r, out = run(root, "tests/test_plant.py", "-k", "test_x")
    assert r.returncode == 1 and len(problems(out)) == 1, out


def test_a_crash_mid_test_is_judged_with_what_it_did(tmp_path):
    body = "def test_x():\n    engine.swe = None\n    raise RuntimeError('crash')\n"
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py")
    assert r.returncode == 1 and "1 failed" in out, out
    assert any("replaces engine.swe, a name ephemeris.py" in p for p in problems(out)), out


@pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["one process", "two workers"])
def test_a_run_ended_early_is_judged_with_what_ran(tmp_path, workers):
    body = "def test_a():\n    vars(engine)['swe'] = None\n    pytest.exit('ended early', returncode=0)\n"
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py", *workers)
    assert r.returncode == 1, out
    assert any("replaces engine.swe, a name ephemeris.py" in p for p in problems(out)), out


def test_a_worker_that_dies_does_not_skip_the_judgement(tmp_path):
    body = ("def test_a():\n    vars(engine)['swe'] = None\n\n\n"
            "def test_b():\n    import os\n    os._exit(1)\n")
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py", "-n", "2", "-p", "no:randomly")
    assert r.returncode == 1 and "crashed" in out, out
    assert any("replaces engine.swe, a name ephemeris.py" in p for p in problems(out)), out


def test_a_report_without_the_tripwire_fails_the_run(tmp_path):
    """A test's report that does not say the tripwire was armed -- a worker
    in which it was never installed -- fails the run."""
    plug = ("import pytest\n\n\n@pytest.hookimpl(wrapper=True, tryfirst=True)\n"
            "def pytest_runtest_makereport(item, call):\n    report = yield\n"
            "    report.user_properties = [p for p in report.user_properties if p[0] != 'engine_tripwire']\n"
            "    return report\n")
    root = clone(tmp_path, {"tests/test_plant.py": HONEST, "tests/strip_plug.py": plug})
    r, out = run(root, "tests/test_plant.py", "-p", "strip_plug", "-n", "2")
    assert r.returncode == 1 and "ENGINE TRIPWIRE: not armed where" in out, out


def test_a_property_a_test_writes_for_the_tripwire_is_dropped(tmp_path):
    body = ("def test_x(record_property):\n    record_property('engine_tripwire', {'armed': True, 'events': [], "
            "'faults': []})\n    vars(engine)['swe'] = None\n")
    root = clone(tmp_path, {"tests/test_plant.py": IMPORTS + body})
    r, out = run(root, "tests/test_plant.py", "-n", "2")
    assert r.returncode == 1 and len(problems(out)) == 1, out


@pytest.mark.parametrize("drop", [("--noconftest",), ("--confcutdir=tests/fixtures",)])
def test_a_run_without_the_conftest_is_refused_still(tmp_path, drop):
    root = clone(tmp_path, {"tests/test_plant.py": HONEST, "tests/fixtures/.keep": ""})
    r, out = run(root, "tests/test_plant.py", *drop)
    assert r.returncode == 4 and "conftest.py did not load in this run" in out, out
    assert "ENGINE TRIPWIRE" not in out, out


def test_the_judgement_reads_a_dynamic_row_as_exactly_its_listed_names():
    """A "<dynamic>" row stands for the names the split guard's DYNAMIC lists
    for it: the real site in the wheel test stands for its two names, and for
    no other."""
    import test_split_astro_2026_10_14 as split

    (f, function, text), (names, _why) = next(iter(split.DYNAMIC.items()))
    line = next(n for n, ln in enumerate((TESTS / f).read_text().splitlines(), 1) if ln.strip() == text)
    base = {"module": "engine", "kind": "set", "file": f, "line": line, "by": "test",
            "nodeid": f"tests/{f}::test_x", "when": "call"}
    lines, _summary = engine_tripwire.judge([dict(base, name=n) for n in names], TESTS, 1)
    assert lines == [], lines
    lines, _summary = engine_tripwire.judge([dict(base, name="OWN_NOT_LISTED")], TESTS, 1)
    assert len(lines) == 2 and "census does not find" in lines[1], lines


# ------------------------------------------------------------------ the import audit

AUDIT = TESTS / "import_audit.py"


def audit(tmp_path, root, *pages, driver=AUDIT):
    scratch = tmp_path / "audit"
    for name in ("home", "xdg", "appdata", "tmp"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(scratch / "home"),
           "XDG_DATA_HOME": str(scratch / "xdg"), "APPDATA": str(scratch / "appdata"),
           "TMPDIR": str(scratch / "tmp"), "LANG": "C.UTF-8"}
    out = scratch / "audit.json"
    r = subprocess.run([sys.executable, str(driver), str(root), str(out), *pages], capture_output=True, text=True,
                       cwd=scratch, env=env, timeout=600)
    assert r.returncode == 0 and out.is_file(), r.stdout + r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def _under(path, root):
    path = Path(os.path.realpath(path))
    return path.is_relative_to(root) and not path.is_relative_to(root / "tests")


def audit_problems(seen, root):
    """What the audit refuses: a module of the tree loaded that the frozen app
    does not carry; an exec, eval or compile called from a file of the tree;
    a module of the tree loaded before the hook; and the program's start not
    seen whole (the launcher's and the engine's imports among the events)."""
    root = Path(root).resolve()
    shipped = set(shipped_modules.shipped_modules(root))
    stems = {name.removesuffix(".py").rstrip("/") for name in shipped} | {
        p.stem for p in root.glob("*.py")}
    loaded = {Path(f).relative_to(root).as_posix() for f in seen["modules"].values() if _under(f, root)}
    for path in seen["opened"]:
        if _under(path, root):
            p = Path(os.path.realpath(path))
            loaded.add(p.relative_to(root).as_posix() if p.suffix == ".py"
                       else f"{p.name.split('.')[0]}.py" if p.parent.name == "__pycache__" else p.name)
    out = [f"loaded, not carried: {name}" for name in sorted(loaded - shipped)]
    out += [f"{r['event']} called from {Path(r['caller']).relative_to(root).as_posix()}:{r['line']} ({r['code']})"
            for r in seen["runs"] if not r["caller"].startswith("<") and _under(r["caller"], root)]
    out += [f"loaded before the audit hook: {m}" for m in seen["before"] if m in stems]
    out += [f"not seen loaded: {m}" for m in ("desktop_launcher", "server_limits", "engine", "ephemeris",
                                                "time_zones", "user_data", "markup", "wheel", "export_html")
            if m not in seen["imports"]]
    if seen["outcome"]["launcher"] != "imported":
        out.append(f"the launcher did not import: {seen['outcome']['launcher']}")
    return out


@pytest.fixture(scope="module")
def real_audit(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("real-audit")
    return audit(tmp, ROOT, *conftest.PAGES)


def test_the_program_loads_only_what_the_frozen_app_carries_and_runs_no_code_from_a_string(real_audit):
    assert audit_problems(real_audit, ROOT) == [], audit_problems(real_audit, ROOT)


def app_page_paths(root):
    """The url_path of each st.Page in the app's navigation. Streamlit finds
    a page by the hash of its url_path, and renders the default page for a
    hash it does not know."""
    tree = ast.parse((Path(root) / "app.py").read_text(encoding="utf-8"))
    return {k.value.value for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == "Page"
            for k in node.keywords if k.arg == "url_path" and isinstance(k.value, ast.Constant)}


def test_every_page_rendered_in_the_audit(real_audit):
    pages = real_audit["outcome"]["pages"]
    assert list(pages) == conftest.PAGES, list(pages)
    unknown = sorted(set(pages) - app_page_paths(ROOT))
    assert unknown == [], f"not a page of the app, so the audit rendered the default page for it: {unknown}"
    failed = {name: p for name, p in pages.items() if p["exceptions"] or p["elements"] == 0}
    assert failed == {}, failed


def test_the_frameworks_own_runs_are_told_from_the_programs(real_audit):
    """Streamlit compiles and runs app.py itself; that call is the
    framework's (its frame is Streamlit's), not the program's."""
    app = str(ROOT / "app.py")
    runs = [r for r in real_audit["runs"] if r["code"] == app]
    assert {r["event"] for r in runs} == {"compile", "exec"}, runs
    assert [r for r in runs if "streamlit" not in Path(r["caller"]).parts] == [], runs


def _tree_with(tmp_path, changes):
    """The repository's program, each top-level entry linked but those `changes` rewrites."""
    root = tmp_path / "tree"
    root.mkdir()
    for entry in ROOT.iterdir():
        if entry.name in (".git", "tests", "__pycache__") or entry.name in changes:
            continue
        (root / entry.name).symlink_to(entry)
    for name, change in changes.items():
        (root / name).write_text(change((ROOT / name).read_text(encoding="utf-8")) if (ROOT / name).is_file()
                                 else change(""), encoding="utf-8")
    return root


PLANTED = "print.__self__.exec('import planted')\n"
# Forms the inventory does not read, each loading planted.py from a module on the program's import path.
LOADS = {
    "code run from a string, reached as another builtin's attribute": PLANTED,
    "a star import": "from site import *\nvars(builtins)['__imp' + 'ort__']('planted')\n",
    "a match pattern": ("import pkgutil\nmatch pkgutil:\n    case object(importlib=I):\n"
                        "        I.__dict__['import_' + 'module']('planted')\n"),
    "a class attribute": "import importlib\n\n\nclass _K:\n    load = importlib.import_module\n\n\n_K.load('planted')\n",
    "a name never written out": "import json\n_b = getattr(json, '__buil' + 'tins__')\n_b['__imp' + 'ort__']('planted')\n",
    "another library": "import pkgutil\npkgutil.resolve_name('planted')\n",
    "a name in globals() never written out": "globals()['__buil' + 'tins__']['__imp' + 'ort__']('planted')\n",
    "vars() of a module, by a name not written out": "import json\nvars(json)['__buil' + 'tins__']['__imp' + 'ort__']('planted')\n",
    "pydoc.locate": "import pydoc\npydoc.locate('planted')\n",
    "pickle loading a global": "import pickle\npickle.loads(b'cplanted\\nPLANTED\\n.')\n",
    "code run by another library": "import code\ncode.InteractiveInterpreter().runsource('import planted')\n",
    "a mock.patch target": "from unittest import mock\nwith mock.patch('planted.PLANTED', False):\n    pass\n",
}


@pytest.mark.parametrize("form", sorted(LOADS))
def test_a_module_loaded_by_a_form_the_inventory_does_not_read_fails_the_audit(tmp_path, form):
    root = _tree_with(tmp_path, {"time_zones.py": lambda text: text + "\n" + LOADS[form],
                                 "planted.py": lambda _text: "PLANTED = True\n"})
    found = audit_problems(audit(tmp_path, root), root)
    assert "loaded, not carried: planted.py" in found, found
    from_a_string = [p for p in found if p.startswith(("exec called from time_zones.py:",
                                                       "compile called from time_zones.py:"))]
    assert len(from_a_string) == (2 if LOADS[form] == PLANTED else 0), found
    assert all("<string>" in p for p in from_a_string), found


def test_code_run_from_a_string_on_a_page_fails_the_audit(tmp_path):
    root = _tree_with(tmp_path, {"app.py": lambda text: text.replace(conftest.UI_MARKER, PLANTED + conftest.UI_MARKER,
                                                                     1),
                                 "planted.py": lambda _text: "PLANTED = True\n"})
    found = audit_problems(audit(tmp_path, root, "chart"), root)
    assert "loaded, not carried: planted.py" in found, found
    assert any(p.startswith("exec called from app.py:") for p in found), found


def test_a_hook_installed_after_the_first_import_fails_the_audit(tmp_path):
    late = tmp_path / "late_audit.py"
    late.write_text(AUDIT.read_text(encoding="utf-8").replace(
        "\nsys.addaudithook(_hook)\n", f"\nsys.path.insert(0, {str(ROOT)!r})\nimport engine\nsys.addaudithook(_hook)\n",
        1), encoding="utf-8")
    found = audit_problems(audit(tmp_path, ROOT, driver=late), ROOT)
    assert "loaded before the audit hook: engine" in found and "not seen loaded: engine" in found, found


def test_an_audit_that_dies_fails(tmp_path):
    dead = tmp_path / "dead_audit.py"
    dead.write_text(AUDIT.read_text(encoding="utf-8").replace("    out.write_text(", "    os._exit(3)\n    out.write_text(",
                                                              1), encoding="utf-8")
    with pytest.raises(AssertionError):
        audit(tmp_path, ROOT, driver=dead)


def test_an_audit_that_starts_nothing_fails(tmp_path):
    """Zero input: an audit whose start loaded none of the program."""
    empty = tmp_path / "empty_audit.py"
    empty.write_text(AUDIT.read_text(encoding="utf-8").replace("        import desktop_launcher  # noqa: F401\n",
                                                               "        pass\n", 1)
                     .replace("        import engine  # noqa: F401\n", "        pass\n", 1), encoding="utf-8")
    found = audit_problems(audit(tmp_path, ROOT, driver=empty), ROOT)
    assert "not seen loaded: engine" in found and "not seen loaded: desktop_launcher" in found, found
