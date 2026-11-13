"""Regression harness for Executable/engine.py and Executable/app.py.

The app is two files: ``engine.py``, the calculation engine, and ``app.py``,
which takes it whole through ``from engine import *`` and carries the
Streamlit pages from the marker ``# 4. STREAMLIT UI INTEGRATION`` onward.
Two ways in:

* ``engine`` -- ``engine.py`` imported as a module and handed to the test as
  its namespace, so constants and evaluators can be inspected without a
  Streamlit run.
* ``make_app()`` -- ``streamlit.testing.v1.AppTest`` driving the whole script
  headless: no browser, no port. One call renders ONE page (Streamlit runs
  the script once per page), so tests parametrise over pages.

Both files are located relative to this file, so the suite runs from any
checkout or CI runner. (It used to hard-code the developer's absolute path
to dodge a stale ``app.py`` one directory up; that file is gone.)
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
from collections import Counter, namedtuple
from datetime import time
from html.parser import HTMLParser
from pathlib import Path

import pytest
from streamlit import config as _st_config

# Same option as Executable/.streamlit/config.toml, set directly
# so the suite renders with magic off regardless of the working directory
# AppTest is invoked from.
_st_config.set_option("runner.magicEnabled", False)

EXECUTABLE_DIR = Path(__file__).resolve().parents[1]
APP_PATH = EXECUTABLE_DIR / "app.py"
ENGINE_PATH = EXECUTABLE_DIR / "engine.py"
UI_MARKER = "# 4. STREAMLIT UI INTEGRATION"


import source_list  # noqa: E402  (tests/source_list.py: the program's source modules)

# app.py finds engine.py beside it because Streamlit puts the running
# script's own directory on sys.path (so does the frozen launcher). The
# suite is not run from there, so it puts the same directory on the path
# itself, once, for the `engine` fixture and for the app's own import.
if str(EXECUTABLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTABLE_DIR))
# A skip the run cannot account for fails it: tests/skip_guard.py, a plugin
# pytest.ini loads (pytest_configure below refuses a run without it; it
# refuses a run in which this file did not load, the redirect below with it). The
# corpus key is read from the Git configuration under the reader's own home,
# so it is resolved here, before the data-folder redirect below moves HOME
# on macOS; every later import of corpus_paths in this process gets this
# resolution. An xdist worker is another process, started with HOME already
# moved: the run hands it this resolution (pytest_configure_node below), and
# the worker takes it in place of its own before it collects a test. A
# process a test starts resolves for itself, under whatever HOME it is given.
import corpus_paths  # noqa: E402,F401

CORPUS_HANDOVER = "zij_corpus"      # the key in a worker's input that carries the resolution

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TABLES_FIXTURE = FIXTURE_DIR / "tables.json"

# Saved charts live in the user's data folder. Point it at a scratch
# directory so a test run can never read or write the real file.
#
# This was once setdefault, and Linux's
# variable alone, so a run started with XDG_DATA_HOME already set -- or any
# run on macOS or Windows, whose folders are not read from it -- used the
# reader's own data folder. The variable each platform's folder is read from
# is now set, whatever it held: XDG_DATA_HOME on Linux, APPDATA on Windows,
# HOME on macOS (Application Support is under the home).
#
# One process keeps the value it was given: a test's own child, which a test
# starts with a data folder of its own and which imports this file too. It
# is known by what only the harness puts in its environment -- the harness's
# mark, naming this harness's scratch folder, which the top-level run sets
# below, and pytest's PYTEST_CURRENT_TEST, which is there only while a test
# runs. Where the value lies says nothing: a TMPDIR at the home made the
# reader's own folder look like scratch. The program itself gains no switch
# for any of this; the mark is the harness's and is read only here.
HARNESS_DATA_HOME = Path(__file__).resolve().parent / ".xdg-scratch"
HARNESS_MARK = "ZIJ_HARNESS_SCRATCH"


def _a_tests_own_child(scratch, environ):
    return bool(environ.get("PYTEST_CURRENT_TEST")) and environ.get(HARNESS_MARK) == str(scratch)


def harness_data_environment(platform=None, scratch=HARNESS_DATA_HOME, environ=None):
    """The variable `platform`'s data folder is read from (sys.platform's
    when not given), set to `scratch`, and the harness's mark naming it.
    Only a test's own child (_a_tests_own_child, read in `environ`,
    os.environ when not given) keeps a value it was given."""
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    name = {"win32": "APPDATA", "darwin": "HOME"}.get(platform, "XDG_DATA_HOME")
    kept = environ.get(name) if _a_tests_own_child(scratch, environ) else None
    return {name: kept or str(scratch), HARNESS_MARK: str(scratch)}


os.environ.update(harness_data_environment())
# Preferences are neither read nor written under the harness, so a
# reading set in one test cannot leak into the next; tests of the preferences
# themselves delete this variable and point XDG_DATA_HOME at a tmp_path.
os.environ.setdefault("ALMUTEN_NO_PREFERENCES", "1")

# The place atlas is not kept in the repository: tools/fetch_atlas.py puts it
# at the root, checked against the SHA-256 time_zones.py records. Without it,
# or with another file there, the run stops at its start with one sentence
# that names the tool, before any test runs, rather than failing test by test.
# Checked in the process that starts the run; an xdist worker is then never
# started. A tree whose time_zones.py records no atlas holds no program that
# reads one (the copies of this harness the guard tests run, with a stand-in
# program or none): there is nothing to check it against, and it is not
# checked. The program's own time_zones.py records it, and the tests of the
# tool hold that record to its place.
FETCH_TOOL = "tools/fetch_atlas.py"


def check_the_atlas(root=None):
    """Raise pytest.UsageError unless `root` (the checkout) holds atlas.db
    with the SHA-256 time_zones.py records there. The tool's own reading of
    the record and of the file is used, so the two cannot disagree."""
    import importlib.util
    root = Path(root) if root is not None else EXECUTABLE_DIR
    record = root / "time_zones.py"
    if not record.is_file() or "SHIPPED_DATA_SHA256" not in record.read_text(encoding="utf-8"):
        return
    spec = importlib.util.spec_from_file_location("_fetch_atlas", EXECUTABLE_DIR / FETCH_TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    fetch = (f"Put it there with  python {FETCH_TOOL} --repo OWNER/NAME  (the repository whose release holds "
             f"it) or  --from <a folder holding its zip>, then run the tests again. No test was run.")
    try:
        digest = tool.pinned_digest(root)
    except tool.Refused as exc:
        raise pytest.UsageError(f"{exc}. No test was run.") from None
    atlas = root / "atlas.db"
    if not atlas.is_file():
        raise pytest.UsageError(f"atlas.db is not in the checkout. {fetch}")
    if not tool.matches(atlas, digest):
        raise pytest.UsageError(f"atlas.db in the checkout is not the file time_zones.py records. {fetch}")


# The fixture writer in test_pages_render.py is session-scoped and collects
# only the slots its own process rendered. Under xdist every worker is its
# own session, each writes the slots it happened to get, and the last one to
# finish overwrites the rest: six charts and eight pages came out as two and
# three. So an update run refuses to start with workers.
def pytest_configure(config):
    if not config.pluginmanager.has_plugin("skip_guard"):
        raise pytest.UsageError("the skip guard (tests/skip_guard.py) is not loaded: pytest.ini names it "
                                "with -p skip_guard; a run without it cannot say what it skipped")
    if not hasattr(config, "workerinput"):
        check_the_atlas()
    handed = getattr(config, "workerinput", {}).get(CORPUS_HANDOVER)
    if handed:                      # an xdist worker: the run's resolution, not one under the moved HOME
        corpus_paths.CORPUS_DIR, corpus_paths.CORPUS_SOURCE = Path(handed[0]), handed[1]
    if os.environ.get("UPDATE_TABLE_FIXTURE") != "1":
        return
    workers = os.environ.get("PYTEST_XDIST_WORKER") or getattr(config.option, "numprocesses", None)
    if workers:
        raise pytest.UsageError(
            "UPDATE_TABLE_FIXTURE=1 must run without xdist (no -n): each worker would write only "
            "its own slots to tests/fixtures/tables.json. Run  UPDATE_TABLE_FIXTURE=1 "
            "python -m pytest tests/test_pages_render.py  (about forty seconds).")


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    """xdist, in the process that starts the run, for each worker before it
    starts: the corpus as this process resolved it, carried in the worker's
    input rather than in its environment, so no process a test starts sees it."""
    node.workerinput[CORPUS_HANDOVER] = [str(corpus_paths.CORPUS_DIR), corpus_paths.CORPUS_SOURCE]


# --- The tripwire on the engine's namespace ----------------------------
# tests/split_census.py reads, by `ast`, every place a test replaces an
# attribute of the engine, and tests/test_split_astro_2026_10_14.py judges
# each: a test that replaces engine.X, where X is a name a module split out
# of the engine binds or reads, reaches nothing there. A reading can miss a
# spelling; the run sees the change a spelling makes, save on an engine
# imported afresh within a test (watched only from the next test's start)
# and in a change made from a frame of a program file (code compiled under
# its name, or a writer a test hands to a program function), taken for the
# program's own. So, in every process that runs tests (the run
# itself, or each xdist worker), the namespaces of the engine and of the
# modules split out of it are watched while the suite runs, and every change
# made to them by any route -- setattr and delattr, monkeypatch, mock.patch
# in each of its forms, an assignment, a write to vars() or __dict__, an
# update, a clear -- is seen as it is made, with the code that made it.
#
# The mechanism is CPython's dictionary watcher (PyDict_AddWatcher, reached
# through ctypes): a module's attributes are its namespace's items, every
# route to them ends in that dictionary, and the watcher is called before
# each change with the key and the new value. A subclass of ModuleType with
# __setattr__ would see the attribute routes only, and a comparison of the
# namespace at fixed points would miss a patch made and undone between two
# of them (a `with mock.patch.dict(...)` inside a test). The engine's module
# also takes a subclass of ModuleType whose __getattribute__ notes two reads
# through it: a name a split-out module binds that the engine does not have
# (the withheld names among them), and a name the running test has replaced
# in a split-out module.
#
# Each change is told by the code making it, read off the stack: a frame of
# the program's own files (its own `global` rebinding, a reload's run) or of
# the import machinery is the program's, and not judged; otherwise the
# innermost frame in tests/ is the site, its file and line; with no such
# frame (a decorator's patch, monkeypatch's undo) the site is the running
# test's own function. A change that puts back a value the name held before
# the tests changed it is a restore, not a replacement (the values kept
# include the last four the program itself gave the name in this process,
# so a replacement with one of them reads as a restore); so is one made by
# monkeypatch's undo that puts back a value a test's own site gave it (the
# undo of two setattr calls on one name passes through the first's value).
#
# Workers record; the process that started the run judges, as the skip guard
# does: each test's report carries what was seen while it ran, and a report
# that does not say the tripwire was armed fails the run. The judgement
# (tests/engine_tripwire.py) applies the split guard's rule to what was seen,
# and asks that every replacement of the engine seen be one the static census
# finds, in that file.
TRIPWIRE = "engine_tripwire"           # the user property each report carries; the key in a worker's output
WATCHED = ("engine", "ephemeris", "time_zones", "user_data", "markup", "wheel", "export_html")
# The modules whose replacements are told to the judgement as well: wheel.py
# and export_html.py hold markup.py's names by their import, so a replacement
# in markup.py alone reaches neither of them.
TOLD = ("markup", "wheel", "export_html")
TESTS_DIR = Path(__file__).resolve().parent
_ABSENT = object()                     # a name not in the namespace (before it was added, after it was deleted)
_BASELINES_KEPT = 4                    # the program's own values per name, kept to tell a restore


class _WatchedModule(type(sys)):
    """The engine's module, two kinds of read through its attributes noted."""

    def __getattribute__(self, name):
        try:
            value = type(sys).__getattribute__(self, name)
        except AttributeError:
            if name in _TRIP.split_names:
                _TRIP.read(name, "missing", sys._getframe(1))
            raise
        if name in _TRIP.replaced_split:
            _TRIP.read(name, "replaced", sys._getframe(1))
        return value


class _Tripwire:
    def __init__(self):
        self.armed = False
        self.why_not = "never installed in this process"
        self.judge = False             # the process that judges: the run itself, or xdist's controller
        self.events = []               # seen since the last report
        self.loose = []                # seen outside any test (collection, the session's end)
        self.in_test = False
        self.spaces = {}               # id(namespace) -> (module name, namespace)
        self.baselines = {}            # (module, name) -> the values it held before the tests changed it
        self.written = {}              # (module, name) -> the values tests' changes gave it, last few
        self.undoing = False           # the change under way is monkeypatch's undo
        self.pending = {}              # id(namespace) -> (its items before a clear, its site, the clearing frames)
        self.replaced_split = frozenset()   # names the running test replaced in a split-out module
        self.split_names = frozenset()
        self.kinds = {}                # code file -> "program", "load", "test" or "other"
        self.faults = []
        self.watcher = None
        self._api = self._callback = None

    # -- installing
    def install(self):
        import ctypes

        try:
            api = ctypes.pythonapi
            callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                             ctypes.c_void_p)
            api.PyDict_AddWatcher.argtypes, api.PyDict_AddWatcher.restype = [callback_type], ctypes.c_int
            for name in ("PyDict_Watch", "PyDict_Unwatch"):
                getattr(api, name).argtypes, getattr(api, name).restype = [ctypes.c_int, ctypes.py_object], ctypes.c_int
            api.PyDict_ClearWatcher.argtypes, api.PyDict_ClearWatcher.restype = [ctypes.c_int], ctypes.c_int
            self._api, self._callback = api, callback_type(_tripwire_seen)
            self.watcher = api.PyDict_AddWatcher(self._callback)
            if self.watcher < 0:
                raise RuntimeError("no dictionary watcher is free")
            self.watch_modules()
            import atexit

            atexit.register(self.uninstall)   # never called back while the interpreter tears the modules down
        except Exception as exc:       # armed stays False: every report says so, and the run fails
            self.why_not = f"the tripwire could not be installed: {exc!r}"
            return
        self.armed = True

    def watch_modules(self):
        """Watch the four modules (the engine imported, which loads the
        others); a module object met for the first time (a fresh import in
        this process) is watched from then on."""
        if self.watcher is None:
            return
        import engine  # noqa: F401  (it loads the modules split out of it)

        for name, loaded in list(sys.modules.items()):
            if name not in WATCHED or id(vars(loaded)) in self.spaces:
                continue
            if self._api.PyDict_Watch(self.watcher, vars(loaded)) != 0:
                raise RuntimeError(f"{name}'s namespace could not be watched")
            self.spaces[id(vars(loaded))] = (name, vars(loaded))
            if name == "engine":
                loaded.__class__ = _WatchedModule
        self.split_names = frozenset(n for name, space in self.spaces.values() if name != "engine"
                                     for n in space if not n.startswith("__"))

    def uninstall(self):
        if self.watcher is None:
            return
        for _module, space in self.spaces.values():
            self._api.PyDict_Unwatch(self.watcher, space)
        self._api.PyDict_ClearWatcher(self.watcher)
        self.watcher, self.armed = None, False
        self.spaces.clear()

    # -- telling who changed it
    def kind(self, filename):
        known = self.kinds.get(filename)
        if known is None:
            known = "other"
            if filename.startswith("<frozen importlib"):
                known = "load"
            elif not filename.startswith("<"):
                path = Path(os.path.realpath(filename))
                if path.parent == EXECUTABLE_DIR and path.suffix == ".py":
                    known = "program"
                elif path.parent.name == "importlib" and path.name == "__init__.py":
                    known = "load"
                elif path.is_relative_to(TESTS_DIR) and path.suffix == ".py":
                    known = "test"
            self.kinds[filename] = known
        return known

    def site(self, frame):
        """(who, file, line): the program's or the import machinery's; or a
        test's, its file under tests/ and line, or (None, None) when no frame
        of tests/ is on the stack."""
        while frame is not None:
            known = self.kind(frame.f_code.co_filename)
            if known in ("program", "load"):
                return known, None, None
            if known == "test":
                where = Path(os.path.realpath(frame.f_code.co_filename)).relative_to(TESTS_DIR)
                return "test", where.as_posix(), frame.f_lineno
            frame = frame.f_back
        return "test", None, None

    # -- what was seen
    def seen(self, event, address, key, new, frame):
        import ctypes

        held = self.spaces.get(address)
        if held is None:
            return
        module, space = held
        if event == 5:                 # the namespace freed
            del self.spaces[address]
            return
        site = self.site(frame)
        if event == 4:                 # cleared: called before the clear, so the items are still there
            self.settle(address)
            chain, f = [], frame       # the clearing frame and its two callers: a refill from one of them pairs
            while f is not None and len(chain) < 3:
                chain.append(f)
                f = f.f_back
            self.pending[address] = (dict(space), site, chain)
            return
        if address in self.pending and not any(frame is f for f in self.pending[address][2]):
            self.settle(address)       # a clear left standing while other code ran
        if event == 3:                 # cloned into the emptied namespace: `key` is the source
            source = ctypes.cast(key, ctypes.py_object).value
            before = self.pending.get(address, ({}, site, ()))[0]
            for name, value in source.items():
                self.change(module, name, before.get(name, _ABSENT), value, site)
            self.settle(address, after=source)     # the namespace becomes the source, whole
            return
        name = ctypes.cast(key, ctypes.py_object).value
        value = ctypes.cast(new, ctypes.py_object).value if new else _ABSENT
        old = space.get(name, _ABSENT)
        if old is _ABSENT and address in self.pending:
            old = self.pending[address][0].get(name, _ABSENT)
        self.undoing = frame is not None and frame.f_code.co_name == "undo" \
            and Path(frame.f_code.co_filename).parent.name == "_pytest"
        try:
            self.change(module, name, old, value, site)
        finally:
            self.undoing = False

    def settle(self, address=None, after=None):
        """A clear is judged with what refilled it from the same code (how
        patch.dict puts a namespace back: clear, then update): the names it
        took and nothing put back by the next fixed point (the end of a
        test's phase), by code elsewhere, or by the next clear, are deleted,
        all at once, at the clear's site."""
        for where in ([address] if address is not None else list(self.pending)):
            if where not in self.pending:
                continue
            before, site, _chain = self.pending.pop(where)
            if where not in self.spaces:
                continue
            module, space = self.spaces[where]
            space = space if after is None else after    # a clone's callback comes before the clone
            gone = [name for name, value in before.items() if name not in space
                    and self.change(module, name, value, _ABSENT, site, quiet=True)]
            if gone and module == "engine":
                self.note({"module": module, "name": "*", "kind": "clear", "count": len(gone),
                           "file": site[1], "line": site[2], "by": "test"})

    def change(self, module, name, old, new, site, quiet=False):
        """Judge one change; True where it is a test's replacement (noted
        unless `quiet`)."""
        who, file, line = site
        kept = self.baselines.setdefault((module, name), [])
        if who in ("program", "load"):
            kept[:] = (kept + [new])[-_BASELINES_KEPT:]
            if module == "engine" and who == "program" and old is _ABSENT and name in self.split_names:
                self.note({"module": module, "name": name, "kind": "set", "file": None, "line": None,
                           "by": "program"})
            return False
        if not kept:
            kept.append(old)
        if any(new is value for value in kept):
            return False               # a restore
        written = self.written.setdefault((module, name), [])
        if self.undoing and any(new is value for value in written):
            return False               # monkeypatch's undo putting back a value a test's own site set
        written[:] = (written + [new])[-_BASELINES_KEPT:]
        if module != "engine":
            if self.in_test:
                self.replaced_split |= {name}
                if module in TOLD and not quiet:
                    self.note({"module": module, "name": name, "kind": "set in a module", "file": file, "line": line,
                               "by": "test"})
            return True
        if not quiet:
            self.note({"module": module, "name": name, "kind": "delete" if new is _ABSENT else "set",
                       "file": file, "line": line, "by": "test"})
        return True

    def read(self, name, how, frame):
        who, file, line = self.site(frame)
        if who != "load":
            self.note({"module": "engine", "name": name, "kind": f"read {how}", "file": file, "line": line,
                       "by": who})

    def note(self, event):
        (self.events if self.in_test else self.loose).append(event)

    def take(self):
        self.settle()
        events, self.events = self.events, []
        return events


_TRIP = _Tripwire()


def _tripwire_seen(event, address, key, new):
    """The dictionary watcher's callback. It may not raise (the change is
    under way), so a fault is kept, and fails the run instead."""
    try:
        _TRIP.seen(event, address, key, new, sys._getframe(1))
    except BaseException as exc:      # noqa: BLE001 -- see the docstring
        _TRIP.faults.append(repr(exc))
    return 0


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    config = session.config
    _TRIP.judge = not hasattr(config, "workerinput")      # the run itself, or xdist's controller
    if not config.pluginmanager.has_plugin("dsession"):    # a process that runs tests: not xdist's controller
        _TRIP.install()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    if _TRIP.armed:
        try:
            _TRIP.watch_modules()
        except Exception as exc:       # noqa: BLE001 -- carried by the test's reports
            _TRIP.faults.append(repr(exc))
    _TRIP.settle()
    _TRIP.loose += _TRIP.events
    _TRIP.events, _TRIP.in_test, _TRIP.replaced_split = [], True, frozenset()
    try:
        return (yield)
    finally:
        _TRIP.settle()
        _TRIP.loose += _TRIP.events
        _TRIP.events, _TRIP.in_test, _TRIP.replaced_split = [], False, frozenset()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    # The tripwire's property is its own: one a test wrote into its own properties is dropped.
    report.user_properties = [p for p in report.user_properties if not (len(p) == 2 and p[0] == TRIPWIRE)]
    report.user_properties.append((TRIPWIRE, {"armed": _TRIP.armed, "why_not": _TRIP.why_not,
                                              "events": _TRIP.take(), "faults": list(_TRIP.faults)}))
    return report


_RECEIVED = {"reports": 0, "unarmed": [], "events": [], "faults": [], "workers": []}


def pytest_runtest_logreport(report):
    if not _TRIP.judge or report.when not in ("setup", "call", "teardown"):
        return                         # a worker (its controller receives the report), or xdist's crash report
    _RECEIVED["reports"] += 1
    carried = [p[1] for p in report.user_properties if len(p) == 2 and p[0] == TRIPWIRE]
    if not carried or not carried[-1].get("armed"):
        _RECEIVED["unarmed"].append((report.nodeid, carried[-1].get("why_not") if carried else "nothing carried"))
        return
    _RECEIVED["events"] += [dict(e, nodeid=report.nodeid, when=report.when) for e in carried[-1]["events"]]
    _RECEIVED["faults"] += [(report.nodeid, f) for f in carried[-1]["faults"]
                            if (report.nodeid, f) not in _RECEIVED["faults"]]


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    """xdist, in the controller: what a worker saw outside its tests. A
    worker that died sends nothing here; what its tests' reports carried is
    judged all the same."""
    carried = getattr(node, "workeroutput", {}).get(TRIPWIRE)
    if carried:
        _RECEIVED["events"] += [dict(e, nodeid="(outside a test)", when="session") for e in carried["events"]]
        _RECEIVED["faults"] += [("(outside a test)", f) for f in carried["faults"]]
    _RECEIVED["workers"].append((getattr(node.gateway, "id", "?"), bool(carried), error))


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput[TRIPWIRE] = {"events": _TRIP.loose + _TRIP.take(), "faults": list(_TRIP.faults)}
        return
    if not _TRIP.judge:
        return
    if _TRIP.armed:                    # the run itself ran the tests: what it saw outside them
        _RECEIVED["events"] += [dict(e, nodeid="(outside a test)", when="session") for e in _TRIP.loose + _TRIP.take()]
    lines = []
    if _RECEIVED["unarmed"]:
        nodeid, why = _RECEIVED["unarmed"][0]
        lines.append(f"ENGINE TRIPWIRE: not armed where {len(_RECEIVED['unarmed'])} test report(s) were made "
                     f"(first {nodeid}: {why})")
    if _RECEIVED["faults"]:
        where, fault = _RECEIVED["faults"][0]
        lines.append(f"ENGINE TRIPWIRE: {len(_RECEIVED['faults'])} fault(s) in the tripwire itself "
                     f"(first {where}: {fault})")
    summary = f"ENGINE TRIPWIRE: nothing replaced in the engine in {_RECEIVED['reports']} test report(s)"
    if _RECEIVED["events"]:
        import engine_tripwire

        found, summary = engine_tripwire.judge(_RECEIVED["events"], TESTS_DIR, _RECEIVED["reports"])
        lines += found
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    write = tr.write_line if tr is not None else print
    write("")
    for ln in lines:
        write(ln, **({"red": True} if tr is not None else {}))
    if lines:
        session.exitstatus = 1
    write(summary)


def pytest_unconfigure(config):
    _TRIP.uninstall()


# --- Charts and pages ----------------------------------------------------
# All Florence, LMT, 14:30. Between them they populate the conditional
# tables that are empty on the default chart.
CHARTS = {
    "1240-05-23": "the app default",
    "1240-05-25": "Reception by nature (Sun/Moon in aversion)",
    "1240-05-26": "Reflection of Light and Favor & Recompense",
    "1240-09-18": "dense Returning and Prevented connections",
    "1240-10-05": "retreating quadrants, a retrograde planet",
    # Added when the Egyptian-bounds fix emptied Favor & Recompense
    # on 1240-05-26 (its only row had come from the transposed Gemini bound).
    # The Sun at 21 Capricorn (degree 22, a Well degree) with Saturn, its
    # domicile lord, connected -- a Saturn-helped Favor, which no other chart
    # has; the others' Favor rows were all Jupiter-helped.
    "1240-01-04": "Favor & Recompense (Sun in a Well, favored by Saturn)",
}
FLORENCE = (43.7792, 11.2463)
LOCAL_TIME = time(14, 30)

# url_path of every st.Page, in navigation order. (The Configurations page's
# three-way view control went; the reading depth, a store key
# like the switches, decides where Abu Ma'shar's tables sit. The depth also
# decides whether some render at all -- the Book V
# degrees, the father Lot's second form, Figure 64's column on the
# Reference page -- so the multiset differs between depths.)
PAGES = ["chart", "dignities", "delineations", "configurations", "lots", "victors", "timing", "releaser", "days", "fardar",
         "reference", "sources", "fixed-stars", "sky"]
READING_DEPTHS = ["Course text", "Course text and supplement"]

# The configurable readings (one entry per switch; the matrix test takes their
# cross-product, so each new switch doubles it). Since the UI restructure each
# control renders on the page and table it affects, and the engine reads its
# value at the top level from a store key that _persist() keeps across
# navigation. Tests set the STORE key through session_state before the run (the
# widget-first read at the top level falls back to it); the widget itself is
# located by label prefix on its page so a reworded or moved control fails
# loudly.
SWITCHES = {
    # name: (store key, alternatives, page, view, widget kind, label prefix)
    "connection": ("_connection_rule", ["Sahl", "Abu Ma'shar"], "configurations", None, "radio", "Connection test"),
    "eastern": ("_eastern_rule", ["hemisphere", "VII.2 band"], "configurations", None, "radio", "Gr. Intr. VII.6, 27/45"),
    "moon_rays": ("_moon_rays_15", [False, True], "chart", None, "checkbox", "Moon under the rays"),
    "mars_west": ("_mars_west_18", [False, True], "chart", None, "checkbox", "Mars under the rays"),
    "domain": ("_domain_rule", ["Abu Ma'shar", "Masha'allah"], "dignities", None, "radio", "Domain (hayz)"),
    "lot_cusp": ("_lot_house_cusp", ["whole-sign place", "quadrant cusp"], "lots", None, "radio", "House-based Lot construction"),
    "fitting": ("_fitting_infortune", [False, True], "configurations", None, "checkbox", "Fitting infortune"),
}


def page_slots():
    """Every (page, view) a test should render. view is always None now;
    the pair is kept so slot names and fixtures read as before."""
    return [(page, None) for page in PAGES]


def slot_name(page, view):
    return page if view is None else f"{page}/{view}"


# --- The app under AppTest ----------------------------------------------

# user_data.py, the data layer the engine takes whole, resolves DATA_DIR,
# SAVED_CHARTS_PATH and PREFERENCES_PATH once, at its import, where
# _user_data_dir() reads the environment. While the engine was the top half
# of app.py every AppTest run re-executed those lines, so a test that
# re-pointed XDG_DATA_HOME at a tmp_path got a fresh path for free; an
# imported module is cached in sys.modules and would hand the next test the
# first test's directory. So the harness re-imports the data layer whenever
# the environment those paths are read from has moved -- which is something
# tests do and a served app never does, its environment being fixed for the
# life of the process either way -- and then the engine, whose star import
# takes the new paths, functions and classes. The data layer is reloaded
# first: a reload of the engine alone re-runs its star import against the
# module already loaded, and resolves nothing again.
_ENGINE_ENVIRONMENT = ("XDG_DATA_HOME", "APPDATA", "ALMUTEN_NO_PREFERENCES")


def sync_engine_to_environment():
    import importlib

    module = sys.modules.get("engine")
    if module is None:
        return
    environment = tuple(os.environ.get(name) for name in _ENGINE_ENVIRONMENT)
    if getattr(module, "_harness_environment", None) == environment:
        return
    importlib.reload(sys.modules["user_data"])
    importlib.reload(module)._harness_environment = environment


def make_app(date="1240-05-23", page=None, view=None, switches=None, timeout=60):
    """Build an AppTest for one chart and one page, unrun.

    Sidebar inputs that carry a session_state key are set through the key
    (that is how the app's own saved-chart loader does it). The page is
    selected the way st.navigation selects it: by the hash of the
    st.Page url_path, which is what AppTest.switch_page() computes for
    file-based pages -- there is no public equivalent for function pages.
    """
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash

    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=timeout)
    at.session_state["manual_coords_key"] = True
    at.session_state["manual_lat_key"] = FLORENCE[0]
    at.session_state["manual_lon_key"] = FLORENCE[1]
    at.session_state["date_input_key"] = date
    at.session_state["time_input_key"] = LOCAL_TIME
    if view is not None:
        # The Configurations view control is gone; a caller
        # passing one of the old view names gets the depth that shows it.
        at.session_state["_reading_depth"] = "Course text and supplement" if view != "Sahl (course text)" else "Course text"
    if page is not None:
        at._page_hash = calc_hash(page)
    if switches:
        apply_switches(at, switches)
    return at


def find_page_widget(at, kind, label_prefix):
    """The one widget of `kind` on the rendered page whose label starts
    with `label_prefix`."""
    widgets = getattr(at.main, kind)
    hits = [w for w in widgets if w.label.startswith(label_prefix)]
    assert len(hits) == 1, (
        f"expected exactly one page {kind} labelled '{label_prefix}...', "
        f"found {[w.label for w in widgets]}")
    return hits[0]


def apply_switches(at, switches):
    """switches: {name: value} using the names in SWITCHES. Sets the store
    key the engine reads; call before at.run()."""
    for name, value in switches.items():
        store, alternatives = SWITCHES[name][0], SWITCHES[name][1]
        assert value in alternatives, f"{name}: {value!r} not in {alternatives}"
        at.session_state[store] = value
    return at


def assert_no_exception(at, context=""):
    if len(at.exception):
        details = "\n\n".join(e.value for e in at.exception)
        pytest.fail(f"{context}: the app raised\n{details}")


# --- A run that never reached the page ------------------------------------

# A script that does not compile leaves AppTest's page empty and
# at.exception with it, so a pin that asserts only that some text is absent
# would pass. Streamlit's script runner logs "Script compilation error", on
# a logger that does not propagate, and sends a compile-error event that
# AppTest does not keep; the record is what is read here. Every AppTest run
# in this process is checked as it returns. A record Streamlit stops logging
# still leaves an empty page, which fails as one. Only the main area is the
# page: the sidebar is drawn before the navigation runs the page, so a run that
# stopped above that call still holds a whole sidebar.
COMPILE_ERROR_LOGGER = "streamlit.runtime.scriptrunner.script_runner"
COMPILE_ERROR_RECORD = "Script compilation error"


class _CompileErrors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.seen = []

    def emit(self, record):
        if record.getMessage() == COMPILE_ERROR_RECORD:
            self.seen.append(record)


def page_not_reached(at, compile_errors=()):
    """Why a finished run did not reach the page, or None if it did: the
    script did not compile, it raised before it rendered anything in the main
    area, or the main area holds nothing. A page's own refusal stands in the
    main area, so a run stopped by one reached it, and its test asserts the
    refusal's sentence."""
    if compile_errors:
        error = compile_errors[0].exc_info
        return f"the app did not compile: {error[1]!r}" if error else "the app did not compile"
    rendered = [node for node in at.main if node is not at.main]
    but = " but its sidebar" if any(node is not at.sidebar for node in at.sidebar) else ""
    if not rendered:
        return f"the app rendered nothing{but}"
    if all(getattr(node, "type", None) == "exception" for node in rendered):
        details = "\n\n".join(e.value for e in at.exception)
        return f"the app raised before it rendered anything{but}\n{details}"
    return None


def assert_page_reached(at, context="", compile_errors=()):
    reason = page_not_reached(at, compile_errors)
    if reason is not None:
        pytest.fail(f"{context}: the run did not reach the page: {reason}")


def _checking_page_reached(run):
    def _run(self, *args, **kwargs):
        handler = _CompileErrors()
        logger = logging.getLogger(COMPILE_ERROR_LOGGER)
        logger.addHandler(handler)
        try:
            result = run(self, *args, **kwargs)
        finally:
            logger.removeHandler(handler)
        assert_page_reached(self, Path(self._script_path).name, handler.seen)
        return result

    _run.checks_page_reached = True
    return _run


def install_page_reached_check():
    """Wrap AppTest._run, the one call every AppTest run goes through (the
    first run, a rerun, a widget's), once per process."""
    from streamlit.testing.v1 import AppTest

    if not getattr(AppTest._run, "checks_page_reached", False):
        AppTest._run = _checking_page_reached(AppTest._run)


install_page_reached_check()


# --- Table identity -----------------------------------------------------

from streamlit.testing.v1 import element_tree  # noqa: E402

NOTES_EXPANDER_LABEL = "Sources and editorial notes"
NOTES_EXPANDER_ICON = ":material/menu_book:"


def _is_notes_expander(node):
    """An expander that is a notes panel, not a table heading: labelled
    "Sources and editorial notes" or carrying the book icon. AppTest
    builds every st.expander as an Expander (type "expander"), with an
    icon or without, and only st.status as a Status (type "status");
    before Streamlit 1.65 it built an expander WITH an icon as a Status.
    Both come from the same Expandable proto and both carry .label and
    .icon, so the walker reads the two types alike. `.icon` is the raw
    string as passed to st.expander(icon=...), e.g.
    ":material/menu_book:", not a normalised form (Streamlit 1.66.1)."""
    if getattr(node, "type", None) not in ("expander", "status"):
        return False
    return node.label == NOTES_EXPANDER_LABEL or node.icon == NOTES_EXPANDER_ICON


def node_kind(node):
    """A node's AppTest type, but "status" for an expander that carries an
    icon: a notes panel's book, or a help panel's question mark. Until
    Streamlit 1.65 AppTest built such an expander as a Status node, and the
    page-structure tests name it so, to tell it from an expander without
    one; AppTest now builds both as an Expander, and the icon is what tells
    them apart. The app draws no st.status, so nothing else is "status"."""
    kind = getattr(node, "type", None)
    return "status" if kind == "expander" and node.icon else kind


def node_class(node):
    """type(node).__name__, but "Status" for an expander that carries an
    icon, as node_kind names its type, and "Dataframe" for a text table, a table among tables."""
    return "Status" if node_kind(node) == "status" else "Dataframe" if isinstance(node, TextTable) else type(node).__name__


# A line under a row that its column's heading does not lead: the page draws no
# word for its column, so a test reads it under this one.
UNLABELLED_LINE = "(line under its row)"


class _TextTableReader(HTMLParser):
    """A text table's markup as a reader sees it: its headings, each row's cells,
    and the lines under each row with the labels that lead them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings, self.tips, self.rows, self.bold = [], {}, [], set()
        self.kind = self.cell = self.label = self.tip = None
        self.in_head = self.in_label = self.under = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        kinds = (attrs.get("class") or "").split()
        if tag == "thead":
            self.in_head = True
        elif tag == "tr":
            self.under = "zij-under" in kinds
            if not self.under and not self.in_head:
                self.rows.append({"cells": [], "lines": []})
        elif tag in ("th", "td"):
            self.cell, self.label, self.tip = "", None, attrs.get("title")
            self.kind = ("fill" if "zij-fill" in kinds else "head" if tag == "th"
                         else "line" if self.under else "cell")
            if self.kind == "cell" and "zij-row-value" in kinds:
                self.bold.add(len(self.rows[-1]["cells"]))
        elif tag == "span" and "zij-under-head" in kinds:
            self.in_label, self.label = True, ""
        elif tag == "br" and self.cell is not None:
            self.cell += "\n"

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_head = False
        elif tag == "span" and self.in_label:
            self.in_label = False
        elif tag in ("th", "td") and self.cell is not None:
            if self.kind == "head":
                self.headings.append(self.cell)
                if self.tip:
                    self.tips[self.cell] = self.tip
            elif self.kind == "cell":
                self.rows[-1]["cells"].append(self.cell)
            elif self.kind == "line":
                self.rows[-1]["lines"].append((self.label or UNLABELLED_LINE, self.cell.lstrip(" \n")))
            self.cell = None

    def handle_data(self, data):
        if self.in_label:
            self.label += data
        elif self.cell is not None:
            self.cell += data


class TextTable(element_tree.Element):
    """A table the page drew in its own markup, as the test tree holds it: a table
    among tables, as `at.main.dataframe` and a walk of the tree read it, its type
    "dataframe". `.value` is a frame with a column for each heading and then one
    for each label of a line under a row; a column of nothing but numbers holds
    numbers, an empty cell empty, as a grid's does, and a list's drawn lines are read as the spaces they
    stand for. `.rows` keeps each row's cells and lines as drawn, a line end for
    each drawn line; the proto is st.html's."""

    def __init__(self, proto, root=None):
        self.proto, self.root, self.type, self.key = proto, root, "dataframe", None
        self.body = proto if isinstance(proto, str) else proto.body
        reader = _TextTableReader()
        reader.feed(self.body)
        self.headings, self.tips, self.rows, self._bold = reader.headings, reader.tips, reader.rows, reader.bold
        self.line_labels = list(dict.fromkeys(label for row in self.rows for label, _ in row["lines"]))
        self.bold_columns = {self.headings[at] for at in self._bold}
        self._frame = None

    def __repr__(self):
        return f"TextTable({self.headings!r})"

    @property
    def value(self):
        # pandas is imported here: a test of another platform's harness loads this
        # file with sys.platform pretending, and pandas cannot load so.
        import pandas as pd
        if self._frame is None:
            self._frame = pd.DataFrame(
                [[*row["cells"], *(dict(row["lines"]).get(label, "") for label in self.line_labels)] for row in self.rows],
                columns=[*self.headings, *self.line_labels], dtype=object).map(lambda cell: cell.replace("\n", " "))
            for at, column in enumerate(self._frame.columns):
                held = self._frame.iloc[:, at]
                if any(held) and all(not cell or _NUMBER_TEXT.fullmatch(cell) for cell in held):
                    self._frame[column] = pd.to_numeric(held)
        return self._frame


_NUMBER_TEXT = re.compile(r"-?\d+(?:\.\d+)?")


def _html_or_text_table(proto, root):
    """What the test tree builds for an st.html: a TextTable when it draws one."""
    return (TextTable if 'class="zij-table"' in proto.body else _Html)(proto, root)


_Html = element_tree.Html
element_tree.Html = _html_or_text_table
_markdown_init = element_tree.Markdown.__init__


def _markdown_as_it_reads(self, proto, root):
    """A Markdown table's kept-whole spaces read as the spaces they are."""
    proto.body = proto.body.replace("\u00a0", " ")
    _markdown_init(self, proto, root)


element_tree.Markdown.__init__ = _markdown_as_it_reads


def table_nodes(at):
    """Every table with rows on the rendered page, a grid or a text table, in
    order, as (heading, node). The heading is the nearest preceding st.subheader
    or expander label; a notes expander (see _is_notes_expander) is skipped -- it
    follows its table, or holds a lookup table of its own, and is not a heading
    for what comes next. A grid's node is Streamlit's, a text table's a TextTable;
    each holds its frame at `.value`."""
    found = []
    heading = None
    for node in at.main:          # Block.__iter__ walks the tree in order
        kind = getattr(node, "type", None)
        if kind == "subheader":
            heading = node.value
        elif kind in ("expander", "status") and not _is_notes_expander(node):
            heading = node.label
        elif kind == "dataframe":
            found.append((heading or "(no heading)", node))
    return found


def text_table_nodes(at):
    """The (heading, table) of table_nodes that are text tables."""
    return [(heading, node) for heading, node in table_nodes(at) if isinstance(node, TextTable)]


def table_inventory(at):
    """Every table on the rendered page, in order, as (heading, columns), keyed
    as table_nodes() keys them."""
    return [(heading, list(node.value.columns)) for heading, node in table_nodes(at)]


def find_table(at, heading):
    """The first table under exactly this heading, keyed as table_nodes() keys
    headings."""
    for found, node in table_nodes(at):
        if found == heading:
            return node
    raise LookupError(f"no table found under heading {heading!r}")


# --- Components ---------------------------------------------------------
# The Chart page's wheel is an st.components.v2 mount rather than an
# st.image. AppTest renders one as an element of type "bidi_component"
# whose proto carries the component's name and the JSON envelope it was
# mounted with, which is where the SVG is read from now.

def component_mounts(node, name, found=None):
    """Every mount of the component `name` under a rendered node."""
    found = [] if found is None else found
    for child in getattr(node, "children", {}).values():
        if getattr(child, "type", None) == "bidi_component" and child.proto.component_name == name:
            found.append(child)
        else:
            component_mounts(child, name, found)
    return found


def natal_wheel_envelope(node):
    """The one natal_wheel mount's data envelope: {'svg', 'width', 'signs'}."""
    mounts = component_mounts(node, "natal_wheel")
    assert len(mounts) == 1, f"expected one natal_wheel mount under {node}, found {len(mounts)}"
    return json.loads(mounts[0].proto.json)


def _key(entry):
    heading, columns = entry
    return (heading, tuple(columns))


def describe_table_diff(expected, actual):
    """A readable account of which tables went missing, appeared, or
    changed multiplicity. Compares multisets, not counts."""
    exp, act = Counter(map(_key, expected)), Counter(map(_key, actual))
    lines = []
    for key in sorted(set(exp) | set(act)):
        e, a = exp[key], act[key]
        if e == a:
            continue
        heading, columns = key
        if a == 0:
            lines.append(f"  MISSING   {heading!r} (expected {e}x) columns={list(columns)}")
        elif e == 0:
            lines.append(f"  UNEXPECTED {heading!r} ({a}x) columns={list(columns)}")
        else:
            lines.append(f"  COUNT     {heading!r}: expected {e}x, rendered {a}x")
    return "\n".join(lines)


def dump_fixture(data):
    """One table per line, so a diff of the fixture reads as which table
    appeared or went missing."""
    out = ["{"]
    dates = list(data)
    for i, d in enumerate(dates):
        out.append(f' "{d}": {{')
        slots = list(data[d])
        for j, s in enumerate(slots):
            out.append(f"  {json.dumps(s, ensure_ascii=False)}: [")
            rows = data[d][s]
            for k, row in enumerate(rows):
                out.append("   " + json.dumps(row, ensure_ascii=False) + ("," if k < len(rows) - 1 else ""))
            out.append("  ]" + ("," if j < len(slots) - 1 else ""))
        out.append(" }" + ("," if i < len(dates) - 1 else ""))
    out.append("}")
    return "\n".join(out) + "\n"


# The labels' renaming took two columns of the aspects table:
# the directed-agency column and the connection verdict, which
# is now a named state rather than Yes/No. The guards that compare this
# fixture with main's bring main's copy forward through the rename, so they
# go on pinning every other column of every other table.
LABEL_RENAMES_2026_09_16 = {"Applying Planet": "Connecting planet", "Connected": "Connection"}


def with_2026_09_16_renames(inventory):
    """A tables.json structure with those two column names brought forward."""
    if isinstance(inventory, dict):
        return {key: with_2026_09_16_renames(value) for key, value in inventory.items()}
    if isinstance(inventory, list):
        return [with_2026_09_16_renames(value) for value in inventory]
    return LABEL_RENAMES_2026_09_16.get(inventory, inventory)


def load_table_fixture():
    if not TABLES_FIXTURE.exists():
        pytest.fail(f"{TABLES_FIXTURE} is missing; run  UPDATE_TABLE_FIXTURE=1 pytest tests/test_pages_render.py")
    return json.loads(TABLES_FIXTURE.read_text())


# --- The engine as a module ---------------------------------------------

def source_files():
    """Every source module of the program, in the list's order
    (source_modules.txt; engine.py and app.py when there is none). A scan
    of the whole program walks these, never two names: a module split out
    of engine.py is read without another edit, and a scan written against
    the pair cannot pass because it stopped reading moved code."""
    return source_list.files(EXECUTABLE_DIR)


def engine_files():
    """The source modules but app.py: the engine, however many files it is."""
    return [path for path in source_files() if path.name != APP_PATH.name]


def engine_source():
    """The engine, whole: every source module but app.py, in the list's
    order, joined by a newline (engine.py alone while it is the only one)."""
    return "\n".join(path.read_text() for path in engine_files())


def ui_source():
    """The pages: app.py from the marker on. Its few lines above the marker
    are the docstring, the imports and the star import, which no page
    prints and no source scan has ever read."""
    src = APP_PATH.read_text()
    return src[src.index(UI_MARKER):]


def app_source():
    """The whole app as one text, which before the split of this file into
    two was one file's ``read_text()``. Every scan written against that --
    the citation scans, the prose guards, the dead-function check -- reads
    every source module here rather than one, so nothing it guarded went
    unguarded when the engine moved out, or goes unguarded when a module
    moves out of the engine."""
    return engine_source() + ui_source()


def _refuse_raw_text(self, *_spec):
    raise TypeError(
        f"{self.status} result reached page text raw ({self.reason!r}); "
        "pass it through _display_result at the page boundary")


@pytest.fixture
def the_data_folder_held_is_let_go(monkeypatch):
    """For a file whose tests launch the data layer (each such file names it
    in its pytestmark): when a test ends, the data folder its launches left
    held (user_data._HELD, a descriptor kept for the life of a launch's
    process) is closed, not left to the garbage collector, so that no test
    ends with a held data folder still open. Only a folder held since the
    test began is closed; the one held before it is left. Torn down before
    the test's monkeypatch is undone (it asks for monkeypatch), so that a
    list of the test's own, set by monkeypatch, is still the one found."""
    module = sys.modules.get("user_data")
    held = getattr(module, "_HELD", None)
    before = held[0] if held else None
    yield
    module = sys.modules.get("user_data")
    held = getattr(module, "_HELD", None)
    if held and held[0] is not None and held[0] is not before:
        held[0].close()
        held[0] = None


@pytest.fixture(autouse=True)
def _unresolved_results_refuse_raw_text():
    """A sweep, made lasting: an UnresolvedResult has no
    truth value (its own __bool__ raises), and under the tests it has no
    text either -- str() and format() of one raise, so a value that reaches
    an f-string, a join or a markdown call without _display_result fails at
    the leak instead of printing the dataclass's repr (a wheel crash
    and a Planetary Condition line were both this class). repr is
    left alone for pytest's own output. Patched per test because the engine
    module is reloaded when the environment changes."""
    module = sys.modules.get("engine")
    if module is None:
        import importlib
        module = importlib.import_module("engine")
    cls = module.UnresolvedResult
    had_str, had_format = "__str__" in cls.__dict__, "__format__" in cls.__dict__
    old_str, old_format = cls.__dict__.get("__str__"), cls.__dict__.get("__format__")
    cls.__str__ = _refuse_raw_text
    cls.__format__ = _refuse_raw_text
    yield
    cls = sys.modules["engine"].UnresolvedResult
    for name, had, old in (("__str__", had_str, old_str), ("__format__", had_format, old_format)):
        if had:
            setattr(cls, name, old)
        elif name in cls.__dict__:
            delattr(cls, name)


@pytest.fixture(scope="session")
def engine():
    """engine.py imported as a module, handed over as its namespace (the
    same mapping shape the exec'd half used to return, so the tests that
    index it by name are untouched)."""
    import importlib

    module = importlib.import_module("engine")
    sync_engine_to_environment()
    return vars(module)


@pytest.fixture(autouse=True, scope="session")
def _one_zone_finder_for_the_process():
    """The app builds a TimezoneFinder on every run, which takes about a fifth
    of a second out of a render of about twice that. It does so afresh each
    time because Streamlit runs sessions in threads of one process; a test
    process runs one session at a time. So this process builds one finder, the
    first time anything asks for one, and hands that object to every later
    plain TimezoneFinder(); a construction with arguments, or of a subclass,
    is made as ever. The finder only reads its data, so what a lookup answers
    is unchanged."""
    import timezonefinder

    cls = timezonefinder.TimezoneFinder
    made = []
    original_init = cls.__init__
    had_own_new = "__new__" in cls.__dict__
    original_new = cls.__dict__.get("__new__")

    def __new__(klass, *args, **kwargs):
        if klass is not cls or args or kwargs:
            return object.__new__(klass)
        if not made:
            made.append(object.__new__(cls))
            original_init(made[0])
        return made[0]

    def __init__(self, *args, **kwargs):
        if not (made and self is made[0]):
            original_init(self, *args, **kwargs)

    cls.__new__, cls.__init__ = __new__, __init__
    try:
        yield
    finally:
        cls.__init__ = original_init
        if had_own_new:
            cls.__new__ = original_new
        else:
            del cls.__new__


# --- The shipped atlas, read once; a small atlas made from it, to damage ---------------

SHIPPED_ATLAS = EXECUTABLE_DIR / "atlas.db"
# Every text a test looks up in a copy of the small atlas. The small atlas
# holds every place each of them finds in the shipped one, and answers each
# exactly as the shipped one does (small_atlas checks it).
SMALL_ATLAS_TEXTS = ("Florence", "London", "Hekou", "\u00e9vora")
# Places a test changes by their id in a copy of the small atlas: Florence, London.
SMALL_ATLAS_IDS = (3176959, 2643743)
SMALL_ATLAS_FIRST_ROWS = 2000

ShippedAtlas = namedtuple("ShippedAtlas", "path sha256 size head")
SmallAtlas = namedtuple("SmallAtlas", "path sha256")


@pytest.fixture(scope="session")
def shipped_atlas():
    """The shipped atlas read whole once in this test process, in blocks: its
    path, SHA-256, size and first 4,096 bytes. A test that needs the file's
    own digest or first bytes takes them from here and never reads the file
    itself. Computed here, not by the program's own check of the atlas,
    which is what several of those tests hold to the recorded digest."""
    import hashlib
    digest, size, head = hashlib.sha256(), 0, b""
    with open(SHIPPED_ATLAS, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            if not size:
                head = block[:4096]
            digest.update(block)
            size += len(block)
    return ShippedAtlas(SHIPPED_ATLAS, digest.hexdigest(), size, head)


def _small_atlas_recorded(monkeypatch, small):
    """time_zones with `small`'s SHA-256 as the atlas recorded, and empty
    records of its checks and of its name tables, until `monkeypatch` is
    undone."""
    import time_zones
    monkeypatch.setitem(time_zones.SHIPPED_DATA_SHA256, "atlas.db", small.sha256)
    monkeypatch.setattr(time_zones, "_ATLAS_SEEN", {})
    monkeypatch.setattr(time_zones, "ATLAS_FOLDED_NAMES", {})


@pytest.fixture(scope="session")
def small_atlas(tmp_path_factory, shipped_atlas):
    """An atlas of a few thousand places, made once in this test process
    from the shipped one by SQLite, not by a copy of its bytes, and only
    from the recorded file: a shipped atlas whose SHA-256 is not the
    recorded one makes none, so every test on a small copy errors.

    Its places are the shipped atlas's first places by id, the places
    SMALL_ATLAS_IDS names and every place the shipped atlas's own search
    finds for a text of SMALL_ATLAS_TEXTS, as typed or spelled in ASCII,
    with their other names; GeoNames' zones, the country and region name
    tables and the metadata whole. The tables, indexes and view are made by
    the shipped file's own statements, the search's keys by the atlas
    builder's own function over those places alone, and the schema made is
    checked against the shipped one, entry by entry. Every row is read by
    its key or through an index, so the shipped file is not read through.
    The file is read-only: a test damages a copy (small_atlas_copy). Each of
    the texts is then looked up in both atlases by the program's own
    lookup, and the two must answer alike: the shipped one with the
    program's check of the atlas passed by (its bytes are the shipped_atlas
    fixture's and the check's own tests' to read, not this one's), the
    small one recorded in place of the shipped one for its look alone."""
    import contextlib
    import hashlib
    import sqlite3
    import unicodedata

    import build_atlas
    import time_zones

    assert shipped_atlas.path == SHIPPED_ATLAS
    assert shipped_atlas.sha256 == time_zones.SHIPPED_DATA_SHA256["atlas.db"], (
        "the shipped atlas is not the recorded file: no small atlas is made from it")
    path = tmp_path_factory.mktemp("small_atlas") / "atlas.db"
    schema = "SELECT type, name, tbl_name, sql FROM {}sqlite_master ORDER BY rowid"
    # the objects the builder's search function makes itself, and the
    # statistics ANALYZE makes
    made_by_the_builder = {"atlas_keys", "atlas_prefix_results", "atlas_key_range", "atlas_country_range",
                           "atlas_region_range"}
    whole = ("metadata", "geonames_zones", "country_names", "admin1_names")
    with contextlib.closing(sqlite3.connect(path.as_uri(), uri=True)) as small:
        small.execute("PRAGMA trusted_schema = OFF")
        small.execute("ATTACH DATABASE ? AS shipped", (SHIPPED_ATLAS.resolve().as_uri() + "?mode=ro",))
        shipped_schema = small.execute(schema.format("shipped.")).fetchall()
        assert [n for t, n, _tbl, _sql in shipped_schema if t == "view"] == ["cities"], shipped_schema
        statements = [(t, n, sql) for t, n, _tbl, sql in shipped_schema
                      if sql is not None and n not in made_by_the_builder and not n.startswith("sqlite_")]
        assert {n for t, n, _sql in statements if t == "table"} == {"places", "names", *whole}, statements
        ids = {gid for (gid,) in small.execute(
            "SELECT geonameid FROM shipped.places ORDER BY geonameid LIMIT ?", (SMALL_ATLAS_FIRST_ROWS,))}
        ids.update(SMALL_ATLAS_IDS)
        with contextlib.closing(sqlite3.connect(SHIPPED_ATLAS.resolve().as_uri() + "?mode=ro", uri=True)) as shipped, \
                pytest.MonkeyPatch.context() as patch:
            shipped.execute("PRAGMA trusted_schema = OFF")
            patch.setattr(time_zones, "ATLAS_FOLDED_NAMES", {})
            for text in SMALL_ATLAS_TEXTS:
                spelled = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
                for typed in {text, spelled}:
                    found = time_zones._atlas_search_matches(shipped.cursor(), typed)
                    assert found, typed
                    ids.update(row["geonameid"] for row in found)
        # made in the shipped file's order: VACUUM keeps the tables in the
        # order they were made, then the indexes in theirs
        builder_at = next(i for i, (_t, n, *_r) in enumerate(shipped_schema) if n in made_by_the_builder)
        first = {n for _t, n, *_r in shipped_schema[:builder_at]}
        for kind, name, sql in statements:
            if kind == "index" or (kind == "table" and name in first):
                small.execute(sql)
        marks = ", ".join("?" * len(ids))
        small.execute(f"INSERT INTO main.places SELECT * FROM shipped.places WHERE geonameid IN ({marks})",
                      sorted(ids))
        small.execute(f"INSERT INTO main.names SELECT * FROM shipped.names WHERE geonameid IN ({marks}) "
                      "ORDER BY rowid", sorted(ids))
        small.execute('INSERT INTO main.geonames_zones SELECT * FROM shipped.geonames_zones')
        small.commit()
        build_atlas.build_app_search(small)
        for kind, name, sql in statements:
            if kind == "view" or (kind == "table" and name not in first):
                small.execute(sql)
        for table in whole:
            if table != "geonames_zones":
                small.execute(f'INSERT INTO main."{table}" SELECT * FROM shipped."{table}"')
        small.commit()
        small.execute("DETACH DATABASE shipped")
        small.commit()
        small.execute("VACUUM")
        small.execute("ANALYZE")
        small.commit()
        assert small.execute(schema.format("")).fetchall() == shipped_schema, (
            "the small atlas's tables, views and indexes are not the shipped atlas's")
        assert small.execute("SELECT COUNT(*) FROM places").fetchone()[0] == len(ids)
    path.chmod(0o444)
    with open(path, "rb") as f:
        made = SmallAtlas(path, hashlib.sha256(f.read()).hexdigest())
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(time_zones, "_atlas_checked", lambda db_path: None)
        patch.setattr(time_zones, "ATLAS_FOLDED_NAMES", {})
        shipped = {text: time_zones.atlas_rows(SHIPPED_ATLAS, text) for text in SMALL_ATLAS_TEXTS}
    with pytest.MonkeyPatch.context() as patch:
        _small_atlas_recorded(patch, made)
        answered = {text: time_zones.atlas_rows(path, text) for text in SMALL_ATLAS_TEXTS}
    assert all(shipped.values()) and answered == shipped, "the small atlas answers as the shipped one does"
    return made


@pytest.fixture
def small_atlas_recorded(small_atlas, monkeypatch):
    """For this test alone, the program records the small atlas's SHA-256 in
    place of the shipped one's (with empty records of its checks and name
    tables): an undamaged copy of the small atlas passes the program's check
    of the atlas, and a damaged one fails it. No test file does this
    elsewhere; this is the narrowest patch that lets a small copy stand in."""
    _small_atlas_recorded(monkeypatch, small_atlas)
    return small_atlas


def small_atlas_copy(small, path):
    """A writable copy of the small atlas `small` at `path`, its folder made."""
    import shutil
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(small.path, path)
    return path


def function_source(name):
    """Source text of one top-level function in the engine, by AST -- the
    scans around it read source text, not the imported module. Each engine
    module is parsed by itself, so the function is found wherever it lives."""
    for path in engine_files():
        src = path.read_text()
        for node in ast.parse(src).body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(src, node)
    raise LookupError(f"no top-level function {name!r} in the engine half")


def cited_paragraphs(text, lo, hi):
    """Paragraph numbers between lo and hi that appear as trailing
    citations in string literals: '... (83)', '(93, 99)', '(106, 119-123)'.
    Docstrings and comments cite ranges too, so this only reads quoted
    strings."""
    found = set()
    for literal in re.findall(r"""(?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")""", text):
        for group in re.findall(r"\(([^()]*)\)", literal):
            # leading run of numbers: "84; ...", "93, 99", "106, 119-123"
            m = re.match(r"\s*(\d{2,3}(?:\s*[-,;]\s*\d{2,3})*)", group)
            if not m:
                continue
            for n in map(int, re.findall(r"\d+", m.group(1))):
                if lo <= n <= hi:
                    found.add(n)
    return found


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def prose_number(pattern, text=None):
    """The number word captured by `pattern` (one group) in the UI source.
    Fails loudly if the phrase has been reworded, which is the point: a
    prose count and the structure it describes must be updated together."""
    text = ui_source() if text is None else text
    m = re.search(pattern, text)
    assert m, f"prose phrase not found in the UI source: /{pattern}/ -- reworded? update the test with it"
    word = m.group(1).lower()
    return NUMBER_WORDS.get(word) if word in NUMBER_WORDS else int(word)


# What the program writes, each entry read and none able to fetch or run. Collected by
# running it: reports at both reading depths; saved and live pictures of every kind,
# light and dark, at the pole and with the division withheld. `fetches_nothing` says how to add one.
WRITTEN_TAGS = frozenset((
    "body", "circle", "details", "div", "footer", "g", "h1", "h2", "h3", "head", "html", "line", "main", "meta", "p",
    "path", "polygon", "rect", "style", "summary", "svg", "table", "tbody", "td", "text", "th", "thead", "title", "tr",
))
WRITTEN_ATTRIBUTES = frozenset((
    "charset", "class", "content", "cx", "cy", "d", "data-arc", "data-aspect", "data-chart", "data-distributor",
    "data-end", "data-from", "data-lon", "data-now", "data-partner", "data-point", "data-ring", "data-sign",
    "data-start", "data-target", "data-to", "dominant-baseline", "fill", "font-size", "font-weight", "height", "lang",
    "media", "name", "paint-order", "points", "r", "rx", "stroke", "stroke-dasharray", "stroke-linejoin", "stroke-width", "style", "text-anchor",
    "transform", "viewbox", "width", "x", "x1", "x2", "xmlns", "y", "y1", "y2",
))  # `media` alone is no output's: the pins read a stylesheet behind it, and it fetches nothing.
WRITTEN_FUNCTIONS = frozenset(("not", "nth-child", "var"))
WRITTEN_AT_RULES = frozenset(("font-face", "media"))


def fetches_nothing(text):
    """Raises unless `text`, a report or a saved picture, holds only what the program writes,
    so that nothing in it can fetch or run. It is read as a browser reads it, by a parser: tags,
    attributes and stylesheets, never the text between tags, which is only ever shown, so an
    escaped hostile name passes whatever it says. A new tag, attribute, function or @rule fails
    here by name; whoever adds one reads it, and if it can neither fetch nor run, adds it to its
    sorted set above. A font held in the file, in the one form the app writes, is all a url() may hold."""
    import html as _html

    def read_sheet(css):
        for sheet in (css, _html.unescape(css)):    # a browser decodes entities in an SVG <style>
            rest = re.sub(r"url\(data:font/woff2;base64,[A-Za-z0-9+/=]+\) format\('woff2'\)", "", sheet).lower()
            assert "\\" not in rest, "an escape in a stylesheet"
            assert "<" not in rest, "a tag in a stylesheet, which is markup inside an <svg>"
            assert not re.search(r"\bsrc\s*:\s*[^\s;}]", rest), "a font's source other than the one form"
            for name in re.findall(r"([\w-]+)\(", rest):
                assert name in WRITTEN_FUNCTIONS, f"the stylesheet function {name}("
            for name in re.findall(r"@([\w-]*)", rest):
                assert name in WRITTEN_AT_RULES, f"the stylesheet rule @{name}"

    class Reader(HTMLParser):
        RCDATA_CONTENT_ELEMENTS = ()    # a <title> inside an <svg> holds markup, so read it for tags
        in_sheet = False
        in_title = False
        def handle_starttag(self, tag, attrs):
            assert tag in WRITTEN_TAGS, f"the tag <{tag}>"
            assert not self.in_title, "a tag inside a <title>"
            self.in_title = tag == "title"
            self.in_sheet = tag == "style"
            for name, value in attrs:
                assert name in WRITTEN_ATTRIBUTES, f"the attribute {name} on <{tag}>"
                value = value or ""
                assert name != "charset" or value == "utf-8", "a charset other than the one"
                if (name, value) != ("xmlns", "http://www.w3.org/2000/svg"):
                    for held in ("url(", "//", "\\"):   # \ too: fill and its like are read as a stylesheet
                        assert held not in value.lower(), f"{held} in the attribute {name}"
                if name == "style":
                    read_sheet(value)
        def handle_startendtag(self, tag, attrs):
            assert tag != "style", "<style/>, which a browser does not close"
            self.handle_starttag(tag, attrs)
        def handle_endtag(self, tag):
            self.in_sheet = False
            assert not self.in_title or tag == "title", "a tag inside a <title>"
            self.in_title = False
        def handle_data(self, data):
            if self.in_sheet:
                read_sheet(data)
        def handle_decl(self, decl):
            assert decl == "doctype html", f"the declaration, comment or instruction {decl}"
        handle_pi = handle_comment = unknown_decl = handle_decl

    reader = Reader(convert_charrefs=True)
    reader.feed(text)
    reader.close()
    assert not reader.in_sheet, "a stylesheet never closed"
