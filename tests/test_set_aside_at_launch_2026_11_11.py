# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""A file in the data folder that another account could change is set aside
at the launch, unread, and brought back only by the page's one button.

An older version under umask 000 left the data folder 0777 (or 0333) and the
store and the preferences 0666. The launch copied each such file into a
private one put over its name, and the next load read what another account
had written into it as the user's. A folder that could not be listed was
passed over, and a store in it read by its name; a link of the user's at the
store's name was followed to a file others could write; a sparse file was
copied to its full size; a lock file was replaced while a window held it.

Now such a file is moved aside, in its own folder, under a recovery name,
made 0600 there and not read; the data folder is made 0700, and one that
still cannot be listed is not used; a link at a store's name is never
followed; the restore reads a file set aside within its limit and writes it
as a new file; nothing the launch copies passes a store's limit or the
launch's bounds; a lock file is narrowed in place.

Run natively on POSIX: real modes, a real hard link, a real descriptor held,
a real second process holding the lock. Windows is stood in (_Windows), its
lists answered by a seam. Every link and every file a test makes lies under
tmp_path."""
import errno
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import user_data
from test_windows_owner_and_link_2026_11_02 import INJECTED, REC, _Windows, _base, _key, _launched, _reads

# Each test's launches leave no held data folder open (conftest).
pytestmark = pytest.mark.usefixtures("the_data_folder_held_is_let_go")

STORE, PREFS = "saved_charts.json", "preferences.json"
OWN = {"Old": REC}
PLANTED = {"Injected": INJECTED}
MIB = 1024 * 1024


@pytest.fixture(autouse=True)
def _nothing_said_yet(monkeypatch):
    """The design before this one kept a one-shot mark of the launch's; a
    tree that has it starts each test without it."""
    if hasattr(user_data, "_CLOSED_AT_LAUNCH"):
        monkeypatch.setattr(user_data, "_CLOSED_AT_LAUNCH", [])
    # What one launch has handled is counted once a process: each test here
    # is a launch of its own.
    monkeypatch.setattr(user_data, "_LAUNCH_TALLY", [0, 0], raising=False)
    monkeypatch.setattr(user_data, "_MODELESS", [], raising=False)


def _mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def _inode(path):
    return os.lstat(path).st_ino


def _aside(folder, name=STORE):
    return sorted(p for p in folder.iterdir() if p.name.startswith(name + ".set-aside-"))


def _kept(folder, mode_of_files, mode_of_folder, charts=OWN):
    """The user's store and preferences in `folder`, at the modes an older
    version's umask gave them."""
    folder.mkdir(exist_ok=True)
    (folder / STORE).write_text(json.dumps(charts, indent=2))
    (folder / PREFS).write_text(json.dumps({"last_chart": "Old"}))
    for name in (STORE, PREFS):
        os.chmod(folder / name, mode_of_files)
    os.chmod(folder, mode_of_folder)


def _written_through(fd, link, charts=PLANTED):
    """What another account writes, after the launch, through the descriptor
    and the hard link it held from before it."""
    text = json.dumps(charts, indent=2)
    if fd is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, text.encode())
        os.ftruncate(fd, len(text))
    if link is not None:
        link.write_text(text)


def _said(**flags):
    """The page's flags (set_aside_notices), all False but `flags`."""
    return {"awaiting": False, "unfollowed": False, "held": False, **flags}


def _notices():
    """What the page is told of files others could change: this design's
    notices; where they are not (the design before it), its one flag, so
    that a control passes at both."""
    if hasattr(user_data, "set_aside_notices"):
        return _said(**user_data.set_aside_notices())
    return _said(awaiting=bool(user_data.store_notices().get("closed_to_others")))


# A 0666 store and preferences in a 0700 folder
# (and in a 0777 one, at the first launch of this version).

@pytest.mark.parametrize("folder_mode", [0o777, 0o700], ids=["first launch", "later launch"])
def test_a_wide_store_and_preferences_are_set_aside_unread_and_restored_as_new_files(monkeypatch, tmp_path,
                                                                                    folder_mode):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, folder_mode)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.link(target / STORE, elsewhere / STORE)
    fd = os.open(target / STORE, os.O_RDWR)
    before = {each: (_inode(target / each), (target / each).read_bytes()) for each in (STORE, PREFS)}
    try:
        assert _launched(monkeypatch, target) is None
        assert _mode(target) == 0o700
        for each in (STORE, PREFS):
            assert not os.path.lexists(target / each), each
            [aside] = _aside(target, each)
            assert (_inode(aside), aside.read_bytes()) == before[each], each          # moved, not copied
            assert _mode(aside) == 0o600, each
        assert user_data.load_saved_charts() == {}
        assert user_data.load_preferences() == {}
        assert _notices() == _said(awaiting=True)
        # a later launch: nothing of it read, nothing set aside again
        assert _launched(monkeypatch, target) is None
        assert user_data.load_saved_charts() == {}
        assert len(_aside(target)) == 1 and _notices()["awaiting"] is True

        assert user_data.restore_set_aside() is True
        assert user_data.load_saved_charts() == OWN
        assert user_data.load_preferences().get("last_chart") == "Old"
        assert _aside(target) == [] and _aside(target, PREFS) == []
        assert _notices() == _said()
        assert _inode(target / STORE) != before[STORE][0] and _mode(target / STORE) == 0o600
        _written_through(fd, elsewhere / STORE)
        assert user_data.load_saved_charts() == OWN                             # neither handle reaches it
    finally:
        os.close(fd)


def test_the_restore_keeps_what_was_saved_since_and_keeps_the_left_out_charts_beside_the_store(monkeypatch,
                                                                                                tmp_path):
    """A chart saved since under a name the file set aside holds as well:
    the saved one is kept, and the file set aside was kept under its
    recovery name, so the notice and its button stayed for ever and every
    press said the restore failed. It is now kept beside the saved charts
    under a name nothing reads, the notice goes, and the page is told once."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700, charts={"Old": REC, "Both": REC})
    assert _launched(monkeypatch, target) is None
    [aside] = _aside(target)
    before = (_inode(aside), aside.read_bytes())
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"New": REC, "Both": INJECTED}) is True
    kept = []
    assert user_data.restore_set_aside(kept) is True and kept == ["charts"]      # "Both" clashes
    assert user_data.load_saved_charts() == {"New": REC, "Both": INJECTED, "Old": REC}
    assert _aside(target) == [] and _notices() == _said()
    [beside] = [p for p in target.iterdir() if p.name.startswith(STORE + ".kept-")]
    assert (_inode(beside), beside.read_bytes(), _mode(beside)) == (*before, 0o600)
    assert _launched(monkeypatch, target) is None                               # nothing reads it after
    assert user_data.load_saved_charts() == {"New": REC, "Both": INJECTED, "Old": REC}
    assert beside.exists() and _notices() == _said()


# A 0333 folder, which narrowing to its owner's
# bits left 0300, unlistable, its store read by name.

@pytest.mark.parametrize("folder_mode", [0o333, 0o300])
@pytest.mark.parametrize("held", ["hard link", "descriptor"])
def test_an_unlistable_folder_is_made_0700_and_its_wide_store_set_aside(monkeypatch, tmp_path, folder_mode, held):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = fd = None
    if held == "hard link":
        link = elsewhere / STORE
        os.link(target / STORE, link)
    else:
        fd = os.open(target / STORE, os.O_RDWR)
    before = (_inode(target / STORE), (target / STORE).read_bytes())
    os.chmod(target, folder_mode)
    try:
        assert _launched(monkeypatch, target) is None
        assert _mode(target) == 0o700
        [aside] = _aside(target)
        assert (_inode(aside), aside.read_bytes(), _mode(aside)) == (*before, 0o600)
        _written_through(fd, link)
        assert user_data.load_saved_charts() == {}
        assert _notices()["awaiting"] is True
    finally:
        os.chmod(target, 0o700)                                 # so that the tree can be removed
        if fd is not None:
            os.close(fd)


def test_a_folder_that_still_cannot_be_listed_fails_closed(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700, charts=PLANTED)
    real = os.listdir

    def listing(path="."):
        # By its name, or through the descriptor the launch holds on it.
        if (os.path.samestat(os.fstat(path), os.stat(target)) if isinstance(path, int)
                else os.path.realpath(path) == os.path.realpath(target)):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real(path)
    monkeypatch.setattr(os, "listdir", listing)
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert user_data.load_preferences() == {}
    assert user_data.data_folder_state() == ("listed", os.strerror(errno.EACCES))
    assert user_data.data_folder_problem() == os.strerror(errno.EACCES)
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts(OWN) is False
    assert json.loads((target / STORE).read_text()) == PLANTED              # nothing read, nothing written


# The user's own link at the store's name, to a
# file others can write.

def test_the_users_link_to_a_wide_file_is_not_read_and_nothing_is_restored_through_it(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.chmod(elsewhere, 0o755)
    file = elsewhere / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o666)
    os.symlink(file, target / STORE)
    hard = tmp_path / "hard.json"
    os.link(file, hard)
    before = (_inode(file), file.read_bytes())
    assert os.path.realpath(target / STORE).startswith(str(tmp_path))

    assert _launched(monkeypatch, target) is None
    assert os.path.islink(target / STORE) and os.readlink(target / STORE) == str(file)
    assert (_inode(file), file.read_bytes(), _mode(file)) == (*before, 0o666)
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)                             # nothing set aside: no button
    _written_through(None, hard)
    assert user_data.load_saved_charts() == {}
    assert _launched(monkeypatch, target) is None                           # a later launch: still left
    assert os.path.islink(target / STORE) and _inode(file) == before[0]

    file.write_text(json.dumps(OWN, indent=2))                              # the user's own again
    kept = file.read_bytes()
    assert user_data.restore_set_aside() is True                            # nothing awaits: a link is not its
    assert os.path.islink(target / STORE)
    assert (_inode(file), file.read_bytes(), _mode(file)) == (before[0], kept, 0o666)
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)


def test_the_users_link_to_a_wide_file_written_by_name_through_open_folders_is_not_read(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    os.chmod(base, 0o755)
    shared = base / "shared"
    shared.mkdir()
    os.chmod(shared, 0o755)
    file = shared / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o666)
    target.mkdir()
    os.symlink(file, target / STORE)
    os.chmod(target, 0o777)

    assert _launched(monkeypatch, target) is None
    file.write_text(json.dumps(PLANTED, indent=2))                          # by its name
    assert "Injected" not in user_data.load_saved_charts()
    assert _notices() == _said(unfollowed=True)


@pytest.mark.parametrize("name", [STORE, PREFS])
def test_the_writer_itself_writes_nothing_through_a_link_the_load_would_not_read(monkeypatch, tmp_path, name):
    """The page asks how the store stands before it saves, and saves
    nothing over a file it could not read; the writer itself did not ask,
    and replaced the file the user's link leads to when others could change
    it, its records gone and no version kept. Called directly, it now writes
    nothing through such a link: the file keeps its bytes and its inode, and
    the call returns False, as the page already takes a failed write. A
    link at the name is now never followed, and the restore writes nothing
    through it either."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.chmod(elsewhere, 0o755)
    file = elsewhere / name
    os.replace(target / name, file)
    os.chmod(file, 0o666)
    os.symlink(file, target / name)
    assert _launched(monkeypatch, target) is None
    before = (_inode(file), file.read_bytes())
    with user_data.saved_charts_lock(), user_data.preferences_lock():
        if name == STORE:
            assert user_data.write_saved_charts({"New": REC}) is False
        else:
            assert user_data.write_preferences({"last_chart": "New"}) is False
    assert (_inode(file), file.read_bytes()) == before and os.path.islink(target / name)
    assert [p.name for p in target.iterdir() if ".previous-" in p.name] == []
    assert user_data.restore_set_aside() is True                                # nothing awaits: a link is not its
    assert (_inode(file), file.read_bytes()) == before and os.path.islink(target / name)


def test_a_link_into_a_folder_others_can_write_is_neither_read_nor_written_through(monkeypatch, tmp_path):
    """After the launch, another account renames the file the user's link
    leads to aside in a folder it may write in, and puts its own link there
    to another file of the user's: that file is neither read nor written."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    file = elsewhere / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o600)
    os.chmod(elsewhere, 0o777)
    os.symlink(file, target / STORE)
    decoy = tmp_path / "decoy.txt"
    decoy.write_text("the user's other file\n")
    os.chmod(decoy, 0o644)
    inode = os.lstat(decoy).st_ino

    assert _launched(monkeypatch, target) is None
    os.rename(file, elsewhere / "aside.json")
    os.symlink(decoy, file)
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)                             # a link not followed: no button
    with user_data.saved_charts_lock():
        user_data.saved_charts_as_they_stand(keep_aside=True)
        assert user_data.write_saved_charts({"New": REC}) is False
    assert (_inode(decoy), decoy.read_bytes(), _mode(decoy)) == (inode, b"the user's other file\n", 0o644)
    assert [p.name for p in target.iterdir()] == [STORE]                    # no copy of the decoy made


@pytest.mark.parametrize("folder_mode", [0o1777, 0o777], ids=["sticky", "not sticky"])
def test_a_link_to_the_users_file_in_a_sticky_folder_others_can_write_is_not_followed(monkeypatch, tmp_path,
                                                                                       folder_mode):
    """The user's link to their own private file in a folder others may
    write in, sticky (as /tmp is) or not: a link at a store's name is never
    followed, so it is neither read nor written through."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    shared = tmp_path / "shared"
    shared.mkdir()
    file = shared / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o600)
    os.chmod(shared, folder_mode)
    os.symlink(file, target / STORE)

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"New": REC}) is False
    assert os.path.islink(target / STORE)
    assert json.loads(file.read_text()) == OWN


def test_a_link_to_a_link_to_a_private_file_is_neither_read_nor_written_through(monkeypatch, tmp_path):
    """The link is followed one hop only: a link at the store's name to a
    second link, to the user's private file in a private folder, is not
    read and not written through, the file and both links left as they are,
    and the page says it is a link the app does not follow, with no button."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.chmod(elsewhere, 0o700)
    file = elsewhere / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o600)
    os.symlink(file, elsewhere / "hop.json")
    os.symlink(elsewhere / "hop.json", target / STORE)
    before = (_inode(file), file.read_bytes())

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"New": REC}) is False
    assert user_data.restore_set_aside() is True and _notices() == _said(unfollowed=True)
    assert (_inode(file), file.read_bytes(), _mode(file)) == (*before, 0o600)
    assert os.readlink(target / STORE) == str(elsewhere / "hop.json") and os.readlink(elsewhere / "hop.json") == str(file)
    assert sorted(p.name for p in target.iterdir() if not p.name.endswith(".lock")) == [STORE]


def test_a_file_judged_fine_by_its_name_but_wide_as_opened_is_set_aside(monkeypatch, tmp_path):
    """The name is looked at, then the file opened: what was opened is
    judged again (fstat), and it is that file that is set aside."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    swapped = target.parent / "swapped.json"
    swapped.write_text(json.dumps(PLANTED, indent=2))
    os.chmod(swapped, 0o666)
    real = user_data._open_regular_file

    def opening(path, *args, **kwargs):
        if Path(path).name == STORE and swapped.exists():
            os.replace(swapped, path)                   # after the look at the name, before the open
        return real(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_open_regular_file", opening)

    assert _launched(monkeypatch, target) is None
    monkeypatch.setattr(user_data, "_open_regular_file", real)
    assert not os.path.lexists(target / STORE)
    [aside] = _aside(target)
    assert json.loads(aside.read_text()) == PLANTED and _mode(aside) == 0o600
    assert user_data.load_saved_charts() == {}


@pytest.mark.parametrize("name", ["saved_charts.json.previous-20000101-000000-001",
                                  "saved_charts.json.unreadable-20000101-000000",
                                  "preferences.json.unreadable-20000101-000000"])
def test_a_wide_version_or_recovery_copy_is_set_aside_unread(monkeypatch, tmp_path, name):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    (target / name).write_text(json.dumps(PLANTED))
    os.chmod(target / name, 0o666)
    inode = _inode(target / name)
    assert _launched(monkeypatch, target) is None
    assert not os.path.lexists(target / name)
    [aside] = _aside(target, name)
    assert _inode(aside) == inode and _mode(aside) == 0o600
    assert user_data.load_saved_charts() == OWN
    assert _notices() == _said()                 # kept for the hand, not restored


# Nothing the launch handles is copied past its bounds.

def _allocated(folder):
    return sum(os.lstat(p).st_blocks * 512 for p in Path(folder).iterdir())


@pytest.mark.parametrize("name, limit", [(STORE, "STORE_BYTE_LIMIT"), (PREFS, "PREFERENCES_BYTE_LIMIT"),
                                         ("saved_charts.json.previous-20000101-000000-001", "STORE_BYTE_LIMIT")])
def test_a_sparse_wide_file_is_set_aside_without_a_byte_allocated_and_its_restore_refused(monkeypatch, tmp_path,
                                                                                         name, limit):
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    with open(target / name, "wb") as handle:
        handle.truncate(80 * MIB)
    os.chmod(target / name, 0o666)
    before = _allocated(target)
    assert _launched(monkeypatch, target) is None
    assert _allocated(target) <= before + 64 * 1024
    [aside] = _aside(target, name)
    assert aside.stat().st_size == 80 * MIB and aside.stat().st_blocks * 512 <= getattr(user_data, limit) + 1
    assert user_data.restore_set_aside() is name.startswith(STORE + ".previous-")    # a version is not restored
    assert _aside(target, name) == [aside] and _allocated(target) <= before + 64 * 1024
    assert user_data.load_saved_charts() == {}


class _Opened:
    """A file object as os.fdopen gives it, whose reads are told to `on_read`
    before they are made."""

    def __init__(self, handle, on_read):
        self.handle, self.on_read = handle, on_read

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self.handle.__exit__(*exc)

    def fileno(self):
        return self.handle.fileno()

    def read(self, size=-1):
        self.on_read(self.handle, size)
        return self.handle.read(size)


def test_a_file_set_aside_that_grows_while_the_restore_reads_it_is_refused(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    os.chmod(target / PREFS, 0o600)
    assert _launched(monkeypatch, target) is None
    [aside] = _aside(target)
    monkeypatch.setattr(user_data, "STORE_BYTE_LIMIT", 4096)
    grown = []

    def growing(handle, size):
        if not grown:                                   # after its size is read, before its bytes are:
            grown.append(size)                          # a store still, past the limit
            text = json.dumps({"Grown": REC}).encode()
            aside.write_bytes(text + b" " * (8192 - len(text)))
    real = os.fdopen
    monkeypatch.setattr(os, "fdopen", lambda fd, *args, **kwargs: _Opened(real(fd, *args, **kwargs), growing))
    assert user_data.restore_set_aside() is False
    monkeypatch.setattr(os, "fdopen", real)
    assert grown and _aside(target) == [aside]
    assert user_data.load_saved_charts() == {}


def test_the_restore_reads_no_byte_of_a_file_set_aside_past_its_limit(monkeypatch, tmp_path):
    """Its size is read from the opened file first: one past the limit is
    refused before a byte of it is read."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    os.chmod(target / PREFS, 0o600)
    assert _launched(monkeypatch, target) is None
    [aside] = _aside(target)
    monkeypatch.setattr(user_data, "STORE_BYTE_LIMIT", 4096)
    os.truncate(aside, 8192)
    asked = []
    real = os.fdopen
    monkeypatch.setattr(os, "fdopen", lambda fd, *args, **kwargs: _Opened(real(fd, *args, **kwargs),
                                                                          lambda handle, size: asked.append(size)))
    assert user_data.restore_set_aside() is False
    monkeypatch.setattr(os, "fdopen", real)
    assert asked == [] and _aside(target) == [aside]


def _a_former_folder_to_copy(monkeypatch, base, legacy):
    real = os.rename

    def renaming(src, dst, *args, **kwargs):
        if Path(src) == legacy:
            raise OSError(errno.EXDEV, os.strerror(errno.EXDEV), str(src))
        return real(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "rename", renaming)


@pytest.mark.parametrize("kind", ["past a store's limit", "growing while copied", "past the launch's files",
                                  "past the launch's bytes", "a store others could write"])
def test_the_former_folder_s_copy_keeps_its_bounds_and_copies_no_wide_file(monkeypatch, tmp_path, kind):
    base, legacy, target = _base(tmp_path)
    _kept(legacy, 0o600, 0o700)
    if kind == "past a store's limit":
        with open(legacy / "saved_charts.json.previous-20000101-000000-001", "wb") as handle:
            handle.truncate(80 * MIB)
    elif kind == "growing while copied":
        (legacy / "notes.txt").write_bytes(b"x" * 1000)
        real_read = os.read

        def reading(fd, n):
            if os.fstat(fd).st_size == 1000:
                os.truncate(legacy / "notes.txt", 32 * MIB)
            return real_read(fd, n)
        monkeypatch.setattr(os, "read", reading)
    elif kind == "past the launch's files":
        monkeypatch.setattr(user_data, "_LAUNCH_FILE_LIMIT", 3, raising=False)
        for n in range(4):
            (legacy / f"saved_charts.json.unreadable-2000010{n}-000000").write_text("{}")
    elif kind == "past the launch's bytes":
        monkeypatch.setattr(user_data, "_LAUNCH_BYTE_LIMIT", 8192, raising=False)
        for n in range(4):
            (legacy / f"saved_charts.json.unreadable-2000010{n}-000000").write_bytes(b"x" * 4096)
    else:
        os.chmod(legacy / STORE, 0o666)
        (legacy / STORE).write_text(json.dumps(PLANTED, indent=2))
    _a_former_folder_to_copy(monkeypatch, base, legacy)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.FormerFolderNotCopied)
    assert not os.path.lexists(target) and legacy.is_dir()
    assert user_data.load_saved_charts() == {}
    assert sum(p.stat().st_blocks * 512 for p in base.rglob("*") if p.is_file() and legacy not in p.parents) < MIB


def test_a_former_folder_whose_copy_keeps_failing_is_copied_within_one_launchs_bound_across_the_page_s_retries(
        monkeypatch, tmp_path):
    """The page asks for the folder again at each of its runs while the
    making failed (data_folder_state). The launch's bound was set back to
    nothing at each asking, so a former folder whose copy kept failing was
    copied whole again at each run: one process copied many times the bound.
    It is one bound for the process."""
    base, legacy, target = _base(tmp_path)
    _kept(legacy, 0o600, 0o700)
    for n in range(3):
        (legacy / f"notes-{n}.bin").write_bytes(b"x" * 4096)
    _a_former_folder_to_copy(monkeypatch, base, legacy)
    monkeypatch.setattr(user_data, "_copy_is_whole_through", lambda copy, top: False)
    monkeypatch.setattr(user_data, "_LAUNCH_BYTE_LIMIT", 5 * 4096, raising=False)
    copied = []
    real = user_data._copy_within_bounds

    def counted(one, out, size):
        try:
            return real(one, out, size)
        finally:
            copied.append(os.lseek(one, 0, os.SEEK_CUR))
    monkeypatch.setattr(user_data, "_copy_within_bounds", counted)
    assert isinstance(_launched(monkeypatch, target), user_data.FormerFolderNotCopied)
    once = sum(copied)
    assert once >= 3 * 4096
    for _run in range(10):
        assert user_data.data_folder_state()[0] == 'made'
    assert sum(copied) <= 5 * 4096, (once, sum(copied))
    assert not os.path.lexists(target) and legacy.is_dir()


def test_the_launch_judges_at_most_its_bound_of_files_and_a_load_reads_none_past_it(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700, charts=PLANTED)
    monkeypatch.setattr(user_data, "_LAUNCH_FILE_LIMIT", 1, raising=False)
    assert _launched(monkeypatch, target) is None
    assert len(_aside(target, PREFS)) == 1 and os.path.lexists(target / STORE)   # the store, past the bound, left
    assert user_data.load_saved_charts() == {}
    assert len(_aside(target)) == 1                                             # set aside by the load


class _AsItReadsThere:
    """A stat result as a filesystem that keeps no modes gives it: every
    group and other bit set, whatever was asked."""

    def __init__(self, seen):
        self._seen = seen
        self.st_mode = seen.st_mode | 0o077

    def __getattr__(self, name):
        return getattr(self._seen, name)


def _keeps_no_modes(monkeypatch, top):
    """A filesystem that keeps no modes under the folder `top`, stood in:
    each look at what is under it (by name, or at a descriptor open on it)
    reads every group and other bit."""
    real = {name: getattr(os, name) for name in ("stat", "lstat", "fstat")}

    def under(seen):
        try:
            names = [top, *top.rglob("*")]
        except OSError:
            return False
        for each in names:
            try:
                if os.path.samestat(seen, real["lstat"](each)) or os.path.samestat(seen, real["stat"](each)):
                    return True
            except OSError:
                continue
        return False

    def looked(name):
        def call(path, *args, **kwargs):
            seen = real[name](path, *args, **kwargs)
            if kwargs.get("dir_fd") is not None or not under(seen):
                return seen
            return _AsItReadsThere(seen)
        return call
    for name in real:
        monkeypatch.setattr(os, name, looked(name))


def test_a_data_folder_on_a_disk_that_keeps_no_modes_is_taken_as_it_is(monkeypatch, tmp_path):
    """On a filesystem that keeps no modes every file reads as one others
    could change, so every store the app wrote was set aside at the next
    load, and nothing could be kept there. The launch tells it from the
    folder it has just made 0700 reading back otherwise, and takes the
    folder as it is: its files read, nothing set aside, nothing said."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    (target / STORE).write_text(json.dumps(OWN, indent=2))
    os.chmod(target / STORE, 0o600)
    _keeps_no_modes(monkeypatch, target)
    assert _mode(target) & 0o077 and _mode(target / STORE) & 0o022

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == OWN
    assert _aside(target) == [] and _notices() == _said()
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts(dict(OWN, Mine=REC)) is True
    assert user_data.write_preferences({"last_chart": "Mine"}) is True
    assert _launched(monkeypatch, target) is None                      # the next launch
    assert user_data.load_saved_charts() == dict(OWN, Mine=REC)
    assert user_data.load_preferences().get("last_chart") == "Mine"
    assert [p.name for p in target.iterdir() if user_data._SET_ASIDE in p.name] == [] and _notices() == _said()
    # Only that folder is taken so: a file others may write elsewhere on the same disk is still judged.
    other = tmp_path / "other"
    other.mkdir()
    (other / STORE).write_text("{}")
    os.chmod(other / STORE, 0o666)
    assert user_data._exposed_at_the_name(other / STORE) is True


def test_on_a_disk_that_keeps_modes_a_store_others_may_write_is_still_set_aside(monkeypatch, tmp_path):
    """The control: a folder whose 0700 holds, with one 0666 store."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    (target / STORE).write_text(json.dumps(OWN, indent=2))
    os.chmod(target / STORE, 0o666)
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert len(_aside(target)) == 1 and _notices() == _said(awaiting=True)


def _swapped_in_at_the_look(monkeypatch, base, target, other):
    """Another account that may write in the folder above the data folder
    renames the data folder aside and the user's own folder `other` in at
    its name, at the moment the launch looks at whether the folder's disk
    keeps modes (by a hook on that call)."""
    real = user_data._note_whether_it_keeps_modes

    def swapped(*args, **kwargs):
        os.rename(target, base / "Zij.old")
        os.rename(other, target)
        return real(*args, **kwargs)
    monkeypatch.setattr(user_data, "_note_whether_it_keeps_modes", swapped)


@pytest.mark.parametrize("disk", ["keeps modes", "keeps no modes"])
def test_a_folder_renamed_in_at_the_data_folders_name_is_not_taken_for_one_that_keeps_no_modes(monkeypatch,
                                                                                                 tmp_path, disk):
    """Another account that may write in the folder above the data folder
    could rename a folder of the user's in at its name between the narrowing
    and the look at whether the disk keeps modes. The whole path is judged
    first now: a data folder in a folder others may write in (0777, not
    sticky) is refused before either, nothing is read or set aside, nothing
    is taken for a disk that keeps no modes, and both folders are left."""
    base, _legacy, target = _base(tmp_path)
    os.chmod(base, 0o777)
    target.mkdir()
    os.chmod(target, 0o700)
    (target / STORE).write_text(json.dumps(OWN, indent=2))
    os.chmod(target / STORE, 0o600)
    other = base / "Other"
    other.mkdir()
    (other / STORE).write_text(json.dumps(PLANTED, indent=2))
    os.chmod(other / STORE, 0o666)
    os.chmod(other, 0o777)
    if disk == "keeps no modes":
        _keeps_no_modes(monkeypatch, base)
    _swapped_in_at_the_look(monkeypatch, base, target, other)
    seen = _reads(monkeypatch)

    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderOpenToOthers), raised
    assert raised.strerror == user_data.DATA_FOLDER_PATH_OPEN
    assert user_data.load_saved_charts() == {}
    assert user_data._MODELESS == []
    assert _aside(target) == [] and _aside(other) == [] and seen == []
    assert json.loads((target / STORE).read_text()) == OWN                    # (its mode as the disk shows it)
    assert json.loads((other / STORE).read_text()) == PLANTED and not os.path.lexists(base / "Zij.old")


class _OwnedBy:
    """A stat result with another owner's id."""

    def __init__(self, seen, uid):
        self._seen = seen
        self.st_uid = uid

    def __getattr__(self, name):
        return getattr(self._seen, name)


@pytest.mark.parametrize("owner", ["another account", "this account"])
def test_a_link_into_another_accounts_sticky_folder_is_not_followed(monkeypatch, tmp_path, owner):
    """A sticky folder others may write in is sound for the one hop only
    where it is this account's or the system's: its owner may rename any
    file in it, the user's too, which the redirect needs. The folder's owner
    stood in as another account (its st_uid); the link at the store's name
    leads to the user's own private file there: not followed, not read, not
    written through, and the page says so with no button. The same folder
    of this account's is not followed either: no link at a store's name is."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    shared = tmp_path / "shared"
    shared.mkdir()
    file = shared / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o600)
    os.chmod(shared, 0o1777)
    os.symlink(file, target / STORE)
    inode = _inode(file)
    theirs = owner == "another account"
    if theirs:
        real = os.stat
        held = real(shared)
        uid = os.getuid() + 1

        def looked(path, *args, **kwargs):
            seen = real(path, *args, **kwargs)
            if kwargs.get("dir_fd") is None and os.path.samestat(seen, held):
                return _OwnedBy(seen, uid)
            return seen
        monkeypatch.setattr(os, "stat", looked)
    assert (os.stat(shared).st_uid not in (os.getuid(), 0)) is theirs and os.lstat(file).st_uid == os.getuid()
    opened = []
    real_open = user_data._open_regular_file

    def opening(path, *args, **kwargs):
        opened.append(os.path.realpath(path))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_open_regular_file", opening)

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)
    assert os.path.realpath(file) not in opened                          # never opened, so never read
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"New": REC}) is False
    assert os.path.islink(target / STORE)
    assert (_inode(file), file.read_bytes()) == (inode, json.dumps(OWN, indent=2).encode())


# The lock between two windows.

@pytest.mark.parametrize("name", ["saved_charts.lock", "preferences.lock"])
def test_a_wide_lock_held_by_another_process_is_narrowed_in_place(monkeypatch, tmp_path, name):
    import fcntl
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    lock = target / name
    lock.write_bytes(b"")
    os.chmod(lock, 0o666)
    inode = _inode(lock)
    holder = subprocess.Popen([sys.executable, "-c",
                               "import fcntl, os, sys\n"
                               "fd = os.open(sys.argv[1], os.O_RDWR)\n"
                               "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                               "print('held', flush=True)\n"
                               "sys.stdin.read()\n", str(lock)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert _launched(monkeypatch, target) is None
        assert _inode(lock) == inode and _mode(lock) == 0o600
        with pytest.raises(user_data.DataLockBusy):
            user_data._take_file_lock(lock, deadline=time.monotonic() + 0.3)
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(OSError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    finally:
        holder.stdin.close()
        holder.wait(timeout=30)


# Controls: nothing another account could change, nothing set aside.

@pytest.mark.parametrize("files, folder", [(0o600, 0o700), (0o644, 0o755), (0o600, 0o777)],
                         ids=["owner only", "others may read", "owner only in a wide folder"])
def test_a_file_no_other_account_could_change_is_read_as_before(monkeypatch, tmp_path, files, folder):
    base, _legacy, target = _base(tmp_path)
    _kept(target, files, folder)
    before = {each: _inode(target / each) for each in (STORE, PREFS)}
    assert _launched(monkeypatch, target) is None
    assert {each: (_inode(target / each), _mode(target / each)) for each in (STORE, PREFS)} == \
        {each: (before[each], files) for each in (STORE, PREFS)}
    assert user_data.load_saved_charts() == OWN
    assert user_data.load_preferences().get("last_chart") == "Old"
    assert _notices() == _said()
    assert getattr(user_data, "restore_set_aside", lambda: True)() is True     # nothing to restore


def test_the_users_link_to_a_private_file_is_not_followed(monkeypatch, tmp_path):
    """Read at the release before this one: a link of the user's to a
    private file in a private folder. A link at a store's name is now never
    followed: not read, not written through, the page told."""
    base, _legacy, target = _base(tmp_path)
    target.mkdir()
    os.chmod(target, 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.chmod(elsewhere, 0o700)
    file = elsewhere / "target.json"
    file.write_text(json.dumps(OWN, indent=2))
    os.chmod(file, 0o600)
    os.symlink(file, target / STORE)
    before = (_inode(file), file.read_bytes())
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert _notices() == _said(unfollowed=True)
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({**OWN, "New": REC}) is False
    assert os.path.islink(target / STORE) and (_inode(file), file.read_bytes()) == before


# Windows stood in: the file's access list is answered by its seam.

@pytest.mark.parametrize("wide", [STORE, PREFS, None], ids=["store", "preferences", "neither"])
def test_windows_asks_the_list_of_the_store_and_the_preferences_and_sets_aside_what_others_could_change(
        monkeypatch, tmp_path, wide):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    win = _Windows(monkeypatch)
    before = {each: _key(target / each) for each in (STORE, PREFS)}
    if wide:
        win.write_wide.add(before[wide])
    assert _launched(monkeypatch, target) is None
    assert before[STORE] in win.write_asked and before[PREFS] in win.write_asked
    for each in (STORE, PREFS):
        assert os.path.lexists(target / each) is (each != wide), each
    assert user_data.load_saved_charts() == ({} if wide == STORE else OWN)
    moved = [before[wide]] if wide else []
    assert [_key(aside) for aside in (_aside(target, wide) if wide else [])] == moved and win.reset == moved
    assert _notices() == _said(awaiting=wide is not None)


def test_windows_never_reads_a_file_whose_move_aside_is_refused(monkeypatch, tmp_path):
    """A handle another account holds on the file without sharing deleting
    refuses its rename: the file is not read, while that handle (a POSIX
    descriptor stands for it) goes on writing, and the page is told."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    win = _Windows(monkeypatch)
    store = _key(target / STORE)
    win.write_wide.add(store)
    fd = os.open(target / STORE, os.O_WRONLY)
    real = os.rename

    def renaming(src, dst, *args, **kwargs):
        if Path(src).name == STORE:
            raise PermissionError(13, "in use by another process", str(src))
        return real(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "rename", renaming)
    try:
        assert _launched(monkeypatch, target) is None
        assert _key(target / STORE) == store and _aside(target) == []
        _written_through(fd, None)
        assert user_data.load_saved_charts() == {}
        assert _notices() == _said(held=True)
        with user_data.saved_charts_lock():
            assert user_data.saved_charts_as_they_stand().state == "unreadable"     # nor written over
    finally:
        os.close(fd)


def test_windows_narrows_a_wide_lock_in_place(monkeypatch, tmp_path):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    lock = target / "saved_charts.lock"
    lock.write_bytes(b"")
    win = _Windows(monkeypatch)
    win.write_wide.add(_key(lock))
    assert _launched(monkeypatch, target) is None
    assert win.reset == [_key(lock)] and os.path.lexists(lock) and _aside(target, lock.name) == []


# The page's words: each case in its own sentence.

SET_ASIDE = "Saved charts or preferences that other accounts on this computer could change were set aside unread."
LINK_EXPOSED = ("Saved charts or preferences behind a link to a file other accounts on this computer could change "
                "were not read.")
LINK_UNFOLLOWED = "Saved charts or preferences behind a link this app does not follow were not read."
RESTORE_FAILED = "They could not all be restored; what is left stays set aside."
HELD = ("Saved charts or preferences that other accounts on this computer could change could not be set aside, so "
        "they were not read.")


@pytest.mark.parametrize("flag, sentence, button", [("awaiting", SET_ASIDE, True),
                                                    ("unfollowed", LINK_UNFOLLOWED, False), ("held", HELD, False)])
def test_the_sidebar_says_each_case_in_its_own_sentence(monkeypatch, flag, sentence, button):
    """Behind a link nothing is set aside, and behind a link the app does
    not follow no other account need be able to change anything: those two
    were said as a file set aside, or as one that could not be. A link,
    never followed, has no button; the sentence of a file that could not be
    set aside is said only for that; the sentence of a link to a file others
    could change is said no more."""
    from conftest import assert_no_exception, make_app
    at = make_app(page="chart")
    engine = sys.modules["engine"]
    flags = {"awaiting": False, "unfollowed": False, "held": False, flag: True}
    monkeypatch.setattr(engine, "set_aside_notices", lambda: dict(flags))
    at.run()
    assert_no_exception(at)
    said = [w.value for w in at.sidebar.warning if w.value in (SET_ASIDE, LINK_EXPOSED, LINK_UNFOLLOWED, HELD)]
    assert said == [sentence]
    assert [b.label for b in at.sidebar.button].count("Restore them") == (1 if button else 0)


KEPT_BESIDE = "Some charts set aside had names already taken; they were kept beside the saved charts."


def test_the_page_says_once_that_charts_set_aside_were_kept_beside(monkeypatch):
    """The press whose restore kept charts beside the saved charts is
    followed by the sentence once; the run after says nothing of it."""
    from conftest import assert_no_exception, make_app
    at = make_app(page="chart")
    engine = sys.modules["engine"]
    waiting = [True]

    def restore(kept=None):
        waiting[0] = False
        kept.append("charts")
        return True
    monkeypatch.setattr(engine, "set_aside_notices", lambda: _said(awaiting=waiting[0]))
    monkeypatch.setattr(engine, "restore_set_aside", restore)
    at.run()
    [button] = [b for b in at.sidebar.button if b.label == "Restore them"]
    button.click().run()
    assert_no_exception(at)
    assert [w.value for w in at.sidebar.warning].count(KEPT_BESIDE) == 1
    assert SET_ASIDE not in [w.value for w in at.sidebar.warning] and RESTORE_FAILED not in [e.value for e in at.sidebar.error]
    assert [b.label for b in at.sidebar.button].count("Restore them") == 0
    at.run()
    assert KEPT_BESIDE not in [w.value for w in at.sidebar.warning]
