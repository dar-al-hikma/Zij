"""A blocked lock file is refused (lane SC3, wave 5; ruling 109), with SC2's check notes.

Ruling 109 narrows ruling 63's fallback. Where the system offers file locks
and something stands under a lock file's name that is no lock file this app
can use -- a directory, a link (dangling, or to a file elsewhere), a file
this account can open in no way -- a save, a delete or a preference write is
refused with a sentence naming the folder, and nothing is written; this
holds for the store's lock and the preferences', in the data folder and
beside the file a linked store or preferences file names. Where the system
has no lock call, the thread lock alone still serves, as ruling 63 has it;
a filesystem that refuses the lock call itself now refuses the write too
(DataLockUnavailable).

The refusal must never be one the app made itself. Under a umask that takes
away the owner's write, the app's own lock file was made read-only, and
every other launch went in on the thread lock alone while it was held
(SC2's check, the data on D01); a launch killed while it held one left it
so. flock takes a descriptor opened for reading as well as for writing, so
a lock file this account can open either way is now locked as it stands: a
lock, not an obstruction (ruling 113, amending ruling 109's list).

SC2's check notes follow: S02 (the old store's move at a busy load), N05
(the former folder's copy), S04 (a deeply nested file), S06 (a label of
invisible characters) and N04 (the revolution's star table). Each case below
was a strict xfail failing on 433fa19 for its reason before its fix.

Orderings are forced at the real calls (the lock's flock in another process,
the copy's copyfile, the star catalogue's read); a launch killed is killed by
its own handle. Nothing sleeps and nothing hopes for a schedule: every wait
on another thread, window or process is bounded, so a lock that never comes
free fails the test rather than hanging the suite.
"""
import errno
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

REPO = Path(APP_PATH).resolve().parent
WAIT = 120            # seconds: the bound on every wait for another thread, window or process
LAUNCH = 600          # seconds: the bound on a child process's import of the engine
SHORT = 2.0           # seconds: the locks' bound where a test shortens it

REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
XY = {"X": REC, "Y": dict(REC, date_string="1990-01-01")}
HOME = {"label": "Florence", "lat": 43.7792, "lon": 11.2463}
FIRST_PREFS = {"_launches": 3, "last_chart": "X"}
NEW_CHART = "-- New Chart --"

# The owner's sentences (ruling 112): ruling 109's refusals, and S02's.
STORE_BLOCKED = ("Charts cannot be saved or deleted: something in their folder, `{folder}`, is in the way of the "
                 "file this app uses to keep two windows from writing at once. Nothing was written.")
PREFS_BLOCKED = ("Preferences cannot be saved: something in their folder, `{folder}`, is in the way of the file "
                 "this app uses to keep two windows from writing at once. This choice was not kept.")
STORE_UNMOVED = ("Another window was using the saved charts when this one opened, so charts kept by an older "
                 "version of the app are not listed yet. Reload the page to list them.")
MISSING_ALGOL = "Not in the catalogue attached, so not placed: Algol."
SAVE_REFUSED = "The saved charts file could not be written to disk."


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
        except BaseException as exc:            # kept and given back by outcome()
            self.error = exc

    def outcome(self):
        """What `fn` came to: ('returned', its value) or ('raised', the exception)."""
        self.thread.join(WAIT)
        assert not self.thread.is_alive(), f"{self.thread.name} did not finish within {WAIT}s"
        return ("raised", self.error) if self.error is not None else ("returned", self.result)


def _attempt(fn, name="window"):
    return _Thread(fn, name).outcome()


def _folder(path):
    return sorted(p.name for p in Path(path).iterdir())


def _save_under_the_lock(engine, name):
    """A save as the app makes one: under the store's lock, the store as it
    stands, the record put in, the whole written."""
    with engine.saved_charts_lock():
        charts = dict(engine.saved_charts_as_they_stand().charts or {})
        charts[name] = REC
        return engine.write_saved_charts(charts)


def _flock_refused(fd):
    """Whether another descriptor's exclusive flock on the same file is
    refused just now (it is held)."""
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    fcntl.flock(fd, fcntl.LOCK_UN)
    return False


def _obstruct(path, kind, outside):
    """Put `kind` under the lock name `path`; what the folder `outside`
    holds then."""
    if kind == "dangling link":
        path.symlink_to(outside / "made-by-the-lock")
    elif kind == "link to a file":
        (outside / "readers-file").write_text("the reader's own")
        path.symlink_to(outside / "readers-file")
        return {"readers-file": b"the reader's own"}
    elif kind == "directory":
        path.mkdir()
    else:                                       # a file this account can open in no way
        path.write_text("")
        path.chmod(0)
        assert not os.access(path, os.R_OK) and not os.access(path, os.W_OK), (
            "the premise: this account can neither read nor write the file (not run as root)")
    return {}


def _what_stands(path):
    mode = os.lstat(path).st_mode
    return "link" if stat.S_ISLNK(mode) else "directory" if stat.S_ISDIR(mode) else oct(stat.S_IMODE(mode))


def _alerts(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning") for e in getattr(where, kind)]


def _picker(at):
    return list(at.sidebar.selectbox(key="chart_picker").options)


def _name_box(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()


def _click_save(at):
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()


def _start_delete(at, name):
    at.sidebar.selectbox(key="chart_picker").select(name).run()
    [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()


def _confirm_delete(at):
    at.sidebar.button(key="_delete_confirm").click().run()


# Another launch of the app: a process of its own, on the data folder its
# environment names, its lines read by a thread of its own so that every
# read is bounded. A refused flock says "waiting" once.
CHILD = textwrap.dedent("""
    import errno, json, os, sys
    sys.path[:0] = [{repo!r}]
    job = json.loads(sys.argv[1])
    if job.get("umask") is not None:
        os.umask(job["umask"])

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
    import ephemeris
    with open(job["folder_note"], "w") as note:      # the folder this launch made, for a kill to remove
        note.write(ephemeris._EPHEMERIS_FOLDER)
    if job["kind"] == "saver":
        say(event="ready")
        hear()
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts or {{}})
            charts[job["name"]] = job["value"]
            ok = engine.write_saved_charts(charts)
        say(event="result", ok=ok)
    elif job["kind"] == "holder":
        with engine.saved_charts_lock():
            say(event="in")
            hear()
        say(event="out")
    elif job["kind"] == "copier":
        import shutil
        from pathlib import Path
        legacy, target = Path(job["legacy"]), Path(job["target"])
        real_rename, real_copyfile = Path.rename, shutil.copyfile

        def rename(self, to):
            if Path(self) == legacy:
                raise PermissionError(errno.EACCES, "the move was refused (the test's)", str(self))
            return real_rename(self, to)

        def copyfile(src, dst, *args, **kwargs):
            if Path(src).name == "saved_charts.json":
                say(event="copying")
                hear()
            return real_copyfile(src, dst, *args, **kwargs)
        Path.rename, shutil.copyfile = rename, copyfile
        say(event="ready")
        hear()
        engine._make_user_data_dir(target)
        say(event="done")
    elif job["kind"] == "load":
        import resource
        with open("/proc/self/status") as status:
            size = [int(line.split()[1]) * 1024 for line in status if line.startswith("VmSize:")][0]
        resource.setrlimit(resource.RLIMIT_AS, (size + job["headroom"], resource.RLIM_INFINITY))
        try:
            charts = engine.load_saved_charts()
            say(event="result", charts=sorted(charts), error=None)
        except BaseException as exc:
            say(event="result", charts=None, error=type(exc).__name__)
""").format(repo=str(REPO))


class _Child:
    def __init__(self, job, env, log):
        self.log = log
        self._err = open(log, "w")
        self.folder_note = Path(f"{log}.ephemeris-folder")
        job = {**job, "folder_note": str(self.folder_note)}
        self.proc = subprocess.Popen([sys.executable, "-c", CHILD, json.dumps(job)], env=env, cwd=str(REPO),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err, text=True)
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
            raise AssertionError(f"expected {events} from the other launch, got {msg}; its stderr ends "
                                 f"{Path(self.log).read_text()[-2000:]}")
        return msg

    def tell(self, word="go"):
        self.proc.stdin.write(word + "\n")
        self.proc.stdin.flush()

    def kill(self):
        """End it now, by its own handle (a launch killed). A killed launch
        runs no exit hook, so the ephemeris folder its engine made in the
        temporary directory stays (FM2: removed at a normal exit only); this
        removes that folder, the one the child named, and nothing else."""
        self.proc.kill()
        self.proc.wait(timeout=WAIT)
        self._err.close()
        try:
            folder = Path(self.folder_note.read_text())
        except OSError:
            return                                  # killed before its engine was imported: no folder
        if folder.name.startswith("zij-ephemeris-") and folder.is_dir() and not folder.is_symlink():
            shutil.rmtree(folder)

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


def _child_env(tmp_path):
    return {**os.environ, "XDG_DATA_HOME": str(tmp_path), "ALMUTEN_NO_PREFERENCES": "1"}


# =============================================================================
# The umask first: the app's own lock file, whatever the umask
# =============================================================================

@pytest.mark.parametrize("mask", [0o222, 0o444], ids=["the owner's write taken", "the owner's read taken"])
def test_u1_another_launch_waits_on_a_lock_file_made_under_any_umask(scratch, tmp_path, mask):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    child = _Child({"kind": "saver", "name": "B", "value": REC, "umask": mask}, _child_env(tmp_path),
                   tmp_path / "child.log")
    try:
        child.expect("ready", timeout=LAUNCH)
        previous = os.umask(mask)
        try:
            with engine.saved_charts_lock():
                os.umask(previous)              # the lock file is made: the rest under the usual mask
                made = stat.S_IMODE(os.stat(engine.DATA_DIR / "saved_charts.lock").st_mode)
                # Ruling 157 (D-10): a lock file is made owner-only, 0600 cut by the umask.
                assert made == 0o600 & ~mask, f"the premise: the lock file made under the umask is {oct(made)}"
                charts = dict(engine.saved_charts_as_they_stand().charts)
                child.tell()
                first = child.expect("waiting", "result")
                charts["A"] = REC
                assert engine.write_saved_charts(charts), "this launch's save was refused"
        finally:
            os.umask(previous)
        last = first if first["event"] == "result" else child.expect("result")
    finally:
        child.close()
    assert last["ok"] is True, "the other launch's save was refused"
    assert first["event"] == "waiting", "the other launch went in without waiting on this launch's own lock file"
    held = json.loads(engine.SAVED_CHARTS_PATH.read_text())
    assert sorted(held) == ["A", "B", "X"], f"a save was lost: {sorted(held)}"


def test_u2_the_lock_file_a_launch_killed_while_holding_leaves_is_taken_as_the_lock(scratch, tmp_path):
    engine = _engine()
    child = _Child({"kind": "holder", "umask": 0o222}, _child_env(tmp_path), tmp_path / "child.log")
    try:
        child.expect("in", timeout=LAUNCH)
    finally:
        child.kill()
    path = engine.DATA_DIR / "saved_charts.lock"
    assert _what_stands(path) == "0o400", "the premise: the killed launch left its lock file, read-only"
    other = os.open(path, os.O_RDONLY)
    try:
        with engine.saved_charts_lock():
            held = _flock_refused(other)
            assert engine.write_saved_charts(XY) is True
    finally:
        os.close(other)
    assert held, "the lock file the killed launch left was passed over: nothing held it while this launch wrote"
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == XY
    assert _what_stands(path) == "0o400", "a lock file this launch could only read was removed or changed"


def test_u3_a_read_only_file_under_the_lock_name_is_locked_as_it_stands(scratch, tmp_path):
    engine = _engine()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "saved_charts.lock"
    path.write_text("")
    path.chmod(0o444)
    other = os.open(path, os.O_RDONLY)
    try:
        fd = engine._take_file_lock(path)
        assert fd is not None, "a read-only file under the lock name was passed over, not locked"
        try:
            assert _flock_refused(other), "the read-only lock file was opened but not locked"
        finally:
            engine._give_file_lock(fd, path)
        with engine.saved_charts_lock():
            assert engine.write_saved_charts(XY) is True
    finally:
        os.close(other)
        path.chmod(0o644)
    assert _folder(outside) == [], f"the lock made a file outside the data folder: {_folder(outside)}"
    assert os.path.lexists(path), "the read-only file was removed"
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == XY


def test_a_writable_lock_file_a_killed_launch_left_is_taken_and_removed(scratch, tmp_path):
    """Beside U2: under the usual umask the file a killed launch left is
    taken as the lock and removed at its release, as KS has it."""
    engine = _engine()
    child = _Child({"kind": "holder", "umask": 0o022}, _child_env(tmp_path), tmp_path / "child.log")
    try:
        child.expect("in", timeout=LAUNCH)
    finally:
        child.kill()
    path = engine.DATA_DIR / "saved_charts.lock"
    assert _what_stands(path) == "0o600", "the premise: the killed launch left its lock file (D-10: owner-only)"
    other = os.open(path, os.O_RDONLY)
    try:
        with engine.saved_charts_lock():
            held = _flock_refused(other)
            assert engine.write_saved_charts(XY) is True
    finally:
        os.close(other)
    assert held, "the lock file the killed launch left was passed over"
    assert not os.path.lexists(path), "the lock file was left after its release"


# =============================================================================
# Ruling 109: something standing under the lock's name refuses the write
# =============================================================================

KINDS = ["dangling link", "link to a file", "directory", "a file it can open in no way"]
STANDS = {"dangling link": "link", "link to a file": "link", "directory": "directory",
          "a file it can open in no way": "0o0"}


@pytest.mark.parametrize("kind", KINDS)
def test_r109_an_obstruction_under_the_stores_lock_refuses_the_save(scratch, tmp_path, kind):
    engine = _engine()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "saved_charts.lock"
    expected = _obstruct(path, kind, outside)
    assert _what_stands(path) == STANDS[kind], "the premise"
    try:
        what, value = _attempt(lambda: _save_under_the_lock(engine, "A"))
        after = _what_stands(path)
    finally:
        if kind == "a file it can open in no way":
            path.chmod(0o644)
    assert what == "raised", f"the save went ahead on the thread lock alone past the {kind} under the lock's name"
    assert type(value).__name__ == "DataLockBlocked", repr(value)
    assert Path(value.folder) == engine.DATA_DIR, f"the refusal named {value.folder}"
    assert not engine.SAVED_CHARTS_PATH.exists(), "the store was written"
    assert _folder(engine.DATA_DIR) == ["saved_charts.lock"], _folder(engine.DATA_DIR)
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == expected, (
        f"the lock made or moved a file outside the data folder: {_folder(outside)}")
    assert after == STANDS[kind], f"the obstruction was moved or changed: {after}"
    assert engine._STORE_THREAD_LOCK.acquire(timeout=0), "the thread lock was kept after the refusal"
    engine._STORE_THREAD_LOCK.release()


@pytest.mark.parametrize("op", ["remember", "forget"])
@pytest.mark.parametrize("kind", KINDS)
def test_r109_an_obstruction_under_the_preferences_lock_refuses_the_write(prefs_on, tmp_path, kind, op):
    engine = _engine()
    assert engine.write_preferences(FIRST_PREFS)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    path = engine.DATA_DIR / "preferences.lock"
    expected = _obstruct(path, kind, outside)
    standing = _what_stands(path)

    def write():
        kept = (engine.remember_preference("_wheel_dark", True) if op == "remember"
                else engine.forget_preference("last_chart"))
        return kept, engine.preferences_notices()
    try:
        what, (kept, notices) = _attempt(write)
        after = _what_stands(path)
    finally:
        if kind == "a file it can open in no way":
            path.chmod(0o644)
    assert what == "returned" and kept is False, f"the preference was written past the {kind} under the lock's name"
    assert notices.get("blocked") == str(engine.DATA_DIR) and notices.get("busy") is False, notices
    assert json.loads(engine.PREFERENCES_PATH.read_text()) == FIRST_PREFS, "the preferences file was written"
    assert _folder(engine.DATA_DIR) == ["preferences.json", "preferences.lock"], _folder(engine.DATA_DIR)
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == expected, _folder(outside)
    assert after == STANDS[kind], f"the obstruction was moved or changed: {after}"


@pytest.mark.parametrize("what", ["charts", "prefs"])
def test_r109_an_obstruction_beside_a_linked_files_target_refuses_the_write(prefs_on, tmp_path, what):
    engine = _engine()
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / ("charts.json" if what == "charts" else "prefs.json")
    before = json.dumps({"X": REC} if what == "charts" else FIRST_PREFS, indent=2)
    target.write_text(before)
    own = engine.SAVED_CHARTS_PATH if what == "charts" else engine.PREFERENCES_PATH
    own.symlink_to(target)
    lock_name = "saved_charts.lock" if what == "charts" else "preferences.lock"
    (shared / lock_name).mkdir()
    if what == "charts":
        outcome, value = _attempt(lambda: _save_under_the_lock(engine, "A"))
        refused = outcome == "raised" and type(value).__name__ == "DataLockBlocked"
        named = getattr(value, "folder", None)
    else:
        outcome, (kept, notices) = _attempt(lambda: (engine.remember_preference("_wheel_dark", True),
                                                    engine.preferences_notices()))
        refused, named = kept is False, notices.get("blocked")
    assert refused, f"the write went ahead past the directory under the lock's name beside {target.name}"
    assert Path(named) == shared, f"the refusal named {named}, not the linked file's folder"
    assert target.read_text() == before, "the linked file was written"
    assert _folder(shared) == sorted([target.name, lock_name]), _folder(shared)
    assert _folder(engine.DATA_DIR) == [own.name], f"a lock file was left in the data folder: {_folder(engine.DATA_DIR)}"


def test_with_no_lock_call_an_obstruction_still_falls_back_to_the_thread_lock(scratch, monkeypatch):
    """Ruling 109 keeps ruling 63's fallback where the system has no lock
    call: the save goes ahead on the thread lock, the obstruction stays."""
    engine = _engine()
    monkeypatch.setattr(engine, "fcntl", None)
    monkeypatch.setattr(engine, "msvcrt", None)
    path = engine.DATA_DIR / "saved_charts.lock"
    path.mkdir()
    assert _attempt(lambda: _save_under_the_lock(engine, "A")) == ("returned", True)
    assert sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == ["A"]
    assert path.is_dir()


def test_a_filesystem_that_refuses_locks_refuses_the_write(scratch, monkeypatch):
    """Ruling 63's fallback no longer holds where the filesystem refuses
    locks (a network share: flock answers ENOLCK): the write is refused
    (DataLockUnavailable), and nothing is written."""
    import fcntl
    engine = _engine()
    calls = []

    def refusing(fd, op):
        calls.append(op)
        raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))
    monkeypatch.setattr(fcntl, "flock", refusing)
    outcome, value = _attempt(lambda: _save_under_the_lock(engine, "A"))
    assert outcome == "raised" and type(value) is engine.DataLockUnavailable, (outcome, value)
    assert calls, "the premise: the lock was asked for and refused"
    assert not engine.SAVED_CHARTS_PATH.exists()


def test_a_data_folder_this_account_cannot_search_is_no_obstruction(scratch):
    """What cannot be looked at is not something standing under the name: a
    data folder this account may read but not search (the name's lstat is
    refused) is the folder's own case, said by the folder's sentence; the
    lock falls back and the write fails as a write."""
    engine = _engine()
    engine.DATA_DIR.chmod(0o600)
    try:
        outcome = _attempt(lambda: _save_under_the_lock(engine, "A"))
    finally:
        engine.DATA_DIR.chmod(0o755)
    assert outcome == ("returned", False), outcome
    assert _folder(engine.DATA_DIR) == [], _folder(engine.DATA_DIR)


@pytest.mark.parametrize("act", ["save", "delete"])
def test_r109_a_save_or_delete_past_an_obstruction_says_so_in_its_run_and_window(scratch, act):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    a.run()
    b = make_app(date="1983-11-19", page="sources", timeout=300).run()
    lock = engine.DATA_DIR / "saved_charts.lock"
    lock.mkdir()
    if act == "save":
        _name_box(a, "Z")
        _click_save(a)
    else:
        _start_delete(a, "Y")
        _confirm_delete(a)
    assert_no_exception(a, act)
    sentence = STORE_BLOCKED.format(folder=engine.DATA_DIR)
    said = _alerts(a)
    assert engine.SAVED_CHARTS_PATH.read_text() == json.dumps(XY, indent=2), f"the {act} was written"
    assert said.count(sentence) == 1, said
    assert lock.is_dir(), "the obstruction was moved"
    assert sorted(_picker(a)) == [NEW_CHART, "X", "Y"], _picker(a)
    b.run()
    assert sentence not in _alerts(b), "said in a window that made no write"


@pytest.mark.parametrize("act", ["set as home", "forget home", "dark wheel"])
def test_r109_a_preference_write_past_an_obstruction_says_so_in_its_run_and_window(prefs_on, act):
    engine = _engine()
    engine.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    if act == "forget home":
        engine.PREFERENCES_PATH.write_text(json.dumps({"home_place": HOME}))
    a = make_app(date="1983-11-19", page="chart", timeout=300).run()
    b = make_app(date="1983-11-19", page="chart", timeout=300).run()
    lock = engine.DATA_DIR / "preferences.lock"
    lock.mkdir()
    if act == "set as home":
        a.sidebar.button(key="_set_home").click().run()
    elif act == "forget home":
        a.sidebar.button(key="_forget_home").click().run()
    else:
        [c for c in a.main.checkbox if c.label == "Dark wheel"][0].check().run()
    assert_no_exception(a, act)
    sentence = PREFS_BLOCKED.format(folder=engine.DATA_DIR)
    said = _alerts(a)
    assert not [t for t in said if t.startswith("The preferences file was not written")
                or t.startswith("This place could not be kept") or t.startswith("This home could not be")], (
        f"a second sentence was said of the one refusal: {said}")
    held = json.loads(engine.PREFERENCES_PATH.read_text())
    if act == "set as home":
        assert "home_place" not in held, f"{act} was written: {held}"
    elif act == "forget home":
        assert held.get("home_place") == HOME, f"{act} was written: {held}"
    else:
        assert held.get("_wheel_dark") is not True, f"{act} was written: {held}"
    assert said.count(sentence) == 1, said
    assert lock.is_dir(), "the obstruction was moved"
    b.run()
    assert sentence not in _alerts(b), "said in a window that made no write"


# =============================================================================
# S02 (SC2's check, finding 3): the old store's move at a busy load
# =============================================================================

def _old_store_beside_the_app(engine, monkeypatch, tmp_path):
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    assert not engine.SAVED_CHARTS_PATH.exists(), "the premise: no store yet, so the old one is to be moved"
    return legacy


def _launch_while_the_store_is_held(engine, at):
    """The window's first run while another holds the store's lock past
    its bound."""
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        at.run()
    finally:
        engine._STORE_THREAD_LOCK.release()
    assert "Old" not in _picker(at), "the premise: the load could not move the old store"


def test_s02_a_load_that_could_not_move_the_old_store_says_so(scratch, monkeypatch, tmp_path):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = _old_store_beside_the_app(engine, monkeypatch, tmp_path)
    _launch_while_the_store_is_held(engine, at)
    assert_no_exception(at, "the launch")
    assert _alerts(at).count(STORE_UNMOVED) == 1, _alerts(at)
    at.run()
    assert STORE_UNMOVED not in _alerts(at), "said again on the next run"
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file was changed"


def test_s02_a_save_after_that_load_brings_the_old_store_in(scratch, monkeypatch, tmp_path):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = _old_store_beside_the_app(engine, monkeypatch, tmp_path)
    _launch_while_the_store_is_held(engine, at)
    _name_box(at, "New")
    _click_save(at)
    assert_no_exception(at, "the save")
    held = json.loads(engine.SAVED_CHARTS_PATH.read_text())
    assert sorted(held) == ["New", "Old"], f"the save left the old store unmoved: {sorted(held)}"
    assert sorted(_picker(at)) == [NEW_CHART, "New", "Old"], _picker(at)
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file was changed"


def test_s02_a_load_that_could_not_move_the_old_store_past_an_obstruction_says_ruling_109s_sentence(
        scratch, monkeypatch, tmp_path):
    """Beside S02's pins: where the move met something standing under the
    store's lock name, the load says ruling 109's sentence, once."""
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = _old_store_beside_the_app(engine, monkeypatch, tmp_path)
    (engine.DATA_DIR / "saved_charts.lock").mkdir()
    at.run()
    assert_no_exception(at, "the launch")
    assert "Old" not in _picker(at), "the old store was moved in past the directory under the lock's name"
    assert _alerts(at).count(STORE_BLOCKED.format(folder=engine.DATA_DIR)) == 1, _alerts(at)
    assert STORE_UNMOVED not in _alerts(at), _alerts(at)
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file was changed"


# =============================================================================
# N05 (SC2's check, finding 6): the former folder's copy
# =============================================================================

def _former_folder(engine, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    legacy = base / engine._LEGACY_APP_DIR_NAME
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"Old": REC}, indent=2))
    (legacy / "preferences.json").write_text(json.dumps({"_launches": 3}, indent=2))
    return base, legacy, base / engine.APP_DIR_NAME


def _refuse_the_move(monkeypatch, legacy):
    real_rename = Path.rename

    def rename(self, target):
        if Path(self) == legacy:
            raise PermissionError(errno.EACCES, "the move was refused (the test's)", str(self))
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", rename)


@pytest.mark.parametrize("how", ["before any byte", "half way"])
def test_n05_a_store_the_copy_could_not_make_whole_is_listed_from_the_former_folder(scratch, monkeypatch,
                                                                                     tmp_path, how):
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    _refuse_the_move(monkeypatch, legacy)
    real_copyfile = shutil.copyfile

    def copyfile(src, dst, *args, **kwargs):
        if Path(src).name == "saved_charts.json":
            if how == "half way":
                Path(dst).write_bytes(Path(src).read_bytes()[:20])
            raise OSError(errno.EIO, "the copy failed (the test's)", str(src))
        return real_copyfile(src, dst, *args, **kwargs)
    monkeypatch.setattr(shutil, "copyfile", copyfile)
    assert engine._make_user_data_dir(target) == target
    monkeypatch.setattr(shutil, "copyfile", real_copyfile)
    monkeypatch.setattr(engine, "SAVED_CHARTS_PATH", target / "saved_charts.json")
    charts = engine.load_saved_charts()
    notices = engine.store_notices()
    assert charts == {"Old": REC}, f"the former folder's charts are not listed: {charts}"
    assert notices["copy"] is None and notices["unreadable"] is False, f"a copy cut short was read: {notices}"
    assert not list(target.glob("saved_charts.json.unreadable-*")), _folder(target)
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"
    assert _folder(base) == sorted([legacy.name, target.name]), _folder(base)


def test_n05_a_copy_a_launch_killed_mid_copy_left_is_removed_by_a_later_launch(scratch, monkeypatch, tmp_path):
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    child = _Child({"kind": "copier", "legacy": str(legacy), "target": str(target)}, _child_env(tmp_path),
                   tmp_path / "child.log")
    try:
        child.expect("ready", timeout=LAUNCH)
        child.tell()
        child.expect("copying")
    finally:
        child.kill()
    left = [name for name in _folder(base) if name.endswith(".copying")]
    assert len(left) == 1, f"the premise: the killed launch left its copy: {_folder(base)}"
    _refuse_the_move(monkeypatch, legacy)
    assert engine._make_user_data_dir(target) == target
    assert _folder(base) == sorted([legacy.name, target.name]), f"the killed launch's copy is still there: {_folder(base)}"
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}
    assert json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, "the former folder was changed"


def test_n05_a_copy_another_launch_is_still_making_is_left(scratch, monkeypatch, tmp_path):
    """Beside N05's pin: a later launch removes only a copy no launch is
    making any more; one still being made is left to its maker, which
    then finds the data folder made and removes its own."""
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    child = _Child({"kind": "copier", "legacy": str(legacy), "target": str(target)}, _child_env(tmp_path),
                   tmp_path / "child.log")
    try:
        child.expect("ready", timeout=LAUNCH)
        child.tell()
        child.expect("copying")
        making = [base / name for name in _folder(base) if name.endswith(".copying")]
        assert len(making) == 1, f"the premise: the other launch's copy is being made: {_folder(base)}"
        _refuse_the_move(monkeypatch, legacy)
        assert engine._make_user_data_dir(target) == target
        assert making[0].is_dir(), "a copy another launch was still making was removed"
        child.tell()
        child.expect("done")
    finally:
        child.close()
    assert _folder(base) == sorted([legacy.name, target.name]), _folder(base)
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_n05_a_dead_copy_holding_what_the_former_folder_does_not_is_left(scratch, monkeypatch, tmp_path):
    """Beside N05's pin: a copy no launch holds is removed only while it is
    nothing but a copy of what the former folder holds; one holding other
    bytes (the former folder changed since) is left, so that nothing is
    lost."""
    engine = _engine()
    base, legacy, target = _former_folder(engine, tmp_path)
    left = base / f".{target.name}.0123456789abcdef.copying"
    left.mkdir()
    (left / "saved_charts.json").write_text(json.dumps({"Kept only here": REC}, indent=2))
    _refuse_the_move(monkeypatch, legacy)
    assert engine._make_user_data_dir(target) == target
    assert json.loads((left / "saved_charts.json").read_text()) == {"Kept only here": REC}, (
        "a copy holding bytes the former folder does not was removed")
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


# =============================================================================
# S04 (SC2's check, finding 8): a deeply nested file at the load
# =============================================================================

# A record holding a thousand lists nested six hundred deep: 1.2 MB of
# JSON, whose text as the writer makes it (indented) is some 700 MB.
DEEP_BRANCH = "[" * 600 + "]" * 600
DEEP = '{"A": {"deep": [' + ",".join([DEEP_BRANCH] * 1000) + "]}}"
HEADROOM = 512 * 1024 * 1024      # bytes of address space the loading launch may take beyond what it holds


@pytest.mark.parametrize("where", ["a stray", "the store"])
def test_s04_a_deeply_nested_file_is_judged_without_running_out_of_memory(scratch, tmp_path, where):
    engine = _engine()
    if where == "a stray":
        engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
        planted = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp")
    else:
        planted = engine.SAVED_CHARTS_PATH
    planted.write_text(DEEP)
    os.utime(planted, (0, 0))
    child = _Child({"kind": "load", "headroom": HEADROOM}, _child_env(tmp_path), tmp_path / "child.log")
    try:
        result = child.expect("result", timeout=LAUNCH)
    finally:
        child.close()
    assert result["error"] is None, f"the load raised {result['error']}"
    if where == "a stray":
        assert result["charts"] == ["X"], result
        assert not planted.exists(), "a stray this app could not write back was kept as a save"
        assert not list(engine.DATA_DIR.glob("saved_charts.json.recovered-*")), _folder(engine.DATA_DIR)
    else:
        assert result["charts"] == [], result
        copies = list(engine.DATA_DIR.glob("saved_charts.json.unreadable-*"))
        assert len(copies) == 1 and copies[0].read_text() == DEEP, "the store's bytes were not kept aside"


# =============================================================================
# S06 (SC2's check, finding 12): a stored standard of invisible characters
# =============================================================================

@pytest.mark.parametrize("label", ["​", "⁦‎⁩"], ids=["zero-width space", "isolates and a mark"])
def test_s06_a_stored_standard_of_invisible_characters_is_said_empty(scratch, label):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"E": dict(REC, time_standard=label)}, indent=2))
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    at.sidebar.selectbox(key="chart_picker").select("E").run()
    assert_no_exception(at, "opening E")
    named = [w.value for w in at.sidebar.warning if w.value.startswith("'E' was saved with")]
    assert len(named) == 1, [w.value for w in at.sidebar.warning]
    assert named[0].startswith("'E' was saved with its time standard empty; it is cast under LMT (Local Mean Time)."), (
        named[0])


# =============================================================================
# N04 (SC2's check, finding 14): the revolution's star table
# =============================================================================

def _algol_unread_when(monkeypatch, unread):
    """Algol's read refused by the catalogue whenever `unread(jd)` holds
    (the date-dependent failure, injected at the catalogue's read)."""
    import swisseph as swe
    real_star = swe.fixstar2_ut

    def flaky(name, jd, *args, **kwargs):
        if name == "Algol" and unread(jd):
            raise OSError("not read on this date (the test's)")
        return real_star(name, jd, *args, **kwargs)
    monkeypatch.setattr(swe, "fixstar2_ut", flaky)


def test_n04_the_revolutions_star_table_names_a_star_it_could_not_place(scratch, monkeypatch):
    engine = _engine()
    assert engine._fixed_star_catalogue_ready() is True, "the premise: the shipped catalogue is attached"
    jd_root, jd_rev = 2451545.5, 2451910.5
    sr = {"planetary_data": {"Sun": {"longitude": 10.0}, "Moon": {"longitude": 200.0}},
          "ascendant": engine.fixed_star_longitudes(jd_rev)["Algol"], "mc": 270.0}
    algol = engine.FIXED_STAR_PAGE_NAME.get("Algol", "Algol")
    placed = engine.pn4_fixed_stars_in_revolution(sr, jd_rev, 100.0, None)
    assert [r for r in placed["rows"] if r["Star"] == algol], "the premise: Algol stands on the year's Ascendant"
    _algol_unread_when(monkeypatch, lambda jd: jd == jd_rev)
    out = engine.pn4_fixed_stars_in_revolution(sr, jd_rev, 100.0, None)
    root = engine.pn4_fixed_stars_in_image({"planetary_data": {"Sun": {"longitude": 10.0},
                                                               "Moon": {"longitude": 200.0}},
                                            "ascendant": 0.0, "mc": 270.0}, jd_root)
    assert not [r for r in out["rows"] if r["Star"] == algol], "the premise: Algol's row is dropped"
    assert out.get("missing") == MISSING_ALGOL, f"the revolution's table said nothing of Algol: {out.get('missing')!r}"
    assert root["missing"] == "", root["missing"]


def test_n04_the_page_says_the_revolutions_missing_star(scratch, monkeypatch):
    at = make_app(page="timing", timeout=300)
    engine = _engine()
    assert engine._fixed_star_catalogue_ready() is True, "the premise: the shipped catalogue is attached"
    in_revolution = threading.Event()
    real = engine.pn4_fixed_stars_in_revolution

    def revolution(*args, **kwargs):
        in_revolution.set()
        try:
            return real(*args, **kwargs)
        finally:
            in_revolution.clear()
    monkeypatch.setattr(engine, "pn4_fixed_stars_in_revolution", revolution)
    _algol_unread_when(monkeypatch, lambda jd: in_revolution.is_set())
    at.run()
    assert_no_exception(at, "the Timing page")
    warnings = [w.value for w in at.main.warning]
    assert warnings.count(MISSING_ALGOL) == 1, warnings


# =============================================================================
# After the blind check (SC3_CHECK.md: findings 2 and 10, the notes on the sentences)
# =============================================================================

def test_f2_a_lock_file_let_go_between_a_refused_open_and_the_look_is_taken_again(scratch, tmp_path, monkeypatch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}, indent=2))
    env = _child_env(tmp_path)
    holder = _Child({"kind": "holder", "umask": 0o222}, env, tmp_path / "holder.log")
    third = _Child({"kind": "saver", "name": "B", "value": REC, "umask": 0o022}, env, tmp_path / "third.log")
    path = engine.DATA_DIR / "saved_charts.lock"
    let_go = []
    try:
        holder.expect("in", timeout=LAUNCH)
        third.expect("ready", timeout=LAUNCH)
        assert _what_stands(path) == "0o400", "the premise: the holder's own lock file is read-only"
        real_open = os.open

        def opening(file, flags, *args, **kwargs):
            try:
                return real_open(file, flags, *args, **kwargs)
            except OSError:
                if Path(file) == path and not let_go and threading.current_thread().name == "window":
                    let_go.append(flags)
                    holder.tell()                   # its holder lets the file go (unlinks it) just now
                    holder.expect("out")
                raise
        monkeypatch.setattr(os, "open", opening)

        def save():
            with engine.saved_charts_lock():
                charts = dict(engine.saved_charts_as_they_stand().charts)
                third.tell()
                seen = third.expect("waiting", "result")
                charts["A"] = REC
                assert engine.write_saved_charts(charts), "this launch's save was refused"
            return seen
        what, first = _attempt(save)
        monkeypatch.setattr(os, "open", real_open)
        assert what == "returned", repr(first)
        last = first if first["event"] == "result" else third.expect("result")
    finally:
        holder.close()
        third.close()
    assert let_go, "the premise: this launch's open met the read-only file, and its holder let it go then"
    assert first["event"] == "waiting", (
        "another launch went in while this one was inside: this one had entered without the file lock")
    assert last["ok"] is True
    held = json.loads(engine.SAVED_CHARTS_PATH.read_text())
    assert sorted(held) == ["A", "B", "X"], f"a save was lost: {sorted(held)}"


def test_f10_the_writer_writes_no_store_its_own_load_would_refuse(scratch, monkeypatch):
    engine = _engine()
    assert engine.write_saved_charts({"X": REC}) is True
    bigger = {"X": REC, "Y": REC}
    text = json.dumps(bigger, indent=2)
    monkeypatch.setattr(engine, "STORE_TEXT_LIMIT", len(text) - 1)
    assert engine.write_saved_charts(bigger) is False, "the app wrote a store its own load will not read"
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == {"X": REC}, "the store was written"
    assert engine.load_saved_charts() == {"X": REC}
    monkeypatch.setattr(engine, "STORE_TEXT_LIMIT", len(text))
    assert engine.write_saved_charts(bigger) is True, "a store at the limit was refused"
    assert engine.load_saved_charts() == bigger


def test_f10_a_save_past_the_limit_is_refused_as_any_refused_save(scratch, monkeypatch):
    a = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    monkeypatch.setattr(engine, "STORE_TEXT_LIMIT", len(json.dumps(XY, indent=2)) + 10)
    a.run()
    _name_box(a, "Z")
    _click_save(a)
    assert_no_exception(a, "the save")
    assert engine.SAVED_CHARTS_PATH.read_text() == json.dumps(XY, indent=2), "a store past the limit was written"
    assert _alerts(a).count(SAVE_REFUSED) == 1, _alerts(a)
    assert sorted(_picker(a)) == [NEW_CHART, "X", "Y"], _picker(a)


def test_s02_an_old_store_that_does_not_read_is_not_promised_by_the_sentence(scratch, monkeypatch, tmp_path):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text("{not json")
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        at.run()
    finally:
        engine._STORE_THREAD_LOCK.release()
    assert_no_exception(at, "the launch")
    assert STORE_UNMOVED not in _alerts(at), "a reload was promised to list charts that do not read"
    assert legacy.read_text() == "{not json", "the old file was changed"


def test_s02_an_old_store_holding_no_chart_is_not_promised_by_the_sentence(scratch, monkeypatch, tmp_path):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text("{}")                 # what an older version wrote after its last chart was deleted
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        at.run()
    finally:
        engine._STORE_THREAD_LOCK.release()
    assert_no_exception(at, "the launch")
    assert STORE_UNMOVED not in _alerts(at), "a reload was promised to list charts an old store does not hold"
    assert legacy.read_text() == "{}", "the old file was changed"


def test_s02_a_load_in_a_folder_that_cannot_be_written_in_does_not_promise_a_reload(scratch, monkeypatch, tmp_path):
    """Beside the pin above: where the data folder cannot be written in, a
    reload would not move the old store in either; the folder's sentence
    speaks, and S02's is not said."""
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = _old_store_beside_the_app(engine, monkeypatch, tmp_path)
    engine.DATA_DIR.chmod(0o555)
    try:
        _launch_while_the_store_is_held(engine, at)
        said = _alerts(at)
    finally:
        engine.DATA_DIR.chmod(0o755)
    assert_no_exception(at, "the launch")
    assert [t for t in said if t.startswith("Saved charts and preferences cannot be kept: their folder")], (
        f"the premise: the folder's own sentence: {said}")
    assert STORE_UNMOVED not in said, "a reload was promised where it cannot move the old store in"
    assert json.loads(legacy.read_text()) == {"Old": REC}, "the old file was changed"


@pytest.mark.parametrize("which", ["a new chart", "an unchanged chart"])
def test_a_save_says_no_preferences_refusal_for_the_last_chart_it_remembers(prefs_on, which):
    engine = _engine()
    engine.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    a = make_app(date="1983-11-19", page="sources", timeout=300).run()
    if which == "an unchanged chart":
        a.sidebar.selectbox(key="chart_picker").select("X").run()
    (engine.DATA_DIR / "preferences.lock").mkdir()
    _name_box(a, "Z" if which == "a new chart" else "X")
    _click_save(a)
    assert_no_exception(a, "the save")
    sentence = PREFS_BLOCKED.format(folder=engine.DATA_DIR)
    if which == "an unchanged chart":
        assert "'X' is already saved as it is." in [i.value for i in a.sidebar.info], (
            "the premise: the Save met the chart unchanged (ruling 78's path)")
    else:
        assert "Saved 'Z'." in [s.value for s in a.sidebar.success], "the premise: the Save said it was saved"
    assert sentence not in _alerts(a), "the Save's own remembering of its chart was said as a refused choice"
    assert sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == (
        ["X", "Y", "Z"] if which == "a new chart" else ["X", "Y"]), "the premise: the save was made"
