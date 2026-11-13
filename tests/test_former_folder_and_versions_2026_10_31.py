"""The folder an older version kept the saved charts in, and the versions
of the store a save keeps.

- A former folder that belongs to another account is neither moved, nor
  copied, nor read: no data folder is made, the page's reason says why, and
  each launch asks again. The old-store reader passes such a folder over,
  and reads no store kept there as a link.
- The copy made when the move of this account's former folder is refused
  publishes regular files and folders only: a link anywhere in the former
  folder, or anything else that is neither, keeps it from being published.
  The move of this account's own folder, and a link at the former name,
  are as they were.
- Every former folder of this account's, whatever its mode now, is moved
  (or copied) only where every entry in it is this account's; one that
  others could write in when it was found must hold nothing but regular
  files and folders besides. One of this account's entries alone that was
  owner-only moves as before, links and all. A refused folder is given
  back the modes it had.
- A copy that failed in any way makes no data folder (the former folder
  stays, each launch tries again), but where another launch's data folder
  now stands; and every copy is compared whole before it is published.

Each test works under its own tmp_path: the data folder's base, the former
folder and every file a planted link names lie under it, and the folder
each launch resolved is asserted under it before anything is saved. A
second account is modelled inside the test (the owner os.stat, os.lstat and
os.fstat report for what stands at one name, judged by its device and inode,
so that a read through a descriptor sees it too), a refused move by a
Path.rename that raises. The data layer reads the former folder through
descriptors: a hook on a listing, a change of mode or the copy knows the
folder by its device and inode (_is, _key), not by its name.
"""
import builtins
import errno
import io
import json
import os
import shutil
from pathlib import Path

import pytest

import user_data

_OS_OPEN = os.open                      # the system's own, before any test's stand-in
from conftest import sync_engine_to_environment

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
LEGACY = "TraditionalAstrologyEngine"


def _launch(monkeypatch, base):
    """The data layer and the engine as a launch with XDG_DATA_HOME at
    `base` finds and makes them, the preferences on; the folder resolved is
    asserted under `base` first."""
    monkeypatch.setenv("XDG_DATA_HOME", str(base))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    import engine
    assert Path(user_data.DATA_DIR).is_relative_to(base), user_data.DATA_DIR
    assert Path(engine.SAVED_CHARTS_PATH).is_relative_to(base), engine.SAVED_CHARTS_PATH
    assert Path(engine.PREFERENCES_PATH).is_relative_to(base), engine.PREFERENCES_PATH
    return engine


def _save(engine, name):
    """A save as the app makes one: under the store's lock, the store as it
    stands, the record put in, the whole written. False where it was not."""
    try:
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts or {})
            charts[name] = REC
            return engine.write_saved_charts(charts)
    except engine.DataLockBusy:
        return False


def _base(tmp_path):
    base = tmp_path / "xdg"
    base.mkdir()
    return base, base / LEGACY, base / "Zij"


def _ordinary_former_folder(legacy):
    legacy.mkdir()
    (legacy / "saved_charts.json").write_text(json.dumps({"Old": REC}, indent=2))
    (legacy / "preferences.json").write_text(json.dumps({"last_chart": "Old"}))
    (legacy / "sub").mkdir()
    (legacy / "sub" / "note.txt").write_text("kept")


# What _ordinary_former_folder and _outside make, as _tree reads it.
ORDINARY = {"saved_charts.json": ("file", json.dumps({"Old": REC}, indent=2).encode()),
            "preferences.json": ("file", json.dumps({"last_chart": "Old"}).encode()),
            "sub": ("folder", None), "sub/note.txt": ("file", b"kept")}
OUTSIDE = {"drop.json": ("file", json.dumps({"Theirs": REC}).encode()),
           "victim.txt": ("file", b"the reader's own file")}


def _outside(tmp_path):
    """Two files outside the data folder a planted link may name: one the
    other account reads, one of the reader's own."""
    outside = tmp_path / "outside"
    outside.mkdir()
    drop = outside / "drop.json"
    drop.write_text(json.dumps({"Theirs": REC}))
    victim = outside / "victim.txt"
    victim.write_text("the reader's own file")
    return drop, victim


def _tree(top):
    """Every name under `top`: its kind, and its bytes or where it leads."""
    found = {}
    for root, dirs, files in os.walk(top):
        for name in dirs + files:
            path = Path(root) / name
            rel = str(path.relative_to(top))
            if path.is_symlink():
                found[rel] = ("link", os.readlink(path))
            elif path.is_dir():
                found[rel] = ("folder", None)
            elif path.is_file():
                found[rel] = ("file", path.read_bytes())
            else:
                found[rel] = ("other", None)
    return found


class _OwnedByAnother:
    """A stat result whose owner is another account's id."""

    def __init__(self, seen):
        self._seen = seen
        self.st_uid = os.getuid() + 1

    def __getattr__(self, name):
        return getattr(self._seen, name)


def _another_account_owns(monkeypatch, *names, link_only=False):
    """What stands at each of `names` -- the name itself, and where it is
    a link, what it leads to as well, unless `link_only` -- belongs to
    another account, as os.stat, os.lstat and os.fstat report it: judged
    at each call by device and inode, so that a look by a name relative to
    a folder's descriptor, or at a descriptor, finds the same owner (a
    reload of the data layer keeps it)."""
    real_stat, real_lstat = os.stat, os.lstat
    looks = (real_lstat,) if link_only else (real_lstat, real_stat)

    def theirs(seen):
        for name in names:
            for look in looks:
                try:
                    if os.path.samestat(look(name), seen):
                        return True
                except OSError:
                    pass
        return False

    def judged(real):
        def call(*args, **kwargs):
            seen = real(*args, **kwargs)
            return _OwnedByAnother(seen) if theirs(seen) else seen
        return call
    for name in ("stat", "lstat", "fstat"):
        monkeypatch.setattr(os, name, judged(getattr(os, name)))


def _key(path):
    """The device and inode of what `path` -- a name (a link followed) or
    a descriptor -- is now; None where nothing is there."""
    try:
        seen = os.fstat(path) if isinstance(path, int) else os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return seen.st_dev, seen.st_ino


def _is(path, folder):
    """Whether `path` -- a name, or a descriptor the data layer reads
    through -- is the folder `folder` stands for now."""
    return _key(folder) is not None and _key(path) == _key(folder)


def _watch_reads(monkeypatch, legacy):
    """Every open, listing, copy or move of a name in or at `legacy`, and
    every one through a descriptor: of `legacy` or a folder in it, or
    relative to one of those (dir_fd). A step of the whole path's judgment
    -- one name opened as a path only (O_PATH), relative to the folder above
    it -- reads nothing, and is not counted."""
    seen = []
    top = str(legacy)
    folders = {_key(each) for each in [legacy, *legacy.rglob("*")] if each.is_dir()} - {None}

    def under(path):
        if isinstance(path, int):
            return _key(path) in folders
        text = os.fspath(path)
        text = text.decode() if isinstance(text, bytes) else text
        return text == top or text.startswith(top + os.sep)

    def a_step(real, args):
        return real is _OS_OPEN and args and args[0] & getattr(os, "O_PATH", 0)

    def watched(real):
        def call(path=".", *args, **kwargs):
            fd = kwargs.get("dir_fd")
            if (under(path) or (fd is not None and _key(fd) in folders)) and not a_step(real, args):
                seen.append((real.__name__, os.fspath(path)))
            return real(path, *args, **kwargs)
        return call
    monkeypatch.setattr(os, "open", watched(os.open))
    monkeypatch.setattr(builtins, "open", watched(builtins.open))
    monkeypatch.setattr(io, "open", watched(io.open))
    monkeypatch.setattr(os, "listdir", watched(os.listdir))
    monkeypatch.setattr(os, "scandir", watched(os.scandir))
    monkeypatch.setattr(shutil, "copytree", watched(shutil.copytree))
    monkeypatch.setattr(os, "rename", watched(os.rename))
    monkeypatch.setattr(Path, "rename", watched(Path.rename))
    return seen


def _refuse_the_move(monkeypatch, legacy):
    real_rename = Path.rename

    def rename(self, target):
        if Path(self) == legacy:
            raise PermissionError(errno.EPERM, "the move was refused (the test's)", str(self))
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", rename)


# =============================================================================
# Another account's former folder: neither moved, nor copied, nor read
# =============================================================================

@pytest.mark.parametrize("refused", [False, True], ids=["move allowed", "move refused"])
def test_another_accounts_former_folder_is_not_taken_in(monkeypatch, tmp_path, refused):
    base, legacy, target = _base(tmp_path)
    drop, victim = _outside(tmp_path)
    legacy.mkdir()
    (legacy / "saved_charts.json").symlink_to(drop)
    (legacy / "preferences.json").symlink_to(victim)
    held, outside = _tree(legacy), _tree(tmp_path / "outside")
    if refused:
        _refuse_the_move(monkeypatch, legacy)
    _another_account_owns(monkeypatch, legacy)
    reads = _watch_reads(monkeypatch, legacy)
    engine = _launch(monkeypatch, base)
    assert not os.path.lexists(target), "a data folder was made"
    assert _save(engine, "Mine") is False
    assert engine.remember_preference("_launches", 4) is False
    assert engine.load_saved_charts() == {}
    assert reads == [], f"the former folder was read or moved: {reads}"
    reason = "the folder an older version kept them in belongs to another account"
    assert user_data.DATA_DIR_ERROR == reason == user_data.FORMER_FOLDER_NOT_OURS
    assert engine.data_folder_state() == ("made", reason)
    assert engine.data_folder_state() == ("made", reason), "asked again, refused again"
    assert sorted(p.name for p in base.iterdir()) == [LEGACY], sorted(base.iterdir())
    assert _tree(legacy) == held, "the former folder was changed"
    assert _tree(tmp_path / "outside") == outside, "a file a planted link names was written"


def test_the_page_says_why_another_accounts_former_folder_is_not_taken_in(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    from conftest import APP_PATH
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _another_account_owns(monkeypatch, legacy)
    engine = _launch(monkeypatch, base)
    engine._harness_environment = None
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    assert not at.exception, at.exception
    said = [e.value for e in at.sidebar.warning if "their folder" in e.value]
    assert said == [f"Saved charts and preferences cannot be kept: their folder, `{target}`, could not be made "
                    "(the folder an older version kept them in belongs to another account). Nothing can be saved "
                    "and no home can be set until it can."], said
    assert not os.path.lexists(target)


def test_a_link_another_account_made_at_the_former_name_is_refused(monkeypatch, tmp_path):
    """Judged at the name, a link there not followed: the link is another
    account's, though the folder it leads to is this account's own."""
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _ordinary_former_folder(real)
    legacy.symlink_to(real)
    _another_account_owns(monkeypatch, legacy, link_only=True)
    with pytest.raises(PermissionError) as raised:
        user_data._make_user_data_dir(target)
    assert not os.path.lexists(target) and legacy.is_symlink()
    assert raised.value.strerror == "the folder an older version kept them in belongs to another account"
    assert isinstance(raised.value, user_data.FormerFolderRefused)
    assert _tree(real) == ORDINARY


def test_a_link_of_this_accounts_at_the_former_name_is_carried_as_before(monkeypatch, tmp_path):
    """Unchanged: carried as a link, the folder it leads to judged and
    narrowed as the data folder; its charts arrive."""
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _ordinary_former_folder(real)
    real.chmod(0o755)
    legacy.symlink_to(real)
    _refuse_the_move(monkeypatch, legacy)
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None
    assert target.is_symlink() and os.readlink(target) == str(real) and legacy.is_symlink()
    assert engine.load_saved_charts() == {"Old": REC}
    assert os.stat(real).st_mode & 0o777 == 0o700


def test_the_dead_copies_beside_another_accounts_former_folder_are_left_unread(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    staging = base / ".Zij.0123456789abcdef.copying"
    staging.mkdir()
    (staging / "saved_charts.json").write_bytes((legacy / "saved_charts.json").read_bytes())
    _another_account_owns(monkeypatch, legacy)
    reads = _watch_reads(monkeypatch, legacy)
    user_data._remove_dead_copies(target, legacy)
    assert reads == [] and staging.is_dir()


# =============================================================================
# The old-store reader
# =============================================================================

def _a_data_folder_with_no_store(monkeypatch, tmp_path):
    """A launch with no former folder, its data folder made and empty; the
    former folder then planted beside it."""
    base, legacy, target = _base(tmp_path)
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and target.is_dir()
    assert not os.path.lexists(engine.SAVED_CHARTS_PATH)
    return engine, legacy, target


def test_the_old_store_reader_passes_another_accounts_former_folder_over(monkeypatch, tmp_path):
    engine, legacy, target = _a_data_folder_with_no_store(monkeypatch, tmp_path)
    _ordinary_former_folder(legacy)
    _another_account_owns(monkeypatch, legacy)
    reads = _watch_reads(monkeypatch, legacy)
    assert engine._the_first_old_store() == (None, None, False)
    assert engine.load_saved_charts() == {}
    assert engine.store_notices()["old_not_a_file"] is False
    with engine.saved_charts_lock():
        assert engine.bring_in_the_old_store() is False
    assert _save(engine, "Mine") is True
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == {"Mine": REC}
    assert reads == [], reads


def test_the_old_store_reader_reads_no_store_of_another_accounts(monkeypatch, tmp_path):
    engine, legacy, target = _a_data_folder_with_no_store(monkeypatch, tmp_path)
    _ordinary_former_folder(legacy)
    real_fstat = os.fstat
    store = os.stat(legacy / "saved_charts.json")

    def fstat(fd):
        seen = real_fstat(fd)
        if (seen.st_dev, seen.st_ino) == (store.st_dev, store.st_ino):
            return _OwnedByAnother(seen)
        return seen
    monkeypatch.setattr(os, "fstat", fstat)
    assert engine._the_first_old_store()[1:] == (None, False)
    with engine.saved_charts_lock():
        assert engine.bring_in_the_old_store() is False
    assert not os.path.lexists(engine.SAVED_CHARTS_PATH)


@pytest.mark.parametrize("names", ["a file", "nothing"])
def test_the_old_store_reader_reads_no_link_at_the_stores_name(monkeypatch, tmp_path, names):
    engine, legacy, target = _a_data_folder_with_no_store(monkeypatch, tmp_path)
    drop, _victim = _outside(tmp_path)
    legacy.mkdir()
    named = drop if names == "a file" else tmp_path / "outside" / "gone.json"
    (legacy / "saved_charts.json").symlink_to(named)
    # A link to a file stands there and is said as no file; a link to
    # nothing is a store that is not there, as it always was.
    said = names == "a file"
    assert engine._the_first_old_store() == ((legacy / "saved_charts.json", None, True) if said
                                             else (None, None, False))
    assert engine.load_saved_charts() == {}
    assert engine.store_notices()["old_not_a_file"] is said
    with engine.saved_charts_lock():
        assert engine.bring_in_the_old_store() is False
    assert not os.path.lexists(engine.SAVED_CHARTS_PATH), "the linked store was brought in"
    assert _tree(tmp_path / "outside") == OUTSIDE


@pytest.mark.parametrize("theirs", ["the folder", "the folder a link at its name leads to"])
def test_the_former_stores_reader_itself_reads_nothing_in_another_accounts_folder(monkeypatch, tmp_path, theirs):
    """The reader's own guard, beside its caller's: the folder at the name
    may change between the caller's look and the read."""
    legacy = tmp_path / LEGACY
    if theirs == "the folder":
        _ordinary_former_folder(legacy)
        _another_account_owns(monkeypatch, legacy)
    else:
        _ordinary_former_folder(tmp_path / "elsewhere")
        legacy.symlink_to(tmp_path / "elsewhere")
        real_stat = os.stat
        monkeypatch.setattr(os, "stat", lambda path, *a, **k: _OwnedByAnother(real_stat(path, *a, **k))
                            if not isinstance(path, int) and os.fspath(path) == str(legacy)
                            else real_stat(path, *a, **k))
    reads = _watch_reads(monkeypatch, legacy)
    with pytest.raises(PermissionError):
        user_data._read_the_former_folders_store(legacy / "saved_charts.json")
    assert reads == [], f"the store was read: {reads}"


def test_the_old_store_reader_still_brings_in_this_accounts_store(monkeypatch, tmp_path):
    engine, legacy, target = _a_data_folder_with_no_store(monkeypatch, tmp_path)
    _ordinary_former_folder(legacy)
    assert engine._the_first_old_store() == (legacy / "saved_charts.json", {"Old": REC}, False)
    assert engine.load_saved_charts() == {"Old": REC}
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == {"Old": REC}


# =============================================================================
# The copy publishes regular files and folders only
# =============================================================================

def _launch_without_a_data_folder(monkeypatch, base, legacy, target, reason):
    """A launch whose data folder is not made for `reason`; a chart save and
    a preference write after it land nowhere, and each look asks again."""
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR == reason
    assert not os.path.lexists(target), "a data folder was made"
    assert _save(engine, "Mine") is False
    assert engine.remember_preference("_launches", 4) is False
    assert engine.data_folder_state() == ("made", reason)
    assert not os.path.lexists(target), "a data folder was made"
    assert sorted(p.name for p in base.iterdir()) == [LEGACY], "a copy was left beside the former folder"
    return engine


def test_links_at_the_stores_names_keep_the_copy_from_being_published(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    drop, victim = _outside(tmp_path)
    legacy.mkdir()
    (legacy / "saved_charts.json").symlink_to(drop)
    (legacy / "preferences.json").symlink_to(victim)
    held, outside = _tree(legacy), _tree(tmp_path / "outside")
    _refuse_the_move(monkeypatch, legacy)
    named = {_key(drop), _key(victim)}
    opened = []
    real_open = os.open

    def watched(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        if _key(fd) in named:
            opened.append(args[0])
        return fd
    monkeypatch.setattr(os, "open", watched)
    _launch_without_a_data_folder(monkeypatch, base, legacy, target, user_data.FORMER_FOLDER_NOT_COPIED)
    assert not opened, f"a file a planted link names was opened: {opened}"
    assert _tree(legacy) == held, "the former folder was changed"
    assert _tree(tmp_path / "outside") == outside, "a file a planted link names was written"


def test_the_look_finds_regular_files_and_folders_only(tmp_path):
    top = tmp_path / "top"
    _ordinary_former_folder(top)
    assert user_data._only_files_and_folders(top) == {"saved_charts.json": False, "preferences.json": False,
                                                      "sub": True, os.path.join("sub", "note.txt"): False}
    (top / "sub" / "link").symlink_to("note.txt")
    assert user_data._only_files_and_folders(top) is None, "a link was taken for a file"
    (top / "sub" / "link").unlink()
    (top / "sub" / "tree").symlink_to(tmp_path)
    assert user_data._only_files_and_folders(top) is None, "a link to a folder was taken for a folder"
    (top / "sub" / "tree").unlink()
    os.mkfifo(top / "pipe")
    assert user_data._only_files_and_folders(top) is None, "a pipe was taken for a file"
    (top / "pipe").unlink()
    assert user_data._only_files_and_folders(top) is not None
    assert user_data._only_files_and_folders(tmp_path / "missing") is None, "a folder not there was listed"


def test_the_look_takes_a_junction_for_a_link(monkeypatch, tmp_path):
    """Windows' junction, a folder by its mode, is judged as a link: os.walk
    would go into it, and copytree copy what it leads to."""
    top = tmp_path / "top"
    _ordinary_former_folder(top)
    junction = top / "sub"
    monkeypatch.setattr(os.path, "isjunction", lambda path: Path(path) == junction, raising=False)
    assert user_data._only_files_and_folders(top) is None


def test_a_copy_holding_the_same_link_as_the_former_folder_is_not_whole(tmp_path):
    """The comparison of a copy with the former folder took two links naming
    the same thing for the same; a link on either side is now never whole."""
    legacy, staging = tmp_path / "legacy", tmp_path / "staging"
    _ordinary_former_folder(legacy)
    shutil.copytree(legacy, staging)
    assert user_data._copy_is_whole(staging, legacy) is True
    (legacy / "link").symlink_to("/nowhere/at/all")
    (staging / "link").symlink_to("/nowhere/at/all")
    assert user_data._copy_is_whole(staging, legacy) is False
    (legacy / "link").unlink()
    assert user_data._copy_is_whole(staging, legacy) is False, "a link only in the copy was taken for whole"


@pytest.mark.parametrize("plant", ["a link one folder down", "a link to a folder", "a link to nothing",
                                   "a pipe"])
def test_any_link_or_other_kind_in_the_former_folder_keeps_the_copy_from_being_published(monkeypatch, tmp_path,
                                                                                         plant):
    base, legacy, target = _base(tmp_path)
    drop, _victim = _outside(tmp_path)
    _ordinary_former_folder(legacy)
    if plant == "a link one folder down":
        (legacy / "sub" / "saved_charts.json").symlink_to(drop)
    elif plant == "a link to a folder":
        (legacy / "sub" / "elsewhere").symlink_to(tmp_path / "outside")
    elif plant == "a link to nothing":
        (legacy / "sub" / "gone.json").symlink_to(tmp_path / "outside" / "gone.json")
    else:
        os.mkfifo(legacy / "sub" / "pipe")
    held, outside = _tree(legacy), _tree(tmp_path / "outside")
    _refuse_the_move(monkeypatch, legacy)
    _launch_without_a_data_folder(monkeypatch, base, legacy, target, user_data.FORMER_FOLDER_NOT_COPIED)
    assert _tree(legacy) == held, "the former folder was changed"
    assert _tree(tmp_path / "outside") == outside


def test_a_link_put_in_the_former_folder_during_the_copy_is_found(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    drop, _victim = _outside(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)
    _copy_then(monkeypatch, legacy, lambda: None, before=lambda: (legacy / "sub" / "late.json").symlink_to(drop))
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]


def test_the_move_of_this_accounts_folder_still_carries_its_links(monkeypatch, tmp_path):
    """Unchanged: the links an account keeps in its own folder are its own,
    and the move carries them."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub" / "link").symlink_to("note.txt")
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and not os.path.lexists(legacy)
    assert os.readlink(target / "sub" / "link") == "note.txt"
    assert engine.load_saved_charts() == {"Old": REC}


# =============================================================================
# A former folder of this account's that others could write in
# =============================================================================

def _mode(path):
    return os.lstat(path).st_mode & 0o777


NOT_CARRIED = ("the folder an older version kept them in was open to other accounts and holds something that is "
               "not carried in")
BUSY = "the folder an older version kept them in is in use elsewhere"
UNREADABLE = "the folder an older version kept them in, or a folder in it, cannot be read"


@pytest.mark.parametrize("move", ["move allowed", "move refused"])
def test_a_wide_former_folder_with_a_link_is_neither_moved_nor_copied(monkeypatch, tmp_path, move):
    base, legacy, target = _base(tmp_path)
    drop, _victim = _outside(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "saved_charts.json").unlink()
    (legacy / "saved_charts.json").symlink_to(drop)
    legacy.chmod(0o777)
    if move == "move refused":
        _refuse_the_move(monkeypatch, legacy)
    engine = _launch(monkeypatch, base)
    assert not os.path.lexists(target), "a data folder was made"
    assert os.readlink(legacy / "saved_charts.json") == str(drop), "the former folder was changed"
    assert _save(engine, "Mine") is False
    assert _tree(tmp_path / "outside") == OUTSIDE, "the link's target was written"
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]
    assert user_data.DATA_DIR_ERROR == NOT_CARRIED
    assert engine.data_folder_state() == ("made", NOT_CARRIED)
    assert user_data.FORMER_FOLDER_NOT_CARRIED == NOT_CARRIED
    assert engine.data_folder_state() == ("made", NOT_CARRIED), "asked again, refused again"


@pytest.mark.parametrize("plant", ["another account's file", "a pipe", "another account's folder"])
def test_a_wide_former_folder_holding_what_others_could_put_there_is_not_moved(monkeypatch, tmp_path, plant):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    legacy.chmod(0o777)
    if plant == "another account's file":
        (legacy / "theirs.json").write_text("{}")
        _another_account_owns(monkeypatch, legacy / "theirs.json")
    elif plant == "a pipe":
        os.mkfifo(legacy / "sub" / "pipe")
    else:
        (legacy / "theirs").mkdir()
        _another_account_owns(monkeypatch, legacy / "theirs")
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(target)
    assert not os.path.lexists(target) and sorted(p.name for p in base.iterdir()) == [LEGACY]
    assert str(raised.value) == NOT_CARRIED and isinstance(raised.value, user_data.FormerFolderNotCarried)


def test_a_wide_former_folder_of_this_accounts_files_moves_narrowed(monkeypatch, tmp_path):
    """As today, but the folders in it are narrowed too, before each is
    looked at, so that nothing can be put in one between the look and the
    move."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub").chmod(0o777)
    (legacy / "sub" / "note.txt").chmod(0o644)
    legacy.chmod(0o777)
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and not os.path.lexists(legacy)
    assert _tree(target) == ORDINARY
    assert _mode(target) == 0o700 and _mode(target / "sub") == 0o700, oct(_mode(target / "sub"))
    assert _mode(target / "sub" / "note.txt") == 0o644, "a file's own mode was changed"
    assert engine.load_saved_charts() == {"Old": REC}


def test_an_owner_only_former_folder_with_a_link_moves_as_before(monkeypatch, tmp_path):
    """The links an account keeps in its own folder, never open to others,
    are its own: moved as they were."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub" / "link").symlink_to("note.txt")
    legacy.chmod(0o700)
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and not os.path.lexists(legacy)
    assert os.readlink(target / "sub" / "link") == "note.txt"
    assert engine.load_saved_charts() == {"Old": REC}


def test_the_look_narrows_each_folder_before_listing_it(monkeypatch, tmp_path):
    """A folder is narrowed before it is listed: an entry another account
    put in it before the narrowing is found, none can be put after."""
    top = tmp_path / "top"
    _ordinary_former_folder(top)
    (top / "sub").chmod(0o777)
    order = []
    real_listdir, real_chmod = os.listdir, os.chmod
    monkeypatch.setattr(os, "listdir", lambda path=".": order.append(("list", _key(path))) or real_listdir(path))
    monkeypatch.setattr(os, "chmod", lambda path, mode, *a, **k: order.append(("narrow", _key(path)))
                        or real_chmod(path, mode, *a, **k))
    fd = user_data._open_a_folder(top)
    try:
        assert user_data._only_this_accounts_entries(fd) is None
    finally:
        os.close(fd)
    sub = _key(top / "sub")
    assert order.index(("narrow", sub)) < order.index(("list", sub)), order
    assert _mode(top / "sub") == 0o700


def test_a_folder_not_carried_in_keeps_the_modes_it_had(monkeypatch, tmp_path):
    """Narrowed and left so, it would read at the next launch as a folder
    never open to others, and be moved whatever it holds."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub").chmod(0o777)
    (legacy / "sub" / "link").symlink_to("note.txt")
    legacy.chmod(0o777)
    for _launch_again in range(2):
        with pytest.raises(OSError) as raised:
            user_data._make_user_data_dir(target)
        assert _mode(legacy) == 0o777 and _mode(legacy / "sub") == 0o777
        assert str(raised.value) == NOT_CARRIED
        assert not os.path.lexists(target)


# =============================================================================
# Every former folder of this account's: each entry this account's, whatever
# the folder's mode is now
# =============================================================================

def _another_accounts_link_at_the_preferences(monkeypatch, tmp_path, legacy):
    """This account's ordinary former folder, but for a link at
    preferences.json that another account made, naming a file of the
    reader's own under tmp_path; returns that file."""
    _drop, victim = _outside(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "preferences.json").unlink()
    (legacy / "preferences.json").symlink_to(victim)
    _another_account_owns(monkeypatch, legacy / "preferences.json", link_only=True)
    return victim


def _launched_and_refused(monkeypatch, tmp_path, base, legacy, target, victim):
    """A launch, a save and a preference write: no data folder, the reason
    given, the former folder and every file outside as they were."""
    held = _tree(legacy)
    engine = _launch(monkeypatch, base)
    assert not os.path.lexists(target), "a data folder was made"
    assert _save(engine, "Mine") is False
    assert engine.remember_preference("_launches", 4) is False
    assert user_data.DATA_DIR_ERROR == NOT_CARRIED
    assert engine.data_folder_state() == ("made", NOT_CARRIED), "asked again, refused again"
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]
    assert _tree(legacy) == held, "the former folder was changed"
    assert os.readlink(legacy / "preferences.json") == str(victim)
    assert _tree(tmp_path / "outside") == OUTSIDE, "a file a planted link names was written"


@pytest.mark.parametrize("mode", [0o700, 0o755], ids=["owner-only", "readable by others"])
def test_another_accounts_link_in_a_closed_former_folder_is_not_carried_in(monkeypatch, tmp_path, mode):
    """A folder once open to others, since closed by its owner: its mode no
    longer says so, the link's owner does."""
    base, legacy, target = _base(tmp_path)
    victim = _another_accounts_link_at_the_preferences(monkeypatch, tmp_path, legacy)
    legacy.chmod(mode)
    _launched_and_refused(monkeypatch, tmp_path, base, legacy, target, victim)
    assert _mode(legacy) == mode, oct(_mode(legacy))


class _Killed(BaseException):
    """A launch ended where it stood (the test's)."""


def test_another_accounts_link_is_not_carried_in_after_a_launch_killed_in_its_look(monkeypatch, tmp_path):
    """The launch killed while it looked left the folder narrowed, its
    modes not given back: the next finds it owner-only."""
    base, legacy, target = _base(tmp_path)
    victim = _another_accounts_link_at_the_preferences(monkeypatch, tmp_path, legacy)
    (legacy / "sub").chmod(0o777)
    legacy.chmod(0o777)
    real_listdir = os.listdir

    def killed(path="."):
        if _is(path, legacy):
            raise _Killed()
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", killed)
    with pytest.raises(_Killed):
        user_data._make_user_data_dir(target)
    monkeypatch.setattr(os, "listdir", real_listdir)
    assert _mode(legacy) == 0o700 and not os.path.lexists(target)
    _launched_and_refused(monkeypatch, tmp_path, base, legacy, target, victim)


def test_another_accounts_link_is_not_carried_in_by_a_launch_during_anothers_look(monkeypatch, tmp_path):
    """A second launch comes while the first, its listing held part-way,
    has narrowed the folder: it would find it owner-only. It cannot have
    the first's lock, and refuses (here, where the first waits on it, it
    cannot wait the first out)."""
    base, legacy, target = _base(tmp_path)
    victim = _another_accounts_link_at_the_preferences(monkeypatch, tmp_path, legacy)
    legacy.chmod(0o777)
    monkeypatch.setattr(user_data, "_FORMER_FOLDER_LOCK_WAIT", 0.2, raising=False)
    real_listdir = os.listdir
    second = []

    def held(path="."):
        if _is(path, legacy) and not second:
            second.append(_mode(legacy))
            with pytest.raises(OSError) as raised:
                user_data._make_user_data_dir(target)
            second.append(str(raised.value))
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", held)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(target)
    monkeypatch.setattr(os, "listdir", real_listdir)
    assert not os.path.lexists(target), "the second launch moved it"
    assert second == [0o700, BUSY] and str(raised.value) == NOT_CARRIED, second
    assert _mode(legacy) == 0o777
    _launched_and_refused(monkeypatch, tmp_path, base, legacy, target, victim)


def test_another_accounts_entry_in_a_wide_folder_under_a_closed_one_is_not_carried_in(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub" / "theirs.json").write_text("{}")
    _another_account_owns(monkeypatch, legacy / "sub" / "theirs.json")
    (legacy / "sub").chmod(0o777)
    legacy.chmod(0o755)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(target)
    assert str(raised.value) == NOT_CARRIED and isinstance(raised.value, user_data.FormerFolderNotCarried)
    assert not os.path.lexists(target) and sorted(p.name for p in base.iterdir()) == [LEGACY]


def test_a_wide_folder_under_a_closed_one_is_narrowed_before_it_is_listed(monkeypatch, tmp_path):
    """Nothing another account puts in it between the look and the move is
    carried in: once narrowed, it can put nothing there."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub").chmod(0o777)
    legacy.chmod(0o755)
    order = []
    sub = _key(legacy / "sub")
    real_listdir, real_chmod = os.listdir, os.chmod
    monkeypatch.setattr(os, "listdir", lambda path=".": order.append(("list", _key(path))) or real_listdir(path))
    monkeypatch.setattr(os, "chmod", lambda path, mode, *a, **k: order.append(("narrow", _key(path)))
                        or real_chmod(path, mode, *a, **k))
    assert user_data._make_user_data_dir(target) == target
    assert order.index(("narrow", sub)) < order.index(("list", sub)), order
    assert not os.path.lexists(legacy) and _tree(target) == ORDINARY
    assert _mode(target / "sub") == 0o700


def _may_set_setgid_on_a_folder(probe):
    """Whether this account may give a folder its setgid bit: a refused
    change, or the bit not there when read back, says it may not."""
    import stat
    probe.mkdir()
    try:
        probe.chmod(0o2775)
    except PermissionError:
        return False
    return bool(os.lstat(probe).st_mode & stat.S_ISGID)


@pytest.mark.parametrize("refusal", ["another account's file", "a link of this account's"])
def test_a_refused_folder_gets_back_exactly_every_mode_the_narrowing_changed(monkeypatch, tmp_path, refusal):
    """Every folder narrowed, not only those others could write in, with
    its setgid bit (where this account may set it) and sticky bit; the
    refusal found in the folder listed last, so that every other has been
    narrowed by then."""
    import stat
    base, legacy, target = _base(tmp_path)
    legacy.mkdir()
    # A service hardened against setuid and setgid bits refuses the change;
    # there that folder keeps an ordinary mode, and the top's sticky bit
    # still pins that a special bit is given back exactly.
    setgid = 0o2775 if _may_set_setgid_on_a_folder(tmp_path / "setgid probe") else 0o775
    modes = {"a0755": 0o755, "b0750": 0o750, "c0705": 0o705, "d2775": setgid, "e0777": 0o777,
             os.path.join("e0777", "f0705"): 0o705}
    for name in modes:
        (legacy / name).mkdir()
        (legacy / name / "note.txt").write_text("kept")
    if refusal == "another account's file":
        (legacy / "a0755" / "theirs.json").write_text("{}")
        _another_account_owns(monkeypatch, legacy / "a0755" / "theirs.json")
    else:
        (legacy / "a0755" / "link").symlink_to("note.txt")
    for name, mode in sorted(modes.items(), key=lambda item: -len(item[0])):
        (legacy / name).chmod(mode)
    legacy.chmod(0o1777)
    found = {name: stat.S_IMODE(os.lstat(legacy / name).st_mode) for name in modes}
    assert found == modes, {k: oct(v) for k, v in found.items()}
    real_listdir, real_chmod = os.listdir, os.chmod
    narrowed = []
    monkeypatch.setattr(os, "listdir", lambda path=".": sorted(real_listdir(path)))
    monkeypatch.setattr(os, "chmod", lambda path, mode, *a, **k: narrowed.append(_key(path))
                        or real_chmod(path, mode, *a, **k))
    for _launch_again in range(2):
        narrowed.clear()
        with pytest.raises(OSError) as raised:
            user_data._make_user_data_dir(target)
        assert str(raised.value) == NOT_CARRIED and not os.path.lexists(target)
        assert {_key(legacy / name) for name in modes} <= set(narrowed), narrowed
        assert stat.S_IMODE(os.lstat(legacy).st_mode) == 0o1777
        after = {name: stat.S_IMODE(os.lstat(legacy / name).st_mode) for name in modes}
        assert after == modes, {k: oct(v) for k, v in after.items()}


def test_the_data_folders_state_names_every_reason_a_former_folder_gives():
    said = " ".join(user_data.data_folder_state.__doc__.split())
    for reason, refusal in [("FORMER_FOLDER_NOT_OURS", "FormerFolderRefused"),
                            ("FORMER_FOLDER_NOT_COPIED", "FormerFolderNotCopied"),
                            ("FORMER_FOLDER_NOT_CARRIED", "FormerFolderNotCarried"),
                            ("FORMER_FOLDER_UNREADABLE", "FormerFolderUnreadable"),
                            ("FORMER_FOLDER_BUSY", "FormerFolderBusy")]:
        assert f"('made', {reason}: {refusal})" in said, (reason, said)


@pytest.mark.parametrize("where", ["a folder in it", "the folder itself"])
def test_an_owner_only_folder_that_cannot_be_read_is_refused_for_that(monkeypatch, tmp_path, where):
    """Not as one open to other accounts: it never was. What it holds cannot
    be judged, so it stays where it is, its modes as they were."""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    shut = legacy / "sub" if where == "a folder in it" else legacy
    real_listdir = os.listdir

    def listdir(path="."):
        if _is(path, shut):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", listdir)
    (legacy / "sub").chmod(0o755)
    legacy.chmod(0o700)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(target)
    assert isinstance(raised.value, user_data.FormerFolderUnreadable), type(raised.value)
    assert str(raised.value) == UNREADABLE == user_data.FORMER_FOLDER_UNREADABLE
    assert not os.path.lexists(target) and _tree(legacy) == ORDINARY
    assert _mode(legacy) == 0o700 and _mode(legacy / "sub") == 0o755
    monkeypatch.setattr(user_data, "DATA_DIR", target)
    monkeypatch.setattr(user_data, "DATA_DIR_ERROR", UNREADABLE)
    assert user_data.data_folder_state() == ("made", UNREADABLE), "asked again, refused again"


def test_the_page_says_why_a_former_folder_that_cannot_be_read_is_not_taken_in(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    from conftest import APP_PATH
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "sub").chmod(0o300)               # its owner may enter it and write in it, not list it
    try:
        engine = _launch(monkeypatch, base)
        engine._harness_environment = None
        sync_engine_to_environment()
        at = AppTest.from_file(str(APP_PATH), default_timeout=300)
        at._page_hash = calc_hash("chart")
        at.run()
        assert not at.exception, at.exception
        said = [e.value for e in at.sidebar.warning if "their folder" in e.value]
    finally:
        (legacy / "sub").chmod(0o700)
    assert said == [f"Saved charts and preferences cannot be kept: their folder, `{target}`, could not be made "
                    "(the folder an older version kept them in, or a folder in it, cannot be read). Nothing can "
                    "be saved and no home can be set until it can."], said
    assert not os.path.lexists(target)


# =============================================================================
# One launch at a time over a former folder
# =============================================================================

def _held_elsewhere(folder):
    """Whether another descriptor holds the flock on `folder`."""
    import fcntl
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


def test_two_launches_at_once_carry_in_nothing_another_account_puts_in_the_gap(monkeypatch, tmp_path):
    """Launch A, its look held, refuses a wide folder holding this account's
    own link and gives its mode back; another account puts a link in it
    then. Launch B, started during A's look, waits for A's lock and then
    looks at the folder as A left it: open to others, and holding that
    account's link. Without the lock B read the mode A had narrowed, looked
    at the folder before the link was there, and moved it in."""
    import threading
    base, legacy, target = _base(tmp_path)
    _drop, victim = _outside(tmp_path)
    _ordinary_former_folder(legacy)
    (legacy / "own-link").symlink_to("saved_charts.json")
    legacy.chmod(0o777)
    theirs = legacy / "theirs.json"
    _another_account_owns(monkeypatch, theirs, link_only=True)
    monkeypatch.setattr(user_data, "_FORMER_FOLDER_LOCK_WAIT", 5.0, raising=False)
    a_held, b_looking, go_a, go_b = (threading.Event() for _ in range(4))
    real_listdir, real_give_back = os.listdir, user_data._give_back_its_mode

    def listdir(path="."):
        me = threading.current_thread().name
        if me == "A" and _is(path, legacy) and not a_held.is_set():
            a_held.set()
            go_a.wait(10)
        elif me == "B" and _is(path, legacy / "sub") and not b_looking.is_set():
            b_looking.set()
            go_b.wait(10)
        return real_listdir(path)

    def give_back(folder, mode):
        real_give_back(folder, mode)
        if threading.current_thread().name == "A" and _is(folder, legacy) and not os.path.lexists(theirs):
            theirs.symlink_to(victim)           # the other account, in the folder open again
    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(user_data, "_give_back_its_mode", give_back)
    raised = {}

    def launch():
        try:
            user_data._make_user_data_dir(target)
        except OSError as exc:
            raised[threading.current_thread().name] = str(exc)
    a = threading.Thread(target=launch, name="A")
    a.start()
    assert a_held.wait(10)
    b = threading.Thread(target=launch, name="B")
    b.start()
    b_looking.wait(1.0)                         # B in its look, or waiting for A's lock
    go_a.set()
    a.join(10)
    go_b.set()
    b.join(10)
    assert not a.is_alive() and not b.is_alive()
    assert not os.path.lexists(target), "the second launch carried the folder in"
    assert raised == {"A": NOT_CARRIED, "B": NOT_CARRIED}, raised
    assert os.readlink(theirs) == str(victim) and _mode(legacy) == 0o777
    assert _tree(tmp_path / "outside") == OUTSIDE


def test_a_lock_held_elsewhere_keeps_the_folder_where_it_is(monkeypatch, tmp_path):
    """Neither moved nor copied, nothing narrowed, no data folder, the
    reason given; a later look asks once, without waiting, and moves it once
    the lock is let go."""
    import fcntl
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    legacy.chmod(0o777)
    held = _tree(legacy)
    monkeypatch.setattr(user_data, "_FORMER_FOLDER_LOCK_WAIT", 0.2, raising=False)
    pauses = []
    real_sleep = user_data._clock.sleep
    monkeypatch.setattr(user_data._clock, "sleep", lambda t: pauses.append(t) or real_sleep(t))
    fd = os.open(legacy, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OSError) as raised:
            user_data._make_user_data_dir(target)
        assert pauses, "the launch did not wait for the lock"
        assert isinstance(raised.value, user_data.FormerFolderBusy) and str(raised.value) == BUSY
        assert user_data.FORMER_FOLDER_BUSY == BUSY
        assert not os.path.lexists(target) and _tree(legacy) == held and _mode(legacy) == 0o777
        monkeypatch.setattr(user_data, "DATA_DIR", target)
        monkeypatch.setattr(user_data, "DATA_DIR_ERROR", BUSY)

        def no_wait(_seconds):
            raise AssertionError("the look at the data folder waited for the lock")
        monkeypatch.setattr(user_data._clock, "sleep", no_wait)
        assert user_data.data_folder_state() == ("made", BUSY)
        assert not os.path.lexists(target) and _mode(legacy) == 0o777
    finally:
        os.close(fd)
    assert user_data.data_folder_state() == (None, None)
    assert _tree(target) == ORDINARY and not os.path.lexists(legacy)


@pytest.mark.parametrize("ending", ["moved", "copied", "refused", "raised"])
def test_the_lock_is_held_to_the_end_and_let_go_on_every_path(monkeypatch, tmp_path, ending):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    seen = []
    real_rename, real_copy, real_give_back = Path.rename, user_data._copy_through, user_data._give_back_its_mode

    def rename(self, there):
        if Path(self) == legacy:
            seen.append(_held_elsewhere(legacy))
            if ending != "moved":
                raise PermissionError(errno.EPERM, "the move was refused (the test's)", str(self))
        return real_rename(self, there)

    def copy(src, dst):
        if _is(src, legacy):
            seen.append(_held_elsewhere(legacy))
            if ending == "raised":
                raise OSError(errno.ENOSPC, "no space (the test's)")
        return real_copy(src, dst)

    def give_back(folder, mode):
        if _is(folder, legacy):
            seen.append(_held_elsewhere(legacy))
        return real_give_back(folder, mode)
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(user_data, "_copy_through", copy)
    monkeypatch.setattr(user_data, "_give_back_its_mode", give_back)
    if ending == "refused":
        (legacy / "own-link").symlink_to("saved_charts.json")
        legacy.chmod(0o777)
        with pytest.raises(user_data.FormerFolderNotCarried):
            user_data._make_user_data_dir(target)
    elif ending == "raised":
        with pytest.raises(user_data.FormerFolderNotCopied):
            user_data._make_user_data_dir(target)
    else:
        assert user_data._make_user_data_dir(target) == target
    assert seen and all(seen), f"the lock was not held throughout: {seen}"
    assert not _held_elsewhere(target if ending == "moved" else legacy), "the lock was kept"


@pytest.mark.parametrize("meanwhile", ["another folder put at the name", "moved in by the holder"])
def test_a_launch_that_waited_for_the_lock_asks_again(monkeypatch, tmp_path, meanwhile):
    """The lock had is on the folder the name led to when the wait began:
    one put at the name meanwhile is not the folder held, and is refused; a
    folder the holder moved in is the data folder, used as it stands."""
    import fcntl
    import threading
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    monkeypatch.setattr(user_data, "_FORMER_FOLDER_LOCK_WAIT", 5.0, raising=False)
    fd = os.open(legacy, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    waiting = threading.Event()
    real_sleep = user_data._clock.sleep
    monkeypatch.setattr(user_data._clock, "sleep", lambda t: waiting.set() or real_sleep(t))
    raised = []

    def launch():
        try:
            user_data._make_user_data_dir(target)
        except OSError as exc:
            raised.append(exc)
    launching = threading.Thread(target=launch)
    try:
        launching.start()
        assert waiting.wait(5), "the launch never waited for the lock"
        if meanwhile == "moved in by the holder":
            legacy.rename(target)
        else:
            legacy.rename(base / "held")
            _ordinary_former_folder(legacy)
    finally:
        os.close(fd)
    launching.join(10)
    assert not launching.is_alive()
    if meanwhile == "moved in by the holder":
        assert raised == [] and _tree(target) == ORDINARY and not os.path.lexists(legacy), raised
    else:
        assert [type(exc) for exc in raised] == [getattr(user_data, "FormerFolderBusy", None)], raised
        assert not os.path.lexists(target) and _tree(legacy) == ORDINARY


def test_a_filesystem_that_refuses_the_lock_moves_the_folder_as_before(monkeypatch, tmp_path):
    import fcntl
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    real_flock = fcntl.flock

    def flock(fd, op):
        if os.path.samestat(os.fstat(fd), os.stat(legacy)):
            raise OSError(errno.EOPNOTSUPP, "no locks here (the test's)")
        return real_flock(fd, op)
    monkeypatch.setattr(fcntl, "flock", flock)
    assert user_data._make_user_data_dir(target) == target
    assert _tree(target) == ORDINARY and not os.path.lexists(legacy)


# =============================================================================
# No data folder after a copy that failed, of any kind
# =============================================================================

def _copy_then(monkeypatch, legacy, after, before=None):
    """The copy, through the former folder's descriptor (_copy_through),
    and then `after()` once the copy of `legacy` is made; `before()` first,
    where given."""
    real_copy = user_data._copy_through

    def copy(src, dst):
        top = _is(src, legacy)
        if top and before is not None:
            before()
        made = real_copy(src, dst)
        if top:
            after()
        return made
    monkeypatch.setattr(user_data, "_copy_through", copy)


def _no_space():
    raise OSError(errno.ENOSPC, "no space left (the test's)")


def test_a_copy_that_raised_a_plain_error_makes_no_data_folder(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)

    real_mkdir = os.mkdir

    def mkdir(path, *args, **kwargs):
        """The copy's making of a folder in it raises, after any file it
        copied before."""
        if kwargs.get("dir_fd") is not None and os.fspath(path) == "sub":
            _no_space()
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(os, "mkdir", mkdir)
    _launch_without_a_data_folder(monkeypatch, base, legacy, target, user_data.FORMER_FOLDER_NOT_COPIED)
    assert _tree(legacy) == ORDINARY


@pytest.mark.parametrize("refusal", [PermissionError(errno.EACCES, "refused (the test's)"),
                                     FileExistsError(errno.EEXIST, "taken (the test's)")],
                         ids=["refused", "every name taken"])
def test_a_copy_whose_folder_cannot_be_made_makes_no_data_folder(monkeypatch, tmp_path, refusal):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)
    real_mkdir = os.mkdir

    def mkdir(path, *args, **kwargs):
        if os.fspath(path).endswith(".incoming"):
            raise refusal
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(os, "mkdir", mkdir)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]


def test_a_whole_copy_that_cannot_take_the_name_makes_no_data_folder(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)
    real_rename = os.rename

    def rename(src, dst, *args, **kwargs):
        if Path(dst) == target:
            raise PermissionError(errno.EPERM, "refused (the test's)", str(dst))
        return real_rename(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]


def test_a_link_at_the_former_name_that_cannot_be_made_makes_no_data_folder(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _ordinary_former_folder(real)
    legacy.symlink_to(real)
    _refuse_the_move(monkeypatch, legacy)
    real_symlink = os.symlink

    def symlink(src, dst, *args, **kwargs):
        if Path(dst) == target:
            raise PermissionError(errno.EPERM, "no links here (the test's)", str(dst))
        return real_symlink(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "symlink", symlink)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [LEGACY] and legacy.is_symlink()
    monkeypatch.setattr(os, "symlink", real_symlink)            # the next launch: the link can be made
    assert user_data._make_user_data_dir(target) == target and os.readlink(target) == str(real)


@pytest.mark.parametrize("added", ["a file", "a folder"])
def test_a_file_added_during_a_copy_that_raised_nothing_is_caught(monkeypatch, tmp_path, added):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)
    real_copy = user_data._copy_through

    def add():
        if added == "a file":
            (legacy / "sub" / "late.json").write_text("{}")
        else:
            (legacy / "later").mkdir()
    _copy_then(monkeypatch, legacy, add)
    with pytest.raises(user_data.FormerFolderNotCopied):
        user_data._make_user_data_dir(target)
    assert sorted(p.name for p in base.iterdir()) == [LEGACY]
    monkeypatch.setattr(user_data, "_copy_through", real_copy)     # the next launch: nothing added during its copy
    assert user_data._make_user_data_dir(target) == target, "the next launch's copy, whole, is published"
    assert _tree(target) == _tree(legacy)


@pytest.mark.parametrize("failure", ["a plain error", "a copy not whole"])
def test_another_launchs_data_folder_standing_is_left_as_it_is(monkeypatch, tmp_path, failure):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    _refuse_the_move(monkeypatch, legacy)
    held = dict(ORDINARY)

    def another_launch():
        target.mkdir(mode=0o700)
        (target / "saved_charts.json").write_text(json.dumps({"New": REC}))
        if failure == "a plain error":
            _no_space()
        (legacy / "sub" / "late.json").write_text("{}")
        held["sub/late.json"] = ("file", b"{}")
    _copy_then(monkeypatch, legacy, another_launch)
    assert user_data._make_user_data_dir(target) == target
    assert _tree(target) == {"saved_charts.json": ("file", json.dumps({"New": REC}).encode())}
    assert sorted(p.name for p in base.iterdir()) == sorted([LEGACY, "Zij"]), "the copy was left"
    assert _tree(legacy) == held


# =============================================================================
# The honest case still arrives whole
# =============================================================================

@pytest.mark.parametrize("move", ["moved", "copied"])
def test_this_accounts_ordinary_former_folder_arrives_whole(monkeypatch, tmp_path, move):
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    held = _tree(legacy)
    if move == "copied":
        _refuse_the_move(monkeypatch, legacy)
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and engine.data_folder_state() == (None, None)
    assert _tree(target) == held
    assert os.path.lexists(legacy) == (move == "copied")
    assert engine.load_saved_charts() == {"Old": REC}
    assert engine.load_preferences().get("last_chart") == "Old"
    assert _save(engine, "Mine") is True and _save(engine, "Yours") is True
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == {"Old": REC, "Mine": REC, "Yours": REC}
    assert len(user_data._versions(target, "saved_charts.json")) == 2, "a version was not kept on each save"
    assert engine.remember_preference("_launches", 4) is True
    assert json.loads(engine.PREFERENCES_PATH.read_text())["_launches"] == 4


def _as_windows(monkeypatch):
    """Windows stood in: no getuid, and the data layer's eight security calls
    answered as for the user's own folders, one seam per call -- the owner
    of what stands at a name (_windows_owner), of what was opened
    (_windows_owner_of_the_open) and this account
    (_windows_this_account), all the user's SID; no list wider than the
    user's (_windows_list_is_wider), nor any file's that lets another account
    change it (_windows_file_is_writable_by_others), nor any folder's on the
    way to the data folder (_windows_folder_is_open_to_others); the
    protected list set (_windows_close_the_list) doing nothing; the folder
    held by a descriptor of it (_windows_hold_the_folder). No test reaches
    ctypes."""
    sid = "S-1-5-21-1000000001-1000000002-1000000003-1001"
    monkeypatch.delattr(os, "getuid")
    monkeypatch.setattr(user_data, "_windows_owner", lambda path, follow_links=True: (
        (os.stat if follow_links else os.lstat)(path) and sid))
    monkeypatch.setattr(user_data, "_windows_owner_of_the_open", lambda fd: sid)
    monkeypatch.setattr(user_data, "_windows_this_account", lambda: sid)
    monkeypatch.setattr(user_data, "_windows_list_is_wider", lambda path, follow_links=False: False)
    monkeypatch.setattr(user_data, "_windows_close_the_list", lambda path: None)
    monkeypatch.setattr(user_data, "_windows_file_is_writable_by_others", lambda path, follow_links=False: False)
    monkeypatch.setattr(user_data, "_windows_folder_is_open_to_others", lambda path: False, raising=False)
    monkeypatch.setattr(user_data, "_windows_hold_the_folder", lambda path: os.open(path, os.O_RDONLY), raising=False)


@pytest.mark.parametrize("move", ["moved", "copied"])
def test_a_windows_launch_of_the_users_own_former_folder_is_unchanged(monkeypatch, tmp_path, move):
    """Windows-shaped: no getuid, the owners read through the security
    calls (stood in: the user's own); the former folder arrives as before.
    (The engine's own import asks for getuid elsewhere, so the folder is
    made by the launch's own function with getuid gone, and the engine
    loaded after.)"""
    base, legacy, target = _base(tmp_path)
    _ordinary_former_folder(legacy)
    held = _tree(legacy)
    if move == "copied":
        _refuse_the_move(monkeypatch, legacy)
    real_getuid = os.getuid
    _as_windows(monkeypatch)
    assert user_data._make_user_data_dir(target) == target
    monkeypatch.setattr(os, "getuid", real_getuid, raising=False)
    assert _tree(target) == held
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None
    assert engine.load_saved_charts() == {"Old": REC}
    assert _save(engine, "Mine") is True


def test_the_old_store_reader_on_windows_is_unchanged_for_the_users_own_folders(monkeypatch, tmp_path):
    engine, legacy, target = _a_data_folder_with_no_store(monkeypatch, tmp_path)
    _ordinary_former_folder(legacy)
    _as_windows(monkeypatch)
    assert engine._the_first_old_store() == (legacy / "saved_charts.json", {"Old": REC}, False)


# =============================================================================
# The kept versions are ignored by Git
# =============================================================================

def test_git_ignores_the_kept_versions_and_their_temporary_files(tmp_path):
    """Git's own reading of the checkout's ignore list (nothing staged or
    written): a version and a version's temporary file, as the store's
    writer names them, are ignored wherever the data folder sits."""
    import subprocess
    from conftest import EXECUTABLE_DIR
    repo = tmp_path / "checkout"
    repo.mkdir()
    shutil.copy2(EXECUTABLE_DIR / ".gitignore", repo / ".gitignore")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
    stamp, hexes = "20000101-000000", "0123456789abcdef"
    for name in (f"saved_charts.json.previous-{stamp}-001", f"saved_charts.json.previous-{stamp}-1000",
                 f"saved_charts.json.previous.{hexes}.tmp", f"some/folder/saved_charts.json.previous-{stamp}-002"):
        done = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", "-q", name],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, (name, done.returncode, done.stderr)
    for name in ("saved_charts.json.previous", f"saved_charts.json.previous.{hexes}x.tmp", "notes.json"):
        done = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", "-q", name],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 1, (name, done.returncode, done.stderr)
    assert user_data._VERSION_FORM.fullmatch(f".previous-{stamp}-001")
