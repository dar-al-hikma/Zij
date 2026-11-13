"""Saved state, the leftovers.

An outside audit reproduced seven leftovers of an earlier review and found four
more, and the page now has a sentence for a cut-short save kept aside. Each
case below was a strict xfail failing for its finding's reason before its fix.

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

import user_data
from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment
from test_repass_l6_2026_10_04 import _picker, _read, _sidebar_texts, _store, scratch  # noqa: F401
from test_followups_2026_10_05 import prefs_on  # noqa: F401

REPO = Path(APP_PATH).resolve().parent
WAIT = 120            # seconds: the bound on every wait for another thread, window or process
SHORT = 2.0           # seconds: the locks' bound where a test shortens it

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
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


def _bounds_ring(at):
    return [c for c in at.main.checkbox if c.label == "Bounds ring"][0]


def _prefs_path():
    return _store().parent / "preferences.json"


# =============================================================================
# The old store's move, beside the app, outside the store's lock
# =============================================================================

def test_s02_the_old_stores_move_does_not_write_over_a_save_made_meanwhile(scratch, monkeypatch, tmp_path):
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(user_data, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    assert not engine.SAVED_CHARTS_PATH.exists(), "the premise: no store yet, so the old one is moved"
    at_write, go_on, progress = threading.Event(), threading.Event(), threading.Event()
    real_write = engine._write_text_atomically

    def gated(path, text):
        if threading.current_thread().name == "loader":
            at_write.set()
            assert go_on.wait(WAIT), "the test never let the move go on"
        return real_write(path, text)
    monkeypatch.setattr(user_data, "_write_text_atomically", gated)
    monkeypatch.setattr(user_data, "_STORE_THREAD_LOCK", _SignallingLock(progress))
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
    monkeypatch.setattr(user_data, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    monkeypatch.setattr(user_data, "LOCK_WAIT_SECONDS", 0.5)
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        assert engine.load_saved_charts() == {}
        assert not engine.SAVED_CHARTS_PATH.exists(), "the old store was moved without the store's lock"
    finally:
        engine._STORE_THREAD_LOCK.release()
    assert engine.load_saved_charts() == {"Old": REC}
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file beside the app was changed"


# =============================================================================
# The unreadable store's copy, made new or not at all
# =============================================================================

def test_n01_two_unreadable_contents_in_one_second_keep_two_copies(scratch, monkeypatch):
    engine = _engine()
    path = engine.SAVED_CHARTS_PATH

    class _OneSecond(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return _real_datetime(2026, 1, 1)
    monkeypatch.setattr(user_data, "datetime", _OneSecond)
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
# Two data folders whose store (or preferences) is one linked file
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


def test_n02_two_data_folders_linked_to_one_store_follow_neither_link(tmp_path, monkeypatch):
    """Two data folders whose stores were links to one file shared the lock
    taken beside that file. A link at the store's name is now never
    followed: no launch reads or writes the file, and no lock is taken
    beside it."""
    engine, target, _env = _two_launches_on_one_linked_file(tmp_path, monkeypatch, "charts")
    before = target.read_bytes()
    assert engine.load_saved_charts() == {}
    assert _save_under_the_lock(engine, "A") is False
    assert target.read_bytes() == before
    assert sorted(p.name for p in target.parent.iterdir()) == [target.name]


def test_n02_two_data_folders_linked_to_one_preferences_file_follow_neither_link(tmp_path, monkeypatch):
    """As for the store: the preferences' link is never followed, the file
    it names neither read nor written, and no lock is taken beside it."""
    engine, target, _env = _two_launches_on_one_linked_file(tmp_path, monkeypatch, "prefs")
    before = target.read_bytes()
    assert engine.remember_preference("_wheel_dark", True) is False
    assert target.read_bytes() == before
    assert sorted(p.name for p in target.parent.iterdir()) == [target.name]


def test_n02_a_linked_store_leaves_no_lock_file_beside_its_target(scratch, tmp_path):
    """Beside the pins above: the lock was taken beside a linked store's
    target. A link at the store's name is now never followed: no lock is
    taken beside the file it names, nothing is written there, and the
    store's lock is the data folder's alone."""
    engine = _engine()
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "charts.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    assert _save_under_the_lock(engine, "Z") is False
    assert sorted(p.name for p in shared.iterdir()) == ["charts.json"], sorted(p.name for p in shared.iterdir())
    assert sorted(json.loads(target.read_text())) == ["X"]
    engine.SAVED_CHARTS_PATH.unlink()
    with engine.saved_charts_lock():
        # No version was kept of the file the link names.
        here = sorted(p.name for p in engine.SAVED_CHARTS_PATH.parent.iterdir())
        assert here == ["saved_charts.lock"], here
        assert sorted(p.name for p in shared.iterdir()) == ["charts.json"], "a lock beside an unlinked store's elsewhere"


# =============================================================================
# The data folder's copy under the former name, published whole
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
    real_copy_a_file = user_data._copy_a_file

    def copy_a_file(*args, **kwargs):
        if threading.current_thread().name == "first launch" and not at_copy.is_set():
            at_copy.set()
            assert go_on.wait(WAIT), "the test never let the copy go on"
        return real_copy_a_file(*args, **kwargs)
    monkeypatch.setattr(user_data, "_copy_a_file", copy_a_file)
    first = _Thread(lambda: engine._make_user_data_dir(target), "first launch")
    try:
        _waited(at_copy, "the first launch's copy reaching the saved charts")
        # The second launch waits for the first's lock on the former folder,
        # held through the copy, and makes no folder of its own meanwhile:
        # it asks again once the first has published its copy, and saves.
        monkeypatch.setattr(user_data, "_FORMER_FOLDER_LOCK_WAIT", 0.2, raising=False)
        with pytest.raises(user_data.FormerFolderBusy):
            engine._make_user_data_dir(target)
        assert not os.path.lexists(target), "the second launch made a folder while the first copied"
    finally:
        go_on.set()
    first.join()
    assert engine._make_user_data_dir(target) == target
    monkeypatch.setattr(user_data, "SAVED_CHARTS_PATH", target / "saved_charts.json")
    assert _save_under_the_lock(engine, "New") is True, "the premise: the second launch's save was written"
    held = json.loads((target / "saved_charts.json").read_text())
    assert "New" in held, f"the save made into the new folder is gone: {sorted(held)}"
    assert "Old" in held, f"the former folder's chart did not reach the new folder: {sorted(held)}"
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name]), sorted(base.iterdir())


def test_n05_a_link_to_nothing_in_the_former_folder_keeps_the_copy_from_being_published(scratch, monkeypatch,
                                                                                         tmp_path):
    """Beside the pin above: a link to nothing in the former folder, which the
    copy used to fail on and publish the rest without, and then carried as
    the link: the copy publishes regular files and folders only, so it is
    not published, the former folder stays as it was, and nothing is left
    beside it."""
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    (legacy / "ephe_stars").mkdir()
    gone = tmp_path / "gone" / "sefstars.txt"
    (legacy / "ephe_stars" / "sefstars.txt").symlink_to(gone)
    _refuse_the_move(monkeypatch, legacy)
    with pytest.raises(engine.FormerFolderNotCopied):
        engine._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], sorted(base.iterdir())
    assert os.readlink(legacy / "ephe_stars" / "sefstars.txt") == str(gone), "the former folder was changed"
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"


# =============================================================================
# A temporary file of another program's, beside a linked store
# =============================================================================

@pytest.mark.parametrize("where", ["in the data folder", "in another folder"])
@pytest.mark.parametrize("data", [b"another program's work", json.dumps({"Theirs": REC}).encode()],
                         ids=["does not read", "reads as a store"])
def test_s03_another_programs_temporary_file_beside_a_linked_store_is_left(scratch, tmp_path, where, data):
    """The link at the store's name is never followed (nothing read), and
    a temporary file named after the file it names is no stray of the
    store's: left as it is, nothing kept aside."""
    engine = _engine()
    folder = engine.SAVED_CHARTS_PATH.parent if where == "in the data folder" else tmp_path / "shared"
    folder.mkdir(exist_ok=True)
    target = folder / "shared.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    theirs = _plant(folder / "shared.json.tmp", data)
    assert engine.load_saved_charts() == {}
    assert theirs.exists() and theirs.read_bytes() == data, "another program's temporary file was removed"
    assert not list(folder.glob("shared.json.recovered-*")), "another program's temporary file was kept aside"


def test_s03_the_former_name_beside_a_linked_store_in_another_folder_is_left(scratch, tmp_path):
    """Beside the pin above: the earlier writer's `saved_charts.json.tmp`,
    beside a store
    kept as a link to a file of that name in another folder, was kept aside
    and removed there. The strays are tidied in the data folder alone now
    (a stray in it of that name is still taken: test_sc_saved_charts), and
    the one in the other folder is left as it is, nothing made beside it;
    the link itself is never followed, so nothing is read."""
    engine = _engine()
    folder = tmp_path / "shared"
    folder.mkdir()
    target = folder / "saved_charts.json"
    target.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    stray = _plant(folder / "saved_charts.json.tmp", COMPLETE)
    assert engine.load_saved_charts() == {}
    assert stray.exists() and stray.read_text() == COMPLETE
    assert sorted(p.name for p in folder.iterdir()) == ["saved_charts.json", "saved_charts.json.tmp"]


# =============================================================================
# A stray judged while the store's lock is held
# =============================================================================

def test_s04_a_save_is_not_kept_waiting_while_a_stray_is_judged(scratch, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(user_data, "LOCK_WAIT_SECONDS", SHORT)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
    judging, judged = threading.Event(), threading.Event()
    real_reads = engine._reads_as_a_store

    def slow(data):
        if threading.current_thread().name == "loader":
            judging.set()
            assert judged.wait(WAIT), "the test never let the judging go on"
        return real_reads(data)
    monkeypatch.setattr(user_data, "_reads_as_a_store", slow)
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
    """Beside the pin above: a stray is removed only while its name still holds
    the file listed under the lock."""
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), b"half a write")
    real_reads = engine._reads_as_a_store

    def swapped(data):
        stray.unlink()
        stray.write_text("something else now")
        return real_reads(data)
    monkeypatch.setattr(user_data, "_reads_as_a_store", swapped)
    engine.load_saved_charts()
    assert stray.read_text() == "something else now", "a file that was not the one judged was removed"


# =============================================================================
# A cut-short save kept aside is told
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
    """Beside the pin above: a stray removed because it does not read was
    no save, and nothing is kept; nothing is said."""
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"X": REC}, indent=2))
    _plant(_store().with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE[:-3])
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert not [t for t in _sidebar_texts(at) if "cut short" in t], _sidebar_texts(at)


# =============================================================================
# The store's notices, each window's own
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
    """Beside the pins above: the kept-aside sentence is each window's own, as
    the unreadable store's is."""
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
# The unreadable-preferences sentence, in the run of the choice
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
    _bounds_ring(at).uncheck().run()
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
# A stored time standard that is empty
# =============================================================================

@pytest.mark.parametrize("label", ["", "   "], ids=["empty", "blank"])
def test_s06_an_empty_stored_standard_is_said_without_empty_quotation_marks(scratch, label):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps({"E": dict(REC, time_standard=label)}, indent=2))
    # The box stands at LMT before the load (a seeded standard is kept), as
    # it opened before the box followed the date.
    at = make_app(date="2000-01-01", page="sources", timeout=300)
    at.session_state["time_standard_key"] = "LMT (Local Mean Time)"
    at.run()
    _picker(at).select("E").run()
    assert_no_exception(at, "opening E")
    named = [w.value for w in at.sidebar.warning if w.value.startswith("'E' was saved with")]
    assert len(named) == 1, [w.value for w in at.sidebar.warning]
    assert "''" not in named[0] and "``" not in named[0], named[0]
    assert "empty" in named[0] and named[0].endswith("Choose the standard, then save the chart again."), named[0]
    assert "LMT (Local Mean Time)" in named[0], named[0]


# =============================================================================
# A refused "Forget home" and the window's copy of the preferences
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
    _bounds_ring(at).uncheck().run()
    assert_no_exception(at, "the tick that rebuilds the file")
    rebuilt = _read(_prefs_path())
    assert rebuilt.get("_chart_bounds") is False, f"the premise: the file was rebuilt with the tick: {rebuilt}"
    assert rebuilt.get("home_place") == HOME, f"the file rebuilt from the window's copy lost the home: {rebuilt}"


# =============================================================================
# The fixed stars' missing-star notice, each table's own
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
    chart_a = engine.calculate_traditional_chart_jd(jd_a, 40.0, 10.0)
    chart_b = engine.calculate_traditional_chart_jd(jd_b, 40.0, 10.0)
    a = _Thread(lambda: engine.pn4_fixed_stars_in_image(chart_a, jd_a), "A")
    try:
        _waited(read, "A's read of the stars")
        b = engine.pn4_fixed_stars_in_image(chart_b, jd_b)
    finally:
        other_done.set()
    out_a = a.join()
    assert b["missing"] == "", b["missing"]
    assert out_a["missing"] == "Not in the catalogue attached, so not placed: Algol.", repr(out_a["missing"])
