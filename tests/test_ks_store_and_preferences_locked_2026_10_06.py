"""Two writers at once on the saved charts and the preferences (lane KS, ruling 63).

Sol's second pass (HP2-01..03) found three races, each reproduced with its
ordering forced (``HP2_REPRODUCTION.md`` in the corpus' records):

- HP2-01: every write of one file went through one temporary name,
  ``<file>.tmp``. Two writes in flight shared it: the one that reported
  success had installed the other's bytes, and the one whose bytes were
  installed reported a failure.
- HP2-02: a save read the store, merged its record and wrote, holding
  nothing across the three steps; another window's save landing between
  this window's read and its write was written over, and both windows said
  "Saved". A delete has the same shape.
- HP2-03: ``remember_preference`` and ``forget_preference`` read the file,
  changed one key and wrote the whole file, with nothing held; another
  window's key set in between was lost, and both calls returned True.

Every ordering here is forced by events at the real calls (``os.replace``
in the atomic writer, ``engine.write_saved_charts``,
``engine.write_preferences``): one writer is held at its write while the
other runs to its end, or until it is seen waiting on the lock. Nothing
sleeps and nothing hopes for a schedule. The sign that the second writer is
waiting comes from the lock itself: in one process a stand-in for the
engine's thread lock, which says so before it blocks; across processes a
wrapper on ``fcntl.flock`` in the waiting process, which tries without
blocking first and says so when that is refused. Before the fix neither is
ever reached, so the second writer runs to its end and the first then
writes over it -- the failure each test asserts against. Every wait is
bounded (``WAIT``), so a lock that never comes free fails the test rather
than hanging the suite. The sixteen cases under the three findings' headings
were strict xfails, each failing at e14fc9d, before the fix.

The guards at the end hold what the fix must not cost: KA's link and mode,
a first file's mode, no lock file left in the folder or named on the page, a
folder the account cannot write in (the folder's sentence, no hang), a
system with no file lock, and the removed-lock-file hand-over.
"""
import errno
import json
import os
import queue
import stat
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

REPO = Path(APP_PATH).resolve().parent
TESTS = REPO / "tests"
WAIT = 120            # seconds: the bound on every wait for another writer or window
APP_WAIT = 600        # seconds: the bound on a child process's launch of a window

LMT = "LMT (Local Mean Time)"
REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
XY = {"X": REC, "Y": dict(REC, date_string="1990-01-01")}
A_CHARTS = dict(XY, A=dict(REC, date_string="1901-02-03"))
B_CHARTS = dict(XY, B=dict(REC, date_string="1999-12-31"))
A_PREFS = {"_wheel_dark": True}
B_PREFS = {"_launches": 7}
HOME = {"label": "Florence", "lat": 43.7792, "lon": 11.2463}
FIRST_PREFS = {"_launches": 3, "last_chart": "X"}


# =============================================================================
# Harness
# =============================================================================

def _engine():
    sync_engine_to_environment()
    import engine
    return engine


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable data folder; preferences off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    _engine()
    return tmp_path


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    """A disposable data folder with the preferences file live."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    _engine()
    return tmp_path


def _text(what, value):
    """The bytes the engine's writer writes for `value`."""
    if what == "charts":
        return json.dumps(value, indent=2).encode("utf-8")
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8")


def _target(engine, what):
    return engine.SAVED_CHARTS_PATH if what == "charts" else engine.PREFERENCES_PATH


def _write(engine, what, value):
    return (engine.write_saved_charts if what == "charts" else engine.write_preferences)(value)


class _Thread:
    """A daemon thread running `fn`, its result or exception kept; joined
    within WAIT."""

    def __init__(self, fn, name):
        self.result, self.error, self.done = None, None, threading.Event()
        self.thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)
        self.thread.start()

    def _run(self, fn):
        try:
            self.result = fn()
        except BaseException as exc:            # kept and re-raised by join()
            self.error = exc
        finally:
            self.done.set()

    def join(self):
        self.thread.join(WAIT)
        assert not self.thread.is_alive(), f"{self.thread.name} did not finish within {WAIT}s"
        if self.error is not None:
            raise self.error
        return self.result


class _SignallingLock:
    """Stands in for one of the engine's thread locks. A caller that finds it
    held sets `waiting` before it blocks (the sign that it is waiting on the
    lock); once that caller has the lock, it waits for `then`, when given,
    before it goes on. A thread `exempt` names takes the lock plainly."""

    def __init__(self, real, waiting, then=None, on_wait=None, exempt=lambda: False):
        self._real, self._waiting, self._then, self._on_wait = real, waiting, then, on_wait
        self._exempt = exempt

    def acquire(self, blocking=True, timeout=-1):
        if self._exempt():
            return self._real.acquire(blocking, timeout)
        if self._real.acquire(False):
            return True
        if self._on_wait is not None:
            self._on_wait()
        self._waiting.set()
        got = self._real.acquire(blocking, timeout)
        if got and self._then is not None:
            assert self._then.wait(WAIT), "the test never let the waiting writer go on"
        return got

    def release(self):
        self._real.release()

    def locked(self):
        return self._real.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def _signal_on_thread_lock(monkeypatch, engine, name, waiting, then=None, on_wait=None, exempt=lambda: False):
    """Put a _SignallingLock in the place of the engine's thread lock `name`
    (a fresh lock where the engine has none: before the fix nothing takes it)."""
    real = getattr(engine, name, None) or threading.Lock()
    monkeypatch.setattr(engine, name, _SignallingLock(real, waiting, then, on_wait, exempt), raising=False)


# A child process: one writer, or one window, of its own, on the data folder
# the test names. It speaks one JSON object per line on stdout and takes one
# word per line on stdin. In every child a blocking fcntl.flock is first
# tried without blocking, and "waiting" is said when that is refused.
CHILD = textwrap.dedent("""
    import json, os, sys
    sys.path[:0] = [{tests!r}, {repo!r}]
    job = json.loads(sys.argv[1])

    def say(**kw):
        print(json.dumps(kw), flush=True)

    def hear():
        line = sys.stdin.readline()
        if not line:
            raise SystemExit("the test went away")
        return line.strip()

    try:
        import fcntl
    except ImportError:
        fcntl = None
    # "waiting" is said the first time a lock is refused (once a process; in a
    # contender with "hold", once for each file it waits on before it next
    # gets a lock: the record is cleared when it gets one, so that a later
    # lock file that happens to take a removed file's inode number is still
    # reported; "one_inode" files every lock file under one number in this
    # record alone, so that the test can force that reuse); a contender with
    # "hold" also says "got" once it has a file's lock, and goes on only when
    # told. A window ("app") names the engine's functions it was waiting in
    # ("via"), says "waiting" once for each place it waits in (so a launch's
    # wait on another launch's tidying, ruling 119, does not hide a second
    # wait elsewhere), and says it afresh once it has said "ready", so that
    # the launch's waits do not spend the report of the wait the test is about.
    _said = set()

    def _engine_frames():
        import traceback
        return [f.name for f in traceback.extract_stack() if os.path.basename(f.filename) == "engine.py"]

    def _refused(fd):
        if job.get("hold"):
            key = 0 if job.get("one_inode") else os.fstat(fd).st_ino
        else:
            key = tuple(_engine_frames()) if job["kind"] == "app" else "once"
        if key not in _said:
            _said.add(key)
            if job["kind"] == "app":
                say(event="waiting", ino=os.fstat(fd).st_ino, via=_engine_frames())
            else:
                say(event="waiting", ino=os.fstat(fd).st_ino)

    if fcntl is not None:
        _real_flock = fcntl.flock

        def _flock(fd, op):
            if op & fcntl.LOCK_NB:
                try:
                    out = _real_flock(fd, op)
                except BlockingIOError:
                    _refused(fd)
                    raise
            elif op == fcntl.LOCK_EX:
                try:
                    out = _real_flock(fd, op | fcntl.LOCK_NB)
                except BlockingIOError:
                    _refused(fd)
                    out = _real_flock(fd, op)
            else:
                return _real_flock(fd, op)
            if job.get("hold"):
                _said.clear()
                say(event="got", ino=os.fstat(fd).st_ino)
                hear()
            return out
        fcntl.flock = _flock

    if job["kind"] == "holder":
        fd = os.open(job["path"], os.O_RDWR | os.O_CREAT, 0o666)
        _real_flock(fd, fcntl.LOCK_EX)
        say(event="held", pid=os.getpid())
        hear()
        raise SystemExit(0)

    if job["kind"] == "contender":
        import engine
        engine.LOCK_WAIT_SECONDS = job["bound"]
        held = dict()
        _real_take = engine._take_file_lock

        def _take(*args, **kwargs):
            held["fd"] = _real_take(*args, **kwargs)
            return held["fd"]
        engine._take_file_lock = _take
        lock_path = engine.SAVED_CHARTS_PATH.parent / "saved_charts.lock"
        say(event="ready")
        while hear() == "take":
            with engine.saved_charts_lock():
                fd = held.get("fd")
                try:
                    named = os.stat(lock_path).st_ino
                except OSError:
                    named = None
                say(event="in", ino=os.fstat(fd).st_ino if fd is not None else None, named=named)
                hear()
            say(event="out")
        raise SystemExit(0)

    if job["kind"] == "app":
        import conftest
        at = conftest.make_app(date=job["date"], page="sources", timeout={app_wait})
        at.run()
        import engine
        if job.get("name"):
            [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(job["name"]).run()
        if job.get("held"):
            real_write = engine.write_saved_charts
            first = []

            def gated(charts):
                if not first:
                    first.append(1)
                    say(event="at-write")
                    hear()
                return real_write(charts)
            engine.write_saved_charts = gated
        _said.clear()
        say(event="ready", picker=list(at.sidebar.selectbox(key="chart_picker").options))
        hear()
        [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
        shown = [e.value for kind in ("error", "warning", "success") for e in getattr(at.sidebar, kind)]
        say(event="result", shown=shown, picker=list(at.sidebar.selectbox(key="chart_picker").options),
            exceptions=[str(e.value) for e in at.exception])
    else:
        import engine
        what = job["what"]
        if job["kind"] == "write":
            target = engine.SAVED_CHARTS_PATH if what == "charts" else engine.PREFERENCES_PATH
            mine = (json.dumps(job["value"], indent=2) if what == "charts"
                    else json.dumps(job["value"], indent=2, sort_keys=True)).encode("utf-8")
            moved = []
            real_replace = os.replace

            def gated_replace(src, dst, *a, **k):
                say(event="at-replace")
                hear()
                try:
                    with open(src, "rb") as f:
                        moved.append(f.read() == mine)
                except OSError:
                    moved.append(None)
                return real_replace(src, dst, *a, **k)
            os.replace = gated_replace
            say(event="ready")
            hear()
            ok = engine.write_saved_charts(job["value"]) if what == "charts" else engine.write_preferences(job["value"])
            say(event="result", ok=ok, moved_own=moved)
        else:
            if job.get("held"):
                real_write = engine.write_preferences

                def gated_prefs(prefs):
                    say(event="at-write")
                    hear()
                    return real_write(prefs)
                engine.write_preferences = gated_prefs
            say(event="ready")
            hear()
            if job["op"] == "remember":
                ok = engine.remember_preference(job["key"], job["value"])
            else:
                ok = engine.forget_preference(job["key"])
            say(event="result", ok=ok)
""").format(tests=str(TESTS), repo=str(REPO), app_wait=APP_WAIT)


class _Child:
    """One child process running CHILD for `job`, its lines read by a
    thread of its own so that every read is bounded."""

    def __init__(self, job, env, log):
        self.log = log
        self._err = open(log, "w")
        self.proc = subprocess.Popen([sys.executable, "-c", CHILD, json.dumps(job)], env=env, cwd=str(REPO),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err,
                                     text=True)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(json.loads(line))
        self.lines.put(None)

    def expect(self, *events, timeout=WAIT):
        try:
            msg = self.lines.get(timeout=timeout)
        except queue.Empty:
            msg = "nothing"
        if msg is None or msg == "nothing" or msg["event"] not in events:
            self._err.flush()
            raise AssertionError(f"expected {events} from the child, got {msg}; its stderr ends "
                                 f"{Path(self.log).read_text()[-2000:]}")
        return msg

    def tell(self, word="go"):
        self.proc.stdin.write(word + "\n")
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=WAIT)
        except subprocess.TimeoutExpired:
            self.proc.kill()            # this test's own child, by its own handle
            self.proc.wait(timeout=WAIT)
        self._err.close()


def _children_env(tmp_path, prefs):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path)}
    if prefs:
        env.pop("ALMUTEN_NO_PREFERENCES", None)
    else:
        env["ALMUTEN_NO_PREFERENCES"] = "1"
    return env


# =============================================================================
# HP2-01: each write its own temporary name
# =============================================================================

@pytest.mark.parametrize("what", ["charts", "prefs"])
def test_hp2_01_two_writes_of_one_file_take_two_temporary_names(prefs_on, monkeypatch, what):
    engine = _engine()
    moved = []
    real_replace = os.replace

    def recording(src, dst, *a, **k):
        moved.append(Path(src))
        return real_replace(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", recording)
    assert _write(engine, what, A_CHARTS if what == "charts" else A_PREFS) is True
    assert _write(engine, what, B_CHARTS if what == "charts" else B_PREFS) is True
    target = _target(engine, what)
    assert len(moved) == 2 and all(p.parent == target.parent for p in moved), moved
    assert moved[0] != moved[1], f"both writes went through one temporary name, {moved[0].name}"


@pytest.mark.parametrize("what", ["charts", "prefs"])
def test_hp2_01_a_write_in_flight_is_not_robbed_by_a_second(prefs_on, monkeypatch, what):
    """A has written its temporary file and is at its replace when B's whole
    write runs (in the same thread, so nothing is left to the scheduler);
    then A's replace goes on. A's bytes must be what A installs."""
    engine = _engine()
    a_value, b_value = (A_CHARTS, B_CHARTS) if what == "charts" else (A_PREFS, B_PREFS)
    real_replace = os.replace
    b_result = []
    started = []

    def b_first(src, dst, *a, **k):
        if not started:
            started.append("B")
            b_result.append(_write(engine, what, b_value))
        return real_replace(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", b_first)
    a_ok = _write(engine, what, a_value)
    monkeypatch.setattr(os, "replace", real_replace)
    assert b_result == [True], f"B's write, made while A's was in flight, returned {b_result}"
    assert a_ok is True, "A's write returned False: its temporary file was taken by B's"
    assert _target(engine, what).read_bytes() == _text(what, a_value), "the file does not hold A's bytes, written last"
    assert list(_target(engine, what).parent.glob("*.tmp")) == [], "a temporary file was left behind"


def _overlapping_writes_in_threads(engine, what, a_value, b_value):
    """A writes its temporary file and stops at its replace; B writes its own
    and stops at its replace; A replaces; B replaces. Each replace records
    whether the bytes it moved were its own writer's."""
    ev = {k: threading.Event() for k in ("A_at", "B_at", "A_done")}
    mine = {"A": _text(what, a_value), "B": _text(what, b_value)}
    moved = {"A": [], "B": []}
    real_replace = os.replace

    def gated(src, dst, *a, **k):
        who = threading.current_thread().name
        if who not in mine:
            return real_replace(src, dst, *a, **k)
        if who == "A":
            ev["A_at"].set()
            assert ev["B_at"].wait(WAIT), "B never reached its replace"
        else:
            ev["B_at"].set()
            assert ev["A_done"].wait(WAIT), "A never replaced"
        try:
            moved[who].append(Path(src).read_bytes() == mine[who])
        except OSError:
            moved[who].append(None)
        try:
            return real_replace(src, dst, *a, **k)
        finally:
            if who == "A":
                ev["A_done"].set()
    return ev, moved, gated


@pytest.mark.parametrize("what", ["charts", "prefs"])
def test_hp2_01_overlapping_writers_in_threads_each_install_their_own_bytes(prefs_on, monkeypatch, what):
    engine = _engine()
    a_value, b_value = (A_CHARTS, B_CHARTS) if what == "charts" else (A_PREFS, B_PREFS)
    ev, moved, gated = _overlapping_writes_in_threads(engine, what, a_value, b_value)
    monkeypatch.setattr(os, "replace", gated)
    a = _Thread(lambda: _write(engine, what, a_value), "A")
    assert ev["A_at"].wait(WAIT), "A never reached its replace"
    b = _Thread(lambda: _write(engine, what, b_value), "B")
    results = {"A": a.join(), "B": b.join()}
    assert results == {"A": True, "B": True}, f"the writers returned {results}"
    assert moved == {"A": [True], "B": [True]}, f"whose bytes each replace moved (True: its own): {moved}"
    assert _target(engine, what).read_bytes() == _text(what, b_value), "the file does not hold B's bytes, written last"


@pytest.mark.parametrize("what", ["charts", "prefs"])
def test_hp2_01_overlapping_writers_in_two_processes_each_install_their_own_bytes(prefs_on, tmp_path, what):
    engine = _engine()
    a_value, b_value = (A_CHARTS, B_CHARTS) if what == "charts" else (A_PREFS, B_PREFS)
    env = _children_env(tmp_path, prefs=True)
    a = _Child({"kind": "write", "what": what, "value": a_value}, env, tmp_path / "a.log")
    b = _Child({"kind": "write", "what": what, "value": b_value}, env, tmp_path / "b.log")
    try:
        a.expect("ready", timeout=APP_WAIT)
        b.expect("ready", timeout=APP_WAIT)
        a.tell("write")
        a.expect("at-replace")
        b.tell("write")
        b.expect("at-replace")
        a.tell()
        got_a = a.expect("result")
        b.tell()
        got_b = b.expect("result")
    finally:
        a.close()
        b.close()
    results = {"A": (got_a["ok"], got_a["moved_own"]), "B": (got_b["ok"], got_b["moved_own"])}
    assert results == {"A": (True, [True]), "B": (True, [True])}, (
        f"(returned, whose bytes each replace moved -- True: its own) {results}")
    assert _target(engine, what).read_bytes() == _text(what, b_value), "the file does not hold B's bytes, written last"


# =============================================================================
# HP2-02: the store's read, merge and write under one lock
# =============================================================================

def _store(engine):
    return engine.SAVED_CHARTS_PATH


def _shown(at):
    return [e.value for kind in ("error", "warning", "success") for e in getattr(at.sidebar, kind)]


def _picker(at):
    return list(at.sidebar.selectbox(key="chart_picker").options)


def _name_box(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()


def _click_save(at):
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()


def _start_delete(at, name):
    """Pick `name` and press the bin; the delete itself is the confirm's run."""
    at.sidebar.selectbox(key="chart_picker").select(name).run()
    [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()


def _confirm_delete(at):
    at.sidebar.button(key="_delete_confirm").click().run()


def _two_windows(monkeypatch, gate_name, lock_name, a_act, b_act):
    """Window A's action `a_act` is held at its first call of the engine's
    `gate_name` (its read of the file done) while window B's `b_act` runs in
    a thread of its own, until B has finished or is waiting on the engine's
    thread lock `lock_name`; then A goes on. A waiting B is held, once it has
    the lock, until A's run is over, so the two windows' runs never cross
    in Streamlit's test harness (whose runs each set and clear one global
    runtime). Returns whether B was seen waiting."""
    from streamlit import config
    from streamlit.runtime import Runtime

    engine = sys.modules["engine"]
    real_gate = getattr(engine, gate_name)
    real_get_option = config.get_option
    out = {"B": None, "waited": False}
    b_out_of_the_way, a_over = threading.Event(), threading.Event()

    def b_waits():
        out["waited"] = True
        out["b_runtime"] = Runtime._instance

    # Window A's own script thread takes the lock plainly: only B is held.
    _signal_on_thread_lock(monkeypatch, engine, lock_name, b_out_of_the_way, then=a_over, on_wait=b_waits,
                           exempt=lambda: threading.get_ident() == out.get("a_thread"))

    def held(*args, **kwargs):
        if out["B"] is None:
            out["a_thread"] = threading.get_ident()
            a_runtime = Runtime._instance

            def run_b():
                try:
                    b_act()
                finally:
                    b_out_of_the_way.set()
            out["B"] = _Thread(run_b, "window-B")
            if not b_out_of_the_way.wait(WAIT):
                out["stuck"] = True
            if not out["waited"]:
                Runtime._instance = a_runtime     # B's run, over, cleared the harness's runtime
        return real_gate(*args, **kwargs)

    monkeypatch.setattr(engine, gate_name, held)
    try:
        a_act()
        if out["waited"]:
            Runtime._instance = out["b_runtime"]  # A's run, over, cleared it; B's goes on
        a_over.set()
        assert out["B"] is not None, f"window A never reached {gate_name}"
        assert not out.get("stuck"), f"window B neither finished nor waited on the lock within {WAIT}s"
        out["B"].join()
    finally:
        a_over.set()
        Runtime._instance = None
        config.get_option = real_get_option
    return out["waited"]


def test_hp2_02_a_save_held_at_its_write_keeps_another_windows_save_in_one_process(scratch, monkeypatch):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    b = make_app(date="1990-01-01", page="sources", timeout=300)
    engine = _engine()
    _store(engine).write_text(json.dumps(XY, indent=2))
    a.run()
    b.run()
    _name_box(a, "From A")
    _name_box(b, "From B")
    _two_windows(monkeypatch, "write_saved_charts", "_STORE_THREAD_LOCK", lambda: _click_save(a), lambda: _click_save(b))
    assert_no_exception(a, "window A's save")
    assert_no_exception(b, "window B's save")
    held = json.loads(_store(engine).read_text())
    assert sorted(held) == ["From A", "From B", "X", "Y"], f"the store holds {sorted(held)}"
    assert "Saved 'From A'." in _shown(a), _shown(a)
    assert "Saved 'From B'." in _shown(b), _shown(b)
    assert {"From A", "From B"} <= set(_picker(b)), f"window B's picker: {_picker(b)}"


def test_hp2_02_a_delete_held_at_its_write_keeps_another_windows_save(scratch, monkeypatch):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    b = make_app(date="1990-01-01", page="sources", timeout=300)
    engine = _engine()
    _store(engine).write_text(json.dumps(XY, indent=2))
    a.run()
    b.run()
    _start_delete(a, "Y")
    _name_box(b, "Z")
    _two_windows(monkeypatch, "write_saved_charts", "_STORE_THREAD_LOCK", lambda: _confirm_delete(a), lambda: _click_save(b))
    assert_no_exception(a, "window A's delete")
    assert_no_exception(b, "window B's save")
    held = json.loads(_store(engine).read_text())
    assert sorted(held) == ["X", "Z"], f"the store holds {sorted(held)}: Y deleted by A, Z saved by B"
    assert "Saved 'Z'." in _shown(b), _shown(b)
    assert "Y" not in _picker(a), f"window A's picker: {_picker(a)}"


def _launched(child):
    """The window's "ready", past any "waiting" its launch said first, each
    of which must come from the launch's tidying of the saved charts' strays
    (ruling 119). Two windows launched at once on one folder each list the
    strays under the store's lock, waited on a moment only (SC-03, ruling
    77), so the second may wait on the first before it is ready; that is
    the only wait a launch may make. Anything else before "ready" fails."""
    for _ in range(100):
        msg = child.expect("waiting", "ready", timeout=APP_WAIT)
        if msg["event"] == "ready":
            return msg
        assert "_tidy_stray_temp_files" in msg["via"], f"a launch waited outside its tidying: {msg}"
    raise AssertionError("the window said 'waiting' a hundred times and never 'ready'")


def test_hp2_02_a_save_held_at_its_write_keeps_another_processs_save(scratch, tmp_path):
    engine = _engine()
    _store(engine).write_text(json.dumps(XY, indent=2))
    env = _children_env(tmp_path, prefs=False)
    a = _Child({"kind": "app", "date": "1983-11-19", "name": "From A", "held": True}, env, tmp_path / "a.log")
    b = _Child({"kind": "app", "date": "1990-01-01", "name": "From B"}, env, tmp_path / "b.log")
    try:
        assert _launched(a)["picker"] == ["-- New Chart --", "X", "Y"]
        assert _launched(b)["picker"] == ["-- New Chart --", "X", "Y"]
        a.tell()
        a.expect("at-write", timeout=APP_WAIT)
        b.tell()
        first = b.expect("waiting", "result", timeout=APP_WAIT)
        a.tell()
        got_a = a.expect("result", timeout=APP_WAIT)
        got_b = first if first["event"] == "result" else b.expect("result", timeout=APP_WAIT)
    finally:
        a.close()
        b.close()
    assert got_a["exceptions"] == [] and got_b["exceptions"] == [], (got_a["exceptions"], got_b["exceptions"])
    held = json.loads(_store(engine).read_text())
    assert sorted(held) == ["From A", "From B", "X", "Y"], f"the store holds {sorted(held)}"
    assert "Saved 'From A'." in got_a["shown"], got_a["shown"]
    assert "Saved 'From B'." in got_b["shown"], got_b["shown"]


# =============================================================================
# HP2-03: the preferences' read, change and write under a lock of their own
# =============================================================================

def _prefs_call(engine, op):
    if op == "remember":
        return engine.remember_preference("_wheel_dark", True)
    return engine.forget_preference("last_chart")


def _expected_prefs(op):
    if op == "remember":
        return {"_launches": 3, "last_chart": "X", "_wheel_dark": True, "home_place": HOME}
    return {"_launches": 3, "_wheel_dark": True}


@pytest.mark.parametrize("op", ["remember", "forget"])
def test_hp2_03_a_preference_held_at_its_write_keeps_another_threads_preference(prefs_on, monkeypatch, op):
    """A (remember `_wheel_dark`, or forget `last_chart`) has read the file
    and is held at its write; B remembers another key (`home_place`, or
    `_wheel_dark`) until it has finished or is waiting on the lock."""
    engine = _engine()
    assert engine.write_preferences(FIRST_PREFS)
    b_key, b_value = ("home_place", HOME) if op == "remember" else ("_wheel_dark", True)
    b_out_of_the_way = threading.Event()
    _signal_on_thread_lock(monkeypatch, engine, "_PREFERENCES_THREAD_LOCK", b_out_of_the_way)
    real_write = engine.write_preferences
    out = {}

    def held(prefs):
        if "B" not in out:
            def run_b():
                try:
                    return engine.remember_preference(b_key, b_value)
                finally:
                    b_out_of_the_way.set()
            out["B"] = _Thread(run_b, "B")
            out["in_time"] = b_out_of_the_way.wait(WAIT)
        return real_write(prefs)

    monkeypatch.setattr(engine, "write_preferences", held)
    a_ok = _Thread(lambda: _prefs_call(engine, op), "A").join()
    assert "B" in out and out["in_time"], "B neither finished nor waited on the lock"
    b_ok = out["B"].join()
    assert (a_ok, b_ok) == (True, True), f"A returned {a_ok}, B {b_ok}"
    assert json.loads(engine.PREFERENCES_PATH.read_text()) == _expected_prefs(op), engine.PREFERENCES_PATH.read_text()


@pytest.mark.parametrize("op", ["remember", "forget"])
def test_hp2_03_a_preference_held_at_its_write_keeps_another_processs_preference(prefs_on, tmp_path, op):
    engine = _engine()
    assert engine.write_preferences(FIRST_PREFS)
    b_key, b_value = ("home_place", HOME) if op == "remember" else ("_wheel_dark", True)
    a_job = ({"kind": "prefs", "what": "prefs", "op": "remember", "key": "_wheel_dark", "value": True, "held": True}
             if op == "remember" else {"kind": "prefs", "what": "prefs", "op": "forget", "key": "last_chart", "held": True})
    env = _children_env(tmp_path, prefs=True)
    a = _Child(a_job, env, tmp_path / "a.log")
    b = _Child({"kind": "prefs", "what": "prefs", "op": "remember", "key": b_key, "value": b_value}, env, tmp_path / "b.log")
    try:
        a.expect("ready", timeout=APP_WAIT)
        b.expect("ready", timeout=APP_WAIT)
        a.tell()
        a.expect("at-write")
        b.tell()
        first = b.expect("waiting", "result")
        a.tell()
        got_a = a.expect("result")
        got_b = first if first["event"] == "result" else b.expect("result")
    finally:
        a.close()
        b.close()
    assert (got_a["ok"], got_b["ok"]) == (True, True), (got_a, got_b)
    assert json.loads(engine.PREFERENCES_PATH.read_text()) == _expected_prefs(op), engine.PREFERENCES_PATH.read_text()


def test_hp2_03_a_dark_wheel_held_at_its_write_keeps_another_windows_home(prefs_on, monkeypatch):
    a = make_app(date="1983-11-19", page="chart", timeout=300)
    b = make_app(date="1990-01-01", page="chart", timeout=300)
    engine = _engine()
    a.run()
    b.run()
    box = [c for c in a.main.checkbox if c.label == "Dark wheel"]
    assert len(box) == 1 and box[0].value is False, "the premise: one Dark wheel box, unticked"

    def tick():
        [c for c in a.main.checkbox if c.label == "Dark wheel"][0].check().run()

    def set_home():
        b.sidebar.button(key="_set_home").click().run()
    _two_windows(monkeypatch, "write_preferences", "_PREFERENCES_THREAD_LOCK", tick, set_home)
    assert_no_exception(a, "window A's tick")
    assert_no_exception(b, "window B's Set as home")
    held = json.loads(engine.PREFERENCES_PATH.read_text())
    assert held.get("_wheel_dark") is True, f"the file lost A's dark wheel: {held}"
    assert engine.home_place_is_valid(held.get("home_place")), f"the file lost B's home: {held}"


# =============================================================================
# Guards: what the fix must not cost
# =============================================================================

def _folder(engine):
    return sorted(p.name for p in engine.DATA_DIR.iterdir())


def test_a_first_file_takes_the_mode_a_plain_write_gives_it(scratch):
    """Rulings 150 and 157 (C-03, D-05) replace what this guard first held
    (0o666 under the account's umask, as write_bytes gave it): a first-ever
    file is made owner-only, 0600, under the usual umask as under any."""
    engine = _engine()
    previous = os.umask(0o022)
    try:
        assert engine.write_saved_charts(XY) is True
    finally:
        os.umask(previous)
    assert stat.S_IMODE(os.stat(engine.SAVED_CHARTS_PATH).st_mode) == 0o600
    assert _folder(engine) == ["saved_charts.json"], _folder(engine)


def test_a_temporary_name_already_there_is_never_opened(scratch, monkeypatch):
    """O_CREAT|O_EXCL: a file standing under the name a write draws is
    another writer's, and is neither written into nor removed."""
    engine = _engine()
    names = iter(["taken", "free"])
    monkeypatch.setattr(engine.secrets, "token_hex", lambda n: next(names))
    other = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.taken.tmp")
    other.write_bytes(b"another writer's bytes")
    assert engine.write_saved_charts(XY) is True
    assert other.read_bytes() == b"another writer's bytes", "a temp file already there was written into"
    assert _folder(engine) == ["saved_charts.json", "saved_charts.json.taken.tmp"], _folder(engine)


def test_the_lock_file_lives_in_the_data_folder_only_while_held(scratch):
    engine = _engine()
    with engine.saved_charts_lock():
        assert "saved_charts.lock" in _folder(engine), _folder(engine)
        with engine.preferences_lock():
            assert {"saved_charts.lock", "preferences.lock"} <= set(_folder(engine)), _folder(engine)
    assert _folder(engine) == [], f"a lock file was left in the folder: {_folder(engine)}"


def test_a_save_a_delete_and_a_preference_leave_no_lock_file_and_name_none(prefs_on):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    a.run()
    _name_box(a, "Z")
    _click_save(a)
    assert json.loads(engine.PREFERENCES_PATH.read_text()).get("last_chart") == "Z", (
        "the save, holding the store's lock, did not remember its chart")
    _start_delete(a, "Y")
    _confirm_delete(a)
    assert_no_exception(a, "the save and the delete")
    assert sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == ["X", "Z"]
    assert "last_chart" not in json.loads(engine.PREFERENCES_PATH.read_text()), (
        "the delete of the chart last opened did not forget it")
    assert _picker(a) == ["-- New Chart --", "X", "Z"], _picker(a)
    assert _folder(engine) == ["preferences.json", "saved_charts.json"], _folder(engine)
    page = [e.value for kind in ("error", "warning", "info", "success", "caption", "markdown")
            for e in getattr(a.sidebar, kind)]
    assert page and not any(".lock" in v for v in page), [v for v in page if ".lock" in v]


def test_a_folder_that_cannot_be_written_in_gives_its_sentence_and_no_hang(scratch):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    a.run()
    engine.DATA_DIR.chmod(0o555)
    try:
        assert os.access(engine.DATA_DIR, os.R_OK) and not os.access(engine.DATA_DIR, os.W_OK), (
            "the premise: a folder this account can read and not write in")
        with engine.saved_charts_lock():
            pass                                  # the thread lock alone: no file could be made
        _name_box(a, "Z")
        _click_save(a)
        assert_no_exception(a, "Save in a folder that cannot be written in")
        _start_delete(a, "Y")
        _confirm_delete(a)
        assert_no_exception(a, "a delete in a folder that cannot be written in")
        shown = _shown(a)
        assert any(v.startswith("Saved charts and preferences cannot be kept: their folder")
                   and "cannot be written in" in v for v in shown), shown
        assert [v for v in shown if ".lock" in v] == [], shown
        assert engine.SAVED_CHARTS_PATH.read_text() == json.dumps(XY, indent=2), "the store moved"
        assert _folder(engine) == ["saved_charts.json"], _folder(engine)
    finally:
        engine.DATA_DIR.chmod(0o755)


def test_a_preference_in_a_folder_that_cannot_be_written_in_returns_false(prefs_on):
    engine = _engine()
    assert engine.write_preferences(FIRST_PREFS)
    engine.DATA_DIR.chmod(0o555)
    try:
        done = _Thread(lambda: (engine.remember_preference("_wheel_dark", True),
                                engine.forget_preference("last_chart")), "prefs").join()
    finally:
        engine.DATA_DIR.chmod(0o755)
    assert done == (False, False), done
    assert json.loads(engine.PREFERENCES_PATH.read_text()) == FIRST_PREFS
    assert _folder(engine) == ["preferences.json"], _folder(engine)


@pytest.mark.parametrize("which", ["store", "preferences"])
def test_with_no_file_lock_the_thread_lock_alone_still_holds_the_threads(prefs_on, monkeypatch, which):
    """Where neither fcntl nor msvcrt is to be had, the thread lock alone
    serialises one server's windows: B, waiting on it, runs only after A's
    read, change and write are over."""
    engine = _engine()
    monkeypatch.setattr(engine, "fcntl", None)
    monkeypatch.setattr(engine, "msvcrt", None)
    lock = engine.saved_charts_lock if which == "store" else engine.preferences_lock
    name = "_STORE_THREAD_LOCK" if which == "store" else "_PREFERENCES_THREAD_LOCK"
    b_waiting, a_holding = threading.Event(), threading.Event()
    _signal_on_thread_lock(monkeypatch, engine, name, b_waiting)
    order = []

    def a():
        with lock():
            a_holding.set()
            assert b_waiting.wait(WAIT), "B never waited on the lock"
            assert _folder(engine) == [], f"a lock file was made with no lock call to take it: {_folder(engine)}"
            order.append("A done")

    def b():
        assert a_holding.wait(WAIT), "A never took the lock"
        with lock():
            order.append("B in")

    ta, tb = _Thread(a, "A"), _Thread(b, "B")
    ta.join()
    tb.join()
    assert order == ["A done", "B in"], order


def test_a_writer_waiting_on_a_removed_lock_file_takes_the_one_in_its_place(scratch, monkeypatch):
    """The holder removes the lock file before it lets go. A writer that was
    waiting on that file gets it, finds the name no longer leads to it, and
    locks the file under the name instead -- so that a third writer, coming
    to the name after, is refused while the second holds it."""
    import fcntl                          # the suite runs where flock is (Linux, macOS)
    engine = _engine()
    path = engine.DATA_DIR / "saved_charts.lock"
    b_waiting = threading.Event()
    real_flock = fcntl.flock

    def flock(fd, op):
        if threading.current_thread().name == "B":
            try:
                return real_flock(fd, op | fcntl.LOCK_NB)
            except BlockingIOError:
                b_waiting.set()
                if op & fcntl.LOCK_NB:
                    raise
        return real_flock(fd, op)
    monkeypatch.setattr(fcntl, "flock", flock)
    a_fd = engine._take_file_lock(path)
    # A descriptor of A's file kept open (no lock on it) to the end, so that
    # the removed file's inode cannot be freed and handed to the new file
    # (ext4 reuses a freed inode number): the two stay distinct to compare.
    first = os.open(path, os.O_RDONLY)
    b = _Thread(lambda: engine._take_file_lock(path), "B")
    try:
        assert b_waiting.wait(WAIT), "B never waited on A's lock file"
        engine._give_file_lock(a_fd, path)
        b_fd = b.join()
        try:
            assert b_fd is not None and os.path.samestat(os.fstat(b_fd), os.stat(path)), (
                "B holds a lock on a file the name no longer leads to")
            assert not os.path.samestat(os.fstat(b_fd), os.fstat(first)), "B holds the removed file"
            third = os.open(path, os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    real_flock(third, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(third)
        finally:
            engine._give_file_lock(b_fd, path)
    finally:
        os.close(first)
    assert not path.exists(), "the lock file was left"


def test_the_windows_byte_lock_is_asked_again_and_its_file_removed(scratch, monkeypatch):
    """Where only msvcrt is to be had: the first byte is asked for without
    blocking (LK_NBLCK), and again after a pause while it is refused
    (EACCES); then let go, the file closed and removed."""
    engine = _engine()
    calls = []
    refusals = iter([True, True, False])

    class FakeMsvcrt:
        LK_NBLCK, LK_UNLCK = 2, 0

        @staticmethod
        def locking(fd, mode, nbytes):
            calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
            if mode == FakeMsvcrt.LK_NBLCK and next(refusals):
                raise PermissionError(errno.EACCES, "Permission denied")
    monkeypatch.setattr(engine, "fcntl", None)
    monkeypatch.setattr(engine, "msvcrt", FakeMsvcrt)
    with engine.saved_charts_lock():
        assert _folder(engine) == ["saved_charts.lock"], _folder(engine)
    assert calls == [(2, 1, 0), (2, 1, 0), (2, 1, 0), (0, 1, 0)], calls
    assert _folder(engine) == [], _folder(engine)


# =============================================================================
# After the blind check (KS_CHECK.md: finding 3, notes 5, 7 and 8)
# =============================================================================

@pytest.mark.parametrize("which", ["store", "preferences"])
def test_the_lock_files_name_is_gone_when_its_lock_is_let_go(scratch, monkeypatch, which):
    """Finding 3: the hand-over is sound only if the holder removes the name
    while it still holds the lock. Removed after the lock is let go, a
    newcomer could lock the old file under the name while a waiter takes the
    new one, and both would hold it. The descriptor's close is what lets an
    flock go: at that moment the name must already be gone."""
    engine = _engine()
    path = engine.DATA_DIR / ("saved_charts.lock" if which == "store" else "preferences.lock")
    lock = engine.saved_charts_lock if which == "store" else engine.preferences_lock
    held, at_close = {}, []
    real_take, real_close = engine._take_file_lock, os.close

    def take(*args, **kwargs):
        fd = real_take(*args, **kwargs)
        held["fd"] = fd
        return fd

    def close(fd):
        if fd == held.get("fd"):
            at_close.append(os.path.lexists(path))
        return real_close(fd)
    monkeypatch.setattr(engine, "_take_file_lock", take)
    monkeypatch.setattr(os, "close", close)
    with lock():
        assert held.get("fd") is not None and path.exists(), "the premise: the lock file is held"
    monkeypatch.setattr(os, "close", real_close)
    assert at_close == [False], f"at the lock's release the name was still there: {at_close}"


def test_a_release_does_not_remove_a_lock_file_that_is_not_its_own(scratch):
    """Note 5: something outside the app removes the held lock file, and a
    newcomer makes and locks a fresh one under the name. The first holder's
    release must not remove the newcomer's file by its name."""
    import fcntl
    engine = _engine()
    path = engine.DATA_DIR / "saved_charts.lock"
    first = engine._take_file_lock(path)
    path.unlink()                                   # the outside removal
    newcomer = engine._take_file_lock(path)
    try:
        assert newcomer is not None and os.path.samestat(os.fstat(newcomer), os.stat(path)), "the premise"
        engine._give_file_lock(first, path)
        assert path.exists() and os.path.samestat(os.fstat(newcomer), os.stat(path)), (
            "the first holder's release removed the newcomer's lock file")
        third = os.open(path, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(third, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(third)
    finally:
        engine._give_file_lock(newcomer, path)
    assert not path.exists(), "the newcomer's release left its file"


def _obstruct(path, kind, outside):
    """Put `kind` under the lock name; what the folder `outside` holds then."""
    if kind == "dangling link":
        path.symlink_to(outside / "made-by-the-lock")
    elif kind == "link to a file":
        (outside / "readers-file").write_text("the reader's own")
        path.symlink_to(outside / "readers-file")
        return {"readers-file": b"the reader's own"}
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_text("")
        path.chmod(0o444)
    return {}


@pytest.mark.parametrize("kind", ["dangling link", "link to a file", "directory"])
def test_an_obstruction_under_the_lock_name_is_refused_and_makes_nothing_outside(scratch, tmp_path, kind):
    """Note 7: what stands under the lock file's name and is not a lock file
    the app can open there -- a link (dangling, or to a file elsewhere), a
    directory -- is not followed and not opened, nothing is made outside the
    data folder and nothing outside is moved. Ruling 109 (lane SC3, under
    ruling 55): the save is refused (DataLockBlocked) and nothing is
    written; it used to go on on the thread lock alone (ruling 63's
    fallback). The read-only file of this test's fourth case is a lock now,
    not an obstruction (ruling 113): SC3's test_u3_a_read_only_file_under_the_lock_name_is_locked_as_it_stands."""
    engine = _engine()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "saved_charts.lock"
    expected = _obstruct(path, kind, outside)
    with pytest.raises(engine.DataLockBlocked):
        engine._take_file_lock(path)
    with pytest.raises(engine.DataLockBlocked):
        with engine.saved_charts_lock():
            engine.write_saved_charts(XY)
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == expected, (
        f"the lock made or moved a file outside the data folder: {sorted(p.name for p in outside.iterdir())}")
    assert os.path.lexists(path), "the obstruction was removed"
    assert not engine.SAVED_CHARTS_PATH.exists(), "the store was written"


# =============================================================================
# After the re-check (KS_CHECK.md, "Re-check (ba92cc2)", R-3)
# =============================================================================

QUICK = 15            # seconds: the bound on a lock taken with nothing to wait for


@pytest.mark.parametrize("kind", ["dangling link", "link to a file"])
def test_with_no_nofollow_a_link_under_the_lock_name_is_refused(scratch, tmp_path, monkeypatch, kind):
    """R-3 of the re-check: where the system has no O_NOFOLLOW (Windows), a
    link under the lock name was opened through, the opened file never
    matched the link, and the taker reopened it without end while holding
    the thread lock -- every Save hung. The taker must give up the file lock
    at once, never open through the link, and make or change nothing
    outside the data folder. A taker still going at the bound fails the
    test; every open after that is then refused, so that the taker stops
    and nothing spins on after the test. Ruling 109 (lane SC3, under ruling
    55): it gives up by refusing the write (DataLockBlocked); it used to go
    on on the thread lock alone (ruling 63)."""
    engine = _engine()
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "saved_charts.lock"
    expected = _obstruct(path, kind, outside)
    over = threading.Event()
    real_open = os.open

    def fused_open(*args, **kwargs):
        if over.is_set():
            raise OSError(errno.EIO, "the test is over")
        return real_open(*args, **kwargs)
    monkeypatch.setattr(os, "open", fused_open)

    def take():
        try:
            result.append(engine._take_file_lock(path))
        except engine.DataLockBlocked as exc:
            result.append(exc)
    taker = threading.Thread(target=take, daemon=True)
    result = []
    taker.start()
    taker.join(QUICK)
    still_going = taker.is_alive()
    over.set()
    taker.join(WAIT)
    monkeypatch.setattr(os, "open", real_open)
    assert not still_going, f"the lock was still being taken through the link after {QUICK}s"
    assert [type(r).__name__ for r in result] == ["DataLockBlocked"], f"a file lock was taken through the link: {result}"
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == expected, (
        f"the lock made or moved a file outside the data folder: {sorted(p.name for p in outside.iterdir())}")
    assert path.is_symlink(), "the link was removed"
    with pytest.raises(engine.DataLockBlocked):
        with engine.saved_charts_lock():
            engine.write_saved_charts(XY)
    assert not engine.SAVED_CHARTS_PATH.exists(), "the store was written"


def test_a_link_put_under_the_name_between_the_look_and_the_open_is_closed_and_refused(
        scratch, tmp_path, monkeypatch):
    """The look before the open can be overtaken: a link put there just
    after it is opened through where there is no O_NOFOLLOW. The look after
    the open finds the link, and what was opened is closed unlocked. Ruling
    109 (lane SC3, under ruling 55): the write is then refused
    (DataLockBlocked); it used to go on on the thread lock alone."""
    engine = _engine()
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "saved_charts.lock"
    expected = _obstruct(path, "link to a file", outside)
    real_kind = engine._lock_name_kind
    looks = []

    def overtaken(lock_path):
        looks.append(lock_path)
        return "absent" if len(looks) == 1 else real_kind(lock_path)
    monkeypatch.setattr(engine, "_lock_name_kind", overtaken)
    import fcntl
    locked = []
    real_flock = fcntl.flock

    def recording(fd, op):
        locked.append(os.fstat(fd))
        return real_flock(fd, op)
    monkeypatch.setattr(fcntl, "flock", recording)
    with pytest.raises(engine.DataLockBlocked):
        _Thread(lambda: engine._take_file_lock(path), "taker").join()
    assert len(looks) == 2, f"the name was looked at {len(looks)} times, not before and after the open"
    assert not locked, "the file opened through the link was locked before the name was looked at again"
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == expected


def test_a_writer_overtaken_at_every_take_waits_out_the_bound_and_never_goes_ahead(scratch, monkeypatch):
    """Ruling 73 with ruling 77 (replacing the sixteen-try cap's guard): a
    writer whose every take is overtaken (the file it locked never the one
    under the name) keeps taking its turn until the bound, then gives up
    with DataLockBusy -- it never returns without the file lock. The thread
    lock is let go with it."""
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", 0.5)
    path = engine.DATA_DIR / "saved_charts.lock"
    opens = []
    real_open = os.open

    def counting(file, *args, **kwargs):
        if Path(file) == path:
            opens.append(file)
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(os, "open", counting)
    monkeypatch.setattr(engine, "_still_named", lambda fd, lock_path: False)

    def take():
        with pytest.raises(engine.DataLockBusy):
            with engine.saved_charts_lock():
                pass
        return len(opens)
    assert _Thread(take, "taker").join() > 16, f"the writer stopped taking its turn after {len(opens)} opens"
    assert engine._STORE_THREAD_LOCK.acquire(timeout=0), "the thread lock was kept after giving up"
    engine._STORE_THREAD_LOCK.release()




# =============================================================================
# Rulings 73 and 77: no going ahead without the file lock; a bounded wait
# =============================================================================

def test_a_writer_that_loses_many_hand_overs_never_enters_while_another_holds(scratch, tmp_path):
    """The KS re-check's forced sequence (R2-3): W waits on A's lock file; A
    lets go; W gets the removed file's lock, and before W looks at the name
    B makes and locks the next file; W must wait on B's; and so on, A and B
    taking turns, twenty times. W never enters while another holds, and
    enters once nobody does."""
    _lose_hand_overs(tmp_path, 20)


def test_a_reused_lock_file_inode_does_not_silence_the_next_wait(scratch, tmp_path):
    """The child's record of the waits it has reported is cleared when it gets
    a lock (ruling 142). Kept for the child's life, it silenced W's report of
    a wait on any later lock file that took a removed file's inode number:
    the test then saw nothing for WAIT seconds. A filesystem that reuses
    inodes at once does so; this one need not, so here W's record files
    every lock file under one number, the reuse forced on every hand-over,
    while the engine still sees the real files."""
    _lose_hand_overs(tmp_path, 3, one_inode=True)


def _lose_hand_overs(tmp_path, times, one_inode=False):
    env = _children_env(tmp_path, prefs=False)
    kids = {name: _Child({"kind": "contender", "bound": 600, "hold": name == "W", "one_inode": one_inode},
                         env, tmp_path / f"{name}.log")
            for name in ("W", "A", "B")}
    w = kids["W"]
    try:
        for kid in kids.values():
            kid.expect("ready", timeout=APP_WAIT)
        holder, other = kids["A"], kids["B"]
        holder.tell("take")
        holder.expect("in")
        w.tell("take")
        w.expect("waiting")
        for lost in range(1, times + 1):
            holder.tell("release")
            holder.expect("out")
            w.expect("got")                       # W has the lock of the file just removed
            other.tell("take")
            taken = other.expect("in")            # the other newcomer makes and locks the next file
            w.tell("cont")
            then = w.expect("waiting", "in")
            assert then["event"] == "waiting", (
                f"after {lost} lost hand-overs W entered ({then}) while the other holds inode {taken['ino']}")
            holder, other = other, holder
        holder.tell("release")
        holder.expect("out")
        while True:
            then = w.expect("got", "in")
            if then["event"] == "in":
                break
            w.tell("cont")
        assert then["ino"] is not None and then["ino"] == then["named"], f"W entered without the file lock: {then}"
        w.tell("release")
        w.expect("out")
    finally:
        for kid in kids.values():
            kid.close()


def _holder(tmp_path, env, lock_path):
    """A second process that takes `lock_path`'s lock and never lets go
    until the test closes it (by its own handle)."""
    kid = _Child({"kind": "holder", "path": str(lock_path)}, env, tmp_path / "holder.log")
    kid.expect("held", timeout=APP_WAIT)
    return kid


BUSY_STORE = "Another window of this app is holding the saved charts just now, so nothing was written. Try again in a moment."
BUSY_PREFS = ("Another window of this app is holding the preferences just now, so this choice was not kept. "
              "Try again in a moment.")
SHORT_BOUND = 2.0


def _bounded(act, tmp_path, env, lock_path):
    """Run `act` in a thread while a second process holds `lock_path`'s lock;
    whether it returned within the bound and a margin. The holder is then
    let go (closed by its own handle), so that a writer still waiting goes
    on and the thread ends."""
    holder = _holder(tmp_path, env, lock_path)
    try:
        runner = _Thread(act, "window")
        returned = runner.done.wait(SHORT_BOUND + QUICK)
    finally:
        holder.close()
    runner.join()
    return returned


def _alerts(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning") for e in getattr(where, kind)]


@pytest.mark.parametrize("act", ["save", "delete"])
def test_a_store_lock_held_by_another_process_gives_the_busy_sentence_and_writes_nothing(
        scratch, tmp_path, monkeypatch, act):
    a = make_app(date="1983-11-19", page="sources", timeout=60)
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT_BOUND, raising=False)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    a.run()
    if act == "save":
        _name_box(a, "Z")
    else:
        _start_delete(a, "Y")
    returned = _bounded(lambda: _click_save(a) if act == "save" else _confirm_delete(a), tmp_path,
                        _children_env(tmp_path, prefs=False), engine.DATA_DIR / "saved_charts.lock")
    assert returned, f"the {act} was still waiting {SHORT_BOUND + QUICK}s after it began"
    assert_no_exception(a, act)
    assert BUSY_STORE in _alerts(a), _alerts(a)
    assert engine.SAVED_CHARTS_PATH.read_text() == json.dumps(XY, indent=2), "the store was written without the lock"
    assert sorted(_picker(a)) == ["-- New Chart --", "X", "Y"], _picker(a)


def test_a_preferences_lock_held_by_another_process_gives_the_busy_sentence_on_set_as_home(
        prefs_on, tmp_path, monkeypatch):
    a = make_app(date="1983-11-19", page="sources", timeout=60)
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT_BOUND, raising=False)
    a.run()
    assert "home_place" not in json.loads(engine.PREFERENCES_PATH.read_text()), "the premise: no home yet"
    returned = _bounded(lambda: a.sidebar.button(key="_set_home").click().run(), tmp_path,
                        _children_env(tmp_path, prefs=True), engine.DATA_DIR / "preferences.lock")
    assert returned, f"Set as home was still waiting {SHORT_BOUND + QUICK}s after it began"
    assert_no_exception(a, "Set as home")
    assert BUSY_PREFS in _alerts(a), _alerts(a)
    assert "home_place" not in json.loads(engine.PREFERENCES_PATH.read_text()), (
        "the home was written without the lock")


@pytest.mark.parametrize("op", ["remember", "forget"])
def test_a_preference_write_gives_up_after_the_bound(prefs_on, tmp_path, monkeypatch, op):
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT_BOUND, raising=False)
    assert engine.write_preferences(FIRST_PREFS)
    holder = _holder(tmp_path, _children_env(tmp_path, prefs=True), engine.DATA_DIR / "preferences.lock")
    try:
        caller = threading.Thread(target=lambda: result.append(_prefs_call(engine, op)), daemon=True)
        result = []
        caller.start()
        caller.join(SHORT_BOUND + QUICK)
        returned = not caller.is_alive()
    finally:
        holder.close()
    caller.join(WAIT)
    assert returned, f"the preference write was still waiting {SHORT_BOUND + QUICK}s after it began"
    assert result == [False], result
    assert getattr(engine, "LAST_PREFERENCES_BUSY", None) is True
    assert json.loads(engine.PREFERENCES_PATH.read_text()) == FIRST_PREFS



@pytest.mark.parametrize("where", ["no file lock call", "a lock file that cannot be made"])
def test_the_fallbacks_still_serialise_threads_and_their_wait_is_bounded(scratch, monkeypatch, where):
    """Ruling 63's fallbacks (no fcntl or msvcrt; a folder the lock file
    cannot be made in) keep the thread lock, which still serialises one
    server's windows; and its wait follows ruling 77's bound: a second
    writer gives up with DataLockBusy while the first holds past it."""
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", 0.5)
    if where == "no file lock call":
        monkeypatch.setattr(engine, "fcntl", None)
        monkeypatch.setattr(engine, "msvcrt", None)
    else:
        engine.DATA_DIR.chmod(0o555)
    try:
        holding, done = threading.Event(), threading.Event()

        def a():
            with engine.saved_charts_lock():
                holding.set()
                assert done.wait(WAIT), "B never gave up"

        def b():
            assert holding.wait(WAIT), "A never took the lock"
            try:
                with pytest.raises(engine.DataLockBusy):
                    with engine.saved_charts_lock():
                        pass
            finally:
                done.set()
            with engine.saved_charts_lock():
                return "in after A"
        ta, tb = _Thread(a, "A"), _Thread(b, "B")
        ta.join()
        assert tb.join() == "in after A"
        assert _folder(engine) == [], _folder(engine)
    finally:
        engine.DATA_DIR.chmod(0o755)
