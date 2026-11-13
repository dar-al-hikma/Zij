"""Three readings of the Moon and the house-master.

The Moon's defects. Sahl, The Introduction Ch. 3, 104 and 109 (Sahl I p. 70): "or she is connecting with
a star in its fall"; "or connecting with a planet falling from the stakes". Neither asks that they look. Ch. 3,
20-21 (Sahl I pp. 53-54, fn 58) calls the body contact across a sign's end a connection: "it is connected with
it", though "it will not see it". 111 counts that row as connected, and so do 104 and 109.

The house-master at a station. On Nativities 1.20, 8 (Sahl I p. 298) lists "eastern, direct, in a good position",
and 10's and 11's "enhanced" refer to it (fn 152); a station is neither direct nor retrograde (Gr. Intr. III.1, 9;
VII.2, 42-43), so it is not enhanced. 20 (Sahl I p. 299), "not retrograde and not burned", then gives a stake the
middle years. 12 (Sahl I p. 299), "in the house of Good Fortune and it is a diurnal planet in one of its places,
eastern", names no motion and keeps its greater years. The precision is the engine's own station tolerance.

A planet the Moon meets twice. PN IV II.22, 2 (PN IV p. 265) counts planets: "for if it was two planets, the year is
divided into two halves ... then the year is divided according to their number". One planet met twice is one planet
with one portion; it takes it at its first meeting, the order being the order of first connection.
"""
from __future__ import annotations

import json
import re
from datetime import time

import pytest

from conftest import assert_no_exception, make_app
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus


def _utc_chart(engine, year, month, day, hour, lat, lon):
    jd = engine["civil_local_to_jd_ut"](year, month, day, hour, 0.0)
    return jd, engine["calculate_traditional_chart_jd"](jd, lat, lon)


def _years(engine, chart, planet):
    data = chart["planetary_data"]
    essential = engine["evaluate_essential_dignities"](data, chart["sect"])
    return (engine["sahl_house_master_years"](planet, data, chart["houses"], chart["sect"], essential),
            engine["jn_years_fallback"](planet, data, chart["houses"], chart["sect"], essential))


def _table_row(engine, chart, planet):
    data = chart["planetary_data"]
    essential = engine["evaluate_essential_dignities"](data, chart["sect"])
    rows = engine["evaluate_planetary_years_display"](data, chart["houses"], chart["ascendant"], chart["sect"],
                                                      essential, supplement=True)
    row = next(r for r in rows if r["Planet"] == planet)
    grant = next(v for k, v in row.items() if k.startswith("On Nativities 1.20 grants"))
    supplement = next(v for k, v in row.items() if k.startswith("Where On Nativities 1.20 is silent"))
    return grant, supplement


# --- the Moon's defects: 104 and 109 read the connection test ---------------------------------------------


def _defects(engine, lat, lon):
    """1950-09-10 08:00 UT: the Moon at the end of Leo, Venus just inside Virgo, her fall: across the sign, by body."""
    _jd, chart = _utc_chart(engine, 1950, 9, 10, 8.0, lat, lon)
    return chart, engine["evaluate_corruption_of_the_moon"](chart["planetary_data"], chart["houses"], chart["sect"])


def test_the_moon_row_is_the_body_connection_across_signs(engine):
    """The fixture stands or the next pins are vacuous: an aversion that Sahl's test admits."""
    chart, _found = _defects(engine, 0.0, -112.0)
    with engine["doctrine"](engine["SAHL"]):
        rows = engine["_pairwise_configurations"](chart["planetary_data"])
        row = next(r for r in rows if {r["p1"], r["p2"]} == {"Moon", "Venus"})
        assert row["aspect_name"] == "Aversion"
        assert engine["_sahl_body_row"](row) and engine["_is_connected"](row)
    assert engine["get_zodiac_sign"](chart["planetary_data"]["Venus"]["longitude"]) == "Virgo"


def test_at_the_equator_104_and_109_both_name_venus(engine):
    _chart, found = _defects(engine, 0.0, -112.0)
    assert found["testimonies"][104]["matched"] and found["testimonies"][109]["matched"]
    assert any("Venus" in clause for clause in found["testimonies"][104]["clauses"])
    assert any("Venus" in clause for clause in found["testimonies"][109]["clauses"])
    assert found["unique_testimony_count"] == 4


def test_at_london_104_alone_and_the_count_is_three(engine):
    _chart, found = _defects(engine, 51.5, -0.12)
    assert found["testimonies"][104]["matched"]
    assert any("Venus" in clause for clause in found["testimonies"][104]["clauses"])
    assert not found["testimonies"][109]["matched"]
    assert found["unique_testimony_count"] == 3


def test_104_and_109_read_the_set_111_reads(engine):
    """Over seeded charts a Moon with any connected planet is never wild, and every planet 104 or 109 names is in
    that set: the three testimonies share one test. 400 charts; the precision is only that sample's."""
    import random

    rng = random.Random(20261103)
    swe = engine["swe"]
    low, high = swe.julday(1900, 1, 1, 0.0), swe.julday(2050, 1, 1, 0.0)
    named = []
    for _ in range(400):
        chart = engine["calculate_traditional_chart_jd"](rng.uniform(low, high), rng.uniform(-60, 60), rng.uniform(-180, 180))
        found = engine["evaluate_corruption_of_the_moon"](chart["planetary_data"], chart["houses"], chart["sect"])
        with engine["doctrine"](engine["SAHL"]):
            rows = engine["_pairwise_configurations"](chart["planetary_data"])
            connected = {(set((r["p1"], r["p2"])) - {"Moon"}).pop() for r in rows
                         if "Moon" in (r["p1"], r["p2"]) and (r["aspect_name"] != "Aversion" or engine["_sahl_body_row"](r))
                         and engine["_is_connected"](r)}
        assert found["testimonies"][111]["matched"] == (not connected)
        clauses = found["testimonies"][104]["clauses"] + found["testimonies"][109]["clauses"]
        named += [(clause.split()[2].rstrip(","), connected) for clause in clauses if clause.startswith("Connecting with ")]
    assert len(named) >= 10
    assert [planet for planet, connected in named if planet not in connected] == []


def test_abu_mashars_test_never_admits_an_aversion(engine):
    """His reader keeps the same words (`aspect_name != 'Aversion' and _is_connected`), and they are harmless there:
    under his doctrine no aversion row is connected (Gr. Intr. VII.4, 13; VII.5, 14), this chart's body row included."""
    _jd, chart = _utc_chart(engine, 1950, 9, 10, 8.0, 0.0, -112.0)
    with engine["doctrine"](engine["ABU_MASHAR"]):
        rows = engine["_pairwise_configurations"](chart["planetary_data"])
        aversions = [r for r in rows if r["aspect_name"] == "Aversion"]
        assert [{r["p1"], r["p2"]} for r in aversions if {r["p1"], r["p2"]} == {"Moon", "Venus"}] == [{"Moon", "Venus"}]
        assert [r for r in aversions if engine["_is_connected"](r)] == []


# --- the house-master at a station --------------------------------------------------------------------------

# Jupiter's first station of 1950, at Moshier's speed: either side of rest, inside the app's tolerance.
JUPITER_STATION = [((1950, 6, 26, 22.0), 1), ((1950, 6, 27, 2.0), 10)]


@pytest.mark.parametrize("moment, division", JUPITER_STATION)
def test_a_stationary_jupiter_in_a_stake_takes_the_middle_years(engine, moment, division):
    _jd, chart = _utc_chart(engine, *moment, 51.5, -0.12)
    assert engine["motion_state"]("Jupiter", chart["planetary_data"]["Jupiter"]["speed_in_lon"]) == "stationary"
    grant, fallback = _years(engine, chart, "Jupiter")
    assert (grant["sentence"], grant["grade"], grant["years"], grant["division"]) == ("1.20, 20", "middle", 45.5, division)
    assert grant["facts"]["share"] and grant["facts"]["eastern"] and not grant["facts"]["retrograde"]
    assert "not retrograde and not burned" in grant["text"]
    assert fallback is None
    assert _table_row(engine, chart, "Jupiter") == ("middle (1.20, 20)", "-")


def test_the_two_station_pins_sit_either_side_of_rest(engine):
    speeds = [_utc_chart(engine, *moment, 51.5, -0.12)[1]["planetary_data"]["Jupiter"]["speed_in_lon"]
              for moment, _division in JUPITER_STATION]
    assert speeds[0] > 0.0 > speeds[1]


def test_a_stationary_diurnal_planet_in_the_eleventh_takes_12s_greater_years(engine):
    """The chart was searched for: Jupiter's station above, the same moment, 51.5 N, longitudes in five-degree
    steps until he stood in the eleventh division."""
    _jd, chart = _utc_chart(engine, 1950, 6, 26, 22.0, 51.5, 40.0)
    assert engine["motion_state"]("Jupiter", chart["planetary_data"]["Jupiter"]["speed_in_lon"]) == "stationary"
    grant, fallback = _years(engine, chart, "Jupiter")
    assert (grant["sentence"], grant["grade"], grant["years"], grant["division"]) == ("1.20, 12", "greater", 79, 11)
    assert "the house of Good Fortune" in grant["text"]
    assert fallback is None
    assert _table_row(engine, chart, "Jupiter") == ("greater (1.20, 12)", "-")


def test_an_eastern_mercury_at_a_station_is_diurnal_for_12(engine):
    """Mercury's sect is his phase wherever the app reads it: eastern, so diurnal. Found the same way."""
    chart = engine["calculate_traditional_chart_jd"](2433551.0, 51.5, -70.0)
    assert engine["motion_state"]("Mercury", chart["planetary_data"]["Mercury"]["speed_in_lon"]) == "stationary"
    grant, _fallback = _years(engine, chart, "Mercury")
    assert (grant["sentence"], grant["grade"], grant["years"], grant["division"]) == ("1.20, 12", "greater", 76, 11)


def test_a_stationary_nocturnal_planet_in_the_eleventh_has_no_sentence_and_reaches_the_ladder(engine):
    """Mars, in a share and eastern: 10 fails on "direct" and 12 is a diurnal planet's. The greater years stood in
    the way of Abu 'Ali's ladder, which now answers."""
    chart = engine["calculate_traditional_chart_jd"](2446590.5, 51.5, 0.0)
    assert engine["motion_state"]("Mars", chart["planetary_data"]["Mars"]["speed_in_lon"]) == "stationary"
    grant, fallback = _years(engine, chart, "Mars")
    assert grant["facts"]["share"] and grant["facts"]["eastern"] and grant["division"] == 11
    assert (grant["sentence"], grant["grade"], grant["years"]) == (None, None, None)
    assert (fallback["class"], fallback["count"]) == ("middle", 40.5)
    table_grant, supplement = _table_row(engine, chart, "Mars")
    assert table_grant == "1.20 silent" and "middle" in supplement


def test_a_station_in_the_fifth_by_night_is_not_11s_greater(engine):
    """The reading has 11's parenthesis carry 11's "enhanced"; Mercury, eastern, in a share."""
    chart = engine["calculate_traditional_chart_jd"](2433551.0, 51.5, 100.0)
    assert chart["sect"] == "Nocturnal"
    grant, fallback = _years(engine, chart, "Mercury")
    assert grant["division"] == 5 and (grant["sentence"], grant["grade"]) == (None, None)
    assert (fallback["class"], fallback["count"]) == ("middle", 48)


# (q, share, east, retro, direct, rays, fall, night, diurnal) -> (sentence, grade)
GRADES = [
    # A direct planet: the grades 10, 11, 12 (through 10) and 20 give as before.
    ((1, True, True, False, True, False, False, False, True), (10, "greater")),
    ((7, True, True, False, True, False, False, False, False), (10, "greater")),
    ((10, True, True, False, True, False, False, True, True), (10, "greater")),
    ((11, True, True, False, True, False, False, False, False), (10, "greater")),
    ((11, True, True, False, True, False, False, False, True), (10, "greater")),
    ((4, True, True, False, True, False, False, False, True), (11, "greater")),
    ((5, True, True, False, True, False, False, True, False), (11, "greater")),
    ((1, False, True, False, True, False, False, False, True), (20, "middle")),
    ((1, True, False, False, True, False, False, False, True), (20, "middle")),
    # The same places at a station.
    ((1, True, True, False, False, False, False, False, True), (20, "middle")),
    ((7, True, True, False, False, False, False, False, False), (20, "middle")),
    ((10, True, True, False, False, False, False, True, True), (20, "middle")),
    ((4, True, True, False, False, False, False, False, True), (20, "middle")),
    ((5, True, True, False, False, False, False, True, False), (None, None)),
    ((11, True, True, False, False, False, False, False, True), (12, "greater")),
    ((11, True, True, False, False, False, False, False, False), (None, None)),
    ((11, False, True, False, False, False, False, False, True), (None, None)),
    ((11, True, False, False, False, False, False, False, True), (None, None)),
    ((11, False, False, False, False, False, False, False, True), (17, "middle")),
    # Left as they were: 12 names neither motion nor the rays, and these two cases are not settled by that.
    ((11, True, True, True, False, False, False, False, True), (23, "lesser")),
    ((11, True, True, True, False, True, False, False, True), ("23b", "months")),
    ((11, True, True, False, True, True, False, False, True), (None, None)),
    ((11, True, True, False, False, True, False, False, True), (None, None)),
]


@pytest.mark.parametrize("facts, expected", GRADES)
def test_the_grade_on_the_facts(engine, facts, expected):
    q, share, east, retro, direct, rays, fall, night, diurnal = facts
    assert engine["_sahl_1_20_grade"](q, share, east, not east, retro, direct, rays, fall, night, diurnal) == expected


def test_the_reading_says_what_the_grade_does(engine):
    reading = engine["SAHL_1_20_READINGS"]
    assert '"enhanced" (7-9) = in a share, eastern, direct, not under the rays' in reading
    assert 'any other stake "not retrograde and not burned" = the middle' in reading
    assert "direct and unburned" not in reading
    assert "a retrograde, stationary or under-the-rays planet there is not 11's greater" in reading
    assert "12 is subsumed by 10 for a direct planet" in reading and "keeps 12's greater years" in reading
    assert engine["SAHL_1_20_SENTENCES"][12][0] == "greater"


def test_the_quoted_sentences_stand_on_the_page(engine):
    path = corpus_file("on_nativities.md")
    skip_without_corpus(path)
    text = re.sub(r"<sup>\d+</sup>|\*\*", "", path.read_text(encoding="utf-8"))
    assert "eastern, direct, in a good position" in text
    assert "so long as it is not retrograde and not burned, it indicates its middle years" in text
    assert engine["SAHL_1_20_SENTENCES"][12][1] in text


# --- a planet the Moon meets twice ----------------------------------------------------------------------------


def _year_with_a_repeat(engine):
    """1958-08-22 00:00 UT, 0 N 45 E, the year of the birth itself: Mercury retrograde, so she meets him twice."""
    jd, chart = _utc_chart(engine, 1958, 8, 22, 0.0, 0.0, 45.0)
    birth = engine["CivilDate"](1958, 8, 22)
    chronocrats = engine["calculate_chronocrats"](jd, 0.0, 45.0, 0.0, 0.0)
    return engine["pn4_timing_bundle"](chart, 0.0, 45.0, birth, birth, engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)


def test_four_planets_take_four_portions_in_the_order_of_first_connection(engine):
    bundle = _year_with_a_repeat(engine)
    portions = bundle["moon_portions"]
    assert [p["planet"] for p in portions] == ["Mercury", "Venus", "Saturn", "Jupiter"]
    assert [(p["portion"], p["of"]) for p in portions] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    quarter = bundle["year_days"] / 4
    assert [p["from_day"] for p in portions] == pytest.approx([0.0, quarter, 2 * quarter, 3 * quarter])
    assert [p["to_day"] for p in portions] == pytest.approx([quarter, 2 * quarter, 3 * quarter, 4 * quarter])
    assert portions[-1]["to_day"] == pytest.approx(bundle["year_days"])
    assert [row["Portion"] for row in bundle["portion_rows"]] == ["1 of 4", "2 of 4", "3 of 4", "4 of 4"]
    assert [row["Owned by"] for row in bundle["portion_rows"]] == ["Mercury", "Venus", "Saturn", "Jupiter"]


def test_the_connections_still_list_every_meeting(engine):
    bundle = _year_with_a_repeat(engine)
    assert [(c["planet"], c["aspect"]) for c in bundle["moon"]["connections"]] == [
        ("Mercury", "square"), ("Venus", "trine"), ("Saturn", "body"), ("Jupiter", "sextile"), ("Mercury", "trine")]
    assert [row["Planet"] for row in bundle["moon_rows"]] == ["Mercury", "Venus", "Saturn", "Jupiter", "Mercury"]


def test_the_first_connection_testimony_reads_only_the_first_planet(engine):
    """IX.9, 8: the first planet she connects with, untouched by the division."""
    bundle = _year_with_a_repeat(engine)
    assert engine["pn4_moon_testimony"](bundle["moon"]) == "Mercury"
    other = dict(bundle["moon"], connections=bundle["moon"]["connections"][1:])
    assert engine["pn4_moon_testimony"](other) == "Venus"
    assert engine["pn4_moon_testimony"](dict(bundle["moon"], connections=[])) == bundle["moon"]["house_lord"]


def test_a_year_with_no_repeat_is_divided_as_before(engine):
    portions = engine["pn4_moon_portions"]
    two = portions([{"planet": "Venus"}, {"planet": "Mars"}], 365.25)
    assert [(p["planet"], p["portion"], p["of"], p["from_day"], p["to_day"]) for p in two] == [
        ("Venus", 1, 2, 0.0, 365.25 / 2), ("Mars", 2, 2, 365.25 / 2, 365.25)]
    assert portions([], 365.25) == []


@pytest.mark.parametrize("meetings, owners", [
    (["Mars", "Mars"], ["Mars"]),
    (["Mars", "Venus", "Mars"], ["Mars", "Venus"]),
    (["Venus", "Mars", "Venus", "Mars"], ["Venus", "Mars"]),
    (["Saturn", "Mars", "Venus", "Mars"], ["Saturn", "Mars", "Venus"]),
])
def test_a_planet_met_twice_holds_its_first_place(engine, meetings, owners):
    portions = engine["pn4_moon_portions"]([{"planet": p} for p in meetings], 360.0)
    assert [p["planet"] for p in portions] == owners
    assert [p["of"] for p in portions] == [len(owners)] * len(owners)
    assert portions[-1]["to_day"] == pytest.approx(360.0)


def _run_the_year(engine):
    """The same chart on the page that shows II.22, in manual UTC+0, its year the birth's."""
    at = make_app(date="1958-08-22", page="timing")
    at.session_state["time_input_key"] = time(0, 0)
    at.session_state["manual_coords_key"] = True
    at.session_state["manual_lat_key"] = 0.0
    at.session_state["manual_lon_key"] = 45.0
    at.session_state["time_standard_key"] = engine["TIME_STANDARD_OPTIONS"][2]
    at.session_state["utc_offset_key"] = 0.0
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1958-08-22"
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    assert_no_exception(at)
    return at


def test_the_page_and_the_exports_say_four(engine):
    at = _run_the_year(engine)
    sentence = next(m.value for m in at.markdown if "before that she connects with" in m.value)
    assert "she connects with **4** planets" in sentence and "is divided into **4** portions" in sentence
    notes = [m.value for m in at.markdown if "the portions go to the planets in the order" in m.value]
    assert len(notes) == 1
    assert ("the portions go to the planets in the order she connects, which II.22 does not state, a planet she "
            "meets twice taking its one portion at its first meeting;") in notes[0]
    frames = [node.value for _heading, node in _tables(at, "The Moon's connections in her sign")]
    assert [len(frame) for frame in frames] == [5, 4]
    assert list(frames[1]["Owned by"]) == ["Mercury", "Venus", "Saturn", "Jupiter"]
    assert list(frames[1]["Portion"]) == ["1 of 4", "2 of 4", "3 of 4", "4 of 4"]
    owners = [("1 of 4", "Mercury"), ("2 of 4", "Venus"), ("3 of 4", "Saturn"), ("4 of 4", "Jupiter")]
    # The Markdown and HTML tables print these two cells side by side; other tables of the export print "n of m" too.
    assert re.findall(r"\| (\d of \d) \| (\w+) \| [\d.]+ \| [\d.]+ \|", at.session_state["_analysis_markdown"]) == owners
    assert re.findall(r"<td[^>]*>(\d of \d)</td>\s*<td[^>]*>(\w+)</td>\s*<td[^>]*>[\d.]+</td>\s*<td[^>]*>[\d.]+</td>",
                      at.session_state["_analysis_html"]) == owners
    exported = json.dumps(at.session_state["_analysis_export"]["results"], ensure_ascii=False, default=str)
    assert re.findall(r'"Owned by": "(\w+)"', exported) == [owner for _portion, owner in owners]
    assert re.findall(r'"Portion": "(\d of \d)"', exported) == [portion for portion, _owner in owners]


def _tables(at, heading):
    from conftest import table_nodes

    return [(h, node) for h, node in table_nodes(at) if h.startswith(heading)]
