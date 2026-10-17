"""Saves where the lock call fails, and saves kept through a crash of the system.

A lock call that fails for any reason but another holder's (a network folder
with no lock service: ENOLCK; a filesystem that does not support locks:
EOPNOTSUPP) refuses the write: nothing is written, and the sidebar says why.
The thread lock alone serves only where the system has no lock call at all:
no lock module, or a call that answers ENOSYS. A lock held by another stays
"busy", as before.

A write of the saved charts or the preferences syncs its temporary file
before the replace and, on Linux and macOS, the folder after it; a folder
whose sync is refused leaves the write standing.

Every wait on another process is bounded, so a lock that never comes free
fails the test rather than hanging the suite.
"""
import ast
import errno
import json
import os
import stat
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

REPO = Path(APP_PATH).resolve().parent
WAIT = 120            # seconds: the bound on every wait for another thread or process
LAUNCH = 600          # seconds: the bound on a child process's import of the engine
SHORT = 1.0           # seconds: the locks' bound where a test shortens it

REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
XY = {"X": REC, "Y": dict(REC, date_string="1990-01-01")}
NEW_CHART = "-- New Chart --"

# The sidebar's sentence for a save, a delete or a move refused so.
STORE_UNLOCKED = ("Charts cannot be saved or deleted, because their folder could not be locked "
                  "against two windows saving at once. Nothing was changed.")
STORE_BUSY = ("Another window of this app is holding the saved charts just now, "
              "so nothing was written. Try again in a moment.")
STORE_UNMOVED = ("Another window was using the saved charts when this one opened, so charts kept by an older "
                 "version of the app are not listed yet. Reload the page to list them.")
PREFS_REFUSED = ("The preferences file was not written, so this choice was not kept. "
                 "Try again once it can be written.")

REFUSING = [errno.ENOLCK, errno.EOPNOTSUPP, errno.EINVAL, errno.EIO]


def _engine():
    sync_engine_to_environment()
    import engine
    return engine


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable data folder; preferences off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    engine = _engine()
    assert Path(engine.DATA_DIR).resolve().is_relative_to(tmp_path.resolve()), engine.DATA_DIR
    return tmp_path


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    """A disposable data folder with the preferences file live."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    engine = _engine()
    assert Path(engine.DATA_DIR).resolve().is_relative_to(tmp_path.resolve()), engine.DATA_DIR
    return tmp_path


class _Fcntl:
    """The engine's fcntl, with flock answering `code` (an errno) every
    time; everything else is the real module's."""

    def __init__(self, code):
        import fcntl
        self._real, self.code, self.calls = fcntl, code, []

    def flock(self, fd, op):
        self.calls.append(op)
        raise OSError(self.code, os.strerror(self.code))

    def __getattr__(self, name):
        return getattr(self._real, name)


def _refuse_lock_calls(engine, monkeypatch, code):
    fake = _Fcntl(code)
    monkeypatch.setattr(engine, "fcntl", fake)
    return fake


def _save_under_the_lock(engine, name):
    """A save as the app makes one: under the store's lock, the store as it
    stands, the record put in, the whole written."""
    with engine.saved_charts_lock():
        charts = dict(engine.saved_charts_as_they_stand().charts or {})
        charts[name] = REC
        return engine.write_saved_charts(charts)


def _attempt(fn):
    """('returned', value) or ('raised', exception), within WAIT, in a
    thread of its own (as a window's script runs)."""
    box = {}

    def run():
        try:
            box["returned"] = fn()
        except BaseException as exc:            # given back below
            box["raised"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(WAIT)
    assert not thread.is_alive(), f"the attempt did not finish within {WAIT}s"
    return next(iter(box.items()))


def _alerts(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning") for e in getattr(where, kind)]


def _picker(at):
    return list(at.sidebar.selectbox(key="chart_picker").options)


# =============================================================================
# The lock call refused
# =============================================================================

@pytest.mark.parametrize("code", REFUSING, ids=[errno.errorcode[c] for c in REFUSING])
def test_a_lock_call_that_fails_refuses_the_save_and_leaves_the_store(scratch, monkeypatch, code):
    engine = _engine()
    before = json.dumps(XY, indent=2)
    engine.SAVED_CHARTS_PATH.write_text(before)
    fake = _refuse_lock_calls(engine, monkeypatch, code)
    outcome, value = _attempt(lambda: _save_under_the_lock(engine, "Z"))
    assert fake.calls, "the premise: the lock was asked for"
    assert outcome == "raised" and type(value) is engine.DataLockUnavailable, (outcome, value)
    assert isinstance(value, engine.DataLockBusy), "whatever gives up on a busy lock must give up here"
    assert Path(value.folder) == engine.DATA_DIR, value.folder
    assert engine.SAVED_CHARTS_PATH.read_text() == before, "the store was written past a refused lock call"
    assert not engine._STORE_THREAD_LOCK.locked(), "the thread lock was left held"


def test_with_a_lock_call_that_answers_enosys_the_thread_lock_alone_serves(scratch, monkeypatch):
    engine = _engine()
    fake = _refuse_lock_calls(engine, monkeypatch, errno.ENOSYS)
    assert _attempt(lambda: _save_under_the_lock(engine, "A")) == ("returned", True)
    assert fake.calls, "the premise: the lock was asked for"
    assert sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == ["A"]


def test_with_no_lock_module_the_thread_lock_alone_serves(scratch, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(engine, "fcntl", None)
    monkeypatch.setattr(engine, "msvcrt", None)
    assert _attempt(lambda: _save_under_the_lock(engine, "A")) == ("returned", True)
    assert sorted(json.loads(engine.SAVED_CHARTS_PATH.read_text())) == ["A"]


@pytest.mark.parametrize("code", REFUSING[:2], ids=[errno.errorcode[c] for c in REFUSING[:2]])
def test_a_lock_call_that_fails_on_windows_refuses_the_save(scratch, monkeypatch, code):
    """The same on Windows' branch: msvcrt's lock answering an error that
    is not another holder's."""
    engine = _engine()
    calls = []

    class FakeMsvcrt:
        LK_NBLCK, LK_UNLCK = 2, 0

        @staticmethod
        def locking(fd, mode, nbytes):
            calls.append(mode)
            raise OSError(code, os.strerror(code))
    monkeypatch.setattr(engine, "fcntl", None)
    monkeypatch.setattr(engine, "msvcrt", FakeMsvcrt)
    outcome, value = _attempt(lambda: _save_under_the_lock(engine, "Z"))
    assert calls and outcome == "raised" and type(value) is engine.DataLockUnavailable, (calls, outcome, value)
    assert not engine.SAVED_CHARTS_PATH.exists(), "the store was written past a refused lock call"


def test_a_lock_held_by_another_is_still_busy(scratch, monkeypatch):
    """Another holder's refusal (EWOULDBLOCK) is waited on to the bound and
    gives DataLockBusy itself, not the refusal of the call."""
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    fake = _refuse_lock_calls(engine, monkeypatch, errno.EWOULDBLOCK)
    outcome, value = _attempt(lambda: _save_under_the_lock(engine, "Z"))
    assert len(fake.calls) > 1, "the premise: the lock was asked for again while it was held"
    assert outcome == "raised" and type(value) is engine.DataLockBusy, (outcome, value)
    assert not engine.SAVED_CHARTS_PATH.exists()


def test_a_refused_lock_call_beside_a_linked_store_refuses_the_save(scratch, monkeypatch, tmp_path):
    """A store kept as a link to a file in another folder: the lock beside
    that file refused by its folder refuses the save, though the data
    folder's lock was had."""
    import fcntl
    engine = _engine()
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "saved_charts.json"
    before = json.dumps(XY, indent=2)
    target.write_text(before)
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    real_flock = fcntl.flock

    class Fake(_Fcntl):
        """flock refused on the lock file beside the linked store only."""

        def flock(self, fd, op):
            beside = shared / "saved_charts.lock"
            if beside.exists() and os.path.samestat(os.fstat(fd), os.stat(beside)):
                self.calls.append(op)
                raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))
            return real_flock(fd, op)
    fake = Fake(errno.ENOLCK)
    monkeypatch.setattr(engine, "fcntl", fake)
    outcome, value = _attempt(lambda: _save_under_the_lock(engine, "Z"))
    assert fake.calls, "the premise: the lock beside the linked store was asked for"
    assert outcome == "raised" and type(value) is engine.DataLockUnavailable, (outcome, value)
    assert Path(value.folder) == shared, value.folder
    assert target.read_text() == before, "the linked store was written past a refused lock call"


def test_a_refused_lock_call_refuses_a_preference_and_breaks_nothing(prefs_on, monkeypatch):
    engine = _engine()
    before = json.dumps({"_launches": 3, "last_chart": "X"}, indent=2)
    engine.PREFERENCES_PATH.write_text(before)
    _refuse_lock_calls(engine, monkeypatch, errno.ENOLCK)
    for write in (lambda: engine.remember_preference("last_chart", "Y"),
                  lambda: engine.forget_preference("last_chart")):
        assert _attempt(lambda: (write(), engine.preferences_notices())) == (
            "returned", (False, {"copy": None, "unreadable": False, "busy": False, "blocked": None, "off": False}))
        assert engine.LAST_PREFERENCES_BUSY is False, "said as another window's hold"
        assert engine.PREFERENCES_PATH.read_text() == before, "the preferences were written past a refused lock"


def test_a_refused_lock_call_at_the_load_leaves_the_old_store_where_it_is(scratch, monkeypatch, tmp_path):
    """A lock call refused while the store is read and tidied at the load:
    the load still lists the store, tidies nothing, and moves no old store
    in; store_notices says the lock call was refused."""
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps(XY, indent=2))
    stray = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp")
    stray.write_text(json.dumps({"Cut": REC}))
    os.utime(stray, (1, 1))
    _refuse_lock_calls(engine, monkeypatch, errno.ENOLCK)
    outcome, (charts, notices) = _attempt(lambda: (engine.load_saved_charts(), engine.store_notices()))
    assert outcome == "returned" and sorted(charts) == ["X", "Y"], charts
    assert stray.exists() and notices["recovered"] == 0, "a stray was tidied without the lock"

    engine.SAVED_CHARTS_PATH.unlink()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    outcome, (charts, notices) = _attempt(lambda: (engine.load_saved_charts(), engine.store_notices()))
    assert outcome == "returned" and not engine.SAVED_CHARTS_PATH.exists(), "the old store was moved in unlocked"
    assert notices["unmoved"] and notices["unlocked"] and notices["blocked"] is None, notices
    assert json.loads(legacy.read_text()) == {"Old": REC}


# Another launch of the app: a process of its own, on the data folder its
# environment names, its lock calls refused with ENOLCK. It reads the store,
# says so, waits for the word, then puts its record in and writes.
CHILD = textwrap.dedent("""
    import errno, json, os, sys
    sys.path[:0] = [{repo!r}]
    import engine

    class Refusing:
        def __init__(self, real):
            self._real = real
        def flock(self, fd, op):
            raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))
        def __getattr__(self, name):
            return getattr(self._real, name)
    engine.fcntl = Refusing(engine.fcntl)
    name = sys.argv[1]
    try:
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts or {{}})
            print(json.dumps({{"read": sorted(charts)}}), flush=True)
            sys.stdin.readline()
            charts[name] = {{"date_string": "1983-11-19"}}
            print(json.dumps({{"wrote": engine.write_saved_charts(charts)}}), flush=True)
    except engine.DataLockUnavailable:
        print(json.dumps({{"refused": True}}), flush=True)
""")


def test_two_launches_on_a_folder_that_refuses_locks_report_no_save_they_did_not_make(scratch, tmp_path):
    engine = _engine()
    before = json.dumps({"Existing": REC}, indent=2)
    engine.SAVED_CHARTS_PATH.write_text(before)
    env = dict(os.environ, XDG_DATA_HOME=str(scratch), HOME=str(tmp_path), ALMUTEN_NO_PREFERENCES="1")
    script = tmp_path / "launch.py"
    script.write_text(CHILD.format(repo=str(REPO)))
    launches = [subprocess.Popen([sys.executable, str(script), name], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=env, cwd=str(tmp_path))
                for name in ("Launch A", "Launch B")]
    said = []
    assert len(launches) == 2
    try:
        for launch in launches:
            out, err = launch.communicate("go\n", timeout=LAUNCH)
            said.append([json.loads(line) for line in out.splitlines()])
            assert launch.returncode == 0, err
    finally:
        for launch in launches:
            if launch.poll() is None:
                launch.kill()
                launch.wait(WAIT)
    assert said == [[{"refused": True}], [{"refused": True}]], said
    assert engine.SAVED_CHARTS_PATH.read_text() == before


# =============================================================================
# The page: the sidebar says why
# =============================================================================

@pytest.mark.parametrize("act", ["save", "delete"])
def test_a_save_or_delete_refused_so_says_why_in_the_sidebar(scratch, monkeypatch, act):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    before = json.dumps(XY, indent=2)
    engine.SAVED_CHARTS_PATH.write_text(before)
    at.run()
    _refuse_lock_calls(engine, monkeypatch, errno.ENOLCK)
    if act == "save":
        [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("Z").run()
        [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    else:
        at.sidebar.selectbox(key="chart_picker").select("Y").run()
        [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()
        at.sidebar.button(key="_delete_confirm").click().run()
    assert_no_exception(at, act)
    said = _alerts(at)
    assert said.count(STORE_UNLOCKED) == 1, said
    assert STORE_BUSY not in said, said
    assert engine.SAVED_CHARTS_PATH.read_text() == before, f"the {act} was written"
    assert sorted(_picker(at)) == [NEW_CHART, "X", "Y"], _picker(at)
    assert not [x.value for x in at.sidebar.success if "Saved" in str(x.value)], "a save was announced"


def test_a_load_that_could_not_move_the_old_store_for_a_refused_lock_says_why(scratch, monkeypatch, tmp_path):
    at = make_app(date="1983-11-19", page="sources", timeout=300)
    engine = _engine()
    legacy = tmp_path / "beside-the-app" / "saved_charts.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"Old": REC}, indent=2))
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", legacy)
    _refuse_lock_calls(engine, monkeypatch, errno.ENOLCK)
    at.run()
    assert_no_exception(at, "the launch")
    said = _alerts(at)
    assert "Old" not in _picker(at), "the old store was moved in without the lock"
    assert said.count(STORE_UNLOCKED) == 1, said
    assert STORE_UNMOVED not in said, said
    at.run()
    assert STORE_UNLOCKED not in _alerts(at), "said again on the next run"
    assert json.loads(legacy.read_text()) == {"Old": REC}


def test_the_refused_lock_sentence_names_no_path_file_or_code():
    """The sidebar's sentence, as app.py holds it: no folder, no file's
    name, no error code."""
    tree = ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
    held = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
            and [getattr(t, "id", None) for t in node.targets] == ["STORE_UNLOCKED_SENTENCE"]]
    assert held == [STORE_UNLOCKED], held
    for mark in ("/", "\\", ".json", ".lock", "`", "ENOLCK", "EOPNOTSUPP", "errno"):
        assert mark not in STORE_UNLOCKED, mark


# =============================================================================
# A write synced: its file before the replace, its folder after
# =============================================================================

def _spy_writes(patch, folder_fsync=None):
    """A log of os.fsync and os.replace, in order: ('fsync', 'file' or
    'folder', the stat of what was synced) and ('replace', src, dst)."""
    log = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        seen = os.fstat(fd)
        kind = "folder" if stat.S_ISDIR(seen.st_mode) else "file"
        log.append(("fsync", kind, seen))
        if kind == "folder" and folder_fsync is not None:
            raise OSError(folder_fsync, os.strerror(folder_fsync))
        return real_fsync(fd)

    def replace(src, dst, **kw):
        log.append(("replace", Path(src), Path(dst)))
        return real_replace(src, dst, **kw)
    patch.setattr(os, "fsync", fsync)
    patch.setattr(os, "replace", replace)
    return log


@pytest.mark.parametrize("system", ["posix", "nt"])
@pytest.mark.parametrize("what", ["charts", "preferences"])
def test_a_state_write_syncs_its_file_before_the_replace_and_its_folder_after(prefs_on, monkeypatch, system, what):
    engine = _engine()
    real_sync = engine._sync_folder

    def sync_as(folder):
        """The folder's sync as on `system`: os.name is that system's for
        this call alone (nothing else in the write reads it)."""
        with monkeypatch.context() as named:
            named.setattr(os, "name", system)
            return real_sync(folder)
    with monkeypatch.context() as patch:
        patch.setattr(engine, "_sync_folder", sync_as)
        log = _spy_writes(patch)
        if what == "charts":
            path, wrote = engine.SAVED_CHARTS_PATH, engine.write_saved_charts(XY)
        else:
            path, wrote = engine.PREFERENCES_PATH, engine.write_preferences({"_launches": 3})
    assert wrote is True
    kinds = [entry[0] if entry[0] == "replace" else entry[1] for entry in log]
    assert kinds == (["file", "replace", "folder"] if system == "posix" else ["file", "replace"]), kinds
    synced, replaced = log[0][2], log[1]
    assert replaced[2] == path and replaced[1].parent == path.parent, replaced
    assert os.path.samestat(synced, os.stat(path)), "the file synced is not the one put in place"
    folders = [os.path.samestat(e[2], os.stat(path.parent)) for e in log[2:]]
    assert folders == ([True] if system == "posix" else []), "the folder synced is not the store's"


def test_a_linked_store_syncs_the_folder_of_the_file_it_names(scratch, monkeypatch, tmp_path):
    engine = _engine()
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "saved_charts.json"
    target.write_text("{}")
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    with monkeypatch.context() as patch:
        log = _spy_writes(patch)
        wrote = engine.write_saved_charts(XY)
    assert wrote is True and json.loads(target.read_text()) == XY
    assert [e[1] for e in log if e[0] == "fsync"] == ["file", "folder"], log
    assert os.path.samestat(log[-1][2], os.stat(shared)), "the folder synced is not the linked file's"


@pytest.mark.parametrize("code", [errno.EINVAL, errno.EIO, errno.EBADF])
def test_a_folder_whose_sync_is_refused_leaves_the_write_standing(scratch, monkeypatch, code):
    engine = _engine()
    with monkeypatch.context() as patch:
        log = _spy_writes(patch, folder_fsync=code)
        wrote = engine.write_saved_charts(XY)
    assert ("fsync", "folder") in [(e[0], e[1]) for e in log if e[0] == "fsync"], "the premise: the folder was synced"
    assert wrote is True and json.loads(engine.SAVED_CHARTS_PATH.read_text()) == XY
    assert sorted(p.name for p in engine.DATA_DIR.iterdir()) == ["saved_charts.json"]


def test_a_folder_that_cannot_be_opened_leaves_the_write_standing(scratch, monkeypatch):
    engine = _engine()
    real_open = os.open
    refused = []

    def opening(path, flags, *args, **kw):
        if flags & getattr(os, "O_DIRECTORY", 0) or Path(path) == engine.DATA_DIR:
            refused.append(path)
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real_open(path, flags, *args, **kw)
    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opening)
        wrote = engine.write_saved_charts(XY)
    assert refused, "the premise: the folder's open was asked for"
    assert wrote is True and json.loads(engine.SAVED_CHARTS_PATH.read_text()) == XY


def test_a_file_whose_sync_fails_is_a_write_that_failed(scratch, monkeypatch):
    engine = _engine()
    before = json.dumps({"X": REC}, indent=2)
    engine.SAVED_CHARTS_PATH.write_text(before)

    def fsync(fd):
        raise OSError(errno.EIO, os.strerror(errno.EIO))
    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fsync)
        wrote = engine.write_saved_charts(XY)
    assert wrote is False, "a write whose bytes could not be synced was reported as made"
    assert engine.SAVED_CHARTS_PATH.read_text() == before
    assert sorted(p.name for p in engine.DATA_DIR.iterdir()) == ["saved_charts.json"], "a temp file was left"


# =============================================================================
# The sentences that promised more than their code
# =============================================================================

def _docstring(path, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = [ast.get_docstring(node) for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(found) == 1, (path, name, len(found))
    return " ".join(found[0].split())


def _comments(path):
    return " ".join(" ".join(line.strip().lstrip("#").split()) for line in
                    Path(path).read_text(encoding="utf-8").splitlines() if line.strip().startswith("#"))


def test_the_window_log_says_a_link_put_after_the_look_is_followed_on_windows():
    said = _docstring(REPO / "desktop_launcher.py", "_open_window_log")
    assert "opened without following a link" not in said, said
    assert "on Windows only by a look before the open" in said, said
    assert "after that look is followed by the open" in said, said


def test_the_delta_t_comment_says_when_the_raced_thread_is_accepted():
    said = _comments(REPO / "ephemeris.py")
    assert "a Delta T table from it is refused for its life)" not in said
    assert "is refused for its life, unless the reference was read from one too" in said


def test_the_star_catalogue_comment_says_the_library_reads_unchecked_bytes():
    said = _comments(REPO / "engine.py")
    assert "checked against this before Swiss Ephemeris is let read it" not in said
    assert "the bytes it reads are not checked again" in said


def test_the_former_folders_copy_says_it_is_published_wide_and_narrowed_after():
    said = _comments(REPO / "engine.py")
    assert "no other account sees the copy being made" not in said
    assert "it is published at that mode, and narrowed only after" in said
    kept = _docstring(REPO / "engine.py", "_keep_the_data_folder_ours")
    assert "the folder is left as it is, and nothing is said" in kept, kept


def test_the_atomic_write_says_what_holds_on_each_system():
    said = _docstring(REPO / "engine.py", "_write_text_atomically")
    for words in ("synced (os.fsync) before it replaces the target",
                  "On Linux and macOS the folder is synced after the replace",
                  "On Windows the folder is not synced"):
        assert words in said, words
