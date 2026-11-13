"""The last versions of the saved charts, kept before each write over them.

Before a write replaces the store, its bytes are kept beside it in the data
folder as `saved_charts.json.previous-<UTC YYYYMMDD-HHMMSS>-<nnn>`, when they
differ from the newest version kept; the newest ten are kept. A valid but
empty store written over a good one can then be undone by hand. A version
that cannot be kept costs the save nothing. Only names of exactly the form
are versions: nothing else is read or removed as one, and no other part of
the data layer takes a version for a stray, a lock or an unreadable copy.

Every test works in a data folder of its own under the test's tmp_path, set
through the harness's environment sync; none reaches a real one.
"""
import errno
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

import user_data
from conftest import sync_engine_to_environment

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
VERSION = re.compile(r"saved_charts\.json\.previous-[0-9]{8}-[0-9]{6}-[0-9]{3,}")
A_SECOND = 1_700_000_000                            # 2023-11-14 22:13:20 UTC


def _stop_the_clock(monkeypatch, at):
    """The data layer's clock, stopped at the Unix time `at`."""
    class Stopped(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(at, timezone.utc).astimezone(tz)
    monkeypatch.setattr(user_data, "datetime", Stopped)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The store's path, in a disposable data folder; preferences off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    sync_engine_to_environment()
    import engine                                   # noqa: F401  (the sync reloads the data layer with it)
    sync_engine_to_environment()
    path = user_data.SAVED_CHARTS_PATH
    assert Path(path).resolve().is_relative_to(tmp_path.resolve()), path
    assert not path.exists()
    return path


def _versions(path):
    """The version files beside the store -- regular files of the form --
    oldest first, by their names."""
    return sorted((p for p in path.parent.iterdir() if VERSION.fullmatch(p.name) and stat.S_ISREG(p.lstat().st_mode)),
                  key=lambda p: _key(p.name))


def _key(name):
    stamp, count = name.rsplit("-", 1)
    return stamp, int(count)


def _charts(n):
    return {f"Chart {i}": dict(REC, date_string=f"19{10 + i:02d}-01-01") for i in range(n)}


def _write(charts):
    assert user_data.write_saved_charts(charts) is True
    return user_data.SAVED_CHARTS_PATH.read_bytes()


def test_charts_written_over_by_an_empty_store_are_in_the_newest_version(store):
    good = _write(_charts(3))
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts({}) is True
    assert json.loads(store.read_bytes()) == {}
    versions = _versions(store)
    assert versions, sorted(p.name for p in store.parent.iterdir())
    assert versions[-1].read_bytes() == good, "the charts written over are not in the newest version"
    assert json.loads(versions[-1].read_bytes()) == _charts(3)


def test_no_store_yet_keeps_no_version(store):
    first = _write(_charts(1))
    assert _versions(store) == []
    assert sorted(p.name for p in store.parent.iterdir()) == ["saved_charts.json"]
    _write(_charts(2))
    assert [p.read_bytes() for p in _versions(store)] == [first], "the premise: a store there is kept"


def test_identical_writes_keep_one_version(store):
    first = _write(_charts(2))
    for _ in range(5):
        _write(_charts(2))
    assert [p.read_bytes() for p in _versions(store)] == [first]


def test_repeated_empty_writes_never_push_a_good_version_out(store):
    good = _write(_charts(4))
    for _ in range(user_data.VERSIONS_KEPT + 3):
        _write({})
    kept = [p.read_bytes() for p in _versions(store)]
    assert good in kept, "a run of empty writes pushed the good version out"
    assert len(kept) == 2, kept                     # the good store, then one empty one


def test_eleven_distinct_writes_keep_ten_and_the_oldest_goes(store):
    assert user_data.VERSIONS_KEPT == 10
    written = [_write(_charts(n)) for n in range(1, 13)]   # the first finds no store: eleven versions made
    kept = [p.read_bytes() for p in _versions(store)]
    assert kept == written[1:11], [json.loads(b) and len(json.loads(b)) for b in kept]
    assert written[0] not in kept, "the oldest version was not removed"


def test_two_writes_in_one_second_keep_two(store, monkeypatch):
    _stop_the_clock(monkeypatch, A_SECOND)
    first = _write(_charts(1))
    second = _write(_charts(2))
    _write(_charts(3))
    versions = _versions(store)
    assert [p.name for p in versions] == ["saved_charts.json.previous-20231114-221320-001",
                                          "saved_charts.json.previous-20231114-221320-002"]
    assert [p.read_bytes() for p in versions] == [first, second]


def test_a_clock_set_back_still_names_the_new_version_newest(store, monkeypatch):
    _stop_the_clock(monkeypatch, A_SECOND)
    _write(_charts(1))
    second = _write(_charts(2))
    _stop_the_clock(monkeypatch, 1_600_000_000)    # three years back
    _write(_charts(3))
    newest = _versions(store)[-1]
    assert newest.read_bytes() == second
    assert newest.name == "saved_charts.json.previous-20231114-221320-002", newest.name


def test_many_writes_in_one_second_sort_by_their_count(store, monkeypatch):
    """Past 999 in one second the count's letters no longer sort: the age is
    read from its number."""
    _stop_the_clock(monkeypatch, A_SECOND)
    stamp = "20231114-221320"
    (store.parent / f"saved_charts.json.previous-{stamp}-999").write_text("{}")
    _write(_charts(1))
    newest = _write(_charts(2))
    names = [p.name for p in _versions(store)]
    assert names[-1] == f"saved_charts.json.previous-{stamp}-1000", names
    assert (store.parent / names[-1]).read_bytes() == _charts_bytes(1)
    assert store.read_bytes() == newest


def _charts_bytes(n):
    return user_data._saved_charts_text(_charts(n)).encode("utf-8")


def test_a_version_is_never_written_over(store, monkeypatch, tmp_path):
    """A name already taken -- by a file that is no version's bytes, or by
    anything at all -- is passed over for the next count. Nothing at a taken
    name is removed to make room: a folder, a link to nothing and a link to
    a file outside the data folder each still stand, the file untouched."""
    _stop_the_clock(monkeypatch, A_SECOND)
    _write(_charts(1))
    name = "saved_charts.json.previous-20231114-221320-{:03d}"
    taken = store.parent / name.format(1)
    taken.mkdir()                                   # not a regular file: no version, but its name is taken
    dangling = store.parent / name.format(2)
    dangling.symlink_to(tmp_path / "nothing here")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"not the data folder's")
    linked = store.parent / name.format(3)
    linked.symlink_to(outside)
    _write(_charts(2))
    assert taken.is_dir()
    assert dangling.is_symlink() and os.readlink(dangling) == str(tmp_path / "nothing here")
    assert not dangling.exists()
    assert linked.is_symlink() and os.readlink(linked) == str(outside)
    assert outside.read_bytes() == b"not the data folder's"
    assert [p.name for p in _versions(store)] == [name.format(4)]
    assert (store.parent / name.format(4)).read_bytes() == _charts_bytes(1)


def test_a_version_that_cannot_be_written_costs_the_save_nothing(store, monkeypatch):
    _write(_charts(1))
    made = user_data._new_temp_file

    def refuse(target, mode=0o600):
        if ".previous" in Path(target).name:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), str(target))
        return made(target, mode)

    with monkeypatch.context() as patch:
        patch.setattr(user_data, "_new_temp_file", refuse)
        assert user_data.write_saved_charts(_charts(2)) is True, "a version not kept cost the save"
    assert store.read_bytes() == _charts_bytes(2)
    assert _versions(store) == []
    assert not [p.name for p in store.parent.iterdir() if p.name.endswith(".tmp")]
    _write(_charts(3))
    assert [p.read_bytes() for p in _versions(store)] == [_charts_bytes(2)], "the next write kept no version"


def test_a_name_refused_costs_the_save_nothing(store, monkeypatch):
    _write(_charts(1))

    def refuse(*_a, **_k):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    monkeypatch.setattr(user_data, "_new_version", refuse)
    assert user_data.write_saved_charts(_charts(2)) is True
    assert store.read_bytes() == _charts_bytes(2)


def test_a_folder_that_cannot_be_listed_is_not_written_in(store, monkeypatch):
    """A folder its owner cannot list fails closed: none of its files can be
    judged for another account's changes, so nothing is written in it. The
    launch holds the data folder open, and lists it through that descriptor:
    one narrowed to 0300 after the launch is still listed, and written in;
    one whose listing is refused even so is not written in."""
    _write(_charts(1))
    folder = store.parent
    folder.chmod(0o300)
    try:
        assert user_data.write_saved_charts(_charts(2)) is True
    finally:
        folder.chmod(0o700)
    assert store.read_bytes() == _charts_bytes(2)
    assert [p.read_bytes() for p in _versions(store)] == [_charts_bytes(1)]
    real = os.listdir

    def listing(path="."):
        if (os.path.samestat(os.fstat(path), os.stat(folder)) if isinstance(path, int)
                else os.path.realpath(path) == os.path.realpath(folder)):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real(path)
    monkeypatch.setattr(os, "listdir", listing)
    assert user_data.write_saved_charts(_charts(3)) is False
    monkeypatch.setattr(os, "listdir", real)
    assert store.read_bytes() == _charts_bytes(2)
    assert [p.read_bytes() for p in _versions(store)] == [_charts_bytes(1)]


def test_without_hard_links_the_version_is_still_kept(store, monkeypatch, tmp_path):
    """The name is asked free and the file renamed to it; a link to nothing
    at the next name takes that name, and is passed over, not replaced."""
    _stop_the_clock(monkeypatch, A_SECOND)
    first = _write(_charts(1))
    name = "saved_charts.json.previous-20231114-221320-{:03d}"
    dangling = store.parent / name.format(1)
    dangling.symlink_to(tmp_path / "nothing here")

    def no_links(*_a, **_k):
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

    monkeypatch.setattr(os, "link", no_links)
    _write(_charts(2))
    assert dangling.is_symlink() and os.readlink(dangling) == str(tmp_path / "nothing here")
    assert [p.name for p in _versions(store)] == [name.format(2)]
    assert [p.read_bytes() for p in _versions(store)] == [first]
    assert not [p.name for p in store.parent.iterdir() if p.name.endswith(".tmp")]


def test_a_name_like_a_version_but_not_of_its_form_is_never_removed(store, monkeypatch):
    alike = ["saved_charts.json.previous-20000101-000000-001.bak", "saved_charts.json.previous-",
             "saved_charts.json.previous-20000101-000000", "saved_charts.json.previous-20000101-000000-01",
             "saved_charts.json.previous-2000010a-000000-001", "saved_charts.json.previous-keep",
             "saved_charts.json.previous-٢٠٠٠٠١٠١-000000-001",
             "xsaved_charts.json.previous-20000101-000000-001",
             "saved_charts.json.previous.0123456789abcdef.tmp.keep"]
    assert len(alike) == 9
    for name in alike:
        (store.parent / name).write_text(name)
    linked = store.parent / "saved_charts.json.previous-20000101-000000-002"
    linked.symlink_to(store.parent / alike[0])      # of the form, but a link: not a version
    for n in range(1, 14):
        _write(_charts(n))
    assert len(_versions(store)) == user_data.VERSIONS_KEPT
    for name in alike:
        assert (store.parent / name).read_text() == name, f"{name!r} was removed or written over"
    assert linked.is_symlink()


@pytest.mark.parametrize("mode", [0o600, 0o644, 0o400])
def test_the_version_takes_the_stores_mode_and_is_never_wider(store, mode):
    """As the store's own temporary file does, whatever the umask; a
    read-only one is still removed in its turn."""
    _write(_charts(1))
    store.chmod(mode)
    old = os.umask(0o077)
    try:
        _write(_charts(2))
    finally:
        os.umask(old)
    [version] = _versions(store)
    assert stat.S_IMODE(version.stat().st_mode) == mode & 0o700         # the owner's part alone
    assert stat.S_IMODE(store.stat().st_mode) == mode & 0o700
    for n in range(3, 15):
        store.chmod(0o600)
        _write(_charts(n))
    assert not version.exists(), "a read-only version was never removed"
    assert len(_versions(store)) == user_data.VERSIONS_KEPT


def test_a_store_kept_as_a_link_is_neither_written_nor_versioned(store, tmp_path):
    """A store kept as a link was written through it, and versioned in the
    data folder. A link at the store's name is now never followed: nothing
    is written through it, and no version is kept of the file it names."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = elsewhere / "charts.json"
    target.write_text(json.dumps(_charts(1), indent=2))
    store.symlink_to(target)
    before = target.read_bytes()
    assert user_data.write_saved_charts({}) is False
    assert store.is_symlink() and target.read_bytes() == before
    assert _versions(store) == []
    assert sorted(p.name for p in elsewhere.iterdir()) == ["charts.json"]


class _Killed(BaseException):
    """The process's end, between a write's temporary file and its replace."""


def test_a_write_killed_after_its_version_leaves_the_version_and_the_store(store, monkeypatch):
    """The version is kept, then the write is killed before its replace: the
    store holds what it held, the version holds the same, and the next
    load keeps the killed write's own temporary file aside as a save cut
    short, as before, and leaves the version alone."""
    good = _write(_charts(2))

    def killed(*_a, **_k):
        raise _Killed()

    monkeypatch.setattr(os, "replace", killed)
    with pytest.raises(_Killed):
        user_data.write_saved_charts({})
    monkeypatch.undo()
    monkeypatch.setenv("XDG_DATA_HOME", str(store.parent.parent))
    monkeypatch.setenv("ALMUTEN_NO_PREFERENCES", "1")
    assert store.read_bytes() == good
    [version] = _versions(store)
    assert version.read_bytes() == good
    strays = [p for p in store.parent.iterdir() if re.fullmatch(r"saved_charts\.json\.[0-9a-f]{16}\.tmp", p.name)]
    assert len(strays) == 1, sorted(p.name for p in store.parent.iterdir())
    past = user_data._LAUNCHED_AT - 60
    os.utime(strays[0], (past, past))
    assert user_data.load_saved_charts() == _charts(2)
    notices = user_data.store_notices()
    assert notices["recovered"] == 1 and not notices["unreadable"] and notices["copy"] is None, notices
    assert not strays[0].exists()
    recovered = list(store.parent.glob("saved_charts.json.recovered-*"))
    assert [json.loads(p.read_bytes()) for p in recovered] == [{}]
    assert _versions(store) == [version] and version.read_bytes() == good
    assert store.read_bytes() == good


def test_a_versions_own_temporary_file_left_by_a_killed_write_is_tidied(store):
    """One made before this launch is removed at the next version kept; one
    of this launch's may be another's in flight, and is left. Neither is
    taken for a save cut short by a load."""
    _write(_charts(1))
    dead = store.parent / "saved_charts.json.previous.0123456789abcdef.tmp"
    live = store.parent / "saved_charts.json.previous.fedcba9876543210.tmp"
    dead.write_bytes(_charts_bytes(1))
    live.write_bytes(_charts_bytes(1))
    past = user_data._LAUNCHED_AT - 60
    os.utime(dead, (past, past))
    assert user_data.load_saved_charts() == _charts(1)
    assert user_data.store_notices()["recovered"] == 0
    assert dead.exists() and live.exists()
    _write(_charts(2))
    assert not dead.exists() and live.exists()


def test_a_version_is_never_loaded_nor_taken_for_a_stray_or_an_unreadable_copy(store):
    _write(_charts(1))
    _write(_charts(2))
    _write(_charts(3))
    versions = {p.name: p.read_bytes() for p in _versions(store)}
    assert len(versions) == 2
    for p in _versions(store):
        os.utime(p, (user_data._LAUNCHED_AT - 60,) * 2)
    assert user_data.load_saved_charts() == _charts(3)
    notices = user_data.store_notices()
    assert notices["recovered"] == 0 and notices["copy"] is None and not notices["unreadable"], notices
    store.write_text("{not json")
    assert user_data.load_saved_charts() == {}
    copy = user_data.store_notices()["copy"]
    assert copy and copy.startswith("saved_charts.json.unreadable-"), copy
    assert (store.parent / copy).read_text() == "{not json"
    assert len(_versions(store)) == 2
    assert all((store.parent / name).read_bytes() == data for name, data in versions.items()), "a version moved"
    assert not list(store.parent.glob("saved_charts.json.recovered-*"))
    with user_data.saved_charts_lock():
        assert sorted(p.name for p in store.parent.iterdir() if "lock" in p.name) == ["saved_charts.lock"]
    assert not [p for p in store.parent.iterdir() if "lock" in p.name]


def test_the_version_is_on_the_disk_before_the_store_is_replaced(store, monkeypatch):
    """Its bytes synced and its name given before the store's own temporary
    file is synced and put in place."""
    good = _write(_charts(2))
    log = []
    real_fsync, real_link, real_replace = os.fsync, os.link, os.replace

    def fsync(fd):
        log.append(("fsync", os.fstat(fd).st_ino))
        return real_fsync(fd)

    def link(src, dst, *a, **k):
        log.append(("link", Path(dst).name))
        return real_link(src, dst, *a, **k)

    def replace(src, dst, *a, **k):
        log.append(("replace", Path(dst).name))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(os, "replace", replace)
    assert user_data.write_saved_charts({}) is True
    [version] = _versions(store)
    assert version.read_bytes() == good
    named, replaced = log.index(("link", version.name)), log.index(("replace", "saved_charts.json"))
    synced = log.index(("fsync", version.stat().st_ino))
    assert synced < named < replaced, log
    assert [e for e in log if e[0] == "fsync"][0] == ("fsync", version.stat().st_ino), log
