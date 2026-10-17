"""The saved charts and Save after the store's lock (lane SC, wave 5).

The notes lanes' saved-charts items (``NOTES_LANE_ITEMS.md`` rows SC-01..SC-18
in the corpus' records of the re-pass, less SC-06, left by ruling 80, and
SC-11, gone), R2-07 of Sol's pass (SC-02), rulings 77 and 78, and KS's
re-check K-1 and K-2. Each case below was a strict xfail failing on 46117e0
for its item's reason before its fix.

Every wait on another thread or window is bounded (``WAIT``); nothing sleeps.
"""
import json
import subprocess
import sys
import threading
import time

import pytest

from conftest import assert_no_exception, make_app, sync_engine_to_environment
from test_repass_l6_2026_10_04 import PETOSKEY, _picker, _read, _save_as, _sidebar_texts, _store, scratch  # noqa: F401
from test_followups_2026_10_05 import prefs_on  # noqa: F401

WAIT = 120            # seconds: the bound on every wait for another thread or window


def XF(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


def _engine():
    sync_engine_to_environment()
    import engine
    return engine


def _copies():
    return sorted(_store().parent.glob("saved_charts.json.unreadable-*"))


# =============================================================================
# SC-05: a store the writer cannot write back
# =============================================================================

# A store of one record nested 50,000 deep: json.loads reads it (to about
# 52,000 here), json.dumps cannot write it back (from about 48,000).
DEEP_STORE = '{"X": ' + '{"a": ' * 49_999 + '1' + '}' * 50_000


def test_sc05_a_store_the_writer_cannot_write_back_does_not_take_save_down(scratch):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(DEEP_STORE)
    at = make_app(date="1983-11-19", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    _save_as(at, "Z")
    assert_no_exception(at, "Save 'Z'")
    assert "Saved 'Z'." in _sidebar_texts(at), _sidebar_texts(at)
    kept = [p for p in [_store(), *_copies()] if p.read_text() == DEEP_STORE]
    assert kept, "the store's bytes are in no file"


def test_sc05_a_store_the_writer_cannot_write_back_is_not_a_store(scratch, monkeypatch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": PETOSKEY}))

    def overflow(charts):
        raise RecursionError("Stack overflow (used 8156 kB) while getting the repr of an object")
    monkeypatch.setattr(engine, "_saved_charts_text", overflow)
    assert engine.saved_charts_as_they_stand().state == "malformed"
    assert engine.load_saved_charts() == {}
    assert engine.LAST_STORE_UNREADABLE is True


def test_sc05_a_mapping_the_writer_cannot_write_is_a_failed_write(scratch, monkeypatch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": PETOSKEY}))

    def overflow(charts):
        raise RecursionError("Stack overflow (used 8156 kB) while getting the repr of an object")
    monkeypatch.setattr(engine, "_saved_charts_text", overflow)
    assert engine.write_saved_charts({"X": PETOSKEY, "Z": PETOSKEY}) is False
    assert engine.SAVED_CHARTS_PATH.read_text() == json.dumps({"X": PETOSKEY}), "the store was written"


# =============================================================================
# Shared helpers for the items below
# =============================================================================

def _put_store(charts):
    _store().parent.mkdir(parents=True, exist_ok=True)
    _store().write_text(json.dumps(charts, indent=2))


def _prefs_path():
    return _store().parent / "preferences.json"


def _strip(at):
    for caption in at.main.caption:
        if " · " in caption.value:
            return caption.value
    return ""


def _alerts(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning") for e in getattr(where, kind)]


def _dark_wheel(at):
    return [c for c in at.main.checkbox if c.label == "Dark wheel"][0]


def _app_function(name, **names):
    """One module-level function of app.py, lifted by its source and run with
    `names` as its globals."""
    import ast
    from conftest import ui_source
    source = ui_source()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = dict(names)
    exec(ast.get_source_segment(source, node), namespace)
    return namespace[name]


FLORENCE = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
            "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
MANUAL = "Manual UTC offset"
HOME = {"label": "Florence", "lat": 43.7792, "lon": 11.2463}
FOLDER_SENTENCE = "Saved charts and preferences cannot be kept: their folder"


# =============================================================================
# SC-01: a record whose place label is empty
# =============================================================================

def test_sc01_a_record_with_an_empty_place_label_opens_unmodified(scratch):
    _put_store({"P": dict(FLORENCE, location_query="")})
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(at).select("P").run()
    assert_no_exception(at, "opening P")
    assert _strip(at).startswith("P · "), _strip(at)
    assert "Edited since it was saved." not in _sidebar_texts(at), _sidebar_texts(at)


# =============================================================================
# SC-02 (R2-07): a stored time standard this app does not offer
# =============================================================================

def test_sc02_a_stored_standard_this_app_does_not_offer_is_named(scratch):
    _put_store({"Manual one": dict(PETOSKEY, time_standard=MANUAL, utc_offset=-5),
                "Bogus": dict(PETOSKEY, time_standard="Eastern War Time", utc_offset=-4)})
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(at).select("Manual one").run()
    _picker(at).select("Bogus").run()
    assert_no_exception(at, "opening Bogus")
    warnings = [w.value for w in at.sidebar.warning]
    assert not [w for w in warnings if "saved before the time standard" in w], warnings
    named = [w for w in warnings if "Eastern War Time" in w]
    assert len(named) == 1 and MANUAL in named[0], warnings


# =============================================================================
# SC-03 (KS check, finding 6): a temporary file left by a write that never ended
# =============================================================================

def _plant_temp(path, age):
    import os
    import time
    path.write_text("half a write")
    then = time.time() + age
    os.utime(path, (then, then))
    return path


def test_sc03_a_stray_temporary_file_older_than_the_launch_is_removed_at_load(scratch):
    _put_store({"X": FLORENCE})
    stray = _plant_temp(_store().with_name("saved_charts.json.0123456789abcdef.tmp"), -3600)
    at = make_app(date="1983-11-19", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert not stray.exists(), sorted(p.name for p in _store().parent.iterdir())


def test_sc03_a_stray_preferences_temporary_file_is_removed_at_load(prefs_on):
    _put_store({"X": FLORENCE})
    _prefs_path().write_text(json.dumps({"_launches": 3}))
    stray = _plant_temp(_prefs_path().with_name("preferences.json.0123456789abcdef.tmp"), -3600)
    at = make_app(date="1983-11-19", page="sources", timeout=300).run()
    assert_no_exception(at, "the launch")
    assert not stray.exists(), sorted(p.name for p in _store().parent.iterdir())


def test_sc03_only_strays_of_the_writers_form_from_before_the_launch_are_removed(scratch):
    """Guards beside SC-03's pins: a temporary file newer than the launch may
    be a write in flight, and is left; so is any name the writer never makes
    and a directory of the writer's form. (The former shared name is ruling
    91's, below.)"""
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    folder = engine.SAVED_CHARTS_PATH.parent
    old = _plant_temp(folder / "saved_charts.json.0123456789abcdef.tmp", -3600)
    young = _plant_temp(folder / "saved_charts.json.fedcba9876543210.tmp", +3600)
    others = [_plant_temp(folder / name, -3600) for name in
              ("saved_charts.json.0123.tmp", "saved_charts.json.0123456789ABCDEF.tmp",
               "notes.json.0123456789abcdef.tmp")]
    (folder / "saved_charts.json.aaaaaaaaaaaaaaaa.tmp").mkdir()
    assert engine.load_saved_charts() == {"X": FLORENCE}
    assert not old.exists()
    assert young.exists() and all(p.exists() for p in others)
    assert (folder / "saved_charts.json.aaaaaaaaaaaaaaaa.tmp").is_dir()


def test_sc03_no_stray_is_removed_while_another_holds_the_stores_lock(scratch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    stray = _plant_temp(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), -3600)
    assert engine._STORE_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        assert engine.load_saved_charts() == {"X": FLORENCE}, "the load goes on without the tidying"
        assert stray.exists(), "a stray was removed without the store's lock"
    finally:
        engine._STORE_THREAD_LOCK.release()
    engine.load_saved_charts()
    assert not stray.exists()

    # KF2's check (its mutation M5): the tidying waits on the store's lock a
    # moment only (_STRAY_TEMP_WAIT, 0.25 s), so a launch while another launch
    # holds the lock loads within about a second, the stray left for a later
    # load. The other launch is a process holding the data folder's lock file
    # as the engine's holder does (flock, removed before it lets go).
    stray = _plant_temp(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), -3600)
    holder = subprocess.Popen([sys.executable, "-c", _LOCK_HOLDER, str(engine.SAVED_CHARTS_PATH.parent / "saved_charts.lock")],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held", "premise: the other process holds the store's lock"
        start = time.monotonic()
        assert engine.load_saved_charts() == {"X": FLORENCE}, "the load goes on without the tidying"
        took = time.monotonic() - start
        assert stray.exists(), "a stray was removed while another process held the store's lock"
        assert took < TIDYING_BOUND, f"the load waited {took:.2f} s on another launch's lock"
    finally:
        holder.stdin.close()
        holder.wait(timeout=WAIT)
    engine.load_saved_charts()
    assert not stray.exists()


# The bound on a load whose tidying meets another launch's lock: the tidying's
# wait, 0.25 s, with 0.75 s for the load itself and a loaded runner's
# scheduling (the load alone takes a few milliseconds here); a wait of a
# second or more, as M5's 10 s, fails it.
TIDYING_BOUND = 1.0

# Another launch holding the store's lock, as the engine's holder does: the
# lock file made, flock'd, and removed before it is let go (on stdin's end).
_LOCK_HOLDER = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("held", flush=True)
sys.stdin.read()
os.unlink(sys.argv[1])
fcntl.flock(fd, fcntl.LOCK_UN)
os.close(fd)
"""


# =============================================================================
# Ruling 91: a stray that reads as a store is kept aside, not removed
# =============================================================================

COMPLETE = json.dumps({"Last save": FLORENCE}, indent=2)


def _plant(path, text):
    """A stray holding `text`, last written long before the launch."""
    import os
    path.write_text(text)
    os.utime(path, (0, 0))
    return path


def _recovered(name="saved_charts.json"):
    return sorted(p.name for p in _store().parent.glob(name + ".recovered-*"))


def test_sc03_a_stray_that_reads_as_a_store_is_kept_aside_under_a_recovery_name(scratch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
    assert engine.load_saved_charts() == {"X": FLORENCE}, "the store is read as it is"
    assert not stray.exists()
    kept = _recovered()
    assert len(kept) == 1 and (_store().parent / kept[0]).read_text() == COMPLETE, kept


def test_sc03_the_former_shared_name_is_kept_aside_when_it_reads_as_a_store(scratch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.tmp"), COMPLETE)
    engine.load_saved_charts()
    assert not stray.exists()
    kept = _recovered()
    assert len(kept) == 1 and (_store().parent / kept[0]).read_text() == COMPLETE, kept


def test_sc03_the_former_shared_name_is_removed_when_it_does_not_read(scratch):
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    stray = _plant_temp(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.tmp"), -3600)
    engine.load_saved_charts()
    assert not stray.exists()
    assert _recovered() == [], "a stray that does not read was kept"


def test_sc03_a_stray_that_does_not_read_is_removed_and_nothing_kept(scratch):
    """Ruling 91's other half, already so since SC-03's tidying: a stray of
    the writer's form that does not read as a store is removed, and nothing
    is kept of it."""
    engine = _engine()
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    strays = [_plant_temp(engine.SAVED_CHARTS_PATH.with_name(f"saved_charts.json.{tag * 16}.tmp"), -3600)
              for tag in "ab"]
    _plant(strays[1], COMPLETE[:-3])               # a write cut short
    assert len(strays) == 2 and all(p.exists() for p in strays), "the premise: two strays planted"
    engine.load_saved_charts()
    assert [p.exists() for p in strays] == [False, False]
    assert _recovered() == [], _recovered()


def test_sc03_a_preferences_stray_that_reads_is_kept_aside(prefs_on):
    engine = _engine()
    engine.write_preferences({"_launches": 3})
    stray = _plant(engine.PREFERENCES_PATH.with_name("preferences.json.0123456789abcdef.tmp"),
                   json.dumps({"_launches": 4, "_wheel_dark": True}))
    engine.load_preferences()
    assert not stray.exists()
    kept = _recovered("preferences.json")
    assert len(kept) == 1 and json.loads((_store().parent / kept[0]).read_text())["_wheel_dark"] is True, kept


def test_sc03_a_recovery_copy_never_takes_a_name_already_there(scratch, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(engine, "_recovery_stamp", lambda: "20260101-000000", raising=False)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    theirs = engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.recovered-20260101-000000")
    theirs.write_text("another launch's recovery")
    strays = [engine.SAVED_CHARTS_PATH.with_name(f"saved_charts.json.{tag * 16}.tmp") for tag in "cd"]
    for n, stray in enumerate(strays):
        _plant(stray, json.dumps({f"Save {n}": FLORENCE}))
    engine.load_saved_charts()
    assert theirs.read_text() == "another launch's recovery", "a recovery copy was written over"
    kept = _recovered()
    assert kept == ["saved_charts.json.recovered-20260101-000000", "saved_charts.json.recovered-20260101-000000-2",
                    "saved_charts.json.recovered-20260101-000000-3"], kept
    held = sorted(json.loads((_store().parent / name).read_text()).popitem()[0] for name in kept[1:])
    assert held == ["Save 0", "Save 1"], held


def test_sc03_a_stray_that_reads_stays_where_no_recovery_copy_can_be_made(scratch, monkeypatch):
    """Ruling 91's guard: a stray that reads is removed only once its copy is
    kept. With every recovery name already taken no copy can be made, and
    the stray stays as it was."""
    engine = _engine()
    monkeypatch.setattr(engine, "_recovery_stamp", lambda: "20260101-000000")
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"X": FLORENCE}))
    stem = "saved_charts.json.recovered-20260101-000000"
    taken = [stem] + [f"{stem}-{n}" for n in range(2, 1000)]
    for name in taken:
        engine.SAVED_CHARTS_PATH.with_name(name).write_text("taken")
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), COMPLETE)
    assert engine.load_saved_charts() == {"X": FLORENCE}
    assert stray.exists(), "the save was removed with no copy of it anywhere"
    assert stray.read_text() == COMPLETE
    assert _recovered() == sorted(taken), "a recovery copy was made under a name not taken"


# =============================================================================
# SC-07: a store file replaced, not one record deleted
# =============================================================================

def test_sc07_a_store_replaced_whole_is_not_called_a_deletion(scratch):
    _put_store({"X": FLORENCE, "Y": dict(FLORENCE, date_string="1990-01-01")})
    a = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(a).select("X").run()
    _store().unlink()
    c = make_app(date="1999-01-01", page="sources", timeout=300).run()
    _save_as(c, "C1")
    assert sorted(_read(_store())) == ["C1"], "the premise: the new file holds C1 alone"
    _save_as(a, "X")
    assert_no_exception(a, "A's save of X")
    texts = _sidebar_texts(a)
    assert not [t for t in texts if "deleted by another window" in t], texts
    assert [t for t in texts if t.startswith("The saved charts file has been replaced")], texts
    assert sorted(_read(_store())) == ["C1"], "nothing is written"


# =============================================================================
# SC-09: a preference the file did not take (ruling 93: tell, don't retry)
# =============================================================================

REFUSED_PREFS = "The preferences file was not written, so this choice was not kept. Try again once it can be written."


def test_sc09_b_refusals_in_an_unwritable_folder_are_said_in_their_runs_and_nothing_is_retried(prefs_on):
    _put_store({"X": FLORENCE})
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    assert _read(_prefs_path()).get("_wheel_dark") is False, "the premise: the launch kept Dark wheel off"
    folder = _store().parent
    folder.chmod(0o555)
    try:
        _dark_wheel(at).check().run()
        ticked = _alerts(at)
        _picker(at).select("X").run()
        opened = _alerts(at)
        assert_no_exception(at, "the choices in the unwritable folder")
    finally:
        folder.chmod(0o755)
    assert REFUSED_PREFS in ticked, ticked
    assert REFUSED_PREFS in opened, opened
    at.run()
    at.run()
    assert_no_exception(at, "the reruns")
    held = _read(_prefs_path())
    assert held.get("_wheel_dark") is False and "last_chart" not in held, f"a refused choice was written later: {held}"
    assert _dark_wheel(at).value is True, "the window's box keeps the reader's value"


def test_sc09_a_refused_write_is_said_in_its_run_and_the_file_is_unchanged(prefs_on, tmp_path):
    synced = tmp_path / "synced"
    synced.mkdir()
    target = synced / "prefs.json"
    target.write_text(json.dumps({"_launches": 3}))
    _store().parent.mkdir(parents=True, exist_ok=True)
    _prefs_path().symlink_to(target)
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    assert json.loads(target.read_text()).get("_wheel_dark") is False, "the premise: the launch kept Dark wheel off"
    synced.chmod(0o555)
    try:
        _dark_wheel(at).check().run()
        first = _alerts(at)
        at.run()
        second = _alerts(at)
    finally:
        synced.chmod(0o755)
    assert_no_exception(at, "the refused write")
    assert first.count(REFUSED_PREFS) == 1, first
    assert REFUSED_PREFS not in second, second
    assert json.loads(target.read_text()).get("_wheel_dark") is False, "the refused choice reached the file"
    assert _dark_wheel(at).value is True, "the window's box keeps the reader's value"


def test_sc09_a_refusal_by_a_file_that_can_neither_be_read_nor_copied_is_said_in_its_run(prefs_on):
    _put_store({"X": FLORENCE})
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    _prefs_path().chmod(0o000)
    try:
        _dark_wheel(at).check().run()
        said = _alerts(at)
    finally:
        _prefs_path().chmod(0o644)
    assert_no_exception(at, "the refused write")
    assert REFUSED_PREFS in said, said
    assert _read(_prefs_path()).get("_wheel_dark") is False, "the refused choice reached the file"


# =============================================================================
# SC-10: the data folder removed while the app is open, and restored
# =============================================================================

def test_sc10_a_folder_removed_while_open_is_said_and_read_again_when_it_returns(scratch):
    import shutil
    _put_store({"X": FLORENCE, "Y": dict(FLORENCE, date_string="1990-01-01")})
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    folder = _store().parent
    shutil.rmtree(folder)
    at.run()
    assert_no_exception(at, "the rerun without the folder")
    assert [t for t in _alerts(at) if t.startswith(FOLDER_SENTENCE)], _alerts(at)
    _save_as(at, "Z")
    assert not [t for t in _alerts(at) if "The saved charts file could not be written" in t], _alerts(at)
    folder.mkdir()
    _put_store({"Old": FLORENCE, "X": FLORENCE, "Y": dict(FLORENCE, date_string="1990-01-01")})
    at.run()
    assert_no_exception(at, "the rerun with the folder restored")
    assert "Old" in _picker(at).options, _picker(at).options


def test_sc10_save_and_set_as_home_name_the_folder_that_has_gone(prefs_on):
    """Beside SC-10's pin: the one cause has one sentence, the folder's, where
    Save and "Set as home" are pressed; nothing is written."""
    import shutil
    _put_store({"X": FLORENCE})
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    folder = _store().parent
    shutil.rmtree(folder)
    at.sidebar.button(key="_set_home").click().run()
    assert_no_exception(at, "Set as home")
    homes = [e.value for e in at.sidebar.error]
    _save_as(at, "Z")
    assert_no_exception(at, "Save")
    saves = [e.value for e in at.sidebar.error]
    for said in (homes, saves):
        assert [e for e in said if e.startswith(FOLDER_SENTENCE) and "cannot be found" in e], said
        assert not [e for e in said if "could not be written" in e or "Could not write" in e], said
    assert not folder.exists(), "something was written where the folder was"


# =============================================================================
# SC-12: "Forget home" in a folder that cannot be written in
# =============================================================================

def test_sc12_forget_home_in_an_unwritable_folder_is_refused(prefs_on):
    _put_store({})
    _prefs_path().write_text(json.dumps({"home_place": HOME}))
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    assert at.session_state["home_place"] == HOME, "the premise: the home is loaded"
    folder = _store().parent
    folder.chmod(0o555)
    try:
        at.sidebar.button(key="_forget_home").click().run()
        assert_no_exception(at, "Forget home")
        errors = [e.value for e in at.sidebar.error]
    finally:
        folder.chmod(0o755)
    assert at.session_state["home_place"] == HOME, "the session forgot a home the file keeps"
    assert [e for e in errors if e.startswith(FOLDER_SENTENCE)], errors
    assert _read(_prefs_path()).get("home_place") == HOME


# =============================================================================
# SC-13: a data folder that can be written in but not listed
# =============================================================================

def test_sc13_an_unlistable_folder_keeps_one_copy_of_one_content(scratch):
    _put_store({})
    _store().write_text("{not json")
    folder = _store().parent
    folder.chmod(0o300)
    try:
        first = make_app(date="2000-01-01", page="sources", timeout=300).run()
        second = make_app(date="2000-01-01", page="sources", timeout=300).run()
    finally:
        folder.chmod(0o755)
    assert_no_exception(first, "the first launch")
    assert_no_exception(second, "the second launch")
    copies = _copies()
    assert len(copies) == 1 and copies[0].read_text() == "{not json", [p.name for p in copies]
    for at in (first, second):
        assert [e for e in _alerts(at) if "A copy of the file was kept beside the saved charts" in e], _alerts(at)


# =============================================================================
# SC-14 (ruling 78): Save on an unchanged chart chooses it
# =============================================================================

def test_sc14_save_on_an_unchanged_chart_remembers_it(prefs_on):
    _put_store({"SA": FLORENCE, "R": dict(FLORENCE, date_string="1990-01-01")})
    a = make_app(date="2000-01-01", page="sources", timeout=300).run()
    b = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(a).select("SA").run()
    _picker(b).select("R").run()
    assert _read(_prefs_path()).get("last_chart") == "R", "the premise: B opened R last"
    _save_as(a, "SA")
    assert "'SA' is already saved as it is." in _sidebar_texts(a), _sidebar_texts(a)
    assert _read(_prefs_path()).get("last_chart") == "SA"


# =============================================================================
# SC-15: "already saved as it is" beside a strip that names no chart
# =============================================================================

def test_sc15_already_saved_names_the_record_on_the_strip(scratch):
    from datetime import time
    _put_store({"Rec": dict(FLORENCE, time_string="08:00:00")})
    a = make_app(date="2000-01-01", page="sources", timeout=300).run()
    b = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(a).select("Rec").run()
    _picker(b).select("Rec").run()
    for hour in (9, 8):
        b.session_state["time_input_key"] = time(hour, 0)
        _save_as(b, "Rec")
        b.sidebar.button(key="_replace_now").click().run()
    assert _read(_store())["Rec"]["time_string"] == "08:00:00", "the premise: B put 08:00 back"
    _save_as(a, "Rec")
    _save_as(a, "Rec")
    assert_no_exception(a, "A's saves")
    assert "'Rec' is already saved as it is." in _sidebar_texts(a), _sidebar_texts(a)
    assert _strip(a).startswith("Rec · "), _strip(a)


# =============================================================================
# SC-16: the stamp in _same_record
# =============================================================================

def test_sc16_a_record_that_gained_its_stamp_is_the_same_record(scratch):
    engine = _engine()
    same = _app_function("_same_record", record_number=engine.record_number)
    stamped = dict(FLORENCE, saved_with={"app": "x", "schema": 2})
    assert same(stamped, FLORENCE) is True
    assert same(FLORENCE, stamped) is True
    assert same(dict(FLORENCE, time_string="09:00:00"), FLORENCE) is False


# =============================================================================
# SC-17: re-saving a record the loader would refuse
# =============================================================================

def test_sc17_a_record_the_loader_refuses_is_not_already_saved(scratch):
    _put_store({"First": FLORENCE, "No time": {k: v for k, v in FLORENCE.items() if k != "time_string"}})
    at = make_app(date="2000-01-01", page="sources", timeout=300).run()
    _picker(at).select("First").run()
    _save_as(at, "No time")
    assert "'No time' is already saved as it is." not in _sidebar_texts(at), _sidebar_texts(at)
    at.sidebar.button(key="_replace_now").click().run()
    assert_no_exception(at, "Replace")
    assert _read(_store())["No time"].get("time_string") == "10:30:00", _read(_store())["No time"]


# =============================================================================
# SC-18: a session key too large for a float
# =============================================================================

def test_sc18_a_target_age_past_a_float_does_not_take_the_page_down(scratch):
    at = make_app(date="2000-01-01", page="chart", timeout=300)
    at.session_state["_target_age"] = 10 ** 400
    at.run()
    assert_no_exception(at, "the run")


# =============================================================================
# SC-04 (ruling 77): the bound itself
# =============================================================================

def test_sc04_the_locks_wait_about_ten_seconds(scratch):
    """Ruling 77, met by KS: the locks wait a bounded time, about 10 s. KS's
    pins shorten the bound to run; this holds the bound they shorten."""
    assert _engine().LOCK_WAIT_SECONDS == 10.0


# =============================================================================
# K-1 and K-2 (KS's re-check): the preferences' notices
# =============================================================================

SHORT = 0.5           # seconds: the lock's bound, shortened for these cases
BUSY_PREFS = ("Another window of this app is holding the preferences just now, so this choice was not kept. "
              "Try again in a moment.")


def test_k1_a_refused_dark_wheel_says_so_in_the_run_it_was_refused(prefs_on, monkeypatch):
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    assert engine._PREFERENCES_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        _dark_wheel(at).check().run()
    finally:
        engine._PREFERENCES_THREAD_LOCK.release()
    assert_no_exception(at, "the tick")
    assert BUSY_PREFS in _alerts(at), _alerts(at)
    assert _read(_prefs_path()).get("_wheel_dark") is False, "the tick was written without the lock"


def _between(monkeypatch, engine, other):
    """Run `other` to its end in a thread of its own just after the window's
    first engine.remember_preference returns, before the window reads what
    it left; joined within WAIT."""
    real = engine.remember_preference
    done = []

    def held(*args, **kwargs):
        kept = real(*args, **kwargs)
        if not done:
            done.append(True)
            runner = threading.Thread(target=other, daemon=True)
            runner.start()
            runner.join(WAIT)
            assert not runner.is_alive(), f"the other thread did not finish within {WAIT}s"
        return kept
    monkeypatch.setattr(engine, "remember_preference", held)


def test_k2_a_windows_busy_notice_is_its_own(prefs_on, monkeypatch):
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    lock = engine._PREFERENCES_THREAD_LOCK
    assert lock.acquire(timeout=WAIT)
    held = [True]

    def other_window():
        lock.release()
        held[0] = False
        assert engine.remember_preference("home_place", HOME) is True
    _between(monkeypatch, engine, other_window)
    try:
        _dark_wheel(at).check().run()
        shown = _alerts(at)
        at.run()
        shown += _alerts(at)
    finally:
        if held[0]:
            lock.release()
    assert_no_exception(at, "the tick")
    assert BUSY_PREFS in shown, shown


def test_k2_another_windows_busy_notice_is_not_this_windows(prefs_on, monkeypatch):
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    engine = _engine()
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    lock = engine._PREFERENCES_THREAD_LOCK

    def other_window():
        assert lock.acquire(timeout=WAIT)
        try:
            refused = []
            busy = threading.Thread(target=lambda: refused.append(engine.remember_preference("_launches", 99)),
                                    daemon=True)
            busy.start()
            busy.join(WAIT)
            assert refused == [False], refused
        finally:
            lock.release()
    _between(monkeypatch, engine, other_window)
    _dark_wheel(at).check().run()
    shown = _alerts(at)
    at.run()
    shown += _alerts(at)
    assert_no_exception(at, "the tick")
    assert BUSY_PREFS not in shown, shown
    assert _read(_prefs_path()).get("_wheel_dark") is True


def test_k2_another_windows_unreadable_notice_is_not_this_windows(prefs_on, monkeypatch):
    at = make_app(date="2000-01-01", page="chart", timeout=300).run()
    engine = _engine()

    def other_window():
        _prefs_path().write_text("{not json")
        assert engine.remember_preference("_launches", 5) is True     # copies the bytes aside, then writes
    _between(monkeypatch, engine, other_window)
    _dark_wheel(at).check().run()
    shown = _alerts(at)
    at.run()
    shown += _alerts(at)
    assert_no_exception(at, "the tick")
    copies = sorted(p.name for p in _store().parent.glob("preferences.json.unreadable-*"))
    assert len(copies) == 1, f"the premise: the other window kept the bytes aside: {copies}"
    assert not [t for t in shown if copies[0] in t], shown


# =============================================================================
# Ruling 93: a choice refused by the lock is said, and not retried
# =============================================================================

def _busy_tick(at, engine, monkeypatch):
    """Tick the window's Dark wheel while the preferences' lock is held: the
    write is refused as busy."""
    monkeypatch.setattr(engine, "LOCK_WAIT_SECONDS", SHORT)
    assert engine._PREFERENCES_THREAD_LOCK.acquire(timeout=WAIT)
    try:
        _dark_wheel(at).check().run()
    finally:
        engine._PREFERENCES_THREAD_LOCK.release()
    assert BUSY_PREFS in _alerts(at), f"the premise: the tick was refused as busy: {_alerts(at)}"


def test_sc09_a_choice_refused_by_the_lock_is_not_retried_on_a_later_run(prefs_on, monkeypatch):
    _put_store({"X": FLORENCE})
    a = make_app(date="2000-01-01", page="chart", timeout=300).run()
    engine = _engine()
    _busy_tick(a, engine, monkeypatch)
    a.run()
    a.run()
    assert_no_exception(a, "the reruns")
    assert BUSY_PREFS not in _alerts(a), "said again"
    assert _read(_prefs_path()).get("_wheel_dark") is False, "the refused choice was written on a later run"
    assert _dark_wheel(a).value is True, "the window's box keeps the reader's value"
