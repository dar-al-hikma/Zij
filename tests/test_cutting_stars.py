"""PN IV IX.8, 32-55: the elected releaser directed to the fourteen cutting stars.

Three things are pinned here: the arithmetic, replayed from a table with no ephemeris
read and at the corners that table never reaches; the fourteen, each row's identity held
to its catalogue key; and the reading, with the parts the text leaves unsettled kept open.
"""
from markup import page_cell, page_words
import ast
import csv
import inspect
import math
import random
import re
from datetime import time
import json
from pathlib import Path

import pytest

import engine as E
import ephemeris as M
from conftest import assert_no_exception, make_app, table_nodes
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

FIXTURES = Path(__file__).parent / "fixtures"
UT = (1980, 3, 10, 12.0)
LAT, LON = 40.0, -3.0
COLUMN = "PN IV IX.8, 54-55"
FIRST, SECOND = E.READING_DEPTH_OPTIONS
NOT_REACHED = ("-", "refused")
PROMITTOR_REFUSED = "the promittor never rises or sets at this latitude, so it has no semi-arc to proportion"
# (cutter, sentence, catalogue key or list entry) of every object, as PN IV Fig. 137 identifies it.
THE_FOURTEEN = (
    (6, 34, ",alTau"), (7, 35, ",alLeo"), (8, 36, ",alSco"), (9, 37, ",bePeg"), (10, 39, ",16Per"), (11, 40, ",muLeo"),
    (12, 41, ",epLeo"), (13, 43, "ngc:884"), (13, 43, ",NGC869"), (14, 44, ",laOri"), (14, 44, ",ph-1Ori"),
    (14, 44, "hip:26366"), (15, 45, ",M44"), (16, 46, ",HR6630"), (16, 46, "ngc:6441"), (17, 47, ",nu-1Sgr"),
    (17, 47, "hip:92845"), (18, 49, ",gaSgr"), (19, 50, ",ome-1Cyg"), (19, 50, ",ome-2Cyg"),
)
# Latitude as printed (IX.8, 34-50), by key, in degrees; the three the identity does not bear out stand apart.
PRINTED_LATITUDE = {",alTau": -5 - 10 / 60, ",alSco": -4.0, ",bePeg": 31.0, ",16Per": 20 + 40 / 60, ",muLeo": 12.0,
                    ",epLeo": 9.5, ",NGC869": 40.5, ",laOri": -13 - 50 / 60, ",ph-1Ori": -13 - 50 / 60, ",M44": 40 / 60,
                    ",HR6630": -13.25, ",ome-1Cyg": 63.75, ",ome-2Cyg": 63.75}
FAR_FROM_PRINTED = {",alLeo": 10.0, ",nu-1Sgr": 5 + 40 / 60, ",gaSgr": 2 + 50 / 60}
# The invented chart's Sun directed: each arc from a reference that shares no code with the engine.
SUN_ARCS = (("[10] Cluster near Algol: 16 Persei", "48.58", 48, "2028-10-08"),
            ("[6] Aldebaran (Oculus Tauri): α Tauri", "76.68", 76, "2056-11-14"),
            ("[14] Meissa et al.: φ¹ Orionis", "91.82", 91, "2072-01-06"),
            ("[14] Meissa et al.: λ Orionis", "91.87", 91, "2072-01-25"))
# And the one added row among them, the engine's own reading: no outside reference has been run on it.
SUN_ARC_ADDED = ("[14] Meissa et al.: φ² Orionis", "92.35", 92, "2072-07-18")


def chart_at(ut=UT, lat=LAT, lon=LON):
    jd = E.swe.julday(*ut)
    return dict(E.calculate_traditional_chart_jd(jd, lat, lon), geo_lat=lat)


def sun_of(chart):
    return {"releaser": "the Sun", "longitude": chart["planetary_data"]["Sun"]["longitude"]}


def by_target(record):
    return {row["Target"]: row for row in record["rows"]}


def placed_at(chart):
    stars, _ = E.fixed_star_places(chart["julian_day"])
    return {f",{star.designation}": star for star in stars}


def table(name):
    with open(FIXTURES / name, encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def replay(row):
    return E.semi_arc_direction(*(float(row[k]) for k in ("sig_lon", "sig_lat", "prom_lon", "prom_lat", "armc",
                                                          "geo_lat", "obliquity")))


def refused_points(result):
    return ",".join(name for name in ("significator", "promittor") if result[name]["circumpolar"])


def gap(a, b):
    return abs(((a - b + 180.0) % 360.0) - 180.0)


# ------------------------------------------------------------- the arithmetic


def test_the_arc_table_is_keyed_on_its_name_with_its_mode():
    rows = table("semi_arc_pins.tsv")
    assert len(rows) == 2000
    assert len({row["id"] for row in rows}) == 1000, "a name alone repeats"
    assert len({(row["id"], row["mode"]) for row in rows}) == 2000
    assert all((row["mode"] == "zodiacal") <= (float(row["prom_lat"]) == 0.0) for row in rows)


def test_the_arc_table_replays_with_no_ephemeris_read():
    rows = table("semi_arc_pins.tsv")
    assert rows
    for row in rows:
        result = replay(row)
        key = (row["id"], row["mode"])
        assert refused_points(result) == row["refused"], key
        if row["refused"]:
            assert result["arc"] is None and result["refused"], key
        else:
            assert gap(result["arc"], float(row["arc"])) < 1e-9, key


def test_the_corners_replay_the_horizon_and_the_refusal_boundary():
    rows = table("semi_arc_corners.tsv")
    assert rows
    kinds = {kind: [row for row in rows if row["id"].startswith(kind)] for kind in ("horizon", "grazing")}
    assert len(kinds["horizon"]) == 90 and len(kinds["grazing"]) == 56
    assert {row["refused"] for row in kinds["grazing"]} == {"", "promittor"}, "both sides of the boundary"
    on_it = [row for row in kinds["horizon"] if row["id"].endswith("_0")]
    assert on_it
    for row in rows:
        result = replay(row)
        assert refused_points(result) == row["refused"], row["id"]
        if not row["refused"]:
            # Near grazing the arcsine is at its worst: a step of 1e-8 from the boundary amplifies the last bit.
            assert gap(result["arc"], float(row["arc"])) < 5e-9, row["id"]
    held = [row for row in on_it if not row["refused"]]
    assert held
    for row in held:
        result = replay(row)
        assert result["significator"]["above"] and result["meridian"] == "upper", (row["id"], "on the horizon counts as above")
        assert abs(abs(result["fraction"]) - 1.0) < 1e-12, row["id"]


def test_motion_is_the_frozen_share_not_the_sky_s_turning():
    """Turned by the arc, the promittor stands at the share the significator first had. An arc does
    not fall by the sky's turn: ARMC plus ten degrees moves an arc by 0 at the equator, not at 40."""
    rng = random.Random(41)
    accepted = 0
    for _ in range(4000):
        lat, armc = rng.choice((0.0, 20.0, 33.0, 45.0, 52.0, 60.0, 66.0, -20.0, -45.0, -60.0)), rng.uniform(0.0, 360.0)
        result = E.semi_arc_direction(rng.uniform(0.0, 360.0), 0.0, rng.uniform(0.0, 360.0), rng.uniform(-80.0, 80.0),
                                      armc, lat, 23.44)
        if result["arc"] is None:
            continue
        accepted += 1
        turned = E.semi_arc_terms(result["promittor"]["longitude"], result["promittor"]["latitude"],
                                  (armc + result["arc"]) % 360.0, lat, 23.44)
        distance = turned["md_upper"] if result["meridian"] == "upper" else turned["md_lower"]
        assert gap(distance, result["fraction"] * result["prom_sa"]) < 1e-9
    assert accepted > 2000
    at_equator = [E.semi_arc_direction(100.0, 0.0, 170.0, 5.0, armc, 0.0, 23.44)["arc"] for armc in (60.0, 70.0)]
    at_forty = [E.semi_arc_direction(100.0, 0.0, 170.0, 5.0, armc, 40.0, 23.44)["arc"] for armc in (60.0, 70.0)]
    assert abs(at_equator[1] - at_equator[0]) < 1e-9
    assert abs(at_forty[1] - at_forty[0]) > 1.0


def test_the_mars_witnesses_labelled_zodiacal_and_bodied():
    chart = chart_at()
    mars = chart["planetary_data"]["Mars"]
    args = chart["armc"], LAT, chart["obliquity"]
    zodiacal = {point: E.semi_arc_direction(chart[point], 0.0, mars["longitude"], 0.0, *args)["arc"] for point in ("ascendant", "mc")}
    bodied = {point: E.semi_arc_direction(chart[point], 0.0, mars["longitude"], mars["latitude"], *args)["arc"] for point in ("ascendant", "mc")}
    assert zodiacal["ascendant"] == pytest.approx(67.52849325, abs=1e-8)
    assert zodiacal["mc"] == pytest.approx(167.19593449, abs=1e-8)
    assert bodied["ascendant"] == pytest.approx(65.570, abs=1e-3)
    assert bodied["mc"] == pytest.approx(168.688, abs=1e-3)


# --------------------------------------------------------------- the fourteen


def test_the_table_is_the_fourteen_and_only_they():
    entries = E.PN4_CUTTING_STARS
    assert [(e["cutter"], e["sentence"], e["key"] or e["listed"]) for e in entries] == list(THE_FOURTEEN)
    assert {e["cutter"] for e in entries} == set(range(6, 20))
    assert not [e for e in entries if e["key"] and e["listed"]], "a key or a list entry, not both"
    named = " ".join(f"{e['name']} {e['identified']}" for e in entries)
    assert not re.search(r"Sun\b|Moon|Saturn|Jupiter|Mars\b|Venus|Mercury", named), "the five planets are not this table"


def test_every_key_opens_its_own_star_and_a_near_miss_opens_another():
    chart = chart_at()
    placed = placed_at(chart)

    def read():
        E._fixed_star_catalogue_read()
        reads = {}
        for key in [e["key"] for e in E.PN4_CUTTING_STARS if e["key"]] + ["Ruchbah", "16Per"]:
            place, label, _flag = E.swe.fixstar2_ut(key, chart["julian_day"], E.swe.FLG_MOSEPH)
            reads[key] = (label, place[0], place[1])
        return reads

    reads = E._on_fixed_star_reader(read)
    keys = [entry["key"] for entry in E.PN4_CUTTING_STARS if entry["key"]]
    assert keys
    for key in keys:
        label, lon, lat = reads[key]
        assert label.partition(",")[2] == key[1:], (key, label)
        assert gap(placed[key].longitude, lon) < 1e-3 and abs(placed[key].latitude - lat) < 1e-3, key
    assert reads["Ruchbah"][0].endswith(",deCas"), "by a name, the wrong star: the row is omega Cygni"
    assert reads["16Per"][0].partition(",")[2] != "16Per", "without its comma, another star"


def test_each_row_is_the_star_the_page_printed_by_its_latitude():
    """Read off the page's latitude, each identity is near; the three that are not are the printed slips."""
    placed = placed_at(chart_at())
    assert set(PRINTED_LATITUDE) | set(FAR_FROM_PRINTED) == {e["key"] for e in E.PN4_CUTTING_STARS if e["key"]}
    for key, printed in PRINTED_LATITUDE.items():
        assert abs(placed[key].latitude - printed) < 1.0, key
    for key, printed in FAR_FROM_PRINTED.items():
        assert abs(placed[key].latitude - printed) > 5.0, key


def test_the_four_objects_take_their_places_from_the_grown_catalogue_itself():
    """No stub: the file's entries and the real rows, at a span long enough to reach each."""
    chart = chart_at()
    record = E.pn4_cutting_stars(chart, sun_of(chart), span_years=720)
    stars = {E.fixed_star_identity(star): star for star in E.fixed_star_places(chart["julian_day"])[0]}
    entries = {entry["id"]: entry for entry in E.fixed_star_list_file()}
    assert not [row for row in record["rows"] if row["Degree"] == "not placed"] and record["missing"] == ""
    rows = {row["Target"].split(": ")[1]: row for row in record["rows"]}
    for name, listed in (("Cluster 884", "ngc:884"), ("φ² Orionis", "hip:26366"), ("Cluster 6441", "ngc:6441"),
                         ("ν² Sagittarii", "hip:92845")):
        assert rows[name]["Degree"] == E.get_degree_string(stars[entries[listed]["row"]].longitude), name
    listed = {entry["id"] for entry in E.fixed_star_list_file()}
    assert {e["listed"] for e in E.PN4_CUTTING_STARS if e["listed"]} <= listed


def test_an_absent_object_fills_when_the_sky_grows_the_catalogue(monkeypatch):
    chart = chart_at()
    stars, missing = E.fixed_star_places(chart["julian_day"])
    grown = E._dataclass_replace(stars[0], name="grown", designation="NGC884", catalogue_name="grown", lookup="grown",
                                 longitude=53.9, latitude=20.0, right_ascension=30.0, declination=30.0)
    entries = [dict(entry, row="grown" if entry["id"] == "ngc:884" else entry["row"]) for entry in E.fixed_star_list_file()]
    monkeypatch.setattr(E, "fixed_star_places", lambda jd: (stars + (grown,), missing))
    monkeypatch.setattr(E, "fixed_star_list_file", lambda: tuple(entries))
    row = by_target(E.pn4_cutting_stars(chart, sun_of(chart)))["[13] Nebula in r. hand of Perseus: Cluster 884"]
    assert row["Degree"] != "not placed" and row["Arc (years)"] not in NOT_REACHED


def test_a_catalogue_absent_says_so_and_draws_nothing(monkeypatch):
    chart = chart_at()
    monkeypatch.setattr(E, "fixed_star_places", lambda jd: (None, {}))
    record = E.pn4_cutting_stars(chart, sun_of(chart))
    assert (record["status"], record["rows"]) == ("unavailable", []) and record["note"] == E.fixed_star_refusal()


# ------------------------------------------------------- the rows, direction


def test_the_sun_of_the_invented_chart_by_a_reference_that_shares_no_code():
    chart = chart_at()
    record = E.pn4_cutting_stars(chart, sun_of(chart))
    assert record["status"] == "available" and record["identity"] == "the Sun"
    rows = [row for row in record["rows"] if row["Arc (years)"] not in NOT_REACHED]
    assert [(r["Target"], r["Arc (years)"], r["In the year of age"], r["Date"]) for r in rows] == [*SUN_ARCS, SUN_ARC_ADDED]
    assert [row["Target"] for row in record["rows"]][5:] == [
        "[13] Nebula in r. hand of Perseus: Cluster 884", "[13] Nebula in r. hand of Perseus: Cluster 869"], (
        "after the reached, in the order of the cutters")
    assert list(record["rows"][0]) == ["Target", "Degree", "Arc (years)", "In the year of age", "North or south", COLUMN, "Source", "Date"]


def test_each_arc_is_the_function_s_with_the_star_s_own_latitude_direct_only():
    for ut, lat, lon in ((UT, LAT, LON), ((1955, 7, 20, 21.0), -35.0, 150.0), ((2001, 1, 2, 3.0), 10.0, 77.0)):
        chart = chart_at(ut, lat, lon)
        placed = placed_at(chart)
        start = chart["planetary_data"]["Sun"]["longitude"]
        rows = by_target(E.pn4_cutting_stars(chart, sun_of(chart)))
        keyed = [entry for entry in E.PN4_CUTTING_STARS if entry["key"]]
        assert keyed
        checked = 0
        for entry in keyed:
            star = placed[entry["key"]]
            arc = E.semi_arc_direction(start, 0.0, star.longitude, star.latitude, chart["armc"], lat, chart["obliquity"])["arc"]
            target = f"[{entry['cutter']}] {entry['name']}: {entry['identified']}"
            if arc is None or arc > 120.0:
                assert arc is None or target not in rows, target
                continue
            checked += 1
            assert rows[target]["Arc (years)"] == f"{math.floor(arc * 100.0) / 100.0:.2f}", target
            assert rows[target]["In the year of age"] == int(arc), target
            when = E.pn4_datetime_from_jd(chart["julian_day"] + arc * E.PN4_DIRECTION_YEAR_DAYS)
            assert rows[target]["Date"] == f"{when:%Y-%m-%d}", target
        assert checked


def test_the_star_s_latitude_moves_the_arc():
    chart = chart_at()
    placed = placed_at(chart)
    start, args = chart["planetary_data"]["Sun"]["longitude"], (chart["armc"], LAT, chart["obliquity"])
    aldebaran = placed[",alTau"]
    assert E.semi_arc_direction(start, 0.0, aldebaran.longitude, 0.0, *args)["arc"] == pytest.approx(75.486, abs=1e-3)
    assert E.semi_arc_direction(start, 0.0, aldebaran.longitude, aldebaran.latitude, *args)["arc"] == pytest.approx(76.682, abs=1e-3)


def test_a_refused_star_stands_as_a_row_and_never_falls_back_to_its_zodiac_degree():
    chart = chart_at()
    placed = placed_at(chart)
    capulus = placed[",NGC869"]
    start, args = chart["planetary_data"]["Sun"]["longitude"], (chart["armc"], LAT, chart["obliquity"])
    assert E.semi_arc_direction(start, 0.0, capulus.longitude, 0.0, *args)["arc"] == pytest.approx(59.373, abs=1e-2), "the premise"
    row = by_target(E.pn4_cutting_stars(chart, sun_of(chart)))["[13] Nebula in r. hand of Perseus: Cluster 869"]
    assert row["Arc (years)"] == "refused" and row[COLUMN] == PROMITTOR_REFUSED
    assert (row["In the year of age"], row["Date"], row["North or south"]) == ("-", "-", "-")
    assert row["Degree"] == E.get_degree_string(capulus.longitude)


def test_a_star_past_the_span_is_left_out_and_the_span_is_the_table_s():
    chart = chart_at()
    rows = by_target(E.pn4_cutting_stars(chart, sun_of(chart)))
    assert "[9] Scheat: β Pegasi" not in rows, "its arc is 352.909"
    assert not [t for t, r in rows.items() if r["Arc (years)"] not in NOT_REACHED and float(r["Arc (years)"]) > 120.0]
    assert len(by_target(E.pn4_cutting_stars(chart, sun_of(chart), span_years=50.0))) < len(rows)


@pytest.mark.parametrize("lat", [90.0, -90.0, 66.6, -66.6, 75.0])
def test_the_guard_stands_before_the_arc_above_the_polar_circle(lat):
    chart = dict(chart_at(), geo_lat=lat)
    assert not E._ascensional_method_applies(chart["obliquity"], lat)
    record = E.pn4_cutting_stars(chart, sun_of(chart))
    assert (record["status"], record["rows"]) == ("unavailable", [])
    assert record["note"] == "PN IV direction unavailable at this latitude"


def test_just_inside_the_polar_circle_the_table_stands():
    chart = chart_at()
    lat = 90.0 - chart["obliquity"] - 0.01
    assert E.pn4_cutting_stars(dict(chart, geo_lat=lat), sun_of(chart))["status"] == "available"


# ----------------------------------------------------------- 54-55's reading


class Star:
    def __init__(self, declination, latitude):
        self.declination, self.latitude = declination, latitude


@pytest.mark.parametrize("star, inclination, latitude, sides, said", [
    # Both measures, both on one side (55: more confirmed).
    (Star(10, 5), 3, 2, "Inclination: star north, releaser north. Latitude: star north, releaser north.", "kills, more confirmed"),
    (Star(-10, -5), -3, -2, "Inclination: star south, releaser south. Latitude: star south, releaser south.", "kills, more confirmed"),
    # A releaser with no latitude: the one measure there is.
    (Star(10, -5), 3, None, "Inclination: star north, releaser north. Latitude: star south, releaser none.", "kills"),
    (Star(-10, 5), 3, None, "Inclination: star south, releaser north. Latitude: star north, releaser none.", "a disaster, not killing"),
    # Both differ (55).
    (Star(10, 5), -3, -2, "Inclination: star north, releaser south. Latitude: star north, releaser south.", "a disaster, not killing"),
    # One matches, one differs: 54 and 55 part, so the cell stays open.
    (Star(10, 5), 3, -2, "Inclination: star north, releaser north. Latitude: star north, releaser south.", "open: kills by 54, a disaster by 55"),
    (Star(10, 5), -3, 2, "Inclination: star north, releaser south. Latitude: star north, releaser north.", "open: kills by 54, a disaster by 55"),
    # On the circle itself there is no side to compare.
    (Star(10, 5), 0.0, None, "Inclination: star north, releaser none. Latitude: star north, releaser none.", "not compared"),
    (Star(10, 5), 0.0, 2, "Inclination: star north, releaser none. Latitude: star north, releaser north.", "kills"),
])
def test_the_two_sides_and_what_the_sentences_say(star, inclination, latitude, sides, said):
    assert E.pn4_cutting_reading(star, inclination, latitude) == (sides, said)


def test_only_the_moon_of_the_releasers_brings_a_latitude():
    chart = chart_at()
    placed = placed_at(chart)
    moon = chart["planetary_data"]["Moon"]
    assert moon["latitude"] > 4.0, "the premise"
    rows = E.pn4_cutting_stars(chart, {"releaser": "the Moon", "longitude": moon["longitude"]})["rows"]
    reached = [row for row in rows if row["North or south"] != "-"]
    assert reached
    assert all("releaser north." in row["North or south"].split("Latitude: ")[1] for row in reached)
    for name in ("the Sun", "the Ascendant", "the Lot of Fortune", "the meeting (the last New Moon)", "the fullness (the last Full Moon)"):
        rows = E.pn4_cutting_stars(chart, {"releaser": name, "longitude": 10.0})["rows"]
        compared = [row for row in rows if row["North or south"] != "-"]
        assert compared
        assert all(row["North or south"].endswith("releaser none.") for row in compared), name
    # The Moon's arc is her degree's, as the page's other directions take it; only the sides read her body.
    rows = by_target(E.pn4_cutting_stars(chart, {"releaser": "the Moon", "longitude": moon["longitude"]}))
    args = chart["armc"], LAT, chart["obliquity"]
    keyed = [entry for entry in E.PN4_CUTTING_STARS if entry["key"]]
    assert keyed
    checked = 0
    for entry in keyed:
        star = placed[entry["key"]]
        arc = E.semi_arc_direction(moon["longitude"], 0.0, star.longitude, star.latitude, *args)["arc"]
        by_body = E.semi_arc_direction(moon["longitude"], moon["latitude"], star.longitude, star.latitude, *args)["arc"]
        target = f"[{entry['cutter']}] {entry['name']}: {entry['identified']}"
        if arc is not None and arc <= 120.0:
            checked += 1
            assert gap(arc, by_body) > 0.5, "the premise: her body would move it"
            assert rows[target]["Arc (years)"] == f"{math.floor(arc * 100.0) / 100.0:.2f}", target
    assert checked


def test_the_moon_s_inclination_is_her_body_s():
    chart = chart_at()
    moon = chart["planetary_data"]["Moon"]
    body = E.semi_arc_terms(moon["longitude"], moon["latitude"], chart["armc"], LAT, chart["obliquity"])["declination"]
    seen = {}
    real = E.pn4_cutting_reading

    def spy(star, inclination, latitude):
        seen["inclination"], seen["latitude"] = inclination, latitude
        return real(star, inclination, latitude)
    try:
        E.pn4_cutting_reading = spy
        E.pn4_cutting_stars(chart, {"releaser": "the Moon", "longitude": moon["longitude"]})
    finally:
        E.pn4_cutting_reading = real
    assert seen == {"inclination": body, "latitude": moon["latitude"]}


# ------------------------------------------------------ the releaser it takes


def test_no_releaser_refused_and_open_have_no_rows():
    chart = chart_at()
    absent = E.pn4_cutting_stars(chart, {"releaser": None, "longitude": None})
    assert (absent["status"], absent["rows"], absent["note"]) == ("absent", [], E.PN4_CUTTING_NO_RELEASER)
    refused = E.pn4_cutting_stars(chart, {"releaser": None, "longitude": None, "refused": "the reason"})
    assert (refused["status"], refused["rows"], refused["note"]) == ("unavailable", [], "the reason")


OPEN_ELECTION = (1900, 4, 27, 8.0), 43.7696, 11.2558


def _bundle(ut, lat, lon, **kw):
    jd = E.swe.julday(*ut)
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    chronocrats = E.calculate_chronocrats(jd, lat, lon, int(ut[3]), 0.0)
    return chart, E.pn4_timing_bundle(chart, lat, lon, E.CivilDate(*ut[:3]), E.CivilDate(ut[0] + 30, 6, 1),
                                      E.PN4_MONTHLY_TURN_OPTIONS[0], chronocrats, **kw)


def test_an_open_election_is_directed_on_each_arm_and_no_arm_chosen():
    chart, bundle = _bundle(*OPEN_ELECTION)
    assert E.is_unresolved(bundle["releaser"]["releaser"]), "the premise: the election is open"
    assert (bundle["cutting_stars"]["status"], bundle["cutting_stars"]["rows"]) == ("unavailable", [])
    assert bundle["cutting_stars"]["note"] == E.PN4_CUTTING_UNRESOLVED
    arms = bundle["cutting_star_arms"]
    assert arms
    assert [arm for arm, _record in arms] == list(E.SAHL_MOON_ORIENTALITY_ARMS)
    pairs = list(zip(arms, bundle["releaser"]["orientation_alternatives"]))
    assert len(pairs) == 2
    for (arm, record), (name, whole) in pairs:
        assert arm == name and record["identity"] == whole["releaser"] and record["longitude"] == whole["longitude"]
        assert record["rows"] or record["status"] == "absent"


def test_the_elected_releaser_is_what_is_directed_never_the_indicator():
    chart, bundle = _bundle(UT, LAT, LON)
    record = bundle["releaser"]
    assert record["releaser"] == "the Sun" and record["house_master"] == "Mars", "the premise: they differ"
    stars = bundle["cutting_stars"]
    assert (stars["identity"], stars["longitude"]) == ("the Sun", record["longitude"]) and bundle["cutting_star_arms"] == []
    assert [row["Reaches"] for row in bundle["hm_turning"]] == [
        row["Reaches"] for row in E.sahl_house_master_turning("Mars", chart["planetary_data"])], "the turning is untouched"
    for name in ("sahl_house_master_turning", "sahl_house_master_direction", "_pn4_distribute", "generate_hit_strip_svg"):
        assert "PN4_CUTTING_STARS" not in inspect.getsource(getattr(E, name)), name
        assert "cutting_stars" not in inspect.getsource(getattr(E, name)), name


def test_no_star_row_changes_a_distributor_table():
    chart, bundle = _bundle(UT, LAT, LON)
    targets = {row["Target"] for row in bundle["cutting_stars"]["rows"]}
    assert targets
    for rows in (bundle["releaser_rows"], bundle["pn4_releaser"]["rows"], bundle["distribution_rows"]):
        assert not targets & {str(value) for row in rows for value in row.values()}


@pytest.mark.parametrize("status", ["tangency", "coincidence", "unresolved"])
def test_a_withheld_ascendant_refuses_before_anything_is_computed(monkeypatch, status):
    monkeypatch.setattr(M, "division_status", lambda *_a: status)
    called = []
    monkeypatch.setattr(E, "pn4_cutting_stars", lambda *a, **k: called.append(a))
    _chart, bundle = _bundle((1975, 3, 14, 18.0), 70.0, 20.0)
    assert set(bundle) == {"refused"} and not called


def test_the_turning_s_docstring_no_longer_takes_the_bracket_numbers_for_sentences():
    doc = E.sahl_house_master_turning.__doc__
    assert "IX.8, 6-19" not in doc and "[6-19] of IX.8, 32" in doc


# ---------------------------------------------------------------- the page


def _run(ut, lat, lon, depth=None, page="releaser"):
    at = make_app(date=f"{ut[0]:04d}-{ut[1]:02d}-{ut[2]:02d}", page=page, timeout=180)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(int(ut[3]), 0)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    if depth:
        at.session_state["_reading_depth"] = depth
    at.run()
    assert_no_exception(at, f"{page} {ut}")
    return at


def test_a_page_and_a_report_say_the_star_never_rises_and_the_file_keeps_the_engine_s_sentence():
    """A word the page does not otherwise use, under a column whose source is not its own."""
    printed = "the star never rises or sets at this latitude"
    assert page_cell(PROMITTOR_REFUSED) == printed
    at = _run(UT[:4], LAT, LON)
    frame = next(node.value for found, node in table_nodes(at) if found == E.PN4_CUTTING_STARS_HEADING)
    assert printed in set(frame[COLUMN]) and PROMITTOR_REFUSED not in set(frame[COLUMN])
    report = at.session_state["_analysis_markdown"]
    assert printed in report and PROMITTOR_REFUSED not in report
    assert PROMITTOR_REFUSED in json.dumps(at.session_state["_analysis_export"], ensure_ascii=False)


def under_heading(at):
    heading = E.PN4_CUTTING_STARS_HEADING
    drawn, inside = [], False
    for node in at.main:
        kind = getattr(node, "type", None)
        if kind == "subheader":
            inside = node.value == heading
        if inside and kind in ("subheader", "caption", "markdown", "warning"):
            drawn.append(str(node.value))
        elif inside and kind == "dataframe":
            drawn.append(node.value.to_csv())
    return "\n".join(drawn)


@pytest.mark.parametrize("depth", [FIRST, SECOND])
def test_the_page_draws_the_table_at_both_depths_as_it_draws_pn_iv_s_testimony(depth):
    at = _run(UT, LAT, LON, depth)
    text = under_heading(at)
    assert page_words(E.PN4_CUTTING_STARS_READING) in text and page_words(E.PN4_CUTTING_STARS_LIMITS) in text
    assert "48.58" in text and "refused" in text and "not placed" not in text
    assert "α Tauri" in text and "so not placed" not in text
    # A date never breaks at its hyphens in the narrow last column.
    assert any('class="zij-whole">2028-10-08<' in getattr(getattr(node, "proto", None), "body", "") for node in at.main
               if getattr(node, "type", None) == "dataframe")


def test_the_strip_is_not_fed_the_stars():
    source = Path(E.__file__).with_name("app.py").read_text(encoding="utf-8")
    calls = re.findall(r"generate_hit_strip_svg\(([^,]+),", source)
    assert calls and not [call for call in calls if "cutting" in call]


def test_the_open_election_draws_each_arm_under_its_label():
    at = _run(*OPEN_ELECTION)
    text = under_heading(at)
    assert E.PN4_CUTTING_UNRESOLVED in text
    arms = E.SAHL_MOON_ORIENTALITY_ARMS
    assert arms
    for arm in arms:
        assert f"**{arm}:**" in text


@pytest.mark.parametrize("status", ["tangency", "coincidence", "unresolved"])
def test_a_withheld_ascendant_draws_no_table(monkeypatch, status):
    monkeypatch.setattr(M, "division_status", lambda *_a: status)
    at = _run((1975, 3, 14, 18.0), 70.0, 20.0)
    assert not under_heading(at)
    assert M.DIVISION_REASONS[status] in [str(w.value) for w in at.main.warning]


def test_the_export_carries_the_rows_and_the_two_lines():
    at = _run(UT, LAT, LON)
    tables = at.session_state["_analysis_export"]["results"]["Prediction"][E.PN4_CUTTING_STARS_HEADING]
    assert len(tables) == 1
    table_ = tables[0]
    assert set(table_["columns"]) == {"Target", "Degree", "Arc (years)", "In the year of age", "North or south", COLUMN, "Source", "Date"}
    assert [row["Target"] for row in table_["rows"]][:4] == [row[0] for row in SUN_ARCS]
    assert E.PN4_CUTTING_STARS_READING in table_["citation"] and E.PN4_CUTTING_STARS_LIMITS in table_["citation"]
    # An open election draws no first table: each arm's rows reach it under the arm's name.
    open_tables = _run(*OPEN_ELECTION).session_state["_analysis_export"]["results"]["Prediction"][E.PN4_CUTTING_STARS_HEADING]
    arms = E.SAHL_MOON_ORIENTALITY_ARMS
    assert len(arms) == 2 and len(open_tables) == len(arms)
    for arm, table_ in zip(arms, open_tables):
        assert table_["label"].startswith(f"{arm}: "), table_["label"]
        assert table_["rows"] and {row["Target"] for row in table_["rows"]} <= _the_fourteen_s_targets()
        assert E.PN4_CUTTING_STARS_READING in table_["citation"] and E.PN4_CUTTING_STARS_LIMITS in table_["citation"]


# ------------------------------------------------------ the rows' names and sources


def _the_fourteen_s_targets():
    return {f"[{entry['cutter']}] {entry['name']}: {entry['identified']}" for entry in E.PN4_CUTTING_STARS}


A_FEW_CHARTS = (((1640, 7, 2, 3.0), 36.0, -5.0), ((1712, 1, 19, 15.0), 52.0, 13.0), ((1860, 9, 30, 8.0), 30.0, 31.0),
                ((1931, 4, 11, 21.0), -33.0, 151.0), ((1999, 12, 5, 6.0), 40.0, -3.7), (UT, LAT, LON))
DOUBTS = {"16 Persei": "fn 247: it seems to be this one, and Dykes would include Algol as well",
          "μ Leonis": "fn 248: it seems to be this one", "ε Leonis": "fn 248: it seems to be this one"}


def _rows_on_a_few_charts():
    rows = []
    for ut, lat, lon in A_FEW_CHARTS:
        chart = chart_at(ut, lat, lon)
        for planet in ("Sun", "Moon", "Jupiter"):     # a releaser's place: any degree will do for a row's name
            rows += E.pn4_cutting_stars(chart, {"releaser": f"the {planet}",
                                                "longitude": chart["planetary_data"][planet]["longitude"]})["rows"]
    return rows


def test_every_target_on_a_few_charts_is_one_of_the_fourteen():
    rows = _rows_on_a_few_charts()
    assert len(rows) > 100
    assert {row["Target"] for row in rows} <= _the_fourteen_s_targets()
    planets = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
    assert not [row["Target"] for row in rows if row["Target"].startswith(planets)]


def test_the_source_column_names_the_sentence_the_figure_and_the_two_doubts():
    by_identity = {entry["identified"]: entry for entry in E.PN4_CUTTING_STARS}
    for entry in E.PN4_CUTTING_STARS:
        doubt = DOUBTS.get(entry["identified"])
        assert entry["source"] == f"PN IV IX.8, {entry['sentence']}; PN IV Fig. 137" + (f"; {doubt}" if doubt else ""), entry
    assert all(name in by_identity for name in DOUBTS)
    rows = _rows_on_a_few_charts()
    drawn = {row["Target"]: row["Source"] for row in rows}
    for entry in E.PN4_CUTTING_STARS:
        target = f"[{entry['cutter']}] {entry['name']}: {entry['identified']}"
        assert drawn.get(target, entry["source"]) == entry["source"], target
    for name in DOUBTS:
        assert any(target.endswith(f": {name}") and DOUBTS[name] in source for target, source in drawn.items()), name


def test_each_source_is_spelled_out_in_the_code_for_a_round_to_read():
    """A locator built at run time reaches no round: the literal holds it, each with its volume."""
    tree = ast.parse(Path(E.__file__).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_pn4_cutter"]
    assert len(calls) == len(E.PN4_CUTTING_STARS)
    for call in calls:
        source = call.args[4]
        assert isinstance(source, ast.Constant), ast.unparse(source)
        assert re.match(r"PN IV IX\.8, \d+; PN IV Fig\. 137(?:; fn \d+: |$)", source.value), source.value


# ------------------------------------------------------ what the text may say


def _published():
    """Every sentence and cell this table adds, the rows of the invented chart's included."""
    chart = chart_at()
    rows = E.pn4_cutting_stars(chart, sun_of(chart))["rows"]
    words = [E.PN4_CUTTING_STARS_HEADING, E.PN4_CUTTING_STARS_READING, E.PN4_CUTTING_STARS_LIMITS, E.PN4_CUTTING_STARS_COLUMN,
             E.PN4_CUTTING_NO_RELEASER, E.PN4_CUTTING_UNRESOLVED]
    words += [str(value) for row in rows for value in row.values()]
    words += [str(value) for entry in E.PN4_CUTTING_STARS for value in entry.values()]
    return words


def test_every_locator_names_its_volume():
    found = [(text, match) for text in _published()
             for match in re.finditer(r"\b(?:I{1,3}|IV|V|VI{0,3}|IX)\.\d+, ?\d+|Fig\. ?\d+", text)]
    assert found
    for text, match in found:
        assert text[:match.start()].endswith("PN IV "), text


def test_the_page_names_no_lesson_course_date_or_file():
    pattern = re.compile(r"Lesson|lesson|course|Course|TNAC|\b20\d\d\b|\.md\b|\.tsv\b|\.py\b|Fig\. 9\b|not built|ruling", re.I)
    texts = [E.PN4_CUTTING_STARS_HEADING, E.PN4_CUTTING_STARS_READING, E.PN4_CUTTING_STARS_LIMITS, E.PN4_CUTTING_NO_RELEASER,
             E.PN4_CUTTING_UNRESOLVED] + [str(v) for entry in E.PN4_CUTTING_STARS for v in entry.values()]
    assert texts
    for text in texts:
        assert not pattern.search(text), text


def test_the_page_says_the_reading_is_its_own_and_what_is_left_out():
    reading, limits = E.PN4_CUTTING_STARS_READING, E.PN4_CUTTING_STARS_LIMITS
    assert "own latitude counted" in reading and "this app's reading" in reading and "PN IV IX.8, 54" in reading
    assert limits.startswith("Directed only from what the election above gives, not from all five PN IV III.3, 1 names. ")
    assert "Only the releaser elected above" not in limits
    assert "a degree a century (PN IV IX.8, 51) and is not computed" in limits
    assert "this app's reading of PN IV IX.8, 54-55" in limits


def test_the_table_agrees_with_the_transcription_of_fig_137_and_its_sentences():
    path = corpus_file("pn4/book_vi_to_ix/pn4_books_vi_to_ix.md")
    skip_without_corpus(path, why="the printed figure")
    text = path.read_text(encoding="utf-8")
    figure = text[text.index("| **Cutter** | **Name / Description**"):text.index("**Figure 137 (PN IV)")]
    cells = {}
    for line in figure.splitlines()[2:]:
        parts = [re.sub(r"</?i>", "", cell).replace("<br>", " ").strip() for cell in line.strip().strip("|").split("|")]
        if len(parts) == 3 and parts[0].isdigit():
            cells[int(parts[0])] = (parts[1], parts[2])
    assert set(cells) == set(range(6, 20))
    entries = E.PN4_CUTTING_STARS
    assert entries
    for entry in entries:
        name, designation = cells[entry["cutter"]]
        assert entry["name"] == re.sub(r"\s+", " ", name), entry
        letters = re.sub(r"[¹²]", "", entry["identified"].split(" ")[0]).strip("()")
        assert letters in designation.replace("Clusters", "Cluster") or entry["identified"] in designation, entry
    for cutter, sentence, _key in THE_FOURTEEN:
        assert re.search(rf"\*\*{sentence}\*\* [^\n]*\[{cutter}\]", text), (cutter, sentence)
