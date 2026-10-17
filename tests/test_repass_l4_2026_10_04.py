"""Re-pass of lane L4 (2026-10-04) on the fixed engine: the new defects found
beside the fixes of the hostile pass of 2026-10-03 (F2, F2b, F3, F3b, F6, F6b).

Each test asserts the RIGHT behaviour and is a strict xfail today, so it
XFAILS until the defect is fixed and then fails the run as an XPASS, which is
the signal to remove the decorator. Run unmasked (--runxfail) each fails at
the assertion that states the finding.

Charts: the harness's default (1240-05-23 14:30 LMT Florence, diurnal), built
as tests/test_hostile_l4_2026_10_03.py builds it, and four charts cast at a
manual UTC offset of 0, each named in its test with the date, the UT hour,
the latitude and the longitude.
"""
from __future__ import annotations

from datetime import time

import pytest

from conftest import make_app, assert_no_exception

FLORENCE = (43.7792, 11.2463)
BIRTH = (1240, 5, 23)


def _lmt_bundle(engine, target, birth=BIRTH, local_hour=14.5, lat=FLORENCE[0], lon=FLORENCE[1]):
    """The bundle as app.py computes it, LMT (the sidebar's default standard)."""
    offset = lon / 15.0
    jd = engine["civil_local_to_jd_ut"](*birth, local_hour, offset)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, int(local_hour), offset)
    bundle = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](*birth), engine["CivilDate"](*target),
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    return chart, bundle


def _ut_chart(engine, birth, ut_hour, lat, lon):
    """A chart cast at a manual UTC offset of 0 (the sidebar's 'Manual UTC offset', 0.0)."""
    jd = engine["civil_local_to_jd_ut"](*birth, ut_hour, 0.0)
    return jd, engine["calculate_traditional_chart_jd"](jd, lat, lon)


def _ut_bundle(engine, birth, ut_hour, lat, lon, target):
    jd, chart = _ut_chart(engine, birth, ut_hour, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, int(ut_hour), 0.0)
    bundle = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](*birth), engine["CivilDate"](*target),
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    return chart, bundle


def _ut_releaser(engine, birth, ut_hour, lat, lon):
    jd, chart = _ut_chart(engine, birth, ut_hour, lat, lon)
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, lat, lon)
    rel = engine["sahl_releaser"](chart["planetary_data"], chart["ascendant"], chart["houses"], chart["sect"],
                                  chart["lot_of_fortune"], syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    return chart, rel


def _ut_app(page, date, ut, lat, lon):
    at = make_app(date=date, page=page)
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = lat, lon
    at.session_state["time_input_key"] = ut
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    return at


# ---------------------------------------------------------------------------
# L4-RP-01: the image of the revolution keys its time lords on the target,
# indicators #2-#4 on the revolution's moment, on one page.
# ---------------------------------------------------------------------------

def test_l4_rp_01_the_image_names_the_time_lords_the_indicators_of_the_year_name(engine):
    # Default chart, 1251-10-13: the 11th revolution (1251-05-24 05:19 UT), 11.389 years elapsed.
    # Indicators #2-#4 (at the revolution's moment): Jupiter / Moon / Venus-Venus.
    # The image's rows (at the target): Venus the distributor, Jupiter the partner, Venus-Mercury the fardar.
    _chart, b = _lmt_bundle(engine, (1251, 10, 13))
    assert b["cycle"] == 11 and b["month"] == 5, "the premise: the 11th revolution, month 5"
    rows, _counts = b["image"]
    points = [r["Point"] for r in rows]
    distributor = b["current_sr"]["distributor"]
    partner = b["current_sr"]["partner"]
    fardar = b["fardar_sr"]
    assert b["year_rows"][1]["Ruler"] == distributor and b["year_rows"][3]["Ruler"] == (
        f"{fardar['lord']} / {fardar['sub_lord']}"), "the premise: #2 and #4 are the revolution's"
    assert f"{distributor}, the distributor" in points, points
    assert f"{partner}, the partner in the management" in points, points
    assert f"{fardar['lord']}, lord of the fardar" in points, points
    assert f"{fardar['sub_lord']}, dividing the fardar with it" in points, points


# ---------------------------------------------------------------------------
# L4-RP-02: IX.9, 12-13 read the revolution's triplicity by the ROOT's sect,
# while II.3 on the same page reads the revolution's dignities by its own.
# ---------------------------------------------------------------------------

def test_l4_rp_02_the_governors_revolution_testimony_agrees_with_ii3(engine):
    # 1988-03-23 12:24 UT, 27.84 S 162.73 E (nocturnal root), target 2012-03-16: the revolution is
    # diurnal; Jupiter, lord of the year and sole primary, stands at 13 Aries 11' in it.
    chart, b = _ut_bundle(engine, (1988, 3, 23), 12.4, -27.84, 162.73, (2012, 3, 16))
    assert (chart["sect"], b["sr"]["sect"]) == ("Nocturnal", "Diurnal"), "the premise: the sects differ"
    assert b["governor"][1]["primary"] == ["Jupiter"] and b["year"]["lord"] == "Jupiter", "the premise"
    claim = next(r for r in b["ii3"]["lord_rows"] if r["Factor"].startswith("In a sign in which it has a claim"))
    assert claim["Revolution"] == "peregrine", "the premise: II.3 reads Jupiter peregrine in the revolution"
    row12 = next(r for r in b["governor_condition"] if r["Test"].startswith("IX.9, 12"))
    revolution_clause = row12["Criteria"].split("revolution:")[1]
    assert "testimony in it met" not in revolution_clause, revolution_clause[:160]


# ---------------------------------------------------------------------------
# L4-RP-03: 1.20, 6's "eastern" for the five planets is their side of the Sun,
# undeclared where it elects, beside a note that defines easternness by 1.22's
# degrees; a burned Mercury keeps a night releaser. Ruled (2026-10-05, ruling
# 16, Q4): 1.20, 6's "eastern" for the five planets is 1.22's as Sahl writes it
# (Saturn and Jupiter 6 degrees, Mars 18, Venus and Mercury direct and 12),
# superseding the side-of-the-Sun reading for the election; this test asserts
# the ruled election.
# ---------------------------------------------------------------------------

def test_l4_rp_03_a_1_20_6_election_says_how_eastern_was_read(engine):
    # 1987-07-06 06:15 UT, 47.98 N 67.72 W, nocturnal. The fullness (20 Gem 23, house 1) has no lord looking;
    # Mercury, its house lord, holds a share in the Ascendant; the Lot of Fortune is falling; the Ascendant's
    # lord Mercury is in whole-sign place 2, so 1.15, 16's test fails.
    chart, rel = _ut_releaser(engine, (1987, 7, 6), 6.25, 47.98, -67.72)
    assert chart["sect"] == "Nocturnal"
    mercury = chart["planetary_data"]["Mercury"]
    q = engine["sahl_eastern_1_22"]("Mercury", mercury["longitude"], chart["planetary_data"]["Sun"]["longitude"],
                                    mercury["speed_in_lon"])
    assert q.level1.status == "below adopted threshold", "the premise: 1.22, 7's 12 degrees are not met"
    assert engine["motion_state"]("Mercury", mercury["speed_in_lon"]) == "retrograde", "the premise: nor is he direct"
    # The election: Mercury is not eastern by 1.22, 7, so 1.20, 6 does not make him house-master, and the chain
    # ends as 1.15, 16 says ("the native does not have a foundation for his lifespan").
    assert rel["house_master"] is None and rel["releaser"] is None, (rel["releaser"], rel["house_master"])
    assert "1.15, 16" in rel["verdict"] and "does not have a foundation for his lifespan" in rel["verdict"], rel["verdict"]
    # The fullness's row says how "eastern" was read: by 1.22, 7, Mercury named with the sentence.
    fullness = next(r for r in rel["candidates"] if r["Candidate"].startswith("the fullness"))
    assert "Mercury, its house lord, holds a share in the Ascendant but is not eastern (1.22, 7" in fullness["Verdict"], (
        fullness["Verdict"])


# ---------------------------------------------------------------------------
# L4-RP-04: on a forked election, the arm with no releaser promises the 1.32
# stand-in "below", and the page draws none.
# ---------------------------------------------------------------------------

def test_l4_rp_04_the_arm_with_no_releaser_shows_the_stand_in_it_promises():
    # 1923-02-08 09:06 UT, 43.7792 N 151.2 E (the F6b check's chart): if the Moon is eastern, the Lot of
    # Fortune; if not, no releaser by Nawbakht's rule.
    at = _ut_app("releaser", "1923-02-08", time(9, 6), 43.7792, 151.2)
    at.run(timeout=300)
    assert_no_exception(at, "1923-02-08 09:06 UT")
    page = [m.value for m in at.main.markdown]
    verdict = next(m for m in page if m.startswith("**Unresolved") and "if the Moon is not eastern: No releaser" in m)
    assert "the Moon is directed after it, below" in verdict, "the premise: the arm promises the stand-in"
    assert any(m.startswith("**The stand-in") for m in page), [m[:60] for m in page if "stand" in m]


# ---------------------------------------------------------------------------
# L4-RP-05: L4-02's shape (a number rounded onto the next row or year) in two
# more tables.
# ---------------------------------------------------------------------------

def test_l4_rp_05a_the_now_row_opens_at_or_before_the_printed_elapsed_years(engine):
    _chart, b = _lmt_bundle(engine, (1251, 10, 13))
    printed = float(engine["pn4_elapsed_text"](b["elapsed_years"]))
    now = [r for r in b["distribution_rows"] if r["Now"] == "yes"]
    assert len(now) == 1, "the premise: one Now row"
    assert float(now[0]["From age"]) <= printed < float(now[0]["To age"]), (now[0]["From age"], printed)


def test_l4_rp_05b_a_directed_arc_is_not_printed_into_the_next_year(engine):
    # 1960-01-11 03:36 UT, 29.22 S 97.74 W: the house-master Mars reaches the Sun's degree (burning) at
    # an arc of 24.99x years; 1.23, 4 is asked of the revolution of year 24 -- right -- but the row
    # prints 25.00.
    chart, rel = _ut_releaser(engine, (1960, 1, 11), 3.6, -29.22, -97.74)
    assert rel["house_master"] == "Mars", "the premise"
    rows = engine["sahl_house_master_direction"](chart["planetary_data"], "Mars", chart["obliquity"], -29.22,
                                                 origin_jd=chart["julian_day"])
    burning = next(r for r in rows if r["Target"] == engine["SAHL_BURNING_TARGET"])
    assert burning["In the year of age"] == 24, "the premise"
    assert float(burning["Arc (years)"]) < burning["In the year of age"] + 1, burning


# ---------------------------------------------------------------------------
# L4-RP-06: the header says "read at noon UT" where the birth-date clamp
# has moved the reading to the birth's own moment.
# ---------------------------------------------------------------------------

def test_l4_rp_06_the_header_says_where_the_birth_date_is_read():
    at = make_app(page="timing")                      # 1240-05-23 14:30 LMT = 13:45 UT, after noon UT
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1240-05-23"
    at.run(timeout=300)
    assert_no_exception(at, "birth date as the target")
    head = next(m.value for m in at.main.markdown if "The revolution of the year fell on" in m.value)
    assert "**0.000** years elapsed" in head, "the premise: the clamp"
    assert "read at noon UT" not in head or "birth's own moment" in head, head


# ---------------------------------------------------------------------------
# L4-RP-07: in a node's fardar the governor counts the fifth testimony as
# "unavailable", with no word why.
# ---------------------------------------------------------------------------

def test_l4_rp_07_a_nodes_fardar_is_not_called_an_unavailable_testimony(engine):
    # Default chart, 1311-08-01: the 71st revolution; #4 reads "Head (no sub-period)".
    _chart, b = _lmt_bundle(engine, (1311, 8, 1))
    assert b["fardar_sr"]["lord"] == "Head" and b["year_rows"][3]["Ruler"] == "Head (no sub-period)", "the premise"
    rows, summary = b["governor"]
    fifth = next(r for r in rows if r["#"] == 5)
    assert fifth["Planet"] == "Head", "the premise"
    # The row says why a node's testimony is not tallied, rather than a bare 'no' counted as unavailable
    assert fifth["Counted"] != "no", fifth


# ---------------------------------------------------------------------------
# L4-RP-08: with the releaser open on the Moon's easternness, the governor
# drops testimony #3 as "unavailable" and names a primary no arm gives.
# ---------------------------------------------------------------------------

def _governor_on_each_arm(engine, chart, b, lat):
    """IX.9's tally recomputed on each arm of the open releaser, by the engine's own path for a settled one:
    the arm's releaser directed (pn4_releaser_direction), read at the revolution's moment, everything else
    as the bundle has it."""
    out = []
    for label, whole in b["releaser"]["orientation_alternatives"]:
        arm = dict(b["releaser"], releaser=whole["releaser"], longitude=whole["longitude"])
        if whole["releaser"] is None:
            pdir, at_sr = engine["pn4_releaser_direction"](dict(chart, geo_lat=lat), arm, b["elapsed_years"]), None
        else:
            pdir = engine["pn4_releaser_direction"](dict(chart, geo_lat=lat), arm, b["elapsed_years"])
            at_sr = engine["pn4_distribution_at_age"](pdir["segments"], b["revolution_window"][0]) if pdir["segments"] else None
        _rows, summary = engine["pn4_governor"](
            b["year"]["lord"], (b["current_sr"] or {}).get("distributor"), (b["current_sr"] or {}).get("partner"), "-",
            (b["fardar_sr"] or {}).get("lord"), b["orb"], b["sr"]["ascendant"], engine["pn4_moon_testimony"](b["moon"]),
            b["moon"]["void"], (at_sr or {}).get("distributor"), (at_sr or {}).get("partner"), pdir["note"], pdir["status"])
        out.append((label, summary["primary"]))
    return out


def test_l4_rp_08_an_open_releaser_does_not_leave_the_governor_a_primary_no_arm_gives(engine):
    lat, lon = FLORENCE
    chart, b = _ut_bundle(engine, (1900, 4, 27), 8.0, lat, lon, (1960, 6, 1))
    assert engine["is_unresolved"](b["releaser"]["releaser"]), "the premise: the election is open (HP-04)"
    arms = _governor_on_each_arm(engine, chart, b, lat)
    assert [p for _l, p in arms] == [["Jupiter", "Venus"], ["Jupiter", "Venus"]], arms
    primary = b["governor"][1]["primary"]
    assert engine["is_unresolved"](primary) or primary in [p for _l, p in arms], (primary, arms)
