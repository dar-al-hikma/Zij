# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The whole path to the data folder judged, the folder held, and no link at
a store's name followed.

A link of the user's at the data folder's name, or at a store's name, was
judged by its own owner and by the last folder it led to, never by the
folders between. Where its path ran through a folder another account may
write in, that account could put another of the user's folders (or files)
in its place, once, before a launch: the launch read that other file as the
user's saved charts and the next save wrote over it, saying it was done; and
a folder on the way changed between a save's look and its replace sent the
replace onto any file of the user's. A refused change of the data folder's
mode was taken for a disk that keeps no modes, and every look at the files
others could change was dropped; on Windows a list that could not be closed
was only recorded. One press of the restore read every file set aside, with
no bound, and read again at every press each it could not bring back.

Now every folder on the way must be this account's or the system's and
closed to other accounts (a sticky folder counting as closed for an entry of
this account's or the system's), the data folder is held for the life of the
process and every file in it reached through that descriptor, a link at a
store's name is never followed, a refused change of mode (or a list not
closed) refuses the folder, and one press reads within the launch's own
bounds, each file once.

Run natively on POSIX: real modes, real links, a real sticky folder, real
descriptors. Every scene is built under tmp_path, below folders this
account made 0700, so its verdict does not hang on the host's /tmp: /tmp
itself is sticky and root's (or, in a user namespace that maps no id to
root's, the overflow id's), and the entry the walk looks up in it is this
account's. Windows is stood in (_Windows), its lists and its hold answered
by seams."""
import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

import user_data
from test_windows_owner_and_link_2026_11_02 import REC, HeldByATest, _Windows, _launched

STORE, PREFS = "saved_charts.json", "preferences.json"
OWN = {"Old": REC}
OTHER = {"OtherApp": REC}
MIB = 1024 * 1024
pytestmark = pytest.mark.usefixtures("the_data_folder_held_is_let_go")


@pytest.fixture(autouse=True)
def _a_launch_of_its_own(monkeypatch):
    """Each test is a launch of its own: nothing counted, noted, refused or
    held by an earlier one. The folder a test's launch holds is closed when
    the test ends (conftest's the_data_folder_held_is_let_go)."""
    monkeypatch.setattr(user_data, "_LAUNCH_TALLY", [0, 0], raising=False)
    monkeypatch.setattr(user_data, "_MODELESS", [], raising=False)
    monkeypatch.setattr(user_data, "_HELD", HeldByATest([None]), raising=False)
    monkeypatch.setattr(user_data, "_REFUSED", {}, raising=False)
    monkeypatch.setattr(user_data, "_RESTORE_FAILED", set(), raising=False)
    monkeypatch.setattr(user_data, "_LET_GO", set(), raising=False)


def _private(folder, charts=None, mode=0o700):
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, mode)
    if charts is not None:
        (folder / STORE).write_text(json.dumps(charts, indent=2))
        os.chmod(folder / STORE, 0o600)
    return folder


def _seen(path):
    return os.lstat(path).st_ino, Path(path).read_bytes()


def _base(tmp_path):
    """A base of the user's for the data folder, below tmp_path, 0700."""
    return _private(tmp_path / "home")


def _refused_with(reason):
    """Nothing read, nothing written, and the folder said refused for the
    reason user_data binds to the name `reason` -- looked up by name after
    what the code does is asked, so that a code without that reason fails
    on what it does."""
    assert user_data.load_saved_charts() == {}
    assert user_data.write_saved_charts({"Mine": REC}) is False
    assert user_data.data_folder_state() == ('used', getattr(user_data, reason, None))


# --- The data folder's name a link through a folder others may write -

def test_a_data_folder_reached_through_a_folder_others_may_write_is_refused(monkeypatch, tmp_path):
    """The user's link at the data folder's name leads to a private folder of
    the user's inside a 0777 folder that is not sticky; another account
    renames that folder aside and puts in its place a link to a second
    private folder of the user's, holding another application's store. The
    folder is refused, nothing is read, and the second store is untouched by
    a save."""
    base = _base(tmp_path)
    shared = _private(tmp_path / "shared", mode=0o777)
    _private(shared / "private", OWN)
    second = _private(tmp_path / "otherapp", OTHER)
    before = _seen(second / STORE)
    zij = base / "Zij"
    os.symlink(shared / "private", zij)
    os.rename(shared / "private", shared / "private-aside")          # the other account's move
    os.symlink(second, shared / "private")
    _launched(monkeypatch, zij)
    _refused_with("DATA_FOLDER_PATH_OPEN")
    assert _seen(second / STORE) == before


# --- A link at the store's name through a folder others may write ----

@pytest.mark.parametrize("payload", ["store", "not a store"])
def test_a_store_link_through_a_folder_others_may_write_is_never_followed(monkeypatch, tmp_path, payload):
    """The user's link at the store's name leads through shared/mid (shared
    0777) to a file of the user's; another account puts a link to a second
    folder of the user's in mid's place. Nothing is read, nothing is copied
    aside, the page is told, and a save leaves the second file as it was."""
    zij = _private(_base(tmp_path) / "Zij")
    shared = _private(tmp_path / "shared", mode=0o777)
    _private(shared / "mid", OWN)
    second = _private(tmp_path / "second")
    (second / STORE).write_text(json.dumps(OTHER) if payload == "store" else "a private note\n")
    before = _seen(second / STORE)
    os.symlink(shared / "mid" / STORE, zij / STORE)
    os.rename(shared / "mid", shared / "mid-aside")
    os.symlink(second, shared / "mid")
    _launched(monkeypatch, zij)
    names = sorted(os.listdir(zij))
    assert user_data.load_saved_charts() == {}
    assert user_data.store_notices()["copy"] is None
    assert sorted(os.listdir(zij)) == names
    assert user_data.set_aside_notices()["unfollowed"] is True
    assert user_data.write_saved_charts({"Mine": REC}) is False
    assert _seen(second / STORE) == before
    assert os.path.islink(zij / STORE)


@pytest.mark.parametrize("name", [STORE, PREFS])
def test_a_link_to_the_users_own_private_file_is_not_followed_either(monkeypatch, tmp_path, name):
    """A link of the user's at the store's or the preferences' name to a
    0600 file of the user's in a 0700 folder (read before, one hop): not
    read, nothing written through it, the page told."""
    zij = _private(_base(tmp_path) / "Zij")
    elsewhere = _private(tmp_path / "elsewhere")
    target = elsewhere / "kept.json"
    target.write_text(json.dumps(OWN if name == STORE else {"last_chart": "Old"}))
    os.chmod(target, 0o600)
    before = _seen(target)
    os.symlink(target, zij / name)
    _launched(monkeypatch, zij)
    if name == STORE:
        assert user_data.load_saved_charts() == {}
        assert user_data.write_saved_charts({"Mine": REC}) is False
    else:
        monkeypatch.setattr(user_data, "_loadable_restored", lambda raw: raw)
        assert user_data._read_preferences_file() is None
        assert user_data.write_preferences({"last_chart": "Mine"}) is False
    assert user_data.set_aside_notices() == {"awaiting": False, "unfollowed": True, "held": False}
    assert _seen(target) == before and os.path.islink(zij / name)


# --- A folder on the way changed after the look -------------------

def test_a_store_link_whose_way_changes_after_the_look_writes_nothing(monkeypatch, tmp_path):
    """A store link through folders closed to others, whose way another hand
    changes right after the save's look at the name: nothing is written
    through it, and the file it comes to lead to is untouched."""
    zij = _private(_base(tmp_path) / "Zij")
    way = _private(tmp_path / "way")
    _private(way / "mid", OWN)
    victim = _private(tmp_path / "victim", OTHER)
    before = _seen(victim / STORE)
    os.symlink(way / "mid" / STORE, zij / STORE)
    _launched(monkeypatch, zij)
    real = user_data._whose
    swapped = []

    def whose(path):
        found = real(path)
        if Path(path) == zij / STORE and not swapped:
            os.rename(way / "mid", way / "mid-aside")
            os.symlink(victim, way / "mid")
            swapped.append(True)
        return found
    monkeypatch.setattr(user_data, "_whose", whose)
    with user_data.saved_charts_lock():
        saved = user_data.write_saved_charts({"Mine": REC})
    assert saved is False
    assert _seen(victim / STORE) == before


def test_a_data_folder_whose_way_changes_after_the_launch_is_written_in_the_folder_held(monkeypatch, tmp_path):
    """The data folder's name a link through folders closed to others; right
    after the launch's judgment returns, a folder on the way is renamed aside
    and a link to a victim folder of the user's put in its place. The load
    and the save go to the folder held, never by its path: the victim's
    store keeps its inode and bytes."""
    base = _base(tmp_path)
    way = _private(tmp_path / "way")
    _private(way / "private", OWN)
    victim = _private(tmp_path / "victim", OTHER)
    before = _seen(victim / STORE)
    zij = base / "Zij"
    os.symlink(way / "private", zij)
    real = user_data._keep_the_data_folder_ours

    def judged_then_swapped(path):
        held = real(path)
        os.rename(way / "private", way / "private-aside")
        os.symlink(victim, way / "private")
        return held
    monkeypatch.setattr(user_data, "_keep_the_data_folder_ours", judged_then_swapped)
    _launched(monkeypatch, zij)
    assert user_data.load_saved_charts() == OWN
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"Mine": REC, **OWN}) is True
    assert _seen(victim / STORE) == before
    assert sorted(json.loads((way / "private-aside" / STORE).read_text())) == ["Mine", "Old"]


@pytest.mark.parametrize("when", ["as the walk opens it", "as the folder held is opened"])
def test_a_folder_swapped_while_the_walk_opens_it_is_refused(monkeypatch, tmp_path, when):
    """A folder on the way replaced between the walk's look at it and its
    open (or the data folder replaced before the descriptor held is opened):
    the folder opened is checked against the one looked at, and refused."""
    base = _base(tmp_path)
    _private(base / "Zij", OWN)
    real_open = os.open
    done = []

    def opening(name, flags, *args, **kwargs):
        reading = flags & getattr(os, "O_PATH", 0) == 0 and flags & os.O_DIRECTORY
        wanted = (kwargs.get("dir_fd") is not None and name == "Zij" and not done
                  and (reading if when == "as the folder held is opened" else not reading or not hasattr(os, "O_PATH")))
        if wanted:
            done.append(True)
            os.rename(base / "Zij", base / "Zij-aside")
            _private(base / "Zij", OTHER)
        return real_open(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", opening)
    raised = _launched(monkeypatch, base / "Zij")
    monkeypatch.setattr(os, "open", real_open)
    assert done and isinstance(raised, user_data.DataFolderOpenToOthers)
    assert user_data._HELD[0] is None
    assert user_data._REFUSED == {str(base / "Zij"): user_data.DATA_FOLDER_PATH_OPEN}
    assert user_data.load_saved_charts() == {}


# --- The walk's own rules ------------------------------------------------

def _fake_owner(monkeypatch, name, uid):
    """os.stat as the walk calls it (relative to a folder, a link not
    followed) answering `uid` as the owner of the entry `name`: another
    account's entry, which no test can make without the system's own."""
    real = os.stat

    def stat_as(path, *args, **kwargs):
        seen = real(path, *args, **kwargs)
        if path == name and kwargs.get("dir_fd") is not None and kwargs.get("follow_symlinks") is False:
            fields = list(seen)
            fields[stat.ST_UID] = uid
            return os.stat_result(fields)
        return seen
    monkeypatch.setattr(os, "stat", stat_as)


def test_an_entry_of_another_accounts_in_a_sticky_folder_is_refused(monkeypatch, tmp_path):
    """A sticky folder others may write counts as closed only for an entry
    of this account's or the system's: one of another account's there, on
    the way, refuses the folder."""
    sticky = _private(tmp_path / "sticky", mode=0o777)
    os.chmod(sticky, 0o1777)
    _private(sticky / "theirs" / "Zij", OWN)
    _fake_owner(monkeypatch, "theirs", os.getuid() + 1)
    _launched(monkeypatch, sticky / "theirs" / "Zij")
    _refused_with("DATA_FOLDER_PATH_OPEN")


def test_a_link_of_another_accounts_on_the_way_is_refused(monkeypatch, tmp_path):
    """A link met on the way is judged by its own owner, not only by where it
    leads: another account's, inside a folder closed to others, refuses the
    folder."""
    base = _base(tmp_path)
    real_folder = _private(tmp_path / "real")
    _private(real_folder / "Zij", OWN)
    os.symlink(real_folder, base / "through")
    _fake_owner(monkeypatch, "through", os.getuid() + 1)
    _launched(monkeypatch, base / "through" / "Zij")
    _refused_with("DATA_FOLDER_PATH_OPEN")


def _groups(monkeypatch, gid, name, members=(), others_primary=False):
    """grp and pwd as the data layer reads them: this account named `name`,
    its primary group `gid`, the group `gid` named `name` with `members`,
    and another account taking it as primary where `others_primary`."""
    me = types.SimpleNamespace(pw_name=name, pw_uid=os.getuid(), pw_gid=gid)
    other = types.SimpleNamespace(pw_name="someone", pw_uid=os.getuid() + 1,
                                  pw_gid=gid if others_primary else gid + 1)
    pwd = types.SimpleNamespace(getpwuid=lambda uid: me, getpwall=lambda: [me, other])
    grp = types.SimpleNamespace(getgrgid=lambda g: types.SimpleNamespace(gr_name=name if g == gid else "staff",
                                                                          gr_mem=list(members)))
    monkeypatch.setitem(sys.modules, "pwd", pwd)
    monkeypatch.setitem(sys.modules, "grp", grp)


@pytest.mark.parametrize("group, read", [("of one", True), ("with a member", False), ("another's primary", False)])
def test_a_folder_its_group_may_write_counts_as_closed_only_for_a_group_of_one(monkeypatch, tmp_path, group, read):
    """Under a desktop's umask 002 the folders a user makes are writable by
    their group, which is the user's own group of one: such a folder on the
    way counts as closed; one whose group lists another member, or is
    another account's primary group, does not."""
    shared = _private(tmp_path / "grouped", mode=0o775)
    _private(shared / "Zij", OWN)
    gid = os.stat(shared).st_gid
    _groups(monkeypatch, gid, "me", members=("someone",) if group == "with a member" else (),
            others_primary=group == "another's primary")
    _launched(monkeypatch, shared / "Zij")
    if read:
        assert user_data.data_folder_state() == (None, None)
        assert user_data.load_saved_charts() == OWN
    else:
        _refused_with("DATA_FOLDER_PATH_OPEN")


# --- A refused change of mode refuses the folder ----------------

def test_a_refused_change_of_the_folders_mode_refuses_it(monkeypatch, tmp_path):
    """A 0777 data folder holding a 0666 store another account wrote, whose
    change of mode through the launch's descriptor is refused: the folder
    is refused, not taken for one that keeps no modes, and the store is not
    loaded."""
    zij = _private(_base(tmp_path) / "Zij", OTHER, mode=0o777)
    os.chmod(zij / STORE, 0o666)
    real = os.chmod

    def refusing(path, mode, *args, **kwargs):
        if isinstance(path, int):
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))
        return real(path, mode, *args, **kwargs)
    monkeypatch.setattr(os, "chmod", refusing)
    _launched(monkeypatch, zij)
    assert user_data._MODELESS == []
    _refused_with("DATA_FOLDER_NOT_CLOSED")
    assert stat.S_IMODE(os.lstat(zij).st_mode) == 0o777


def test_a_folder_already_0700_needs_no_change_and_is_used(monkeypatch, tmp_path):
    """A data folder already 0700 asks no change of mode, so a filesystem
    that would refuse one refuses nothing (a control)."""
    zij = _private(_base(tmp_path) / "Zij", OWN)
    real = os.chmod

    def refusing(path, mode, *args, **kwargs):
        if isinstance(path, int):
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))
        return real(path, mode, *args, **kwargs)
    monkeypatch.setattr(os, "chmod", refusing)
    _launched(monkeypatch, zij)
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN


# --- Windows, a list that cannot be closed -----------------------

def test_windows_a_list_that_cannot_be_closed_refuses_the_folder(monkeypatch, tmp_path):
    """Windows (stood in): a data folder whose list gives others a right and
    cannot be closed is refused, and the store in it (a file of the user's
    renamed back to the store's name through it, say) is not read."""
    win = _Windows(monkeypatch)
    base = _private(tmp_path / "appdata")
    zij = _private(base / "Zij", OWN)
    win.wide.add((os.stat(zij).st_dev, os.stat(zij).st_ino))
    closing = user_data._windows_close_the_list

    def unclosable(path):
        if os.path.samestat(os.stat(path), os.stat(zij)):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return closing(path)
    monkeypatch.setattr(user_data, "_windows_close_the_list", unclosable)
    _launched(monkeypatch, zij)
    assert not hasattr(user_data, "_WINDOWS_LISTS_LEFT_OPEN") or user_data._WINDOWS_LISTS_LEFT_OPEN == {}
    _refused_with("DATA_FOLDER_NOT_CLOSED")


# --- One restore is bounded ---------------------------------------

def test_one_restore_reads_within_the_launchs_bounds_each_file_once(monkeypatch, tmp_path):
    """Hard links under eight recovery names to one invalid store near its
    size, and a bound of three such files a press: one press reads the file
    once, leaves every name as it was, says not all were restored, and a
    second press reads nothing already refused."""
    zij = _private(_base(tmp_path) / "Zij")
    _launched(monkeypatch, zij)
    size = 2 * MIB
    first = zij / f"{STORE}.set-aside-20000101-000000"
    with open(first, "wb") as f:
        f.truncate(size)                    # sparse: no store
    os.chmod(first, 0o600)
    names = [first] + [zij / f"{STORE}.set-aside-20000101-000000-{n}" for n in range(2, 9)]
    for name in names[1:]:
        os.link(first, name)
    monkeypatch.setattr(user_data, "_LAUNCH_BYTE_LIMIT", 3 * size)
    real = user_data._read_what_was_set_aside
    read = []

    def reading(path, limit, *args, **kwargs):
        try:
            data, opened = real(path, limit, *args, **kwargs)
        except OSError:
            read.append((os.lstat(path).st_ino, 0))
            raise
        read.append((opened.st_ino, len(data)))
        return data, opened
    monkeypatch.setattr(user_data, "_read_what_was_set_aside", reading)
    before = {name: os.lstat(name).st_ino for name in names}
    assert user_data.restore_set_aside() is False
    assert sum(n for _ino, n in read) <= 3 * size
    assert len({ino for ino, _n in read}) == len(read)
    assert {name: os.lstat(name).st_ino for name in names} == before
    assert user_data.set_aside_notices()["awaiting"] is True
    read.clear()
    assert user_data.restore_set_aside() is False
    assert read == []


def test_one_restore_leaves_what_is_past_its_bound_for_a_later_press(monkeypatch, tmp_path):
    """Three valid files set aside and a bound of two a press: the first
    press brings two back and leaves the third untouched; the next brings
    it back."""
    zij = _private(_base(tmp_path) / "Zij")
    _launched(monkeypatch, zij)
    for n in range(3):
        aside = zij / f"{STORE}.set-aside-20000101-00000{n}"
        aside.write_text(json.dumps({f"Chart {n}": REC}))
        os.chmod(aside, 0o600)
    monkeypatch.setattr(user_data, "_LAUNCH_FILE_LIMIT", 2)
    assert user_data.restore_set_aside() is False
    assert sorted(user_data.load_saved_charts()) == ["Chart 0", "Chart 1"]
    assert [p.name for p in zij.iterdir() if ".set-aside-" in p.name] == [f"{STORE}.set-aside-20000101-000002"]
    assert user_data.restore_set_aside() is True
    assert sorted(user_data.load_saved_charts()) == ["Chart 0", "Chart 1", "Chart 2"]



def _reads_aside(monkeypatch):
    """Each file the restore reads, as (inode, bytes read); a refused read
    as (inode, 0)."""
    real = user_data._read_what_was_set_aside
    read = []

    def reading(path, limit, *args, **kwargs):
        try:
            data, opened = real(path, limit, *args, **kwargs)
        except OSError:
            read.append((os.lstat(path).st_ino, 0))
            raise
        read.append((opened.st_ino, len(data)))
        return data, opened
    monkeypatch.setattr(user_data, "_read_what_was_set_aside", reading)
    return read


def test_one_restore_reads_within_its_byte_bound_over_files_of_their_own(monkeypatch, tmp_path):
    """Eight files of their own set aside, each an invalid store of 2 MiB,
    and a bound of three such files' bytes a press: one press reads no
    more than the bound, and every file stays where it was."""
    zij = _private(_base(tmp_path) / "Zij")
    _launched(monkeypatch, zij)
    size = 2 * MIB
    names = [zij / f"{STORE}.set-aside-20000101-00000{n}" for n in range(8)]
    for name in names:
        with open(name, "wb") as f:
            f.truncate(size)                # sparse: no store
        os.chmod(name, 0o600)
    monkeypatch.setattr(user_data, "_LAUNCH_BYTE_LIMIT", 3 * size)
    read = _reads_aside(monkeypatch)
    before = {name: os.lstat(name).st_ino for name in names}
    assert user_data.restore_set_aside() is False
    assert read and sum(n for _ino, n in read) <= 3 * size
    assert {name: os.lstat(name).st_ino for name in names} == before


def test_one_restore_reads_a_file_reached_by_several_names_once(monkeypatch, tmp_path):
    """A store set aside under three recovery names, hard links to one
    file, and a file of its own set aside after them: one press reads the
    linked file once, brings its chart back and removes its other two
    names, unread; the file of its own, another file, is read and brought
    back too, not removed with them. Nothing is left set aside."""
    zij = _private(_base(tmp_path) / "Zij")
    _launched(monkeypatch, zij)
    first = zij / f"{STORE}.set-aside-20000101-000000"
    first.write_text(json.dumps({"Chart": REC}))
    os.chmod(first, 0o600)
    others = [zij / f"{STORE}.set-aside-20000101-00000{n}" for n in (1, 2)]
    for name in others:
        os.link(first, name)
    own = zij / f"{STORE}.set-aside-20000101-000003"
    own.write_text(json.dumps({"Other": REC}))
    os.chmod(own, 0o600)
    read = _reads_aside(monkeypatch)
    assert user_data.restore_set_aside() is True
    assert len(read) == 2 and len({ino for ino, _size in read}) == 2      # each file read once
    assert sorted(user_data.load_saved_charts()) == ["Chart", "Other"]
    assert [os.path.lexists(name) for name in [first, *others, own]] == [False, False, False, False]
    assert user_data.set_aside_notices()["awaiting"] is False


# --- Controls: as before, at both -----------------------------------------

def test_the_default_data_folder_with_a_private_store_is_read(monkeypatch, tmp_path):
    zij = _private(_base(tmp_path) / "Zij", OWN)
    _launched(monkeypatch, zij)
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN
    assert user_data.write_saved_charts({"Mine": REC, **OWN}) is True


@pytest.mark.parametrize("mode", [0o700, 0o755])
def test_a_data_folder_linked_through_the_users_closed_folders_is_read(monkeypatch, tmp_path, mode):
    base = _base(tmp_path)
    kept = _private(tmp_path / "kept", mode=mode)
    _private(kept / "Zij", OWN)
    os.symlink(kept / "Zij", base / "Zij")
    _launched(monkeypatch, base / "Zij")
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN
    assert user_data.write_saved_charts({"Mine": REC, **OWN}) is True
    assert sorted(json.loads((kept / "Zij" / STORE).read_text())) == ["Mine", "Old"]


def test_a_path_through_a_sticky_folder_whose_entry_is_the_users_is_read(monkeypatch, tmp_path):
    sticky = _private(tmp_path / "sticky", mode=0o777)
    os.chmod(sticky, 0o1777)
    _private(sticky / "mine" / "Zij", OWN)
    _launched(monkeypatch, sticky / "mine" / "Zij")
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN


def test_a_change_of_mode_taken_that_does_not_hold_is_a_disk_that_keeps_no_modes(monkeypatch, tmp_path):
    """The change taken but not kept (a disk that keeps no modes, stood in):
    the folder is taken as it is, as before."""
    zij = _private(_base(tmp_path) / "Zij", OWN, mode=0o777)
    os.chmod(zij / STORE, 0o666)
    real = os.chmod
    monkeypatch.setattr(os, "chmod", lambda path, mode, *a, **k: None if isinstance(path, int)
                        else real(path, mode, *a, **k))
    _launched(monkeypatch, zij)
    assert user_data._MODELESS != []
    assert user_data.load_saved_charts() == OWN


def test_a_store_its_group_and_others_may_only_read_is_left_and_read(monkeypatch, tmp_path):
    zij = _private(_base(tmp_path) / "Zij", OWN)
    os.chmod(zij / STORE, 0o644)
    _launched(monkeypatch, zij)
    assert user_data.load_saved_charts() == OWN
    assert user_data.set_aside_notices() == {**{k: False for k in user_data.set_aside_notices()}}


# --- The descriptor held, and let go -------------------------------------

def _descriptors():
    """How many descriptors this process holds open (each number below 4096
    asked with fstat: no listing of /proc, which not every system has)."""
    held = 0
    for fd in range(4096):
        try:
            os.fstat(fd)
        except OSError:
            continue
        held += 1
    return held


def test_one_folder_is_held_at_a_time_and_let_go(monkeypatch, tmp_path):
    """Each launch holds one descriptor, in the place of the one before; the
    module loaded again lets the one it held go."""
    before = _descriptors()
    for n in range(5):
        user_data._make_user_data_dir(_private(_base(tmp_path) / f"Zij{n}", OWN))
    assert _descriptors() == before + 1
    user_data._HELD[0].close()
    assert _descriptors() == before
    home = tmp_path / "child"
    code = ("import importlib, os, user_data\n"
            "def held():\n"
            "    n = 0\n"
            "    for fd in range(4096):\n"
            "        try:\n            os.fstat(fd)\n        except OSError:\n            continue\n"
            "        n += 1\n"
            "    return n\n"
            "n = held()\n"
            "for _ in range(3):\n    importlib.reload(user_data)\n"
            "print(n, held(), user_data._HELD[0] is not None)\n")
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "xdg"), APPDATA=str(home / "appdata"))
    _private(home)
    done = subprocess.run([sys.executable, "-c", code], cwd=Path(user_data.__file__).parent, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    first, last, held = done.stdout.split()
    assert first == last and held == "True"


def _held():
    return getattr(user_data, "_HELD", [None])[0]


def test_a_held_folder_removed_is_let_go_and_one_made_again_is_judged_and_held(monkeypatch, tmp_path):
    """The data folder removed while the app runs is said gone, as by its
    name, and nothing is read; a folder made at its name again is held
    before anything is read from it, and its store read."""
    zij = _private(_base(tmp_path) / "Zij", OWN)
    _launched(monkeypatch, zij)
    assert user_data.load_saved_charts() == OWN
    shutil.rmtree(zij)
    assert user_data.data_folder_state()[0] == 'found'
    assert user_data.load_saved_charts() == {}
    _private(zij, OTHER)
    assert user_data.load_saved_charts() == OTHER
    held = _held()
    assert held is not None and os.path.samestat(os.fstat(held.fd), os.stat(zij))
    assert user_data.data_folder_state() == (None, None)


def test_a_folder_made_again_through_a_folder_others_may_write_is_refused(monkeypatch, tmp_path):
    """The data folder removed, and the user's link put at its name, through
    a 0777 folder that is not sticky: judged as at a launch, and refused."""
    zij = _private(_base(tmp_path) / "Zij", OWN)
    _launched(monkeypatch, zij)
    shutil.rmtree(zij)
    shared = _private(tmp_path / "shared", mode=0o777)
    _private(shared / "private", OTHER)
    os.symlink(shared / "private", zij)
    assert user_data.load_saved_charts() == {}
    assert user_data.data_folder_state() == ('used', getattr(user_data, "DATA_FOLDER_PATH_OPEN", None))


def test_a_held_folder_renamed_aside_is_never_let_go(monkeypatch, tmp_path):
    """The data folder renamed aside and another folder of the user's made at
    its name: the folder held is still the one read and written, and the
    other is left as it was."""
    zij = _private(_base(tmp_path) / "Zij", OWN)
    _launched(monkeypatch, zij)
    os.rename(zij, zij.with_name("Zij-aside"))
    _private(zij, OTHER)
    before = _seen(zij / STORE)
    assert user_data.load_saved_charts() == OWN
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({"Mine": REC, **OWN}) is True
    assert _seen(zij / STORE) == before
    assert sorted(json.loads((zij.with_name("Zij-aside") / STORE).read_text())) == ["Mine", "Old"]


def test_every_file_in_the_folder_held_is_reached_through_its_descriptor(monkeypatch, tmp_path):
    """The store's read, its temporary file, its replace and the folder's
    listing are made relative to the descriptor held, never by the folder's
    name."""
    zij = _private(_base(tmp_path) / "Zij", OWN)
    _launched(monkeypatch, zij)
    held = user_data._HELD[0]
    assert held is not None and held.name == str(zij)
    assert user_data._in_the_held_folder(zij / STORE) == (held.fd, STORE)
    assert user_data._in_the_held_folder(zij) == (held.fd, ".")
    assert user_data._in_the_held_folder(tmp_path / STORE) == (None, tmp_path / STORE)
    by_name = []
    with pytest.MonkeyPatch.context() as spies:         # undone here; the launch's own patches at the end
        for name in ("open", "replace", "listdir", "unlink", "stat", "lstat"):
            real = getattr(os, name)

            def spy(*args, _real=real, _name=name, **kwargs):
                if args and isinstance(args[0], (str, Path)) and str(args[0]).startswith(str(zij)):
                    by_name.append((_name, str(args[0])))
                return _real(*args, **kwargs)
            spies.setattr(os, name, spy)
        assert user_data.load_saved_charts() == OWN
        with user_data.saved_charts_lock():
            assert user_data.write_saved_charts({"Mine": REC, **OWN}) is True
        assert user_data.set_aside_notices()["awaiting"] is False
    assert by_name == []


# --- The folder an older version used, reached through an open path ---

FORMER = "TraditionalAstrologyEngine"


def _former_through(tmp_path, base, swapped, mode=0o777):
    """The data folder's neighbour under the app's former name: the user's
    link to shared/old, a private folder of the user's holding OWN, with
    shared at `mode`. Where `swapped`, another account has renamed old
    aside and put in its place a link to a second private folder of the
    user's, holding another application's store. Returns that second
    folder and its store as first seen."""
    shared = _private(tmp_path / "shared", mode=mode)
    _private(shared / "old", OWN)
    second = _private(tmp_path / "otherapp", OTHER)
    os.symlink(shared / "old", base / FORMER)
    if swapped:
        os.rename(shared / "old", shared / "old-aside")              # the other account's move
        os.symlink(second, shared / "old")
    return second, _seen(second / STORE)


@pytest.mark.parametrize("swapped", [True, False], ids=["swapped", "as made"])
def test_a_former_folder_reached_through_a_folder_others_may_write_is_left_unread(monkeypatch, tmp_path, swapped):
    """The data folder stands, holding no store; beside it, the former
    name is the user's link through a 0777 folder that is not sticky. Its
    store is not read (neither the folder put in its place nor the user's
    own), nothing is written, the folder is said as a failed move is said,
    and the second store is untouched."""
    base = _base(tmp_path)
    zij = _private(base / "Zij")
    second, before = _former_through(tmp_path, base, swapped)
    _launched(monkeypatch, zij)
    assert user_data.load_saved_charts() == {}
    assert user_data.write_saved_charts({"Mine": REC}) is False
    assert user_data.data_folder_state() == ('used', getattr(user_data, "FORMER_FOLDER_NOT_COPIED", None))
    assert os.listdir(zij) == []
    assert _seen(second / STORE) == before
    assert os.path.islink(base / FORMER)


@pytest.mark.parametrize("swapped", [True, False], ids=["swapped", "as made"])
def test_the_former_folders_store_is_read_only_through_the_folder_its_walk_judged(monkeypatch, tmp_path, swapped):
    """As above, with the data folder's look made before the path was
    opened to others (stood in: the look says nothing is wrong). The read
    itself judges the path, and reads nothing through it."""
    base = _base(tmp_path)
    zij = _private(base / "Zij")
    second, before = _former_through(tmp_path, base, swapped)
    _launched(monkeypatch, zij)
    monkeypatch.setattr(user_data, "_former_folder_left_unread", lambda folder: False, raising=False)
    old = base / FORMER / STORE
    with pytest.raises(OSError):
        user_data._read_the_former_folders_store(old)
    assert user_data._the_first_old_store()[1] is None
    assert user_data.load_saved_charts() == {}
    assert user_data.write_saved_charts({"Mine": REC}) is True
    assert json.loads((zij / STORE).read_text()) == {"Mine": REC}
    assert _seen(second / STORE) == before


def test_a_former_folder_whose_path_others_may_write_is_left_where_it_is(monkeypatch, tmp_path):
    """No data folder yet: the former name a link through a 0777 folder,
    swapped. The launch moves nothing and reads nothing, and says the
    move failed, also where the look before the move is passed over
    (stood in): the move opens the former folder by the walk that judges
    its path."""
    base = _base(tmp_path)
    second, before = _former_through(tmp_path, base, swapped=True)
    zij = base / "Zij"
    assert type(_launched(monkeypatch, zij)).__name__ == "FormerFolderNotCopied"
    assert not os.path.lexists(zij) and os.path.islink(base / FORMER)
    monkeypatch.setattr(user_data, "_judge_the_former_folders_path", lambda legacy: None, raising=False)
    assert type(_launched(monkeypatch, zij)).__name__ == "FormerFolderNotCopied"
    assert not os.path.lexists(zij) and os.path.islink(base / FORMER)
    assert _seen(second / STORE) == before


def test_a_former_folder_linked_through_the_users_closed_folders_is_brought_in(monkeypatch, tmp_path):
    """The control: the same link through a 0700 folder of the user's is
    read, and its store brought in, as before."""
    base = _base(tmp_path)
    zij = _private(base / "Zij")
    _former_through(tmp_path, base, swapped=False, mode=0o700)
    _launched(monkeypatch, zij)
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN


def test_windows_a_former_folder_reached_through_a_folder_others_may_change_is_left_unread(monkeypatch, tmp_path):
    """Windows (stood in): the former name a link through a folder that
    gives another account a right over it. Its store is not read, at the
    look or at the read itself, and the folder is said as a failed move is
    said."""
    from test_windows_owner_and_link_2026_11_02 import _key
    win = _Windows(monkeypatch)
    base = _private(tmp_path / "appdata")
    zij = _private(base / "Zij")
    shared = _private(tmp_path / "shared")
    _private(shared / "old", OWN)
    os.symlink(shared / "old", base / FORMER)
    win.folder_open.add(_key(shared, False))
    _launched(monkeypatch, zij)
    assert user_data.load_saved_charts() == {}
    assert user_data.data_folder_state() == ('used', getattr(user_data, "FORMER_FOLDER_NOT_COPIED", None))
    monkeypatch.setattr(user_data, "_former_folder_left_unread", lambda folder: False, raising=False)
    assert user_data._the_first_old_store()[1] is None
    assert user_data.load_saved_charts() == {}


# --- A folder on the way whose access list gives another account write --

def _access_list_giving_write_to(uid):
    """The binary form of a POSIX access list (as Linux keeps it in the
    folder's system.posix_acl_access attribute) for mode 0755 with one
    named entry: `uid` may read, write and search; the mask rwx."""
    import struct
    undefined = 0xFFFFFFFF
    entries = [(0x01, 7, undefined), (0x02, 7, uid), (0x04, 5, undefined), (0x10, 7, undefined),
               (0x20, 5, undefined)]
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, perm, who) for tag, perm, who in entries)


def _swap_through(tmp_path, mid):
    """The swap of this file's first pin, through `mid`: the user's link at
    the data folder's name leads to mid/data, a private folder of the user's
    holding OWN; the account mid lets write renames data aside and puts in
    its place a link to a second private folder of the user's, holding
    another application's store."""
    _private(mid / "data", OWN)
    second = _private(tmp_path / "otherapp", OTHER)
    zij = _base(tmp_path) / "Zij"
    os.symlink(mid / "data", zij)
    os.rename(mid / "data", mid / "data-aside")
    os.symlink(second, mid / "data")
    return zij, second, _seen(second / STORE)


def test_a_folder_whose_access_list_gives_another_account_write_is_refused(monkeypatch, tmp_path):
    """A real access list, set where the filesystem takes one: a 0755
    folder of the user's on the way, whose list lets another account write
    in it (so its mode reads 0775, the group the user's own group of one).
    The swap is refused, nothing read, the second store untouched. Where no
    list can be set here (a filesystem that keeps none, or a sandbox that
    maps no other account), that is all this pin can show, and it says so;
    the stand-in below carries the case everywhere."""
    mid = _private(tmp_path / "mid", mode=0o755)
    try:
        os.setxattr(mid, "system.posix_acl_access", _access_list_giving_write_to(os.getuid() + 1))
    except (AttributeError, OSError) as exc:
        assert isinstance(exc, AttributeError) or exc.errno in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP,
                                                                 errno.EPERM), exc
        return
    assert stat.S_IMODE(os.stat(mid).st_mode) == 0o775
    monkeypatch.setattr(user_data, "_a_group_of_one", lambda gid: gid == os.stat(mid).st_gid, raising=False)
    zij, second, before = _swap_through(tmp_path, mid)
    _launched(monkeypatch, zij)
    _refused_with("DATA_FOLDER_PATH_OPEN")
    assert _seen(second / STORE) == before


def _attribute_read(monkeypatch, mid, answer):
    """Stand in for the reading of a folder's access list: for `mid`, the
    list itself (`answer` "a list"), no such attribute ("none"), a
    filesystem that keeps none ("not kept"), or another error ("an error");
    every other folder carries none."""
    target = _seen_key(mid)

    def getxattr(path, attribute, *, follow_symlinks=True):
        seen = os.fstat(path) if isinstance(path, int) else os.stat(path)
        if attribute != "system.posix_acl_access" or (seen.st_dev, seen.st_ino) != target or answer == "none":
            raise OSError(errno.ENODATA, os.strerror(errno.ENODATA), str(path))
        if answer == "not kept":
            raise OSError(errno.EOPNOTSUPP, os.strerror(errno.EOPNOTSUPP), str(path))
        if answer == "an error":
            raise OSError(errno.EIO, os.strerror(errno.EIO), str(path))
        return _access_list_giving_write_to(os.getuid() + 1)
    monkeypatch.setattr(os, "getxattr", getxattr, raising=False)


def _seen_key(path):
    seen = os.stat(path)
    return seen.st_dev, seen.st_ino


@pytest.mark.parametrize("answer, read", [("a list", False), ("an error", False), ("none", True),
                                          ("not kept", True)])
def test_a_group_writable_folder_counts_as_closed_only_where_it_carries_no_access_list(monkeypatch, tmp_path,
                                                                                     answer, read):
    """Stand-in, on every filesystem: a 0775 folder of the user's on the way,
    its group the user's own group of one, and its access list read as
    `answer`. A list, or a reading that fails, refuses the swap through it;
    no list, or a filesystem that keeps none, counts the folder closed, as
    the group of one does, and the folder the link now leads to is read."""
    mid = _private(tmp_path / "mid", mode=0o775)
    monkeypatch.setattr(user_data, "_a_group_of_one", lambda gid: gid == os.stat(mid).st_gid, raising=False)
    _attribute_read(monkeypatch, mid, answer)
    zij, second, before = _swap_through(tmp_path, mid)
    _launched(monkeypatch, zij)
    if read:
        assert user_data.data_folder_state() == (None, None)
        assert user_data.load_saved_charts() == OTHER
    else:
        _refused_with("DATA_FOLDER_PATH_OPEN")
        assert _seen(second / STORE) == before


# --- The owner a user namespace shows for the system's ------------------

OVERFLOW = 4242424          # an id no file here has: the overflow id the stand-in's kernel shows


def _namespace(monkeypatch, tmp_path, identity):
    """Stand in for the map the data layer reads of this process's user
    namespace: the identity (`identity`: the system's own namespace, as at
    any ordinary launch), or one that maps this account's id alone (a
    sandbox's), with OVERFLOW as the kernel's overflow id. A folder `mid`
    on the way is shown owned by OVERFLOW; every other owner but this
    account's is shown as root's, as the system's own namespace shows the
    folders above tmp_path (so that the verdict hangs on `mid` alone, in a
    sandbox too). Returns the data folder's name below `mid`."""
    me = os.getuid()
    rows = {"/proc/self/uid_map": "0 0 4294967295\n" if identity else f"{me} {me} 1\n",
            "/proc/sys/kernel/overflowuid": f"{OVERFLOW}\n"}
    real_open = open

    def map_read(file, *args, **kwargs):
        if file in rows:
            import io
            return io.StringIO(rows[file])
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(user_data, "open", map_read, raising=False)
    monkeypatch.setattr(user_data, "_UNMAPPED", [], raising=False)
    mid = _private(tmp_path / "mid", mode=0o755)
    _private(mid / "Zij", OWN)
    key = _seen_key(mid)
    real_fstat = os.fstat

    def fstat_as(fd):
        seen = real_fstat(fd)
        uid = OVERFLOW if (seen.st_dev, seen.st_ino) == key else seen.st_uid if seen.st_uid == me else 0
        if uid == seen.st_uid:
            return seen
        fields = list(seen)
        fields[stat.ST_UID] = uid
        return os.stat_result(fields)
    monkeypatch.setattr(os, "fstat", fstat_as)
    return mid / "Zij"


def test_inside_a_namespace_that_maps_no_system_id_the_overflow_owner_counts_as_the_systems(monkeypatch, tmp_path):
    """Inside a user namespace whose map is not the identity, and leaves
    the overflow id unmapped, a folder on the way shown owned by that id is
    taken for the system's: the data folder below it is read."""
    zij = _namespace(monkeypatch, tmp_path, identity=False)
    _launched(monkeypatch, zij)
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == OWN


def test_with_the_identity_map_a_folder_of_the_overflow_id_on_the_way_is_refused(monkeypatch, tmp_path):
    """With the identity map (any ordinary launch), the overflow id is an
    account like any other (often `nobody`): a folder of its on the way
    refuses the data folder below it."""
    zij = _namespace(monkeypatch, tmp_path, identity=True)
    _launched(monkeypatch, zij)
    _refused_with("DATA_FOLDER_PATH_OPEN")


# --- A held folder's listing on a filesystem whose kept descriptor lags ---

def _a_lagging_listing(monkeypatch, zij):
    """The held descriptor listed as Btrfs lists a folder's descriptor kept
    open: the names as they stood when it was last rewound to its start,
    not as they stand. Any other listing is the system's own."""
    held = user_data._HELD[0]
    real_listdir, real_lseek = os.listdir, os.lseek
    seen = [real_listdir(zij)]

    def lseek(fd, pos, how):
        if fd == held.fd and pos == 0 and how == os.SEEK_SET:
            seen[0] = real_listdir(zij)
        return real_lseek(fd, pos, how)

    def listdir(path="."):
        return list(seen[0]) if path == held.fd else real_listdir(path)
    monkeypatch.setattr(os, "lseek", lseek)
    monkeypatch.setattr(os, "listdir", listdir)


def test_the_folder_held_is_listed_as_it_stands_where_a_kept_descriptor_lags(monkeypatch, tmp_path):
    """A file made in the folder held after the launch is in its listing,
    and twelve saves keep the newest ten versions, where the descriptor
    held lists the folder as it stood when last rewound."""
    zij = _private(_base(tmp_path) / "Zij")
    _launched(monkeypatch, zij)
    _a_lagging_listing(monkeypatch, zij)
    (zij / "made-after-the-launch").write_bytes(b"")
    assert "made-after-the-launch" in user_data._listdir(zij)
    for n in range(1, 13):
        charts = {f"Chart {i}": dict(REC, date_string=f"19{10 + i:02d}-01-01") for i in range(n)}
        assert user_data.write_saved_charts(charts) is True
    versions = sorted(p for p in os.listdir(zij) if p.startswith(STORE + ".previous-"))
    assert len(versions) == user_data.VERSIONS_KEPT, versions
    assert not versions[0].endswith("-001"), "the oldest version was not removed"
