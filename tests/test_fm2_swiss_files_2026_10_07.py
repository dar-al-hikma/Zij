"""Swiss Ephemeris's files: none that Zij does not ship reaches a value (ruling 103).

The library opens files by name from the folders on its ephemeris path:

* ``swe_deltat.txt``, then ``sedeltat.txt`` -- a Delta T table, read once per
  thread and kept for its life, behind every value asked at a moment of
  Universal Time (bodies, houses, sidereal time, sunrise, eclipses, stars);
* ``sefstars.txt``, then the older ``fixstars.cat`` -- the star catalogue;
* ``*.se1`` -- planetary and lunar files (the bodies are Moshier's since lane
  FM, but the path setter still opens the pair);
* ``seleapsec.txt``, ``seorbel.txt``, ``seasnam.txt`` -- leap seconds,
  fictitious bodies' elements, asteroid names: no app call asks for them,
  but a thread whose path reaches one can read it;
* ``eop_1962_today.txt`` and ``eop_finals.txt`` -- read only after a JPL
  ephemeris opens, which no app call asks for;
* ``force.flg`` -- read only by a build with tracing compiled in.

Where it looks: one path per thread. A thread's first call starts it at the
library's compiled default, ``.:/users/ephe2/:/users/ephe/`` (the working
directory first); importing the module sets the importing thread's path; a
path setter takes ``$SE_EPHE_PATH`` over the folder its caller names. So
the places are the working directory (in any thread but the importing one),
``$SE_EPHE_PATH``, a folder some caller set, and ``ephe/`` beside the
engine (the star reader's folder before this lane).

Ruling 103: the engine makes a private folder that holds only a copy of
``ephe/sefstars.txt`` checked against its recorded SHA-256, sets
``$SE_EPHE_PATH`` to it before ``swisseph`` loads, points every thread at it
before the thread's first calculation, looks for no other catalogue, and
keeps Streamlit's caches and reloads from reusing library state a file
reached first.

The matrix runs the engine in a fresh process once with an empty place and
once with a fabricated file there (no file is downloaded; the Delta T, star,
leap-second, element and name files are a few lines of text, the ``.se1``
files text where binary is expected), and compares packed IEEE-754 bits:
the engine's values, and, in every thread the engine computed in (the
asking thread and the star reader), what the library itself returns there
when asked for the file's own kind of value -- Delta T, a UTC conversion, a
fictitious body, an asteroid's name, the Sun at the library's default
flags, a star. A file that changes any of them is reachable. The EOP files,
and the older catalogue format in ``ephe/`` beside the shipped one, are
listed as documented unreachable and not run (no cell of theirs could
fail); the ``force.flg`` cells cannot fail on the pinned wheel either, and
rest on the scan of the wheel's binary.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR
from ephemeris_check_count import CHECK_COUNT

# The sunset chart's moment (2026), Florence (lane FM's), and J2000.
JD = 2461042.1650830186
JD2000 = 2451545.0
LAT, LON = 43.7696, 11.2558
SHIPPED = EXECUTABLE_DIR / "ephe" / "sefstars.txt"
TIMEOUT = 300

_PROBE = r"""
import json, struct, sys, threading
mode, folder = sys.argv[1], sys.argv[2]
JD, JD2000, LAT, LON = map(float, sys.argv[3:7])
import engine
import swisseph as raw
out = {}

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

def grab(key, fn):
    try:
        out[key] = bits(fn())
    except Exception as exc:
        out[key] = {"error": f"{type(exc).__name__}: {exc}"}

def reach(prefix):
    # What the library returns in this thread for each kind of file.
    grab(prefix + "delta_t", lambda: [raw.deltat_ex(JD, -1), raw.deltat_ex(JD2000, -1)])
    grab(prefix + "leap_seconds", lambda: raw.utc_to_jd(2020, 1, 1, 0, 0, 0.0, 1))
    grab(prefix + "elements", lambda: raw.calc_ut(JD, 40, raw.FLG_MOSEPH))
    grab(prefix + "asteroid_name", lambda: raw.get_planet_name(10001 + raw.AST_OFFSET))
    grab(prefix + "default_flags", lambda: raw.calc_ut(JD, raw.SUN))
    grab(prefix + "star", lambda: raw.fixstar2_ut("Algol", JD2000, raw.FLG_MOSEPH))

def chart(jd):
    c = engine.calculate_traditional_chart_jd(jd, LAT, LON)
    return {"bodies": {k: [v["longitude"], v["speed_in_lon"]] for k, v in c["planetary_data"].items()},
            "angles": [c["ascendant"], c["mc"], c["armc"], c["obliquity"]], "sect": c["sect"]}

def run():
    if mode == "path":
        raw.set_ephe_path(folder)
    grab("chart", lambda: chart(JD))
    grab("chart_2000", lambda: chart(JD2000))
    grab("sunrise_sunset", lambda: [engine._rise_trans_sun(JD, LAT, LON, True), engine._rise_trans_sun(JD, LAT, LON, False)])
    grab("sidereal_time", lambda: engine.swe.sidtime(JD))
    grab("stars", lambda: [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD),
                           sorted(engine._FIXED_STAR_STATE.get("missing") or {})])
    reach("thread_")
    engine._on_fixed_star_reader(reach, "reader_")

if mode == "env":
    run()
else:
    worker = threading.Thread(target=run)
    worker.start()
    worker.join(240)
    if worker.is_alive():
        out["timeout"] = True
print("PROBE " + json.dumps(out))
"""


def _algol_an_hour_later(text):
    """The catalogue with Algol's right ascension an hour later (about 11.75
    degrees of longitude): a file that reads, and moves a star."""
    lines = text.splitlines(True)
    moved = [ln.replace(",ICRS,03,", ",ICRS,04,", 1) if ln.startswith("Algol ") else ln for ln in lines]
    assert moved != lines
    return "".join(moved)


def _fabricate(folder, name):
    path = folder / name
    if name == "sedeltat.txt":
        path.write_text("".join(f"{year} 360.00\n" for year in range(1995, 2036)))
    elif name == "swe_deltat.txt":
        path.write_text("".join(f"{year} 720.00\n" for year in range(1995, 2036)))
    elif name == "sefstars.txt":
        path.write_text(_algol_an_hour_later(SHIPPED.read_text(encoding="latin-1")), encoding="latin-1")
    elif name == "fixstars.cat":
        path.write_text("Algol,bePer,ICRS,04,08,10.13245,+40,57,20.3280,0,0,0,0,2.12,\n")
    elif name in ("sepl_18.se1", "semo_18.se1"):
        path.write_bytes(b"not an ephemeris file\n" * 64)
    elif name == "seleapsec.txt":
        path.write_text("20191231\n")
    elif name == "seorbel.txt":
        path.write_text("J1900,J1900, 263.7409, 40.99837, 0.00460, 171.4333, 129.8325, 1.0833, Cupido # 1\n")
    elif name == "seasnam.txt":
        path.write_text("10001 Fabricated\n")
    elif name == "de431.eph":
        path.write_bytes(b"not a JPL ephemeris\n" * 64)
    elif name in ("eop_1962_today.txt", "eop_finals.txt"):
        path.write_text("not an Earth orientation record\n" * 8)
    elif name == "force.flg":
        path.write_text("2\n")
    else:
        raise KeyError(name)


def _tree_with_its_own_ephe(tmp_path_factory):
    """The app's own tree, but for its ephe/ folder: links to every other
    entry, and a real ephe/ holding a copy of the shipped catalogue."""
    root = tmp_path_factory.mktemp("tree")
    for entry in EXECUTABLE_DIR.iterdir():
        if entry.name != "ephe":
            (root / entry.name).symlink_to(entry)
    (root / "ephe").mkdir()
    shutil.copyfile(SHIPPED, root / "ephe" / "sefstars.txt")
    return root


def _env(tmp_path_factory, root):
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = str(root)
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    return env


def _probe(tmp_path_factory, mode, contents, bare=False):
    """The engine's values in a fresh process, with `contents` (file names)
    fabricated in the place `mode` names. Every place holds a copy of the
    shipped catalogue too (unless `bare`), as a reader's own folder might:
    before this lane $SE_EPHE_PATH outranked the folder the star reader set,
    so a place without one refused the stars whatever else it held. The
    older catalogue format is reached only where sefstars.txt is not, so it
    stands alone (but for ephe/, which keeps the shipped file it is read
    from)."""
    root = EXECUTABLE_DIR
    if mode == "ephe":
        root = _tree_with_its_own_ephe(tmp_path_factory)
        folder = root / "ephe"
    else:
        folder = tmp_path_factory.mktemp(f"place-{mode}")
        if not bare:
            shutil.copyfile(SHIPPED, folder / "sefstars.txt")
    for name in contents:
        if name == "fixstars.cat" and mode != "ephe":
            (folder / "sefstars.txt").unlink(missing_ok=True)
        _fabricate(folder, name)
    env = _env(tmp_path_factory, root)
    if mode in ("env", "env-thread"):
        env["SE_EPHE_PATH"] = str(folder)
    cwd = folder if mode == "cwd" else tmp_path_factory.mktemp("cwd")
    done = subprocess.run([sys.executable, "-c", _PROBE, mode, str(folder), repr(JD), repr(JD2000), repr(LAT), repr(LON)],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("PROBE ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    return json.loads(lines[-1][len("PROBE "):])


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    seen = {}

    def get(mode, *contents, bare=False):
        key = (mode, contents, bare)
        if key not in seen:
            seen[key] = _probe(tmp_path_factory, mode, contents, bare)
        return seen[key]
    return get


PLACES = ("cwd", "env", "env-thread", "path", "ephe")

# Each class with the files that stand for it.
CLASSES = {
    "sedeltat.txt": ("sedeltat.txt",),
    "swe_deltat.txt": ("swe_deltat.txt",),
    "sefstars.txt": ("sefstars.txt",),
    "fixstars.cat": ("fixstars.cat",),
    "se1": ("sepl_18.se1", "semo_18.se1"),
    "seleapsec.txt": ("seleapsec.txt",),
    "seorbel.txt": ("seorbel.txt",),
    "seasnam.txt": ("seasnam.txt",),
    # Read only by a build with tracing compiled in, and then from the working
    # directory by its literal name, outside any ephemeris path: these five
    # cells cannot fail on the pinned wheel whatever the engine does. What
    # pins force.flg is test_the_library_carries_no_force_flag_or_trace_file_name.
    "force.flg": ("force.flg",),
}

# Documented unreachable, not pinned: no cell built from them can fail under
# any change to the app, so none is run.
# - eop (de431.eph + eop_1962_today.txt + eop_finals.txt): the EOP files are
#   read only after a valid JPL file opens, no call here asks for a JPL value,
#   and a JPL file cannot be fabricated without downloading one (a text
#   de431.eph is skipped silently even where FLG_JPLEPH is asked).
# - fixstars.cat in ephe/: the shipped sefstars.txt stands beside it there,
#   and the library tries sefstars.txt over the whole path first.
DOCUMENTED_UNREACHABLE = {
    ("eop", place): ("de431.eph", "eop_1962_today.txt", "eop_finals.txt") for place in PLACES
} | {("fixstars.cat", "ephe"): ("fixstars.cat",)}

# A sefstars.txt in ephe/ is the shipped catalogue itself, altered: refused,
# not read (test_an_altered_shipped_catalogue_is_refused_not_read below).
MATRIX = [(cls, place) for cls in CLASSES for place in PLACES
          if (cls, place) != ("sefstars.txt", "ephe") and (cls, place) not in DOCUMENTED_UNREACHABLE]


def _clean(values):
    """The empty place: every engine value computed, the 28 stars read."""
    assert not values.get("timeout"), values
    for key in ("chart", "chart_2000", "sunrise_sunset", "sidereal_time", "stars"):
        assert not (isinstance(values[key], dict) and "error" in values[key]), (key, values[key])
    ready, stars, missing = values["stars"]
    assert ready is True and len(stars) == 28 and missing == [], values["stars"]
    return values


@pytest.mark.parametrize("cls, place", MATRIX)
def test_a_file_in_any_place_reaches_no_value(probe, cls, place):
    clean, polluted = _clean(probe(place)), probe(place, *CLASSES[cls])
    moved = sorted(k for k in set(clean) | set(polluted) if clean.get(k) != polluted.get(k))
    assert not moved, (cls, place, {k: (clean.get(k), polluted.get(k)) for k in moved})


@pytest.mark.parametrize("place", ["env", "env-thread"])
def test_a_se_ephe_path_holding_no_catalogue_refuses_no_star(probe, place):
    """$SE_EPHE_PATH naming an empty folder: before this lane it outranked the
    star reader's folder and the 28 stars were refused."""
    clean, bare = _clean(probe(place)), probe(place, bare=True)
    assert bare == clean, sorted(k for k in clean if clean[k] != bare.get(k))


def test_an_altered_shipped_catalogue_is_refused_not_read(probe):
    """ephe/sefstars.txt with Algol an hour later: it is not the catalogue
    whose hash the engine records, so no star is computed (the page says the
    fixed-star file could not be read), and nothing else moves."""
    clean, altered = _clean(probe("ephe")), probe("ephe", "sefstars.txt")
    assert altered["stars"] == [False, None, []], altered["stars"]
    moved = sorted(k for k in set(clean) | set(altered) if k != "stars" and clean.get(k) != altered.get(k)
                   and not k.endswith("star"))
    assert not moved, moved
    # The reader's own catalogue read returns the shipped star, never the altered one.
    assert altered["reader_star"] in (clean["reader_star"],) or "error" in altered["reader_star"], altered["reader_star"]


# ---------------------------------------------------------------------------
# The folder, the variable, the threads.

def test_the_folder_holds_only_the_verified_catalogue(engine):
    import ephemeris                                  # the folder's module: the engine holds no live copy of it
    folder = ephemeris._EPHEMERIS_FOLDER
    assert engine["fixed_star_longitudes"](JD2000), "no catalogue attached"
    assert sorted(os.listdir(folder)) == ["sefstars.txt"]
    copy = os.path.join(folder, "sefstars.txt")
    with open(copy, "rb") as fh:
        held = hashlib.sha256(fh.read()).hexdigest()
    assert held == hashlib.sha256(SHIPPED.read_bytes()).hexdigest() == engine["FIXED_STAR_CATALOGUE_SHA256"]
    assert os.path.isabs(folder) and engine["_ephemeris_folder_is_safe"](folder)
    real = os.path.realpath(folder)
    assert real != os.path.realpath(os.getcwd())
    for outside in (EXECUTABLE_DIR, os.environ.get("XDG_DATA_HOME") or EXECUTABLE_DIR):
        outside = os.path.realpath(outside)
        assert os.path.commonpath([real, outside]) != outside, outside
    # tempfile.mkdtemp's own folder: under the user's temporary folder, and
    # (where modes say so) readable and writable by this user alone.
    assert os.path.basename(folder).startswith("zij-ephemeris-")
    assert os.path.dirname(real) == os.path.realpath(tempfile.gettempdir())
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    else:
        assert os.access(folder, os.W_OK)
    assert os.environ.get("SE_EPHE_PATH") == folder


_WATCH = r"""
import importlib.util, os, sys, threading
seen, first = [], {}
WATCHED = ("set_ephe_path", "calc_ut", "calc", "houses", "rise_trans", "fixstar2_ut", "sidtime", "julday",
           "deltat_ex", "nod_aps_ut", "lun_eclipse_when", "revjul", "close")

def wrap(module):
    for name in WATCHED:
        real = getattr(module, name)
        def call(*a, _real=real, _name=name, **k):
            me = threading.current_thread()
            first.setdefault(me, (me.name, _name, a[0] if _name == "set_ephe_path" else None))
            return _real(*a, **k)
        setattr(module, name, call)

class Watch:
    # Records $SE_EPHE_PATH as swisseph is first imported, and each
    # thread's first call into it from then on, wherever the import happens.
    def find_spec(self, name, path=None, target=None):
        if name != "swisseph":
            return None
        seen.append(os.environ.get("SE_EPHE_PATH"))
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(name)
        run = spec.loader.exec_module
        def exec_module(module):
            run(module)
            wrap(module)
        spec.loader.exec_module = exec_module
        return spec
sys.meta_path.insert(0, Watch())
"""


def test_se_ephe_path_names_the_folder_before_swisseph_loads(tmp_path_factory):
    """$SE_EPHE_PATH, hostile at the start, already names the engine's
    folder when swisseph is first imported; the import's own path setter
    takes it from there."""
    hostile = tmp_path_factory.mktemp("hostile")
    _fabricate(hostile, "sedeltat.txt")
    code = _WATCH + ("import engine, ephemeris\nprint('WATCH ' + repr([seen, getattr(ephemeris, '_EPHEMERIS_FOLDER', None),"
                            " os.environ.get('SE_EPHE_PATH')]))\n")
    env = {**_env(tmp_path_factory, EXECUTABLE_DIR), "SE_EPHE_PATH": str(hostile)}
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path_factory.mktemp("cwd"), env=env,
                          capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("WATCH ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    seen, folder, now = ast.literal_eval(line[-1][len("WATCH "):])
    assert seen == [folder] and now == folder and folder != str(hostile), (seen, folder, now)


def test_the_app_loads_swisseph_only_through_the_engine():
    """app.py imports the engine before anything imports swisseph, and takes
    `swe` from it (the star import), never the library itself. Of the
    program's modules only ephemeris.py imports the library, once, at its top
    level, after it has set $SE_EPHE_PATH, and binds `swe`; engine.py's first
    statement after its docstring imports ephemeris.py."""
    from conftest import source_files

    def imports_swisseph(node):
        return ((isinstance(node, ast.Import) and any(a.name.split(".")[0] == "swisseph" for a in node.names))
                or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "swisseph"))

    trees = {path.name: ast.parse(path.read_text(encoding="utf-8")) for path in source_files()}
    raw = {name: [n.lineno for n in ast.walk(tree) if imports_swisseph(n)] for name, tree in trees.items()}
    assert {name: lines for name, lines in raw.items() if lines} == {"ephemeris.py": raw["ephemeris.py"]}, raw
    ephemeris_tree = trees["ephemeris.py"]
    imports = [n for n in ephemeris_tree.body if imports_swisseph(n)]
    assert [ast.unparse(n) for n in imports] == ["import swisseph as _swisseph"] and len(raw["ephemeris.py"]) == 1, raw
    first = ephemeris_tree.body.index(imports[0])
    pins = [n for n in ephemeris_tree.body[:first] if "SE_EPHE_PATH" in ast.unparse(n) and "environ" in ast.unparse(n)]
    assert pins, "nothing before the import sets $SE_EPHE_PATH"
    binds = [ast.unparse(n) for tree in trees.values() for n in tree.body
             if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["swe"]]
    assert binds == ["swe = _SwissEphemeris(_swisseph)"], binds
    engine_body = trees["engine.py"].body
    statements = engine_body[1:] if ast.get_docstring(trees["engine.py"]) else engine_body
    assert ast.unparse(statements[0]) == "from ephemeris import *", ast.unparse(statements[0])


_THREAD_LOG = _WATCH + r"""
import json, concurrent.futures
import engine, ephemeris
JD, LAT, LON = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
def work():
    engine.calculate_traditional_chart_jd(JD, LAT, LON)
    engine.fixed_star_longitudes(JD)
    engine.swe.sidtime(JD)
work()
t = threading.Thread(target=work, name="fresh")
t.start(); t.join(120)
with concurrent.futures.ThreadPoolExecutor(2, thread_name_prefix="pool") as pool:
    list(pool.map(lambda _: work(), range(4)))
print("LOG " + json.dumps([list(first.values()), getattr(ephemeris, "_EPHEMERIS_FOLDER", None), t.is_alive()]))
"""


def test_every_thread_points_at_the_folder_before_its_first_calculation(tmp_path_factory):
    """The importing thread, a fresh thread, the star reader and a pool's
    workers: in each, the first call into the library is set_ephe_path,
    to the engine's folder."""
    done = subprocess.run([sys.executable, "-c", _THREAD_LOG, repr(JD), repr(LAT), repr(LON)],
                          cwd=tmp_path_factory.mktemp("cwd"), env=_env(tmp_path_factory, EXECUTABLE_DIR),
                          capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("LOG ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    firsts, folder, stuck = json.loads(line[-1][len("LOG "):])
    assert not stuck
    names = sorted(n for n, _c, _a in firsts)
    assert {"MainThread", "fresh"} <= set(names) and any(n.startswith("pool") for n in names), names
    assert any(n.startswith("fixed-star-catalogue") for n in names), names
    wrong = [(n, c, a) for n, c, a in firsts if (c, a) != ("set_ephe_path", folder)]
    assert folder and not wrong, (folder, wrong)


def test_the_app_loads_swisseph_after_the_folder_and_its_threads_point_there_first(tmp_path_factory):
    """The page run as the harness runs it (make_app), in a thread of its own
    as Streamlit runs a session, in a fresh process where nothing has
    imported the engine or swisseph, with a Delta T file in the working
    directory: swisseph is loaded with $SE_EPHE_PATH already naming the
    engine's folder, every thread's first library call points it there, and
    a later thread (a session's next run) computes the chart with no file."""
    code = _WATCH + r"""
import json
sys.path.insert(0, sys.argv[1])
from conftest import make_app
box = {}
def page():
    at = make_app(date="2026-01-01").run(timeout=240)
    box["exceptions"] = [str(e.value)[:300] for e in at.exception]
t = threading.Thread(target=page, name="script")
t.start(); t.join(280)
import engine, ephemeris
def rerun():
    box["moon"] = engine.calculate_traditional_chart_jd(2461042.1650830186, 43.7696, 11.2558)["planetary_data"]["Moon"]["longitude"].hex()
t2 = threading.Thread(target=rerun, name="script-2")
t2.start(); t2.join(120)
print("APP " + json.dumps([seen, getattr(ephemeris, "_EPHEMERIS_FOLDER", None), box, [t.is_alive(), t2.is_alive()],
                          sorted({v[1:] for v in first.values()})]))
"""
    place = tmp_path_factory.mktemp("cwd")
    _fabricate(place, "sedeltat.txt")
    env = _env(tmp_path_factory, EXECUTABLE_DIR)
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR / "tests"), str(EXECUTABLE_DIR)])
    done = subprocess.run([sys.executable, "-c", code, str(EXECUTABLE_DIR / "tests")], cwd=place,
                          env=env, capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("APP ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    seen, folder, box, stuck, firsts = json.loads(line[-1][len("APP "):])
    assert stuck == [False, False] and box.get("exceptions") == [], box
    assert folder and seen == [folder], (seen, folder)
    assert firsts == [["set_ephe_path", folder]], firsts
    clean = subprocess.run([sys.executable, "-c", "import engine; print('MOON ' + engine.calculate_traditional_chart_jd("
                            "2461042.1650830186, 43.7696, 11.2558)['planetary_data']['Moon']['longitude'].hex())"],
                           cwd=tmp_path_factory.mktemp("cwd"), env=_env(tmp_path_factory, EXECUTABLE_DIR),
                           capture_output=True, text=True, timeout=TIMEOUT)
    assert f"MOON {box['moon']}" in clean.stdout.splitlines(), (box, clean.stderr[-2000:])


# ---------------------------------------------------------------------------
# No other catalogue is looked for.

def test_no_catalogue_other_than_the_shipped_one_is_read(engine, monkeypatch, tmp_path):
    """The shipped catalogue hidden, a good copy offered through
    $SE_EPHE_PATH and the user data directory: nothing is attached, and the
    page's sentence is the one refusal."""
    import engine as engine_module
    shipped = str(SHIPPED)
    real_isfile = os.path.isfile
    (tmp_path / "sefstars.txt").write_bytes(SHIPPED.read_bytes())
    data = tmp_path / "data"
    (data / "ephe").mkdir(parents=True)
    (data / "ephe" / "sefstars.txt").write_bytes(SHIPPED.read_bytes())
    state = engine["_FIXED_STAR_STATE"]
    try:
        monkeypatch.setattr(os.path, "isfile", lambda p: False if str(p) == shipped else real_isfile(p))
        monkeypatch.setenv("SE_EPHE_PATH", str(tmp_path))
        monkeypatch.setattr(engine_module, "_user_data_dir", lambda: data)
        state.update(checked=False, ready=False, where=None, why=None)
        assert engine["_fixed_star_catalogue_ready"]() is False
        assert engine["fixed_star_longitudes"](JD2000) is None
        assert engine["fixed_star_refusal"]() == ("no Swiss Ephemeris star catalogue is attached; nothing is computed"
                                                  " -- the fixed-star file could not be read")
    finally:
        monkeypatch.undo()
        state.update(checked=False, ready=False, where=None, why=None)
    assert engine["_fixed_star_catalogue_ready"]() is True


def test_the_catalogue_search_and_its_wording_are_gone():
    from conftest import engine_source
    source = engine_source()                          # every engine module
    for retired in ("site-packages", "ephe_stars", "glob.glob", "no other copy of the fixed-star file",
                    "in $SE_EPHE_PATH, in the user data directory", "could not link it into",
                    "_user_data_dir() / 'ephe'"):
        assert retired not in source, retired


# ---------------------------------------------------------------------------
# Streamlit's caches and reloads.

def test_swisseph_loaded_before_the_engine_empties_streamlit_s_caches(tmp_path_factory):
    """Whatever ran before the engine's folder existed may have read a file;
    no cached result from then is handed out after."""
    code = r"""
import warnings; warnings.simplefilter("ignore")
import swisseph, streamlit as st
calls = []
@st.cache_data
def cached(x):
    calls.append(x)
    return swisseph.deltat_ex(x, -1)
cached(2451545.0)
cached(2451545.0)
import engine
cached(2451545.0)
print("CALLS " + str(len(calls)))
"""
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    assert "CALLS 2" in done.stdout.splitlines(), (done.stdout[-500:], done.stderr[-2000:])


def test_a_thread_whose_delta_t_a_file_reached_first_is_refused(tmp_path_factory):
    """A thread that read a Delta T file before the engine pointed it at its
    folder keeps that table for its life (neither the path setter nor
    swe.close restores it): the engine refuses to compute in it, and a fresh
    thread computes the values with no file."""
    code = r"""
import json, sys, threading
import engine
import swisseph as raw
JD, LAT, LON = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
out = {}
def reached_first():
    raw.deltat_ex(JD, -1)                       # the library's own default path: the working directory first
    try:
        out["reached"] = engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"].hex()
    except RuntimeError as exc:
        out["reached"] = "refused: " + str(exc)
def fresh():
    out["fresh"] = engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"].hex()
for fn in (reached_first, fresh):
    t = threading.Thread(target=fn)
    t.start(); t.join(120)
    out.setdefault("stuck", []).append(t.is_alive())
print("OUT " + json.dumps(out))
"""
    place = tmp_path_factory.mktemp("cwd")
    _fabricate(place, "sedeltat.txt")
    done = subprocess.run([sys.executable, "-c", code, repr(JD), repr(LAT), repr(LON)], cwd=place,
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("OUT ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    out = json.loads(line[-1][len("OUT "):])
    assert out["stuck"] == [False, False], out
    assert out["reached"].startswith("refused: "), out
    clean = subprocess.run([sys.executable, "-c", "import engine; print('MOON ' + engine.calculate_traditional_chart_jd("
                            f"{JD!r}, {LAT!r}, {LON!r})['planetary_data']['Moon']['longitude'].hex())"],
                           cwd=tmp_path_factory.mktemp("cwd"), env=_env(tmp_path_factory, EXECUTABLE_DIR),
                           capture_output=True, text=True, timeout=TIMEOUT)
    assert f"MOON {out['fresh']}" in clean.stdout.splitlines(), (out, clean.stderr[-2000:])


def test_a_reload_and_a_fresh_import_keep_the_folder_and_the_values(tmp_path_factory):
    """importlib.reload (the test harness) and a fresh import after the
    modules are dropped from sys.modules (Streamlit's watcher) of the folder's
    module, the engine after it, keep one folder for the process, keep
    $SE_EPHE_PATH on it, and move no value. The positive control: each route's
    `ephemeris` step, counted alone before the engine's (whose import-time
    library call reaches the handle's guard, which does the same work), is
    seen to run ephemeris.py's module code again (its code object's "exec"
    audit event), to run its check of the folder (the check's own calls,
    tests/ephemeris_check_count.py) and to set $SE_EPHE_PATH (the os.putenv
    audit event), so the test fails where a route does not reach them."""
    code = r"""
import importlib, json, os, sys, threading
runs = {"module": 0, "set": 0}
def _audit(event, args):
    if event == "exec" and getattr(args[0], "co_filename", "").endswith("ephemeris.py"):
        runs["module"] += 1
    elif event == "os.putenv" and os.fsdecode(args[0]) == "SE_EPHE_PATH":
        runs["set"] += 1
sys.addaudithook(_audit)
""" + CHECK_COUNT + r"""
steps = []
def ephemeris_step(step):
    before = {**runs, **counted()}
    module = step()
    steps.append({k: v - before[k] for k, v in {**runs, **counted()}.items()})
    return module
ephemeris = ephemeris_step(lambda: importlib.import_module("ephemeris"))
import engine
JD, LAT, LON = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
def moon():
    box = []
    t = threading.Thread(target=lambda: box.append(engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"].hex()))
    t.start(); t.join(120)
    return box[0] if box else None
def row():
    folder = getattr(ephemeris, "_EPHEMERIS_FOLDER", None)
    return (folder, os.environ.get("SE_EPHE_PATH"), moon(), sorted(os.listdir(folder)) if folder else None)
rows = [row()]
ephemeris = ephemeris_step(lambda: importlib.reload(ephemeris))
engine = importlib.reload(engine)
rows.append(row())
del sys.modules["engine"], sys.modules["ephemeris"]
ephemeris = ephemeris_step(lambda: importlib.import_module("ephemeris"))
import engine
rows.append(row())
print("ROWS " + json.dumps([rows, steps]))
"""
    done = subprocess.run([sys.executable, "-c", code, repr(JD), repr(LAT), repr(LON)], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("ROWS ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    rows, steps = json.loads(line[-1][len("ROWS "):])
    assert len(rows) == 3, rows
    folder, variable, moon, listing = rows[0]
    assert folder and folder == variable and moon and listing in ([], ["sefstars.txt"]), rows[0]
    assert all(r[:3] == [folder, variable, moon] for r in rows), rows
    # The import ran the module and its check, which found no folder and made
    # one (whose name the making checks too); each route's `ephemeris` step ran
    # the module once more, checked the folder it found (its name, then its
    # identity) and set the variable once.
    assert steps == [{"module": 1, "set": 1, "safe": 2, "held": 0},
                     {"module": 1, "set": 1, "safe": 1, "held": 1},
                     {"module": 1, "set": 1, "safe": 1, "held": 1}], steps


def test_the_folder_goes_with_the_process(tmp_path_factory):
    code = ("import json, os, engine, ephemeris; engine.fixed_star_longitudes(2451545.0)\n"
            "folder = getattr(ephemeris, '_EPHEMERIS_FOLDER', None)\n"
            "print('FOLDER ' + json.dumps([folder, bool(folder) and os.path.isdir(folder)]))\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("FOLDER ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    folder, existed = json.loads(line[-1][len("FOLDER "):])
    assert existed and not os.path.exists(folder), (folder, existed)


def test_a_folder_a_cleaner_removed_is_made_again(tmp_path_factory):
    """A temporary-files cleaner can remove the folder under an app left
    running: the next thread makes a new one, the star reader copies the
    catalogue into it, and no value moves."""
    code = r"""
import json, os, shutil, sys, threading
import engine, ephemeris
JD, LAT, LON = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
def values():
    box = []
    def run():
        c = engine.calculate_traditional_chart_jd(JD, LAT, LON)
        box.append([c["planetary_data"]["Moon"]["longitude"].hex(), c["ascendant"].hex(),
                    {k: v.hex() for k, v in engine.fixed_star_longitudes(JD).items()}])
    t = threading.Thread(target=run); t.start(); t.join(120)
    return box[0] if box else None
before = values()
first = getattr(ephemeris, "_EPHEMERIS_FOLDER", None)
shutil.rmtree(first)
after = values()
second = getattr(ephemeris, "_EPHEMERIS_FOLDER", None)
print("AGAIN " + json.dumps([before, after, first, second, sorted(os.listdir(second)) if second and os.path.isdir(second) else None,
                             os.environ.get("SE_EPHE_PATH")]))
"""
    done = subprocess.run([sys.executable, "-c", code, repr(JD), repr(LAT), repr(LON)], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("AGAIN ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    before, after, first, second, listing, variable = json.loads(line[-1][len("AGAIN "):])
    assert before and len(before[2]) == 28 and after == before, (before, after)
    assert second and second != first and listing == ["sefstars.txt"] and variable == second, (first, second, listing, variable)


_ADOPT = r"""
import hashlib, json, os, shutil, stat, sys, threading
import engine, ephemeris
mode, elsewhere = sys.argv[1], sys.argv[2]
JD, LAT, LON = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
def in_a_thread(fn):
    box = []
    t = threading.Thread(target=lambda: box.append(fn()))
    t.start(); t.join(120)
    return box[0] if box else None
chart = lambda: engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"].hex()
before = in_a_thread(chart)                       # no star read yet: the reader has not attached
first = ephemeris._EPHEMERIS_FOLDER
shutil.rmtree(first)                              # a temporary-files cleaner
real_lstat, me = os.lstat, os.getuid()
if mode == "symlink":                             # a link to a folder holding an altered catalogue
    os.symlink(elsewhere, first)
elif mode == "open-mode":                         # a directory anyone may write into
    os.mkdir(first)
    os.chmod(first, 0o777)
else:                                             # "other-owner": 0700, but another user's
    os.mkdir(first, 0o700)
    def lstat(path, *a, **k):
        st = real_lstat(path, *a, **k)
        if os.path.abspath(os.fspath(path)) == first:
            fields = list(st)
            fields[4] = me + 1
            return os.stat_result(fields)
        return st
    os.lstat = lstat
try:
    after = in_a_thread(lambda: [chart(), {k: v.hex() for k, v in (engine.fixed_star_longitudes(JD) or {}).items()}])
    second = ephemeris._EPHEMERIS_FOLDER
    st = real_lstat(second)
    with open(os.path.join(elsewhere, "sefstars.txt"), "rb") as fh:
        planted = hashlib.sha256(fh.read()).hexdigest()
finally:                                          # what this probe planted goes with it
    os.lstat = real_lstat
    if os.path.islink(first):
        os.unlink(first)
    elif os.path.isdir(first) and first != ephemeris._EPHEMERIS_FOLDER:
        shutil.rmtree(first)
print("ADOPT " + json.dumps([before, after, first, second, stat.S_ISDIR(st.st_mode), stat.S_IMODE(st.st_mode),
                             st.st_uid == me, os.environ.get("SE_EPHE_PATH"),
                             sorted(os.listdir(second)) if stat.S_ISDIR(st.st_mode) else None, planted]))
"""


@pytest.mark.parametrize("mode", ["symlink", "open-mode", "other-owner"])
def test_what_stands_at_a_removed_folder_s_path_is_not_adopted(probe, tmp_path_factory, mode):
    """After a cleaner removes the folder, its name, visible in the temporary
    folder, can be taken by anyone: a link elsewhere, a directory others may
    write into, another user's directory. None is used, and nothing is written
    into it: the engine makes a new folder of its own."""
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    _fabricate(elsewhere, "sefstars.txt")             # Algol an hour later
    altered = hashlib.sha256((elsewhere / "sefstars.txt").read_bytes()).hexdigest()
    done = subprocess.run([sys.executable, "-c", _ADOPT, mode, str(elsewhere), repr(JD), repr(LAT), repr(LON)],
                          cwd=tmp_path_factory.mktemp("cwd"), env=_env(tmp_path_factory, EXECUTABLE_DIR),
                          capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("ADOPT ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    before, after, first, second, is_dir, mode_bits, mine, variable, listing, planted = json.loads(line[-1][len("ADOPT "):])
    assert planted == altered, "the engine wrote into a folder it does not own"
    assert second != first and is_dir and mode_bits == 0o700 and mine, (first, second, is_dir, oct(mode_bits), mine)
    assert variable == second and listing == ["sefstars.txt"], (variable, listing)
    clean_stars = _clean(probe("cwd"))["stars"][1]
    assert after is not None and after[0] == before and len(after[1]) == 28, after
    assert after[1] == _float_hex(clean_stars), after[1]


def _float_hex(packed):
    """The probe's packed bits as float.hex(), the form the subprocess prints."""
    return {k: struct.unpack("!d", bytes.fromhex(v))[0].hex() for k, v in packed.items()}


# The page's one sentence where the engine refuses a thread (ruling 58 (c)'s
# way: the detail stays off the page).
EPHEMERIS_REFUSAL = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                     "Close the app and open it again.")

_PAGE = r"""
import json, os, sys, threading
sys.path.insert(0, sys.argv[1])
case, app, wrapper_dir = sys.argv[2], sys.argv[3], sys.argv[4]
import engine, ephemeris
from streamlit.testing.v1 import AppTest
JD, LAT, LON = 2461042.1650830186, 43.7696, 11.2558
out = {}
def page(script):
    at = AppTest.from_file(script, default_timeout=240).run(timeout=240)
    return {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error],
            "markdown": len(at.main.markdown)}
def in_a_thread(fn):
    box = []
    def run():
        try:
            box.append(fn())
        except RuntimeError as exc:
            box.append("refused: " + str(exc))
    t = threading.Thread(target=run); t.start(); t.join(120)
    return box[0] if box else None
moon = lambda: engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"]["Moon"]["longitude"].hex()
if case == "delta-t":
    # This run's own script thread reads a Delta T file (the working directory's,
    # the library's default path) before the app's first call points it anywhere.
    wrapper = os.path.join(wrapper_dir, "reached_first.py")
    with open(wrapper, "w") as fh:
        fh.write("import runpy, swisseph\nswisseph.deltat_ex(2451545.0, -1)\n"
                 f"runpy.run_path({app!r}, run_name='__main__')\n")
    out["page"] = page(wrapper)
else:
    out["clean"] = moon()                         # the importing thread, pointed at the folder
    stray = os.path.join(ephemeris._EPHEMERIS_FOLDER, "sedeltat.txt")
    with open(stray, "w") as fh:
        fh.write("".join(f"{y} 360.00\n" for y in range(1995, 2036)))
    out["page"] = page(app)                       # a new run, a new thread
    out["new_thread"] = in_a_thread(moon)
    out["pointed_thread"] = moon()                # already pointed: goes on, with its own table
    os.remove(stray)
    out["page_after"] = page(app)                 # no restart
    out["new_thread_after"] = in_a_thread(moon)
print("PAGE " + json.dumps(out))
"""


def _page(tmp_path_factory, case, cwd):
    env = _env(tmp_path_factory, EXECUTABLE_DIR)
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    done = subprocess.run([sys.executable, "-c", _PAGE, str(EXECUTABLE_DIR), case, str(APP_PATH),
                           str(tmp_path_factory.mktemp("wrapper"))],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("PAGE ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    return json.loads(line[-1][len("PAGE "):])


def _says_only_the_sentence(page):
    assert page["exceptions"] == [], page["exceptions"]
    assert page["errors"] == [EPHEMERIS_REFUSAL], page["errors"]
    assert "/" not in EPHEMERIS_REFUSAL and "\\" not in EPHEMERIS_REFUSAL and ".txt" not in EPHEMERIS_REFUSAL


def test_a_refused_script_thread_shows_one_plain_sentence(tmp_path_factory):
    """A session run whose own thread read a Delta T file before the app's
    first call: the page says one plain sentence and stops; no exception box,
    no path, no file name."""
    place = tmp_path_factory.mktemp("cwd")
    _fabricate(place, "sedeltat.txt")
    out = _page(tmp_path_factory, "delta-t", place)
    _says_only_the_sentence(out["page"])


def test_a_stray_file_in_the_folder_refuses_new_threads_while_it_is_there(tmp_path_factory):
    """A file planted in the engine's folder: a new run's page says the one
    sentence; a new thread is refused with words that are true (in that
    thread, while the file is there); a thread already pointed at the folder
    goes on; once the file is gone the next run computes, with no restart."""
    out = _page(tmp_path_factory, "stray", tmp_path_factory.mktemp("cwd"))
    _says_only_the_sentence(out["page"])
    refused = out["new_thread"]
    assert refused.startswith("refused: ") and "while" in refused and "restart" not in refused, refused
    assert out["pointed_thread"] == out["clean"], out
    assert out["page_after"]["exceptions"] == [] and EPHEMERIS_REFUSAL not in out["page_after"]["errors"], out["page_after"]
    assert out["page_after"]["markdown"] > 0 and out["new_thread_after"] == out["clean"], out


_COPY_LINK = r"""
import hashlib, json, os, sys, threading
import engine, ephemeris
outside = sys.argv[1]
copy = os.path.join(ephemeris._EPHEMERIS_FOLDER, "sefstars.txt")
os.symlink(outside, copy)                         # a link where the copy goes, before the first star read
box = []
def stars():
    box.append([engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(2451545.0)])
t = threading.Thread(target=stars); t.start(); t.join(120)
with open(outside, "rb") as fh:
    after = hashlib.sha256(fh.read()).hexdigest()
print("LINK " + json.dumps([box[0] if box else None, after, os.path.islink(copy)]))
"""


def test_a_link_in_place_of_the_catalogue_s_copy_is_not_followed(tmp_path_factory):
    """A link standing where the copy is written (planted by something running
    as this user): it is not written through, the file it points at is left as
    it was, and no star is computed from it."""
    outside = tmp_path_factory.mktemp("outside")
    _fabricate(outside, "sefstars.txt")               # Algol an hour later
    before = hashlib.sha256((outside / "sefstars.txt").read_bytes()).hexdigest()
    done = subprocess.run([sys.executable, "-c", _COPY_LINK, str(outside / "sefstars.txt")],
                          cwd=tmp_path_factory.mktemp("cwd"), env=_env(tmp_path_factory, EXECUTABLE_DIR),
                          capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("LINK ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    stars, after, still_a_link = json.loads(line[-1][len("LINK "):])
    assert after == before, "the copy was written through the link"
    assert stars == [False, None] and still_a_link, (stars, still_a_link)


_LEFT_AT_THE_PATH = r"""
import json, os, shutil, sys, threading
import engine, ephemeris
first = ephemeris._EPHEMERIS_FOLDER
shutil.rmtree(first)                              # a cleaner
os.mkdir(first)                                   # and a directory the engine did not make, with a file in it
os.chmod(first, 0o777)
with open(os.path.join(first, "theirs.txt"), "w") as fh:
    fh.write("not the engine's\n")
box = []
t = threading.Thread(target=lambda: box.append(engine.calculate_traditional_chart_jd(2451545.0, 43.77, 11.25)["sect"]))
t.start(); t.join(120)
print("LEFT " + json.dumps([first, ephemeris._EPHEMERIS_FOLDER, box]))
"""


def test_at_exit_a_directory_the_engine_did_not_make_is_left_where_it_stands(tmp_path_factory):
    """After a cleaner, a directory put at the folder's old path is not the
    engine's: a normal exit removes the folder the engine made instead, and
    leaves that directory and what is in it."""
    done = subprocess.run([sys.executable, "-c", _LEFT_AT_THE_PATH], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, EXECUTABLE_DIR), capture_output=True, text=True, timeout=TIMEOUT)
    line = [ln for ln in done.stdout.splitlines() if ln.startswith("LEFT ")]
    assert done.returncode == 0 and line, done.stderr[-3000:]
    first, second, sect = json.loads(line[-1][len("LEFT "):])
    try:
        assert sect and second != first, (first, second, sect)
        assert not os.path.exists(second), "the folder the engine made was not removed at exit"
        assert os.path.isfile(os.path.join(first, "theirs.txt")), "the directory the engine did not make was removed"
    finally:
        shutil.rmtree(first, ignore_errors=True)


# ---------------------------------------------------------------------------
# What the library takes whole, and what it cannot open at all.

def test_a_folder_name_swiss_ephemeris_would_not_take_whole_is_refused(engine):
    """The library splits its path at ';' (and ':' outside Windows) and
    falls back to its compiled default -- the working directory first -- for
    a path too long to hold with a file's name. Such a folder is never
    used."""
    import ephemeris
    safe = engine["_ephemeris_folder_is_safe"]
    assert safe(ephemeris._EPHEMERIS_FOLDER)
    root = os.path.abspath(os.sep)
    for bad in ("relative/folder", os.path.join(root, "a;b"), os.path.join(root, "x" * 230), "", None):
        assert not safe(bad), bad
    assert not safe(os.path.join(root, "a:b"))          # past a Windows drive's colon, ':' anywhere


def test_the_library_carries_no_force_flag_or_trace_file_name():
    """force.flg is read, and swetrace.* written, only by a build with
    tracing compiled in; the pinned wheel names neither."""
    import swisseph
    binary = open(swisseph.__file__, "rb").read()
    assert b"sedeltat.txt" in binary                              # the scan reads the names the library opens
    assert b"force.flg" not in binary and b"swetrace" not in binary


def test_the_engine_calls_the_library_itself_only_to_point_a_thread_at_its_folder():
    """Every engine computation goes through `swe`, the guarded handle; the
    library module itself is reached only by the guard, and by the star
    reader to close its catalogue."""
    from conftest import engine_files
    direct = {}
    for top in [top for path in engine_files() for top in ast.parse(path.read_text(encoding="utf-8")).body]:
        name = getattr(top, "name", "<module>")
        for node in ast.walk(top):
            if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Name) and node.value.id == "_swisseph"):
                direct.setdefault(name, set()).add(node.attr)
    assert direct == {"_ephemeris_thread_ready": {"set_ephe_path"},
                      "_delta_t_table": {"deltat_ex", "julday"},
                      "_delta_t_reference": {"set_ephe_path"},
                      "_fixed_star_catalogue_install": {"close"},
                      "_fixed_star_reader_close": {"close"}}, direct


def test_only_the_guard_reads_se_ephe_path():
    """No catalogue is looked for in $SE_EPHE_PATH: the variable is read
    only where a thread is pointed at the folder, to set it back if it was
    changed."""
    from conftest import engine_files
    reads = {}
    for top in [top for path in engine_files() for top in ast.parse(path.read_text(encoding="utf-8")).body]:
        for node in ast.walk(top):
            text = ast.unparse(node)
            subscript = (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
                         and ast.unparse(node.value) == "os.environ")
            getter = (isinstance(node, ast.Call) and ast.unparse(node.func) in ("os.environ.get", "os.getenv"))
            if (subscript or getter) and "SE_EPHE_PATH" in text:
                reads.setdefault(getattr(top, "name", "<module>"), []).append(text)
    assert set(reads) == {"_ephemeris_thread_ready"}, reads
