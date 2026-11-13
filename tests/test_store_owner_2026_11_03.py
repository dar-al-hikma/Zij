"""Each file in the data folder judged by its own owner, on every platform.

The data folder was judged and narrowed, the files in it were not. Where an
older version left the folder open to other accounts, another account's
store put in it before the first launch of this version was loaded as the
user's, and its link at the store's name was followed by the load and by
every save after, the user's whole store written into that account's file,
the page silent. Every file the app reads, follows or writes there -- the
store, the preferences, their locks, versions and recovery copies, the
cut-short saves a load tidies -- is now judged at its name (a link by its own
owner, not followed) and as opened; only this account's is read or written
through. Another account's store is a store that cannot be read and of which
no copy is made, and the next save puts a new store of the user's at the
name; the user's own link is followed as before. The former folder is held
to the same: on Windows its store is judged as it is read, and a copy of it,
which would make every file the user's, is made only of the user's entries.

The owner calls are stood in: on POSIX, another account's id for an object
the test plants, by its identity, at its name, through a link and as opened;
on Windows, the security calls, one seam per call (_Windows). Every link a
test plants points under tmp_path. And on macOS an earlier version's dead
copy of the former folder is kept, neither compared nor removed: a macOS
access list does not show in the mode the comparison's gate reads."""
import errno
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

import user_data
from test_windows_owner_and_link_2026_11_02 import (ADMINISTRATORS, DENIED, INJECTED, LEGACY, OTHER_SID, REC, _REAL,
                                                    _Windows,
                                                    _an_earlier_versions_dead_copy, _base, _former_tree, _key,
                                                    _launched, _listings, _tree)

STORE = "saved_charts.json"


class _Posix:
    """POSIX with another account: the owner of each object the test plants
    (by its identity) is another id, read at its name, through a link and
    as opened; every other object's is its own."""

    def __init__(self, monkeypatch):
        self.other, self.planted = os.getuid() + 1, set()
        monkeypatch.setattr(user_data, "_owner_of_the_name", lambda path: self._of(_REAL["lstat"](path)))
        monkeypatch.setattr(user_data, "_owner_of", lambda path: self._of(_REAL["stat"](path)))
        monkeypatch.setattr(user_data, "_owner_of_the_open", lambda fd: self._of(_REAL["fstat"](fd)), raising=False)

    def _of(self, seen):
        return self.other if (seen.st_dev, seen.st_ino) in self.planted else seen.st_uid

    def plant(self, path, follow=True):
        self.planted.add(_key(path, follow))
        return path

    def widen(self, folder):
        folder.chmod(0o777)             # as an older version made it under umask 000


class _Win(_Windows):
    """_Windows, planting as _Posix does: another account's SID."""

    def plant(self, path, follow=True):
        return self.own(path, OTHER_SID, follow)

    def widen(self, folder):
        self.wide.add(_key(folder))


def _platform(monkeypatch, which):
    return _Posix(monkeypatch) if which == "posix" else _Win(monkeypatch)


def _opened(monkeypatch):
    """The identity of every file the data layer opened by a name, once it
    was opened (a refused open is no open)."""
    seen, real = [], os.open

    def opening(path, flags, mode=0o777, *, dir_fd=None):
        fd = real(path, flags, mode, dir_fd=dir_fd)
        if dir_fd is None:
            found = _REAL["fstat"](fd)
            seen.append((found.st_dev, found.st_ino))
        return fd
    monkeypatch.setattr(os, "open", opening)
    return seen


def _folder(monkeypatch, tmp_path, which, name="Zij", wide=True):
    """The user's folder under `name`, made as an older version made it
    (open to others where `wide`), in a base of the test's; the platform
    stood in, the base, the folder and the data folder's path."""
    stood = _platform(monkeypatch, which)
    base, _legacy, target = _base(tmp_path)
    folder = base / name
    folder.mkdir()
    if wide:
        stood.widen(folder)
    return stood, folder, target


def _outside(tmp_path, charts=None, name="harvest.json"):
    where = tmp_path / "elsewhere"
    where.mkdir(exist_ok=True)
    (where / name).write_text(json.dumps(charts if charts is not None else {"Injected": INJECTED}, indent=2))
    return where / name


def test_a_store_of_the_users_others_could_write_is_set_aside_unread_after_the_folder_is_repaired(
        monkeypatch, tmp_path):
    """An older version's 0777 folder could leave the user's own store at
    0666. Closing the folder does not close the file: it is set aside at the
    launch, unread, and the page offers to restore it; the launch after it
    finds nothing to set aside."""
    _stood, folder, target = _folder(monkeypatch, tmp_path, "posix")
    store = folder / STORE
    store.write_text(json.dumps({"Old": REC}, indent=2))
    store.chmod(0o666)
    before, inode = store.read_bytes(), store.stat().st_ino

    assert _launched(monkeypatch, target) is None
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    [aside] = [p for p in target.iterdir() if p.name.startswith(STORE + ".set-aside-")]
    assert (aside.stat().st_ino, aside.read_bytes(), stat.S_IMODE(aside.stat().st_mode)) == (inode, before, 0o600)
    assert not store.exists() and user_data.load_saved_charts() == {}
    assert user_data.set_aside_notices()["awaiting"] is True

    assert _launched(monkeypatch, target) is None
    assert [p.name for p in target.iterdir()] == [aside.name] and user_data.load_saved_charts() == {}
    assert user_data.restore_set_aside() is True and user_data.load_saved_charts() == {"Old": REC}


# (platform, folder name, launch): the Windows former folder is moved in
# without a look at its entries, so another account's store comes in with
# it; on POSIX the move refuses such a folder (FormerFolderNotCarried).
CASES = [("posix", "Zij", "first"), ("posix", "Zij", "later"), ("windows", "Zij", "first"),
         ("windows", "Zij", "later"), ("windows", LEGACY, "first")]
IDS = [f"{w}-{n}-{l}" for w, n, l in CASES]


def _the_next_save_is_a_store_of_the_users(target, planted_key):
    store = target / STORE
    assert user_data.saved_charts_as_they_stand().state == "absent"
    assert user_data.write_saved_charts({"Mine": REC}) is True
    assert not os.path.islink(store) and _key(store, follow=False) != planted_key, "not replaced at the name"
    assert json.loads(store.read_text()) == {"Mine": REC}
    assert user_data.load_saved_charts() == {"Mine": REC}


@pytest.mark.parametrize("which, name, launch", CASES, ids=IDS)
def test_another_accounts_store_is_not_loaded_and_the_next_save_puts_the_users_at_the_name(monkeypatch, tmp_path,
                                                                                         which, name, launch):
    stood, folder, target = _folder(monkeypatch, tmp_path, which, name, wide=launch == "first")
    store = folder / STORE
    store.write_text(json.dumps({"Injected": INJECTED}, indent=2))
    planted = _key(stood.plant(store), follow=False)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    assert {k: user_data.store_notices()[k] for k in ("unreadable", "copy")} == {"unreadable": True, "copy": None}
    assert not [n for n in os.listdir(target) if ".unreadable-" in n or ".previous-" in n]
    assert planted not in opened, "another account's store was opened"
    _the_next_save_is_a_store_of_the_users(target, planted)


@pytest.mark.parametrize("which, name, launch", CASES, ids=IDS)
def test_another_accounts_link_at_the_stores_name_is_never_followed(monkeypatch, tmp_path, which, name, launch):
    stood, folder, target = _folder(monkeypatch, tmp_path, which, name, wide=launch == "first")
    harvest = stood.plant(_outside(tmp_path))
    link = folder / STORE
    link.symlink_to(harvest)
    planted = _key(stood.plant(link, follow=False), follow=False)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    assert {k: user_data.store_notices()[k] for k in ("unreadable", "copy")} == {"unreadable": True, "copy": None}
    _the_next_save_is_a_store_of_the_users(target, planted)
    assert _key(harvest) not in opened, "the link was followed"
    assert json.loads(harvest.read_text()) == {"Injected": INJECTED}
    # A later launch: the user's own store, the other account's file unchanged.
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {"Mine": REC}
    assert user_data.write_saved_charts({"Mine": REC, "Second": REC}) is True
    assert json.loads(harvest.read_text()) == {"Injected": INJECTED}


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_link_to_a_file_of_the_users_own_is_not_followed(monkeypatch, tmp_path, which):
    """Another account's link at the store's name may lead to any file of the
    user's: it was read as the store, and the save wrote the store over it."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which)
    users = _outside(tmp_path, {"Elsewhere": REC}, "the_users_other_file.json")
    link = folder / STORE
    link.symlink_to(users)
    planted = _key(stood.plant(link, follow=False), follow=False)
    before = users.read_bytes()
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    _the_next_save_is_a_store_of_the_users(target, planted)
    assert users.read_bytes() == before and _key(users) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_link_to_nothing_at_the_stores_name_is_replaced_not_written_through(monkeypatch, tmp_path,
                                                                                            which):
    """A link of another account's to a name it may make a file at: the save
    made the user's store there, in that account's folder."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which)
    (tmp_path / "elsewhere").mkdir()
    harvest = tmp_path / "elsewhere" / "harvest.json"
    link = folder / STORE
    link.symlink_to(harvest)
    planted = _key(stood.plant(link, follow=False), follow=False)
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert user_data.store_notices()["unreadable"] is True
    _the_next_save_is_a_store_of_the_users(target, planted)
    assert not os.path.lexists(harvest)


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_file_put_at_the_name_between_the_look_and_the_open_is_not_read(monkeypatch, tmp_path,
                                                                                         which):
    """The name looked at is the user's store; what is opened is judged by
    its own owner, read through what was opened."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    (folder / STORE).write_text(json.dumps({"Old": REC}, indent=2))
    theirs = tmp_path / "theirs.json"
    theirs.write_text(json.dumps({"Injected": INJECTED}, indent=2))
    stood.plant(theirs)
    assert _launched(monkeypatch, target) is None
    real = user_data._open_regular_file

    def swapped(path, *args, **kwargs):
        if Path(path).name == STORE and theirs.exists():
            os.replace(theirs, path)        # put in its place after the look
        return real(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_open_regular_file", swapped)
    assert user_data.load_saved_charts() == {}
    assert user_data.store_notices()["unreadable"] is True


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_the_users_own_link_to_their_own_store_is_not_followed(monkeypatch, tmp_path, which):
    """A store kept as a link (to one in a synced folder) was followed for
    the load and the save. A link at a store's name is now never followed:
    not read, not written through, the link and its file left, the page
    told."""
    _stood, folder, target = _folder(monkeypatch, tmp_path, which)
    kept = _outside(tmp_path, {"Old": REC}, "store.json")
    (folder / STORE).symlink_to(kept)
    before = kept.read_bytes()
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert user_data.set_aside_notices()["unfollowed"] is True
    assert user_data.saved_charts_as_they_stand().state == "unreadable"
    assert user_data.write_saved_charts({"Old": REC, "Mine": REC}) is False
    assert os.readlink(target / STORE) == str(kept)
    assert kept.read_bytes() == before


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_the_users_own_link_to_another_accounts_file_is_neither_read_nor_written_through(monkeypatch, tmp_path,
                                                                                        which):
    """Not read, no copy made, and the page says a link was not followed
    (a link at a store's name is never followed, wherever it leads); a save
    is refused, and the link is left."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which)
    theirs = stood.plant(_outside(tmp_path))
    (folder / STORE).symlink_to(theirs)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    assert {k: user_data.store_notices()[k] for k in ("unreadable", "copy")} == {"unreadable": False, "copy": None}
    assert user_data.set_aside_notices()["unfollowed"] is True
    assert user_data.saved_charts_as_they_stand().state == "unreadable"
    assert user_data.write_saved_charts({"Mine": REC}) is False
    assert os.readlink(target / STORE) == str(theirs)
    assert json.loads(theirs.read_text()) == {"Injected": INJECTED}
    assert _key(theirs) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
@pytest.mark.parametrize("kind", ["file", "link", "link to nothing"])
def test_another_accounts_preferences_are_not_read_and_left_as_they_are(monkeypatch, tmp_path, which, kind):
    """Not read, no copy made: the page's sentence says the file is left as
    it is and choices are not kept, and none is written over it: a link
    leading nowhere, which no read would refuse, is left as well."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which)
    theirs = stood.plant(_outside(tmp_path, {"last_chart": "Injected"}, "prefs.json"))
    nothing = theirs.with_name("nothing.json")
    if kind == "file":
        theirs = stood.plant(theirs.rename(folder / "preferences.json"))
    else:
        (folder / "preferences.json").symlink_to(theirs if kind == "link" else nothing)
    planted = _key(stood.plant(folder / "preferences.json", follow=False), follow=False)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_preferences() == {}
    notices = user_data.preferences_notices()
    assert (notices["unreadable"], notices["copy"]) == (True, None)
    assert user_data.remember_preference("last_chart", "Mine") is False
    assert _key(target / "preferences.json", follow=False) == planted, "replaced at the name"
    assert os.path.islink(target / "preferences.json") is (kind != "file")
    assert not nothing.exists()
    assert json.loads(theirs.read_text()) == {"last_chart": "Injected"}
    assert _key(theirs) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_versions_are_neither_read_counted_nor_removed(monkeypatch, tmp_path, which):
    """Ten of another account's under newer version names held the store's
    own bytes: the user's version was not kept, and the user's two were
    removed as the oldest."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    store = folder / STORE
    store.write_text(json.dumps({"Old": REC}, indent=2))
    own = [folder / f"{STORE}.previous-20200101-000000-00{n}" for n in (1, 2)]
    for path in own:
        path.write_text("{}")
    theirs = []
    for n in range(1, 11):
        version = folder / f"{STORE}.previous-29991231-235959-{n:03d}"
        version.write_bytes(store.read_bytes())
        theirs.append(stood.plant(version))
    planted = {_key(p) for p in theirs}
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.write_saved_charts({"Mine": REC}) is True
    assert [p.exists() for p in own] == [True, True], "the user's own versions were removed"
    assert [json.loads(p.read_text()) for p in theirs] == [{"Old": REC}] * 10
    assert not planted & set(opened), "another account's version was read"
    kept = [n for n in os.listdir(target) if n.startswith(STORE + ".previous-2") and not n.startswith(
        STORE + ".previous-2999") and n not in {p.name for p in own}]
    assert len(kept) == 1 and json.loads((target / kept[0]).read_text()) == {"Old": REC}


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_recovery_copy_is_not_taken_for_the_users(monkeypatch, tmp_path, which):
    """A malformed store of the user's: the copy beside it under a recovery
    name, another account's and holding the same bytes, was read and named
    as the user's copy. A copy of the user's own is made."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    (folder / STORE).write_bytes(b"{not a store")
    theirs = folder / f"{STORE}.unreadable-20000101-000000"
    theirs.write_bytes(b"{not a store")
    stood.plant(theirs)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    copy = user_data.store_notices()["copy"]
    assert copy and copy != theirs.name
    assert (target / copy).read_bytes() == b"{not a store" and _key(target / copy) != _key(theirs)
    assert _key(theirs) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_cut_short_save_is_left_unread(monkeypatch, tmp_path, which):
    """A stray of another account's under a cut-short save's name, holding
    a store: it was read, kept aside as the user's recovered save, and
    removed. It is left as it stands."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    stray = folder / f"{STORE}.0123456789abcdef.tmp"
    stray.write_text(json.dumps({"Injected": INJECTED}))
    os.utime(stray, (1_000_000_000, 1_000_000_000))
    stood.plant(stray)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    user_data.load_saved_charts()
    assert user_data.store_notices()["recovered"] == 0
    assert json.loads(stray.read_text()) == {"Injected": INJECTED}
    assert not [n for n in os.listdir(target) if ".recovered-" in n]
    assert _key(stray) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
@pytest.mark.parametrize("lock", ["saved_charts_lock", "preferences_lock"])
def test_another_accounts_lock_file_is_never_opened_and_refuses_the_write(monkeypatch, tmp_path, which, lock):
    """Another account's regular file under the lock's name was opened for
    reading and writing, locked as the app's own and removed at the release.
    It is now something in the way: DataLockBlocked, and left as it stands."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    name = "saved_charts.lock" if lock == "saved_charts_lock" else "preferences.lock"
    theirs = folder / name
    theirs.write_text("")
    stood.plant(theirs)
    assert _launched(monkeypatch, target) is None
    opened = _opened(monkeypatch)
    with pytest.raises(user_data.DataLockBlocked):
        with getattr(user_data, lock)():
            pass
    assert theirs.exists() and _key(theirs) not in opened


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_file_at_the_imported_mark_marks_nothing(monkeypatch, tmp_path, which):
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    (folder / user_data._IMPORTED_BESIDE_THE_PROGRAM).write_text("")
    stood.plant(folder / user_data._IMPORTED_BESIDE_THE_PROGRAM)
    assert _launched(monkeypatch, target) is None
    assert user_data._the_store_beside_the_program_was_imported() is False


@pytest.mark.parametrize("which", ["posix", "windows"])
@pytest.mark.parametrize("how", ["the writer", "a save"])
def test_a_link_to_another_accounts_file_put_at_the_name_after_the_writers_look_is_not_written_through(
        monkeypatch, tmp_path, which, how):
    """The look found the user's store; following what then stood at the
    name reached that account's file, and the save replaced it there. Only
    what can change a name in the narrowed folder can put it there. The
    write no longer follows anything at the name: its temporary file
    replaces what stands there, so a link put there after the look (here as
    the temporary file is made) is itself replaced, and the file it names is
    left as it was."""
    stood, folder, target = _folder(monkeypatch, tmp_path, which, wide=False)
    (folder / STORE).write_text(json.dumps({"Old": REC}, indent=2))
    theirs = stood.plant(_outside(tmp_path))
    assert _launched(monkeypatch, target) is None
    store, real, swaps = target / STORE, user_data._new_temp_file, []

    def swapped(path, *args, **kwargs):
        if not swaps and not os.path.islink(store):
            os.unlink(store)
            os.symlink(theirs, store)
            stood.plant(store, follow=False)
            swaps.append(True)
        return real(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_new_temp_file", swapped)
    if how == "a save":
        assert user_data.write_saved_charts({"Mine": REC}) is True
    else:
        user_data._write_text_atomically(store, json.dumps({"Mine": REC}))
    assert swaps, "the look was never passed"
    assert not os.path.islink(store) and json.loads(store.read_text()) == {"Mine": REC}
    assert json.loads(theirs.read_text()) == {"Injected": INJECTED}
    assert os.listdir(theirs.parent) == [theirs.name]


def _the_former_folder_whose_move_is_refused(monkeypatch, tmp_path):
    """Windows stood in: the user's former folder, open to others, holding
    the user's store; its rename refused, as one is while another account
    holds a file in it open. The platform, the base, the folder and the data
    folder's path."""
    stood = _Win(monkeypatch)
    base, legacy, target = _base(tmp_path)
    legacy.mkdir()
    stood.widen(legacy)
    (legacy / STORE).write_text(json.dumps({"Old": REC}, indent=2))
    real = Path.rename

    def rename(self, to):
        if Path(self) == legacy:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(self))
        return real(self, to)
    monkeypatch.setattr(Path, "rename", rename)
    return stood, base, legacy, target


def _the_copy_refused(base, target, raised):
    """FormerFolderNotCarried, with today's reason, no data folder and no copy
    left beside the former folder."""
    assert type(raised) is user_data.FormerFolderNotCarried
    assert str(raised) == user_data.FORMER_FOLDER_NOT_CARRIED
    assert os.listdir(base) == [LEGACY]
    assert user_data.data_folder_state() == ("made", user_data.FORMER_FOLDER_NOT_CARRIED)
    assert not os.path.lexists(target)


@pytest.mark.parametrize("entry", ["the store", "a file in a folder in it", "a folder in it", "a link",
                                   "an owner refused"])
def test_another_accounts_entry_keeps_the_windows_copy_from_being_made(monkeypatch, tmp_path, entry):
    """Every file a copy makes is the user's: another account's store copied
    in by name was loaded as the user's own, the page silent, where POSIX's
    look at the same folder refuses it."""
    stood, base, legacy, target = _the_former_folder_whose_move_is_refused(monkeypatch, tmp_path)
    if entry == "the store":
        (legacy / STORE).write_text(json.dumps({"Injected": INJECTED}, indent=2))
        stood.plant(legacy / STORE)
    elif entry == "an owner refused":
        stood.own(legacy / STORE, DENIED)
    elif entry == "a link":
        (legacy / "a link").symlink_to(_outside(tmp_path))
        stood.plant(legacy / "a link", follow=False)
    else:
        (legacy / "kept").mkdir()
        (legacy / "kept" / "file.json").write_text("{}")
        stood.plant(legacy / "kept" / ("file.json" if entry == "a file in a folder in it" else ""), follow=False)
    copied = []
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: copied.append(a))
    raised = _launched(monkeypatch, target)
    _the_copy_refused(base, target, raised)
    assert not copied, "the former folder was copied"


def test_another_accounts_store_is_not_in_the_load_after_the_windows_copy_is_refused(monkeypatch, tmp_path):
    """The load of a launch refused so reads nothing of it."""
    stood, base, legacy, target = _the_former_folder_whose_move_is_refused(monkeypatch, tmp_path)
    (legacy / STORE).write_text(json.dumps({"Injected": INJECTED}, indent=2))
    planted = _key(stood.plant(legacy / STORE))
    _the_copy_refused(base, target, _launched(monkeypatch, target))
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    assert planted not in opened, "another account's store was opened"
    assert json.loads((legacy / STORE).read_text()) == {"Injected": INJECTED}


def _a_store_in_the_former_folder_beside_the_data_folder(monkeypatch, tmp_path, which, charts):
    """The data folder standing with no store, the user's former folder
    beside it holding `charts`: the platform, the store, the data folder."""
    stood = _platform(monkeypatch, which)
    _the_base, legacy, target = _base(tmp_path)
    legacy.mkdir()
    target.mkdir()
    (legacy / STORE).write_text(json.dumps(charts, indent=2))
    assert _launched(monkeypatch, target) is None
    return stood, legacy / STORE, target


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_store_in_the_former_folder_is_not_brought_in(monkeypatch, tmp_path, which):
    """On Windows it was opened and brought in as the user's, nothing said;
    a data folder with no store beside a former folder that stayed open to
    others is reach enough."""
    stood, theirs, target = _a_store_in_the_former_folder_beside_the_data_folder(monkeypatch, tmp_path, which,
                                                                                 {"Injected": INJECTED})
    planted = _key(stood.plant(theirs))
    opened = _opened(monkeypatch)
    assert user_data.load_saved_charts() == {}
    with user_data.saved_charts_lock():
        assert user_data.bring_in_the_old_store() is False
    assert not (target / STORE).exists()
    assert planted not in opened, "another account's store was opened"
    assert user_data.write_saved_charts({"Mine": REC}) is True
    assert user_data.load_saved_charts() == {"Mine": REC}
    assert json.loads(theirs.read_text()) == {"Injected": INJECTED}


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_another_accounts_file_put_at_the_former_stores_name_after_the_look_is_not_read(monkeypatch, tmp_path, which):
    """The name looked at is the user's; what is opened is judged by its own
    owner, read through what was opened. (On POSIX the store is opened by its
    own name relative to the folder its path's walk opened: the swap is made
    at that open as well.)"""
    stood, old, target = _a_store_in_the_former_folder_beside_the_data_folder(monkeypatch, tmp_path, which,
                                                                              {"Old": REC})
    theirs = tmp_path / "theirs.json"
    theirs.write_text(json.dumps({"Injected": INJECTED}, indent=2))
    stood.plant(theirs)
    real = os.open

    def swapped(path, *args, **kwargs):
        relative = kwargs.get("dir_fd") is not None and path == old.name
        if (path == old or relative) and theirs.exists():
            os.replace(theirs, old)
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", swapped)
    assert user_data._the_first_old_store() == (old, None, False)
    assert not (target / STORE).exists()


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_the_users_own_store_in_the_former_folder_is_still_brought_in(monkeypatch, tmp_path, which):
    _stood, old, target = _a_store_in_the_former_folder_beside_the_data_folder(monkeypatch, tmp_path, which,
                                                                               {"Old": REC})
    assert user_data.load_saved_charts() == {"Old": REC}
    assert json.loads((target / STORE).read_text()) == {"Old": REC}
    assert json.loads(old.read_text()) == {"Old": REC}


def test_another_accounts_entry_put_in_during_the_windows_copy_keeps_it_from_being_published(monkeypatch, tmp_path):
    """The first look found the user's alone; the copy is whole, and holds
    a file of another account's."""
    stood, base, legacy, target = _the_former_folder_whose_move_is_refused(monkeypatch, tmp_path)
    real = shutil.copytree

    def copying(*args, **kwargs):
        (legacy / "put.json").write_text("{}")
        stood.plant(legacy / "put.json")
        return real(*args, **kwargs)
    monkeypatch.setattr(shutil, "copytree", copying)
    _the_copy_refused(base, target, _launched(monkeypatch, target))


@pytest.mark.parametrize("owner", ["the user", "Administrators", "no owners kept"])
def test_a_former_folder_of_the_users_own_entries_is_still_copied_on_windows(monkeypatch, tmp_path, owner):
    """Taken for the user's as _ours takes them: the copy published, the
    former folder kept."""
    stood, _base_folder, legacy, target = _the_former_folder_whose_move_is_refused(monkeypatch, tmp_path)
    (legacy / "kept").mkdir()
    (legacy / "kept" / "file.json").write_text("{}")
    if owner != "the user":
        stood.own(legacy / STORE, ADMINISTRATORS if owner == "Administrators" else None)
        stood.own(legacy / "kept" / "file.json", ADMINISTRATORS if owner == "Administrators" else None)
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {"Old": REC}
    assert json.loads((target / "kept" / "file.json").read_text()) == {}
    assert json.loads((legacy / STORE).read_text()) == {"Old": REC}


@pytest.mark.parametrize("which", ["posix", "windows"])
def test_an_ordinary_first_launch_and_save_are_unchanged(monkeypatch, tmp_path, which):
    """The control: nothing of another account's anywhere."""
    _platform(monkeypatch, which)
    _base_folder, _legacy, target = _base(tmp_path)
    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {}
    assert user_data.store_notices()["unreadable"] is False
    assert user_data.write_saved_charts({"Mine": REC}) is True
    assert user_data.write_saved_charts({"Mine": REC, "Second": REC}) is True
    assert user_data.load_saved_charts() == {"Mine": REC, "Second": REC}
    assert user_data.remember_preference("last_chart", "Mine") is True


def test_an_earlier_versions_dead_copy_on_macos_is_kept_neither_compared_nor_removed(monkeypatch, tmp_path):
    """On macOS an access list that lets another account write does not show
    in the mode the comparison's gate reads, so a copy that matches is kept,
    and its folder never listed."""
    legacy, target, staging = _an_earlier_versions_dead_copy(tmp_path, 0o700)
    monkeypatch.setattr(sys, "platform", "darwin")
    listed = _listings(monkeypatch, staging)
    user_data._remove_dead_copies(target, legacy)
    assert listed == [], "the copy was listed"
    assert _tree(staging) == _former_tree()


def test_an_earlier_versions_dead_copy_on_linux_still_goes(monkeypatch, tmp_path):
    """The control: Linux keeps the rule (no write for the group or others,
    which an access list's mask shows)."""
    legacy, target, staging = _an_earlier_versions_dead_copy(tmp_path, 0o700)
    monkeypatch.setattr(sys, "platform", "linux")
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(staging)
