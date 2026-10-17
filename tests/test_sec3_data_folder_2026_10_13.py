"""The data folder made its owner's alone (rulings 150 and 157).

- C-03: the data folder is made 0700, and one of this account's that is
  wider is narrowed; one that belongs to another account is refused. The
  store, the preferences, their recovery copies and their lock files are
  0600 when new (D-10 for the locks); an existing file keeps its mode (K-06).
- D-05: the temporary file a write makes is never wider than its target.
- C-08: an empty or relative XDG_DATA_HOME or APPDATA counts as unset.
- SB-05: only regular files are read at the store's, the preferences', an
  old store's or a recovery copy's name, without waiting; the preferences
  have a size bound.
- SB-06: the store beside the program is brought in once, said, and never
  inside a packaged build.
- SB-11: with preferences off, the page says so in the owner's sentence.
- K-07 and SB-12: a link the owner placed is followed, and the checks apply
  to the folder it names.
- SE-04: the harness puts the data folder in scratch on every platform.

Modes are judged under os.umask(0), where the umask hides nothing. Another
account's folder cannot be made without root, so the owner is faked where
the engine reads it (engine._owner_of, the one place a folder's owner is
read): it answers another account's id for the folder under test.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import make_app, sync_engine_to_environment

REC = {"date_string": "1990-01-01", "time_string": "12:00", "location_query": "Florence, Italy"}
FORMER_NAME = "TraditionalAstrologyEngine"
PREFERENCES_OFF = "Preferences are off for this launch, so no choice made in it will be kept."
IMPORTED = ("Charts kept beside the program by an older version of the app were brought into the saved charts. "
            "That file is left as it is and is not read again.")
OLD_NOT_A_FILE = "Something that is not a file stands where an older version of the app kept saved charts, so it was not read."
TIME_BOUND = 10.0


def _engine():
    sync_engine_to_environment()
    import engine
    return engine


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def umask0():
    previous = os.umask(0)
    try:
        yield
    finally:
        os.umask(previous)


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


@pytest.fixture
def beside(tmp_path, monkeypatch):
    """The store beside the program, moved into a folder of the test's own."""
    engine = _engine()
    program = tmp_path / "program"
    program.mkdir()
    monkeypatch.setattr(engine, "_LEGACY_SAVED_CHARTS_PATH", program / "saved_charts.json")
    return program / "saved_charts.json"


def _another_account(monkeypatch, engine, folder):
    """Fake `folder` (a link followed) as another account's, where the
    engine reads a folder's owner."""
    real = engine._owner_of
    target = os.path.realpath(folder)

    def owner(path):
        uid = real(path)
        return uid + 1 if os.path.realpath(path) == target else uid
    monkeypatch.setattr(engine, "_owner_of", owner)


def _sidebar(at):
    return [e.value for kind in ("error", "warning", "info", "success", "caption")
            for e in getattr(at.sidebar, kind)]


# =============================================================================
# C-03: the folder
# =============================================================================

def test_a_new_data_folder_is_owner_only(tmp_path, umask0):
    engine = _engine()
    folder = engine._make_user_data_dir(tmp_path / "base" / "Zij")
    assert _mode(folder) == 0o700, f"a new data folder is {oct(_mode(folder))}"


def test_a_new_data_folder_is_owner_only_whatever_the_umask_cuts(tmp_path):
    engine = _engine()
    folder = tmp_path / "Zij"
    previous = os.umask(0o444)
    try:
        engine._make_user_data_dir(folder)
    finally:
        os.umask(previous)
    made = _mode(folder)
    folder.chmod(0o700)                 # so that the run's temporary folders can be removed whatever was made
    assert made == 0o700, f"a new data folder under umask 0o444 is {oct(made)}"


def test_a_new_data_folder_is_owner_only_as_it_is_made(tmp_path, umask0, monkeypatch):
    """Before the narrowing (which would hide a folder made wider): the
    folder as mkdir and its chmod leave it."""
    engine = _engine()
    seen = []
    real = engine._keep_the_data_folder_ours

    def judged(path):
        seen.append(_mode(path))
        return real(path)
    monkeypatch.setattr(engine, "_keep_the_data_folder_ours", judged)
    engine._make_user_data_dir(tmp_path / "Zij")
    assert seen == [0o700], f"the new folder was made {[oct(m) for m in seen]}"


@pytest.mark.parametrize("wide", [0o755, 0o777, 0o750])
def test_a_wider_data_folder_of_this_accounts_is_narrowed(tmp_path, umask0, wide):
    engine = _engine()
    folder = tmp_path / "Zij"
    folder.mkdir()
    folder.chmod(wide)
    engine._make_user_data_dir(folder)
    assert _mode(folder) == 0o700, f"a {oct(wide)} data folder is left {oct(_mode(folder))}"


def test_a_folder_its_owner_made_unwritable_is_not_opened_up(tmp_path, umask0):
    """Narrowing takes only the group's and others' bits: K-09's 0555 folder
    stays one its owner cannot write in, and is said."""
    engine = _engine()
    folder = tmp_path / "Zij"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        engine._make_user_data_dir(folder)
        assert _mode(folder) == 0o500
    finally:
        folder.chmod(0o700)


def test_a_data_folder_of_another_account_is_refused(tmp_path, umask0, monkeypatch):
    engine = _engine()
    folder = tmp_path / "Zij"
    folder.mkdir()
    folder.chmod(0o777)
    _another_account(monkeypatch, engine, folder)
    with pytest.raises(engine.DataFolderRefused):
        engine._make_user_data_dir(folder)
    assert _mode(folder) == 0o777, "another account's folder was changed"


def test_nothing_is_read_from_or_written_in_another_accounts_folder(prefs_on, monkeypatch):
    engine = _engine()
    store, prefs = engine.SAVED_CHARTS_PATH, engine.PREFERENCES_PATH
    store.write_text(json.dumps({"Planted": REC}))
    prefs.write_text(json.dumps({"_launches": 3}))
    _another_account(monkeypatch, engine, engine.DATA_DIR)
    assert engine.data_folder_state() == ("used", "it belongs to another account")
    assert engine.load_saved_charts() == {}, "a store in another account's folder was read"
    assert engine.saved_charts_as_they_stand().state == "unreadable"
    assert engine.write_saved_charts({"Mine": REC}) is False
    assert engine.load_preferences() == {}, "preferences in another account's folder were read"
    assert engine.remember_preference("_launches", 4) is False
    assert engine.bring_in_the_old_store() is False
    held = sorted(p.name for p in engine.DATA_DIR.iterdir())
    assert held == ["preferences.json", "saved_charts.json"], f"the folder now holds {held}"
    assert json.loads(store.read_text()) == {"Planted": REC}, "the store in another account's folder was written"
    assert json.loads(prefs.read_text()) == {"_launches": 3}, "the preferences in another account's folder were written"


def test_the_page_says_another_accounts_folder_cannot_be_used(scratch, monkeypatch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"Planted": REC}))
    _another_account(monkeypatch, engine, engine.DATA_DIR)
    at = make_app(page="chart").run()
    assert not at.exception, [e.value for e in at.exception]
    said = (f"Saved charts and preferences cannot be kept: their folder, `{engine.DATA_DIR}`, cannot be used "
            "(it belongs to another account). Nothing can be saved and no home can be set until it can.")
    assert said in _sidebar(at), _sidebar(at)
    assert "Planted" not in at.sidebar.selectbox(key="chart_picker").options


# =============================================================================
# C-03 and D-10: the files
# =============================================================================

def test_a_new_store_is_owner_only(scratch, umask0):
    engine = _engine()
    assert engine.write_saved_charts({"X": REC}) is True
    assert _mode(engine.SAVED_CHARTS_PATH) == 0o600, oct(_mode(engine.SAVED_CHARTS_PATH))


def test_a_new_preferences_file_is_owner_only(prefs_on, umask0):
    engine = _engine()
    assert engine.remember_preference("_launches", 1) is True
    assert _mode(engine.PREFERENCES_PATH) == 0o600, oct(_mode(engine.PREFERENCES_PATH))


def test_an_existing_file_keeps_its_mode(scratch, umask0):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": REC}))
    engine.SAVED_CHARTS_PATH.chmod(0o640)
    assert engine.write_saved_charts({"Y": REC}) is True
    assert _mode(engine.SAVED_CHARTS_PATH) == 0o640, oct(_mode(engine.SAVED_CHARTS_PATH))


@pytest.mark.parametrize("which", ["store", "preferences"])
def test_a_recovery_copy_of_an_unreadable_file_is_owner_only(prefs_on, umask0, which):
    engine = _engine()
    path = engine.SAVED_CHARTS_PATH if which == "store" else engine.PREFERENCES_PATH
    path.write_text("{ not json")
    path.chmod(0o644)
    if which == "store":
        engine.load_saved_charts()
        copy = engine.store_notices()["copy"]
    else:
        engine.load_preferences()
        copy = engine.preferences_notices()["copy"]
    assert copy, "the premise: a copy was made"
    assert _mode(path.with_name(copy)) == 0o600, f"the copy is {oct(_mode(path.with_name(copy)))}"


def test_a_recovery_copy_is_owner_only_from_its_making(prefs_on, umask0, monkeypatch):
    """Before the exact mode is set (which would hide a copy made wider): the
    copy as its open made it, before any byte is written."""
    engine = _engine()
    seen = []
    real = engine._owner_only

    def judged(fd):
        seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return real(fd)
    monkeypatch.setattr(engine, "_owner_only", judged)
    engine.SAVED_CHARTS_PATH.write_text("{ not json")
    engine.load_saved_charts()
    assert engine.store_notices()["copy"], "the premise: a copy was made"
    assert seen and all(mode & ~0o600 == 0 for mode in seen), f"the copy was made {[oct(m) for m in seen]}"


def test_a_cut_short_save_kept_aside_is_owner_only(scratch, umask0):
    engine = _engine()
    stray = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp")
    stray.write_text(json.dumps({"Cut": REC}))
    stray.chmod(0o644)
    os.utime(stray, (engine._LAUNCHED_AT - 60, engine._LAUNCHED_AT - 60))
    engine.load_saved_charts()
    kept = [p for p in engine.DATA_DIR.iterdir() if ".recovered-" in p.name]
    assert len(kept) == 1, f"the premise: one save kept aside, {sorted(p.name for p in engine.DATA_DIR.iterdir())}"
    assert _mode(kept[0]) == 0o600, f"the kept save is {oct(_mode(kept[0]))}"


@pytest.mark.parametrize("which", ["saved_charts", "preferences"])
def test_a_lock_file_is_owner_only(prefs_on, umask0, which):
    engine = _engine()
    lock = engine.saved_charts_lock if which == "saved_charts" else engine.preferences_lock
    with lock():
        made = _mode(engine.DATA_DIR / f"{which}.lock")
    assert made == 0o600, f"the {which} lock file is {oct(made)}"


# =============================================================================
# D-05: the temporary file is never wider than its target
# =============================================================================

@pytest.mark.parametrize("target_mode", [None, 0o600, 0o640, 0o400], ids=["new", "0600", "0640", "0400"])
def test_the_temporary_file_is_never_wider_than_its_target(scratch, umask0, monkeypatch, target_mode):
    engine = _engine()
    store = engine.SAVED_CHARTS_PATH
    if target_mode is not None:
        store.write_text(json.dumps({"X": REC}))
        store.chmod(target_mode)
    bound = 0o600 if target_mode is None else target_mode
    seen = []
    real_open, real_chmod, real_replace = os.open, os.chmod, os.replace

    def is_temp(path):
        return str(path).endswith(".tmp") and Path(path).parent == store.parent

    def spying_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if is_temp(path):
            seen.append(("made", _mode(path)))
        return fd

    def spying_chmod(path, mode, *args, **kwargs):
        real_chmod(path, mode, *args, **kwargs)
        if is_temp(path):
            seen.append(("set", _mode(path)))

    def spying_replace(src, dst, *args, **kwargs):
        if is_temp(src):
            seen.append(("replaced", _mode(src)))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "open", spying_open)
    monkeypatch.setattr(os, "chmod", spying_chmod)
    monkeypatch.setattr(os, "replace", spying_replace)
    try:
        assert engine.write_saved_charts({"Y": REC}) is True
    finally:
        store.chmod(0o600)
    assert seen and seen[0][0] == "made", f"the premise: the temporary file was seen as it was made: {seen}"
    wider = [(when, oct(mode)) for when, mode in seen if mode & ~bound]
    assert not wider, f"the temporary file was wider than its target ({oct(bound)}): {wider}"


# =============================================================================
# C-08: an empty or relative variable counts as unset
# =============================================================================

@pytest.mark.parametrize("value", ["", "rel", "rel/share"])
def test_an_empty_or_relative_xdg_data_home_counts_as_unset(monkeypatch, value):
    engine = _engine()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", value)
    assert engine._user_data_path() == Path.home() / ".local" / "share" / "Zij"


@pytest.mark.parametrize("value", ["", "rel", "rel/Roaming"])
def test_an_empty_or_relative_appdata_counts_as_unset(monkeypatch, value):
    engine = _engine()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", value)
    assert engine._user_data_path() == Path.home() / "AppData" / "Roaming" / "Zij"


def test_an_absolute_variable_is_still_taken(monkeypatch, tmp_path):
    engine = _engine()
    for platform, name in (("linux", "XDG_DATA_HOME"), ("win32", "APPDATA")):
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setenv(name, str(tmp_path))
        assert engine._user_data_path() == tmp_path / "Zij"


# =============================================================================
# SB-05: only regular files are read, and never waited on
# =============================================================================

def _within_the_bound(fifo, work):
    """Run `work` in a thread; whether it returned within TIME_BOUND. A
    reader left waiting on `fifo` is let go (a writer opened and closed), so
    that a failing run ends."""
    done = []
    thread = threading.Thread(target=lambda: done.append(work()), daemon=True)
    thread.start()
    thread.join(TIME_BOUND)
    finished = not thread.is_alive()
    if not finished:
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        thread.join(TIME_BOUND)
    return finished, (done[0] if done else None)


def _former_store(engine):
    former = engine.DATA_DIR.parent / FORMER_NAME
    former.mkdir()
    return former / "saved_charts.json"


@pytest.mark.parametrize("name", ["store", "preferences", "beside the program", "former folder", "recovery copy"])
def test_a_pipe_at_a_name_the_app_reads_is_refused_with_a_sentence_without_waiting(prefs_on, beside, name):
    engine = _engine()
    if name == "store":
        fifo = engine.SAVED_CHARTS_PATH
    elif name == "preferences":
        fifo = engine.PREFERENCES_PATH
    elif name == "beside the program":
        fifo = beside
    elif name == "former folder":
        fifo = _former_store(engine)
    else:
        engine.SAVED_CHARTS_PATH.write_text("{ not json")
        fifo = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.unreadable-20000101-000000")
    os.mkfifo(fifo)

    def load():
        if name == "preferences":
            return engine.load_preferences(), engine.preferences_notices()
        return engine.load_saved_charts(), engine.store_notices()

    finished, result = _within_the_bound(fifo, load)
    assert finished, f"the load waited on a pipe at the {name}'s name"
    loaded, notices = result
    assert loaded == {}
    if name in ("store", "preferences"):
        # the sentence for a file that cannot be read and of which no copy could be made
        assert notices["unreadable"] and notices["copy"] is None, notices
    elif name == "recovery copy":
        # the store's own sentence: a copy was kept, under a name of its own
        assert notices["unreadable"] and notices["copy"] not in (None, fifo.name), notices
    else:
        assert notices["old_not_a_file"], notices
    assert stat.S_ISFIFO(os.lstat(fifo).st_mode), "the pipe was replaced"


@pytest.mark.parametrize("name", ["beside the program", "former folder"])
def test_the_page_says_an_old_store_is_no_file(scratch, beside, name):
    engine = _engine()
    (beside if name == "beside the program" else _former_store(engine)).mkdir()
    at = make_app(page="chart").run()
    assert not at.exception, [e.value for e in at.exception]
    assert OLD_NOT_A_FILE in _sidebar(at), _sidebar(at)


def test_a_device_at_the_preferences_name_is_refused(prefs_on):
    engine = _engine()
    engine.PREFERENCES_PATH.symlink_to(os.devnull)
    assert engine.load_preferences() == {}
    notices = engine.preferences_notices()
    assert notices["unreadable"] and notices["copy"] is None, notices
    assert engine.remember_preference("_launches", 1) is False
    assert engine.PREFERENCES_PATH.is_symlink()


def test_a_preferences_file_past_its_bound_is_refused(prefs_on):
    engine = _engine()
    bound = getattr(engine, "PREFERENCES_BYTE_LIMIT", 1024 * 1024)
    data = (json.dumps({"_launches": 3}) + " " * bound).encode()
    engine.PREFERENCES_PATH.write_bytes(data)
    assert engine.load_preferences() == {}, "a preferences file past its bound was read"
    notices = engine.preferences_notices()
    assert notices["unreadable"] and notices["copy"] is None, notices
    assert engine.remember_preference("_launches", 4) is False
    assert engine.PREFERENCES_PATH.read_bytes() == data, "the file past its bound was written over"


def test_preferences_past_the_bound_are_not_written(prefs_on):
    engine = _engine()
    bound = getattr(engine, "PREFERENCES_BYTE_LIMIT", 1024 * 1024)
    assert engine.remember_preference("last_chart", "x" * (bound + 1)) is False
    assert not engine.PREFERENCES_PATH.exists()


# =============================================================================
# SB-06: the store beside the program, once, never from a bundle
# =============================================================================

def test_the_store_beside_the_program_is_brought_in_once(scratch, beside):
    engine = _engine()
    beside.write_text(json.dumps({"Old": REC}))
    assert engine.load_saved_charts() == {"Old": REC}
    assert engine.store_notices()["imported"] is True
    engine.SAVED_CHARTS_PATH.unlink()
    assert engine.load_saved_charts() == {}, "the store beside the program came back after the store was deleted"
    assert engine.store_notices()["imported"] is False
    assert not engine.SAVED_CHARTS_PATH.exists()
    assert beside.exists(), "the file beside the program was removed"


def test_the_page_says_the_store_beside_the_program_was_brought_in(scratch, beside):
    beside.write_text(json.dumps({"Old": REC}))
    at = make_app(page="chart").run()
    assert not at.exception, [e.value for e in at.exception]
    assert IMPORTED in _sidebar(at), _sidebar(at)
    assert "Old" in at.sidebar.selectbox(key="chart_picker").options
    at.run()
    assert IMPORTED not in _sidebar(at), "said again on the next run"


def test_a_pipe_at_the_marks_name_is_not_waited_on(scratch, beside, monkeypatch):
    """A pipe put at the mark's name after the look for the mark (the look
    faked to have found nothing) is refused at once: the charts are brought
    in and the pipe is left as it is."""
    engine = _engine()
    beside.write_text(json.dumps({"Old": REC}))
    fifo = engine.SAVED_CHARTS_PATH.parent / "saved_charts.json.imported-from-beside-the-program"
    os.mkfifo(fifo)
    monkeypatch.setattr(engine, "_the_store_beside_the_program_was_imported", lambda: False)
    done = []
    thread = threading.Thread(target=lambda: done.append(engine.load_saved_charts()), daemon=True)
    thread.start()
    thread.join(TIME_BOUND)
    finished = not thread.is_alive()
    if not finished:
        # let a writer left waiting go (a reader opened and closed), so that a failing run ends
        os.close(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK))
        thread.join(TIME_BOUND)
    assert finished, "the mark's write waited on a pipe at its name"
    assert done == [{"Old": REC}]
    assert stat.S_ISFIFO(os.lstat(fifo).st_mode), "the pipe was replaced"


@pytest.mark.parametrize("bundle", ["frozen", "_MEIPASS", "both"])
def test_the_store_beside_the_program_is_never_brought_in_from_a_bundle(scratch, beside, monkeypatch, bundle):
    engine = _engine()
    beside.write_text(json.dumps({"Planted": REC}))
    if bundle in ("frozen", "both"):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
    if bundle in ("_MEIPASS", "both"):
        monkeypatch.setattr(sys, "_MEIPASS", str(beside.parent), raising=False)
    assert engine.load_saved_charts() == {}
    assert not engine.SAVED_CHARTS_PATH.exists()


# =============================================================================
# SB-11: preferences off, said
# =============================================================================

def test_the_page_says_preferences_are_off(scratch):
    at = make_app(page="chart").run()
    assert not at.exception, [e.value for e in at.exception]
    assert [c.value for c in at.sidebar.caption if c.value == PREFERENCES_OFF] == [PREFERENCES_OFF]


def test_the_page_says_nothing_of_preferences_when_they_are_on(prefs_on):
    at = make_app(page="chart").run()
    assert not at.exception, [e.value for e in at.exception]
    assert PREFERENCES_OFF not in _sidebar(at)


# =============================================================================
# K-07 and SB-12: links the owner placed
# =============================================================================

def test_a_link_the_owner_placed_at_the_store_is_written_through(scratch, umask0, tmp_path):
    """K-07 stands: passes before and after this lane."""
    engine = _engine()
    synced = tmp_path / "synced"
    synced.mkdir()
    (synced / "charts.json").write_text(json.dumps({"X": REC}))
    (synced / "charts.json").chmod(0o600)
    engine.SAVED_CHARTS_PATH.symlink_to(synced / "charts.json")
    assert engine.write_saved_charts({"X": REC, "Y": REC}) is True
    assert engine.SAVED_CHARTS_PATH.is_symlink()
    assert sorted(json.loads((synced / "charts.json").read_text())) == ["X", "Y"]
    assert _mode(synced / "charts.json") == 0o600


def _former_folder_as_a_link(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "saved_charts.json").write_text(json.dumps({"Old": REC}))
    elsewhere.chmod(0o777)
    (base / FORMER_NAME).symlink_to(elsewhere)
    return base / "Zij", elsewhere


def test_a_former_folder_that_is_a_link_is_followed_and_its_target_narrowed(tmp_path, umask0):
    engine = _engine()
    path, elsewhere = _former_folder_as_a_link(tmp_path)
    engine._make_user_data_dir(path)
    assert path.is_symlink() and os.path.realpath(path) == str(elsewhere), "the former folder was not followed"
    assert json.loads((path / "saved_charts.json").read_text()) == {"Old": REC}
    assert _mode(elsewhere) == 0o700, f"the folder the link names is left {oct(_mode(elsewhere))}"


def test_a_former_folder_that_is_a_link_to_another_accounts_folder_is_refused(tmp_path, umask0, monkeypatch):
    engine = _engine()
    path, elsewhere = _former_folder_as_a_link(tmp_path)
    _another_account(monkeypatch, engine, elsewhere)
    with pytest.raises(engine.DataFolderRefused):
        engine._make_user_data_dir(path)
    assert _mode(elsewhere) == 0o777, "another account's folder was changed"


# =============================================================================
# SE-04: the harness's data folder is in scratch
# =============================================================================

def test_the_harness_sets_the_data_folder_whatever_the_environment_held(tmp_path):
    tests = Path(__file__).resolve().parent
    elsewhere = "/nonexistent-data-home-" + tmp_path.name
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    env["XDG_DATA_HOME"] = elsewhere
    out = subprocess.run(
        [sys.executable, "-c",
         "import os, sys; sys.path.insert(0, sys.argv[1]); import conftest; "
         "print(os.environ['XDG_DATA_HOME'])", str(tests)],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    held = out.stdout.splitlines()[-1]
    assert held == str(tests / ".xdg-scratch"), f"the harness left XDG_DATA_HOME at {held!r}"


@pytest.mark.parametrize("platform, name, own",
                         [("darwin", "HOME", "/elsewhere/reader"), ("win32", "APPDATA", "/elsewhere/AppData/Roaming"),
                          ("linux", "XDG_DATA_HOME", "/elsewhere/.local/share")])
def test_the_harness_puts_each_platforms_data_folder_in_scratch(monkeypatch, tmp_path, platform, name, own):
    import conftest
    engine = _engine()
    scratch = tmp_path / "scratch"
    environment = conftest.harness_data_environment(platform, scratch, {name: own})
    assert environment == {name: str(scratch), conftest.HARNESS_MARK: str(scratch)}
    monkeypatch.setattr(sys, "platform", platform)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    folder = engine._user_data_path()
    assert scratch in folder.parents, f"on {platform} the harness's data folder is {folder}"


_DATA_VARIABLE = {"linux": "XDG_DATA_HOME", "darwin": "HOME", "win32": "APPDATA"}


@pytest.mark.parametrize("held", ["neither", "the mark alone", "a test alone", "another harness's mark", "both"])
def test_only_a_tests_own_child_keeps_the_value_it_was_given(tmp_path, held):
    """Kept only where the harness's mark names this scratch and a test is
    running; where the value lies decides nothing."""
    import conftest
    scratch, own = tmp_path / "scratch", str(tmp_path / "own")
    environ = {"XDG_DATA_HOME": own}
    if held in ("the mark alone", "both"):
        environ[conftest.HARNESS_MARK] = str(scratch)
    if held == "another harness's mark":
        environ[conftest.HARNESS_MARK] = str(tmp_path / "another")
    if held in ("a test alone", "another harness's mark", "both"):
        environ["PYTEST_CURRENT_TEST"] = "tests/test_x.py::test_y (call)"
    kept = conftest.harness_data_environment("linux", scratch, environ)["XDG_DATA_HOME"]
    assert kept == (own if held == "both" else str(scratch)), held


def test_a_tests_own_child_keeps_the_data_folder_it_was_given(tmp_path):
    """The child a test starts with a folder of its own (as the locked-store
    tests do) is left there."""
    tests = Path(__file__).resolve().parent
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path)}
    out = subprocess.run(
        [sys.executable, "-c",
         "import os, sys; sys.path.insert(0, sys.argv[1]); import conftest; "
         "print(os.environ['XDG_DATA_HOME'])", str(tests)],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.splitlines()[-1] == str(tmp_path)


def _a_fresh_start(**values):
    """os.environ as a run started from a shell would have it: nothing of
    pytest's or the harness's, with `values` set."""
    import conftest
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_") and k != conftest.HARNESS_MARK}
    env.update(values, PYTHONDONTWRITEBYTECODE="1")
    return env


def _started_inside_its_temporary_folder(tmp_path, platform, layout):
    """(TMPDIR, the data variable's value) for a run whose temporary folder
    holds its data folder: TMPDIR at a stand-in home, or a data folder kept
    in the temporary folder."""
    if layout == "home":
        temp = tmp_path / "home"
        value = {"linux": temp / ".local" / "share", "darwin": temp,
                 "win32": temp / "AppData" / "Roaming"}[platform]
    else:
        temp = tmp_path / "temp"
        value = temp / "owner-data"
    value.mkdir(parents=True, exist_ok=True)
    return temp, value


@pytest.mark.parametrize("layout", ["home", "temp"])
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_the_harness_ignores_where_the_folder_it_was_given_lies(tmp_path, platform, layout):
    """Each platform's variable, faked, at harness start: replaced though
    it lies in the temporary folder TMPDIR names."""
    import conftest
    tests = Path(__file__).resolve().parent
    name = _DATA_VARIABLE[platform]
    temp, value = _started_inside_its_temporary_folder(tmp_path, platform, layout)
    env = _a_fresh_start(TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp), HOME=str(tmp_path / "home"))
    env[name] = str(value)
    out = subprocess.run(
        [sys.executable, "-c",
         "import json, os, sys, tempfile; sys.path.insert(0, sys.argv[1]); import pytest, streamlit.config; "
         "sys.platform = sys.argv[2]; import conftest; "
         "print(json.dumps([tempfile.gettempdir(), os.environ[sys.argv[3]]]))", str(tests), platform, name],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    temporary, held = json.loads(out.stdout.splitlines()[-1])
    assert os.path.realpath(temporary) == os.path.realpath(temp), "premise: TMPDIR names the temporary folder"
    assert held == str(conftest.HARNESS_DATA_HOME), f"on {platform} the harness left {name} at {held!r}"


_OWNERS_STORE = json.dumps({"Owner": REC}).encode()


def _stand_in_owners_folder(share):
    folder = share / "Zij"
    folder.mkdir(parents=True)
    os.chmod(folder, 0o755)
    store = folder / "saved_charts.json"
    store.write_bytes(_OWNERS_STORE)
    os.chmod(store, 0o644)
    return folder


def _as_it_stands(folder):
    return (_mode(folder), sorted(os.listdir(folder.parent)),
            {p.name: (_mode(p), p.read_bytes()) for p in folder.iterdir()})


@pytest.fixture
def short_root():
    """A folder of the test's own with a short name: the session's
    temporary folder is made inside it, and Swiss Ephemeris refuses a
    temporary folder whose name is long (tmp_path's would be). It is made
    under /tmp (or, where /tmp is not a writable directory, the temporary
    folder), never under the inherited TMPDIR, whose own length would
    count against the inner session's folders."""
    import shutil
    import tempfile
    base = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK | os.X_OK) else tempfile.gettempdir()
    root = Path(tempfile.mkdtemp(prefix="se04-", dir=base))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("layout", ["home", "temp"])
def test_a_run_started_inside_its_temporary_folder_keeps_out_of_the_folder_it_was_given(short_root, layout):
    """A pytest session of its own, started with TMPDIR at a stand-in home
    and XDG_DATA_HOME in it (or with a data folder kept in the temporary
    folder): its data folder is the harness's scratch, and the stand-in
    folder is as it was, mode and contents."""
    tmp_path = short_root
    temp, share = _started_inside_its_temporary_folder(tmp_path, "linux", layout)
    folder = _stand_in_owners_folder(share)
    made = (0o755, ["Zij"], {"saved_charts.json": (0o644, _OWNERS_STORE)})
    assert _as_it_stands(folder) == made, "premise: the stand-in folder as made"
    (tmp_path / "home").mkdir(exist_ok=True)
    env = _a_fresh_start(TMPDIR=str(temp), HOME=str(tmp_path / "home"), XDG_DATA_HOME=str(share))
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         f"tests/{Path(__file__).name}::test_this_runs_data_folder_is_in_scratch",
         "tests/test_record_lifecycle_2026_09_16.py"],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=600)
    out = run.stdout + run.stderr
    assert run.returncode == 0, out[-3000:]
    assert " passed" in out and " failed" not in out, out[-3000:]
    assert _as_it_stands(folder) == made, "the session touched the folder it was started with"


def test_this_runs_data_folder_is_in_scratch():
    """The harness's own scratch, exactly: not anywhere a temporary folder
    happens to cover."""
    import conftest
    engine = _engine()
    name = _DATA_VARIABLE.get(sys.platform, "XDG_DATA_HOME")
    assert os.environ[name] == str(conftest.HARNESS_DATA_HOME), (name, os.environ.get(name))
    assert conftest.HARNESS_DATA_HOME.resolve() in Path(engine.DATA_DIR).resolve().parents, engine.DATA_DIR
