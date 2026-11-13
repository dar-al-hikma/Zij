# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""A save cut short that another account could change is set aside unread;
the writers make no file wider than its owner's; the set-aside's own guards.

An older version under umask 000 made the data folder 0777 and its files
0666. The launch replaced each such file with a private copy of its bytes,
which the next load read as the user's; the files the app reads are now set
aside at the launch, unread, and restored only at the user's word
(test_set_aside_at_launch_2026_11_11). What is pinned here is what stands
beside that: a stray of a save cut short that others could change, judged at
its name and as opened, is set aside unread as well, and counted with the
strays kept aside; no file the app makes carries a group or other bit; and a
file put at the name, a fchmod refused or a umask that takes the owner's
read bit leave nothing read that should not be.

Run natively on POSIX: real modes. Windows is stood in (_Windows), its access
list answered by a seam. Every file a test makes lies under tmp_path."""
import json
import os
import stat
from pathlib import Path

import pytest

import user_data
from test_windows_owner_and_link_2026_11_02 import INJECTED, REC, _Windows, _base, _key, _launched

STORE, PREFS = "saved_charts.json", "preferences.json"
OWN = {"Old": REC}


def _names(path, called, dir_fd=None):
    """Whether a system call given `called` (and `dir_fd`) names `path`: by
    its path, or by its name relative to a descriptor of its folder (a file
    in the data folder the launch holds is reached so)."""
    if dir_fd is None:
        return Path(called) == Path(path)
    return (os.fspath(called) == Path(path).name
            and os.path.samestat(os.fstat(dir_fd), os.stat(Path(path).parent)))


def _mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def _inode(path):
    return os.lstat(path).st_ino


def _kept(folder, mode_of_files, mode_of_folder):
    """The user's own store and preferences in `folder`, at the modes an
    older version's umask gave them."""
    folder.mkdir(exist_ok=True)
    (folder / STORE).write_text(json.dumps(OWN, indent=2))
    (folder / PREFS).write_text(json.dumps({"last_chart": "Old"}))
    for name in (STORE, PREFS):
        os.chmod(folder / name, mode_of_files)
    os.chmod(folder, mode_of_folder)


def test_a_save_under_umask_000_makes_every_file_owner_only(monkeypatch, tmp_path):
    """The store's writer, its version and the preferences' writer carry
    the owner's part of the mode alone: a store widened after the launch is
    not made 0666 again by a save, nor is its version; and the widened store
    is not read for a version."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    assert _launched(monkeypatch, target) is None
    for each in (STORE, PREFS):
        os.chmod(target / each, 0o666)
    old = os.umask(0)
    try:
        with user_data.saved_charts_lock():
            assert user_data.write_saved_charts({**OWN, "New": REC}) is True
            assert user_data.write_saved_charts({**OWN, "Newer": REC}) is True
        assert user_data.write_preferences({"last_chart": "New"}) is True
    finally:
        os.umask(old)
    made = sorted(p.name for p in target.iterdir())
    # the store widened was not read, so no version of it was kept; the next write's version was
    assert [n for n in made if n.startswith(STORE + ".previous-")] and len(made) == 3, made
    assert {n: _mode(target / n) for n in made} == {n: 0o600 for n in made}


# A save cut short leaves its temporary file, which the first load keeps
# aside in a private copy and removes; one another account could change is
# set aside unread instead, under a recovery name of its own, and counted
# with the strays kept aside, which the page says.

def _a_stray(folder, name, mode):
    stray = folder / name
    stray.write_text(json.dumps({"Injected": INJECTED}, indent=2))
    os.chmod(stray, mode)
    past = user_data._LAUNCHED_AT - 60
    os.utime(stray, (past, past))
    return stray


def _strays_aside(folder, stray):
    return [p for p in folder.iterdir() if p.name.startswith(stray.name + ".set-aside-")]


@pytest.mark.parametrize("name", [STORE + ".0123456789abcdef.tmp", STORE + ".tmp"], ids=["temp", "former temp"])
@pytest.mark.parametrize("mode, wide", [(0o666, True), (0o646, True), (0o660, True), (0o644, False)],
                         ids=["0666", "0646", "0660", "0644"])
def test_a_cut_short_save_others_could_change_is_set_aside_unread(monkeypatch, tmp_path, name, mode, wide):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    stray = _a_stray(target, name, mode)
    inode = _inode(stray)

    assert _launched(monkeypatch, target) is None
    assert _mode(stray) == mode                                     # left at the launch, for the load
    assert user_data.load_saved_charts() == OWN
    assert user_data.store_notices()["recovered"] == 1
    assert not stray.exists()
    copies = [p for p in target.iterdir() if ".recovered-" in p.name]
    aside = _strays_aside(target, stray)
    if wide:
        assert copies == [] and len(aside) == 1 and _inode(aside[0]) == inode and _mode(aside[0]) == 0o600
    else:
        assert aside == [] and len(copies) == 1 and _mode(copies[0]) == 0o600


def test_a_cut_short_save_judged_fine_by_its_name_but_wide_as_opened_is_not_read(monkeypatch, tmp_path):
    """Listed at 0600, made 0666 before it is opened: judged again as
    opened, and not read."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    stray = _a_stray(target, STORE + ".0123456789abcdef.tmp", 0o600)
    assert _launched(monkeypatch, target) is None
    real = os.open

    def opening(path, flags, *args, **kwargs):
        if _names(stray, path, kwargs.get("dir_fd")):
            os.chmod(stray, 0o666)
        return real(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", opening)
    assert user_data.load_saved_charts() == OWN
    monkeypatch.setattr(os, "open", real)
    assert not stray.exists() and len(_strays_aside(target, stray)) == 1
    assert [p for p in target.iterdir() if ".recovered-" in p.name] == []


@pytest.mark.parametrize("wide", [True, False], ids=["its list lets others write", "it does not"])
def test_windows_asks_the_list_of_a_cut_short_save(monkeypatch, tmp_path, wide):
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o600, 0o700)
    stray = _a_stray(target, STORE + ".0123456789abcdef.tmp", 0o600)
    win = _Windows(monkeypatch)
    key = _key(stray)
    if wide:
        win.write_wide.add(key)

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == OWN
    assert key in win.write_asked and not stray.exists()
    assert user_data.store_notices()["recovered"] == 1
    assert bool(_strays_aside(target, stray)) is wide


# The set-aside's own guards, each pinned.

def test_a_file_put_at_the_name_before_the_move_is_neither_moved_nor_read_over(monkeypatch, tmp_path):
    """Between the look and the rename the name comes to hold another
    file of the user's (another window's save): it is not moved aside, and it
    is what the load reads."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    os.chmod(target / PREFS, 0o600)                                 # the store alone is to be set aside
    newer = json.dumps({**OWN, "New": REC}, indent=2)
    real = user_data._recovery_stamp

    def stamping():
        if (target / STORE).exists() and _mode(target / STORE) == 0o666:
            beside = target / "newer.json"
            beside.write_text(newer)
            os.chmod(beside, 0o600)
            os.replace(beside, target / STORE)
        return real()
    monkeypatch.setattr(user_data, "_recovery_stamp", stamping)

    assert _launched(monkeypatch, target) is None
    monkeypatch.setattr(user_data, "_recovery_stamp", real)
    assert (target / STORE).read_text() == newer and _mode(target / STORE) == 0o600
    assert sorted(p.name for p in target.iterdir()) == [PREFS, STORE]
    assert user_data.load_saved_charts() == {**OWN, "New": REC}
    assert user_data.set_aside_notices() == {"awaiting": False, "unfollowed": False, "held": False}


def test_a_file_set_aside_whose_0600_is_refused_is_still_set_aside_and_unread(monkeypatch, tmp_path):
    """A filesystem that sets modes for itself refuses the fchmod: the
    file is set aside all the same, and nothing of it is read."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    inode = _inode(target / STORE)

    def refused(fd, mode):
        raise PermissionError(1, "not permitted")
    monkeypatch.setattr(os, "fchmod", refused)
    assert _launched(monkeypatch, target) is None
    monkeypatch.undo()
    [aside] = [p for p in target.iterdir() if p.name.startswith(STORE + ".set-aside-")]
    assert (_inode(aside), _mode(aside)) == (inode, 0o666) and not (target / STORE).exists()


def test_a_file_set_aside_and_restored_under_a_umask_that_cuts_the_owner_s_reading_is_read_back(monkeypatch,
                                                                                               tmp_path):
    """Under umask 0444 a file made at 0600 comes out 0200: the set-aside
    file is given 0600 itself (fchmod is not cut), and the restored store
    too, so the owner can read it."""
    base, _legacy, target = _base(tmp_path)
    _kept(target, 0o666, 0o700)
    old = os.umask(0o444)
    try:
        assert _launched(monkeypatch, target) is None
        assert user_data.restore_set_aside() is True
    finally:
        os.umask(old)
    assert _mode(target / STORE) == 0o600
    assert user_data.load_saved_charts() == OWN
