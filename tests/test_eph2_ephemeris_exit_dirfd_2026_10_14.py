"""The exit removal of the engine's ephemeris folder made through its
parent's descriptor (the owner's ruling 188, under rulings 139 and 183).

At a normal exit the folder, emptied through the descriptor held on it, was
removed by a path, its own or the one the system gives for that descriptor,
only where os.lstat of the path showed the very folder; then os.rmdir of
the same path. Each call resolved the whole path, so a parent of the folder
swapped for a link between the two carried the rmdir into the directory the
link pointed at, and an empty directory of this user's there, at the
folder's name, was removed in its place. The identity and the removal are
now both made through one descriptor on the path's parent, opened as a
directory with no link followed at its own name: what is left is the race
at the folder's very name in that parent, an empty directory swapped in
between the identity and the rmdir.

Each race here is CONSTRUCTED: the child wraps os.rmdir so that its call on
the folder's name makes the swap first (after the hook's identity check has
passed, before its removal), then calls the real one.

At 296acfd these failed: the parent swapped for a link, at the folder's own
path and at the path where another program moved it (the empty directory of
this user's where the link pointed was removed, and the engine's folder,
emptied, left); and every case of the hook's own calls but the removed
folder's (no parent was opened). Passed there: the final name's race, the
link left at the folder's path, the linked temporary folders, and the
removed folder's case.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from conftest import EXECUTABLE_DIR
from test_fm3_ephemeris_folder_umask_2026_10_07 import _child, short_root  # noqa: F401 (a fixture)

TIMEOUT = 300


def _look(path):
    """What stands at `path`: a link's target, a directory's listing, or
    'gone'."""
    if os.path.islink(path):
        return "link -> " + os.readlink(path)
    if os.path.isdir(path):
        return sorted(os.listdir(path))
    return "gone" if not os.path.lexists(path) else "other"


# ---------------------------------------------------------------------------
# The engine's own exit, in a child, with the race CONSTRUCTED inside it.

_RACE = r"""
def body():
    case, root = ARGS[0], ARGS[1]
    j = os.path.join
    first = ephemeris._EPHEMERIS_FOLDER
    name = os.path.basename(first)
    out["first"] = first
    grab("stars", stars)                              # the catalogue copied in
    out["listing"] = sorted(os.listdir(first))
    mine = out["mine"] = {}
    def make_mine(path, holding=False):               # a directory of this user's, 0700
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        if holding:
            with open(j(path, "theirs.txt"), "w") as fh:
                fh.write("theirs")
        st = os.lstat(path)
        mine[path] = [st.st_dev, st.st_ino, sorted(os.listdir(path))]
    os.mkdir(j(root, "Q"), 0o700)
    make_mine(j(root, "D"), holding=True)             # a bystander in every case
    if case == "moved-parent":                        # the folder moved aside into a directory P
        os.mkdir(j(root, "P"), 0o700)
        os.rename(first, j(root, "P", "kept"))
        out["chart"] = in_a_thread(moon)              # the engine makes its second folder
        out["second"] = ephemeris._EPHEMERIS_FOLDER
        make_mine(j(root, "Q", "kept"))
        hit, parent = "kept", j(root, "P")
    elif case == "link-at-path":                      # moved aside, a link to it left at its path
        out["moved"] = first + "-moved"
        os.rename(first, out["moved"])
        os.symlink(out["moved"], first)
        PLANTED.append(first)
        out["chart"] = in_a_thread(moon)
        out["second"] = ephemeris._EPHEMERIS_FOLDER
        return
    else:                                             # at its own path
        make_mine(j(root, "Q", name))                 # the same name in another directory of mine
        hit, parent = name, os.path.dirname(first)
        if case == "own-parent":
            PLANTED.append(first)                     # after the swap its path names Q's directory, mine
        else:
            make_mine(j(parent, "E"))                 # an empty sibling
    real = os.rmdir
    def rmdir(path, *a, **k):
        # CONSTRUCTED window: the swap is made on the hook's own rmdir of the
        # folder, after its identity check and before its removal.
        if os.path.basename(os.fspath(path)) == hit and not swapped:
            swapped.append(True)
            if case == "final":                       # the folder renamed aside, an empty one of mine at its name
                os.rename(first, first + "-aside")
                os.mkdir(first, 0o700)
                os.chmod(first, 0o700)
            else:                                     # the parent renamed and replaced by a link to Q
                os.rename(parent, parent + "2")
                os.symlink(j(root, "Q"), parent)
        return real(path, *a, **k)
    swapped = []
    os.rmdir = rmdir
"""


def _raced(tmp_path_factory, short_root, case):
    tmpdir = os.path.join(short_root, "t")
    os.mkdir(tmpdir)
    out, left = _child(tmp_path_factory, 0o022, _RACE, case, short_root, tmpdir=tmpdir)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["stars"][0] is True and out["listing"] == ["sefstars.txt"], out
    assert left == [], left
    if "second" in out:                               # the folder made after the move, removed as before
        assert out["second"] != out["first"] and not os.path.lexists(out["second"]), out
    D = os.path.join(short_root, "D")
    assert _look(D) == ["theirs.txt"] and [os.lstat(D).st_dev, os.lstat(D).st_ino] == out["mine"][D][:2], _look(D)
    return out


@pytest.mark.parametrize("case", ["own-parent", "moved-parent"])
def test_a_parent_swapped_for_a_link_inside_the_removal_carries_it_nowhere(tmp_path_factory, short_root, case):
    """CONSTRUCTED: between the hook's identity check and its rmdir, the
    folder's parent (at its own path, or where another program moved it) is
    renamed and replaced by a link to a directory of this user's holding an
    empty 0700 directory at the folder's name. That directory is kept, as it
    was; the engine's folder is removed in the parent it was judged in.
    Failed at 296acfd: the empty directory was removed through the link and
    the engine's folder, emptied, left."""
    out = _raced(tmp_path_factory, short_root, case)
    name = "kept" if case == "moved-parent" else os.path.basename(out["first"])
    parent = os.path.join(short_root, "P" if case == "moved-parent" else "t")
    assert os.path.islink(parent) and os.path.isdir(parent + "2"), "the constructed swap did not happen"
    theirs = os.path.join(short_root, "Q", name)
    st = os.lstat(theirs) if os.path.lexists(theirs) else None
    assert st is not None and [st.st_dev, st.st_ino] == out["mine"][theirs][:2], "the empty directory was removed"
    assert _look(theirs) == [], _look(theirs)
    assert _look(os.path.join(parent + "2", name)) == "gone", _look(os.path.join(parent + "2", name))


def test_the_final_name_s_race_is_the_one_left_and_reaches_nothing_else(tmp_path_factory, short_root):
    """CONSTRUCTED: between the hook's identity check and its rmdir, the
    folder is renamed aside in its own parent and an empty 0700 directory of
    this user's is made at its name. That directory is removed in the
    folder's place -- the race ruling 183 accepts, an empty directory at the
    folder's very name in the parent it is judged in -- and the folder,
    emptied, is left. Nothing else of this user's is reached: the same name
    in another directory, an empty sibling, a directory holding a file."""
    out = _raced(tmp_path_factory, short_root, "final")
    first = out["first"]
    assert _look(first + "-aside") == [], "the constructed swap did not happen, or the folder was not emptied"
    assert _look(first) == "gone", _look(first)
    now = {path: [os.lstat(path).st_dev, os.lstat(path).st_ino, _look(path)] for path in out["mine"]
           if os.path.lexists(path)}
    assert len(out["mine"]) == 3 and now == out["mine"], (now, out["mine"])


def test_a_link_left_at_the_folder_s_path_is_not_taken_for_the_folder(tmp_path_factory, short_root):
    """Another program moved the folder aside and left a link to it at its
    path. The identity at the path is the link's own, not its target's: the
    link is kept, and the folder is removed where it went."""
    out = _raced(tmp_path_factory, short_root, "link-at-path")
    first, moved = out["first"], out["moved"]
    assert os.path.islink(first) and os.readlink(first) == moved, _look(first)
    assert _look(moved) == "gone", _look(moved)


@pytest.mark.parametrize("shape", ["last-name-a-link", "an-inner-link"])
def test_a_temporary_folder_reached_through_a_link_still_has_its_folder_removed(tmp_path_factory, short_root,
                                                                                shape):
    """TMPDIR through a link, as macOS's often is: its own last name a link
    (as /tmp is there: the parent is not opened through it, and the folder
    is removed by the path the system gives for its descriptor, which is
    the resolved one), or a link before it (as /var is, before
    /var/folders/.../T: followed when the parent is opened, as by any
    path). The folder made there is removed at a normal exit, the links and
    the directories they point at kept."""
    real = os.path.join(short_root, "private", "tmp" if shape == "last-name-a-link" else "var")
    os.makedirs(real)
    if shape == "last-name-a-link":
        os.symlink(real, os.path.join(short_root, "tmp"))
        tmpdir, reached = os.path.join(short_root, "tmp"), real
    else:
        os.mkdir(os.path.join(real, "T"))
        os.symlink(real, os.path.join(short_root, "var"))
        tmpdir, reached = os.path.join(short_root, "var", "T"), os.path.join(real, "T")
    out, left = _child(tmp_path_factory, 0o022, "def body():\n    grab('stars', stars)\n", tmpdir=tmpdir)
    assert out["import"] is None and "body" not in out and out["stars"][0] is True, out
    assert len(out["made"]) == 1 and out["made"][0].startswith(tmpdir + os.sep), out["made"]
    assert left == [] and os.listdir(reached) == [], (left, os.listdir(reached))
    assert os.path.islink(os.path.join(short_root, "tmp" if shape == "last-name-a-link" else "var"))


# ---------------------------------------------------------------------------
# The hook's own calls: the parent it opens, how, and that it is closed.

_DIRECT = r"""
import errno, json, os, shutil, sys
root, case = sys.argv[1], sys.argv[2]
import ephemeris

def count():                                     # the descriptors this process has open
    n = 0
    for fd in range(4096):
        try:
            os.fstat(fd)
        except OSError:
            continue
        n += 1
    return n

def mkdir700(path):
    os.mkdir(path, 0o700)
    os.chmod(path, 0o700)
    return path

def look(path):
    if os.path.islink(path):
        return "link"
    return sorted(os.listdir(path)) if os.path.isdir(path) else "gone"

j = os.path.join
place = mkdir700(j(root, "c"))
folder = mkdir700(j(place, "F"))
with open(j(folder, "sefstars.txt"), "w") as fh:
    fh.write("the copy")
reached = place
if case == "linked-parent":                      # the folder's parent's own name a link
    reached = j(root, "real")
    os.rename(place, reached)
    os.symlink(reached, place)
held = ephemeris._ephemeris_folder_hold(folder)
if case == "unreadable-parent":                  # a parent this user may pass through and write, not read
    os.chmod(place, 0o300)
moved = j(place, "M")
real_stat, real_rmdir, real_where = os.stat, os.rmdir, ephemeris._ephemeris_folder_where
if case in ("moved", "stranger-at-both"):
    os.rename(folder, moved)
if case == "stranger-at-both":                   # an empty 0700 directory at both paths the hook looks at
    mkdir700(folder)
    ephemeris._ephemeris_folder_where = lambda fd: folder
elif case == "removed":                          # a cleaner removed it: its link count is 0
    shutil.rmtree(folder)
elif case == "rmdir-fails":
    def failing(*a, **k):
        raise OSError(errno.EBUSY, "busy")
    os.rmdir = failing
elif case == "identity-unlinked":                # the name's identity reports a link count of 0
    def unlinked(*a, **k):
        st = real_stat(*a, **k)
        if k.get("dir_fd") not in (None, held):
            fields = list(st)
            fields[3] = 0
            st = os.stat_result(fields)
        return st
    os.stat = unlinked
elif case == "no-dir-fd":                        # no dir_fd for the parent's calls
    def refused(*a, **k):
        if k.get("dir_fd") not in (None, held):
            raise NotImplementedError("dir_fd unavailable on this platform")
        return real_stat(*a, **k)
    os.stat = refused
real_open = os.open
opens = []
def recording(path, flags, *a, **k):
    try:
        fd = real_open(path, flags, *a, **k)
    except OSError as exc:
        opens.append([os.fspath(path), flags, exc.errno])
        raise
    opens.append([os.fspath(path), flags, None])
    return fd
before = count()
os.open = recording
ephemeris._ephemeris_folder_remove(folder, os.getpid(), held)
os.open, os.stat, os.rmdir, ephemeris._ephemeris_folder_where = real_open, real_stat, real_rmdir, real_where
os.chmod(place, 0o700)
after = count()                                  # (and the process's own folder is removed at its exit as ever)
print("DIRECT " + json.dumps({"before": before, "after": after, "opens": opens, "folder": look(folder),
                               "moved": look(moved), "place": look(place), "reached": reached,
                               "in_reached": sorted(os.listdir(reached)),
                               "wanted": os.O_DIRECTORY | os.O_NOFOLLOW}))
"""


def _direct(tmp_path_factory, short_root, case):
    tmpdir = os.path.join(short_root, "t")
    os.mkdir(tmpdir)
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    env["TMPDIR"] = tmpdir
    done = subprocess.run([sys.executable, "-c", _DIRECT, short_root, case], cwd=tmp_path_factory.mktemp("cwd"),
                          env=env, capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("DIRECT ")]
    assert done.returncode == 0 and lines and not done.stderr.strip(), done.stderr[-3000:]
    assert os.listdir(tmpdir) == [], os.listdir(tmpdir)    # the process's own folder, removed at its exit
    return json.loads(lines[-1][len("DIRECT "):])


# case: (what is left at the folder's path and at the moved path; the parents opened, "!" where the open was
# refused; what the directory the parent's path reaches holds after)
_CASES = {
    "own": (["gone", "gone"], ["c"], []),
    "moved": (["gone", "gone"], ["c", "c"], []),
    "linked-parent": (["gone", "gone"], ["c!", "real"], []),
    "stranger-at-both": ([[], []], ["c", "c"], ["F", "M"]),
    "removed": (["gone", "gone"], [], []),
    "rmdir-fails": ([[], "gone"], ["c"], ["F"]),
    "identity-unlinked": ([[], "gone"], ["c", "c"], ["F"]),
    "no-dir-fd": ([[], "gone"], ["c", "c"], ["F"]),
    # O_PATH (Linux) needs no leave to read the parent; without it the
    # parent is refused at both paths and the folder, emptied, is left.
    "unreadable-parent": ((["gone", "gone"], ["c"], []) if hasattr(os, "O_PATH") else
                          ([[], "gone"], ["c!", "c!"], ["F"])),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_the_hook_opens_only_the_parent_as_a_directory_and_closes_it(tmp_path_factory, short_root, case):
    """The hook called on a folder of the test's own, held as the engine
    holds its folder: the only descriptors it opens are on the parents of
    the paths it judges, each as a directory with no link followed at its
    own name (a parent whose own name is a link is refused, and the folder
    is removed through the resolved path the system gives); every one is
    closed, as the held one is, whether the folder was removed, judged
    another directory (an empty one of this user's at both paths), removed
    already (no parent opened), refused by its rmdir, judged unlinked at its
    name, or met a system with no dir_fd (emptied and left); and a parent
    this user cannot read, which a removal by its path did not need to,
    still has the folder removed where the system has O_PATH."""
    seen = _direct(tmp_path_factory, short_root, case)
    left, parents, holds = _CASES[case]
    assert [seen["folder"], seen["moved"]] == left, seen
    named = {"c": os.path.join(short_root, "c"), "real": os.path.join(short_root, "real")}
    assert [[p, errno is not None] for p, _, errno in seen["opens"]] == \
        [[named[p.rstrip("!")], p.endswith("!")] for p in parents], seen["opens"]
    assert [flags & seen["wanted"] for _, flags, _ in seen["opens"]] == [seen["wanted"]] * len(parents), seen["opens"]
    assert seen["after"] == seen["before"] - 1, (seen["before"], seen["after"])
    assert seen["in_reached"] == holds and (seen["place"] == "link") == (case == "linked-parent"), seen
