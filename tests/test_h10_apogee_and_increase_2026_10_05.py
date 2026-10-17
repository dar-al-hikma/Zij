"""Gr. Intr. VII.6, 23 and VII.6, 9 after the owner's rulings 17 and 18 (2026-10-05).

VII.6, 23 (Gr. Intr. p. 480): "Or they are rising up in the circle of their
apogee." VII.1, 10 (Gr. Intr. p. 408) defines it by place: "if the corrected
planet is at the top of its apogee, or between it and [the apogee] are less
than 90° to the right or left, then it is rising in the zone of the circle of
its apogee"; 11 puts exactly 90° in the middle zone; 12 has it "falling from
the middle of the circle of its apogee" from 90° past the top "until it reaches
exactly 270°".

VII.6, 9 (Gr. Intr. p. 478): "Or they are quick in motion, increasing in light
and number." VII.1, 17 and 19 (Gr. Intr. p. 409): "if it was rising from the
middle zone of the circle of the apogee, it is decreasing in light"; "if it was
falling down from the middle zone of the circle of the apogee, it is increasing
in light and size". VII.1, 22 lets the three superiors increase in light from
the Sun to his opposition, "except that the first [way] which we stated
previously is the one agreed upon [by all]".

Ruling 17: 23 is counted for the Sun only, by his distance from the earth
(his model has no epicycle); for the five planets and the Moon it is shown as
not computed, with the reason (the texts give no apogee), and counted in
nothing. Ruling 18: 9's increase in light is the agreed way of VII.1, 19, so
it is never credited beside 23's rising, the state VII.1, 17 makes its
opposite. The engine had credited 9 by the distance shrinking, which follows
VII.1, 22's Sun-relative way (Saturn, 2019-01-20 12:00 UT, London: both 9 and
23 at once).
"""
from __future__ import annotations

import random
import re

import pytest

from conftest import assert_no_exception, make_app
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

LONDON = (51.5074, -0.1278)
FIVE = ("Saturn", "Jupiter", "Mars", "Venus", "Mercury")
NOT_THE_SUN = ("Saturn", "Jupiter", "Mars", "Venus", "Mercury", "Moon")

C6 = 2458504.0     # 2019-01-20 12:00 UT: Saturn swift, his distance shrinking, 16.5 degrees west of the Sun
C1X = 2453196.0    # 2004-07-09 12:00 UT: Saturn 0.7 degrees west of the Sun, swift, farther than his middle distance
C4A = 2459127.0    # 2020-10-04 12:00 UT: the Sun at 1.00015 AU, just beyond the middle of his range
C4B = 2459131.0    # 2020-10-08 12:00 UT: the Sun at 0.99902 AU, just inside it, and swift

APOGEE_23 = "Rising in the circle of the apogee (23)"
LIGHT_9 = "Swift and increasing in light (9"
# The two reasons as printed (ruling 17's "which no source text gives": the
# translator's own apogee tables, Gr. Intr. p. 244 Fig. 27, are not used).
REASON_23 = ("Rising in the circle of the apogee (23): Gr. Intr. VII.1, 10 places a planet there by the degrees "
             "between it and the top of its apogee, and no source text gives where that apogee lies; counted in "
             "nothing")
REASON_9 = ("Swift and increasing in light (9): swift, but whether it is increasing in light is not computed. "
            "Gr. Intr. VII.1, 19 has a planet increasing in light when it is falling from the middle zone of the "
            "circle of its apogee, the way Gr. Intr. VII.1, 22 calls the one agreed upon, and no source text gives "
            "where that apogee lies; counted in nothing")


def _condition(E, jd, lat=LONDON[0], lon=LONDON[1], sim=False):
    chart = E["calculate_traditional_chart_jd"](jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = E["evaluate_essential_dignities"](p, sect)
    accidental = E["evaluate_accidental_dignities"](p, chart["houses"], sect, chart["julian_day"],
                                                    armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    forward = E["_simulate_forward"](p, chart["julian_day"]) if sim else None
    condition = E["evaluate_abu_mashar_condition"](p, chart["houses"], sect, essential, accidental,
                                                   chart["julian_day"], chart["ascendant"], forward)
    return chart, accidental, condition


def _credited(row, head):
    return [label for label in row["Positive Labels"] if label.startswith(head)]


def _any_23(row):
    return [label for label in row["Positive Labels"] if "(23" in label]


def _not_computed(row, head):
    return [value for value in row.get("Not Computed Labels", ()) if value.reason.startswith(head)]


def _sun_middle(E):
    low, high = E["GEOCENTRIC_DISTANCE_RANGE"]["Sun"]
    return (low + high) / 2.0


# --- Ruling 18 (Q15): 9's increase in light is the agreed way ---------------

def test_q15_saturn_swift_and_his_distance_shrinking_is_not_credited_9_beside_23(engine):
    """C6, the reading's clearest chart. Saturn is swift and his distance from
    the earth is shrinking, which the engine read as 9's increase in light,
    while it also credited him 23 by his standing far off: the two states
    VII.1, 17 and 19 make the two halves of one circle. In the agreed way his
    increase in light is his place below the middle zone of the circle of his
    apogee, which no text lets this app find; so 9 is shown as not computed
    for him and credited to him in nothing."""
    E = engine
    chart, accidental, condition = _condition(E, C6)
    saturn = condition["Saturn"]
    assert accidental["Saturn"]["Swift"] is True, "premise: 9's first half holds for Saturn"
    assert chart["planetary_data"]["Saturn"]["speed_in_dist"] < 0, "premise: his distance is shrinking"
    assert not _credited(saturn, LIGHT_9), saturn["Positive Labels"]
    assert not _any_23(saturn), saturn["Positive Labels"]
    (shown,) = _not_computed(saturn, LIGHT_9)
    assert shown.status == "unavailable" and shown.display_label == "Not computed", shown
    assert shown.reason == REASON_9, shown.reason
    assert "Gr. Intr. VII.6, 9" in shown.source and "Gr. Intr. VII.1, 19" in shown.source, shown.source


def test_q15_the_sun_increases_in_light_below_the_middle_of_his_range(engine):
    """The same chart, the Sun: near his nearest, past it and drawing away
    (his distance growing), and swift. By VII.1, 19 he is increasing in light
    (below the middle zone); by the distance's change he was not."""
    E = engine
    chart, accidental, condition = _condition(E, C6)
    sun = chart["planetary_data"]["Sun"]
    assert accidental["Sun"]["Swift"] is True and sun["speed_in_dist"] > 0, "premise"
    assert sun["distance"] < _sun_middle(E), "premise: nearer than the middle of his range"
    (label,) = _credited(condition["Sun"], LIGHT_9)
    assert "distance from the earth" in label, label
    assert not _any_23(condition["Sun"]), condition["Sun"]["Positive Labels"]
    assert not condition["Sun"].get("Not Computed Labels"), condition["Sun"]


# --- Ruling 17 (Q5): 23 for the Sun only, by distance -----------------------

def test_vii6_23_counts_for_the_sun_by_his_distance(engine):
    """C4a and C4b, a degree either side of the Sun's middle distance: 23 on the
    far side, not on the near side, where (swift) he increases in light; never
    both, and nothing of either shown as not computed for him."""
    E = engine
    for jd, far in ((C4A, True), (C4B, False)):
        chart, accidental, condition = _condition(E, jd)
        sun, row = chart["planetary_data"]["Sun"], condition["Sun"]
        assert (sun["distance"] >= _sun_middle(E)) is far, (jd, sun["distance"])
        assert _any_23(row) == (["Apogee circle, approximated by distance from the earth (23)"] if far else []), row
        assert bool(_credited(row, LIGHT_9)) is (not far and accidental["Sun"]["Swift"] is True), row
        assert not row.get("Not Computed Labels"), row


def test_vii6_23_is_not_computed_for_the_five_planets_and_the_moon(engine):
    """C1x: Saturn 166 degrees from the apogee of either table the translator
    prints, which the engine still credited 23 by his distance. On this chart
    and C6, each of the six carries 23 as not computed, with the reason, and no
    23 among the labels counted."""
    E = engine
    for jd in (C1X, C6):
        _chart, _accidental, condition = _condition(E, jd)
        for planet in NOT_THE_SUN:
            row = condition[planet]
            assert not _any_23(row), (jd, planet, row["Positive Labels"])
            (shown,) = _not_computed(row, APOGEE_23)
            assert shown.status == "unavailable" and shown.display_label == "Not computed", shown
            assert shown.reason == REASON_23, shown.reason
            assert shown.source.startswith("Gr. Intr. VII.6, 23; Gr. Intr. VII.1, 10"), shown.source


def test_what_is_not_computed_counts_in_nothing(engine):
    """C1x, Saturn: 9 and 23 were two of his ten positive labels (Net 2, Good,
    "leans Good"). Neither is counted now, and the counts are the labels'
    own: Positive Score is the labels counted, Net their votes, Unresolved
    nothing, and the class and the lean fall inside the margin of one."""
    E = engine
    chart, accidental, condition = _condition(E, C1X, sim=True)
    saturn = condition["Saturn"]
    assert accidental["Saturn"]["Swift"] is True, "premise"
    assert _not_computed(saturn, APOGEE_23) and _not_computed(saturn, LIGHT_9), saturn
    assert saturn["Positive Score"] == len(saturn["Positive Labels"]) == 8, saturn["Positive Labels"]
    positive, negative = E["_abu_mashar_condition_votes"](saturn)
    assert saturn["Net"] == len(positive) - len(negative) == 0, (positive, negative)
    assert saturn["Unresolved Count"] == 0
    assert saturn["Condition"] == "Indeterminate"
    houses = E["evaluate_planets_in_houses"](chart["planetary_data"], condition, chart["ascendant"])
    (row,) = [r for r in houses if r["Planet"] == "Saturn"]
    assert (row["Net"], row["Lean"]) == (0, "Indeterminate"), row


def test_over_a_sample_23_and_9_follow_the_rulings(engine):
    """Two hundred seeded dates, 1900-2100, at London. The Sun: 23 exactly when
    he stands at or beyond the middle of his range, 9 exactly when he is swift
    and nearer than it, so never both. The five: neither 23 nor 9 credited; 23
    shown as not computed always, 9 exactly when the planet is swift. The Moon:
    23 shown as not computed; her 9 is her glow and is not touched here."""
    E = engine
    rng = random.Random(20261005)
    middle = _sun_middle(E)
    seen = {"sun 23": 0, "sun 9": 0, "five 9 shown": 0}
    for _ in range(200):
        jd = 2415020.5 + rng.random() * 200 * 365.25
        chart, accidental, condition = _condition(E, jd)
        data = chart["planetary_data"]
        sun = condition["Sun"]
        far = data["Sun"]["distance"] >= middle
        assert bool(_any_23(sun)) is far, (jd, sun["Positive Labels"])
        assert bool(_credited(sun, LIGHT_9)) is (not far and accidental["Sun"]["Swift"] is True), jd
        seen["sun 23"] += far
        seen["sun 9"] += bool(_credited(sun, LIGHT_9))
        for planet in NOT_THE_SUN:
            row = condition[planet]
            assert not _any_23(row) and len(_not_computed(row, APOGEE_23)) == 1, (jd, planet)
        for planet in FIVE:
            row = condition[planet]
            assert not _credited(row, LIGHT_9), (jd, planet, row["Positive Labels"])
            swift = accidental[planet]["Swift"] is True
            assert len(_not_computed(row, LIGHT_9)) == int(swift), (jd, planet)
            seen["five 9 shown"] += swift
    assert min(seen.values()) > 20, seen


# --- The page and the export ------------------------------------------------

@pytest.fixture(scope="module")
def configurations():
    at = make_app(date="1240-05-23", page="configurations")
    at.session_state["_reading_depth"] = "Course text"
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-10-05"
    at.run(timeout=180)
    assert_no_exception(at, "configurations")
    return at


def _texts(node, out):
    for attr in ("value", "body", "label", "help"):
        v = getattr(node, attr, None)
        if isinstance(v, str) and v:
            out.append(v)
    for child in (getattr(node, "children", None) or {}).values():
        _texts(child, out)
    return out


SUN_ONLY_NOTE_TITLE = "23, and 9's increase in light by distance: the Sun only."


def test_the_condition_notes_say_23_and_9_are_the_suns_alone(configurations):
    notes = [t for t in _texts(configurations.main, []) if "The distance reading above is used for the Sun alone" in t]
    assert len(set(notes)) == 1, notes
    (note,) = set(notes)
    for words in ("his model has no epicycle",
                  "\"if it was falling down from the middle zone of the circle of the apogee, it is increasing in "
                  "light and size\"",
                  "(17: rising from it, \"it is decreasing in light\")",
                  "the Sun, when swift, counts at 9 by standing nearer the earth than the middle of his range, and "
                  "never together with 23",
                  "For the five planets and the Moon no source text gives where their apogees lie, and the "
                  "translator's own apogee tables are not used here, so 23 is shown for them as not computed; for "
                  "the five, Gr. Intr. VII.1, 16, 18 and 21 also make the distance the epicycle's work, so it cannot "
                  "stand in.",
                  "Gr. Intr. VII.1, 22 also has the three superiors",
                  "for a swift planet of the five 9 is shown as not computed too; the Moon's increase in light is "
                  "her glow",
                  "What is not computed counts in none of the four counts, Net or the Verdict.",
                  "\"except that the first [way] which we stated previously is the one agreed upon [by all]\""):
        assert words in note, (words, note)
    assert "no text gives" not in note, note
    assert [t for t in _texts(configurations.main, []) if SUN_ONLY_NOTE_TITLE in t]


def test_the_table_and_the_export_show_23_not_computed_with_the_reason(configurations):
    rows = configurations.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    by_planet = {row["Planet"]: row for row in rows}
    assert set(by_planet) >= set(NOT_THE_SUN) | {"Sun"}
    for planet in NOT_THE_SUN:
        cell = by_planet[planet]["Good Fortune / Strength"]
        assert f"Not computed — {REASON_23}" in cell, (planet, cell)
        assert "no text gives" not in cell, (planet, cell)
        assert "Apogee circle, approximated by distance from the earth (23)" not in cell, (planet, cell)
    assert "Not computed" not in by_planet["Sun"]["Good Fortune / Strength"], by_planet["Sun"]


# --- The words the note quotes are the corpus's -----------------------------

_corpus = needs_corpus()


@_corpus
def test_the_quoted_sentences_are_the_great_introductions():
    text = corpus_file("gr_intr/abu_mashar_great_introduction.md").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", text)
    assert "9 Or they are quick in motion, increasing in light and number." in flat
    assert "23 Or they are rising up in the circle of their apogee." in flat
    assert ("19 And if it was falling down from the middle zone of the circle of the apogee, it is increasing in "
            "light and size.") in flat
    assert ("17 And if it was rising from the middle zone of the circle of the apogee, it is decreasing in light, "
            "with little size.") in flat
    assert ("(except that the first [way] which we stated previously is the one agreed upon [by all])") in flat
    assert ("then it is falling from the middle of the circle of its apogee [and] increasing in motion") in flat
