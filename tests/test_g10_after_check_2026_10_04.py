"""Lane G10 of the re-pass of 2026-10-04, after its blind check: two of the
lane's own prints, made true in every case they reach.

* The birth-date clamp (L4-RP-06 = L1-N6) applies wherever noon UT on the
  target date falls before the birth. Under a UTC offset below -12 h (the box
  accepts -14 to +14) a late-evening birth is already the next day in UT, so
  the clamp applies to the day after the printed birth date too. The export's
  `target.hour` must not call that target "the birth date".
* The Turning tab's direction by proportional semi-arcs prints its period's
  span in the years the header prints (pn4_elapsed_text: three decimals,
  truncated), as the angle planets' tables print the same period
  (L4-RP-05a's shape): a span rounded to two places opened after the
  header's figure.
"""
from __future__ import annotations

import json
from datetime import time

from conftest import assert_no_exception, make_app


def test_the_export_hour_is_true_when_the_clamp_reaches_the_day_after_the_birth_date():
    # Born 1950-06-01 23:30 at a manual UTC offset of -13 h (= 1950-06-02 12:30 UT), 40 N 170 W;
    # the target 1950-06-02 is the day after the birth date the page prints, and its noon UT falls
    # half an hour before the birth, so every clock is read at the birth's own moment.
    at = make_app(date="1950-06-01", page="timing")
    at.session_state["manual_lat_key"] = 40.0
    at.session_state["manual_lon_key"] = -170.0
    at.session_state["time_input_key"] = time(23, 30)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = -13.0
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1950-06-02"
    at.run(timeout=300)
    assert_no_exception(at, "timing, -13 h, the day after the birth date")
    head = next(m.value for m in at.main.markdown if "The revolution of the year fell on" in m.value)
    assert "(born 1950-06-01)" in head and "**1950-06-02**" in head, head
    assert "**0.000** years elapsed" in head, f"the premise: the clamp applies -- {head}"
    assert "read at the birth's own moment" in head, head
    exp = at.session_state["_analysis_export"]
    export = exp if isinstance(exp, dict) else json.loads(exp)
    hour = export["target"]["hour"]
    assert hour.startswith("the birth's own moment"), hour
    assert "birth date" not in hour, hour
    assert "noon UT on the target date falls before the birth" in hour, hour


def test_the_turning_span_is_printed_as_the_header_prints_the_years_elapsed(engine):
    # 1942-07-22 03:16:34 UT, 26.35 N 106.74 E, target 1946-03-15: the header prints 3.647 years
    # elapsed; Mercury's angle-planet table marks the period 3.645 to 11.147 Now, and the Turning
    # tab's row for Mercury directs the same degree by the same semi-arcs.
    hour = 3 + 16 / 60 + 34 / 3600
    lat, lon = 26.35, 106.74
    jd = engine["civil_local_to_jd_ut"](1942, 7, 22, hour, 0.0)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, int(hour), 0.0)
    b = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](1942, 7, 22), engine["CivilDate"](1946, 3, 15),
                                    engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    printed = engine["pn4_elapsed_text"](b["elapsed_years"])
    assert printed == "3.647", printed
    mercury = next(ap for ap in b["angle_planets"] if ap.get("planet") == "Mercury")
    now = [(r["From age"], r["To age"]) for r in mercury["rows"] if r["Now"] == "yes"]
    assert now == [("3.645", "11.147")], now
    turning = next(r for r in b["turning_rows"] if r["Point"] == "Mercury")["Directed a year per degree"]
    assert "(age 3.645 to 11.147)" in turning, turning
    assert float(now[0][0]) <= float(printed) < float(now[0][1])
