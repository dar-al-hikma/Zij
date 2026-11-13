"""The data folder, its move from the former name and its reads, made as
safe as their comments say.

- The stray tidy works in the data folder alone: beside a store kept as a
  link to a file in another folder, a stray is that folder's owner's.
- The folder moved or copied in from the former name is never wider than
  its owner's at the moment it takes the data folder's name.
- The folders above the data folder that a launch makes are made 0700;
  those already there are left as they are.
- The copy made when the move is refused publishes regular files and
  folders only, and is not published when some of its files cannot be
  copied, or the former folder holds a link or anything else: no folder is
  made, and the next look tries the move again.
- The data layer's first import, in a fresh interpreter, imports cleanly
  with no former folder, one to move, one to copy, one that cannot be copied
  whole and a copy a killed launch left: every name the folder's making
  reaches is bound above it.
- The store, the old stores, the recovery copies and the strays are read
  only as far as their bound; the comparison of a dead copy with the former
  folder waits on no pipe.
- A key given twice in one object of the store or of the preferences makes
  the file unreadable, as a chart named twice makes the store.
- The window's log is refused when the file opened is not what the name
  holds (a link put there between the look and the open, on Windows).
- The ignore list names every file the data folder holds.

Every test works in a folder under its own tmp_path; each that reloads the
data layer checks first that the folder it resolved is there, and each that
imports it in a fresh interpreter checks, before the import, that HOME,
XDG_DATA_HOME and APPDATA are under its tmp_path.
"""
import ast
import errno
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import subprocess
import symtable
import sys
import textwrap
import threading
import tracemalloc
import types
from pathlib import Path

import pytest

import user_data
from conftest import APP_PATH, EXECUTABLE_DIR, sync_engine_to_environment

# Each test's launches leave no held data folder open (conftest).
pytestmark = pytest.mark.usefixtures("the_data_folder_held_is_let_go")

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
WAIT = 10


def _engine(monkeypatch, base, preferences=False):
    """The data layer and the engine as a launch with XDG_DATA_HOME at
    `base` finds them; the folder they resolved is asserted under `base`
    before anything else is done."""
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    if preferences:
        monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    import engine
    assert Path(user_data.DATA_DIR).is_relative_to(base), user_data.DATA_DIR
    assert Path(engine.SAVED_CHARTS_PATH).is_relative_to(base), engine.SAVED_CHARTS_PATH
    return engine


def _plant(path, data):
    """A stray holding `data`, last written long before the launch."""
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.utime(path, (0, 0))
    return path


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _former_folder(base, mode=0o755):
    """A folder under the former name holding a store, the preferences and
    a sub-folder, made as an older version made them (folder 0755, files
    0644)."""
    base.mkdir(exist_ok=True)
    legacy = base / user_data._LEGACY_APP_DIR_NAME
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"Old": REC}, indent=2))
    (legacy / "preferences.json").write_text(json.dumps({"last_chart": "Old"}))
    (legacy / "sub").mkdir()
    (legacy / "sub" / "note.txt").write_text("kept")
    for path in (legacy / "saved_charts.json", legacy / "preferences.json", legacy / "sub" / "note.txt"):
        path.chmod(0o644)
    (legacy / "sub").chmod(0o755)
    legacy.chmod(mode)
    return legacy, base / user_data.APP_DIR_NAME


def _refuse_the_move(monkeypatch, legacy):
    real_rename = Path.rename

    def rename(self, target):
        if Path(self) == legacy:
            raise OSError(errno.EXDEV, "the move was refused (the test's)", str(self))
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", rename)


# =============================================================================
# Strays beside a linked store
# =============================================================================

def test_a_stray_beside_a_linked_store_in_another_folder_is_left(monkeypatch, tmp_path):
    """A link at the store's name is never followed: neither the file it
    names nor a stray beside that file is read, tidied or written."""
    engine = _engine(monkeypatch, tmp_path / "xdg")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = elsewhere / "x.json"
    target.write_text(json.dumps({"Mine": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    stray = _plant(elsewhere / "x.json.0123456789abcdef.tmp", json.dumps({"Theirs": REC}))
    assert engine.load_saved_charts() == {}
    assert stray.exists() and json.loads(stray.read_text()) == {"Theirs": REC}
    assert sorted(p.name for p in elsewhere.iterdir()) == ["x.json", "x.json.0123456789abcdef.tmp"]
    assert engine.write_saved_charts({"Mine": REC, "New": REC}) is False
    assert engine.SAVED_CHARTS_PATH.is_symlink() and json.loads(target.read_text()) == {"Mine": REC}


def test_a_stray_in_the_data_folder_is_still_tidied(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"Mine": REC}))
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"), b"not a store")
    assert engine.load_saved_charts() == {"Mine": REC}
    assert not stray.exists()


def test_a_stray_beside_a_store_linked_within_the_data_folder_is_left(monkeypatch, tmp_path):
    """A link at the store's name, even to a file in the data folder, is
    never followed: the file is not read, and a stray named after it is no
    stray of the store's, and is left."""
    engine = _engine(monkeypatch, tmp_path / "xdg")
    target = engine.SAVED_CHARTS_PATH.with_name("shared.json")
    target.write_text(json.dumps({"Mine": REC}))
    engine.SAVED_CHARTS_PATH.symlink_to(target)
    stray = _plant(target.with_name("shared.json.0123456789abcdef.tmp"), b"not a store")
    assert engine.load_saved_charts() == {}
    assert stray.exists() and engine.SAVED_CHARTS_PATH.is_symlink()


# =============================================================================
# The move from the former name: never wider than its owner's when published
# =============================================================================

def test_the_moved_former_folder_is_owner_only_when_it_takes_the_name(monkeypatch, tmp_path):
    legacy, target = _former_folder(tmp_path / "base")
    seen = []
    real_rename = Path.rename

    def rename(self, to):
        if Path(self) == legacy:
            seen.append(_mode(self))
        return real_rename(self, to)
    monkeypatch.setattr(Path, "rename", rename)
    assert user_data._make_user_data_dir(target) == target
    assert seen == [0o700], [oct(m) for m in seen]
    assert _mode(target) == 0o700 and not legacy.exists()
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_the_copied_former_folder_is_owner_only_when_it_takes_the_name(monkeypatch, tmp_path):
    """The former folder's narrowing is refused here (a filesystem that
    keeps no modes for it), so it stays wide before the move, which is
    refused; the copy copytree widens to its mode is narrowed before it is
    published. (Another account's former folder is not copied at all:
    tests/test_former_folder_and_versions_2026_10_31.py.) The former folder
    is narrowed through its descriptor, and the copy published by a rename
    from the folder it was made in."""
    legacy, target = _former_folder(tmp_path / "base")
    real_chmod = os.chmod

    def chmod(path, mode, *args, **kwargs):
        if _is(path, legacy):
            raise PermissionError(errno.EPERM, "no modes here (the test's)", str(path))
        return real_chmod(path, mode, *args, **kwargs)
    monkeypatch.setattr(os, "chmod", chmod)
    _refuse_the_move(monkeypatch, legacy)
    seen = []
    real_rename = os.rename

    def rename(src, dst, *args, **kwargs):
        if Path(dst) == target:
            seen.append(stat.S_IMODE(os.lstat(src, dir_fd=kwargs.get("src_dir_fd")).st_mode))
        return real_rename(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "rename", rename)
    assert user_data._make_user_data_dir(target) == target
    assert seen == [0o700], [oct(m) for m in seen]
    assert _mode(legacy) == 0o755, "the premise: the former folder was not narrowed"
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_a_copy_after_a_refused_move_leaves_the_former_folder_narrowed(monkeypatch, tmp_path):
    legacy, target = _former_folder(tmp_path / "base")
    _refuse_the_move(monkeypatch, legacy)
    assert user_data._make_user_data_dir(target) == target
    assert _mode(legacy) == 0o700 and _mode(target) == 0o700
    assert json.loads((target / "preferences.json").read_text()) == {"last_chart": "Old"}


# =============================================================================
# The folders above the data folder
# =============================================================================

@pytest.mark.parametrize("mask", [0o000, 0o022, 0o077, 0o444])
def test_missing_folders_above_the_data_folder_are_made_owner_only(tmp_path, mask):
    base = tmp_path / "base"
    base.mkdir()
    base.chmod(0o755)
    target = base / "a" / "b" / "Zij"
    old = os.umask(mask)
    try:
        assert user_data._make_user_data_dir(target) == target
    finally:
        os.umask(old)
    assert [oct(_mode(p)) for p in (base / "a", base / "a" / "b", target)] == ["0o700"] * 3
    assert _mode(base) == 0o755, "a folder already there was changed"


def test_a_folder_above_already_there_is_left_as_it_is(tmp_path):
    base = tmp_path / "base"
    (base / "a").mkdir(parents=True)
    (base / "a").chmod(0o751)
    target = base / "a" / "b" / "Zij"
    old = os.umask(0)
    try:
        user_data._make_user_data_dir(target)
    finally:
        os.umask(old)
    assert _mode(base / "a") == 0o751 and _mode(base / "a" / "b") == 0o700


def test_the_launch_makes_the_folders_above_owner_only(monkeypatch, tmp_path):
    old = os.umask(0)
    try:
        _engine(monkeypatch, tmp_path / "x" / "y")
    finally:
        os.umask(old)
    assert _mode(tmp_path / "x") == 0o700 and _mode(tmp_path / "x" / "y") == 0o700
    assert Path(user_data.DATA_DIR) == tmp_path / "x" / "y" / "Zij" and user_data.DATA_DIR_ERROR is None


# =============================================================================
# The copy carries links as links
# =============================================================================

@pytest.mark.parametrize("link", ["notes.txt", "tree", "relative"])
def test_a_link_in_the_former_folder_keeps_the_copy_from_being_published(monkeypatch, tmp_path, link):
    """The copy carried a link as a link, and the data folder published
    held a name leading out of it; a link of any kind there now keeps the
    copy from being published, and the former folder keeps it."""
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside bytes")
    named = {"notes.txt": str(outside / "secret.txt"), "tree": str(outside), "relative": "../elsewhere.txt"}[link]
    (legacy / link).symlink_to(named)
    _refuse_the_move(monkeypatch, legacy)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], "a folder was made, or a copy left"
    assert os.readlink(legacy / link) == named
    assert sorted(p.name for p in outside.iterdir()) == ["secret.txt"]


def test_a_link_at_the_former_name_is_carried_as_the_move_carries_it(monkeypatch, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o755)
    (real / "saved_charts.json").write_text(json.dumps({"Old": REC}))
    legacy = base / user_data._LEGACY_APP_DIR_NAME
    legacy.symlink_to(real)
    target = base / user_data.APP_DIR_NAME
    _refuse_the_move(monkeypatch, legacy)
    assert user_data._make_user_data_dir(target) == target
    assert target.is_symlink() and os.readlink(target) == str(real)
    assert legacy.is_symlink(), "the former link was changed"
    assert _mode(real) == 0o700, "the folder the link names was not narrowed, as the move's is"
    assert sorted(p.name for p in real.iterdir()) == ["saved_charts.json"]


def test_the_move_carries_a_link_at_the_former_name_unchanged(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    legacy = base / user_data._LEGACY_APP_DIR_NAME
    legacy.symlink_to(real)
    target = base / user_data.APP_DIR_NAME
    assert user_data._make_user_data_dir(target) == target
    assert target.is_symlink() and os.readlink(target) == str(real) and not os.path.lexists(legacy)


def _dead_copy(base, legacy, fill):
    """A copy left beside the data folder by a launch killed while making it,
    owner-only: one another account could write in is never compared, and
    is kept (tests/test_windows_owner_and_link_2026_11_02.py)."""
    staging = base / ".Zij.0123456789abcdef.copying"
    staging.mkdir(mode=0o700)
    fill(staging)
    staging.chmod(0o700)
    return staging


def test_a_dead_copy_holding_only_the_former_folders_links_is_removed(tmp_path):
    legacy, target = _former_folder(tmp_path / "base")
    (legacy / "link").symlink_to("/nowhere/at/all")

    def fill(staging):
        shutil.copy2(legacy / "saved_charts.json", staging / "saved_charts.json")
        (staging / "link").symlink_to("/nowhere/at/all")
    staging = _dead_copy(tmp_path / "base", legacy, fill)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(staging)


def test_a_dead_copy_an_earlier_version_made_through_a_link_is_still_removed(tmp_path):
    """An earlier version's copy held the bytes a link of the former folder
    led to; removing such a dead copy loses nothing, and it is removed."""
    legacy, target = _former_folder(tmp_path / "base")
    (tmp_path / "outside.txt").write_text("outside bytes")
    (legacy / "notes.txt").symlink_to(tmp_path / "outside.txt")

    def fill(staging):
        (staging / "notes.txt").write_text("outside bytes")
    staging = _dead_copy(tmp_path / "base", legacy, fill)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(staging)


def test_a_dead_copy_whose_link_names_another_thing_is_left(tmp_path):
    legacy, target = _former_folder(tmp_path / "base")
    (legacy / "link").symlink_to("/nowhere/at/all")

    def fill(staging):
        (staging / "link").symlink_to("/somewhere/else")
    staging = _dead_copy(tmp_path / "base", legacy, fill)
    user_data._remove_dead_copies(target, legacy)
    assert os.path.lexists(staging / "link")


# =============================================================================
# A copy some of whose files cannot be copied is not published
# =============================================================================

def _key(path):
    """The device and inode of what `path` -- a name or a descriptor -- is
    now; None where nothing is there."""
    try:
        seen = os.fstat(path) if isinstance(path, int) else os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return seen.st_dev, seen.st_ino


def _is(path, folder):
    """Whether `path` -- a name, or a descriptor the data layer reads
    through -- is the folder `folder` stands for now."""
    return _key(folder) is not None and _key(path) == _key(folder)


def _refuse_one_file(monkeypatch, name):
    """The copy's read of the file `name` (opened for reading relative to
    its folder's descriptor) refused; returns the real os.open."""
    real_open = os.open

    def refusing(path, flags, *args, **kwargs):
        if (kwargs.get("dir_fd") is not None and os.fspath(path) == name
                and not flags & (os.O_WRONLY | os.O_RDWR)):
            raise PermissionError(errno.EACCES, "refused (the test's)", str(path))
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", refusing)
    return real_open


def test_a_copy_that_could_not_copy_a_file_is_not_published(monkeypatch, tmp_path):
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    _refuse_one_file(monkeypatch, "preferences.json")
    with pytest.raises(user_data.FormerFolderNotCopied) as raised:
        user_data._make_user_data_dir(target)
    assert str(raised.value) == user_data.FORMER_FOLDER_NOT_COPIED and raised.value.strerror is None
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], "a folder was made, or a copy left"
    assert sorted(p.name for p in legacy.iterdir()) == ["preferences.json", "saved_charts.json", "sub"]
    # The next try, the file copied: everything arrives.
    monkeypatch.undo()
    _refuse_the_move(monkeypatch, legacy)
    assert user_data._make_user_data_dir(target) == target
    assert json.loads((target / "preferences.json").read_text()) == {"last_chart": "Old"}
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_a_copy_refused_only_its_modes_and_times_is_published(monkeypatch, tmp_path):
    """A filesystem that keeps no modes refuses the copy's change of mode
    and of times on every file and folder (each made through its
    descriptor); the copy still holds every byte, and is the whole copy."""
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    refused = []

    def refusing(real):
        def call(path, *args, **kwargs):
            if isinstance(path, int):
                refused.append(real.__name__)
                raise PermissionError(errno.EPERM, "no modes here (the test's)")
            return real(path, *args, **kwargs)
        return call
    monkeypatch.setattr(os, "chmod", refusing(os.chmod))
    monkeypatch.setattr(os, "utime", refusing(os.utime))
    assert user_data._make_user_data_dir(target) == target
    assert json.loads((target / "preferences.json").read_text()) == {"last_chart": "Old"}
    assert (target / "sub" / "note.txt").read_text() == "kept"
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name])
    assert {"chmod", "utime"} <= set(refused), "the premise: the copy's modes and times were refused"


def test_a_link_put_in_the_former_folder_during_the_copy_keeps_it_from_being_published(monkeypatch, tmp_path):
    """A link put in the former folder while the copy was being made: the
    comparison after the copy finds it, and the copy is not published; the
    former folder keeps the link."""
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    real_copy = user_data._copy_through

    def copy(src, dst):
        top = _is(src, legacy)
        made = real_copy(src, dst)
        if top:                                         # the whole copy made, before it is judged
            (legacy / "link").symlink_to("/another/thing")
        return made
    monkeypatch.setattr(user_data, "_copy_through", copy)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], "a folder was made, or a copy left"
    assert os.readlink(legacy / "link") == "/another/thing"


def test_a_launch_whose_copy_failed_says_so_and_tries_again(monkeypatch, tmp_path):
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    _refuse_one_file(monkeypatch, "preferences.json")
    engine = _engine(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR == user_data.FORMER_FOLDER_NOT_COPIED
    assert engine.data_folder_state() == ("made", user_data.FORMER_FOLDER_NOT_COPIED)
    assert not os.path.lexists(target)
    assert engine.data_folder_state() == ("made", user_data.FORMER_FOLDER_NOT_COPIED), "tried again, refused again"
    monkeypatch.undo()                                  # the file can be copied now
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    _refuse_the_move(monkeypatch, legacy)
    assert engine.data_folder_state() == (None, None)
    assert user_data.DATA_DIR_ERROR is None
    assert json.loads((target / "preferences.json").read_text()) == {"last_chart": "Old"}


def test_the_page_says_the_folder_could_not_be_made_while_the_copy_fails(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    real_open = _refuse_one_file(monkeypatch, "preferences.json")
    engine = _engine(monkeypatch, base)
    engine._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    assert not at.exception, at.exception
    said = [e.value for e in at.sidebar.warning if "their folder" in e.value]
    assert said == [f"Saved charts and preferences cannot be kept: their folder, `{target}`, could not be made "
                    f"({user_data.FORMER_FOLDER_NOT_COPIED}). Nothing can be saved and no home can be set "
                    "until it can."], said
    monkeypatch.setattr(os, "open", real_open)
    at.run()
    assert not at.exception, at.exception
    assert not [e.value for e in at.sidebar.warning if "their folder" in e.value]
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


# =============================================================================
# The data layer's first import, in a fresh interpreter
# =============================================================================

# A launch imports the data layer once, in a new process: every name the
# folder's making reaches must be bound by then. A reload re-runs the module
# in the namespace its first import filled, and cannot see a name defined
# below the call.
_FIRST_IMPORT = r"""
import errno, json, os, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
for name in ("HOME", "XDG_DATA_HOME", "APPDATA"):
    value = os.environ.get(name, "")
    assert value and Path(value).resolve().is_relative_to(root), (name, value)
print("FOLDER", Path(os.environ["XDG_DATA_HOME"]) / "Zij", flush=True)
if sys.argv[2] == "refuse the move":
    real_rename = Path.rename

    def rename(self, target):
        if self.name == "TraditionalAstrologyEngine":
            raise OSError(errno.EXDEV, "the move was refused (the test's)", str(self))
        return real_rename(self, target)
    Path.rename = rename
import user_data
assert Path(user_data.DATA_DIR).resolve().is_relative_to(root), user_data.DATA_DIR
print("CHILD " + json.dumps({"folder": str(user_data.DATA_DIR), "error": user_data.DATA_DIR_ERROR}))
"""


def _first_import(tmp_path, base, move=True):
    """Import the data layer in a fresh interpreter with HOME, XDG_DATA_HOME
    and APPDATA under `tmp_path` (XDG_DATA_HOME at `base`), the former
    folder's move refused when `move` is False; what the import left in
    DATA_DIR and DATA_DIR_ERROR."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("HOME", "XDG_DATA_HOME", "APPDATA")}
    env.update(HOME=str(home), XDG_DATA_HOME=str(base), APPDATA=str(tmp_path / "appdata"),
               PYTHONPATH=str(EXECUTABLE_DIR))
    done = subprocess.run([sys.executable, "-c", _FIRST_IMPORT, str(tmp_path), "move" if move else "refuse the move"],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("CHILD ")]
    assert done.returncode == 0 and lines, (done.stdout[-1000:], done.stderr[-3000:])
    out = json.loads(lines[-1][len("CHILD "):])
    assert Path(out["folder"]) == base / user_data.APP_DIR_NAME
    return out


def _listing(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*"))


FORMER = ["preferences.json", "saved_charts.json", "sub", "sub/note.txt"]


def test_the_first_import_with_no_former_folder_makes_the_folder(tmp_path):
    base = tmp_path / "xdg"
    out = _first_import(tmp_path, base)
    assert out["error"] is None
    assert _listing(base) == [user_data.APP_DIR_NAME] and _mode(base / user_data.APP_DIR_NAME) == 0o700


def test_the_first_import_moves_the_former_folder_in(tmp_path):
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    out = _first_import(tmp_path, base)
    assert out["error"] is None
    assert sorted(p.name for p in base.iterdir()) == [target.name]
    assert _listing(target) == FORMER and _mode(target) == 0o700


def test_the_first_import_copies_the_former_folder_when_the_move_is_refused(tmp_path):
    """The copy's look at what the former folder holds, and its
    comparison, run in the first import too."""
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    held = sorted(FORMER)
    out = _first_import(tmp_path, base, move=False)
    assert out["error"] is None
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name]), "a copy was left beside"
    assert _listing(target) == held and _listing(legacy) == held and _mode(target) == 0o700
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_the_first_import_whose_copy_cannot_be_whole_makes_no_folder_and_says_why(tmp_path):
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    os.mkfifo(legacy / "pipe")
    out = _first_import(tmp_path, base, move=False)
    assert out["error"] == user_data.FORMER_FOLDER_NOT_COPIED
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], "a folder was made, or a copy left"
    assert _listing(legacy) == sorted(FORMER + ["pipe"])


def test_the_first_import_removes_a_dead_copy_beside_the_data_folder(tmp_path):
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    target.mkdir(mode=0o700)
    (target / "saved_charts.json").write_text(json.dumps({"New": REC}))
    staging = _dead_copy(base, legacy, lambda s: shutil.copy2(legacy / "saved_charts.json", s / "saved_charts.json"))
    out = _first_import(tmp_path, base)
    assert out["error"] is None
    assert not os.path.lexists(staging)
    assert sorted(p.name for p in base.iterdir()) == sorted([legacy.name, target.name])
    assert json.loads((target / "saved_charts.json").read_text()) == {"New": REC} and _listing(legacy) == FORMER


@pytest.mark.parametrize("mode", [0o700, 0o755, 0o775], ids=["owner-only", "readable by others",
                                                             "writable by its group"])
@pytest.mark.parametrize("move", [False, True], ids=["move refused", "move allowed"])
def test_the_first_import_after_a_failed_copy_removes_its_copy_and_brings_the_folder_in(tmp_path, move, mode):
    """What a copy left when the launch making it died before publishing it
    -- every file copied, the folder never renamed -- is a dead copy: the
    next launch removes it, where it is this account's and no other account
    can write in it or in anything in it (owner-only, or open to others for
    reading, as copytree leaves it with the former folder's mode), and moves
    (or copies) the former folder in. One its group may write in is left
    unread and kept: what is in it may be another account's."""
    base = tmp_path / "xdg"
    legacy, target = _former_folder(base)
    staging = base / ".Zij.0123456789abcdef.copying"
    shutil.copytree(legacy, staging, symlinks=True)
    staging.chmod(mode)
    out = _first_import(tmp_path, base, move=move)
    assert out["error"] is None
    kept = [staging.name] if mode & 0o022 else []
    assert os.path.lexists(staging) is bool(kept)
    assert sorted(p.name for p in base.iterdir()) == sorted(([target.name] if move else [legacy.name, target.name])
                                                            + kept)
    assert _listing(target) == FORMER and _mode(target) == 0o700


def _bindings(tree):
    """Each name the module binds at its top level, with the line it is
    first bound at."""
    first = {}

    def bind(name, line):
        first[name] = min(line, first.get(name, line))

    def walk(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bind(node.name, node.lineno)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bind(node.id, node.lineno)
        elif isinstance(node, ast.alias):
            bind((node.asname or node.name).split(".")[0], node.lineno)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bind(node.name, node.lineno)
        for child in ast.iter_child_nodes(node):
            walk(child)
    for statement in tree.body:
        walk(statement)
    return first


def _scope_reads(table, bound):
    """The module's names read in the scope `table` (a symtable) and in
    every scope nested in it, each scope by itself: a name a scope reads
    that is global there -- not its parameter or its own name, nor a name
    of a function around it -- so a nested scope's own name never hides the
    outer one's read of the module's name. Annotations' scopes are read as
    well, though their names are looked up only when they are asked for."""
    found = {symbol.get_name() for symbol in table.get_symbols()
             if symbol.is_referenced() and symbol.is_global() and symbol.get_name() in bound}
    for child in table.get_children():
        found |= _scope_reads(child, bound)
    return found


def _reached_at_import(source):
    """For the statement that makes the data folder at import, the module's
    names it reads, through every function it can call (its call graph
    through the module), each with the line it is first bound at; the line
    of the statement; and the functions and classes reached."""
    tree = ast.parse(source)
    bound = _bindings(tree)
    defined = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    module = symtable.symtable(source, "user_data.py", "exec")
    scopes = {(table.get_name(), table.get_lineno()): table for table in module.get_children()}
    call = [n for n in tree.body if isinstance(n, ast.Try)
            and any(isinstance(s, ast.Assign) and ast.unparse(s.targets[0]) == "DATA_DIR" for s in n.body)]
    assert len(call) == 1, "the statement that makes the data folder at import was not found"
    # The statement is read as the body of a function of its own, so that
    # what it loads is global there and what it binds (the exception's
    # name) its own.
    wrapped = "def _the_call():\n" + textwrap.indent(ast.get_source_segment(source, call[0]), "    ")
    the_call = next(table for table in symtable.symtable(wrapped, "the call", "exec").get_children()
                    if table.get_name() == "_the_call")
    names, todo = set(), [the_call]
    seen = set()
    while todo:
        table = todo.pop()
        for name in _scope_reads(table, bound):
            names.add(name)
            if name in defined and name not in seen:
                seen.add(name)
                todo.append(scopes[(name, defined[name].lineno)])
    return {name: bound[name] for name in names}, call[0].lineno, seen


def test_every_name_the_import_reaches_is_bound_above_it():
    """Static: every function and class the import-time making of the data
    folder can reach, and every module name each of them reads, is bound
    above the statement that makes it -- one bound below fails a launch's
    import with NameError, which no reload in this process would show."""
    reached, line, functions = _reached_at_import((EXECUTABLE_DIR / "user_data.py").read_text(encoding="utf-8"))
    late = sorted(f"{name} (line {at})" for name, at in reached.items() if at >= line)
    assert late == [], f"bound below the import-time call at line {line}: {late}"
    assert {"_make_user_data_dir", "_copy_the_former_folder", "_remove_dead_copies", "_same_bytes",
            "_open_regular_file", "NotAPlainFile"} <= functions, sorted(functions)


def test_the_static_reach_finds_a_name_bound_below_the_call():
    """The instrument itself: a function the call reaches through two
    others, reading a name bound below the call, is found."""
    source = ("def a():\n    return b()\n\ndef b():\n    return c(1)\n\n"
              "try:\n    DATA_DIR = a()\nexcept OSError as exc:\n    DATA_DIR = None\n\n"
              "def c(x):\n    return LATE + x\n\nLATE = 1\n")
    reached, line, functions = _reached_at_import(source)
    assert functions == {"a", "b", "c"} and line == 7
    assert {name for name, at in reached.items() if at >= line} == {"c", "LATE"}


def test_the_static_reach_reads_each_scope_by_itself():
    """The instrument itself: a name bound below the call is found where the
    function the call reaches reads it, though a lambda in that function
    takes a parameter of the same name; and a name a nested function takes
    from the function around it is no read of the module's name."""
    source = ("def a():\n    return c(1) + d()\n\n"
              "try:\n    DATA_DIR = a()\nexcept OSError as exc:\n    DATA_DIR = None\n\n"
              "def c(x):\n    same = lambda LATE: LATE\n    return LATE + same(x)\n\n"
              "def d():\n    OWN = 1\n    return (lambda: OWN)()\n\n"
              "LATE = 1\nOWN = 2\n")
    reached, line, functions = _reached_at_import(source)
    assert functions == {"a", "c", "d"} and line == 4
    assert {name for name, at in reached.items() if at >= line} == {"c", "d", "LATE"}


def test_the_static_reach_reads_the_scopes_nested_in_a_function():
    """The instrument itself: a name bound below the call that a function
    the call reaches reads only inside a lambda of its own is found."""
    source = ("def a():\n    return c()\n\n"
              "try:\n    DATA_DIR = a()\nexcept OSError as exc:\n    DATA_DIR = None\n\n"
              "def c():\n    return (lambda: LATE)()\n\nLATE = 1\n")
    reached, line, functions = _reached_at_import(source)
    assert functions == {"a", "c"} and line == 4
    assert {name for name, at in reached.items() if at >= line} == {"c", "LATE"}


# =============================================================================
# Reads bounded before they are whole
# =============================================================================

SPARSE = 64 * 1024 * 1024
BOUND = 4096


def _sparse(path, size=SPARSE, head=b""):
    """A file of `size` bytes that takes no room: `head`, then nothing."""
    with open(path, "wb") as handle:
        handle.write(head)
        handle.truncate(size)
    return path


def _peak(fn):
    tracemalloc.start()
    try:
        result = fn()
        return result, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _small_bound(monkeypatch):
    """The bounds made small (after the data layer's reload, which sets
    them again), so that a file past them needs no room."""
    monkeypatch.setattr(user_data, "STORE_BYTE_LIMIT", BOUND, raising=False)
    monkeypatch.setattr(user_data, "PREFERENCES_BYTE_LIMIT", BOUND)


def test_a_store_past_the_bound_is_not_read_whole(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    _small_bound(monkeypatch)
    _sparse(engine.SAVED_CHARTS_PATH, head=b'{"A": {}}')
    charts, peak = _peak(engine.load_saved_charts)
    assert charts == {} and peak < SPARSE // 8, peak
    assert engine.store_notices()["unreadable"] and engine.store_notices()["copy"] is None
    stands, peak = _peak(engine.saved_charts_as_they_stand)
    assert stands.state == "unreadable" and peak < SPARSE // 8, (stands, peak)
    assert engine.SAVED_CHARTS_PATH.stat().st_size == SPARSE, "the store was changed"


def test_a_store_at_the_bound_is_read_and_one_byte_past_it_is_not(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    _small_bound(monkeypatch)
    text = json.dumps({"A": REC}).encode()
    engine.SAVED_CHARTS_PATH.write_bytes(text + b" " * (BOUND - len(text)))
    assert engine.load_saved_charts() == {"A": REC}
    engine.SAVED_CHARTS_PATH.write_bytes(text + b" " * (BOUND + 1 - len(text)))
    assert engine.load_saved_charts() == {} and engine.store_notices()["unreadable"]


def test_an_old_store_past_the_bound_is_not_read_whole_and_does_not_read(monkeypatch, tmp_path):
    base = tmp_path / "xdg"
    engine = _engine(monkeypatch, base)
    _small_bound(monkeypatch)
    legacy = base / user_data._LEGACY_APP_DIR_NAME
    legacy.mkdir()
    _sparse(legacy / "saved_charts.json", head=b'{"A": {}}')
    found, peak = _peak(user_data._the_first_old_store)
    assert found == (legacy / "saved_charts.json", None, False) and peak < SPARSE // 8, (found, peak)
    assert engine.load_saved_charts() == {}
    assert engine.store_notices()["old_not_a_file"] is False and not engine.SAVED_CHARTS_PATH.exists()


def test_a_recovery_copy_past_the_bytes_compared_is_not_read_whole(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    _small_bound(monkeypatch)
    engine.SAVED_CHARTS_PATH.write_bytes(b"{not json")
    _sparse(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.unreadable-20200101-000000"), head=b"{not json")
    _, peak = _peak(engine.load_saved_charts)
    assert peak < SPARSE // 8, peak
    copy = engine.store_notices()["copy"]
    assert copy and copy != "saved_charts.json.unreadable-20200101-000000"
    assert engine.SAVED_CHARTS_PATH.with_name(copy).read_bytes() == b"{not json"


def test_a_recovery_copy_in_a_folder_that_cannot_be_listed_is_not_read_whole(monkeypatch, tmp_path):
    """Where the folder cannot be listed, the copy named by the content's
    digest, and then the name already taken that the copy is asked for, are
    each read only as far as the bytes compared with them."""
    folder = tmp_path / "unlisted"
    folder.mkdir()
    store = folder / "saved_charts.json"
    data = b"{not json"
    real_listdir = os.listdir

    def listdir(path="."):
        if Path(path) == folder:
            raise PermissionError(errno.EACCES, "not listed (the test's)", str(path))
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", listdir)
    stem = f"saved_charts.json.unreadable-{hashlib.sha256(data).hexdigest()[:16]}"
    _sparse(folder / stem, head=data)
    name, peak = _peak(lambda: user_data._preserve_unreadable_store(store, data))
    assert name == stem + "-2" and peak < SPARSE // 8, (name, peak)
    assert (folder / name).read_bytes() == data and (folder / stem).stat().st_size == SPARSE


@pytest.mark.parametrize("which", ["store", "preferences"])
def test_a_stray_past_the_bound_is_not_read_and_is_left(monkeypatch, tmp_path, which):
    engine = _engine(monkeypatch, tmp_path / "xdg", preferences=True)
    _small_bound(monkeypatch)
    path = engine.SAVED_CHARTS_PATH if which == "store" else engine.PREFERENCES_PATH
    stray = _sparse(path.with_name(path.name + ".0123456789abcdef.tmp"), head=b"{}")
    os.utime(stray, (0, 0))
    load = engine.load_saved_charts if which == "store" else engine.load_preferences
    _, peak = _peak(load)
    assert peak < SPARSE // 8, peak
    assert stray.exists() and stray.stat().st_size == SPARSE
    assert not list(path.parent.glob(path.name + ".recovered-*"))


def test_the_stray_reader_reads_no_further_than_its_bound(tmp_path):
    """The read itself is bounded, not only the listing's look at the size:
    a stray that grew past the bound after it was listed is not read whole."""
    stray = _sparse(tmp_path / "saved_charts.json.0123456789abcdef.tmp", head=b"{}")
    data, peak = _peak(lambda: user_data._read_the_stray(stray, os.lstat(stray), BOUND))
    assert data is None and peak < SPARSE // 8, peak
    small = _plant(tmp_path / "saved_charts.json.fedcba9876543210.tmp", b"{}")
    assert user_data._read_the_stray(small, os.lstat(small), BOUND) == b"{}"


def test_a_stray_within_the_bound_is_still_kept_aside(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    _small_bound(monkeypatch)
    stray = _plant(engine.SAVED_CHARTS_PATH.with_name("saved_charts.json.0123456789abcdef.tmp"),
                   json.dumps({"Cut short": REC}))
    assert engine.load_saved_charts() == {}
    assert not stray.exists() and engine.store_notices()["recovered"] == 1


# =============================================================================
# The comparison with the former folder waits on no pipe
# =============================================================================

def _in_a_thread(fn, unblock):
    out = {}

    def run():
        try:
            out["result"] = fn()
        except BaseException as exc:            # noqa: BLE001
            out["error"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(WAIT)
    if thread.is_alive():
        unblock()
        thread.join(WAIT)
        pytest.fail("the comparison waited on a pipe")
    if "error" in out:
        raise out["error"]
    return out.get("result")


def _unblock(fifo):
    def go():
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
    return go


def test_a_dead_copy_beside_a_pipe_in_the_former_folder_is_judged_at_once(tmp_path):
    legacy, target = _former_folder(tmp_path / "base")
    os.mkfifo(legacy / "pipe")

    def fill(staging):
        (staging / "pipe").write_bytes(b"")
    staging = _dead_copy(tmp_path / "base", legacy, fill)
    _in_a_thread(lambda: user_data._remove_dead_copies(target, legacy), _unblock(legacy / "pipe"))
    assert (staging / "pipe").exists(), "a copy of something that is not a file was taken for a copy"
    assert user_data._same_bytes(legacy / "pipe", staging / "pipe") is False
    assert user_data._same_bytes(staging / "pipe", legacy / "pipe") is False


def test_a_pipe_in_the_former_folder_keeps_the_copy_from_being_published(monkeypatch, tmp_path):
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    os.mkfifo(legacy / "pipe")
    _refuse_the_move(monkeypatch, legacy)
    with pytest.raises(user_data.FormerFolderNotCopied):
        _in_a_thread(lambda: user_data._make_user_data_dir(target), _unblock(legacy / "pipe"))
    assert sorted(p.name for p in base.iterdir()) == [legacy.name]


def test_two_files_of_the_same_bytes_are_the_same(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 3_000_000)
    (tmp_path / "b").write_bytes(b"x" * 3_000_000)
    (tmp_path / "c").write_bytes(b"x" * 2_999_999 + b"y")
    assert user_data._same_bytes(tmp_path / "a", tmp_path / "b") is True
    assert user_data._same_bytes(tmp_path / "a", tmp_path / "c") is False
    assert user_data._same_bytes(tmp_path / "a", tmp_path) is False


# =============================================================================
# A key given twice
# =============================================================================

@pytest.mark.parametrize("text, reason", [
    ('{"A": {"date_string": "1977-12-16", "lat": 10, "lat": -55}}', "a saved chart gives a field twice"),
    ('{"A": {"date_string": "1977-12-16", "readings": {"x": 1, "x": 2}}}', "a saved chart gives a field twice"),
    ('{"A": {"lat": 1}, "A": {"lat": 2}}', "a saved chart is named twice"),
])
def test_a_store_giving_a_key_twice_is_refused_and_kept_aside(monkeypatch, tmp_path, text, reason):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    with pytest.raises(ValueError, match=reason):
        user_data._parse_chart_mapping(text.encode())
    engine.SAVED_CHARTS_PATH.write_text(text)
    assert engine.load_saved_charts() == {}
    notices = engine.store_notices()
    assert notices["unreadable"] and engine.SAVED_CHARTS_PATH.with_name(notices["copy"]).read_text() == text
    assert engine.saved_charts_as_they_stand().state == "malformed"


def test_a_store_giving_each_key_once_still_loads(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg")
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"A": REC, "B": dict(REC, readings={"x": 1})}))
    assert sorted(engine.load_saved_charts()) == ["A", "B"]


@pytest.mark.parametrize("text", ['{"last_chart": "A", "last_chart": "B"}',
                                  '{"home_place": {"lat": 1, "lat": 2}}'])
def test_preferences_giving_a_key_twice_are_unreadable_and_kept_aside(monkeypatch, tmp_path, text):
    engine = _engine(monkeypatch, tmp_path / "xdg", preferences=True)
    engine.PREFERENCES_PATH.write_text(text)
    assert engine.load_preferences() == {}
    notices = engine.preferences_notices()
    assert notices["unreadable"] and engine.PREFERENCES_PATH.with_name(notices["copy"]).read_text() == text
    assert engine.PREFERENCES_PATH.read_text() == text
    stray = _plant(engine.PREFERENCES_PATH.with_name("preferences.json.0123456789abcdef.tmp"), text)
    assert user_data._reads_as_preferences(stray.read_bytes()) is False


def test_preferences_giving_each_key_once_still_load(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg", preferences=True)
    engine.PREFERENCES_PATH.write_text(json.dumps({"last_chart": "A"}))
    assert engine.load_preferences() == {"last_chart": "A"}


# =============================================================================
# The window's log: a link put at the name between the look and the open
# =============================================================================

def _open_window_log():
    """desktop_launcher._open_window_log and the names it reads, taken from
    the file's text (importing the launcher brings in the window's
    toolkit)."""
    source = (EXECUTABLE_DIR / "desktop_launcher.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name == "_open_window_log")
            or (isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["WINDOW_LOG_NAME"])]
    assert len(keep) == 2, [ast.unparse(n)[:40] for n in keep]
    import logging
    namespace = {"os": os, "stat": stat, "logging": logging}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "desktop_launcher.py", "exec"), namespace)
    return namespace


class _WindowsOs(types.ModuleType):
    """os as Windows has it for this purpose -- no O_NOFOLLOW, no getuid --
    whose islink answers truly and then puts a link at the name."""

    def __init__(self, plant):
        super().__init__("os")
        self.path = types.SimpleNamespace(**{k: getattr(os.path, k) for k in dir(os.path) if not k.startswith("__")})
        real_islink = os.path.islink

        def islink(name):
            answer = real_islink(name)
            plant(name)
            return answer
        self.path.islink = islink

    def __getattr__(self, name):
        if name in ("O_NOFOLLOW", "getuid"):
            raise AttributeError(name)
        return getattr(os, name)


def test_the_window_log_refuses_a_link_put_at_the_name_after_the_look(tmp_path):
    namespace = _open_window_log()
    folder = tmp_path / "Zij"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside file, first line\n")

    def plant(name):
        os.symlink(outside, name)
    namespace["os"] = _WindowsOs(plant)
    handler = namespace["_open_window_log"](folder)
    assert handler is None
    assert outside.read_text() == "outside file, first line\n"


def test_the_window_log_refuses_a_dangling_link_put_at_the_name_after_the_look(tmp_path):
    """A link naming no file, put at the name between the look and the open
    (Windows): the open has made the file it names, empty, and the log is
    refused; nothing is written there."""
    namespace = _open_window_log()
    folder = tmp_path / "Zij"
    folder.mkdir()
    outside = tmp_path / "outside.txt"

    def plant(name):
        os.symlink(outside, name)
    namespace["os"] = _WindowsOs(plant)
    assert namespace["_open_window_log"](folder) is None
    assert outside.exists() and outside.read_bytes() == b""


def test_the_window_log_still_opens_a_plain_file(tmp_path):
    namespace = _open_window_log()
    folder = tmp_path / "Zij"
    folder.mkdir()
    namespace["os"] = _WindowsOs(lambda name: None)
    handler = namespace["_open_window_log"](folder)
    assert handler is not None
    try:
        import logging
        handler.emit(logging.LogRecord("pywebview", logging.WARNING, __file__, 1, "a diagnostic line", None, None))
        handler.flush()
    finally:
        handler.close()
    assert "a diagnostic line" in (folder / namespace["WINDOW_LOG_NAME"]).read_text()


# =============================================================================
# The ignore list
# =============================================================================

def _ignored(name):
    rules = [line.strip() for line in (EXECUTABLE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    return any("/" not in rule and fnmatch.fnmatchcase(name, rule) for rule in rules)


def test_the_ignore_list_names_every_file_the_data_folder_holds(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path / "xdg", preferences=True)
    engine.SAVED_CHARTS_PATH.write_text(json.dumps({"A": REC}))
    engine.PREFERENCES_PATH.write_text(json.dumps({"last_chart": "A"}))
    made = [engine.SAVED_CHARTS_PATH.name, engine.PREFERENCES_PATH.name, user_data._IMPORTED_BESIDE_THE_PROGRAM,
            "saved_charts.json.tmp"]
    for path in (engine.SAVED_CHARTS_PATH, engine.PREFERENCES_PATH):
        made.append(user_data._preserve_unreadable_store(path, b"{bytes"))
        made.append(user_data._preserve_unreadable_store(path, b"{other bytes"))
        made.append(user_data._keep_stray_aside(path, b"{}"))
        tmp, fd = user_data._new_temp_file(path)
        os.close(fd)
        made.append(tmp.name)
    # The store's versions, made by two saves over it, and the temporary
    # file a version's write leaves when it is killed before the name is
    # given (the version's own writer's name, its file left as it stands).
    assert engine.write_saved_charts({"B": REC}) is True and engine.write_saved_charts({"C": REC}) is True
    versions = [path.name for _key, path in user_data._versions(engine.SAVED_CHARTS_PATH.parent,
                                                                 engine.SAVED_CHARTS_PATH.name)]
    assert len(versions) == 2, versions
    made += versions
    real_link, real_replace = os.link, os.replace

    def killed(*args, **kwargs):
        raise KeyboardInterrupt("killed before the version was named (the test's)")
    monkeypatch.setattr(os, "link", killed)
    monkeypatch.setattr(os, "replace", killed)
    real_remove = user_data._remove
    monkeypatch.setattr(user_data, "_remove", lambda path: None)        # a killed write removes nothing
    with pytest.raises(KeyboardInterrupt):
        user_data._new_version(engine.SAVED_CHARTS_PATH.parent, engine.SAVED_CHARTS_PATH.name, b"{}",
                               "20000101-000000", 1, 0o600)
    monkeypatch.setattr(os, "link", real_link)
    monkeypatch.setattr(os, "replace", real_replace)
    monkeypatch.setattr(user_data, "_remove", real_remove)
    left = [name for name in os.listdir(engine.SAVED_CHARTS_PATH.parent) if ".previous." in name]
    assert len(left) == 1 and left[0].endswith(".tmp"), left
    made += left
    made += [lock.name for lock in user_data._lock_files(engine.SAVED_CHARTS_PATH, "saved_charts.lock")]
    made += [lock.name for lock in user_data._lock_files(engine.PREFERENCES_PATH, "preferences.lock")]
    made.append("webview_debug.log")
    assert all(made) and len(set(made)) == len(made), made
    assert [name for name in made if not _ignored(name)] == []
    for name in ("saved_charts.json.0123.tmp", "saved_charts.json.0123456789abcdeg.tmp", "other.json.tmp",
                 "preferences.jsonl", "notes.json", "saved_charts.json.previous.0123.tmp",
                 "saved_charts.json.previous.0123456789abcdeg.tmp", "saved_charts.json.previous"):
        assert not _ignored(name), name


# =============================================================================
# Listings through a folder's descriptor, where a kept descriptor lags
# =============================================================================

AS_IT_STANDS = "listed as the filesystem lists"
LAGGING = "listed as a kept descriptor lags"


def _listings_that_lag(monkeypatch):
    """Every folder's descriptor listed as Btrfs lists one: the names that
    stood in the folder when the descriptor was opened or last rewound to
    its start (an lseek to 0, or the end of a listing, which rewinds it),
    and stand there still; a name made since is not listed. A listing by
    name sees the folder as it stands, as does a descriptor no listing or
    open was seen for."""
    real_open, real_close, real_lseek, real_listdir = os.open, os.close, os.lseek, os.listdir
    marks = {}

    def now(fd):
        fresh = real_open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
        try:
            return set(real_listdir(fresh))
        finally:
            real_close(fresh)

    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        try:
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                marks[fd] = now(fd)
        except OSError:
            marks.pop(fd, None)
        return fd

    def close(fd):
        marks.pop(fd, None)
        return real_close(fd)

    def lseek(fd, pos, how):
        if fd in marks and pos == 0 and how == os.SEEK_SET:
            marks[fd] = now(fd)
        return real_lseek(fd, pos, how)

    def listdir(path="."):
        if not isinstance(path, int):
            return real_listdir(path)
        names = now(path)
        shown = [name for name in sorted(names) if path not in marks or name in marks[path]]
        marks[path] = names                             # the listing's own rewind, at its end
        return shown
    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "close", close)
    monkeypatch.setattr(os, "lseek", lseek)
    monkeypatch.setattr(os, "listdir", listdir)


def _contents(top):
    """Every entry under `top`, by its path within it: a file's bytes, or
    None for a folder."""
    found = {}
    for root, dirs, files in os.walk(top):
        for name in dirs:
            found[os.path.relpath(os.path.join(root, name), top)] = None
        for name in files:
            found[os.path.relpath(os.path.join(root, name), top)] = Path(root, name).read_bytes()
    return found


def _carried(target):
    """The data folder _make_user_data_dir made, or None where the copy
    was not published."""
    try:
        return user_data._make_user_data_dir(target)
    except user_data.FormerFolderNotCopied:
        return None


@pytest.mark.parametrize("listing", [AS_IT_STANDS, LAGGING])
def test_a_copy_written_after_its_folder_was_opened_is_judged_whole(monkeypatch, tmp_path, listing):
    """The copy's folder is opened before the copy is written into it, and
    then listed to compare it with the former folder: it is found whole
    and published, everything the former folder holds in it."""
    legacy, target = _former_folder(tmp_path / "base")
    held = _contents(legacy)
    _refuse_the_move(monkeypatch, legacy)
    if listing == LAGGING:
        _listings_that_lag(monkeypatch)
    assert _carried(target) == target, "the copy was not judged whole"
    assert _contents(target) == held


@pytest.mark.parametrize("listing", [AS_IT_STANDS, LAGGING])
@pytest.mark.parametrize("published", [True, False])
def test_the_folder_a_copy_was_made_in_is_removed(monkeypatch, tmp_path, listing, published):
    """The folder the copy was made in, listed once while empty and then
    written into, is emptied and removed through its descriptor once the
    copy is published, or once it is found not whole (one file refused):
    nothing is left beside the data folder."""
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    if not published:
        _refuse_one_file(monkeypatch, "preferences.json")
    if listing == LAGGING:
        _listings_that_lag(monkeypatch)
    if published:
        # Whole by the comparison of the copy's names alone, so that only the removal is asked here.
        monkeypatch.setattr(user_data, "_copy_is_whole_through", lambda copy, top: True)
    assert _carried(target) == (target if published else None)
    left = sorted(p.name for p in base.iterdir())
    assert left == sorted([legacy.name] + ([target.name] if published else [])), left


def _made_in_the_former_folder(legacy):
    """A file and a folder others could write in, made in the former folder
    as another process of this account's would make them."""
    (legacy / "late").mkdir()
    (legacy / "late").chmod(0o777)
    (legacy / "late" / "note.txt").write_text("made late")
    (legacy / "late.txt").write_text("made late")


@pytest.mark.parametrize("listing", [AS_IT_STANDS, LAGGING])
def test_what_is_made_in_the_former_folder_after_it_was_opened_is_looked_at(monkeypatch, tmp_path, listing):
    """A folder made in the former folder after the launch opened it, and
    before the look at its entries: the look lists it through the
    descriptor opened before and narrows it to its owner, so that it
    arrives no wider than its owner's."""
    legacy, target = _former_folder(tmp_path / "base")
    real_look = user_data._only_this_accounts_entries

    def look(top):
        _made_in_the_former_folder(legacy)
        return real_look(top)
    monkeypatch.setattr(user_data, "_only_this_accounts_entries", look)
    if listing == LAGGING:
        _listings_that_lag(monkeypatch)
    assert _carried(target) == target
    assert (target / "late" / "note.txt").read_text() == "made late"
    assert _mode(target / "late") == 0o700, oct(_mode(target / "late"))


@pytest.mark.parametrize("listing", [AS_IT_STANDS, LAGGING])
def test_what_is_made_in_the_former_folder_after_the_look_is_copied(monkeypatch, tmp_path, listing):
    """A file and a folder made in the former folder after the look, before
    the copy reads it: the copy lists the former folder's descriptor again,
    copies them, and is found whole."""
    legacy, target = _former_folder(tmp_path / "base")
    _refuse_the_move(monkeypatch, legacy)
    real_copy = user_data._copy_through

    def copy(src, dst):
        if _is(src, legacy):
            _made_in_the_former_folder(legacy)
        return real_copy(src, dst)
    monkeypatch.setattr(user_data, "_copy_through", copy)
    if listing == LAGGING:
        _listings_that_lag(monkeypatch)
    assert _carried(target) == target, "the copy was not judged whole"
    assert (target / "late.txt").read_text() == "made late"
    assert (target / "late" / "note.txt").read_text() == "made late"


@pytest.mark.parametrize("listing", [AS_IT_STANDS, LAGGING])
def test_what_is_made_in_the_former_folder_after_the_copy_keeps_it_from_being_published(monkeypatch, tmp_path,
                                                                                         listing):
    """A file made in the former folder after the copy was made, before it
    is compared: the comparison lists the former folder's descriptor
    again, finds the file the copy lacks, and the copy is not published;
    the former folder keeps the file."""
    base = tmp_path / "base"
    legacy, target = _former_folder(base)
    _refuse_the_move(monkeypatch, legacy)
    real_whole = user_data._copy_is_whole_through

    def whole(copy, top):
        (legacy / "late.txt").write_text("made late")
        return real_whole(copy, top)
    monkeypatch.setattr(user_data, "_copy_is_whole_through", whole)
    if listing == LAGGING:
        _listings_that_lag(monkeypatch)
    assert _carried(target) is None, "a copy lacking a file was published"
    assert sorted(p.name for p in base.iterdir()) == [legacy.name], "a folder was made, or a copy left"
    assert (legacy / "late.txt").read_text() == "made late"
