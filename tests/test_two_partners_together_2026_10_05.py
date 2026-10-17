"""Two partners met at once: ruled lane H7 of the re-pass (rulings 14, 19 and 33, 2026-10-05).

PN IV III.1, 50 (PN IV p. 293): "But if one of them was in the management of
two planets or more, then the work in it is in accordance with their natures"
-- n. 39: "Reading in the plural, for the Arabic's dual ("one of the two")";
n. 40: "The Latin understands this to mean that one of the time lords is a
fortune, and the other a fortune, so that we ought to combine them."

The owner ruled that in a PN IV distribution two partners met at once count
together (ruling 14), at the opening as well as later (ruling 19, with
III.1, 23-25); and that where the text expects one partner, both are read,
each by its own nature -- in the seven static types (III.2, 10-17), the
twenty-four shifts (III.2, 55-101) and the governor's partner testimony
(IX.9: each partner credited) -- a pair of one nature collapsing to one type
and one shift, the page labelling it as this app's reading of III.1, 50
(ruling 33, after the blind reading Q16). Lane F3b (HP-05) had left such a
tie open: the partner a typed unknown that every consumer unfolded
alternative by alternative.

The probes are the Q16 reading's: P1-P4 and S2-S3 on the identity measure
from 0 Aries over 30 degrees, synthetic case A for the governor, and the
constructed chart C2 (the reading's section 3.3).
"""
from __future__ import annotations

import pytest

from conftest import APP_PATH, ENGINE_PATH

PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")

# Two contacts the direction reaches at one position, 10 degrees on from the
# start: two bodies, and a body with a ray (Saturn's sextile, 70 - 60).
PAIRS = {
    "two bodies": ({"Mars": {"longitude": 10.0}, "Venus": {"longitude": 10.0}}, {"Mars", "Venus"}),
    "a body and a ray": ({"Mars": {"longitude": 10.0}, "Saturn": {"longitude": 70.0}}, {"Mars", "Saturn"}),
}


def _segments(engine, **longitudes):
    planets = {name: {"longitude": lon} for name, lon in longitudes.items()}
    return engine["_pn4_distribute"](planets, 0.0, lambda lon: lon, 30.0, "test point")


def _named(text):
    return {name for name in PLANETS if name in text}


@pytest.mark.parametrize("case", sorted(PAIRS))
def test_two_partners_met_at_once_are_read_together(engine, case):
    planets, pair = PAIRS[case]
    segments = engine["_pn4_distribute"](planets, 0.0, lambda lon: lon, 30.0, "test point")
    alone = engine["pn4_distribution_at_age"](segments, 9.5)
    assert alone["partner"] is None, "the probe's premise: the distributor acts alone before the pair is met"

    met = engine["pn4_distribution_at_age"](segments, 10.5)
    assert not engine["is_unresolved"](met["partner"]), met["partner"]
    assert not engine["is_unresolved"](met["partner_from"]), met["partner_from"]
    assert _named(engine["pn4_result_text"](met["partner"])) == pair, met["partner"]
    assert _named(engine["pn4_result_text"](met["partner_from"])) == pair, met["partner_from"]


# --- Q16-a: the seven static types (PN IV III.2, 10-17) --------------------------------

def test_a_same_nature_pair_has_its_one_static_type(engine):
    """P2: Mars's body and Saturn's sextile at 10 Aries, in Venus's bound --
    both infortunes partnering a fortune: type 4 whichever partner is read."""
    met = engine["pn4_distribution_at_age"](_segments(engine, Mars=10.0, Saturn=70.0), 10.5)
    assert met["distributor"] == "Venus", "the probe's premise: the bound of Venus"
    number, _label, _cite = engine["pn4_static_type"](met["distributor"], met["partner"])
    assert not engine["is_unresolved"](number), number
    assert number == 4


def test_a_mixed_pair_is_typed_by_each_partner_s_own_nature(engine):
    """P4: Venus's body and Saturn's square at 10 Aries, Venus distributing:
    with Venus both fortunes (type 7, III.2, 17), with Saturn a fortune
    distributing and an infortune partnering (type 4, III.2, 14) -- both in
    force, labelled as this app's reading of III.1, 50."""
    met = engine["pn4_distribution_at_age"](_segments(engine, Venus=10.0, Saturn=100.0), 10.5)
    assert met["distributor"] == "Venus", "the probe's premise: the bound of Venus"
    number, label, cite = engine["pn4_static_type"](met["distributor"], met["partner"])
    assert not any(engine["is_unresolved"](v) for v in (number, label, cite)), (number, label, cite)
    assert sorted(number) == [4, 7], number
    assert _named(label) == {"Venus", "Saturn"}, label
    assert "III.2, 17" in cite and "III.2, 14" in cite, cite
    assert "III.1, 50" in cite and "this app's reading" in cite, cite


# --- Q16-b: the twenty-four shifts (PN IV III.2, 55-101) -------------------------------

def test_a_shift_out_of_a_mixed_pair_is_read_from_each_partner(engine):
    """S2: Mars and Venus by body at 3 Aries hand the management to
    Jupiter's trine at 8, in Venus's bound: from Mars, an infortune to a
    fortune (#7, #21, III.2, 95); from Venus, a fortune to a fortune (#5,
    #17, III.2, 92) -- both, neither conditional on the other."""
    rows = engine["pn4_year_transitions"](_segments(engine, Mars=3.0, Venus=3.0, Jupiter=128.0), 7.5, 8.5)
    assert len(rows) == 2, rows
    assert not any(engine["is_unresolved"](v) for row in rows for v in row.values()), rows
    assert all("Status" not in row for row in rows), rows
    shifts = {row["Transition"]: row for row in rows}
    assert sorted(shifts) == ["#5, #17", "#7, #21"], rows
    assert "III.2, 95" in shifts["#7, #21"]["Indication"] and shifts["#7, #21"]["Shift"].endswith("read for Mars")
    assert "III.2, 92" in shifts["#5, #17"]["Indication"] and shifts["#5, #17"]["Shift"].endswith("read for Venus")
    assert all("Mars and Venus" in row["Shift"] for row in rows), rows


def test_a_shift_out_of_a_same_nature_pair_is_one_shift(engine):
    """S3: Mars's body and Saturn's sextile at 3 Aries hand the management
    to Jupiter's trine at 8: an infortune to a fortune whichever partner is
    read, so one shift, #7, #21 (III.2, 95), naming both."""
    rows = engine["pn4_year_transitions"](_segments(engine, Mars=3.0, Saturn=63.0, Jupiter=128.0), 7.5, 8.5)
    assert len(rows) == 1, rows
    (row,) = rows
    assert [key for key, v in row.items() if engine["is_unresolved"](v)] == [], row
    assert "Status" not in row, row
    assert row["Transition"] == "#7, #21" and "III.2, 95" in row["Indication"], row
    assert "Mars and Saturn" in row["Shift"], row


# --- Q16-c: the governor's partner testimony (PN IV IX.9, 5 and 10) --------------------

def test_each_partner_of_a_pair_is_credited_in_the_fourth_testimony(engine):
    """Synthetic case A: the Ascendant's distribution has Mars and Venus
    together, the releaser's Mars. #4, "the partner to them both", credits
    Mars, a partner of both distributions; Venus is not the releaser's."""
    pair = engine["pn4_distribution_at_age"](_segments(engine, Mars=10.0, Venus=10.0), 10.5)["partner"]
    rows, summary = engine["pn4_governor"]("Venus", "Venus", pair, "n/a", "Mars", "Jupiter", 185.0, None, None,
                                           "Jupiter", "Mars", None, "available")
    four = next(row for row in rows if row["#"] == 4)
    assert not engine["is_unresolved"](four["Planet"]) and four["Counted"] == "yes", four
    assert four["Planet"].split(";")[0] == "Mars", four
    # #1, #2 and #8 are Venus; #3 and #6 Jupiter; #5 and #4 Mars.
    assert summary["tally"] == {"Venus": 3, "Jupiter": 2, "Mars": 2}, summary["tally"]


def _c2_bundle(engine):
    """The reading's C2 (section 3.3): Florence, 1990-03-10 12:00 LMT, Mars
    moved to 14 Cancer 14' and Saturn to 14 Virgo 14' -- Mars's body and
    Saturn's sextile meet the Ascendant's direction at one degree, and the
    Sun's direction opens on Mars's trine and Saturn's opposition at 14
    Pisces 14'. Read at 2000-05-22."""
    lat, lon = 43.7698, 11.2556
    jd = engine["civil_local_to_jd_ut"](1990, 3, 10, 12.0, lon / 15)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chart["planetary_data"]["Mars"]["longitude"] = 104.2491639574803
    chart["planetary_data"]["Saturn"]["longitude"] = 164.2491639574803
    chronocrats = engine["calculate_chronocrats"](jd, lat, lon, 12, lon / 15)
    return engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](1990, 3, 10), engine["CivilDate"](2000, 5, 22),
                                       engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)


def test_both_partners_of_both_distributions_are_credited_on_the_constructed_chart(engine):
    bundle = _c2_bundle(engine)
    assert {"Mars", "Saturn"} == _named(engine["pn4_result_text"](bundle["current"]["partner"])), \
        "the probe's premise: the Ascendant's pair"
    rows, summary = bundle["governor"]
    four = next(row for row in rows if row["#"] == 4)
    assert not engine["is_unresolved"](four["Planet"]) and four["Counted"] == "yes", four
    assert _named(four["Planet"].split(";")[0]) == {"Mars", "Saturn"}, four
    # #4 credits each: Mars (#8) and Saturn (#7) one more apiece; Jupiter
    # (#2, #3, #6) stays primary.
    assert summary["tally"] == {"Venus": 2, "Jupiter": 3, "Mars": 2, "Saturn": 2}, summary["tally"]
    assert summary["primary"] == ["Jupiter"], summary["primary"]
    # The tally sums to 9 over 8 testimonies: the page's sentence says why
    # (the blind check's N2).
    assert "#4, counts for each of Mars and Saturn" in summary["text"], summary["text"]


# --- the reading's incidental slips -----------------------------------------------------

def _strings(value, engine):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item, engine)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item, engine)
    elif engine["is_unresolved"](value):
        yield value.reason
        for name, item in value.alternatives:
            yield name
            yield from _strings(item, engine)


def test_no_doubled_article_where_a_direction_is_labelled_with_its_releaser(engine):
    texts = list(_strings(_c2_bundle(engine), engine))
    assert len(texts) > 1000, "the probe's premise: the bundle's text"
    doubled = sorted({text for text in texts if "the the " in text})
    assert doubled == [], doubled[:5]


def test_nothing_says_a_direction_always_has_exactly_one_partner():
    from conftest import source_files
    files = source_files()                            # every source module
    assert len(files) >= 2, files
    for path in files:
        assert "always exactly one" not in path.read_text(encoding="utf-8"), path.name


# --- the blind check's B1: one order, and the shift reads who the partners are -----------

def test_the_same_pair_met_again_is_no_shift_whichever_way_it_is_drawn(engine):
    """Venus's body and Mars's sextile at 10 Aries open the direction from
    15 (and, mirrored, Mars's body and Venus's sextile); at 55 it meets the
    same two again at 10 Gemini, with nothing between. The same planets on
    both sides are no shift of management, in either drawing, and the pair
    is the same value at the opening and later."""
    drawings = {}
    for venus, mars in ((10.0, 70.0), (70.0, 10.0)):
        segs = engine["_pn4_distribute"]({"Venus": {"longitude": venus}, "Mars": {"longitude": mars}}, 15.0,
                                         lambda lon: lon, 100, "test point")
        rows = engine["pn4_year_transitions"](segs, 0, 100)
        assert rows, "the probe's premise: the bound shifts are listed"
        drawings[venus] = (segs, [row for row in rows if row["At age"].startswith("55")])
    assert drawings[10.0][1] == [] and drawings[70.0][1] == [], (drawings[10.0][1], drawings[70.0][1])
    (one, _r1), (mirror, _r2) = drawings[10.0], drawings[70.0]
    assert tuple(one[0]["partner"]) == tuple(mirror[0]["partner"]) == ("Mars", "Venus"), (one[0]["partner"], mirror[0]["partner"])
    assert engine["pn4_distribution_at_age"](one, 55.5)["partner"] == one[0]["partner"]
    assert engine["pn4_distribution_at_age"](mirror, 55.5)["partner"] == mirror[0]["partner"]


def test_three_met_at_one_degree_print_one_order_by_day_and_by_night(engine):
    """Venus moved onto the Sun and Saturn opposite, Florence 1240-05-23 at
    13:00 and 01:00 local mean time: the three meet the Ascendant's
    direction at one degree (by sextile, sextile and trine at night), their
    degrees summed differently; they print in one order everywhere."""
    lat, lon = 43.7792, 11.2463
    seen = set()
    for hour in (13.0, 1.0):
        chart = engine["calculate_traditional_chart_jd"](engine["civil_to_jd"](1240, 5, 23, hour - lon / 15), lat, lon)
        planets = chart["planetary_data"]
        planets["Venus"]["longitude"] = planets["Sun"]["longitude"]
        planets["Saturn"]["longitude"] = (planets["Sun"]["longitude"] + 180.0) % 360.0
        segs = engine["pn4_distribution_from_ascendant"](planets, chart["ascendant"], chart["obliquity"], lat)
        three = {str(s["partner"]) for s in segs if isinstance(s["partner"], engine["PN4Together"]) and len(s["partner"]) == 3}
        assert three, f"premise: the three meet at one degree at {hour:g}h"   # each hour, not the union (lane TL, TL-23)
        seen |= three
    assert seen == {"Saturn, Sun and Venus"}, seen


# --- the blind check's N1: a partner on both sides of a shift does not shift --------------

def test_a_partner_on_both_sides_of_a_shift_does_not_shift(engine):
    together = engine["PN4Together"]

    def shifts(before, after):
        rows = engine["pn4_classify_shift"]({"distributor": "Jupiter", "partner": before},
                                            {"distributor": "Jupiter", "partner": after})
        return [(row["kind"], row["numbers"]) for row in rows]
    # Mars stays and Venus comes: from Mars, an infortune, to Venus, a fortune.
    assert shifts("Mars", together(("Mars", "Venus"))) == [("management", [7, 21])]
    # Venus leaves and Mars stays: from Venus to Mars.
    assert shifts(together(("Mars", "Venus")), "Mars") == [("management", [6, 19])]
    # Venus stays; Mars leaves and Jupiter comes: from Mars to Jupiter.
    assert shifts(together(("Mars", "Venus")), together(("Jupiter", "Venus"))) == [("management", [7, 21])]
    # The same partners, in either order: no shift.
    assert shifts(together(("Mars", "Venus")), together(("Venus", "Mars"))) == []


def test_the_page_says_how_a_partner_on_both_sides_of_a_shift_is_read():
    source = APP_PATH.read_text(encoding="utf-8")
    start = source.index('("Classifications, and the three planets of neither nature."')
    note = source[start:source.index('"),', start)]
    assert "A partner on both sides of a shift does not" in note, note
    assert note.rstrip().endswith("This is this app's reading of III.1, 50."), note[-200:]
