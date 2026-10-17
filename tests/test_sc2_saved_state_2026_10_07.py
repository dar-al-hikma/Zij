"""Saved state, the leftovers (lane SC2, wave 5).

An outside audit of face757 reproduced the seven leftovers lane SC's check
named (S01-S07) and found four more (N01, N02, N04, N05); ruling 100 gives
the page a sentence for a cut-short save kept aside. Each case below was a
strict xfail failing on face757 for its finding's reason before its fix.

Orderings are forced at the real calls (the engine's writer, its stray
validator, its copier's create, its star reader's return, a copy's
copyfile; across processes a wrapper on fcntl.flock in the child, which
says "waiting" when a lock is refused). Nothing sleeps and nothing hopes
for a schedule: every wait on another thread, window or process is bounded
(WAIT), so a lock that never comes free fails the test rather than hanging
the suite.
"""
import errno
import json
import os
import queue
import shutil
import subprocess
import sys
import textwrap
import threading
from datetime import datetime as _real_datetime
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment
from test_repass_l6_2026_10_04 import _picker, _read, _sidebar_texts, _store, scratch  # noqa: F401
from test_followups_2026_10_05 import prefs_on  # noqa: F401

REPO = Path(APP_PATH).resolve().parent
WAIT = 120            # seconds: the bound on every wait for another thread, window or process
SHORT = 2.0           # seconds: the locks' bound where a test shortens it

REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
HOME = {"label": "Florence", "lat": 43.7792, "lon": 11.2463}
COMPLETE = json.dumps({"Last save": REC}, indent=2)
RECOVERED_SENTENCE = ("A save that was cut short was found and kept beside the saved charts; "
                      "it is not in the list.")
UNREADABLE_STORE = "Saved charts could not be read. A copy of the file was kept beside the saved charts."
UNREADABLE_PREFS_COPY = "Preferences could not be read. A copy of the file was kept beside the saved charts."
UNREADABLE_PREFS_NO_COPY = ("Preferences could not be read, and no copy of the file could be made, so it is "
                            "left as it is: readings, the home place and the last chart are not kept.")


def XF(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


def _engine():
    sync_engine_to_environment()
    import engine
    return engine


class _Thread:
    """A daemon thread running `fn`, its result or exception kept; joined
    within WAIT."""

    def __init__(self, fn, name):
        self.result, self.error = None, None
        self.thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)
        self.thread.start()

    def _run(self, fn):
        try:
            self.result = fn()
        except BaseException as exc:            # kept and re-raised by join()
            self.error = exc

    def join(self):
        self.thread.join(WAIT)
        assert not self.thread.is_alive(), f"{self.thread.name} did not finish within {WAIT}s"
        if self.error is not None:
            raise self.error
        return self.result


def _waited(event, what):
    assert event.wait(WAIT), f"{what} did not happen within {WAIT}s"


class _SignallingLock:
    """Stands in for one of the engine's thread locks: a caller that finds
    it held sets `waiting` before it blocks."""

    def __init__(self, waiting):
        self._real, self._waiting = threading.Lock(), waiting

    def acquire(self, blocking=True, timeout=-1):
        if self._real.acquire(False):
            return True
        self._waiting.set()
        return self._real.acquire(blocking, timeout)

    def release(self):
        self._real.release()

    def locked(self):
        return self._real.locked()


def _plant(path, data):
    """A stray holding `data`, last written long before the launch."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    os.utime(path, (0, 0))
    return path


def _save_under_the_lock(engine, name):
    """A save as the app makes one: under the store's lock, the store as it
    stands, the record put in, the whole written."""
    with engine.saved_charts_lock():
        charts = dict(engine.saved_charts_as_they_stand().charts or {})
        charts[name] = REC
        return engine.write_saved_charts(charts)


def _alerts(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning") for e in getattr(where, kind)]


def _dark_wheel(at):
    return [c for c in at.main.checkbox if c.label == "Dark wheel"][0]


def _prefs_path():
    return _store().parent / "preferences.json"


# =============================================================================
# S02: the old store's move, beside the app, outside the store's lock
# =============================================================================

def test_s02_the_old_stores_move_does_not_write_over_a_save_made_meanwhile(scratch, monkeypatch, tmp_path):
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    assert not engine.SAVED_CHARTS_PATH.exists(), "the premise: no store yet, so the old one is moved"
    at_write, go_on, progress = threading.Event(), threading.Event(), threading.Event()
    real_write = engine._write_text_atomically

    def gated(path, text):
        if threading.current_thread().name == "loader":
            at_write.set()
            assert go_on.wait(WAIT), "the test never let the move go on"
        return real_write(path, text)
    monkeypatch.setattr(engine, "_write_text_atomically", gated)
    monkeypatch.setattr(engine, "_STORE_THREAD_LOCK", _SignallingLock(progress))
    loader = _Thread(engine.load_saved_charts, "loader")
    _waited(at_write, "the old store's move reaching its write")

    def save():
        try:
            return _save_under_the_lock(engine, "New")
        finally:
            progress.set()
    saver = _Thread(save, "saver")
    _waited(progress, "the save ending or waiting on the store's lock")
    go_on.set()
    loader.join()
    assert saver.join() is True, "the save was refused"
    held = json.loads(engine.SAVED_CHARTS_PATH.read_text())
    assert "New" in held, f"the save made while the old store was moved is gone: {sorted(held)}"
    assert "Old" in held, f"the old store's chart was not moved: {sorted(held)}"


def test_s02_the_old_stores_move_waits_for_the_stores_lock(scratch, monkeypatch, tmp_path):
    """While another holds the store's lock the move is not made (nothing is
    written without the lock); the next load makes it."""
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", 0.5)
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        assert engine.load_saved_charts() == {}
        assert not engine.SAVED_CHARTS_PATH.exists(), "the old store was moved without the store's lock"
    finally:
        engine._STORE_THREAD_LOCK.release()
    assert engine.load_saved_charts() == {"Old": REC}
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file beside the app was changed"


# =============================================================================
# N01: the unreadable store's copy, made new or not at all
# =============================================================================

def test_n01_two_unreadable_contents_in_one_second_keep_two_copies(scratch, monkeypatch):
    engine = _engine()
    path = engine.SAVED_CHARTS_PATH

    class _OneSecond(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return _real_datetime(2026, 1, 1)
    monkeypatch.setattr(engine, "datetime", _OneSecond)
    both = threading.Barrier(2, timeout=WAIT)
    gated = set()
    real_write_bytes, real_open = Path.write_bytes, os.open

    def _first_create(name):
        # Each copier's first create of a copy waits for the other's: both
        # have chosen their copy's name by then, from one folder's listing.
        me = threading.current_thread().name
        if ".unreadable-" in name and me in ("A", "B") and me not in gated:
            gated.add(me)
            both.wait()

    def write_bytes(self, data):
        _first_create(self.name)
        return real_write_bytes(self, data)

    def opened(file, flags, mode=0o777, *, dir_fd=None):
        _first_create(os.path.basename(os.fspath(file)))
        return real_open(file, flags, mode, dir_fd=dir_fd)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)
    monkeypatch.setattr(os, "open", opened)
    a = _Thread(lambda: engine._preserve_unreadable_store(path, b"bad-A"), "A")
    b = _Thread(lambda: engine._preserve_unreadable_store(path, b"bad-B"), "B")
    named = {"bad-A": a.join(), "bad-B": b.join()}
    copies = {p.name: p.read_bytes() for p in path.parent.glob("saved_charts.json.unreadable-*")}
    assert sorted(copies.values()) == [b"bad-A", b"bad-B"], f"a content was lost: {copies}"
    assert copies.get(named["bad-A"]) == b"bad-A", f"A's copy was said to be {named['bad-A']}: {copies}"
    assert copies.get(named["bad-B"]) == b"bad-B", f"B's copy was said to be {named['bad-B']}: {copies}"
    # The frozen clock is the one the copier read: both copies are named for its one second.
    stem = f"{path.name}.unreadable-20260101-000000"
    assert sorted(copies) == [stem, stem + "-2"], sorted(copies)


# =============================================================================
# N02: two data folders whose store (or preferences) is one linked file
# =============================================================================

CHILD = textwrap.dedent("""
    import json, os, sys
    sys.path[:0] = [{repo!r}]
    job = json.loads(sys.argv[1])

    def say(**kw):
        print(json.dumps(kw), flush=True)

    def hear():
        line = sys.stdin.readline()
        if not line:
            raise SystemExit("the test went away")
        return line.strip()

    import fcntl
    _real_flock = fcntl.flock
    _said = []

    def _flock(fd, op):
        try:
            return _real_flock(fd, op)
        except BlockingIOError:
            if not _said:
                _said.append(1)
                say(event="waiting")
            raise
    fcntl.flock = _flock

    import engine
    say(event="ready")
    hear()
    if job["what"] == "charts":
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts or {{}})
            charts[job["name"]] = job["value"]
            ok = engine.write_saved_charts(charts)
    else:
        ok = engine.remember_preference(job["name"], job["value"])
    say(event="result", ok=ok)
""").format(repo=str(REPO))


class _Child:
    """Another launch of the app, a process of its own on its own data
    folder, its lines read by a thread of its own so that every read is
    bounded."""

    def __init__(self, job, env, log):
        self.log = log
        self._err = open(log, "w")
        self.proc = subprocess.Popen([sys.executable, "-c", CHILD, json.dumps(job)], env=env, cwd=str(REPO),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err, text=True)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(json.loads(line))
        self.lines.put(None)

    def expect(self, *events):
        try:
            msg = self.lines.get(timeout=WAIT)
        except queue.Empty:
            msg = "nothing"
        if msg is None or msg == "nothing" or msg["event"] not in events:
            self._err.flush()
            raise AssertionError(f"expected {events} from the other launch, got {msg}; its stderr ends "
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


def _two_launches_on_one_linked_file(tmp_path, monkeypatch, what):
    """This process on data folder a, a child on data folder b; each one's
    store (or preferences) a link to one file in a third folder."""
    name = "saved_charts.json" if what == "charts" else "preferences.json"
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / ("charts.json" if what == "charts" else "prefs.json")
    target.write_text(json.dumps({"X": REC} if what == "charts" else {"_launches": 3}, indent=2))
    homes = [tmp_path / "a", tmp_path / "b"]
    for home in homes:
        (home / "Zij").mkdir(parents=True)
        (home / "Zij" / name).symlink_to(target)
    monkeypatch.setenv("XDG_DATA_HOME", str(homes[0]))
    if what == "charts":
        monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    else:
        monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    engine = _engine()
    env = {**os.environ, "XDG_DATA_HOME": str(homes[1])}
    return engine, target, env


def test_n02_two_data_folders_linked_to_one_store_share_its_lock(tmp_path, monkeypatch):
    engine, target, env = _two_launches_on_one_linked_file(tmp_path, monkeypatch, "charts")
    child = _Child({"what": "charts", "name": "B", "value": REC}, env, tmp_path / "child.log")
    try:
        child.expect("ready")
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts)
            child.tell()
            first = child.expect("waiting", "result")
            charts["A"] = REC
            assert engine.write_saved_charts(charts), "this launch's save was refused"
        last = first if first["event"] == "result" else child.expect("result")
    finally:
        child.close()
    assert last["ok"] is True, "the other launch's save was refused"
    held = json.loads(target.read_text())
    assert sorted(held) == ["A", "B", "X"], f"a save to the linked store was lost: {sorted(held)}"
    assert first["event"] == "waiting", "the other launch went in without waiting for this one's lock"


def test_n02_two_data_folders_linked_to_one_preferences_file_share_its_lock(tmp_path, monkeypatch):
    engine, target, env = _two_launches_on_one_linked_file(tmp_path, monkeypatch, "prefs")
    child = _Child({"what": "prefs", "name": "_launches", "value": 7}, env, tmp_path / "child.log")
    try:
        child.expect("ready")
        with engine.preferences_lock():
            prefs, _from_file = engine._preferences_as_they_stand()
            child.tell()
            first = child.expect("waiting", "result")
            prefs["_wheel_dark"] = True
            assert engine.write_preferences(prefs), "this launch's write was refused"
        last = first if first["event"] == "result" else child.expect("result")
    finally:
        child.close()
    assert last["ok"] is True, "the other launch's write was refused"
    held = json.loads(target.read_text())
    assert held.get("_launches") == 7 and held.get("_wheel_dark") is True, f"a preference was lost: {held}"
    assert first["event"] == "waiting", "the other launch went in without waiting for this one's lock"


def test_n02_a_linked_store_leaves_no_lock_file_beside_its_target(scratch, tmp_path):
    """Beside N02's pins: the lock taken beside a linked store's target lives
    only while it is held, as the data folder's does (KS); the unlinked
    store's lock is the data folder's alone, as before."""
    engine = _engine()
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "charts.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    assert _save_under_the_lock(engine, "Z") is True
    assert sorted(p.name for p in shared.iterdir()) == ["charts.json"], sorted(p.name for p in shared.iterdir())
    assert sorted(json.loads(target.read_text())) == ["X", "Z"]
    engine.SAVED_CHARTS_PATH.unlink()
    with engine.saved_charts_lock():
        assert sorted(p.name for p in engine.SAVED_CHARTS_PATH.parent.iterdir()) == ["saved_charts.lock"]
        assert sorted(p.name for p in shared.iterdir()) == ["charts.json"], "a lock beside an unlinked store's elsewhere"


# =============================================================================
# N05: the data folder's copy under the former name, published whole
# =============================================================================

def _former_folder(engine, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    legacy = base / engine._LEGACY_APP_DIR_NAME
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"Old": REC}, indent=2))
    return base, legacy, base / engine.APP_DIR_NAME


def _refuse_the_move(monkeypatch, legacy):
    real_rename = Path.rename

    def rename(self, target):
        if Path(self) == legacy:
            raise PermissionError(errno.EACCES, "the move was refused (the test's)", str(self))
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", rename)


def test_n05_the_former_folders_copy_does_not_write_over_a_save_made_meanwhile(scratch, monkeypatch, tmp_path):
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    _refuse_the_move(monkeypatch, legacy)
    at_copy, go_on = threading.Event(), threading.Event()
    real_copyfile = shutil.copyfile

    def copyfile(src, dst, *args, **kwargs):
        if threading.current_thread().name == "first launch" and not at_copy.is_set():
            at_copy.set()
            assert go_on.wait(WAIT), "the test never let the copy go on"
        return real_copyfile(src, dst, *args, **kwargs)
    monkeypatch.setattr(shutil, "copyfile", copyfile)
    first = _Thread(lambda: engine._make_user_data_dir(target), "first launch")
    try:
        _waited(at_copy, "the first launch's copy reaching the saved charts")
        engine._make_user_data_dir(target)               # the second launch's folder, made as a launch makes it
        monkeypatch.setattr(engine, "SAVED_CHARTS_PATH", target / "saved_charts.json")
        assert _save_under_the_lock(engine, "New") is True, "the premise: the second launch's save was written"
    finally:
        go_on.set()
    first.join()
    held = json.loads((target / "saved_charts.json").read_text())
    assert "New" in held, f"the save made into the new folder is gone: {sorted(held)}"
    assert "Old" in held, f"the former folder's chart did not reach the new folder: {sorted(held)}"
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name]), sorted(base.iterdir())


def test_n05_a_copy_refused_in_part_publishes_the_rest_whole(scratch, monkeypatch, tmp_path):
    """Beside N05's pin: a file of the former folder that cannot be copied (a
    link to nothing) does not keep the rest out; what could be copied is
    published whole, as the copy made in place left it, the former folder
    stays as it was, and nothing is left beside them."""
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    (legacy / "ephe_stars").mkdir()
    (legacy / "ephe_stars" / "sefstars.txt").symlink_to(tmp_path / "gone" / "sefstars.txt")
    _refuse_the_move(monkeypatch, legacy)
    assert engine._make_user_data_dir(target) == target
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name]), sorted(base.iterdir())
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}, "the charts were not copied"
    assert (legacy / "ephe_stars" / "sefstars.txt").is_symlink(), "the former folder was changed"
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"


# =============================================================================
# S03: a temporary file of another program's, beside a linked store
# =============================================================================

@pytest.mark.parametrize("where", ["in the data folder", "in another folder"])
@pytest.mark.parametrize("data", [b"another program's work", json.dumps({"Theirs": REC}).encode()],
                         ids=["does not read", "reads as a store"])
def test_s03_another_programs_temporary_file_beside_a_linked_store_is_left(scratch, tmp_path, where, data):
    engine = _engine()
    folder = engine.SAVED_CHARTS_PATH.parent if where == "in the data folder" else tmp_path / "shared"
    folder.mkdir(exist_ok=True)
    target = folder / "shared.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    theirs = _plant(folder / "shared.json.tmp", data)
    assert engine.load_saved_charts() == {"X": REC}
    assert theirs.exists() and theirs.read_bytes() == data, "another program's temporary file was removed"
    assert not list(folder.glob("shared.json.recovered-*")), "another program's temporary file was kept aside"


def test_s03_the_former_name_beside_the_stores_own_name_is_still_taken(scratch, tmp_path):
    """Beside S03's pin: ruling 91's `saved_charts.json.tmp` is still kept
    aside beside a store kept as a link to a file of that name."""
    engine = _engine()
    folder = tmp_path / "shared"
    folder.mkdir()
    target = folder / "saved_charts.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    stray = _plant(folder / "saved_charts.json.tmp", COMPLETE)
    assert engine.load_saved_charts() == {"X": REC}
    assert not stray.exists()
    kept = sorted(folder.glob("saved_charts.json.recovered-*"))
    assert len(kept) == 1 and kept[0].read_text() == COMPLETE, kept


# =============================================================================
# S04: a stray judged while the store's lock is held
# =============================================================================

def test_s04_a_save_is_not_kept_waiting_while_a_stray_is_judged(scratch, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
    judging, judged = threading.Event(), threading.Event()
    real_reads = engine._reads_as_a_store

    def slow(data):
        if threading.current_thread().name == "loader":
            judging.set()
            assert judged.wait(WAIT), "the test never let the judging go on"
        return real_reads(data)
    monkeypatch.setattr(engine, "_reads_as_a_store", slow)
    loader = _Thread(engine.load_saved_charts, "loader")
    _waited(judging, "the tidying judging the stray")
    busy, saved = False, False
    try:
        saved = _save_under_the_lock(engine, "New")
    except engine.DataLockBusy:
        busy = True
    finally:
        judged.set()
    assert "X" in loader.join()
    assert not busy, "the save was refused as busy while the tidying judged a stray"
    assert saved is True and sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == ["New", "X"]
    assert not stray.exists()
    kept = sorted(engine.SAVED_CHARTS_PATH.parent.glob("saved_charts.json.recovered-*"))
    assert len(kept) == 1 and kept[0].read_text() == COMPLETE, kept


def test_s04_a_stray_that_changed_after_it_was_listed_is_left(scratch, monkeypatch):
    """Beside S04's pin: a stray is removed only while its name still holds
    the file listed under the lock."""
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), b"half a write")
    real_reads = engine._reads_as_a_store

    def swapped(data):
        stray.unlink()
        stray.write_text("something else now")
        return real_reads(data)
    monkeypatch.setattr(engine, "_reads_as_a_store", swapped)
    engine.load_saved_charts()
    assert stray.read_text() == "something else now", "a file that was not the one judged was removed"


# =============================================================================
# Ruling 100: a cut-short save kept aside is told
# =============================================================================

def test_r100_a_cut_short_save_kept_aside_is_told_once(scratch):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    stray = _plant(_store().with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert not stray.exists(), "the premise: the stray was kept aside"
    assert _alerts(at).count(RECOVERED_SENTENCE) == 1, _alerts(at)
    at.run()
    assert RECOVERED_SENTENCE not in _alerts(at), "said again on the next run"
    other = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert RECOVERED_SENTENCE not in _alerts(other), "said by a window whose load kept nothing aside"


def test_r100_a_stray_that_does_not_read_is_not_told(scratch):
    """Beside ruling 100's pin: a stray removed because it does not read was
    no save, and nothing is kept; nothing is said."""
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    _plant(_store().with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE[:-3])
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert not [t for t in _sidebar_texts(at) if "cut short" in t], _sidebar_texts(at)


# =============================================================================
# S01: the store's notices, each window's own
# =============================================================================

def _between_loads(monkeypatch, engine, other):
    """Run `other` to its end in a thread of its own just after the window's
    first load of the store returns, before the window reads what it left;
    joined within WAIT."""
    real = engine.load_saved_charts
    done = []

    def held(*args, **kwargs):
        charts = real(*args, **kwargs)
        if not done:
            done.append(True)
            runner = _Thread(lambda: other(real), "another window")
            runner.join()
        return charts
    monkeypatch.setattr(engine, "load_saved_charts", held)


def test_s01_a_windows_unreadable_store_notice_is_its_own(scratch, monkeypatch):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text("{not json")
    engine = _engine()

    def other_window(load):
        _store().write_text(json.dumps({"X": REC}, indent=2))
        assert load() == {"X": REC}
    _between_loads(monkeypatch, engine, other_window)
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    copies = sorted(p.name for p in _store().parent.glob("saved_charts.json.unreadable-*"))
    assert len(copies) == 1, f"the premise: this window's load kept the bytes aside: {copies}"
    assert [t for t in _alerts(at) if t == UNREADABLE_STORE], _alerts(at)


def test_s01_another_windows_unreadable_store_notice_is_not_this_windows(scratch, monkeypatch):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    engine = _engine()

    def other_window(load):
        _store().write_text("{not json")
        assert load() == {}
    _between_loads(monkeypatch, engine, other_window)
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert sorted(p.name for p in _store().parent.glob("saved_charts.json.unreadable-*")), (
        "the premise: the other window's load kept the bytes aside")
    assert not [t for t in _alerts(at) if "could not be read" in t], _alerts(at)


def test_s01_another_windows_kept_aside_save_is_not_this_windows(scratch, monkeypatch):
    """Beside S01's pins: ruling 100's sentence is each window's own, as the
    unreadable store's is."""
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    engine = _engine()

    def other_window(load):
        _plant(_store().with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
        assert load() == {"X": REC}
        assert sorted(_store().parent.glob("saved_charts.json.recovered-*")), "the premise: it was kept aside"
    _between_loads(monkeypatch, engine, other_window)
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert RECOVERED_SENTENCE not in _alerts(at), _alerts(at)


# =============================================================================
# S05: the unreadable-preferences sentence, in the run of the choice
# =============================================================================

@pytest.mark.parametrize("copyable", [True, False], ids=["copied aside", "no copy"])
def test_s05_an_unreadable_preferences_file_met_by_a_control_is_said_in_that_run(prefs_on, copyable):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    assert_no_exception(at, "the launch")
    _prefs_path().unlink()
    if copyable:
        _prefs_path().write_text("{not json")
    else:
        _prefs_path().mkdir()               # nothing to read, so nothing to copy
    _dark_wheel(at).check().run()
    said = _alerts(at)
    at.run()
    again = _alerts(at)
    assert_no_exception(at, "the tick")
    copies = sorted(p.name for p in _store().parent.glob("preferences.json.unreadable-*"))
    assert len(copies) == (1 if copyable else 0), f"the premise: the file was kept aside or not: {copies}"
    sentence = UNREADABLE_PREFS_COPY if copyable else UNREADABLE_PREFS_NO_COPY
    assert said.count(sentence) == 1, said
    assert sentence not in again, again


# =============================================================================
# S06: a stored time standard that is empty
# =============================================================================

@pytest.mark.parametrize("label", ["", "   "], ids=["empty", "blank"])
def test_s06_an_empty_stored_standard_is_said_without_empty_quotation_marks(scratch, label):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"E": dict(REC, time_standard=label)}, indent=2))
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(at).select("E").run()
    assert_no_exception(at, "opening E")
    named = [w.value for w in at.sidebar.warning if w.value.startswith("'E' was saved with")]
    assert len(named) == 1, [w.value for w in at.sidebar.warning]
    assert "''" not in named[0] and "``" not in named[0], named[0]
    assert "empty" in named[0] and named[0].endswith("Choose the standard, then save the chart again."), named[0]
    assert "LMT (Local Mean Time)" in named[0], named[0]


# =============================================================================
# S07: a refused "Forget home" and the window's copy of the preferences
# =============================================================================

def test_s07_a_refused_forget_home_leaves_the_windows_copy_and_the_next_rebuild_keeps_it(prefs_on):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({}))
    _prefs_path().write_text(json.dumps({"home_place": HOME}))
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    assert at.session_state["home_place"] == HOME, "the premise: the home is loaded"
    _prefs_path().unlink()
    _prefs_path().mkdir()                   # neither read nor copied: the forget is refused
    at.sidebar.button(key="_forget_home").click().run()
    assert_no_exception(at, "Forget home")
    assert at.session_state["home_place"] == HOME, "the premise: the refused forget keeps the session's home"
    assert at.session_state["_prefs"].get("home_place") == HOME, "the window's copy of the file lost the home"
    _prefs_path().rmdir()
    _prefs_path().write_text("{not json")   # unreadable but copied aside: rebuilt from the window's copy
    _dark_wheel(at).check().run()
    assert_no_exception(at, "the tick that rebuilds the file")
    rebuilt = _read(_prefs_path())
    assert rebuilt.get("_wheel_dark") is True, f"the premise: the file was rebuilt with the tick: {rebuilt}"
    assert rebuilt.get("home_place") == HOME, f"the file rebuilt from the window's copy lost the home: {rebuilt}"


# =============================================================================
# N04: the fixed stars' missing-star notice, each table's own
# =============================================================================

def test_n04_a_tables_missing_star_notice_is_its_own_reads(scratch, monkeypatch):
    engine = _engine()
    assert engine._fixed_star_catalogue_ready() is True, "the premise: the shipped catalogue is attached"
    import swisseph as swe
    real_star = swe.fixstar2_ut
    jd_a, jd_b = 2451545.5, 2451910.5

    def flaky(name, jd, *args, **kwargs):
        if name == "Algol" and jd == jd_a:
            raise OSError("not read on this date (the test's)")
        return real_star(name, jd, *args, **kwargs)
    monkeypatch.setattr(swe, "fixstar2_ut", flaky)
    read, other_done = threading.Event(), threading.Event()
    real_reader = engine._on_fixed_star_reader

    def on_reader(fn, *args):
        out = real_reader(fn, *args)
        if threading.current_thread().name == "A" and fn.__name__ != "_fixed_star_catalogue_search":
            read.set()
            assert other_done.wait(WAIT), "the test never let A go on"
        return out
    monkeypatch.setattr(engine, "_on_fixed_star_reader", on_reader)
    chart = {"planetary_data": {"Sun": {"longitude": 10.0}, "Moon": {"longitude": 200.0}},
             "ascendant": 0.0, "mc": 270.0}
    a = _Thread(lambda: engine.pn4_fixed_stars_in_image(chart, jd_a), "A")
    try:
        _waited(read, "A's read of the stars")
        b = engine.pn4_fixed_stars_in_image(chart, jd_b)
    finally:
        other_done.set()
    out_a = a.join()
    assert b["missing"] == "", b["missing"]
    assert out_a["missing"] == "Not in the catalogue attached, so not placed: Algol.", repr(out_a["missing"])
