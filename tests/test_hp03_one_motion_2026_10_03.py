"""HP-03, second build: one station rule for every PN IV motion string.

The first build of F7 read the accidental row's three states (retrograde,
stationary, direct) in the I.7 `Motion (7)` column and in Sahl's testimony
80, and the Revolutions page said so in a caption. Its blind check found
the same page's image table still printing the bare sign of the speed
(`Saturn (retrograde)` beside I.7's `stationary`), and five more PN IV
strings reading the sign the same way. These tests pin that every one of
them now reads `motion_state`, the one definition under
`STATION_SPEED_TOLERANCE`, and that the exports carry the rule beside the
tables that print the state.

2026-07-27 at Florence: Saturn moves about -0.0011 a day, inside the
tolerance, in both the root and its revolution for that year.

The third build (after the re-check) took the remaining readers through
the same helper: the wheels' retrograde mark (Chart and Revolutions),
Sahl's short-life testimonies, the house-master's flag and 1.20 grade, the
prosperity clause, point_summary, and the Victors page's direct-course
column, whose own exact-zero rule the owner struck. A source scan names
every reader of the speed's sign that remains, with its reason.
"""
from __future__ import annotations

import re

import pytest

from conftest import assert_no_exception, engine_source, function_source, make_app

FLORENCE = (43.7792, 11.2463)
CUSPS = [(100.0 + 30.0 * i) % 360.0 for i in range(12)]


def _pdata(**overrides):
    values = {"Sun": (40.0, 1.0), "Moon": (20.0, 13.0), "Mercury": (80.0, 1.3), "Venus": (250.0, 1.2),
              "Mars": (170.0, 0.5), "Jupiter": (220.0, 0.08), "Saturn": (305.0, 0.03), "North Node": (130.0, -0.05)}
    values.update(overrides)
    return {p: {"longitude": x, "latitude": 0.0, "distance": 1.0, "speed_in_lon": v, "speed_in_lat": 0.0, "speed_in_dist": 0.0}
            for p, (x, v) in values.items()}


def _chart(**overrides):
    return {"planetary_data": _pdata(**overrides), "ascendant": 100.0, "sect": "Diurnal", "houses": CUSPS}


# --- the one definition --------------------------------------------------------------------

@pytest.mark.parametrize("speed, state", [
    (-0.0031, "retrograde"), (-0.0030, "stationary"), (-0.0011, "stationary"), (0.0, "stationary"),
    (0.0030, "stationary"), (0.0031, "direct"), (0.03, "direct"),
])
def test_motion_state_has_three_states_under_the_one_tolerance(engine, speed, state):
    assert engine["motion_state"]("Saturn", speed) == state


def test_motion_state_agrees_with_the_accidental_row(engine):
    for speed in (-0.0031, -0.0011, 0.0, 0.0031):
        chart = _chart(Saturn=(305.0, speed))
        a = engine["evaluate_accidental_dignities"](chart["planetary_data"], CUSPS, "Diurnal", None)["Saturn"]
        state = engine["motion_state"]("Saturn", speed)
        assert (a["Retrograde"], a["Stationary"]) == (state == "retrograde", state == "stationary"), (speed, state, a)


def test_the_luminaries_are_never_retrograde(engine):
    assert engine["motion_state"]("Sun", -1.0) == "direct"
    assert engine["motion_state"]("Moon", -13.0) == "direct"


# --- the six PN IV strings, at the engine level ---------------------------------------------

def test_ii3_condition_string_reads_the_station(engine):
    data = _pdata(Saturn=(305.0, -0.0011))
    assert engine["_pn4_condition_string"](data, "Saturn").split(", ")[1] == "stationary"
    data = _pdata(Saturn=(305.0, -0.0031))
    assert engine["_pn4_condition_string"](data, "Saturn").split(", ")[1] == "retrograde"


def test_governor_not_retrograde_is_met_by_a_stationary_planet_and_says_so(engine):
    root = _chart(Saturn=(305.0, -0.0011))
    row11 = next(r for r in engine["pn4_governor_condition"]("Saturn", root, root) if r["Test"].startswith("IX.9, 11"))
    assert "not retrograde met (stationary, this app's third state)" in row11["Criteria"], row11["Criteria"]
    assert "not retrograde not met" not in row11["Criteria"], row11["Criteria"]
    moving = _chart(Saturn=(305.0, -0.0031))
    row11 = next(r for r in engine["pn4_governor_condition"]("Saturn", moving, moving) if r["Test"].startswith("IX.9, 11"))
    assert "not retrograde not met" in row11["Criteria"], row11["Criteria"]


@pytest.mark.parametrize("name", ["pn4_ii3_examination", "pn4_distribution_checklist", "pn4_luminary_proxies",
                                  "pn4_revolution_image", "pn4_governor_condition", "_pn4_condition_string"])
def test_each_pn4_motion_reader_goes_through_motion_state(name):
    body = function_source(name)
    assert "motion_state(" in body, name
    assert "speed_in_lon', 1.0) < 0" not in body, name


def test_no_pn4_string_reads_the_bare_sign_of_the_speed():
    """The sign of the speed decides a motion string nowhere in the PN IV
    code: every `pn4` function that prints a motion goes through
    motion_state. (The third build took Sahl's testimonies, the wheels and
    point_summary through it too; the source scan below holds the whole
    file.)"""
    import ast
    tree = ast.parse(engine_source())
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and "pn4" in n.name]
    assert len(names) > 20, names
    bad = [n for n in names if re.search(r"'retrograde' if .*speed_in_lon.* < 0 else 'direct'", function_source(n))]
    assert not bad, bad


# --- one page, one motion (the check's reproduction) ------------------------------------------

@pytest.fixture(scope="module")
def saturn_station_export():
    at = make_app(date="2026-07-27", page="timing").run(timeout=300)
    assert_no_exception(at)
    return at.session_state["_analysis_export"]


def test_one_page_one_motion_for_a_stationary_planet(saturn_station_export):
    pred = saturn_station_export["results"]["Prediction"]
    i7 = {(r["Planet"], r["Chart"]): r["Motion (7)"] for t in pred["The reading checklist (PN IV I.7, 1-26)"]
          for r in t["rows"] if "Motion (7)" in r}
    image = {(r["Chart"], r["Point"]) for t in pred["The image of the revolution of the year: its points (PN IV I.6, 3-8)"]
             for r in t["rows"] if str(r.get("Point", "")).startswith("Saturn (")}
    assert i7[("Saturn", "revolution")] == "stationary"
    assert i7[("Saturn", "root")] == "stationary"
    assert ("revolution", "Saturn (retrograde)") not in image, (i7, image)
    assert image == {("revolution", "Saturn (stationary)"), ("root", "Saturn (stationary)")}, image


@pytest.fixture(scope="module")
def saturn_station_releaser_export():
    at = make_app(date="2026-07-27", page="releaser").run(timeout=300)
    assert_no_exception(at)
    return at.session_state["_analysis_export"]


# Cells that pair the planet's name with "retrograde" or "direct" in a sense
# that is not the planet's own motion: a sentence title, or a quoted text.
_MOTION_WORD_ALLOWLIST = (
    "The Moon connects with a retrograde planet",      # 1.18, 1's title
)


def _cells_calling_saturn_retrograde_or_direct(pred):
    """Every Prediction cell that names Saturn within a clause of the word
    `retrograde` or `direct` (whole words: `directions` is not one), minus
    the allowlist. The third build widened this from three fixed phrases:
    the re-check found "Saturn by square on day 0.2, retrograde" slipping
    past them."""
    bad = []
    for heading, tables in pred.items():
        for t in tables:
            for r in t["rows"]:
                for k, v in r.items():
                    s = str(v)
                    if "Saturn" not in s or any(a in s for a in _MOTION_WORD_ALLOWLIST):
                        continue
                    if (re.search(r"Saturn(?:[^.;\n]|\.(?=\d)){0,60}\b(retrograde|direct)\b", s)
                            or re.search(r"\b(retrograde|direct)\b(?:[^.;\n]|\.(?=\d)){0,30}Saturn", s)):
                        bad.append((heading, k, s[:120]))
    return bad


def test_no_prediction_cell_calls_saturn_retrograde_on_that_chart(saturn_station_export):
    assert not _cells_calling_saturn_retrograde_or_direct(saturn_station_export["results"]["Prediction"])


def test_no_releaser_cell_calls_saturn_retrograde_on_that_chart(saturn_station_releaser_export):
    assert not _cells_calling_saturn_retrograde_or_direct(saturn_station_releaser_export["results"]["Prediction"])


def test_the_scan_sees_the_releaser_cell_it_was_widened_for():
    """The widened scan catches the shape of the re-check's finding 25 cell
    and the two older shapes, and lets 1.18, 1's title through."""
    pred = {"h": [{"rows": [
        {"Fact": "her first perfection in Capricorn: Saturn by square on day 0.2, retrograde, receiving her"},
        {"Point": "Saturn (retrograde)"},
        {"Fact": "Saturn: direct"},
        {"Testimony": "1. The Moon connects with a retrograde planet not receiving her", "Fact": "Saturn stationary"},
        {"Fact": "Saturn, by primary directions"},
    ]}]}
    assert [b[2][:14] for b in _cells_calling_saturn_retrograde_or_direct(pred)] == [
        "her first perf", "Saturn (retrog", "Saturn: direct"]


def test_the_exports_carry_the_station_rule_beside_the_state(saturn_station_export, engine):
    """The page states the rule once under I.7 and once under Strength; the
    export prints `stationary` and drops 80, so it carries the same line as
    those two tables' citations."""
    results = saturn_station_export["results"]
    i7 = results["Prediction"]["The reading checklist (PN IV I.7, 1-26)"]
    planets = next(t for t in i7 if any("Motion (7)" in r for r in t["rows"]))
    strength = results["Configurations"]["Strength of the Planets"][0]
    tol = str(engine["STATION_SPEED_TOLERANCE"])
    assert f"within {tol} degrees a day" in planets["citation"], planets.get("citation")
    assert f"within {tol} degrees a day" in strength["citation"], strength.get("citation")
    assert "Ch. 3, 78-88" in strength["citation"]


# --- the re-check's two breaks (24, 25): the wheel and Sahl's testimonies ---------------------

def test_the_revolutions_wheel_marks_saturn_as_its_tables_do(monkeypatch):
    """Finding 24: the wheel drew ℞ beside a Saturn its own page's tables
    called stationary. The ℞ goes only where motion_state says retrograde."""
    import engine
    at = make_app(date="2026-07-27", page="timing")
    caught, orig = [], engine.generate_multiwheel_svg
    monkeypatch.setattr(engine, "generate_multiwheel_svg", lambda *a, **k: caught.append(orig(*a, **k)) or caught[-1])
    at.run(timeout=300)
    assert_no_exception(at)
    pred = at.session_state["_analysis_export"]["results"]["Prediction"]
    i7 = {r["Chart"]: r["Motion (7)"] for t in pred["The reading checklist (PN IV I.7, 1-26)"]
          for r in t["rows"] if r.get("Planet") == "Saturn" and "Motion (7)" in r}
    assert caught, "the Revolutions page drew no wheel"
    texts = re.findall(r">([^<>]*)</text>", caught[0])
    i = next(i for i, t in enumerate(texts) if t.startswith("♄") and re.fullmatch(r"\d+°", texts[i + 1]))
    assert ("℞" in "".join(texts[i + 1:i + 5])) == (i7["revolution"] == "retrograde"), (i7, texts[i:i + 5])
    assert i7["revolution"] == "stationary"


def test_the_releaser_page_reads_saturn_as_the_revolutions_page_does(saturn_station_releaser_export, saturn_station_export):
    """Finding 25: Sahl 1.18, 1's fact called Saturn retrograde on the chart
    whose Revolutions tables call him stationary."""
    i7 = {r["Chart"]: r["Motion (7)"] for t in saturn_station_export["results"]["Prediction"]["The reading checklist (PN IV I.7, 1-26)"]
          for r in t["rows"] if r.get("Planet") == "Saturn" and "Motion (7)" in r}
    pred = saturn_station_releaser_export["results"]["Prediction"]
    rows = [r for t in pred["The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)"] for r in t["rows"]]
    t1 = next(r for r in rows if str(r.get("Testimony", "")).startswith("1. The Moon connects"))
    assert (", retrograde," in t1["Fact"]) == (i7["root"] == "retrograde"), (i7, t1["Fact"])
    assert ", stationary," in t1["Fact"], t1["Fact"]


# --- the source scan: the sign of the speed decides a motion state nowhere else ----------------

def _speed_sign_readers(src):
    """Every top-level function in `src` whose code (comments and strings
    dropped) compares a longitude speed with a number -- `speed < 0`,
    `v > 0.0`, `.get('speed_in_lon', 1.0) < 0` -- mapped to the lines."""
    import ast
    import io
    import tokenize
    code_lines = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                        tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        if tok.type == tokenize.STRING and "speed" not in tok.string:
            continue   # prose and labels are not readers; a 'speed_in_lon' key is
        code_lines[tok.start[0]] = code_lines.get(tok.start[0], "") + " " + tok.string
    forward = re.compile(r"(?:\w*speed\w*(?:\s*\[[^\]]*\])?|\.get\(\s*'speed\w*'[^)]*\))[\s'\]\)]*(?:<=?|>=?)\s*-?\d")
    backward = re.compile(r"-?\d(?:\.\d+)?\s*(?:<=?|>=?)\s*\w*speed\w*")
    hits = {}
    for line, text in code_lines.items():
        if "speed_in_lat" in text or "speed_in_dist" in text:
            continue
        if forward.search(text) or backward.search(text):
            hits[line] = text.strip()
    tree = ast.parse(src)
    spans = [(n.name, n.lineno, n.end_lineno) for n in tree.body if isinstance(n, ast.FunctionDef)]
    by_function = {}
    for line, text in hits.items():
        owner = next((name for name, a, b in spans if a <= line <= b), "<module>")
        by_function.setdefault(owner, []).append((line, text))
    return by_function


# The readers of the speed's sign left outside motion_state on purpose.
# Each asks how a planet travels (which way, how fast, when it turns), not
# what state to print for it; none prints "direct" or "retrograde" as the
# planet's condition.
LEFT_ON_PURPOSE = {
    "motion_state": "the one definition itself",
    "_encounter_phase": "an application needs the lighter body actually moving forward",
    "_simulate_forward_uncached": "the moment of a station is where the speed changes sign",
    "calculate_prenatal_syzygy": "a guard against dividing by a zero relative speed",
    "sahl_prenatal_meeting_and_fullness": "a guard against dividing by a zero relative speed",
    "pn4_revolution_jd": "a guard against dividing by a zero speed",
    "_abu_mashar_moon_corruption": "the Moon's slowness; her speed is never negative, so the lower bound is vacuous",
    "evaluate_corruption_of_the_moon": "the Moon's slowness; her speed is never negative, so the lower bound is vacuous",
    "_prosperity_moon_motion": "ahead of or behind the Moon by relative travel",
}


def test_no_speed_sign_motion_reading_remains_outside_motion_state(engine):
    """Every comparison of a longitude speed with a number in both halves
    sits in a function LEFT_ON_PURPOSE names, with its reason; and every
    named function still has one, so the list cannot go stale."""
    from conftest import ui_source
    found = _speed_sign_readers(engine_source())
    found_ui = _speed_sign_readers(ui_source())
    assert not found_ui, found_ui
    unlisted = {name: lines for name, lines in found.items() if name not in LEFT_ON_PURPOSE}
    assert not unlisted, unlisted
    stale = sorted(set(LEFT_ON_PURPOSE) - set(found))
    assert not stale, stale


@pytest.mark.parametrize("name", [
    "generate_hybrid_svg", "_draw_ring_points", "generate_multiwheel_svg", "sahl_eastern_1_22",
    "sahl_syzygy_governor", "_sahl_house_master_years_branch", "sahl_short_life_testimonies",
    "sahl_house_master_flags", "_prosperity_lifetime", "point_summary",
])
def test_each_motion_reader_of_the_third_build_goes_through_motion_state(name):
    body = function_source(name)
    assert "motion_state(" in body, name
    assert "exactly zero speed" not in body, name


# --- the other readers the third build took through the helper, at the engine level -----------

def test_the_chart_page_wheel_marks_only_a_retrograde_planet(engine):
    """The Chart page's wheel and its side list read motion_state: no ℞ for a
    stationary Saturn, and the side list says `stationary`, as the page's
    Motion column does."""
    from datetime import datetime, timedelta
    from conftest import LOCAL_TIME
    local = datetime.combine(datetime(2026, 7, 27).date(), LOCAL_TIME)
    chart = engine["calculate_traditional_chart"](local - timedelta(hours=FLORENCE[1] / 15.0), *FLORENCE)
    state = engine["motion_state"]("Saturn", chart["planetary_data"]["Saturn"]["speed_in_lon"])
    assert state == "stationary", chart["planetary_data"]["Saturn"]["speed_in_lon"]
    svg = engine["generate_hybrid_svg"](chart_data=chart, chart_name="Transits", location_query="Florence",
                                        lat=FLORENCE[0], lon=FLORENCE[1], dt_local=local, tz_name="LMT", wide=True)
    texts = re.findall(r">([^<>]*)</text>", svg)
    i = next(i for i, t in enumerate(texts) if t.startswith("♄") and re.fullmatch(r"\d+°", texts[i + 1]))
    assert "℞" not in "".join(texts[i + 1:i + 5]), texts[i:i + 5]
    side = next(i for i, t in enumerate(texts) if t == "Saturn")
    assert "stationary" in texts[side:side + 5], texts[side:side + 5]
    assert "retrograde" not in "".join(texts[side:side + 5])


def test_the_house_master_flag_and_grade_read_the_station(engine):
    """1.23, 53's "is retrograde" flag and the 1.20 grade's retro arm both
    read motion_state: a stationary Saturn is not retrograde to either."""
    data = _pdata(Saturn=(305.0, -0.0011))
    flags = engine["sahl_house_master_flags"]("Saturn", data, CUSPS)
    assert flags and not [f for f in flags if "is retrograde" in f], flags
    data = _pdata(Saturn=(305.0, -0.0031))
    flags = engine["sahl_house_master_flags"]("Saturn", data, CUSPS)
    assert any("is retrograde" in f for f in flags), flags


def test_sahl_short_life_testimonies_print_the_three_states(engine):
    """Testimonies 4 and 6 print the lord's state from motion_state, so a
    stationary lord reads `stationary`, never `direct` or `retrograde`."""
    chart = _chart(Saturn=(305.0, -0.0011))   # Saturn rules Capricorn: the Lot's sign below
    rows = engine["sahl_short_life_testimonies"](chart, 275.0)["rows"]
    t4 = next(r for r in rows if r["Testimony"].startswith("4."))
    assert "lord of the Lot Saturn: stationary" in t4["Fact"], t4["Fact"]
    assert t4["Met"] == "no"
    chart = _chart(Saturn=(305.0, -0.0031))
    rows = engine["sahl_short_life_testimonies"](chart, 275.0)["rows"]
    t4 = next(r for r in rows if r["Testimony"].startswith("4."))
    assert "lord of the Lot Saturn: retrograde" in t4["Fact"], t4["Fact"]


def test_slow_in_course_is_a_direct_planets_condition(engine):
    """VII.6, 31's "slow in course" read "not retrograde" by the sign of the
    speed, so a planet at its station was slow on one side of rest and not
    the other; it is now a direct planet's condition, the mirror of swift."""
    jd = 2451545.0
    for speed, slow in ((-0.0011, False), (0.0011, False), (0.01, True), (-0.01, False)):
        data = _pdata(Saturn=(305.0, speed))
        essential = engine["evaluate_essential_dignities"](data, "Diurnal")
        accidental = engine["evaluate_accidental_dignities"](data, CUSPS, "Diurnal", jd)
        cond = engine["evaluate_abu_mashar_condition"](data, CUSPS, "Diurnal", essential, accidental, jd, CUSPS[0])
        labels = cond["Saturn"]["Negative Labels"]
        assert any("(31)" in l for l in labels) is slow, (speed, labels)


def test_configurations_does_not_call_a_stationary_saturns_connections_retrogradation():
    at = make_app(date="2026-07-27", page="configurations").run(timeout=300)
    assert_no_exception(at)
    conf = at.session_state["_analysis_export"]["results"]["Configurations"]
    rows = [r for t in conf["Aspects, aversions and connections"] for r in t["rows"]]
    sat = [r for r in rows if "Saturn" in (r.get("Light Planet"), r.get("Heavy Planet"))]
    assert sat and not any("retrogradation" in r["Motion"] for r in sat), [(r["Light Planet"], r["Motion"]) for r in sat]
