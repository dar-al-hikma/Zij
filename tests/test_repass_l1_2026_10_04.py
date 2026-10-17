"""Re-pass of 2026-10-04, lane L1 (astronomy and time), on the development
repository's main, 428e05e.

Each test asserts the RIGHT behaviour for a finding the re-pass made beside
the fixes of the hostile pass of 2026-10-03 -- a finding that is fixed only
for its reported input ("partly") or a new defect next to a fix -- and is
marked xfail(strict=True), so it fails today and fails loudly the day the
defect is repaired and the mark can go. The report is
process/hostile_pass_2026-10-03/repass/L1_REPASS.md in the corpus.
"""
from __future__ import annotations

import math
from datetime import time

import pytest

from conftest import assert_no_exception, make_app

LMT, STD, MANUAL = "LMT (Local Mean Time)", "Standard time (named zone)", "Manual UTC offset"
FLORENCE = (43.7792, 11.2463)


def XF(ident, claim):
    return pytest.mark.xfail(strict=True, reason=f"{ident}: {claim}")


def _app(date, hhmm, page, lat, lon, standard=LMT, offset=None):
    at = make_app(date=date, page=page)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    at.run()
    assert_no_exception(at, f"{date} {hhmm} {page}")
    return at


def _sidebar(at):
    return "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])


def _page(at):
    out = []
    for kind in ("markdown", "caption", "info", "warning", "error"):
        out.extend(str(n.value) for n in getattr(at.main, kind))
    return "\n".join(out)


def _strip(at):
    return next(c.value for c in at.main.caption if " · " in c.value)


# --- L1-N1 (critical): a zone the database has merged into another -----------
# The time-zone database this app reads (zoneinfo: the pinned tzdata
# package alone, ruling 71) carries, for every zone it has merged since 2022,
# only a LINK to another zone ("L Europe/Berlin Europe/Stockholm" in
# tzdata.zi): the linked zone's own pre-1970 history is not in it.
# timezonefinder still answers the linked name (106 of its 444 zones), so
# the sidebar casts the birth at the other zone's history under the
# birthplace's zone name, although its help says "with daylight saving as
# the zone's own history records it". The right behaviour: the birthplace's
# own offset, or a refusal with a sentence -- never the other zone's.
MERGED = (
    # Sweden kept CET (+01:00) through 1947; Berlin's record (the link's
    # target) has its "Hochsommerzeit" +03:00 CEMT that summer.
    ("Stockholm", 59.3293, 18.0686, "1947-06-01", "+01:00"),
    # Iceland kept -01:00 in winter until 1968; the link's target is
    # Africa/Abidjan, GMT.
    ("Reykjavik", 64.1466, -21.9426, "1950-01-15", "-01:00"),
    # Amsterdam kept its own mean time, +00:19:32, until 1937 (the app's own
    # comment at the named-zone branch says so); the link's target is
    # Europe/Brussels, WET +00:00 that winter.
    ("Amsterdam", 52.3676, 4.9041, "1930-01-15", "+00:19:32"),
)


@pytest.mark.parametrize("city, lat, lon, date, offset", MERGED, ids=[m[0] for m in MERGED])
def test_repass_l1_n1_a_merged_zone_is_not_cast_at_another_zones_history(city, lat, lon, date, offset):
    at = _app(date, (12, 0), "chart", lat, lon, standard=STD)
    text = _sidebar(at)
    refused = len(at.sidebar.error) > 0
    assert refused or f"UTC offset {offset} " in text, (city, text)


# --- L1-N2 (high): the lunation's sect asks another horizon -------------------
def test_repass_l1_n2_the_lunations_sect_divides_day_and_night_as_the_chart_does(engine):
    import swisseph as swe
    lat, lon = FLORENCE
    jd_birth = engine["civil_to_jd"](2009, 10, 20, 12.0)
    cusps, _ascmc = swe.houses(jd_birth, lat, lon, b'B')
    syz = engine["calculate_prenatal_syzygy"](jd_birth, lat, lon, cusps)
    js = syz["jd_syzygy"]
    # The new Moon of 2009-10-18 05:33:04 UT, sixteen seconds after the
    # Sun's visible rising at Florence (05:32:48 UT), his centre still
    # 49.9' below the true horizon: the band where the two horizons differ.
    assert str(engine["CivilMoment"].from_jd(js)) == "2009-10-18 05:33:04"
    assert engine["_sun_is_up"](js, lat, lon) is True
    chart = engine["calculate_traditional_chart_jd"](js, lat, lon)
    sun = chart["planetary_data"]["Sun"]
    centre = math.degrees(math.asin(engine["_sin_altitude"](sun["longitude"], sun["latitude"], sun["distance"],
                                                            chart["obliquity"], chart["armc"], lat))) * 60.0
    assert -52.0 < centre < 0.0, centre
    assert chart["sect"] == "Diurnal"
    # The right behaviour: the lunation is a day lunation, so the degree's
    # (24 Libra 58) day triplicity lord, Saturn, takes the three points, and
    # Saturn (exaltation 4 + triplicity 3) ties Venus (domicile 5 + bound 2).
    assert syz["sect_diurnal"] is True, (syz["sect_diurnal"], syz["active_triplicity_lord"])
    assert syz["active_triplicity_lord"] == "Saturn", syz["active_triplicity_lord"]
    assert engine["is_unresolved"](syz["almuten"]), (syz["almuten"], syz["almuten_score"])


# --- L1-05, partly: the first night after the polar day -----------------------
def test_repass_l1_05_first_night_after_the_polar_day_names_the_missing_event(engine):
    lat, lon = 70.0, 25.0
    jd = engine["civil_to_jd"](2000, 7, 27, 22.0 + 20.0 / 60.0)
    sunset = engine["_previous_sun_event"](jd, lat, lon, False)
    rise_after, _set_after = engine["_next_sun_events"](jd, lat, lon)
    assert sunset is not None and 0 < (jd - sunset) * 1440.0 < 30.0            # set 21:57:35 UT
    assert rise_after is not None and 0 < (rise_after - jd) * 1440.0 < 60.0     # rises 22:56:17 UT
    cr = engine["calculate_chronocrats"](jd, lat, lon, 22, 0.0)
    assert "no sunset falls within the day before" not in cr["Hour Reason"], cr
    at = _app("2000-07-27", (22, 20), "chart", lat, lon, standard=MANUAL, offset=0.0)
    assert "no sunset falls within the day before this moment" not in _page(at).lower()


# --- L1-07, partly: the pole's qualification stays on the Chart page ----------
# The re-pass ran Lots, Dignities, Victors and Revolutions ("timing"); the
# plan's fix is every page built on the Ascendant, so the five others that
# count from it -- places, stakes, the profection, the releaser's places --
# are pinned beside them (G12).
def _pole_ascendant_sentence():
    """app.py's POLE_ASCENDANT_SENTENCE, read from its source (the page is a
    script, not a module to import)."""
    import ast
    from conftest import APP_PATH
    names = {}
    for node in ast.parse(APP_PATH.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] in (
                ["POLE_CROSSING_SENTENCE"], ["POLE_ASCENDANT_SENTENCE"]):
            names[node.targets[0].id] = eval(compile(ast.Expression(node.value), "app.py", "eval"), {}, names)
    return names["POLE_ASCENDANT_SENTENCE"]


@pytest.mark.parametrize("page", ["lots", "dignities", "victors", "timing",
                                  "findings", "configurations", "releaser", "days", "fardar"])
def test_repass_l1_07_the_pole_qualification_reaches_the_pages_built_on_the_ascendant(page):
    at = _app("2000-12-21", (12, 0), page, 90.0, 0.0, standard=MANUAL, offset=0.0)
    # The sentence itself among the page's warnings, not any later "pole" on
    # the page (lane TL, TL-24).
    warnings = [str(w.value) for w in at.main.warning]
    assert _pole_ascendant_sentence() in warnings, warnings


# --- HP-23, partly: the seam in the helpers the fix did not reach -------------
SEAM_HELPERS = ("pn4_bound_lord", "_brightness_category", "_in_last_bound", "_current_bound_width",
                "_counterpart_degree", "_twelfth_part_sign", "_ray_degrees")


@pytest.mark.parametrize("name", SEAM_HELPERS)
def test_repass_hp23_every_one_longitude_helper_reads_the_seam_as_0_aries(engine, name):
    helper = engine[name]
    assert engine["get_zodiac_sign"](-1e-16) == "Aries"
    assert helper(-1e-16) == helper(0.0), (name, helper(-1e-16), helper(0.0))


# --- L1-N3 (low): the circumpolar note states the retired rule ----------------
def test_repass_l1_n3_the_circumpolar_note_states_the_disk_rule():
    at = _app("2000-05-16", (22, 20), "chart", 70.0, 25.0, standard=MANUAL, offset=0.0)
    assert "**Diurnal" in _strip(at)
    text = _page(at)
    i = text.find("Where the Sun is circumpolar.")
    assert i >= 0, text[:300]
    note = text[i:i + 400]
    assert "the sect follows the geometric altitude of the Sun's centre" not in note, note
    assert "disk" in note, note


# --- L1-N4 (low): a manual offset's label is not the offset cast --------------
def test_repass_l1_n4_a_manual_offset_label_names_the_offset_cast():
    at = make_app(date="1982-06-01", page="chart")
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 5.125
    at.run()
    assert_no_exception(at, "manual 5.125")
    text = _sidebar(at)
    refused = len(at.sidebar.error) > 0
    assert refused or "UTC+05:07:30" in text, text


# --- L1-N5 (low): the strip and the box sign a zero offset differently ---------
def test_repass_l1_n5_the_strip_and_the_box_sign_a_zero_offset_alike():
    at = _app("1982-06-01", (12, 0), "chart", 0.0, -0.001)
    assert "UTC offset +00:00:00" in _sidebar(at), _sidebar(at)
    assert "LMT +00:00:00" in _strip(at), _strip(at)


# --- L1-N6 (low): "read at noon UT" on the birth date -------------------------
def test_repass_l1_n6_a_birth_date_target_says_it_stands_at_the_birth(engine):
    import json
    at = make_app(date="1240-05-23", page="timing")          # born 14:30 LMT Florence = 13:45:01 UT
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1240-05-23"
    at.run()
    assert_no_exception(at, "timing on the birth date")
    text = _page(at)
    header = next(line for line in text.splitlines() if "completed (born" in line)
    assert "read at noon UT" not in header or "birth's own moment" in text, header
    exp = at.session_state["_analysis_export"]
    export = exp if isinstance(exp, dict) else json.loads(exp)
    hour = export["target"]["hour"]
    assert "12:00 UT" not in hour or "birth" in hour, hour
