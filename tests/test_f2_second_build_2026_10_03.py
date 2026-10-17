"""Hostile pass of 2026-10-03, fix lane F2 (the counts of the year), second
build: the five breaks the blind check found (its items 13-17), each as the
test the check wrote, adapted to the way the coordinator took the break.

13  Sahl's year of the turning counts completed civil years while PN IV's
    terminal point turns with the revolution; the page says so (its count
    line and the Sahl line itself), so the two signs may differ.
14  The civil age is not II.3, 1's count: II.3, 1 completes a year at the
    Sun's return (I.2, 2-3), so it is cited where the terminal point is
    turned by the cycle and nowhere for the civil age.
15  The governor's testimonies #2-#5 and the year's indicators #3-#4 are
    read as they stand at the revolution's moment (IX.9, 1 and 10), so one
    revolution has one governor and the next return changes it.
16  Years elapsed are printed truncated to three decimals, never rounded
    onto a fardar row's own boundary.
17  The Target-by help no longer says the birthday "opens the year".

Chart throughout: the harness's default, 1240-05-23 14:30 LMT Florence.
"""
from __future__ import annotations

from datetime import time

import pytest

from conftest import assert_no_exception, find_table, make_app, table_nodes
from test_hostile_l4_2026_10_03 import BIRTH, FLORENCE, _chart


def _bundle_at(engine, target, local_hour=14.5):
    _jd, chart, chronocrats = _chart(engine, BIRTH, local_hour=local_hour)
    return engine["pn4_timing_bundle"](
        chart, FLORENCE[0], FLORENCE[1], engine["CivilDate"](*BIRTH), engine["CivilDate"](*target),
        engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)


def _timing_at(date, hour=None):
    at = make_app(page="timing")
    if hour is not None:
        at.session_state["time_input_key"] = hour
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = date
    at.run(timeout=300)
    assert_no_exception(at, f"timing at {date}")
    return at


@pytest.fixture(scope="module")
def tenth_birthday_page():
    """1250-05-23: age 10, the 9th return (17:43 UT that day), month 12."""
    return _timing_at("1250-05-23")


# --- 13: Sahl's turning says its count, and the page says why the signs differ ---

def test_sahl_turning_line_says_it_counts_completed_civil_years(tenth_birthday_page):
    at = tenth_birthday_page
    sahl = next(m.value for m in at.main.markdown if m.value.startswith("**Sahl, the year of the turning"))
    # The stated count, not a re-keying: Leo is the 10th sign from Libra, by
    # the civil age, and the line says so.
    assert "(Leo, by 10 completed civil years)" in sahl, sahl
    # The terminal point on the same page is the revolution's, nine signs on.
    year = find_table(at, "Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)").value
    assert year[year["#"] == 1]["Active point"].iloc[0].startswith("Cancer")
    # The page's count line says which count Sahl's turning uses and why
    # its sign can differ from the terminal point's.
    line = next(c.value for c in at.main.caption if c.value.startswith("Each table's count"))
    assert "the civil age (birthdays completed): the labels, and Sahl's turning, so its sign can differ from the terminal point's" in line, line
    assert len(line) <= 400


# --- 14: the civil age is not II.3, 1's count --------------------------------

def test_the_civil_age_is_not_cited_as_the_profections_count(tenth_birthday_page, engine):
    at = tenth_birthday_page
    rev = find_table(at, "The revolution of the year").value
    count = rev[rev["Item"] == "Count of the year"]["Value"].iloc[0]
    assert "(the profection's count)" not in count
    assert "(the Chronocrator Matrix's profection and the labels)" in count
    captions = [c.value for c in at.main.caption]
    assert len(captions) > 1 and [c for c in captions if "birthdays completed, II.3, 1" in c] == []
    assert "II.3, 1" not in engine["PN4_COUNTS_OF_THE_YEAR"]["age"]
    # II.3, 1 stays cited where its rule is turned: the terminal point, by the cycle.
    b = _bundle_at(engine, (1250, 5, 23))
    assert b["year_rows"][0]["Source"].startswith("II.3, 1")
    assert b["year_rows"][0]["Active point"].startswith("Cancer") and b["cycle"] == 9


# --- 15: one revolution, one governor --------------------------------------

def _ix9(date):
    at = _timing_at(date)
    return next(m.value for m in at.main.markdown if m.value.startswith("**IX.9:**"))


def test_the_governor_is_the_same_on_two_dates_of_one_revolution():
    # Both dates are in the 11th return (1251-05-24 05:19 UT), month 3.
    assert _ix9("1251-08-14") == _ix9("1251-08-17")


def test_the_governor_holds_across_the_revolution_and_changes_at_the_next_return(engine):
    inside = [_bundle_at(engine, t) for t in ((1251, 8, 14), (1251, 8, 17), (1251, 10, 13), (1252, 5, 22))]
    assert len({b["jd_sr"] for b in inside}) == 1 and all(b["cycle"] == 11 for b in inside), "premise: one return"
    rows = [[(r["#"], r["Planet"], r["Counted"]) for r in b["governor"][0]] for b in inside]
    assert len(rows) == 4 and rows == [rows[0]] * 4, rows
    primaries = [b["governor"][1]["primary"] for b in inside]
    assert primaries == [primaries[0]] * 4 and primaries[0]
    # Inside the same revolution the Ascendant's distribution has moved on
    # (its Now is the target's), yet testimony #2 is the revolution's.
    assert inside[0]["current"]["distributor"] != inside[2]["current"]["distributor"], "premise: the distribution moved"
    partners = [b["year_rows"][2]["Ruler"] for b in inside]
    fardars = [b["year_rows"][3]["Active point"] for b in inside]
    assert partners == [partners[0]] * 4 and fardars == [fardars[0]] * 4, (partners, fardars)
    assert fardars[0].startswith("at the revolution's moment, 10.999 years elapsed")
    # The 12th return falls on 1252-05-23 at 11:16 UT, before the noon the
    # pages read: a new revolution, a new governor.
    after = _bundle_at(engine, (1252, 5, 23))
    assert after["cycle"] == 12 and after["jd_sr"] != inside[0]["jd_sr"]
    assert [(r["#"], r["Planet"]) for r in after["governor"][0]] != [(r["#"], r["Planet"]) for r in inside[0]["governor"][0]]
    assert after["governor"][1]["primary"] != inside[0]["governor"][1]["primary"]


def test_indicators_2_and_3_name_one_distributor_and_its_own_partner(engine):
    # 1251-10-13, in the 11th return: the Ascendant's distribution has
    # moved on to Venus (partner Jupiter) at the target, which is what the
    # distribution table's Now shows; the indicators are read in the
    # revolution, where it stood in Jupiter's bound with the Moon as
    # partner, and #2 and #3 say so together.
    b = _bundle_at(engine, (1251, 10, 13))
    assert b["cycle"] == 11 and (b["current"]["distributor"], b["current"]["partner"]) == ("Venus", "Jupiter")
    row2, row3 = b["year_rows"][1], b["year_rows"][2]
    assert row2["Active point"].startswith("at the revolution's moment, ") and row2["Ruler"] == "Jupiter"
    assert row3["Active point"].startswith("at the revolution's moment, Moon by") and row3["Ruler"] == "Moon"
    assert (row2["Ruler"], row3["Ruler"]) == (b["current_sr"]["distributor"], b["current_sr"]["partner"])
    gov2 = next(r for r in b["governor"][0] if r["#"] == 2)
    assert gov2["Planet"] == "Jupiter"
    # The next return, 1252-05-23 at 11:16 UT: #2 moves with it.
    after = _bundle_at(engine, (1252, 5, 23))
    assert after["cycle"] == 12
    assert after["year_rows"][1]["Ruler"] == "Venus" != row2["Ruler"]
    assert after["year_rows"][1]["Active point"] != row2["Active point"]
    assert after["year_rows"][2]["Ruler"] == after["current_sr"]["partner"] == "Jupiter"


# --- 16: the printed elapsed years never round onto a fardar boundary -------

def test_elapsed_years_are_truncated_not_rounded(engine):
    text = engine["pn4_elapsed_text"]
    assert text(9.99978) == "9.999" and text(10.0) == "10.000" and text(9.9999999) == "9.999"
    assert text(0.0) == "0.000"


def test_a_birth_at_0430_prints_no_ten_beside_the_suns_fardar_row(engine):
    # 9.99978 years have elapsed at noon on the tenth birthday: inside Sun
    # 0-10, and the pages must not print "10.000" beside that row.
    b = _bundle_at(engine, (1250, 5, 23), local_hour=4.5)
    assert 9.9995 < b["elapsed_years"] < 10.0, b["elapsed_years"]
    active = [r for r in b["fardar_rows"] if r["Active"] == "yes"]
    assert len(active) == 1 and active[0]["Lord"] == "Sun" and active[0]["To age"] == "10"
    at = _timing_at("1250-05-23", hour=time(4, 30))
    header = next(m.value for m in at.main.markdown if "years elapsed from the birth hour" in m.value and "-- age" in m.value)
    assert "**9.999** years elapsed" in header, header
    rev = find_table(at, "The revolution of the year").value
    count = rev[rev["Item"] == "Count of the year"]["Value"].iloc[0]
    assert "9.999 years elapsed" in count and "10.000" not in count, count
    row4 = next(n.value for h, n in table_nodes(at) if "Active point" in n.value.columns and len(n.value) == 5).iloc[3]
    assert "10.000 years" not in row4["Active point"], row4["Active point"]


# --- 17: the Target-by help ---------------------------------------------------

def test_the_target_by_help_does_not_say_the_birthday_opens_the_year():
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 10
    at.run(timeout=300)
    assert_no_exception(at, "timing by age")
    help_text = next(r for r in at.main.radio if r.label == "Target by").help
    assert "opens the year" not in help_text
    assert "noon UT" in help_text and "completed civil years" in help_text
