"""The engine's ephemeris folder under any umask (lane FM3, after FM2; ruling 103).

FM2 gives Swiss Ephemeris a private folder of the engine's own, made by
``tempfile.mkdtemp``, holding only a checked copy of the shipped star
catalogue. ``mkdtemp`` asks for mode 0700, and the process's umask cuts what
it asks: under 0o444 the folder came out 0o300 (no read), under 0o222 or
0o277 0o500 (no write), under 0o777 0o000. The guard's listing of the folder
then raised a raw ``PermissionError`` -- at the engine's import, so a launch
computed nothing -- and the check that the folder is still this user's 0700
directory failed for the folder just made, so it was made again at every
call. The catalogue's copy, written 0600, was cut the same way (0o200 under
0o444: its own read-back failed and no star was computed).

Every case runs the engine in a fresh process under each umask: 0o022 (the
usual), 0o077 (a private one), and the four that cut the owner's own bits.
Values are compared as packed IEEE-754 bits with the same launch under
0o022; every thread join and subprocess is bounded. FM2's guarantees are
asked again under each umask: the folder is a real directory, this user's,
mode 0700 (``os.lstat``); what stands at its path after a cleaner is not
adopted, and a normal exit removes only the directory the engine made; a
link in place of the catalogue's copy is not followed (``O_NOFOLLOW``); the
two refusals (a file in the folder the app did not put there, a thread that
read a Delta T file first) and the page's one sentence.

Where nothing can make the folder usable -- a filesystem that keeps no
modes, stood in for by an ``os.chmod`` that does nothing, after a cleaner,
under 0o444 -- the engine refuses as FM2 refuses, and the page says the
sentence ruling 121 gives that case; no raw exception reaches it. The same
holds where no folder can be made at all (the temporary directory gone with
it, a full disk), and at import, where app.py catches the refusal (ruling
120). A
folder a cleaner removes between the guard's check and its listing is
refused the same way, and the next thread makes a new one.

On b5e0e9d 38 of these 61 failed, each for its reason; the 23 that passed
there are every case under 0o022 and 0o077, and the exit and Delta T cases
under 0o222 and 0o277, where the folder came out 0o500, which its owner can
still list and remove. The two cases where no folder can be made at all
were added after the check of d6aa3f8, and failed there (a raw
FileNotFoundError and ENOSPC). After the owner's rulings 120 and 121 (each
refusal its own sentence; the import caught in app.py), the five cases where
no private folder can be had expect the folder's sentence and its own
refusal, the sentence is pinned equal in the engine and app.py, and the
import-time case is pinned on the page; those seven failed on d6aa3f8 (and
on its successor 9a20e8c). The Delta T page case guards that FM2's sentence
stays with its own refusal. Ruling 122's two name cases (a ':' in the
temporary folder's name, a name past the library's length) failed on
cb41bad; the guard that any other error at the engine's import still shows
as itself passed there, and fails where app.py catches every RuntimeError.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

import pytest

from conftest import APP_PATH, ENGINE_PATH, EXECUTABLE_DIR

JD = 2461042.1650830186
JD2000 = 2451545.0
LAT, LON = 43.7696, 11.2558
SHIPPED = EXECUTABLE_DIR / "ephe" / "sefstars.txt"
TIMEOUT = 300

UMASKS = (0o022, 0o077, 0o222, 0o277, 0o444, 0o777)


def _umasks(only=UMASKS):
    return [pytest.param(u, id=f"{u:#05o}") for u in only]


# Each child process: the umask set first, then `tempfile.mkdtemp` watched,
# so the parent knows every folder the process made (and removes any a
# failing engine left behind, after its own assertions).
_HEAD = r"""
import hashlib, json, os, shutil, stat, struct, sys, tempfile, threading
UMASK = int(sys.argv[1], 8)
JD, JD2000, LAT, LON = map(float, sys.argv[2:6])
ARGS = sys.argv[6:]
os.umask(UMASK)
MADE = []
_mkdtemp = tempfile.mkdtemp
def _watched(*a, **k):
    path = _mkdtemp(*a, **k)
    if os.path.basename(path).startswith("zij-ephemeris-"):
        MADE.append(os.path.abspath(path))
    return path
tempfile.mkdtemp = _watched
PLANTED = []                                      # what a case puts at a path the engine made; the test removes it
out = {"made": MADE, "planted": PLANTED}

def bits(x):
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        return struct.pack("!d", x).hex()
    if isinstance(x, dict):
        return {str(k): bits(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [bits(v) for v in x]
    return repr(x)

def said(exc):
    return {"error": type(exc).__name__, "text": str(exc)[:400]}

def grab(key, fn):
    try:
        out[key] = bits(fn())
    except BaseException as exc:
        out[key] = said(exc)

def in_a_thread(fn):
    box = []
    def run():
        try:
            box.append(bits(fn()))
        except BaseException as exc:
            box.append(said(exc))
    worker = threading.Thread(target=run)
    worker.start()
    worker.join(120)
    return box[0] if box else {"error": "timeout", "text": "the thread did not finish within 120 s"}

def chart():
    c = engine.calculate_traditional_chart_jd(JD, LAT, LON)
    return {"bodies": {k: [v["longitude"], v["speed_in_lon"]] for k, v in c["planetary_data"].items()},
            "angles": [c["ascendant"], c["mc"], c["armc"], c["obliquity"]], "sect": c["sect"]}

def moon():
    return engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"]

def stars():
    return [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD),
            sorted(engine._FIXED_STAR_STATE.get("missing") or {})]

def described(path):
    try:
        st = os.lstat(path)
    except OSError as exc:
        return said(exc)
    return {"dir": stat.S_ISDIR(st.st_mode), "file": stat.S_ISREG(st.st_mode), "mode": stat.S_IMODE(st.st_mode),
            "mine": st.st_uid == os.getuid()}

def body():
    pass

try:
    import engine
    import ephemeris                              # the folder's module: the engine holds no live copy of the folder
    out["import"] = None
except BaseException as exc:
    out["import"] = said(exc)
else:
    try:
        body()
    except BaseException as exc:
        out["body"] = said(exc)
print("CHILD " + json.dumps(out))
"""


def _child(tmp_path_factory, umask, body, *args, cwd=None, tmpdir=None):
    """Run `body` (the code of a function `body()`, which fills `out`) in a
    fresh process under `umask`, the engine imported first. Returns
    (out, the folders the process made that still stand after it exited,
    but for what the case itself put at such a path); those are removed
    here, after being reported."""
    code = _HEAD.replace("def body():\n    pass\n", body)
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    if tmpdir is not None:                            # the temporary directory the engine's folder is made in
        env["TMPDIR"] = str(tmpdir)
    cwd = cwd or tmp_path_factory.mktemp("cwd")
    try:
        done = subprocess.run([sys.executable, "-c", code, f"{umask:o}", repr(JD), repr(JD2000), repr(LAT), repr(LON),
                               *map(str, args)],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    finally:                                          # what the umask cut there, pytest must still be able to remove
        for place in (env["XDG_DATA_HOME"], str(cwd)):
            _owner_may_remove(place)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("CHILD ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    out = json.loads(lines[-1][len("CHILD "):])
    left = [p for p in out["made"] if os.path.lexists(p) and p not in out["planted"]]
    for path in left:                                 # this child's own, left by a failing engine
        _remove(path)
    return out, left


def _owner_may_remove(place):
    """Give back to the owner what a cut umask left unreadable under `place`
    (top-down: each directory is opened after it is mended)."""
    for root, dirs, files in os.walk(place):
        for name in dirs + files:
            path = os.path.join(root, name)
            if not os.path.islink(path):
                os.chmod(path, 0o700 if os.path.isdir(path) else 0o600)


def _remove(path):
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
        return
    os.chmod(path, 0o700)
    for root, dirs, _files in os.walk(path):
        for d in dirs:
            if not os.path.islink(os.path.join(root, d)):
                os.chmod(os.path.join(root, d), 0o700)
    shutil.rmtree(path)


def _no_error(value):
    return not (isinstance(value, dict) and "error" in value)


@pytest.fixture
def short_root():
    """A folder of this test's own under /tmp (or, where /tmp is not a
    writable directory, the temporary folder), removed after it: a case that
    hands its child a temporary directory of its own makes it here, so the
    engine's folder made in it stays short whatever the runner's TMPDIR. Made
    under pytest's own temporary directory, a TMPDIR of a hundred characters
    or more put the folder past the 200 bytes the engine takes, and the case
    failed for that alone."""
    root = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK | os.X_OK) else tempfile.gettempdir()
    base = tempfile.mkdtemp(prefix="zij-short-", dir=root)
    try:
        yield base
    finally:
        if os.path.isdir(base):
            _owner_may_remove(base)
            shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# A launch: a chart in the importing thread and in a fresh one, the stars.

_LAUNCH = r"""
def body():
    out["folder_at_import"] = ephemeris._EPHEMERIS_FOLDER
    grab("main", chart)
    out["thread"] = in_a_thread(chart)
    grab("stars", stars)
    folder = ephemeris._EPHEMERIS_FOLDER
    out["folder"] = folder
    out["folder_lstat"] = described(folder)
    grab("listing", lambda: sorted(os.listdir(folder)))
    out["copy_lstat"] = described(os.path.join(folder, "sefstars.txt"))
"""


@pytest.fixture(scope="module")
def launch(tmp_path_factory):
    seen = {}

    def get(umask):
        if umask not in seen:
            seen[umask] = _child(tmp_path_factory, umask, _LAUNCH)
        return seen[umask]
    return get


@pytest.mark.parametrize("umask", _umasks())
def test_a_launch_under_any_umask_computes_in_its_threads_and_reads_the_stars(launch, umask):
    out, _left = launch(umask)
    assert out["import"] is None, out["import"]
    for key in ("main", "thread", "stars"):
        assert _no_error(out[key]), (key, out[key])
    ready, longitudes, missing = out["stars"]
    assert ready is True and len(longitudes) == 28 and missing == [], out["stars"]


@pytest.mark.parametrize("umask", _umasks())
def test_the_folder_is_this_user_s_0700_directory_made_once_under_any_umask(launch, umask):
    out, _left = launch(umask)
    assert out["import"] is None, out["import"]
    assert out["folder_lstat"] == {"dir": True, "file": False, "mode": 0o700, "mine": True}, \
        (out["folder_lstat"], oct(out["folder_lstat"].get("mode", 0)))
    assert out["made"] == [out["folder_at_import"]] == [out["folder"]], out["made"]
    assert out["listing"] == ["sefstars.txt"], out["listing"]


@pytest.mark.parametrize("umask", _umasks())
def test_the_catalogue_s_copy_is_its_owner_s_0600_file_under_any_umask(launch, umask):
    out, _left = launch(umask)
    assert out["import"] is None, out["import"]
    assert out["copy_lstat"] == {"dir": False, "file": True, "mode": 0o600, "mine": True}, out["copy_lstat"]


@pytest.mark.parametrize("umask", _umasks(only=[u for u in UMASKS if u != 0o022]))
def test_values_under_any_umask_are_bit_identical_to_those_under_0o022(launch, umask):
    usual, _ = launch(0o022)
    out, _left = launch(umask)
    assert _no_error(usual["main"]) and len(usual["stars"][1]) == 28, usual
    moved = [k for k in ("main", "thread", "stars") if out.get(k) != usual[k]]
    assert not moved, {k: (usual[k], out.get(k)) for k in moved}
    assert usual["thread"] == usual["main"], "the fresh thread's chart differs from the importing thread's"


@pytest.mark.parametrize("umask", _umasks())
def test_a_normal_exit_removes_every_folder_the_launch_made_under_any_umask(launch, umask):
    out, left = launch(umask)
    assert out["made"], "the launch made no folder"
    assert left == [], f"left behind after a normal exit: {left}"


# The catalogue's copy on its own: the folder made under the usual umask,
# then the umask changed before the first star read, so only the copy's mode
# can be cut.
_LATE = r"""
def body():
    grab("main", chart)
    os.umask(int(ARGS[0], 8))
    grab("stars", stars)
    out["copy_lstat"] = described(os.path.join(ephemeris._EPHEMERIS_FOLDER, "sefstars.txt"))
"""


@pytest.mark.parametrize("umask", _umasks())
def test_the_copy_s_mode_is_set_whatever_the_umask_at_the_star_read(tmp_path_factory, launch, umask):
    out, left = _child(tmp_path_factory, 0o022, _LATE, f"{umask:o}")
    assert out["import"] is None and _no_error(out["main"]), out
    assert out["copy_lstat"] == {"dir": False, "file": True, "mode": 0o600, "mine": True}, out["copy_lstat"]
    usual, _ = launch(0o022)
    assert out["stars"] == usual["stars"], out["stars"]
    assert left == [], left


# ---------------------------------------------------------------------------
# FM2's guarantees, under each umask.

_STRAY = r"""
def body():
    from streamlit.testing.v1 import AppTest
    out["clean"] = bits(moon())
    stray = os.path.join(ephemeris._EPHEMERIS_FOLDER, "sedeltat.txt")
    with open(stray, "w") as fh:
        fh.write("".join(f"{y} 360.00\n" for y in range(1995, 2036)))
    os.chmod(stray, 0o600)
    out["new_thread"] = in_a_thread(moon)
    out["pointed_thread"] = bits(moon())
    at = AppTest.from_file(ARGS[0], default_timeout=240).run(timeout=240)
    out["page"] = {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
    os.remove(stray)
    out["new_thread_after"] = in_a_thread(moon)
"""

EPHEMERIS_REFUSAL = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                     "Close the app and open it again.")
# Ruling 121, the owner's words, for every case where no private folder can
# be made (ruling 120); FM2's sentence above stays for its two refusals.
EPHEMERIS_FOLDER_REFUSAL = ("Nothing is calculated: this app could not make a private folder for its ephemeris "
                            "in the computer's temporary folder.")


@pytest.mark.parametrize("umask", _umasks())
def test_a_stray_file_refuses_new_threads_and_the_page_says_the_sentence_under_any_umask(tmp_path_factory, umask):
    """FM2's first refusal: a file in the folder the app did not put there.
    A new thread is refused with the engine's own refusal, the page says the
    one sentence, a thread already pointed goes on, and once the file is gone
    a new thread computes."""
    out, left = _child(tmp_path_factory, umask, _STRAY, APP_PATH)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    refused = out["new_thread"]
    assert refused.get("error") == "EphemerisRefused" and "while" in refused["text"], refused
    assert out["pointed_thread"] == out["clean"] == out["new_thread_after"], out
    assert out["page"] == {"exceptions": [], "errors": [EPHEMERIS_REFUSAL]}, out["page"]
    assert left == [], left


_DELTA_T = r"""
def body():
    import swisseph
    out["clean"] = in_a_thread(moon)
    def reached_first():
        swisseph.deltat_ex(JD2000, -1)                # the working directory's Delta T file, before the engine
        return moon()
    out["reached_first"] = in_a_thread(reached_first)
    out["fresh"] = in_a_thread(moon)
"""


@pytest.mark.parametrize("umask", _umasks())
def test_a_thread_that_read_a_delta_t_file_first_is_refused_under_any_umask(tmp_path_factory, umask):
    """FM2's second refusal: a thread whose library read a Delta T file (the
    working directory's) before its first engine call."""
    place = tmp_path_factory.mktemp("cwd")
    (place / "sedeltat.txt").write_text("".join(f"{y} 360.00\n" for y in range(1995, 2036)))
    out, left = _child(tmp_path_factory, umask, _DELTA_T, cwd=place)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert _no_error(out["clean"]) and out["fresh"] == out["clean"], out
    assert out["reached_first"].get("error") == "EphemerisRefused", out["reached_first"]
    assert left == [], left


_CLEANER = r"""
def body():
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    shutil.rmtree(first)                              # a temporary-files cleaner
    os.mkdir(first)                                   # and a directory anyone may write into, with a file
    PLANTED.append(first)
    os.chmod(first, 0o777)
    with open(os.path.join(first, "theirs.txt"), "w") as fh:
        fh.write("not the engine's\n")
    out["chart"] = in_a_thread(moon)
    out["stars"] = in_a_thread(stars)
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    out["second_lstat"] = described(second)
    grab("listing", lambda: sorted(os.listdir(second)))
    out["copy_lstat"] = described(os.path.join(second, "sefstars.txt"))
"""


@pytest.mark.parametrize("umask", _umasks())
def test_what_stands_at_a_removed_folder_s_path_is_neither_adopted_nor_removed_under_any_umask(
        tmp_path_factory, launch, umask):
    """FM2's lstat check and its removal of only the directory made: after a
    cleaner, a 0777 directory at the old path is not used; a new 0700
    folder of this user's is made, with the copy; a normal exit removes it
    and leaves the other directory where it stands."""
    out, left = _child(tmp_path_factory, umask, _CLEANER)
    first = out.get("first")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert out["second"] != first and out["made"][-1] == out["second"], out
        assert out["second_lstat"] == {"dir": True, "file": False, "mode": 0o700, "mine": True}, out["second_lstat"]
        assert out["listing"] == ["sefstars.txt"], out["listing"]
        assert out["copy_lstat"] == {"dir": False, "file": True, "mode": 0o600, "mine": True}, out["copy_lstat"]
        usual, _ = launch(0o022)
        assert out["stars"] == usual["stars"] and out["chart"] == usual["main"]["bodies"]["Moon"][0], out
        assert left == [] and not os.path.lexists(out["second"]), "the folder the engine made was not removed at exit"
        assert os.path.isfile(os.path.join(first, "theirs.txt")), "the directory the engine did not make was removed"
    finally:
        if first and os.path.isdir(first) and not os.path.islink(first):
            shutil.rmtree(first, ignore_errors=True)


_COPY_LINK = r"""
def body():
    outside = ARGS[0]
    copy = os.path.join(ephemeris._EPHEMERIS_FOLDER, "sefstars.txt")
    os.symlink(outside, copy)                         # a link where the copy goes, before the first star read
    out["stars"] = in_a_thread(lambda: [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD2000)])
    with open(outside, "rb") as fh:
        out["outside"] = hashlib.sha256(fh.read()).hexdigest()
    out["still_a_link"] = os.path.islink(copy)
"""


@pytest.mark.parametrize("umask", _umasks())
def test_a_link_in_place_of_the_copy_is_not_followed_under_any_umask(tmp_path_factory, umask):
    """FM2's O_NOFOLLOW: the copy is not written through a link put in its
    place, and no star is computed from what the link names."""
    outside = tmp_path_factory.mktemp("outside") / "sefstars.txt"
    text = SHIPPED.read_text(encoding="latin-1").splitlines(True)
    moved = [ln.replace(",ICRS,03,", ",ICRS,04,", 1) if ln.startswith("Algol ") else ln for ln in text]
    assert moved != text
    outside.write_text("".join(moved), encoding="latin-1")
    before = hashlib.sha256(outside.read_bytes()).hexdigest()
    out, left = _child(tmp_path_factory, umask, _COPY_LINK, outside)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["outside"] == before, "the copy was written through the link"
    assert out["stars"] == [False, None] and out["still_a_link"] is True, out
    assert left == [], left


# ---------------------------------------------------------------------------
# Where nothing can make the folder usable.

_UNUSABLE = r"""
def body():
    from streamlit.testing.v1 import AppTest
    first = ephemeris._EPHEMERIS_FOLDER
    out["clean"] = bits(moon())                       # the importing thread, pointed at the folder
    out["stars_before"] = bits(stars())
    os.umask(0o444)
    os.chmod = lambda *a, **k: None                   # a filesystem that keeps no modes
    shutil.rmtree(first)                              # a temporary-files cleaner
    out["new_thread"] = in_a_thread(moon)
    out["again"] = in_a_thread(moon)
    grab("stars_after", lambda: [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD)])
    at = AppTest.from_file(ARGS[0], default_timeout=240).run(timeout=240)
    out["page"] = {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
    out["pointed_thread"] = bits(moon())
    out["standing"] = [p for p in MADE if os.path.lexists(p)]
"""


def test_a_folder_nothing_can_make_usable_is_refused_with_the_page_s_one_sentence(tmp_path_factory):
    """After a cleaner removed the folder, on a filesystem that keeps no
    modes (os.chmod does nothing) under umask 0o444, no folder the engine
    makes can be its own 0700 one. A new thread is refused with the engine's
    refusal, not a raw PermissionError; each such folder is removed, not left
    behind; the star read is refused as stars are; the page says the
    folder's sentence (ruling 121) and nothing else; a thread already pointed goes on."""
    out, left = _child(tmp_path_factory, 0o022, _UNUSABLE, APP_PATH)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    for key in ("new_thread", "again"):
        assert out[key].get("error") == "EphemerisFolderRefused", (key, out[key])
    assert out["stars_after"] == [False, None], out["stars_after"]
    assert out["page"] == {"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL]}, out["page"]
    assert out["pointed_thread"] == out["clean"], out
    assert out["standing"] == [] and left == [], (out["standing"], left)


_RACED = r"""
def body():
    folder = ephemeris._EPHEMERIS_FOLDER
    out["clean"] = in_a_thread(moon)
    real, raced = os.listdir, []
    def listdir(path=".", *a, **k):
        if not raced and os.fspath(path) == ephemeris._EPHEMERIS_FOLDER:
            raced.append(path)
            shutil.rmtree(path)                       # a cleaner, between the guard's check and its listing
        return real(path, *a, **k)
    os.listdir = listdir
    out["raced"] = in_a_thread(moon)
    out["next"] = in_a_thread(moon)
    out["raced_at"] = list(raced)
    out["moved"] = ephemeris._EPHEMERIS_FOLDER != folder
    out["folder_after"] = described(ephemeris._EPHEMERIS_FOLDER)
    raced.clear()                                     # again, in a page run's own thread
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(ARGS[0], default_timeout=240).run(timeout=240)
    out["page"] = {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
    out["raced_in_page"] = list(raced)
    os.listdir = real
"""


def test_a_folder_removed_between_the_check_and_the_listing_is_refused_then_made_again(tmp_path_factory):
    """A cleaner can remove the folder after the guard found it this user's
    and before it lists it: that thread is refused with the engine's own
    refusal, not a raw FileNotFoundError, and the next thread makes a new
    folder and computes the same Moon. A page run caught in the same window
    says the folder's sentence (ruling 121): at that moment there is no
    private folder, and no file was found."""
    out, left = _child(tmp_path_factory, 0o022, _RACED, APP_PATH)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["raced_at"], "the listing was never reached"
    assert out["raced"].get("error") == "EphemerisFolderRefused", out["raced"]
    assert _no_error(out["clean"]) and out["next"] == out["clean"], out
    assert out["raced_in_page"], "the page run's listing was never reached"
    assert out["page"] == {"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL]}, out["page"]
    assert out["moved"] and out["folder_after"] == {"dir": True, "file": False, "mode": 0o700, "mine": True}, out
    assert left == [], left



_NO_MKDTEMP = r"""
def body():
    import errno
    from streamlit.testing.v1 import AppTest
    first = ephemeris._EPHEMERIS_FOLDER
    out["clean"] = bits(moon())                       # the importing thread, pointed at the folder
    out["stars_before"] = bits(stars())
    if ARGS[0] == "temporary-directory-gone":         # a cleaner takes the temporary directory with the folder
        shutil.rmtree(os.path.dirname(first))
    else:                                             # "disk-full": the folder goes, and no new one can be made
        shutil.rmtree(first)
        made = tempfile.mkdtemp
        def full(*a, **k):
            if k.get("prefix") == "zij-ephemeris-":
                raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
            return made(*a, **k)
        tempfile.mkdtemp = full
    out["new_thread"] = in_a_thread(moon)
    grab("stars_after", lambda: [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD)])
    at = AppTest.from_file(ARGS[1], default_timeout=240).run(timeout=240)
    out["page"] = {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
    out["pointed_thread"] = bits(moon())
"""


@pytest.mark.parametrize("cause", ["temporary-directory-gone", "disk-full"])
def test_a_folder_that_cannot_be_made_at_all_is_refused_with_the_page_s_one_sentence(tmp_path_factory, short_root,
                                                                                     cause):
    """After a cleaner removed the folder, no new one can be made at all: the
    temporary directory went with it, or the disk is full. A new thread is
    refused with the engine's refusal, not a raw OSError; the star read is
    refused as stars are; the page says the folder's sentence (ruling 121)
    and nothing else;
    a thread already pointed goes on. The temporary directory is the test's
    own short one (short_root)."""
    tmpdir = os.path.join(short_root, "tmpdir")
    os.mkdir(tmpdir)
    out, left = _child(tmp_path_factory, 0o022, _NO_MKDTEMP, cause, APP_PATH, tmpdir=tmpdir)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["made"] and os.path.dirname(out["made"][0]) == str(tmpdir), out["made"]
    assert out["new_thread"].get("error") == "EphemerisFolderRefused", out["new_thread"]
    assert out["stars_after"] == [False, None], out["stars_after"]
    assert out["page"] == {"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL]}, out["page"]
    assert out["pointed_thread"] == out["clean"], out
    assert left == [], left


# ---------------------------------------------------------------------------
# Rulings 120 and 121: each refusal its own sentence, and the import itself
# caught in app.py.

def _assigned(paths, name):
    """The one top-level assignment of `name` in `paths` (one file, or the
    engine's modules: wherever the list puts the code)."""
    paths = [paths] if hasattr(paths, "read_text") else list(paths)
    values = [ast.literal_eval(node.value) for path in paths
              for node in ast.parse(path.read_text(encoding="utf-8")).body
              if isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == [name]]
    assert len(values) == 1, ([p.name for p in paths], name, values)
    return values[0]


def test_the_folder_sentence_is_the_owner_s_and_app_py_holds_the_same_words():
    """Ruling 121's words, once in the engine for the page's check and once
    in app.py for a refusal at import, when the engine never loaded: the two
    are one sentence. Neither names a path or a file; FM2's sentence is
    unchanged and is not this one."""
    from conftest import engine_files
    in_engine = _assigned(engine_files(), "EPHEMERIS_FOLDER_REFUSAL")
    in_app = _assigned(APP_PATH, "_EPHEMERIS_FOLDER_REFUSAL_AT_IMPORT")
    assert in_engine == in_app == EPHEMERIS_FOLDER_REFUSAL, (in_engine, in_app)
    assert _assigned(engine_files(), "EPHEMERIS_REFUSAL") == EPHEMERIS_REFUSAL != EPHEMERIS_FOLDER_REFUSAL
    for sentence in (EPHEMERIS_FOLDER_REFUSAL, EPHEMERIS_REFUSAL):
        assert "/" not in sentence and "\\" not in sentence and ".txt" not in sentence and "zij-" not in sentence


_IMPORT_PAGE = r"""
import json, os, stat, sys, tempfile
os.umask(int(sys.argv[1], 8))
app = sys.argv[2]
made = []
_mkdtemp = tempfile.mkdtemp
def _watched(*a, **k):
    path = _mkdtemp(*a, **k)
    if os.path.basename(path).startswith("zij-ephemeris-"):
        made.append(os.path.abspath(path))
    return path
tempfile.mkdtemp = _watched
# A filesystem that keeps no modes (a vfat or drvfs TMPDIR): chmod does
# nothing, and every directory the engine makes reads 0755.
os.chmod = lambda *a, **k: None
_lstat = os.lstat
def lstat(path, *a, **k):
    st = _lstat(path, *a, **k)
    if os.path.basename(os.fspath(path)).startswith("zij-ephemeris-") and stat.S_ISDIR(st.st_mode):
        fields = list(st)
        fields[0] = stat.S_IFDIR | 0o755
        return os.stat_result(fields)
    return st
os.lstat = lstat
from streamlit.testing.v1 import AppTest
pages = []
for _ in range(2):                                    # a rerun tries the import again
    at = AppTest.from_file(app, default_timeout=240).run(timeout=240)
    pages.append({"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]})
print("IMPORT " + json.dumps({"pages": pages, "made": made, "engine_loaded": "engine" in sys.modules,
                              "standing": [p for p in made if os.path.lexists(p)]}))
"""


@pytest.mark.parametrize("umask", _umasks(only=(0o022, 0o444)))
def test_a_launch_where_no_private_folder_can_be_made_says_the_folder_sentence_not_an_exception(tmp_path_factory, umask):
    """Ruling 120: on a filesystem that keeps no modes the engine's import
    itself refuses (no private folder, so nothing is computed); app.py
    catches it where it imports the engine, and the page says ruling 121's
    sentence and nothing else, on every rerun. No folder is left behind."""
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    cwd = tmp_path_factory.mktemp("cwd")
    try:
        done = subprocess.run([sys.executable, "-c", _IMPORT_PAGE, f"{umask:o}", str(APP_PATH)], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=TIMEOUT)
    finally:
        for place in (env["XDG_DATA_HOME"], str(cwd)):
            _owner_may_remove(place)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("IMPORT ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    out = json.loads(lines[-1][len("IMPORT "):])
    for path in out["standing"]:
        _remove(path)
    assert out["made"] and out["engine_loaded"] is False, out
    assert out["pages"] == [{"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL]}] * 2, out["pages"]
    assert out["standing"] == [], out["standing"]


_DELTA_T_PAGE = r"""
def body():
    from streamlit.testing.v1 import AppTest
    wrapper = os.path.join(ARGS[1], "reached_first.py")
    with open(wrapper, "w") as fh:                    # the run's own thread reads cwd's Delta T file first
        fh.write("import runpy, swisseph\nswisseph.deltat_ex(2451545.0, -1)\n"
                 f"runpy.run_path({ARGS[0]!r}, run_name='__main__')\n")
    at = AppTest.from_file(wrapper, default_timeout=240).run(timeout=240)
    out["page"] = {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
"""


def test_a_delta_t_thread_keeps_fm2_s_sentence(tmp_path_factory):
    """Ruling 121 leaves FM2's sentence to its two refusals: a page run whose
    thread read a Delta T file first says FM2's, not the folder's. (The stray
    file's page is pinned under every umask above.)"""
    place = tmp_path_factory.mktemp("cwd")
    (place / "sedeltat.txt").write_text("".join(f"{y} 360.00\n" for y in range(1995, 2036)))
    out, left = _child(tmp_path_factory, 0o022, _DELTA_T_PAGE, APP_PATH, tmp_path_factory.mktemp("wrapper"), cwd=place)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["page"] == {"exceptions": [], "errors": [EPHEMERIS_REFUSAL]}, out["page"]
    assert left == [], left


# ---------------------------------------------------------------------------
# Ruling 122: a temporary folder whose name Swiss Ephemeris cannot take whole
# is a "no private folder" case too; and an error of any other kind at the
# engine's import is still raised, not said as that sentence.

_LAUNCH_PAGE = r"""
import json, os, sys, tempfile
app, case = sys.argv[1], sys.argv[2]
made = []
_mkdtemp = tempfile.mkdtemp
def _watched(*a, **k):
    path = _mkdtemp(*a, **k)
    if os.path.basename(path).startswith("zij-ephemeris-"):
        made.append(os.path.abspath(path))
    return path
tempfile.mkdtemp = _watched
if case in ("RuntimeError", "ImportError"):
    # An error of another kind while the engine is imported: the library
    # itself fails to load.
    class Broken:
        def find_spec(self, name, path=None, target=None):
            if name != "swisseph":
                return None
            if case == "RuntimeError":
                raise RuntimeError("an unrelated failure while the engine loads")
            raise ImportError("an unrelated failure while the engine loads")
    sys.meta_path.insert(0, Broken())
from streamlit.testing.v1 import AppTest
pages = []
for _ in range(2):                                    # a rerun tries the import again
    at = AppTest.from_file(app, default_timeout=240).run(timeout=240)
    pages.append({"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]})
print("LAUNCH " + json.dumps({"pages": pages, "made": made, "engine_loaded": "engine" in sys.modules,
                              "tempdir": tempfile.gettempdir()}))
"""


def _launch_page(tmp_path_factory, case, tmpdir=None):
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    done = subprocess.run([sys.executable, "-c", _LAUNCH_PAGE, str(APP_PATH), case], cwd=tmp_path_factory.mktemp("cwd"),
                          env=env, capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("LAUNCH ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    out = json.loads(lines[-1][len("LAUNCH "):])
    out["standing"] = [p for p in out["made"] if os.path.lexists(p)]    # after the process exited
    for path in out["standing"]:
        _remove(path)
    return out


@pytest.mark.parametrize("case", ["colon", "too-long"])
def test_a_temporary_folder_name_swiss_ephemeris_cannot_take_whole_says_the_folder_sentence(tmp_path_factory, case):
    """Ruling 122: where the temporary folder's name cannot be given to Swiss
    Ephemeris whole -- a ':' in it, or longer than the library takes -- no
    private folder can be had: the folder made is removed, the engine's
    import refuses, and the page says ruling 121's sentence and nothing
    else, on every rerun."""
    base = tmp_path_factory.mktemp("tmpdir")
    if case == "colon":
        tmpdir = base / "temporary:folder"
    else:                                             # the folder's name past 200 characters
        tmpdir = base / ("t" * 120) / ("u" * 120)
    tmpdir.mkdir(parents=True)
    out = _launch_page(tmp_path_factory, case, tmpdir)
    assert out["tempdir"] == str(tmpdir), out["tempdir"]
    made = out["made"]
    assert len(made) == 2, made                       # one per run, each removed
    assert [os.path.dirname(p) for p in made] == [str(tmpdir)] * 2, made
    assert [":" in p or len(p) > 200 for p in made] == [True, True], made   # names the library cannot take whole
    assert out["engine_loaded"] is False, out
    assert out["pages"] == [{"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL]}] * 2, out["pages"]
    assert out["standing"] == [], out["standing"]


@pytest.mark.parametrize("case", ["RuntimeError", "ImportError"])
def test_an_unrelated_error_at_the_engine_s_import_is_raised_not_said_as_the_folder_sentence(tmp_path_factory, case):
    """app.py catches only the engine's "no private folder" refusal where it
    imports the engine: any other error while the engine loads still shows
    as itself, and the folder's sentence is not said."""
    out = _launch_page(tmp_path_factory, case)
    assert out["engine_loaded"] is False and len(out["pages"]) == 2, out
    _shows_itself(out["pages"][0])
    _shows_itself(out["pages"][1])
    assert out["standing"] == [], out["standing"]


def _shows_itself(page):
    assert page["errors"] == [] and len(page["exceptions"]) == 1, page
    assert "an unrelated failure while the engine loads" in page["exceptions"][0], page
