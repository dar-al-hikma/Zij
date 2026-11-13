"""The former folder's move is bound to the one folder the launch opens.

Where another account owns the folder above the data folder (a sticky
folder of its own: it may rename or replace anything in it), it can put a
folder of its own at the former name at any moment. The launch identifies
what stands there once (device and inode, a link not followed), opens it
without following a link, reads its owner from what it opened, locks it,
looks at it, and copies it through that descriptor; the name is looked at
again before the move, after a refused move and before a copy is
published. Another account's folder at any step ends the move with no data
folder and the reason the page gives; another folder of this account's
there ends it as busy.

Each test works under its own tmp_path. The other account is stood in
inside the test: what it owns is known by device and inode, and os.stat,
os.lstat and os.fstat report it as that account's (_Theirs); the sticky
folder's refusal to move another account's folder is a Path.rename that
raises EPERM for it (_sticky). The swap is made by a hook on the call the
code makes at each point, with the hook the code before this change made
there too, so that each swap lands on both.
"""
import errno
import json
import os
import shutil
from pathlib import Path

import fcntl
import pytest

import user_data
from conftest import sync_engine_to_environment

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
INJECTED = dict(REC, location_query="Elsewhere")
LEGACY = "TraditionalAstrologyEngine"
NOT_OURS = "the folder an older version kept them in belongs to another account"
BUSY = "the folder an older version kept them in is in use elsewhere"
_RENAME = os.rename                 # the real one, for the swaps


def _base(tmp_path):
    base = tmp_path / "xdg"
    base.mkdir()
    return base, base / LEGACY, base / "Zij"


def _ordinary(folder, chart="Old", record=REC):
    folder.mkdir(parents=True)
    (folder / "saved_charts.json").write_text(json.dumps({chart: record}, indent=2))
    (folder / "preferences.json").write_text(json.dumps({"last_chart": chart}))
    (folder / "sub").mkdir()
    (folder / "sub" / "note.txt").write_text(chart)


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
            else:
                found[rel] = ("file", path.read_bytes())
    return found


def _key(path):
    """The device and inode of what `path` -- a name (a link followed) or a
    descriptor -- is now; None where nothing is there."""
    try:
        seen = os.fstat(path) if isinstance(path, int) else os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return seen.st_dev, seen.st_ino


def _is(path, folder):
    return _key(folder) is not None and _key(path) == _key(folder)


class _OwnedByAnother:
    """A stat result whose owner is another account's id."""

    def __init__(self, seen):
        self._seen = seen
        self.st_uid = seen.st_uid + 1

    def __getattr__(self, name):
        return getattr(self._seen, name)


class _Theirs:
    """The other account: everything it owns, by device and inode, which
    os.stat, os.lstat and os.fstat report as its own; and every look the
    data layer takes inside one of its folders (a listing, or an entry
    opened)."""

    def __init__(self, monkeypatch):
        self.keys, self.entries, self.reads = set(), set(), []
        real = {name: getattr(os, name) for name in ("stat", "lstat", "fstat")}
        self._lstat = real["lstat"]

        def judged(look):
            def call(*args, **kwargs):
                seen = look(*args, **kwargs)
                return _OwnedByAnother(seen) if (seen.st_dev, seen.st_ino) in self.keys else seen
            return call
        for name, look in real.items():
            monkeypatch.setattr(os, name, judged(look))
        real_listdir, real_scandir, real_open = os.listdir, os.scandir, os.open

        def listdir(path="."):
            if (isinstance(path, int) or path != ".") and _key(path) in self.keys:
                self.reads.append(("list", path))
            return real_listdir(path)

        def scandir(path="."):
            if (isinstance(path, int) or path != ".") and _key(path) in self.keys:
                self.reads.append(("list", path))
            return real_scandir(path)

        def open_(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if _key(fd) in self.entries:
                self.reads.append(("open", path))
            return fd
        monkeypatch.setattr(os, "listdir", listdir)
        monkeypatch.setattr(os, "scandir", scandir)
        monkeypatch.setattr(os, "open", open_)

    def own(self, top):
        """`top` and everything in it, theirs from now on."""
        inside = [os.path.join(root, name) for root, dirs, files in os.walk(top) for name in dirs + files]
        seen = self._lstat(top)
        self.keys.add((seen.st_dev, seen.st_ino))
        for path in inside:
            seen = self._lstat(path)
            self.keys.add((seen.st_dev, seen.st_ino))
            self.entries.add((seen.st_dev, seen.st_ino))
        return top


def _sticky(monkeypatch, theirs, legacy, refuse_ours=False):
    """The sticky folder above: a move of another account's folder at the
    former name is refused (EPERM); this account's own is moved, unless
    `refuse_ours` (a move refused for some other reason)."""
    real = Path.rename

    def rename(self, target):
        if Path(self) == legacy:
            seen = theirs._lstat(legacy)
            if (seen.st_dev, seen.st_ino) in theirs.keys or refuse_ours:
                raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(self))
        return real(self, target)
    monkeypatch.setattr(Path, "rename", rename)


def _hook(monkeypatch, owner, name, before=None, after=None, when=lambda *a, **k: True):
    """Wrap `owner.name` (where it exists: the code before this change had
    other calls at some points): `before()` ahead of its first call that
    `when` accepts, `after()` behind it."""
    real = getattr(owner, name, None)
    if real is None:
        return
    done = []

    def call(*args, **kwargs):
        first = not done and when(*args, **kwargs)
        if first:
            done.append(True)
            if before:
                before()
        result = real(*args, **kwargs)
        if first and after:
            after()
        return result
    monkeypatch.setattr(owner, name, call)


class _Scene:
    """The user's former folder at the former name; a folder ready to be
    put there in its place (another account's, holding a store a parser
    accepts, or another of this account's); and the place the user's folder
    is moved aside to by the swap."""

    def __init__(self, monkeypatch, tmp_path, whose):
        self.base, self.legacy, self.target = _base(tmp_path)
        _ordinary(self.legacy)
        self.held = _tree(self.legacy)
        self.aside = tmp_path / "xdg" / "aside"
        self.other = tmp_path / "xdg" / "prepared"
        _ordinary(self.other, "Injected", INJECTED)
        self.other_held = _tree(self.other)
        self.other_key = _key(self.other)
        self.theirs = _Theirs(monkeypatch)
        if whose == "another account's":
            self.theirs.own(self.other)
        self.whose = whose
        self.swapped = False
        self.copied = []                        # each file the copy made
        real_copy = getattr(user_data, "_copy_a_file", None)
        if real_copy is not None:
            monkeypatch.setattr(user_data, "_copy_a_file", lambda *args: self.copied.append(args[2]) or real_copy(*args))

    def watch(self, monkeypatch):
        """Every step the launch takes, outermost (after the hooks): each
        folder it locks, each look at the entries, each move of the former
        name it tries."""
        self.locked, self.looked, self.moves = [], [], []
        real_flock, real_look, real_rename = fcntl.flock, user_data._only_this_accounts_entries, Path.rename

        def flock(fd, *args):
            self.locked.append(_key(fd))
            return real_flock(fd, *args)

        def look(*args):
            self.looked.append(True)
            return real_look(*args)

        def rename(path, target):
            if Path(path) == self.legacy:
                self.moves.append(True)
            return real_rename(path, target)
        monkeypatch.setattr(fcntl, "flock", flock)
        monkeypatch.setattr(user_data, "_only_this_accounts_entries", look)
        monkeypatch.setattr(Path, "rename", rename)

    def stopped_at(self, point):
        """The launch went no further than `point` allows: the folder put at
        the name never locked; the entries looked at only once the lock
        was had and the name looked at again; a move tried only where the
        swap came after the look before it; a copy begun only where the
        swap came during or after it."""
        assert self.other_key not in self.locked, "the folder put at the name was locked"
        assert bool(self.looked) == (point not in NOT_LOOKED), self.looked
        assert bool(self.moves) == (point in MOVED), self.moves
        assert bool(self.copied) == (point in COPYING), self.copied

    def swap(self):
        """The user's folder moved aside, the prepared one put at the name."""
        _RENAME(self.legacy, self.aside)
        _RENAME(self.other, self.legacy)
        self.swapped = True

    def ended(self, raised):
        """The move ended: the reason, no data folder, nothing of the other
        folder read, both folders whole where they now stand."""
        assert self.swapped, "the premise: the swap was made"
        if self.whose == "another account's":
            assert isinstance(raised, user_data.FormerFolderRefused), type(raised)
            assert str(raised) == f"[Errno {errno.EPERM}] {NOT_OURS}: '{self.legacy}'", str(raised)
            assert raised.strerror == NOT_OURS == user_data.FORMER_FOLDER_NOT_OURS
        else:
            assert isinstance(raised, user_data.FormerFolderBusy), type(raised)
            assert str(raised) == BUSY == user_data.FORMER_FOLDER_BUSY
        assert not os.path.lexists(self.target), "a data folder was made"
        assert sorted(p.name for p in self.base.iterdir()) == sorted([LEGACY, "aside"]), "a copy was left"
        assert self.theirs.reads == [], f"the other account's folder was read: {self.theirs.reads}"
        assert _tree(self.aside) == self.held, "the user's former folder is not whole"
        assert _tree(self.legacy) == self.other_held, "the folder put at the name was changed"


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
    try:
        with engine.saved_charts_lock():
            charts = dict(engine.saved_charts_as_they_stand().charts or {})
            charts[name] = REC
            return engine.write_saved_charts(charts)
    except engine.DataLockBusy:
        return False


def _and_after(monkeypatch, scene):
    """A launch after the refusal, the other account's folder still at the
    name: no data folder; a chart read, a save and a preference write land
    nowhere; the page's reason; both folders as they were."""
    scene.theirs.reads.clear()                  # the test's own looks at the folders, before
    engine = _launch(monkeypatch, scene.base)
    assert user_data.DATA_DIR_ERROR == NOT_OURS
    assert engine.load_saved_charts() == {}
    assert _save(engine, "Mine") is False
    assert engine.remember_preference("_launches", 4) is False
    assert engine.data_folder_state() == ("made", NOT_OURS)
    assert not os.path.lexists(scene.target)
    assert scene.theirs.reads == [], scene.theirs.reads
    assert _tree(scene.aside) == scene.held and _tree(scene.legacy) == scene.other_held


# =============================================================================
# The swap at each point
# =============================================================================

def _at(point, monkeypatch, scene):
    """Set the hook that makes the swap at `point`; the move refused where
    the point lies on the copy's path."""
    legacy, swap = scene.legacy, scene.swap
    refuse_ours = point in ("(e) after a refused move", "(f) during the copy", "(g) before publication")
    if point == "(b) between the first look and the open":
        _hook(monkeypatch, os, "open", before=swap, when=lambda path, *a, **k: path == legacy or path == str(legacy))
    elif point == "(c) once the lock is had":
        _hook(monkeypatch, fcntl, "flock", after=swap, when=lambda fd, *a, **k: _is(fd, legacy))
    elif point == "(c) before the entries' look":
        _hook(monkeypatch, user_data, "_only_this_accounts_entries", before=swap)
    elif point == "(d) after the entries' look":
        _hook(monkeypatch, user_data, "_only_this_accounts_entries", after=swap)
    elif point == "(d) at the move itself":
        _sticky(monkeypatch, scene.theirs, legacy)      # beneath the hook: the sticky folder refuses theirs
        _hook(monkeypatch, Path, "rename", before=swap, when=lambda self, *a: Path(self) == legacy)
        return
    elif point == "(e) after a refused move":
        real = Path.rename

        def rename(self, target):
            if Path(self) == legacy:
                swap()
                raise PermissionError(errno.EPERM, "the move was refused (the test's)", str(self))
            return real(self, target)
        monkeypatch.setattr(Path, "rename", rename)
        return
    elif point == "(f) during the copy":
        _hook(monkeypatch, user_data, "_copy_a_file", after=swap)
        _hook(monkeypatch, shutil, "copyfile", after=swap)
    elif point == "(g) before publication":
        _hook(monkeypatch, user_data, "_copy_is_whole_through", after=swap)
        _hook(monkeypatch, user_data, "_copy_is_whole", after=swap)
    _sticky(monkeypatch, scene.theirs, legacy, refuse_ours=refuse_ours)


# Where the swap lands before the look at the entries (which then never
# runs), at or after the move (which is then tried), and once a copy has
# begun: the name no longer leading to the folder first found ends the move
# at the next step, before anything further is done.
NOT_LOOKED = {"(b) between the first look and the open", "(c) once the lock is had"}
MOVED = {"(d) at the move itself", "(e) after a refused move", "(f) during the copy", "(g) before publication"}
COPYING = {"(f) during the copy", "(g) before publication"}
POINTS = ["(b) between the first look and the open", "(c) once the lock is had", "(c) before the entries' look",
          "(d) after the entries' look", "(d) at the move itself", "(e) after a refused move",
          "(f) during the copy", "(g) before publication"]


@pytest.mark.parametrize("point", POINTS)
def test_another_accounts_folder_put_at_the_name_ends_the_move(monkeypatch, tmp_path, point):
    scene = _Scene(monkeypatch, tmp_path, "another account's")
    _at(point, monkeypatch, scene)
    scene.watch(monkeypatch)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(scene.target)
    scene.ended(raised.value)
    scene.stopped_at(point)
    monkeypatch.undo()                          # the hooks gone; the other account's folder stays at the name
    scene.theirs = _Theirs(monkeypatch)
    scene.theirs.own(scene.legacy)
    _and_after(monkeypatch, scene)


@pytest.mark.parametrize("point", [p for p in POINTS if p != "(d) at the move itself"])
def test_another_folder_of_this_accounts_put_at_the_name_ends_the_move(monkeypatch, tmp_path, point):
    scene = _Scene(monkeypatch, tmp_path, "this account's")
    _at(point, monkeypatch, scene)
    scene.watch(monkeypatch)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(scene.target)
    scene.ended(raised.value)
    scene.stopped_at(point)


def test_a_folder_of_this_accounts_the_move_itself_carried_is_not_used(monkeypatch, tmp_path):
    """The rename carried the folder put there between the last look and
    the move: this launch ends, using nothing of it; it stands at the data
    folder's name, where the next look judges it as the data folder."""
    scene = _Scene(monkeypatch, tmp_path, "this account's")
    _at("(d) at the move itself", monkeypatch, scene)
    with pytest.raises(user_data.FormerFolderBusy):
        user_data._make_user_data_dir(scene.target)
    assert _tree(scene.target) == scene.other_held and _tree(scene.aside) == scene.held
    assert sorted(p.name for p in scene.base.iterdir()) == sorted(["Zij", "aside"])


def test_another_accounts_folder_at_the_name_before_the_first_look_is_refused(monkeypatch, tmp_path):
    scene = _Scene(monkeypatch, tmp_path, "another account's")
    scene.swap()
    _sticky(monkeypatch, scene.theirs, scene.legacy)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(scene.target)
    scene.ended(raised.value)
    _and_after(monkeypatch, scene)


def test_the_copy_reads_the_folder_opened_and_never_the_one_put_at_the_name(monkeypatch, tmp_path):
    """The swap during the copy: every file the copy read is the user's (by
    device and inode), none of the folder put there; the copy is removed."""
    scene = _Scene(monkeypatch, tmp_path, "another account's")
    _at("(f) during the copy", monkeypatch, scene)
    real_open, opened = os.open, []

    def open_(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and not flags & (os.O_WRONLY | os.O_RDWR):
            opened.append(_key(fd))
        return fd
    monkeypatch.setattr(os, "open", open_)
    users = {_key(Path(root) / name) for root, dirs, files in os.walk(scene.legacy) for name in dirs + files}
    with pytest.raises(user_data.FormerFolderRefused) as raised:
        user_data._make_user_data_dir(scene.target)
    scene.ended(raised.value)
    assert set(opened) & users, "the premise: the copy read the user's files"
    assert not set(opened) & scene.theirs.keys, "the copy read the folder put at the name"


# =============================================================================
# A link of this account's at the former name
# =============================================================================

@pytest.mark.parametrize("move", ["moved", "copied"])
def test_a_link_of_this_accounts_at_the_former_name_is_carried_as_a_link(monkeypatch, tmp_path, move):
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _ordinary(real)
    legacy.symlink_to(real)
    theirs = _Theirs(monkeypatch)
    _sticky(monkeypatch, theirs, legacy, refuse_ours=(move == "copied"))
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None
    assert target.is_symlink() and os.readlink(target) == str(real)
    assert legacy.is_symlink() == (move == "copied")
    assert engine.load_saved_charts() == {"Old": REC}


@pytest.mark.parametrize("whose", ["another account's", "this account's"])
@pytest.mark.parametrize("point", ["(c) once the lock is had", "(d) after the entries' look",
                                   "(e) after a refused move"])
def test_a_link_at_the_former_name_swapped_for_a_folder_ends_the_move(monkeypatch, tmp_path, point, whose):
    scene = _Scene(monkeypatch, tmp_path, whose)
    real = tmp_path / "real"
    _RENAME(scene.legacy, real)
    scene.legacy.symlink_to(real)
    scene.held = _tree(scene.legacy)            # the link, as the swap moves it aside
    _at(point, monkeypatch, scene)
    with pytest.raises(OSError) as raised:
        user_data._make_user_data_dir(scene.target)
    scene.ended(raised.value)
    assert scene.aside.is_symlink() and os.readlink(scene.aside) == str(real)


@pytest.mark.parametrize("point", ["(c) before the entries' look", "(d) after the entries' look"])
def test_the_folder_swapped_for_a_link_of_this_accounts_ends_the_move(monkeypatch, tmp_path, point):
    """A link of the account's own, leading to the user's folder itself:
    another object at the name than the folder identified."""
    scene = _Scene(monkeypatch, tmp_path, "this account's")
    shutil.rmtree(scene.other)
    scene.other.symlink_to(scene.aside)
    _at(point, monkeypatch, scene)
    with pytest.raises(user_data.FormerFolderBusy):
        user_data._make_user_data_dir(scene.target)
    assert not os.path.lexists(scene.target)
    assert scene.legacy.is_symlink() and _tree(scene.aside) == scene.held


# =============================================================================
# The honest cases, and Windows
# =============================================================================

@pytest.mark.parametrize("move", ["moved", "moved after its narrowing", "copied after a refused move"])
def test_this_accounts_former_folder_arrives_whole(monkeypatch, tmp_path, move):
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    if move == "moved after its narrowing":
        legacy.chmod(0o777)
        (legacy / "sub").chmod(0o777)
    theirs = _Theirs(monkeypatch)
    _sticky(monkeypatch, theirs, legacy, refuse_ours=move.startswith("copied"))
    engine = _launch(monkeypatch, base)
    assert user_data.DATA_DIR_ERROR is None and engine.data_folder_state() == (None, None)
    assert _tree(target) == held
    assert os.path.lexists(legacy) == move.startswith("copied")
    assert os.stat(target).st_mode & 0o777 == 0o700
    assert os.stat(target / "sub").st_mode & 0o777 == 0o700, "a folder in it was not narrowed by the look"
    assert sorted(p.name for p in base.iterdir()) == sorted({LEGACY, "Zij"} if move.startswith("copied") else {"Zij"})
    assert engine.load_saved_charts() == {"Old": REC}
    assert engine.load_preferences().get("last_chart") == "Old"
    assert _save(engine, "Mine") is True and _save(engine, "Yours") is True
    assert json.loads(engine.SAVED_CHARTS_PATH.read_text()) == {"Old": REC, "Mine": REC, "Yours": REC}
    assert len(user_data._versions(target, "saved_charts.json")) == 2, "a version was not kept on each save"
    assert engine.remember_preference("_launches", 4) is True


@pytest.mark.parametrize("move", ["moved", "copied"])
def test_a_windows_launch_moves_and_copies_the_users_own_former_folder_by_name(monkeypatch, tmp_path, move):
    """Windows-shaped: no getuid, the owners read through the security
    calls, one seam per call (stood in: the user's own folders, no list
    wider). No descriptor is opened, no lock taken: the folder is judged,
    narrowed and moved, or copied by name."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    if move == "copied":
        real = Path.rename
        monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
            PermissionError(errno.EPERM, "refused (the test's)")) if Path(self) == legacy else real(self, to))
    sid = "S-1-5-21-1000000001-1000000002-1000000003-1001"
    monkeypatch.delattr(os, "getuid")
    monkeypatch.setattr(user_data, "_windows_owner", lambda path, follow_links=True: (
        (os.stat if follow_links else os.lstat)(path) and sid))
    monkeypatch.setattr(user_data, "_windows_this_account", lambda: sid)
    monkeypatch.setattr(user_data, "_windows_list_is_wider", lambda path, follow_links=False: False)
    monkeypatch.setattr(user_data, "_windows_close_the_list", lambda path: None)
    monkeypatch.setattr(user_data, "_windows_file_is_writable_by_others", lambda path, follow_links=False: False)
    monkeypatch.setattr(user_data, "_windows_folder_is_open_to_others", lambda path: False, raising=False)
    monkeypatch.setattr(user_data, "_windows_hold_the_folder", lambda path: os.open(path, os.O_RDONLY), raising=False)

    def bound(*args, **kwargs):
        raise AssertionError("the bound move ran where there are no owners")
    monkeypatch.setattr(user_data, "_move_the_former_folder", bound, raising=False)
    assert user_data._make_user_data_dir(target) == target
    assert _tree(target) == held and os.path.lexists(legacy) == (move == "copied")
    assert sorted(p.name for p in target.parent.iterdir()) == sorted({LEGACY, "Zij"} if move == "copied" else {"Zij"})


# =============================================================================
# A copy a killed launch left, once its source has become the data folder
# =============================================================================

def _left_copy(target, record):
    """A copy's own folder as a launch killed while copying leaves it: the
    record `record` (bytes; None for none) and a copy part made."""
    holder = target.with_name(f".{target.name}.0123456789abcdef.incoming")
    holder.mkdir(mode=0o700)
    if record is not None:
        (holder / "source").write_bytes(record)
    (holder / "copy").mkdir(mode=0o700)
    (holder / "copy" / "saved_charts.json").write_text(json.dumps({"Old": REC}, indent=2))
    return holder


def _record_of(path):
    seen = os.lstat(path)
    return f"{seen.st_dev} {seen.st_ino}\n".encode("ascii")


def _moved_in(base, legacy, target):
    """The former folder, its record taken, moved to the data folder by
    another launch."""
    _ordinary(legacy)
    record = _record_of(legacy)
    _RENAME(legacy, target)
    return record


def test_a_dead_copy_whose_source_became_the_data_folder_is_removed(tmp_path):
    base, legacy, target = _base(tmp_path)
    holder = _left_copy(target, _moved_in(base, legacy, target))
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(holder), "the dead copy was kept"
    assert sorted(p.name for p in base.iterdir()) == ["Zij"]
    assert json.loads((target / "saved_charts.json").read_text()) == {"Old": REC}


def test_a_dead_copy_whose_source_is_not_the_data_folder_is_kept(tmp_path):
    """The former name gone, but the data folder is not the folder the copy
    was made from (removed by hand, say, and a new one made): kept."""
    base, legacy, target = _base(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target.mkdir(mode=0o700)
    holder = _left_copy(target, _record_of(elsewhere))
    user_data._remove_dead_copies(target, legacy)
    assert json.loads((holder / "copy" / "saved_charts.json").read_text()) == {"Old": REC}


def test_a_copy_still_held_is_kept(tmp_path):
    base, legacy, target = _base(tmp_path)
    holder = _left_copy(target, _moved_in(base, legacy, target))
    fd = os.open(holder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        user_data._remove_dead_copies(target, legacy)
        assert json.loads((holder / "copy" / "saved_charts.json").read_text()) == {"Old": REC}
    finally:
        os.close(fd)


@pytest.mark.parametrize("record", ["none", "not one line", "a link to a true one", "another account's",
                                    "a folder"])
def test_a_record_that_cannot_be_read_keeps_the_copy(monkeypatch, tmp_path, record):
    base, legacy, target = _base(tmp_path)
    true = _moved_in(base, legacy, target)
    holder = _left_copy(target, None if record in ("none", "a link to a true one", "a folder") else
                        true.rstrip(b"\n") if record == "not one line" else true)
    if record == "a link to a true one":
        (tmp_path / "true").write_bytes(true)
        (holder / "source").symlink_to(tmp_path / "true")
    elif record == "a folder":
        (holder / "source").mkdir()
    elif record == "another account's":
        _Theirs(monkeypatch).own(holder / "source")
    user_data._remove_dead_copies(target, legacy)
    assert json.loads((holder / "copy" / "saved_charts.json").read_text()) == {"Old": REC}


def test_a_dead_copy_in_a_folder_that_is_not_as_made_is_kept(tmp_path):
    """Open to others, or holding anything but the copy and its record: not
    a folder the copy made, whatever its record says."""
    base, legacy, target = _base(tmp_path)
    holder = _left_copy(target, _moved_in(base, legacy, target))
    (holder / "more.txt").write_text("not the copy's")
    user_data._remove_dead_copies(target, legacy)
    assert (holder / "more.txt").exists()
    (holder / "more.txt").unlink()
    holder.chmod(0o755)
    user_data._remove_dead_copies(target, legacy)
    assert (holder / "copy" / "saved_charts.json").exists()


CHILD = r"""
import errno, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import user_data
legacy, target = Path(sys.argv[2]), Path(sys.argv[3])
real_rename, real_copy = Path.rename, user_data._copy_a_file

def rename(self, to):
    if Path(self) == legacy:
        raise PermissionError(errno.EPERM, "the move was refused (the test's)", str(self))
    return real_rename(self, to)

def copy(*args):
    real_copy(*args)
    print("copying", flush=True)
    time.sleep(120)
Path.rename, user_data._copy_a_file = rename, copy
user_data._make_user_data_dir(target)
"""


def test_a_launch_killed_while_another_moved_the_folder_leaves_no_copy_for_good(monkeypatch, tmp_path):
    """Launch A, its move refused, is copying; launch B's cleanup finds A's
    copy held and passes it over, then waits for the former folder's lock.
    A is killed; B moves the folder in. A's copy is dead and the former
    name gone; the next launch removes it, by its record."""
    import subprocess
    import sys
    import threading
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path / "child-xdg"))
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(Path(user_data.__file__).parent), str(legacy),
                              str(target)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "copying", child.stderr.read()[-2000:]
        waiting, raised = threading.Event(), []
        real_lock = user_data._lock_the_former_folder

        def lock(*args):
            waiting.set()
            return real_lock(*args)
        monkeypatch.setattr(user_data, "_lock_the_former_folder", lock)

        def launch():
            try:
                user_data._make_user_data_dir(target, lock_wait=60)
            except BaseException as exc:
                raised.append(exc)
        b = threading.Thread(target=launch)
        b.start()
        assert waiting.wait(30), "the premise: launch B reached the former folder's lock"
    finally:
        child.kill()
        child.wait()
    b.join(60)
    assert not b.is_alive() and raised == [], raised
    left = [p.name for p in base.iterdir() if p.name.endswith(".incoming")]
    assert len(left) == 1 and not os.path.lexists(legacy), f"the premise: A's copy left, moved in: {left}"
    assert _tree(target) == held
    assert user_data._make_user_data_dir(target) == target
    assert sorted(p.name for p in base.iterdir()) == ["Zij"], "the dead copy was kept"


@pytest.mark.parametrize("form", ["copying", "incoming"])
def test_a_folder_given_a_dead_copys_name_after_its_judgement_is_not_removed(monkeypatch, tmp_path, form):
    """The account owning the folder above renames a folder of the reader's
    (holding a store) to a dead copy's name between the judgement and the
    removal: the copy is judged and removed through the descriptor that
    holds it, and that folder is left whole."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    staging = base / f".Zij.0123456789abcdef.{form}"
    staging.mkdir(mode=0o700)
    inside = staging if form == "copying" else staging / "copy"
    inside.mkdir(mode=0o700, exist_ok=True)
    (inside / "saved_charts.json").write_bytes((legacy / "saved_charts.json").read_bytes())
    mine = base / "mine"
    _ordinary(mine, "Mine")
    held = _tree(mine)
    aside = tmp_path / "aside"

    def swap():
        _RENAME(staging, aside)
        _RENAME(mine, staging)
    for name in ("_only_a_copy", "_only_a_copy_through"):
        _hook(monkeypatch, user_data, name, after=swap)
    user_data._remove_dead_copies(target, legacy)
    assert os.path.lexists(aside), "the premise: the swap was made"
    assert _tree(staging) == held, "the reader's folder given the dead copy's name was removed"


# =============================================================================
# The dead-copy cleanup compares a copy with the former folder it judged
# =============================================================================

WHOSE = ["another account's", "this account's"]


def _put_at_the_name(monkeypatch, tmp_path, legacy, whose, chart="Old"):
    """A folder holding what the user's former folder held (another
    account's copy of it, or another folder of this account's), and the
    swap that puts it at the former name; with the other account."""
    theirs = _Theirs(monkeypatch)
    prepared = tmp_path / "prepared"
    _ordinary(prepared, chart)
    if whose == "another account's":
        theirs.own(prepared)
    return theirs, prepared, lambda: _RENAME(prepared, legacy)


@pytest.mark.parametrize("whose", WHOSE)
@pytest.mark.parametrize("form", ["copying", "incoming"])
def test_a_folder_put_at_the_former_name_after_its_judgement_removes_no_copy(monkeypatch, tmp_path, form, whose):
    """The account owning the folder above has given the reader's unmoved
    former folder an earlier version's dead-copy name (or moved it aside,
    a dead copy of it left), so that nothing stands at the former name
    when the cleanup judges it; then it puts a folder holding the same at
    the former name. Nothing put there after the judgement is read, and
    the reader's folder and the copy are left whole."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    if form == "copying":
        mine = base / ".Zij.0123456789abcdef.copying"
        _RENAME(legacy, mine)
    else:
        _RENAME(legacy, tmp_path / "aside")
        mine = _left_copy(target, None)
        held = {"copy": ("folder", None), "copy/saved_charts.json": ("file", json.dumps({"Old": REC}, indent=2).encode())}
    theirs, prepared, put = _put_at_the_name(monkeypatch, tmp_path, legacy, whose)
    _hook(monkeypatch, user_data, "_hold_a_copy", before=put)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(prepared), "the premise: the folder was put at the former name"
    assert _tree(mine) == held, "the reader's folder (or its copy) was removed as a copy of the folder put there"
    assert theirs.reads == [], f"the other account's folder was read: {theirs.reads}"


@pytest.mark.parametrize("whose", WHOSE)
def test_the_former_folder_given_a_dead_copys_name_once_judged_is_not_removed(monkeypatch, tmp_path, whose):
    """A dead copy an earlier version left, found and the former folder
    judged; then the account owning the folder above moves the copy aside,
    gives its name to the reader's former folder and puts a folder holding
    the same at the former name. The folder judged is never a copy of
    itself, nothing put at the name is read, and the reader's former folder
    is left whole."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    staging = base / ".Zij.0123456789abcdef.copying"
    staging.mkdir(mode=0o700)
    (staging / "saved_charts.json").write_bytes((legacy / "saved_charts.json").read_bytes())
    theirs, prepared, put = _put_at_the_name(monkeypatch, tmp_path, legacy, whose)

    def swap():
        _RENAME(staging, tmp_path / "copy aside")
        _RENAME(legacy, staging)
        put()
    _hook(monkeypatch, user_data, "_hold_a_copy", before=swap)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(prepared), "the premise: the swap was made"
    assert _tree(staging) == held, "the reader's former folder was removed as a copy of itself or of the one put there"
    assert theirs.reads == [], f"the other account's folder was read: {theirs.reads}"


@pytest.mark.parametrize("whose", WHOSE)
def test_a_link_of_this_accounts_at_the_former_name_is_followed_only_to_its_own_folder(monkeypatch, tmp_path, whose):
    """A link of the reader's at the former name: the folder it leads to is
    compared only where it is the reader's own; another account's is never
    read through it, and the copy is kept."""
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _ordinary(real)
    legacy.symlink_to(real)
    staging = base / ".Zij.0123456789abcdef.copying"
    staging.mkdir(mode=0o700)
    (staging / "saved_charts.json").write_bytes((real / "saved_charts.json").read_bytes())
    held = {"saved_charts.json": ("file", (real / "saved_charts.json").read_bytes())}
    theirs = _Theirs(monkeypatch)
    if whose == "another account's":
        theirs.own(real)
    user_data._remove_dead_copies(target, legacy)
    if whose == "another account's":
        assert _tree(staging) == held, "the copy was removed as a copy of another account's folder"
        assert theirs.reads == [], f"the other account's folder was read: {theirs.reads}"
    else:
        assert not os.path.lexists(staging), "a copy of the reader's own folder, through the reader's link, was kept"


def test_a_link_swapped_at_the_former_name_as_it_is_opened_keeps_every_copy(monkeypatch, tmp_path):
    """A link of this account's at the former name, identified; as it is
    opened, another link of this account's, to a folder holding the same,
    is put in its place. What was opened is not the object identified, so
    no copy is compared with it, and the copy is kept."""
    base, legacy, target = _base(tmp_path)
    real, other = tmp_path / "real", tmp_path / "other"
    _ordinary(real)
    _ordinary(other)
    legacy.symlink_to(real)
    second = tmp_path / "second"
    second.symlink_to(other)
    staging = base / ".Zij.0123456789abcdef.copying"
    staging.mkdir(mode=0o700)
    (staging / "saved_charts.json").write_bytes((real / "saved_charts.json").read_bytes())
    held = {"saved_charts.json": ("file", (real / "saved_charts.json").read_bytes())}

    def swap():
        _RENAME(legacy, tmp_path / "link aside")
        _RENAME(second, legacy)
    _hook(monkeypatch, os, "open", before=swap,
          when=lambda path, *a, **k: not isinstance(path, int) and Path(path) == legacy)
    user_data._remove_dead_copies(target, legacy)
    assert os.readlink(legacy) == str(other), "the premise: the second link was put at the name"
    assert _tree(staging) == held, "a copy was compared with a folder another link led to"


def _a_link_read_under_a_swap(monkeypatch, tmp_path, opens_a_link, swap, at="the read"):
    """A link of this account's at the former name, leading to the user's
    folder, its move refused; another link of this account's, to another
    folder, put in its place for the length of the read only (`swap`: the
    link itself, or the folder above), and everything put back after it;
    or, `at` "the open", for the length of the open of the descriptor the
    link is read through.
    Where the system cannot open a link itself (`opens_a_link` False:
    macOS), O_PATH is taken away. Returns what the launch raised (None)
    and the places."""
    base, legacy, target = _base(tmp_path)
    real, elsewhere = tmp_path / "real", tmp_path / "elsewhere"
    _ordinary(real)
    _ordinary(elsewhere, "Elsewhere")
    legacy.symlink_to(real)
    if not opens_a_link:
        monkeypatch.delattr(os, "O_PATH", raising=False)
    theirs = _Theirs(monkeypatch)
    _sticky(monkeypatch, theirs, legacy, refuse_ours=True)
    if swap == "the link":
        second, aside = tmp_path / "second", tmp_path / "aside"
        second.symlink_to(elsewhere)
        moves = [(legacy, aside), (second, legacy)]
    else:
        decoy, aside = tmp_path / "decoy", tmp_path / "xdg aside"
        decoy.mkdir()
        (decoy / LEGACY).symlink_to(elsewhere)
        moves = [(base, aside), (decoy, base)]
    swapped = []

    def swap_in():
        for one, other in moves:
            _RENAME(one, other)
        swapped.append(True)

    def swap_back():
        for one, other in reversed(moves):
            _RENAME(other, one)
    def plant():
        if at == "the read":
            _hook(monkeypatch, os, "readlink", before=swap_in, after=swap_back,
                  when=lambda path, *a, dir_fd=None: dir_fd is not None or Path(path) == legacy)
        else:
            o_path = getattr(os, "O_PATH", 0)
            _hook(monkeypatch, os, "open", before=swap_in, after=swap_back,
                  when=lambda path, flags, *a, **k: not isinstance(path, int) and (
                      (Path(path) == legacy and flags & o_path) or Path(path) == base))
    # The swap is planted for the move's own read: where the former folder's
    # path is judged first (and the link read there), only after that; and
    # where the folder opened is then compared with the one its path's walk
    # reaches (the link read there too), only after that.
    judge = getattr(user_data, "_judge_the_former_folders_path", None)
    walked = getattr(user_data, "_the_former_folder_walked", None)
    if judge is None:
        plant()
    else:
        last = "_the_former_folder_walked" if walked is not None else "_judge_the_former_folders_path"
        real_last = walked if walked is not None else judge

        def then_plant(*args, **kwargs):
            result = real_last(*args, **kwargs)
            plant()
            return result
        monkeypatch.setattr(user_data, last, then_plant)
    try:
        user_data._make_user_data_dir(target)
        raised = None
    except OSError as exc:
        raised = exc
    assert swapped, "the premise: the other link was put at the name for the read"
    assert legacy.is_symlink() and os.readlink(legacy) == str(real) and _tree(real), "the user's link was changed"
    assert not (target.is_symlink() and os.readlink(target) == str(elsewhere)), \
        "the data folder became a link to the other link's target"
    return raised, target, real


@pytest.mark.parametrize("opens_a_link", [True, False], ids=["O_PATH", "no O_PATH"])
def test_a_link_swapped_in_for_its_read_and_back_is_never_carried(monkeypatch, tmp_path, opens_a_link):
    """The link itself swapped for the read and back: read through a
    descriptor bound to the link first found, the data folder is a link to
    what that one names; where the link is read by its name relative to the
    folder above, its change time shows the swap and the launch ends as
    busy, no link made."""
    raised, target, real = _a_link_read_under_a_swap(monkeypatch, tmp_path, opens_a_link, "the link")
    if opens_a_link:
        assert raised is None and target.is_symlink() and os.readlink(target) == str(real), raised
    else:
        assert isinstance(raised, user_data.FormerFolderBusy), raised
        assert not os.path.lexists(target), "a data folder was made"


@pytest.mark.parametrize("opens_a_link", [True, False], ids=["O_PATH", "no O_PATH"])
def test_the_folder_above_swapped_for_the_links_read_is_never_carried(monkeypatch, tmp_path, opens_a_link):
    """The account owning the folder above renames that folder itself for
    the length of the read, putting there a folder of its own holding
    another link at the former name; the user's link is never touched. The
    link is read through a descriptor bound to it (or to the folder above,
    opened once): the data folder is a link to what the user's link names,
    never to the other."""
    raised, target, real = _a_link_read_under_a_swap(monkeypatch, tmp_path, opens_a_link, "the folder above")
    assert raised is None and target.is_symlink() and os.readlink(target) == str(real), raised


@pytest.mark.parametrize("opens_a_link", [True, False], ids=["O_PATH", "no O_PATH"])
def test_the_folder_above_swapped_as_the_link_is_opened_ends_the_move(monkeypatch, tmp_path, opens_a_link):
    """The folder above swapped for the length of the open of the
    descriptor the link is read through (the link itself, or the folder
    above): what was opened leads to another link than the one first
    found, and the launch ends as busy, no link made."""
    raised, target, real = _a_link_read_under_a_swap(monkeypatch, tmp_path, opens_a_link, "the folder above",
                                                     at="the open")
    assert isinstance(raised, user_data.FormerFolderBusy), raised
    assert not os.path.lexists(target), "a data folder was made"


@pytest.mark.parametrize("form", ["copying", "incoming"])
def test_a_copy_is_compared_with_the_folder_judged_and_never_the_one_put_at_the_name(monkeypatch, tmp_path, form):
    """A dead copy of the reader's former folder, the former folder judged;
    then, as the copy is held, the account owning the folder above moves
    the former folder aside and puts its own folder, holding the same, at
    the former name. The copy is compared with the folder judged (and goes,
    as a copy of it), and nothing of the folder put at the name is read."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    held = _tree(legacy)
    store = (legacy / "saved_charts.json").read_bytes()
    if form == "copying":
        staging = base / ".Zij.0123456789abcdef.copying"
        staging.mkdir(mode=0o700)
        (staging / "saved_charts.json").write_bytes(store)
    else:
        staging = _left_copy(target, None)
    theirs, prepared, put = _put_at_the_name(monkeypatch, tmp_path, legacy, "another account's")
    theirs_held = _tree(prepared)
    theirs.reads.clear()                        # the test's own look at that folder, before
    aside = tmp_path / "former aside"

    def swap():
        _RENAME(legacy, aside)
        put()
    _hook(monkeypatch, user_data, "_hold_a_copy", before=swap)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(prepared), "the premise: the other folder was put at the former name"
    assert theirs.reads == [], f"the folder put at the former name was read: {theirs.reads}"
    assert not os.path.lexists(staging), "the copy, a copy of the folder judged, was kept"
    assert _tree(aside) == held, "the reader's former folder is not whole"
    assert _tree(legacy) == theirs_held, "the folder put at the name was changed"


@pytest.mark.parametrize("form", ["copying", "incoming"])
def test_a_folder_put_at_a_dead_copys_name_inside_its_removal_is_left_whole(monkeypatch, tmp_path, form):
    """The removal's first look finds the dead copy at its name; the account
    owning the folder above then gives that name to a folder of the
    reader's, holding a store. The copy is emptied through its descriptor
    alone, and the reader's folder is left whole."""
    base, legacy, target = _base(tmp_path)
    _ordinary(legacy)
    staging = base / f".Zij.0123456789abcdef.{form}"
    staging.mkdir(mode=0o700)
    inside = staging if form == "copying" else staging / "copy"
    inside.mkdir(mode=0o700, exist_ok=True)
    (inside / "saved_charts.json").write_bytes((legacy / "saved_charts.json").read_bytes())
    mine = base / "mine"
    _ordinary(mine, "Mine")
    held = _tree(mine)
    aside = tmp_path / "aside"
    armed, real_lstat, real_remove = [], os.lstat, user_data._remove_through

    def remove(fd, name):
        armed.append(Path(name))
        return real_remove(fd, name)

    def lstat(path, *args, **kwargs):
        seen = real_lstat(path, *args, **kwargs)
        if armed and armed[-1] == staging and not isinstance(path, int) and Path(path) == staging:
            armed.clear()
            _RENAME(staging, aside)
            _RENAME(mine, staging)
        return seen
    monkeypatch.setattr(user_data, "_remove_through", remove)
    monkeypatch.setattr(os, "lstat", lstat)
    user_data._remove_dead_copies(target, legacy)
    assert os.path.lexists(aside), "the premise: the name was given to the reader's folder inside the removal"
    assert _tree(staging) == held, "the reader's folder given the dead copy's name inside its removal was emptied"
