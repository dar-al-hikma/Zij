"""The ephemeris folder counted in bytes, and exit cleanup that a replacement
cannot pass (lane LS; the owner's rulings 138 and 139).

Ruling 138. Swiss Ephemeris is handed the engine's folder as bytes -- the
name's UTF-8 form through its path setter, the filesystem's form through
$SE_EPHE_PATH -- and on the pinned wheel takes a path whole only up to 242
bytes; past that it searches its compiled default, the working directory
first, where a star catalogue or a Delta T file changes values with no
refusal. The guard counted characters, so a folder under a temporary
directory with non-ASCII characters in its name could be 199 characters and
over 300 bytes, and pass. The guard now counts bytes, at 200; a folder with
no UTF-8 form is refused too, never raised. Pinned here: the guard at 200
bytes taken and 201 refused for characters of one to four bytes; the wheel's
own limit, 242 taken and 243 not, measured in fresh processes, so the
margin's basis is pinned; the reproduction's launch end to end; and the
guard on the folder found again at import and on the folder in use when a
thread is pointed at it.

Ruling 139. Exit cleanup compared the (st_dev, st_ino) it recorded with
what stood at the folder's path; where a cleaner removed the folder and a
filesystem gave a directory made at its path the freed number, exit removed
that directory and what was in it. The engine now holds a descriptor on the
folder from its making: while it is open the inode cannot be reused, and its
link count shows the removal. The replacement test forces the old identity
onto the replacement -- every lstat, stat and fstat of it reports the old
number, as on a filesystem that reused it -- so it does not depend on this
machine's allocator.

Of the first 25 cases, all failed at main (4c741bd). The guard took every 201-byte name of
two- to four-byte characters, the three names the library cannot be handed,
and the one whose two forms differ; it has no bound in bytes (the one-byte
case and the wheel's case fail there on that alone: the wheel's own limit,
measured, is the same at main). The launch under each non-ASCII temporary
directory drew the page with no refusal, and under the undecodable one
raised the path setter's UnicodeEncodeError onto the page. Both routes used
the long folder. Exit removed the forced replacement and its file after a
plain import, a reload and a fresh import. No descriptor was held, under
any umask or across the imports; the parts of those cases that say every
folder made is removed at exit and a forked child's exit leaves it pass at
main too: they are what must not move.

The blind check (LS_CHECK.md, item 5) found that the replacement with a file
in it kept every removal by name from taking it, so no case held the
identity check itself. Five cases came after it. An empty replacement, which
a removal by name would take, after a cleaner that removed the folder (its
own identity; the old one forced) and one that moved it away: kept. A
program the process starts holds no descriptor on the folder. Where no
descriptor can be had (EMFILE), the folder's refusal, nothing computed, the
folder removed. The two empty cases with their own identity pass at main
(its comparison of numbers keeps them, numbers being unique there); they
fail when either of the head's two checks is dropped. The long folders are
built under a short folder of the tests' own (short_base), so a deep TMPDIR
on the runner cannot fail them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR
from ephemeris_check_count import CHECK_COUNT, indented
from test_fm3_ephemeris_folder_umask_2026_10_07 import UMASKS, _child, _no_error, _umasks

TIMEOUT = 300
JD2000 = 2451545.0
SHIPPED = EXECUTABLE_DIR / "ephe" / "sefstars.txt"
BOUND = 200                                           # the guard's, in bytes
WHEEL = 242                                           # the pinned wheel's, in bytes, measured below
PREFIX_AND_NAME = len("/zij-ephemeris-") + 8          # tempfile.mkdtemp's name under TMPDIR, 23 ASCII bytes

# Ruling 121's sentence, the owner's words.
EPHEMERIS_FOLDER_REFUSAL = ("Nothing is calculated: this app could not make a private folder for its ephemeris "
                            "in the computer's temporary folder.")

WIDTHS = {1: "a", 2: "ع", 3: "天", 4: "\U0001F31F"}   # a, Arabic ain, CJK heaven, a star


def _env(tmp_path_factory, **extra):
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    env.update(extra)
    return env


def _planted_catalogue():
    """The shipped catalogue with Algol's right ascension moved an hour."""
    text = SHIPPED.read_text(encoding="latin-1").splitlines(True)
    moved = [ln.replace(",ICRS,03,", ",ICRS,04,", 1) if ln.startswith("Algol ") else ln for ln in text]
    assert moved != text
    return "".join(moved)


def _planted_cwd(tmp_path_factory, deltat=False):
    place = tmp_path_factory.mktemp("planted-cwd")
    (place / "sefstars.txt").write_text(_planted_catalogue(), encoding="latin-1")
    if deltat:                                        # Delta T near 1000 s: every planet would move
        (place / "swe_deltat.txt").write_text("".join(f"{y} 1063.54\n" for y in range(1995, 2036)))
    return place


def _name_of_bytes(total, char):
    """An absolute name of exactly `total` UTF-8 bytes, `char` as far as it
    goes and ASCII 'a' after it, in one component (the guard is a pure
    function of the name)."""
    width = len(char.encode("utf-8"))
    body = total - 1
    name = "/" + char * (body // width) + "a" * (body % width)
    assert len(name.encode("utf-8")) == total
    return name


# ---------------------------------------------------------------------------
# Ruling 138: the guard.

@pytest.mark.parametrize("width", sorted(WIDTHS))
def test_the_guard_takes_200_bytes_and_refuses_201_whatever_the_characters(engine, width):
    """200 bytes taken, 201 refused, for characters of one to four bytes.
    Each name is within 200 characters but the one-byte 201 (which cannot
    be: its bytes are its characters); for two to four bytes the 201-byte
    name is 101, 68 and 51 characters, which a count of characters took."""
    safe = engine["_ephemeris_folder_is_safe"]
    taken, refused = _name_of_bytes(BOUND, WIDTHS[width]), _name_of_bytes(BOUND + 1, WIDTHS[width])
    assert len(taken) <= 200 and (width == 1 or len(refused) <= 200), (len(taken), len(refused))
    assert safe(taken) is True, (width, len(taken), len(taken.encode()))
    assert safe(refused) is False, (width, len(refused), len(refused.encode()))
    assert engine["_EPHEMERIS_FOLDER_BYTES"] == BOUND < WHEEL


@pytest.mark.parametrize("name", ["/tmp/zij-\udcff", "/tmp/zij-\ud83c", "/tmp/zij\x00ephemeris"],
                         ids=["undecodable-byte", "lone-surrogate", "nul"])
def test_a_name_the_library_cannot_be_handed_is_refused_not_raised(engine, name):
    """A byte the filesystem's encoding could not decode comes back as a
    lone surrogate, which the path setter cannot encode (it raises); a NUL
    neither route carries. Refused, and the guard does not raise."""
    assert engine["_ephemeris_folder_is_safe"](name) is False


def test_a_name_whose_two_forms_differ_is_refused(engine, monkeypatch):
    """Where the filesystem's encoding is not UTF-8, $SE_EPHE_PATH would
    carry one name and the path setter another: refused unless they agree."""
    safe = engine["_ephemeris_folder_is_safe"]
    monkeypatch.setattr(os, "fsencode", lambda name: os.fspath(name).encode("latin-1"))
    assert safe("/tmp/zij-ephemeris-plain") is True
    assert safe("/tmp/zij-éphéméris") is False


@pytest.fixture
def short_base():
    """A folder of this test's own under /tmp (or, where /tmp is not a
    writable directory, the temporary folder), removed after it: the long
    folders are built under it, so the depth of pytest's base temporary
    directory (a runner's TMPDIR) cannot leave too little room for them."""
    root = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK | os.X_OK) else tempfile.gettempdir()
    base = tempfile.mkdtemp(prefix="zij-ls-", dir=root)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# The wheel's own limit, measured.

_WHEEL = r"""
import json, os, sys
route, folder = sys.argv[1], sys.argv[2]
os.environ.pop("SE_EPHE_PATH", None)
if route == "env":
    os.environ["SE_EPHE_PATH"] = folder
import swisseph as swe
swe.set_ephe_path(folder if route == "api" else None)
try:
    out = swe.fixstar2_ut("Algol", 2451545.0, swe.FLG_MOSEPH)[0][0].hex()
except Exception as exc:
    out = "error: " + str(exc)
print("WHEEL " + json.dumps(out))
"""


def _folder_of_bytes(base, total, char):
    """A real folder whose absolute name is exactly `total` UTF-8 bytes,
    `char` as far as it goes, in components of at most 200 bytes."""
    path = os.fsencode(str(base))
    left = total - len(path)
    width = len(char.encode("utf-8"))
    parts = []
    while left > 0:
        size = min(200, left - 1)
        if left - 1 - size == 1:                      # leave no remainder too short for '/' and a byte
            size -= 1
        parts.append(char * (size // width) + "a" * (size % width))
        left -= 1 + size
    folder = os.path.join(str(base), *parts)
    assert len(folder.encode("utf-8")) == total, (len(folder.encode("utf-8")), total)
    os.makedirs(folder)
    return folder


def _wheel_runs(tmp_path_factory, cases):
    """Each case (route, folder) in a fresh process, from a working
    directory holding the planted catalogue."""
    cwd = _planted_cwd(tmp_path_factory)
    env = _env(tmp_path_factory)
    runs = [subprocess.Popen([sys.executable, "-c", _WHEEL, route, folder], cwd=cwd, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for route, folder in cases]
    seen = []
    for run in runs:
        out, err = run.communicate(timeout=TIMEOUT)
        lines = [ln for ln in out.splitlines() if ln.startswith("WHEEL ")]
        assert run.returncode == 0 and lines, err[-2000:]
        seen.append(json.loads(lines[-1][len("WHEEL "):]))
    return seen


def test_the_wheel_takes_a_folder_of_242_bytes_whole_and_not_243(engine, tmp_path_factory, short_base):
    """The margin's basis: on both routes, with one- and four-byte
    characters, a folder of 242 bytes holding the shipped catalogue is read;
    at 243 bytes the library reads the working directory's planted one. The
    guard's bound, in the same unit, is under it."""
    assert engine["_EPHEMERIS_FOLDER_BYTES"] == BOUND < WHEEL
    real_place = tmp_path_factory.mktemp("real")
    shutil.copyfile(SHIPPED, real_place / "sefstars.txt")
    planted_place = tmp_path_factory.mktemp("planted")
    (planted_place / "sefstars.txt").write_text(_planted_catalogue(), encoding="latin-1")
    cases, labels = [("api", str(real_place)), ("api", str(planted_place))], ["real", "planted"]
    for width in (1, 4):
        for total in (WHEEL, WHEEL + 1):
            base = tempfile.mkdtemp(prefix=f"w{width}-", dir=short_base)   # short, whatever the runner's TMPDIR
            folder = _folder_of_bytes(base, total, WIDTHS[width])
            shutil.copyfile(SHIPPED, os.path.join(folder, "sefstars.txt"))
            for route in ("api", "env"):
                cases.append((route, folder))
                labels.append((width, total, route, len(folder)))
    assert len(labels) == 10
    seen = dict(zip(map(str, labels), _wheel_runs(tmp_path_factory, cases)))
    real, planted = seen["real"], seen["planted"]
    assert not real.startswith("error") and not planted.startswith("error") and real != planted, seen
    for label in labels[2:]:
        width, total, route, chars = label
        expected = real if total <= WHEEL else planted
        assert seen[str(label)] == expected, (label, seen[str(label)], {"real": real, "planted": planted})
        if width == 4:
            assert chars < 200, label                 # far fewer characters than bytes


# ---------------------------------------------------------------------------
# The reproduction's launch, end to end.

_LAUNCH = r"""
import json, os, sys, tempfile
app = sys.argv[1]
made = []
_mkdtemp = tempfile.mkdtemp
def _watched(*a, **k):
    path = _mkdtemp(*a, **k)
    if os.path.basename(path).startswith("zij-ephemeris-"):
        made.append(os.path.abspath(path))
    return path
tempfile.mkdtemp = _watched
from streamlit.testing.v1 import AppTest
pages = []
for _ in range(2):                                    # a rerun tries the import again
    at = AppTest.from_file(app, default_timeout=240).run(timeout=240)
    pages.append({"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error],
                  "algol": any("Algol" in str(m.value) for m in at.markdown),
                  "tables": len(at.table) + len(at.dataframe)})
try:
    import engine
    direct = None
except Exception as exc:
    direct = type(exc).__name__
print("LAUNCH " + json.dumps({"pages": pages, "made": [os.fsencode(p).hex() for p in made],
                              "tempdir": os.fsencode(tempfile.gettempdir()).hex(), "direct": direct,
                              "engine_loaded": "engine" in sys.modules, "swisseph_loaded": "swisseph" in sys.modules}))
"""

# The reproduction's three temporary directories, by the folder's length in
# characters: emoji 182, CJK 188, Arabic 199; each well over 242 bytes.
LONG = {"emoji": (4, 182), "cjk": (3, 188), "arabic": (2, 199)}


def _long_tmpdir(base, width, chars):
    """A temporary directory under `base` that makes the engine's folder
    exactly `chars` characters, its own name all `width`-byte characters,
    in components of at most 60 characters."""
    room = chars - PREFIX_AND_NAME - len(str(base))
    assert room > 1, f"the base folder is too long for this case: {base}"
    parts = []
    while room > 0:
        size = min(60, room - 1)
        if room - 1 - size == 1:
            size -= 1
        parts.append(WIDTHS[width] * size)
        room -= 1 + size
    tmpdir = os.path.join(str(base), *parts)
    os.makedirs(tmpdir)
    return tmpdir


@pytest.mark.parametrize("case", [*LONG, "undecodable"])
def test_a_launch_whose_folder_the_library_cannot_take_whole_is_refused_and_nothing_planted_is_read(
        tmp_path_factory, short_base, case):
    """Under a TMPDIR whose name makes the engine's folder 182-199
    characters and over 242 bytes (or holds a byte with no UTF-8 form), with
    a star catalogue and a Delta T file planted in the working directory:
    the engine's import refuses, the page says the folder's sentence and
    nothing else on every rerun, no star row is printed, the library is
    never loaded (so neither planted file can change a value), and no
    folder is left. The TMPDIR is built under a short folder of the test's
    own (short_base), whatever the runner's temporary directory."""
    base = short_base
    if case == "undecodable":
        tmpdir = os.fsdecode(os.path.join(os.fsencode(str(base)), b"temp\xff"))
        os.mkdir(tmpdir)
    else:
        width, chars = LONG[case]
        tmpdir = _long_tmpdir(base, width, chars)
        folder_chars = len(tmpdir) + PREFIX_AND_NAME
        folder_bytes = len(os.fsencode(tmpdir)) + PREFIX_AND_NAME
        assert folder_chars == chars and 182 <= folder_chars <= 199 and folder_bytes > WHEEL, (folder_chars,
                                                                                               folder_bytes)
    cwd = _planted_cwd(tmp_path_factory, deltat=True)
    done = subprocess.run([sys.executable, "-c", _LAUNCH, str(APP_PATH)], cwd=cwd,
                          env=_env(tmp_path_factory, TMPDIR=tmpdir), capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("LAUNCH ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    out = json.loads(lines[-1][len("LAUNCH "):])
    made = [os.fsdecode(bytes.fromhex(p)) for p in out["made"]]
    standing = [p for p in made if os.path.lexists(p)]
    for path in standing:
        shutil.rmtree(path, ignore_errors=True)
    assert bytes.fromhex(out["tempdir"]) == os.fsencode(tmpdir), out["tempdir"]
    assert out["pages"] == [{"exceptions": [], "errors": [EPHEMERIS_FOLDER_REFUSAL], "algol": False, "tables": 0}] * 2, \
        out["pages"]
    assert len(made) == 3 and all(os.path.dirname(p) == tmpdir for p in made), made   # two reruns and one import
    assert out["direct"] == "EphemerisFolderRefused", out["direct"]
    assert out["engine_loaded"] is False and out["swisseph_loaded"] is False, out
    assert standing == [], standing


# ---------------------------------------------------------------------------
# Every route by which the folder reaches the library is behind the guard.

def _long_private_folder(base):
    """A real 0700 directory of this user's, 199 characters and over 242
    bytes: one the character count took."""
    tmpdir = _long_tmpdir(base, 3, 199)
    folder = tmpdir + "/" + "a" * (PREFIX_AND_NAME - 1)
    os.mkdir(folder, 0o700)
    os.chmod(folder, 0o700)
    assert len(folder) == 199 and len(os.fsencode(folder)) > WHEEL
    return folder


# Every name handed to the library, by either route: $SE_EPHE_PATH as it is
# put into the environment (the os.putenv audit event), and the path setter's
# argument.
_HANDED = r"""
import json, os, sys, threading
long = sys.argv[1]
handed = []
def _audit(event, args):
    if event == "os.putenv" and os.fsdecode(args[0]) == "SE_EPHE_PATH":
        handed.append(["env", os.fsdecode(args[1])])
sys.addaudithook(_audit)
import swisseph
_setter = swisseph.set_ephe_path
def _set(*a, **k):
    handed.append(["setter", a[0] if a else k.get("path")])
    return _setter(*a, **k)
swisseph.set_ephe_path = _set
"""

_FOUND_AT_IMPORT = _HANDED + r"""
swisseph._zij_ephemeris_folder = long                 # as a fresh import finds the folder on the library
held = os.open(long, os.O_RDONLY)
swisseph._zij_ephemeris_held = {long: held}
import engine
import ephemeris
box = []
t = threading.Thread(target=lambda: box.append(engine.calculate_traditional_chart_jd(2451545.0, 43.77, 11.25)["sect"]))
t.start(); t.join(120)
print("FOUND " + json.dumps([ephemeris._EPHEMERIS_FOLDER, os.environ.get("SE_EPHE_PATH"), handed, box]))
"""

_IN_USE = _HANDED + r"""
import engine
import ephemeris                                      # the folder's module, where the folder in use is held
held = os.open(long, os.O_RDONLY)
getattr(ephemeris, "_EPHEMERIS_HELD", {})[long] = held  # (no such record before ruling 139)
ephemeris._EPHEMERIS_FOLDER = long                    # the folder in use, as a thread next points at it
box = []
t = threading.Thread(target=lambda: box.append(engine.calculate_traditional_chart_jd(2451545.0, 43.77, 11.25)["sect"]))
t.start(); t.join(120)
print("FOUND " + json.dumps([ephemeris._EPHEMERIS_FOLDER, os.environ.get("SE_EPHE_PATH"), handed, box]))
"""


@pytest.mark.parametrize("route", ["found-at-import", "in-use-at-a-thread-s-first-call"])
def test_a_folder_the_library_cannot_take_whole_is_never_handed_to_it(tmp_path_factory, short_base, route):
    """The folder reaches the library by $SE_EPHE_PATH (set at import and
    when a thread is pointed at it) and by the path setter (each thread's
    first call, and the Delta T reference's thread), always the folder the
    engine holds at that moment. Where that is one the library cannot take
    whole -- found again at a fresh import, or in use when a thread is next
    pointed at it -- a new folder is made, and the long one is handed to
    neither route."""
    long = _long_private_folder(short_base)
    code = _FOUND_AT_IMPORT if route == "found-at-import" else _IN_USE
    done = subprocess.run([sys.executable, "-c", code, long], cwd=_planted_cwd(tmp_path_factory, deltat=True),
                          env=_env(tmp_path_factory), capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("FOUND ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    found = json.loads(lines[-1][len("FOUND "):])
    folder, variable, handed = found[0], found[1], found[2]
    assert folder != long and variable == folder, found
    assert handed and [name for _route, name in handed if name == long] == [], handed
    assert os.path.isdir(long) and not os.path.exists(folder), "the long folder was removed, or the made one kept"
    assert found[3], found                            # a chart computed after it


# ---------------------------------------------------------------------------
# Ruling 139: exit cleanup and a replacement.

_FORCED = r"""
def body():
    global engine, ephemeris
    import importlib
    mode = ARGS[0]
    runs = {"module": 0, "set": 0}                    # the route's positive control (_RUNS, below)
    def audit(event, args):
        if event == "exec" and getattr(args[0], "co_filename", "").endswith("ephemeris.py"):
            runs["module"] += 1
        elif event == "os.putenv" and os.fsdecode(args[0]) == "SE_EPHE_PATH":
            runs["set"] += 1
    sys.addaudithook(audit)
""" + indented(CHECK_COUNT) + r"""
    out["route_runs"] = {**runs, **counted()}         # the plain import: no route
    if mode == "reload":                              # the folder's module, then the engine
        ephemeris = importlib.reload(ephemeris)
        out["route_runs"] = {**runs, **counted()}     # taken before the engine's step
        engine = importlib.reload(engine)
    elif mode == "fresh-import":                      # both dropped from sys.modules, as Streamlit's watcher does
        del sys.modules["engine"], sys.modules["ephemeris"]
        ephemeris = importlib.import_module("ephemeris")
        out["route_runs"] = {**runs, **counted()}
        engine = importlib.import_module("engine")
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    out["chart_before"] = in_a_thread(moon)
    old = os.lstat(first)
    shutil.rmtree(first)                              # a temporary-files cleaner
    os.mkdir(first)                                   # and a directory made at its path, with a file in it
    PLANTED.append(first)
    os.chmod(first, 0o777)
    with open(os.path.join(first, "theirs.txt"), "w") as fh:
        fh.write("not the engine's\n")
    new = os.lstat(first)
    out["chart"] = in_a_thread(moon)                  # the engine makes its second folder
    out["second"] = ephemeris._EPHEMERIS_FOLDER
    # CONSTRUCTED: the replacement carries the old identity, in every view of
    # it, as on a filesystem that gave it the freed number.
    real = {"lstat": os.lstat, "stat": os.stat, "fstat": os.fstat}
    def forced(st):
        if (st.st_dev, st.st_ino) != (new.st_dev, new.st_ino):
            return st
        fields = list(st)
        fields[1], fields[2] = old.st_ino, old.st_dev
        return os.stat_result(fields)
    os.lstat = lambda *a, **k: forced(real["lstat"](*a, **k))
    os.stat = lambda *a, **k: forced(real["stat"](*a, **k))
    os.fstat = lambda *a, **k: forced(real["fstat"](*a, **k))
    seen = os.lstat(first)
    out["forced"] = (seen.st_dev, seen.st_ino) == (old.st_dev, old.st_ino) != (new.st_dev, new.st_ino)
"""


@pytest.mark.parametrize("mode", ["import", "reload", "fresh-import"])
def test_a_replacement_carrying_the_old_identity_is_kept_at_exit(tmp_path_factory, mode):
    """After a cleaner removes the folder and a directory with a file is made
    at its path, the old (st_dev, st_ino) is forced onto that directory; a
    normal exit keeps it and its file, and removes the folder the engine
    made in its place. After a reload and a fresh import too."""
    out, left = _child(tmp_path_factory, 0o022, _FORCED, mode)
    first = out.get("first")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert out["forced"] is True, out
        # The route's `ephemeris` step ran the folder's module, its check of the
        # folder (its name, then its identity) and set $SE_EPHE_PATH, once each
        # (none for the plain import).
        assert out["route_runs"] == ({"module": 0, "set": 0, "safe": 0, "held": 0} if mode == "import"
                                     else {"module": 1, "set": 1, "safe": 1, "held": 1}), out
        assert out["chart"] == out["chart_before"] and out["second"] != first, out
        assert left == [] and not os.path.lexists(out["second"]), "the folder the engine made was not removed at exit"
        assert os.path.isfile(os.path.join(first, "theirs.txt")), "the directory the engine did not make was removed"
    finally:
        if first and os.path.isdir(first) and not os.path.islink(first):
            shutil.rmtree(first, ignore_errors=True)


# The positive control: the routes are the folder's module's own, so each must
# be seen to run that module's code again and its check of the folder. Each
# execution of ephemeris.py's module code is counted (the "exec" audit event of
# its code object), and so are the check's own calls
# (tests/ephemeris_check_count.py), each look taken at the folder (os.lstat of
# its path) and each time $SE_EPHE_PATH is set (the os.putenv audit event). A
# route's count is taken between its `ephemeris` step and the engine's: the
# engine's import makes a library call, whose guard looks at the folder and
# checks it too, so a count taken after the engine's step would be met
# without the route. Where the `ephemeris` step does not happen, or happens and
# skips the check, its count is nothing and the test fails.
_RUNS = r"""
runs = {"module": 0, "looked": 0, "set": 0}
def _audit(event, args):
    if event == "exec" and getattr(args[0], "co_filename", "").endswith("ephemeris.py"):
        runs["module"] += 1
    elif event == "os.putenv" and os.fsdecode(args[0]) == "SE_EPHE_PATH":
        runs["set"] += 1
sys.addaudithook(_audit)
_lstat = os.lstat
def _looked(path, *a, **k):
    if isinstance(path, str) and os.path.basename(path).startswith("zij-ephemeris-"):
        runs["looked"] += 1
    return _lstat(path, *a, **k)
os.lstat = _looked
""" + CHECK_COUNT + r"""
steps = []
def ephemeris_step(step):
    before = {**runs, **counted()}
    module = step()
    steps.append({k: v - before[k] for k, v in {**runs, **counted()}.items()})
    return module
"""

_ONE_REGISTRATION = r"""
import atexit, importlib, json, os, sys
registered = []
_register = atexit.register
def watched(fn, *a, **k):
    if getattr(fn, "__name__", "") == "_ephemeris_folder_remove":
        registered.append(a[0])
    return _register(fn, *a, **k)
atexit.register = watched
""" + _RUNS + r"""
ephemeris = ephemeris_step(lambda: importlib.import_module("ephemeris"))
import engine
def row():
    folder = ephemeris._EPHEMERIS_FOLDER
    held = getattr(ephemeris, "_EPHEMERIS_HELD", {}).get(folder)
    same = isinstance(held, int) and os.fstat(held)[1:3] == _lstat(folder)[1:3]
    return [folder, held, same, os.environ.get("SE_EPHE_PATH")]
rows = [row()]
ephemeris = ephemeris_step(lambda: importlib.reload(ephemeris))   # the folder's module, then the engine
engine = importlib.reload(engine)
rows.append(row())
del sys.modules["engine"], sys.modules["ephemeris"]   # as Streamlit's watcher drops them
ephemeris = ephemeris_step(lambda: importlib.import_module("ephemeris"))
import engine
rows.append(row())
print("ROWS " + json.dumps([rows, registered, steps]))
"""


def _ran_again(steps):
    """The import, and then each route's `ephemeris` step, counted alone
    (_RUNS): each ran the folder's module once, ran its check of the folder,
    looked at the folder and set $SE_EPHE_PATH once. The routes' positive
    control."""
    assert len(steps) == 3, ("a route's `ephemeris` step did not happen", steps)
    first, *routes = steps
    assert first["module"] == 1 and first["safe"] >= 1 and first["looked"] >= 1 and first["set"] == 1, steps
    for step in routes:
        assert step["module"] == 1, ("the route did not run the folder's module again", steps)
        assert step["safe"] == 1 and step["held"] == 1, ("the route's run did not check the folder", steps)
        assert step["looked"] >= 1, ("the route's run did not look at the folder", steps)
        assert step["set"] == 1, ("the route's run did not set $SE_EPHE_PATH", steps)


def test_the_held_identity_is_found_again_after_a_reload_and_a_fresh_import_with_one_registration(tmp_path_factory):
    """A reload and a fresh import of the folder's module (the engine after
    it) find the folder and the descriptor held on it, register no second
    exit hook, and exit removes the folder. Each route is seen to run the
    module's code and its check again (_ran_again), so the test cannot pass
    because a route no longer reaches the check."""
    done = subprocess.run([sys.executable, "-c", _ONE_REGISTRATION], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory), capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("ROWS ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    rows, registered, steps = json.loads(lines[-1][len("ROWS "):])
    folder = rows[0][0]
    assert len(rows) == 3 and registered == [folder], (rows, registered)
    assert rows == [[folder, rows[0][1], True, folder]] * 3, rows
    _ran_again(steps)
    assert not os.path.exists(folder), "the folder was not removed at exit"


_EXIT = r"""
def body():
    import atexit
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    held = getattr(ephemeris, "_EPHEMERIS_HELD", {}).get(first)
    out["held"] = isinstance(held, int) and os.fstat(held)[1:3] == os.lstat(first)[1:3]
    out["chart"] = in_a_thread(moon)
    grab("stars", stars)                              # the catalogue copied in
    sys.stdout.flush()
    child = os.fork()
    if child == 0:                                    # a forked child's normal exit: its exit hooks run
        atexit._run_exitfuncs()
        os._exit(0)
    os.waitpid(child, 0)
    grab("after_fork", lambda: sorted(os.listdir(first)))
    shutil.rmtree(first)                              # a cleaner
    out["chart_after"] = in_a_thread(moon)
    out["second"] = ephemeris._EPHEMERIS_FOLDER
"""


@pytest.mark.parametrize("umask", _umasks())
def test_every_folder_made_is_removed_at_exit_and_held_from_its_making_under_any_umask(tmp_path_factory, umask):
    """Under each of FM3's umasks: the folder is held by a descriptor on it
    from its making; a forked child's exit leaves it; after a cleaner the
    engine makes a second; and a normal exit leaves no folder it made."""
    assert umask in UMASKS
    out, left = _child(tmp_path_factory, umask, _EXIT)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["held"] is True, out
    assert out["after_fork"] == ["sefstars.txt"], out["after_fork"]
    assert out["chart_after"] == out["chart"] and out["second"] != out["first"], out
    assert len(out["made"]) == 2 and left == [], (out["made"], left)


# ---------------------------------------------------------------------------
# The identity itself (the blind check's item 5): an empty replacement, which
# os.rmdir by name would remove, so only the identity check keeps it.

_EMPTY = r"""
def body():
    cleaner, forcing = ARGS[0], ARGS[1] == "forced"
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    out["chart_before"] = in_a_thread(moon)
    old = os.lstat(first)
    if cleaner == "rename":                           # a cleaner that moves the folder away
        moved = first + "-moved"
        os.rename(first, moved)
        out["moved"] = moved
    else:                                             # a cleaner that removes it
        shutil.rmtree(first)
    os.mkdir(first)                                   # and an empty directory made at its path
    PLANTED.append(first)
    os.chmod(first, 0o777)
    new = os.lstat(first)
    out["chart"] = in_a_thread(moon)                  # the engine makes its second folder
    out["second"] = ephemeris._EPHEMERIS_FOLDER
    if forcing:
        # CONSTRUCTED: the replacement carries the old identity, in every
        # view of it, as on a filesystem that gave it the freed number.
        real = {"lstat": os.lstat, "stat": os.stat, "fstat": os.fstat}
        def forced(st):
            if (st.st_dev, st.st_ino) != (new.st_dev, new.st_ino):
                return st
            fields = list(st)
            fields[1], fields[2] = old.st_ino, old.st_dev
            return os.stat_result(fields)
        os.lstat = lambda *a, **k: forced(real["lstat"](*a, **k))
        os.stat = lambda *a, **k: forced(real["stat"](*a, **k))
        os.fstat = lambda *a, **k: forced(real["fstat"](*a, **k))
    seen = os.lstat(first)
    out["identity"] = "old" if (seen.st_dev, seen.st_ino) == (old.st_dev, old.st_ino) else "new"
"""


@pytest.mark.parametrize("cleaner, forcing", [("rmtree", "unforced"), ("rmtree", "forced"), ("rename", "unforced")])
def test_an_empty_replacement_is_kept_at_exit_by_the_identity_alone(tmp_path_factory, cleaner, forcing):
    """An empty directory at the folder's path after a cleaner, which a
    removal by name would take: kept at a normal exit after a cleaner that
    removed the folder (with its own identity, and with the old one forced
    onto it: the link count tells) and after one that moved the folder away
    (the folder is still linked elsewhere: the identity at the path tells).
    The folder the engine made in its place is removed."""
    out, left = _child(tmp_path_factory, 0o022, _EMPTY, cleaner, forcing)
    first, moved = out.get("first"), out.get("moved")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert out["identity"] == ("old" if forcing == "forced" else "new"), out
        assert out["chart"] == out["chart_before"] and out["second"] != first, out
        assert left == [] and not os.path.lexists(out["second"]), "the folder the engine made was not removed at exit"
        assert os.path.isdir(first) and os.listdir(first) == [], "the empty directory at the folder's path was removed"
    finally:
        for place in (first, moved):
            if place and os.path.isdir(place) and not os.path.islink(place):
                shutil.rmtree(place, ignore_errors=True)


_INHERIT = r"""
def body():
    import subprocess
    folder = ephemeris._EPHEMERIS_FOLDER
    out["folder"] = folder
    grab("stars", stars)
    looks = ("import json, os\n"
             "seen = []\n"
             "for n in os.listdir('/proc/self/fd'):\n"
             "    try:\n"
             "        seen.append(os.readlink('/proc/self/fd/' + n))\n"
             "    except OSError:\n"
             "        pass\n"
             "print(json.dumps(seen))\n")
    out["own"] = json.loads(subprocess.run([sys.executable, "-c", looks.replace("/self/", "/%d/" % os.getpid())],
                                           capture_output=True, text=True, timeout=60).stdout)
    out["child"] = json.loads(subprocess.run([sys.executable, "-c", looks], close_fds=False,
                                             capture_output=True, text=True, timeout=60).stdout)
"""


def test_a_program_the_engine_s_process_starts_holds_no_descriptor_on_the_folder(tmp_path_factory):
    """The descriptor held on the folder is the process's own: a program it
    starts with subprocess, even with close_fds=False, does not inherit it
    (the process itself holds one, so the check has something to find)."""
    out, left = _child(tmp_path_factory, 0o022, _INHERIT)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    folder = out["folder"]
    assert out["own"].count(folder) == 1, out["own"]
    assert folder not in out["child"] and out["child"], out["child"]
    assert left == [], left


_NO_DESCRIPTOR = r"""
def body():
    import errno, resource
    first = ephemeris._EPHEMERIS_FOLDER
    out["clean"] = in_a_thread(moon)
    shutil.rmtree(first)                              # a cleaner: the next thread's call makes a folder
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft, 256), hard))
    fds = []
    try:
        try:
            while True:
                fds.append(os.open(os.devnull, os.O_RDONLY))
        except OSError as exc:
            out["full"] = exc.errno == errno.EMFILE
        out["check"] = in_a_thread(engine.ephemeris_thread_check)
        out["chart_refused"] = in_a_thread(moon)
        out["tried"] = list(MADE[1:])
        out["standing"] = [os.path.lexists(p) for p in MADE[1:]]
    finally:
        for fd in fds:
            os.close(fd)
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    out["after"] = in_a_thread(moon)
"""


def test_a_folder_no_descriptor_can_be_held_on_is_refused_and_removed(tmp_path_factory):
    """With the process's descriptors used up (EMFILE) when a folder must be
    made again: the engine refuses with the folder's refusal, nothing is
    computed, and the folder it made is removed at once; once descriptors
    are free again a thread computes as before."""
    out, left = _child(tmp_path_factory, 0o022, _NO_DESCRIPTOR)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["full"] is True, out
    for key in ("check", "chart_refused"):
        assert out[key].get("error") == "EphemerisFolderRefused" and "held open" in out[key]["text"], (key, out[key])
    assert len(out["tried"]) == 2 and out["standing"] == [False, False], out
    assert out["after"] == out["clean"] and _no_error(out["clean"]), out
    assert left == [], left
