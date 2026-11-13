"""The data folder on Windows, and a link at its name on every platform.

On Windows the data folder and the folder an older version kept the charts
in were judged by their names alone: no owner was read, so a folder another
account put at either name was taken as the user's own. Their owners are now
read through the system's security calls; the user, Administrators and
SYSTEM are accepted, any other owner is refused as POSIX refuses it, and an
owner the user is denied the reading of is refused too. The data folder is
given a protected access list when it is made, and a wider one of the
user's is narrowed at each launch, as is one of Administrators' or SYSTEM's
whose list grants the user's own SID nothing (a run as administrator's),
and the folder a copy by name is made in before anything is copied. A link at the data folder's name is
judged by its own owner before it is followed, and the former name's link by
its own owner at every look; an earlier version's dead copy of the former
folder is compared only where it is this account's and no other account can
write in it or in anything in it.

Here the Windows calls are stood in on POSIX, one seam per call
(_windows_owner, _windows_this_account, _windows_list_is_wider,
_windows_file_is_writable_by_others, _windows_reset_the_list,
_windows_list_names_this_account, _windows_close_the_list, and the owner of a
file as opened, _windows_owner_of_the_open). The same scenes run natively, against a second
account, in tests/windows_data_folder_check.py, which the Windows workflow
runs and pytest never collects."""
import errno
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

import user_data
from conftest import EXECUTABLE_DIR

# Each test's launches leave no held data folder open (conftest).
pytestmark = pytest.mark.usefixtures("the_data_folder_held_is_let_go")

WORKFLOW = EXECUTABLE_DIR / ".github" / "workflows" / "windows-data-folder.yml"
NATIVE = "tests/windows_data_folder_check.py"


# =============================================================================
# The native run
# =============================================================================

def _workflow():
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_native_check_is_run_by_the_windows_workflow_and_never_collected():
    """The check is a script the workflow runs on GitHub's Windows runner;
    its name is not a test's, so the suite here neither collects nor skips
    it."""
    assert (EXECUTABLE_DIR / NATIVE).is_file()
    assert not Path(NATIVE).name.startswith("test_") and not Path(NATIVE).stem.endswith("_test")
    assert re.search(r"^\s+run: python " + re.escape(NATIVE) + r"\s*$", _workflow(), re.M)


def test_the_windows_workflow_runs_where_the_data_layer_changes_and_by_hand():
    """On a pull request that changes the data layer, the check or the
    workflow, with no branch named, so once per push to it; on a push to main
    alone that changes them (a push to a pull request's branch would run it
    twice); and by hand."""
    text = _workflow()
    blocks = {}
    for event in ("push", "pull_request"):
        block = re.search(r"^  " + event + r":\n((?:    .*\n)+)", text, re.M)
        assert block, event
        blocks[event] = block.group(1)
        paths = re.findall(r"^      - (\S+)$", block.group(1), re.M)
        assert sorted(paths) == sorted(["user_data.py", NATIVE, ".github/workflows/windows-data-folder.yml"]), paths
    assert re.findall(r"^    branches:.*$", blocks["push"], re.M) == ["    branches: [main]"], blocks["push"]
    assert "branches" not in blocks["pull_request"]
    assert re.search(r"^  workflow_dispatch:\s*$", text, re.M)


def test_the_windows_workflow_holds_a_read_only_token_and_pinned_parts():
    text = _workflow()
    assert re.search(r"^permissions: \{\}$", text, re.M)
    assert re.findall(r"^\s+permissions:\n\s+contents: read$", text, re.M)
    assert "write" not in re.sub(r"#.*", "", text)
    assert "secrets." not in text and "GITHUB_TOKEN" not in text
    assert re.search(r"^    runs-on: windows-2025-vs2026$", text, re.M)
    assert "python-version: '3.14.8'" in text
    uses = re.findall(r"uses: (\S+)", text)
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses
    assert "persist-credentials: false" in text
    assert "pip install" not in text


# =============================================================================
# Windows stood in: one seam per security call
# =============================================================================

REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
INJECTED = {"date_string": "1900-01-01", "time_string": "00:00:00", "time_standard": "LMT (Local Mean Time)",
            "location_query": "Elsewhere", "lat": 0.0, "lon": 0.0}
LEGACY = "TraditionalAstrologyEngine"
USER_SID = "S-1-5-21-1000000001-1000000002-1000000003-1001"
OTHER_SID = "S-1-5-21-1000000001-1000000002-1000000003-1002"
ADMINISTRATORS, SYSTEM = "S-1-5-32-544", "S-1-5-18"
DENIED = object()
_REAL = {name: getattr(os, name) for name in ("stat", "lstat", "fstat")}


def _key(path, follow=True):
    look = _REAL["stat"] if follow else _REAL["lstat"]
    seen = look(path)
    return seen.st_dev, seen.st_ino


class _Windows:
    """Windows as the data layer meets it, on POSIX: no getuid, and each of
    the six security calls answered here -- the owner of a file or folder
    (keyed by what the name leads to, or, not followed, by the name's own
    object: a link's or a junction's), the owner of a file as opened (keyed
    by what the descriptor is open on), this account's SID, whether a
    folder's list gives anyone else anything, whether it grants this
    account's own SID anything, and the setting of the protected list;
    and whether a folder on the way to the data folder gives another
    account a right over it, and the handle that holds the data folder (a
    descriptor of it, here).
    `owners` maps an object's key to a SID, None (a volume that keeps no
    owners) or DENIED; anything not in it is `default`'s. A folder in
    `unnamed` has a list that grants this account nothing; every other
    folder's grants it full control. A folder in `folder_open` (keyed by
    the name's own object) gives another account a right over it; one in
    `unclosable` refuses the protected list."""

    def __init__(self, monkeypatch, default=USER_SID):
        self.owners, self.default = {}, default
        self.wide, self.write_wide, self.unnamed = set(), set(), set()
        self.folder_open, self.unclosable = set(), set()
        self.closed, self.asked, self.write_asked, self.looked, self.reset = [], [], [], [], []
        monkeypatch.delattr(os, "getuid")
        monkeypatch.setattr(user_data, "_windows_owner", self.owner, raising=False)
        monkeypatch.setattr(user_data, "_windows_owner_of_the_open", self.opened, raising=False)
        monkeypatch.setattr(user_data, "_windows_this_account", lambda: USER_SID, raising=False)
        monkeypatch.setattr(user_data, "_windows_list_is_wider", self.wider, raising=False)
        monkeypatch.setattr(user_data, "_windows_file_is_writable_by_others", self.writable, raising=False)
        monkeypatch.setattr(user_data, "_windows_list_names_this_account", self.names, raising=False)
        monkeypatch.setattr(user_data, "_windows_close_the_list", self.close, raising=False)
        monkeypatch.setattr(user_data, "_windows_reset_the_list", self.reset_list, raising=False)
        monkeypatch.setattr(user_data, "_windows_folder_is_open_to_others", self.folder_is_open, raising=False)
        monkeypatch.setattr(user_data, "_windows_hold_the_folder", self.hold, raising=False)

    def own(self, path, sid, follow=True):
        self.owners[_key(path, follow)] = sid
        return path

    def owner(self, path, follow_links=True):
        found = self.owners.get(_key(path, follow_links), self.default)
        if found is DENIED:
            raise user_data._OwnerDenied(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return found

    def opened(self, fd):
        seen = _REAL["fstat"](fd)
        found = self.owners.get((seen.st_dev, seen.st_ino), self.default)
        if found is DENIED:
            raise user_data._OwnerDenied(errno.EACCES, os.strerror(errno.EACCES), f"descriptor {fd}")
        return found

    def wider(self, path):
        self.asked.append(_key(path))
        return _key(path) in self.wide

    def writable(self, path, follow_links=True):
        self.write_asked.append(_key(path, follow_links))
        return _key(path, follow_links) in self.write_wide

    def names(self, path):
        self.looked.append(_key(path))
        return _key(path) not in self.unnamed

    def folder_is_open(self, path):
        return _key(path, False) in self.folder_open

    def hold(self, path):
        return os.open(path, os.O_RDONLY)

    def close(self, path):
        if _key(path) in self.unclosable:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        self.closed.append(_key(path))
        self.wide.discard(_key(path))
        self.write_wide.discard(_key(path))
        self.unnamed.discard(_key(path))

    def reset_list(self, path):
        self.reset.append(_key(path))
        self.write_wide.discard(_key(path))


def _base(tmp_path):
    base = tmp_path / "appdata"
    base.mkdir()
    return base, base / LEGACY, base / "Zij"


def _store(folder, charts):
    folder.mkdir(exist_ok=True)
    (folder / "saved_charts.json").write_text(json.dumps(charts, indent=2))
    return folder / "saved_charts.json"


def _stored(charts):
    """The tree _store leaves: one store holding `charts`."""
    return {"saved_charts.json": ("file", json.dumps(charts, indent=2).encode())}


def _tree(top):
    found = {}
    for root, dirs, files in os.walk(top):
        for name in dirs + files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, top)
            if os.path.islink(path):
                found[rel] = ("link", os.readlink(path))
            elif os.path.isdir(path):
                found[rel] = ("folder", None)
            else:
                with open(path, "rb") as f:
                    found[rel] = ("file", f.read())
    return found


class HeldByATest(list):
    """The data layer's list of the folder held (user_data._HELD), as a
    test's launch sets it: told apart from the module's own, so that a
    second launch in one test closes the folder the first held."""


def _launched(monkeypatch, target):
    """The data layer as a launch's import leaves it with its folder at
    `target`: the folder made (or refused) by the launch's own function and
    the paths named under it, the preferences on. Returns what the making
    raised, or None."""
    # The folder a launch here holds is the test's own: one an earlier launch
    # of the same test held is closed here, and the last is closed when the
    # test ends (conftest's the_data_folder_held_is_let_go).
    held = getattr(user_data, "_HELD", None)
    if isinstance(held, HeldByATest) and held[0] is not None:
        held[0].close()
    monkeypatch.setattr(user_data, "_HELD", HeldByATest([None]), raising=False)
    monkeypatch.setattr(user_data, "_REFUSED", {}, raising=False)
    monkeypatch.setattr(user_data, "_LET_GO", set(), raising=False)
    try:
        made, error, raised = user_data._make_user_data_dir(target), None, None
    except OSError as exc:
        made, error, raised = target, exc.strerror or str(exc), exc
    monkeypatch.setattr(user_data, "DATA_DIR", made)
    monkeypatch.setattr(user_data, "DATA_DIR_ERROR", error)
    monkeypatch.setattr(user_data, "SAVED_CHARTS_PATH", made / "saved_charts.json")
    monkeypatch.setattr(user_data, "PREFERENCES_PATH", made / "preferences.json")
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return raised


def _reads(monkeypatch):
    """Every file the data layer reads through its one reader."""
    seen = []
    real = user_data._read_regular_file

    def read(path, *args, **kwargs):
        seen.append(os.path.realpath(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_read_regular_file", read)
    return seen


def _refused_throughout(monkeypatch, tmp_path, target, reason, planted=None):
    """After a refusal: data_folder_state() gives `reason`; a chart read
    finds nothing, a save and a preference write are refused; the planted
    store is never read and nothing lands anywhere under the test's folder."""
    reads = _reads(monkeypatch)
    before = _tree(tmp_path)
    assert user_data.data_folder_state()[1] == reason
    assert user_data.load_saved_charts() == {}
    with user_data.saved_charts_lock():
        assert user_data.bring_in_the_old_store() is False
        assert user_data.write_saved_charts({"Mine": REC}) is False
    assert user_data.write_preferences({"last_chart": "Mine"}) is False
    after = {k: v for k, v in _tree(tmp_path).items() if not k.endswith((".lock", ".lck"))}
    assert after == {k: v for k, v in before.items() if not k.endswith((".lock", ".lck"))}
    if planted is not None:
        assert os.path.realpath(planted) not in reads, "the planted store was read"


def _used_throughout(monkeypatch, charts):
    """A launch that takes the folder: nothing said, its charts read, a save
    and a preference write made."""
    assert user_data.data_folder_state() == (None, None)
    assert user_data.load_saved_charts() == charts
    with user_data.saved_charts_lock():
        assert user_data.write_saved_charts(dict(charts, Mine=REC)) is True
    assert user_data.write_preferences({"last_chart": "Mine"}) is True
    assert json.loads(user_data.SAVED_CHARTS_PATH.read_text()) == dict(charts, Mine=REC)


def _copies_begun(monkeypatch):
    """Every copy of a former folder the data layer begins: its copy by name
    entered, a copytree started, a staging folder (`.copying`) made."""
    begun = []
    real_copy, real_copytree, real_mkdir = user_data._copy_the_former_folder_by_name, shutil.copytree, os.mkdir

    def copy(legacy, path):
        begun.append(("copy by name", os.path.basename(legacy)))
        return real_copy(legacy, path)

    def copytree(src, dst, *args, **kwargs):
        begun.append(("copytree", os.path.basename(src)))
        return real_copytree(src, dst, *args, **kwargs)

    def mkdir(path, *args, **kwargs):
        if os.fspath(path).endswith(".copying"):
            begun.append(("staging folder", os.path.basename(path)))
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(user_data, "_copy_the_former_folder_by_name", copy)
    monkeypatch.setattr(shutil, "copytree", copytree)
    monkeypatch.setattr(os, "mkdir", mkdir)
    return begun


NOT_OURS = "it belongs to another account"
FORMER_NOT_OURS = "the folder an older version kept them in belongs to another account"


# =============================================================================
# Whose folder, on Windows
# =============================================================================

def test_another_accounts_folder_at_the_data_folders_name_is_refused_with_no_race(monkeypatch, tmp_path):
    """The user's Zij renamed aside before a launch and another account's,
    holding a store a parser takes, put in its place: refused, never read."""
    base, legacy, target = _base(tmp_path)
    _store(base / "Zij aside", {"Mine": REC})
    planted = _store(target, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(target, OTHER_SID)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderRefused) and raised.strerror == NOT_OURS, raised
    _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, planted)
    assert win.closed == [], "another account's folder had its list set"


def test_another_accounts_folder_made_before_an_upgrade_is_refused_and_nothing_copied_in(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    target.mkdir()
    win = _Windows(monkeypatch)
    win.own(target, OTHER_SID)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderRefused), raised
    _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS)
    assert _tree(target) == {}, "the former charts were copied in"
    assert _tree(legacy) == _stored({"Old": REC})


def test_another_accounts_folder_put_in_the_way_of_the_move_is_refused_and_nothing_copied_in(monkeypatch, tmp_path):
    """At an upgrade, another account puts its folder at Zij as the former
    folder is renamed there; Windows refuses a rename onto a folder, so the
    launch copies by name, finds the name taken, and judges what is there."""
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    win = _Windows(monkeypatch)
    real = Path.rename

    def rename(self, to):
        if self == legacy:
            _store(target, {"Injected": INJECTED})
            win.own(target, OTHER_SID)
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(to))
        return real(self, to)
    monkeypatch.setattr(Path, "rename", rename)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderRefused), raised
    assert _tree(target) == _stored({"Injected": INJECTED}), "the former charts were copied in"
    assert _tree(legacy) == _stored({"Old": REC})
    _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, target / "saved_charts.json")


@pytest.mark.parametrize("owner", [ADMINISTRATORS, SYSTEM, USER_SID])
def test_a_data_folder_of_administrators_system_or_the_user_is_taken(monkeypatch, tmp_path, owner):
    base, legacy, target = _base(tmp_path)
    _store(target, {"Old": REC})
    win = _Windows(monkeypatch)
    win.own(target, owner)
    assert _launched(monkeypatch, target) is None
    _used_throughout(monkeypatch, {"Old": REC})


@pytest.mark.parametrize("move", ["moved", "copied"])
def test_another_accounts_former_folder_is_refused_and_nothing_copied(monkeypatch, tmp_path, move):
    base, legacy, target = _base(tmp_path)
    planted = _store(legacy, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(legacy, OTHER_SID)
    if move == "copied":
        real = Path.rename
        monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
            PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real(self, to))
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.FormerFolderRefused) and raised.strerror == FORMER_NOT_OURS, raised
    assert sorted(os.listdir(base)) == [LEGACY], "a data folder or a copy was made"
    assert _tree(legacy) == _stored({"Injected": INJECTED})
    _refused_throughout(monkeypatch, tmp_path, target, FORMER_NOT_OURS, planted)


def test_another_accounts_former_folder_is_never_read_into_a_copy(monkeypatch, tmp_path):
    """The move refused, so that the launch would copy by name: another
    account's former folder is refused before any copy of it begins -- no
    copy entered, no copytree, no staging folder -- not only kept from being
    published."""
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(legacy, OTHER_SID)
    real = Path.rename
    monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
        PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real(self, to))
    begun = _copies_begun(monkeypatch)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.FormerFolderRefused) and raised.strerror == FORMER_NOT_OURS, raised
    assert begun == [], "a copy of another account's folder was begun"
    assert sorted(os.listdir(base)) == [LEGACY], "a data folder or a copy was published"
    assert _tree(legacy) == _stored({"Injected": INJECTED})


def test_a_former_folder_swapped_for_another_accounts_during_its_copy_is_not_published(monkeypatch, tmp_path):
    """The move refused, the copy made by name; the folder at the former
    name is another account's by the time the copy would be published."""
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    win = _Windows(monkeypatch)
    real_rename, real_copytree = Path.rename, shutil.copytree
    monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
        PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real_rename(self, to))

    def copytree(src, dst, *args, **kwargs):
        done = real_copytree(src, dst, *args, **kwargs)
        win.own(legacy, OTHER_SID)
        return done
    monkeypatch.setattr(shutil, "copytree", copytree)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.FormerFolderRefused), raised
    assert sorted(os.listdir(base)) == [LEGACY], "the copy was published, or left"


def test_what_the_move_put_at_the_data_folders_name_is_judged_after_it(monkeypatch, tmp_path):
    """Another account's folder swapped in at the former name between the
    look and the rename: the rename carries it to Zij, and the launch
    refuses it there."""
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    win = _Windows(monkeypatch)
    real = Path.rename

    def rename(self, to):
        done = real(self, to)
        if self == legacy:
            win.own(target, OTHER_SID)
        return done
    monkeypatch.setattr(Path, "rename", rename)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.FormerFolderRefused), raised


@pytest.mark.parametrize("where", ["the data folder", "the former folder"])
def test_an_owner_the_user_is_denied_the_reading_of_is_refused(monkeypatch, tmp_path, where):
    base, legacy, target = _base(tmp_path)
    folder = target if where == "the data folder" else legacy
    planted = _store(folder, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(folder, DENIED)
    raised = _launched(monkeypatch, target)
    if where == "the data folder":
        assert isinstance(raised, user_data.DataFolderRefused), raised
        _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, planted)
    else:
        assert isinstance(raised, user_data.FormerFolderRefused), raised
        assert not os.path.lexists(target)
        _refused_throughout(monkeypatch, tmp_path, target, FORMER_NOT_OURS, planted)


@pytest.mark.parametrize("where", ["the data folder", "the former folder"])
def test_a_security_descriptor_that_names_no_owner_is_refused(monkeypatch, tmp_path, where):
    """An owner read as no one ("", a descriptor that names no owner) is not
    a volume that keeps no owners (None): refused at either name."""
    base, legacy, target = _base(tmp_path)
    folder = target if where == "the data folder" else legacy
    planted = _store(folder, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(folder, "")
    begun = _copies_begun(monkeypatch)
    raised = _launched(monkeypatch, target)
    if where == "the data folder":
        assert isinstance(raised, user_data.DataFolderRefused) and raised.strerror == NOT_OURS, raised
        assert _tree(target) == _stored({"Injected": INJECTED})
        _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, planted)
    else:
        assert isinstance(raised, user_data.FormerFolderRefused) and raised.strerror == FORMER_NOT_OURS, raised
        assert begun == [], "a copy of the former folder was begun"
        assert sorted(os.listdir(base)) == [LEGACY], "a data folder was made from the former folder"
        assert _tree(legacy) == _stored({"Injected": INJECTED})
        _refused_throughout(monkeypatch, tmp_path, target, FORMER_NOT_OURS, planted)


@pytest.mark.parametrize("move", ["first launch", "moved", "copied"])
def test_a_volume_that_keeps_no_owners_is_used_and_nothing_said(monkeypatch, tmp_path, move):
    """FAT or exFAT: no owner to read (None), left as it is, as a filesystem
    that keeps no modes is on POSIX."""
    base, legacy, target = _base(tmp_path)
    if move != "first launch":
        _store(legacy, {"Old": REC})
    if move == "copied":
        real = Path.rename
        monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
            PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real(self, to))
    _Windows(monkeypatch, default=None)
    assert _launched(monkeypatch, target) is None
    _used_throughout(monkeypatch, {} if move == "first launch" else {"Old": REC})


def test_no_windows_call_is_looked_up_at_import():
    """ctypes is loaded at the first Windows call, never at import, so that
    POSIX never reaches for it."""
    import ast
    tree = ast.parse((EXECUTABLE_DIR / "user_data.py").read_text(encoding="utf-8"))
    top = [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [line for line in top if "ctypes" in line], top
    assert user_data._WINDOWS_CALLS == {}


# =============================================================================
# How private, on Windows
# =============================================================================

def test_the_data_folder_made_is_given_the_protected_list(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    win = _Windows(monkeypatch)
    assert _launched(monkeypatch, target) is None
    assert win.closed == [_key(target)]
    _used_throughout(monkeypatch, {})


def _names_matched_whatever_their_case(monkeypatch, own, found):
    """A volume that matches names whatever their case (Windows', and
    macOS' by default), stood in: while the file `found` stands, a look at
    the name `own` is a look at it."""
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if os.fspath(path) == os.fspath(own):
            try:
                return real(found, *args, **kwargs)
            except FileNotFoundError:
                pass
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "lstat", lstat)


@pytest.mark.parametrize("name, volume", [("saved_charts.json", "either"),
                                          ("SAVED_CHARTS.JSON", "matching names whatever their case"),
                                          ("SAVED_CHARTS.JSON", "telling the cases apart")])
def test_a_store_of_the_users_another_account_may_write_is_set_aside_before_it_is_read(monkeypatch, tmp_path,
                                                                                       name, volume):
    """A store the user owns whose own list lets another account change it
    (an explicit entry, which the folder's closed list does not take away)
    is set aside at the launch, unread, under a recovery name, its own
    entries taken from its list, and the page told. A name in another case
    is the same file to Windows (and to macOS by default): it is set aside
    under the store's own name, awaited by the restore, with the notice and
    its button, and the restore writes the store's own name; it was set
    aside under its own case, which the restore never looked for, and the
    charts were gone from the app without a word. On a volume that tells
    the cases apart it is no file the app reads as its store, and is not
    offered."""
    base, legacy, target = _base(tmp_path)
    target.mkdir()
    store = target / name
    store.write_text(json.dumps({"Old": REC}, indent=2))
    before, data = _key(store), store.read_bytes()
    win = _Windows(monkeypatch)
    win.wide.add(_key(target))
    win.write_wide.add(before)
    if volume == "matching names whatever their case":
        _names_matched_whatever_their_case(monkeypatch, target / "saved_charts.json", store)
    the_store = volume != "telling the cases apart"

    assert _launched(monkeypatch, target) is None
    assert _key(target) in win.closed and before in win.write_asked
    [aside] = [p for p in target.iterdir() if p.name.startswith(("saved_charts.json" if the_store else name)
                                                                + ".set-aside-")]
    assert not store.exists() and _key(aside) == before and aside.read_bytes() == data and win.reset == [before]
    assert user_data.load_saved_charts() == {}
    assert user_data.set_aside_notices()["awaiting"] is the_store
    assert user_data.restore_set_aside() is True
    assert user_data.load_saved_charts() == ({"Old": REC} if the_store else {})
    assert os.path.lexists(aside) is not the_store
    assert sorted(p.name for p in target.iterdir() if not p.name.endswith(".lock")) == (
        ["saved_charts.json"] if the_store else [aside.name])


def test_a_foreign_read_only_allowance_does_not_replace_the_store(monkeypatch, tmp_path):
    """A list that lets another account read the store, not change it, is
    narrowed with the folder's and the store is left as it is."""
    base, legacy, target = _base(tmp_path)
    store = _store(target, {"Old": REC})
    before = _key(store)
    win = _Windows(monkeypatch)
    win.wide.update({_key(target), before})

    assert _launched(monkeypatch, target) is None
    assert user_data.load_saved_charts() == {"Old": REC}
    assert _key(store) == before and before in win.write_asked and win.reset == []
    assert user_data.set_aside_notices() == {"awaiting": False, "unfollowed": False, "held": False}


@pytest.mark.parametrize("wide", [True, False], ids=["wider", "closed already"])
def test_a_data_folder_of_the_users_is_narrowed_at_a_launch_only_where_its_list_is_wider(monkeypatch, tmp_path,
                                                                                          wide):
    base, legacy, target = _base(tmp_path)
    _store(target, {"Old": REC})
    win = _Windows(monkeypatch)
    if wide:
        win.wide.add(_key(target))
    assert _launched(monkeypatch, target) is None
    assert win.asked == [_key(target)]
    assert win.closed == ([_key(target)] if wide else [])
    _used_throughout(monkeypatch, {"Old": REC})


def test_another_accounts_wide_folder_is_neither_asked_nor_given_the_list(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _store(target, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(target, OTHER_SID)
    win.wide.add(_key(target))
    assert isinstance(_launched(monkeypatch, target), user_data.DataFolderRefused)
    assert win.asked == [] and win.closed == []


def test_a_wider_former_folder_of_the_users_is_narrowed_before_it_is_moved(monkeypatch, tmp_path):
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    win = _Windows(monkeypatch)
    win.wide.add(_key(legacy))
    order = []
    real = Path.rename

    def rename(self, to):
        if self == legacy:
            order.append(("moved", list(win.closed)))
        return real(self, to)
    monkeypatch.setattr(Path, "rename", rename)
    folder = _key(legacy)
    assert _launched(monkeypatch, target) is None
    assert order == [("moved", [folder])], order
    _used_throughout(monkeypatch, {"Old": REC})


@pytest.mark.parametrize("owner", [ADMINISTRATORS, SYSTEM], ids=["Administrators", "SYSTEM"])
def test_a_folder_of_administrators_or_system_whose_list_grants_the_user_nothing_is_given_the_list(
        monkeypatch, tmp_path, owner):
    """A folder a run as administrator made (its owner Administrators, its
    list SYSTEM, Administrators and OWNER RIGHTS, none naming the user):
    taken, and given the protected list naming the user, once, after its
    owner was read."""
    base, legacy, target = _base(tmp_path)
    _store(target, {"Old": REC})
    win = _Windows(monkeypatch)
    win.own(target, owner)
    win.unnamed.add(_key(target))
    order = []
    real_owner, real_close = win.owner, win.close
    monkeypatch.setattr(user_data, "_windows_owner", lambda path, follow_links=True: (
        order.append("owner read"), real_owner(path, follow_links))[1])
    monkeypatch.setattr(user_data, "_windows_close_the_list", lambda path: (
        order.append("list given"), real_close(path))[1])
    assert _launched(monkeypatch, target) is None
    assert win.closed == [_key(target)]
    assert win.looked == [_key(target)]
    assert order.count("list given") == 1 and order.index("list given") > 1, order
    _used_throughout(monkeypatch, {"Old": REC})


@pytest.mark.parametrize("owner", [ADMINISTRATORS, SYSTEM, USER_SID],
                         ids=["Administrators, the list naming the user", "SYSTEM, the list naming the user",
                              "the user, OWNER RIGHTS alone"])
def test_a_folder_whose_list_grants_the_user_or_whose_owner_is_the_user_is_not_touched(monkeypatch, tmp_path, owner):
    """A list that already names the user is left; so is the user's own
    folder whose list names only OWNER RIGHTS, which grants it its owner."""
    base, legacy, target = _base(tmp_path)
    _store(target, {"Old": REC})
    win = _Windows(monkeypatch)
    win.own(target, owner)
    if owner == USER_SID:
        win.unnamed.add(_key(target))
    assert _launched(monkeypatch, target) is None
    assert win.closed == []
    _used_throughout(monkeypatch, {"Old": REC})


def test_another_accounts_folder_whose_list_grants_the_user_nothing_is_refused_and_given_no_list(monkeypatch,
                                                                                                 tmp_path):
    base, legacy, target = _base(tmp_path)
    planted = _store(target, {"Injected": INJECTED})
    win = _Windows(monkeypatch)
    win.own(target, OTHER_SID)
    win.unnamed.add(_key(target))
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderRefused) and raised.strerror == NOT_OURS, raised
    assert win.closed == [] and win.looked == [] and win.asked == []
    _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, planted)
    assert win.closed == []


def test_the_folder_a_copy_by_name_is_made_in_is_given_the_list_before_anything_is_copied(monkeypatch, tmp_path):
    """The move refused: the copy's own folder is given the protected list
    before the copy begins, so that what is copied takes it; the folder then
    published at the data folder's name is that one."""
    base, legacy, target = _base(tmp_path)
    _store(legacy, {"Old": REC})
    win = _Windows(monkeypatch)
    real_rename, real_copytree, real_close = Path.rename, shutil.copytree, win.close
    monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
        PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real_rename(self, to))
    events = []

    def close(path):
        events.append(("list given", os.path.basename(path), _key(path)))
        return real_close(path)

    def copytree(src, dst, *args, **kwargs):
        events.append(("copy begun", os.path.basename(dst), _key(dst)))
        return real_copytree(src, dst, *args, **kwargs)
    monkeypatch.setattr(user_data, "_windows_close_the_list", close)
    monkeypatch.setattr(shutil, "copytree", copytree)
    assert _launched(monkeypatch, target) is None
    staged = [event for event in events if event[1].endswith(".copying")]
    assert [what for what, _name, _k in staged] == ["list given", "copy begun"], events
    assert staged[0][1:] == staged[1][1:], events
    assert _key(target) == staged[0][2], "the folder published is not the one given the list"
    _used_throughout(monkeypatch, {"Old": REC})


@pytest.mark.parametrize("call", ["read", "set"])
def test_a_list_that_cannot_be_read_or_set_refuses_the_folder(monkeypatch, tmp_path, call):
    """A folder of Administrators' this account may not change, or one
    whose list cannot be read: it cannot be closed to other accounts, so it
    is refused, and nothing in it is read. (A volume that keeps no lists
    reads as closed, and needs no closing.)"""
    base, legacy, target = _base(tmp_path)
    _store(target, {"Old": REC})
    win = _Windows(monkeypatch)
    win.wide.add(_key(target))

    def refused(path):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
    monkeypatch.setattr(user_data, "_windows_list_is_wider" if call == "read" else "_windows_close_the_list", refused)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderNotClosed), raised
    assert user_data.data_folder_state() == ("used", user_data.DATA_FOLDER_NOT_CLOSED)
    assert user_data.load_saved_charts() == {}


# =============================================================================
# A link at the data folder's name, judged by its own owner (every platform)
# =============================================================================

class _OwnedByAnother:
    """A stat result whose owner is another account's id."""

    def __init__(self, seen):
        self._seen = seen
        self.st_uid = seen.st_uid + 1

    def __getattr__(self, name):
        return getattr(self._seen, name)


def _another_account_made(monkeypatch, link):
    """The link at `link` is another account's, as os.lstat and os.fstat
    report it (the link's own device and inode): what it leads to stays the
    user's."""
    key = _key(link, follow=False)

    def judged(look):
        def call(*args, **kwargs):
            seen = look(*args, **kwargs)
            return _OwnedByAnother(seen) if (seen.st_dev, seen.st_ino) == key else seen
        return call
    for name in ("lstat", "fstat"):
        monkeypatch.setattr(os, name, judged(_REAL[name]))
    monkeypatch.setattr(os, "stat", lambda path, *a, follow_symlinks=True, **k: (
        judged(_REAL["stat"]) if not follow_symlinks else _REAL["stat"])(path, *a, follow_symlinks=follow_symlinks,
                                                                        **k))


def _a_link_at_the_data_folders_name(tmp_path):
    """A link at Zij, to a folder of the user's holding the user's store."""
    base, legacy, target = _base(tmp_path)
    mine = tmp_path / "mine"
    planted = _store(mine, {"Old": REC})
    target.symlink_to(mine, target_is_directory=True)
    return target, planted


@pytest.mark.parametrize("platform", ["POSIX", "Windows"])
def test_another_accounts_link_at_the_data_folders_name_is_refused(monkeypatch, tmp_path, platform):
    """Judged by its own owner before it is followed: refused, the store it
    leads to unread."""
    target, planted = _a_link_at_the_data_folders_name(tmp_path)
    if platform == "Windows":
        _Windows(monkeypatch).own(target, OTHER_SID, follow=False)
    else:
        _another_account_made(monkeypatch, target)
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderRefused) and raised.strerror == NOT_OURS, raised
    _refused_throughout(monkeypatch, tmp_path, target, NOT_OURS, planted)
    assert json.loads(planted.read_text()) == {"Old": REC}


@pytest.mark.parametrize("platform", ["POSIX", "Windows"])
def test_the_users_link_at_the_data_folders_name_is_followed(monkeypatch, tmp_path, platform):
    target, planted = _a_link_at_the_data_folders_name(tmp_path)
    if platform == "Windows":
        _Windows(monkeypatch)
    assert _launched(monkeypatch, target) is None
    _used_throughout(monkeypatch, {"Old": REC})
    assert json.loads(planted.read_text()) == {"Old": REC, "Mine": REC}


def _junction_lists(monkeypatch, win, refused=()):
    """Windows' setting of a list at a name, stood in: given at a junction's
    name it is set on the junction itself, and the folder it leads to keeps
    what it inherited; given at a folder, everything in it takes the
    protected list. A name whose own key is in `refused` is refused. The
    keys of the names it was given, not followed."""
    given = []

    def close(path):
        given.append(_key(path, follow=False))
        if _key(path, follow=False) in refused:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        if os.path.islink(path):
            return
        win.close(path)
        for each in Path(path).iterdir():
            win.write_wide.discard(_key(each))
    monkeypatch.setattr(user_data, "_windows_close_the_list", close)
    return given


def test_the_folder_the_users_junction_at_the_data_folders_name_leads_to_is_closed(monkeypatch, tmp_path):
    """The user's junction at Zij leads to a folder that passes another
    account's Modify entry down to the store in it, as a drive's root does.
    The list was set at the junction's name, on the junction itself: the
    store stayed one others could change, was set aside at the launch, and
    every save after was too. The folder it leads to is closed as well, so
    the store in it is read and a save kept."""
    target, planted = _a_link_at_the_data_folders_name(tmp_path)
    mine = planted.parent
    win = _Windows(monkeypatch)
    win.wide.add(_key(mine))
    win.write_wide.add(_key(planted))
    given = _junction_lists(monkeypatch, win)
    assert _launched(monkeypatch, target) is None
    assert _key(mine, follow=False) in given and _key(mine) not in win.wide
    _used_throughout(monkeypatch, {"Old": REC})
    assert json.loads(planted.read_text()) == {"Old": REC, "Mine": REC}


def test_a_list_the_launch_could_not_close_at_the_junctions_folder_refuses_the_folder(monkeypatch, tmp_path):
    """Where the folder the junction leads to refuses its list, it was
    recorded where no page read it, and the folder used. It is now refused
    with its reason; nothing of the store others could change is read."""
    target, planted = _a_link_at_the_data_folders_name(tmp_path)
    mine = planted.parent
    win = _Windows(monkeypatch)
    win.wide.add(_key(mine))
    win.write_wide.add(_key(planted))
    _junction_lists(monkeypatch, win, refused={_key(mine, follow=False)})
    raised = _launched(monkeypatch, target)
    assert isinstance(raised, user_data.DataFolderNotClosed), raised
    assert raised.strerror == user_data.DATA_FOLDER_NOT_CLOSED
    assert user_data.load_saved_charts() == {}


# =============================================================================
# The former name's link, judged by its own owner at every look
# =============================================================================

@pytest.mark.parametrize("opens_a_link, at", [(True, "before the read"), (False, "before the read"),
                                              (False, "after the read")],
                         ids=["O_PATH", "no O_PATH, before", "no O_PATH, after"])
def test_another_accounts_link_bound_at_the_former_name_is_refused(monkeypatch, tmp_path, opens_a_link, at):
    """A link of the user's at the former name, its move refused: while it
    is read, the object bound -- the same device and inode, as a link
    another account made in the freed inode would be -- is another
    account's. The move ends refused and no link is made."""
    base, legacy, target = _base(tmp_path)
    real = tmp_path / "real"
    _store(real, {"Old": REC})
    legacy.symlink_to(real, target_is_directory=True)
    if not opens_a_link:
        monkeypatch.delattr(os, "O_PATH", raising=False)
    real_rename = Path.rename
    monkeypatch.setattr(Path, "rename", lambda self, to: (_ for _ in ()).throw(
        PermissionError(errno.EPERM, "refused (the test's)")) if self == legacy else real_rename(self, to))
    key, theirs = _key(legacy, follow=False), []

    def judged(look):
        def call(*args, **kwargs):
            seen = look(*args, **kwargs)
            return _OwnedByAnother(seen) if theirs and (seen.st_dev, seen.st_ino) == key else seen
        return call
    for name in ("lstat", "fstat"):
        monkeypatch.setattr(os, name, judged(_REAL[name]))
    real_read, real_readlink = user_data._read_the_link, os.readlink

    def read(former):
        if at == "before the read":
            theirs.append(True)
        try:
            return real_read(former)
        finally:
            theirs.clear()

    def readlink(*args, **kwargs):
        target_text = real_readlink(*args, **kwargs)
        if at == "after the read":
            theirs.append(True)
        return target_text
    monkeypatch.setattr(user_data, "_read_the_link", read)
    monkeypatch.setattr(os, "readlink", readlink)
    with pytest.raises(user_data.FormerFolderRefused):
        user_data._make_user_data_dir(target)
    assert not os.path.lexists(target), "a data folder or link was made"
    assert legacy.is_symlink() and _tree(real) == {"saved_charts.json": ("file", (real / "saved_charts.json")
                                                                         .read_bytes())}


# =============================================================================
# An earlier version's dead copy: compared only where it is this account's
# and no other account can write in it or in anything in it
# =============================================================================

def _an_earlier_versions_dead_copy(tmp_path, mode):
    """A `.copying` folder beside the data folder, of mode `mode`, holding
    what the user's owner-only former folder holds -- the store, a folder
    with a file in it, and a link naming what the former folder's link
    names (the guess another account would plant) -- the files 0644 and the
    folder 0755 in it, as copytree gives them under umask 022."""
    base, legacy, target = _base(tmp_path)
    for folder in (legacy, base / ".Zij.0123456789abcdef.copying"):
        _store(folder, {"Old": REC}).chmod(0o644)
        (folder / "sub").mkdir()
        (folder / "sub" / "notes.txt").write_text("the user's notes")
        (folder / "sub" / "notes.txt").chmod(0o644)
        (folder / "private").symlink_to("/a/private/place")
    (legacy / "sub").chmod(0o700)
    legacy.chmod(0o700)
    staging = base / ".Zij.0123456789abcdef.copying"
    (staging / "sub").chmod(0o755)
    staging.chmod(mode)
    return legacy, target, staging


def _former_tree():
    return dict(_stored({"Old": REC}), sub=("folder", None), private=("link", "/a/private/place"),
                **{os.path.join("sub", "notes.txt"): ("file", b"the user's notes")})


@pytest.mark.parametrize("mode", [0o700, 0o750, 0o755], ids=["owner-only", "readable by its group",
                                                             "readable by others"])
def test_an_earlier_versions_dead_copy_of_the_users_that_no_other_can_write_in_goes(monkeypatch, tmp_path, mode):
    """Owner-only, or open to others for reading alone, as copytree gave it
    the former folder's mode: compared, and removed where it matches -- on
    Linux, whose mode shows an access list's write; on macOS it is kept."""
    monkeypatch.setattr(sys, "platform", "linux")
    legacy, target, staging = _an_earlier_versions_dead_copy(tmp_path, mode)
    user_data._remove_dead_copies(target, legacy)
    assert not os.path.lexists(staging), "the user's own dead copy was kept"
    assert _tree(legacy) == _former_tree()


def _listings(monkeypatch, *folders):
    """Each listing of one of `folders`, by name or descriptor."""
    keys, listed, real_listdir = {_key(f, follow=False) for f in folders}, [], os.listdir

    def listdir(path="."):
        seen = _REAL["fstat"](path) if isinstance(path, int) else (
            _REAL["lstat"](path) if os.path.lexists(path) else None)
        if seen is not None and (seen.st_dev, seen.st_ino) in keys:
            listed.append(path)
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", listdir)
    return listed


def _owned_by_another_through_fstat(monkeypatch, path):
    key = _key(path)
    monkeypatch.setattr(os, "fstat", lambda fd, *a, **k: (
        lambda seen: _OwnedByAnother(seen) if (seen.st_dev, seen.st_ino) == key else seen)(_REAL["fstat"](fd)))


@pytest.mark.parametrize("copy", ["another account's", "the user's, writable by its group",
                                  "the user's, writable by others"])
def test_an_earlier_versions_dead_copy_is_compared_only_where_no_other_can_write_in_it(monkeypatch, tmp_path, copy):
    """Another account's, or one its group or others may write in, is left
    unread and kept, as another account's things are."""
    mode = {"another account's": 0o700, "the user's, writable by its group": 0o775,
            "the user's, writable by others": 0o757}[copy]
    legacy, target, staging = _an_earlier_versions_dead_copy(tmp_path, mode)
    if copy == "another account's":
        _owned_by_another_through_fstat(monkeypatch, staging)
    listed = _listings(monkeypatch, staging)
    user_data._remove_dead_copies(target, legacy)
    assert listed == [], "the copy's folder was listed"
    assert _tree(staging) == _former_tree(), "something in the copy was removed"


@pytest.mark.parametrize("inside, listings", [("a folder writable by others", 0), ("a folder writable by its group", 0),
                                              ("a file writable by others", 1), ("a folder of another account's", 0)],
                         ids=lambda value: value if isinstance(value, str) else f"{value} listing(s)")
def test_an_earlier_versions_dead_copy_holding_what_another_could_write_in_is_kept(monkeypatch, tmp_path, inside,
                                                                                   listings):
    """The copy's own folder 0755 and the user's, but a folder or file in it
    that another account could have written in: kept, nothing in it removed,
    such a folder never listed (the folder holding such a file is, once).
    With a 0755 copy another account can reach a folder in it, and where
    that folder is writable to it, plant a guess there."""
    legacy, target, staging = _an_earlier_versions_dead_copy(tmp_path, 0o755)
    if inside == "a folder writable by others":
        (staging / "sub").chmod(0o757)
    elif inside == "a folder writable by its group":
        (staging / "sub").chmod(0o775)
    elif inside == "a file writable by others":
        (staging / "sub" / "notes.txt").chmod(0o646)
    else:
        _owned_by_another_through_fstat(monkeypatch, staging / "sub")
    listed = _listings(monkeypatch, staging / "sub")
    user_data._remove_dead_copies(target, legacy)
    assert os.path.lexists(staging), "the copy was removed"
    assert _tree(staging) == _former_tree(), "something in the copy was removed"
    assert len(listed) == listings, listed
    assert _tree(legacy) == _former_tree()
