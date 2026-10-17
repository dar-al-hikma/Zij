"""The planets' ephemeris flag: Moshier, whatever a directory holds.

The exports say "Ephemeris: Moshier (built in)" (ruling 58 (a)). Swiss
Ephemeris computes with Moshier when it is asked to (``FLG_MOSEPH``) or when
it is asked for its own files (``FLG_SWIEPH``, the default of every
pyswisseph call) and finds none. Where it looks:

* the folder given to ``swe.set_ephe_path`` in the asking thread;
* ``$SE_EPHE_PATH``, which a path setter takes over the folder its caller
  names (since ruling 103 the engine sets it to a folder of its own before
  ``swisseph`` loads, and points every thread there before its first
  calculation: ``tests/test_fm2_swiss_files_2026_10_07.py``);
* the working directory, in any thread but the one that imported
  ``swisseph`` (the library's state is per thread; the import sets its own
  thread's path to the system folders, every other thread starts at the
  library default ``.:/users/ephe2/:/users/ephe/``). Streamlit runs the
  script in a thread of its own.

Each behavioural pin runs the engine in a fresh process, once with an empty
folder and once with a fabricated ``.se1`` (a few lines of text under the name
Swiss Ephemeris opens for 1800-2400: ``sepl_18.se1`` for the planets,
``semo_18.se1`` for the Moon, which is opened only after the planet file)
placed where it looks, and asks for equal values. At the default flags the
file is opened, found damaged, and the call raises. With ``FLG_MOSEPH``
nothing read from such a file reaches a value (the library may still open
the pair once per thread, for the Moon file's DE number). Nothing is
downloaded. The fixed stars are read in a thread of their own, from the
copy of the shipped catalogue in the engine's folder (ruling 103).

The static pins hold every call site in engine.py and app.py to the flag:
``swe.calc_ut`` of a body and ``swe.nod_aps_ut`` with ``MOSHIER_FLAGS``;
``swe.rise_trans``, ``swe.lun_eclipse_when`` and ``swe.fixstar2_ut`` with
``FLG_MOSEPH``. Where no file exists this moves some values (ruling 90,
amending 84, accepts the moves by their cause: delta T then takes the tidal
term matched to the Moshier ephemeris, as the bodies' already did).
``swe.houses`` and ``swe.sidtime`` take no flag; their delta T is the
library's fixed default whatever ephemeris file is on disk. The obliquity
reads (``ECL_NUT``) keep that default too, asked so that no ephemeris file can
reach them: ``swe.calc(jd + swe.deltat_ex(jd, -1), swe.ECL_NUT,
swe.FLG_MOSEPH)``. (As ``swe.calc_ut(jd, swe.ECL_NUT)`` their delta T took the
tidal term of a Moon file the thread could read, unless a Moshier body read
came first in it.) A delta T file (``sedeltat.txt``) where Swiss Ephemeris
looks still reaches ``houses``, ``sidtime`` and the obliquity, and every
other value with them: not an ephemeris file, and not pinned here. Ruling
103's folder keeps it out, and a thread that read one first is refused
(``tests/test_fm2_swiss_files_2026_10_07.py``).
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import APP_PATH, ENGINE_PATH, EXECUTABLE_DIR

# The sunset chart's moment (2026), Florence: inside sepl_18/semo_18's range.
# Mercury stands 4.4 degrees from his own mean node then (Abu Ma'shar's 52).
JD = 2461042.1650830186
# The total lunar eclipse of 2000 January 21 (Abu Ma'shar's 64).
JD_ECLIPSE = 2451564.697
LAT, LON = 43.7696, 11.2558

PLANET_FILE = "sepl_18.se1"
MOON_FILE = "semo_18.se1"

_PROBE = r"""
import json, sys, threading
import swisseph as swe
import engine

mode, ephe_dir = sys.argv[1], sys.argv[2]
JD, LAT, LON = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
JD_ECLIPSE = float(sys.argv[6])
OBLIQUITY_READS = json.loads(sys.argv[7])
out = {}

def plain(x):
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, (int, float, str, bool)) or x is None:
        return x
    return repr(x)

def condition(jd):
    chart = engine.calculate_traditional_chart_jd(jd, LAT, LON)
    pd_, houses, sect = chart["planetary_data"], chart["houses"], chart["sect"]
    essential = engine.evaluate_essential_dignities(pd_, sect)
    accidental = engine.evaluate_accidental_dignities(pd_, houses, sect, jd, armc=chart["armc"],
                                                      obliquity=chart["obliquity"], geo_lat=LAT)
    return plain(engine.evaluate_abu_mashar_condition(pd_, houses, sect, essential, accidental, jd,
                                                      chart["ascendant"]))

def grab(key, fn):
    try:
        out[key] = fn()
    except Exception as exc:
        out[key] = {"error": f"{type(exc).__name__}: {exc}"}

def run():
    if mode == "path":
        swe.set_ephe_path(ephe_dir)
    # The engine's own obliquity reads, as written, first in this thread.
    grab("obliquity", lambda: [[eval(src, {"swe": swe, **{n: jd for n in names}}) for src, names in OBLIQUITY_READS]
                               for jd in (JD, 1721426.0, 2176000.0, 2451545.0)])
    grab("planets", lambda: {name: [row["longitude"], row["speed_in_lon"]]
                             for name, row in engine.third_day_positions(JD)["planetary_data"].items()
                             if name != "Moon"})
    grab("phase", lambda: list(engine._sahl_phase_at("Mars", JD)))
    grab("moon", lambda: [{key: repr(row["longitude"]) for key, row in engine.gestation_moons(JD).items()},
                          engine.third_day_positions(JD)["planetary_data"]["Moon"]["longitude"],
                          list(engine._sun_moon_signed_offset(JD, 0.0))])
    grab("sunrise", lambda: [engine._rise_trans_sun(JD, LAT, LON, True),
                             engine._rise_trans_sun(JD, LAT, LON, False)])
    grab("chart", lambda: {name: row["longitude"] for name, row in
                           engine.calculate_traditional_chart_jd(JD, LAT, LON)["planetary_data"].items()})
    grab("own_node", lambda: condition(JD))
    grab("eclipse", lambda: condition(JD_ECLIPSE))
    grab("stars", lambda: [engine._fixed_star_catalogue_ready(), engine.fixed_star_longitudes(JD)])

if mode == "env":
    run()
else:
    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
print("PROBE " + json.dumps(out))
"""


def _is_obliquity_read(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "swe"
            and node.func.attr in ("calc_ut", "calc") and len(node.args) > 1
            and ast.unparse(node.args[1]) == "swe.ECL_NUT")


def _obliquity_reads():
    """Each obliquity read in the engine's modules as written, with the names
    its time is built from (bound to the probe's Julian Day)."""
    from conftest import engine_files
    return [(ast.unparse(node), sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} - {"swe"}))
            for path in engine_files() for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if _is_obliquity_read(node)]


def _fabricate(folder, name):
    """A file Swiss Ephemeris opens by name and finds damaged: no header."""
    (folder / name).write_bytes(b"not an ephemeris file\n" * 64)


def _probe(tmp_path_factory, mode, contents):
    """The engine's values in a fresh process, with a folder holding
    `contents` (file names) where Swiss Ephemeris looks under `mode`."""
    root = EXECUTABLE_DIR
    if mode == "ephe":
        # The app's own tree, but for its ephe/ folder: the star reader's
        # folder before ruling 103 (now the source its catalogue is copied
        # from), and the file goes there.
        root = tmp_path_factory.mktemp("tree")
        for entry in EXECUTABLE_DIR.iterdir():
            if entry.name != "ephe":
                (root / entry.name).symlink_to(entry)
        folder = root / "ephe"
        folder.mkdir()
    else:
        folder = tmp_path_factory.mktemp(f"ephe-{mode}-{'-'.join(contents) or 'empty'}")
    for name in contents:
        _fabricate(folder, name)
    # The catalogue the app ships goes beside the file, in every mode alike
    # (placed when $SE_EPHE_PATH outranked the star reader's folder; in the
    # ``ephe`` mode it is the source the engine copies from).
    shutil.copyfile(EXECUTABLE_DIR / "ephe" / "sefstars.txt", folder / "sefstars.txt")
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(root), env.get("PYTHONPATH", "")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    if mode == "env":
        env["SE_EPHE_PATH"] = str(folder)
    cwd = folder if mode == "cwd" else tmp_path_factory.mktemp("cwd")
    done = subprocess.run([sys.executable, "-c", _PROBE, mode, str(folder), repr(JD), repr(LAT), repr(LON),
                           repr(JD_ECLIPSE), json.dumps(_obliquity_reads())],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("PROBE ")]
    assert done.returncode == 0 and lines, done.stderr[-2000:]
    return json.loads(lines[-1][len("PROBE "):])


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    seen = {}

    def get(mode, *contents):
        key = (mode, contents)
        if key not in seen:
            seen[key] = _probe(tmp_path_factory, mode, contents)
        return seen[key]
    return get


MODES = ("path", "env", "cwd")


def _clean(values, key):
    """The no-file value: computed, not an error."""
    value = values[key]
    assert not (isinstance(value, dict) and "error" in value), value
    return value


@pytest.mark.parametrize("mode", MODES)
def test_a_planet_file_does_not_move_the_planets(probe, mode):
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    for key in ("planets", "phase"):
        assert doctored[key] == _clean(clean, key), (mode, key)


@pytest.mark.parametrize("mode", MODES)
def test_a_moon_file_does_not_move_the_moon(probe, mode):
    """Both files: Swiss Ephemeris reads the planet file (the Earth) before it
    opens the Moon's, so a Moon file alone is never reached."""
    clean, doctored = probe(mode), probe(mode, PLANET_FILE, MOON_FILE)
    assert doctored["moon"] == _clean(clean, "moon"), mode


@pytest.mark.parametrize("mode", MODES)
def test_a_planet_file_does_not_move_the_sunrise(probe, mode):
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    assert doctored["sunrise"] == _clean(clean, "sunrise"), mode


@pytest.mark.parametrize("mode", MODES)
def test_a_planet_file_does_not_move_the_chart(probe, mode):
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    assert doctored["chart"] == _clean(clean, "chart"), mode


@pytest.mark.parametrize("mode", MODES)
def test_a_planet_file_does_not_drop_the_own_node_condition(probe, mode):
    """52's own nodes: the read sat in a try that dropped the condition."""
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    assert "With its own" in json.dumps(_clean(clean, "own_node"))
    assert doctored["own_node"] == clean["own_node"], mode


@pytest.mark.parametrize("mode", MODES)
def test_a_planet_file_does_not_drop_the_eclipse(probe, mode):
    """64's eclipse: the search sat in a try that dropped the label."""
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    assert "Eclipsed (64)" in json.dumps(_clean(clean, "eclipse"))
    assert doctored["eclipse"] == clean["eclipse"], mode


@pytest.mark.parametrize("mode", ["env", "ephe"])
def test_a_planet_file_does_not_refuse_the_star_catalogue(probe, mode):
    """The catalogue attaches and the 28 stars read; the Earth they are seen
    from is Moshier's. Asked in the two places that reached the star
    reader's thread before ruling 103: $SE_EPHE_PATH, and the shipped
    catalogue's own folder (``ephe``). The ``path`` and ``cwd`` modes are not
    asked: the reader points its thread at a folder itself (``ephe/`` then,
    the engine's own folder now), so neither another thread's folder nor the
    working directory is searched there."""
    clean, doctored = probe(mode), probe(mode, PLANET_FILE)
    ready, stars = _clean(clean, "stars")
    assert ready is True and len(stars) == 28, clean["stars"]
    assert doctored["stars"] == clean["stars"], mode


@pytest.mark.parametrize("mode", ["path", "env", "cwd", "ephe"])
def test_a_planet_file_does_not_move_the_obliquity_read_first_in_its_thread(probe, mode):
    """The engine's obliquity reads, evaluated as written and first in their
    thread (no Moshier body read before them), at four dates, with damaged
    planet and Moon files where Swiss Ephemeris looks: no raise, no move.
    A damaged pair cannot make the old read (swe.calc_ut of ECL_NUT) fail
    either -- the library skips a Moon file it cannot read; only a readable
    one moved it -- so this pin stands beside the static one below."""
    clean, doctored = probe(mode), probe(mode, PLANET_FILE, MOON_FILE)
    values = _clean(clean, "obliquity")
    assert len(values) == 4 and all(len(row) >= 3 for row in values), values
    assert doctored["obliquity"] == values, mode


# ---------------------------------------------------------------------------
# Static pins: every call site, both files.

# The flag's place in each call: (positional index, keyword).
FLAG_ARG = {"calc_ut": (2, "flags"), "rise_trans": (6, "flags"), "nod_aps_ut": (3, "flags"),
            "lun_eclipse_when": (1, "flags"), "fixstar2_ut": (2, "flags"), "calc": (2, "flags")}
# Called with no ephemeris flag, reading no planetary file (deltat_ex's -1
# is the library's default tidal term, not an ephemeris).
NO_FLAG = {"houses", "sidtime", "julday", "revjul", "cotrans", "refrac_extended", "set_ephe_path", "deltat_ex"}


def _swe_calls():
    from conftest import source_files
    for path in source_files():                       # every source module
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "swe"):
                yield path.name, node


def _flag(call):
    index, keyword = FLAG_ARG[call.func.attr]
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[index] if len(call.args) > index else None


def _names_moshier(flag):
    """The flag is engine.MOSHIER_FLAGS or an expression naming FLG_MOSEPH
    and no file ephemeris."""
    text = ast.unparse(flag) if flag is not None else ""
    if text == "MOSHIER_FLAGS":
        return True
    return "swe.FLG_MOSEPH" in text and "FLG_SWIEPH" not in text and "FLG_JPLEPH" not in text


def test_moshier_flags_is_moshier_with_speed():
    from conftest import engine_files
    values = [ast.unparse(node.value) for path in engine_files()
              for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.Assign)
              and [ast.unparse(t) for t in node.targets] == ["MOSHIER_FLAGS"]]
    assert values == ["swe.FLG_MOSEPH | swe.FLG_SPEED"], values
    assert "MOSHIER_FLAGS =" not in APP_PATH.read_text(encoding="utf-8")


def _ecl_nut(call):
    return len(call.args) > 1 and ast.unparse(call.args[1]) == "swe.ECL_NUT"


def test_every_swe_call_is_one_this_file_has_judged():
    called = {call.func.attr for _f, call in _swe_calls()}
    assert called <= set(FLAG_ARG) | NO_FLAG, called - set(FLAG_ARG) - NO_FLAG


def test_every_body_read_by_calc_ut_names_moshier():
    calls = [(f, c) for f, c in _swe_calls() if c.func.attr == "calc_ut" and not _ecl_nut(c)]
    # The floor keeps the scan from passing on nothing. It was 27 until the
    # Sun's hand-over came to be read by weight, which dropped the two speed
    # reads in _pn4_luminary_connections.
    assert len(calls) >= 25, len(calls)
    wrong = [(f, c.lineno, ast.unparse(c)) for f, c in calls if not _names_moshier(_flag(c))]
    assert not wrong, wrong


@pytest.mark.parametrize("name", ["rise_trans", "nod_aps_ut", "lun_eclipse_when", "fixstar2_ut", "calc"])
def test_every_other_ephemeris_call_names_moshier(name):
    sites = [(f, c.lineno, ast.unparse(c)) for f, c in _swe_calls() if c.func.attr == name]
    assert sites, name
    wrong = [(f, c.lineno, ast.unparse(c)) for f, c in _swe_calls()
             if c.func.attr == name and not _names_moshier(_flag(c))]
    assert not wrong, wrong


def test_the_house_calls_ask_for_no_body():
    """swe.houses reads the Sun only for the Sunshine system ('I')."""
    systems = [ast.unparse(c.args[3]) for _f, c in _swe_calls() if c.func.attr == "houses"]
    assert systems and all(s == "b'B'" for s in systems), systems


def test_each_obliquity_read_takes_the_default_delta_t_whatever_ephemeris_file_is_on_disk():
    """No obliquity read is swe.calc_ut (whose delta T took the tidal term of
    any Moon file its thread could read, unless a Moshier read came first);
    each is swe.calc at jd + swe.deltat_ex(jd, -1), the library's default
    tidal term, asking FLG_MOSEPH. This replaces the earlier pin that each
    calc_ut read followed a Moshier read in its function."""
    reads = []
    from conftest import source_files
    for path in source_files():                       # every source module
        tree = ast.parse(path.read_text(encoding="utf-8"))
        reads += [(path.name, node) for node in ast.walk(tree) if _is_obliquity_read(node)]
    assert len(reads) >= 3, len(reads)
    wrong = []
    for name, node in reads:
        when = node.args[0]
        ok = (node.func.attr == "calc" and isinstance(when, ast.BinOp) and isinstance(when.op, ast.Add)
              and ast.unparse(when.right) == f"swe.deltat_ex({ast.unparse(when.left)}, -1)"
              and _names_moshier(_flag(node)))
        if not ok:
            wrong.append(f"{name}:{node.lineno} {ast.unparse(node)}")
    assert not wrong, wrong
