"""The time standards, repaired after the hostile pass of 2026-10-03 (lane F1).

A named zone is read through zoneinfo, which keeps the whole of a zone's
history; a birth before the zone's first rule is refused with a sentence, and
a point at sea or a zone the database does not hold has no zone.
"""
from __future__ import annotations

from datetime import time

import pytest
from timezonefinder import TimezoneFinder

from conftest import assert_no_exception, make_app

LMT, STD = "LMT (Local Mean Time)", "Standard time (pytz)"


def _app(date, hhmm, lat, lon, standard=STD):
    at = make_app(date=date, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = standard
    at.run()
    assert_no_exception(at, f"{date} {hhmm} {lat},{lon}")
    return at


def _sidebar(at):
    return "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])


def test_c_06_a_point_at_sea_has_no_standard_time_zone():
    at = _app("2000-01-01", (12, 0), 0.0, -30.0)
    text = _sidebar(at)
    assert at.sidebar.error and "no standard-time zone at these coordinates" in text, text
    assert "Etc/GMT" not in text, text


def test_c_07_an_unknown_zone_name_is_refused_not_raised(monkeypatch):
    monkeypatch.setattr(TimezoneFinder, "timezone_at", lambda self, **kw: "Nowhere/Atlantis")
    at = _app("2000-01-01", (12, 0), 43.7792, 11.2463)
    assert "no standard-time zone at these coordinates" in _sidebar(at), _sidebar(at)


def test_a_zone_before_its_first_rule_is_refused_after_it_and_before_it(engine):
    state = engine["named_zone_state"]
    refusal = engine["NamedZoneRefusal"]
    # New York kept standard time from 1883-11-18 (the database's first rule).
    assert state("America/New_York", 1890, 6, 1, 12, 0, 0) == {"offset_seconds": -18000, "abbreviation": "EST"}
    with pytest.raises(refusal) as caught:
        state("America/New_York", 1880, 6, 1, 12, 0, 0)
    assert caught.value.kind == "before_rules"
    # Tokyo 1888, a zone whose rule the 32-bit reader never saw.
    assert state("Asia/Tokyo", 1890, 1, 1, 12, 0, 0)["abbreviation"] == "JST"


def _refusal_kind(engine, name):
    try:
        engine["named_zone_state"](name, 2000, 1, 2, 12, 0, 0)
    except engine["NamedZoneRefusal"] as refusal:
        return refusal.kind
    return None


def test_only_one_zone_of_the_database_is_before_its_rules_in_2000(engine):
    """The first rule is read as 'the state the record begins with'; no zone
    may return to that state, or a modern birth would be refused. Troll
    Station's database record begins in 2005, so 2000 is truly before it."""
    names = sorted(n for n in TimezoneFinder().timezone_names if not n.startswith("Etc/"))
    refused = {n: _refusal_kind(engine, n) for n in names if _refusal_kind(engine, n)}
    assert refused == {"Antarctica/Troll": "before_rules"}, refused


def test_the_boxes_say_the_seconds_a_zones_own_history_holds(engine):
    # Liberia kept Monrovia Mean Time, -00:44:30, until 1972; pytz rounded it
    # to the minute.
    state = engine["named_zone_state"]("Africa/Monrovia", 1971, 6, 1, 12, 0, 0)
    assert state["offset_seconds"] == -(44 * 60 + 30), state


def test_the_box_and_the_strip_print_those_seconds():
    at = _app("1971-06-01", (12, 0), 6.3, -10.8)
    assert "UTC offset -00:44:30 (MMT)" in _sidebar(at), _sidebar(at)


def test_the_refusal_of_a_birth_before_a_zones_first_rule_names_the_date_and_lmt():
    at = _app("1850-05-23", (14, 30), 28.6139, 77.209)
    text = "\n".join(n.value for n in at.sidebar.error)
    assert "1850-05-23" in text and "LMT" in text and "Asia/Kolkata" in text, text
    assert not at.sidebar.info or "UTC offset" not in "\n".join(n.value for n in at.sidebar.info)
    assert any("1850-05-23" in n.value for n in at.main.error), "the page's recovery panel carries the sentence"


def test_ambiguous_and_skipped_clocks_are_still_refused():
    twice = _app("2000-10-29", (2, 30), 43.7792, 11.2463)
    assert "happens twice in" in _sidebar(twice), _sidebar(twice)
    skipped = _app("2000-03-26", (2, 30), 43.7792, 11.2463)
    assert "does not exist in" in _sidebar(skipped), _sidebar(skipped)


def test_an_out_of_range_offset_seed_is_refused_and_stays_refused():
    at = make_app(date="1982-06-01", page="chart")
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 14.25
    at.run()
    assert_no_exception(at, "manual 14.25")
    assert any("outside the box's range" in n.value for n in at.sidebar.error), _sidebar(at)
    at.run()
    assert any("-14 to +14" in n.value for n in at.sidebar.error), "the refusal stands on the next run"
    at.sidebar.number_input(key="utc_offset_key").set_value(-5.0).run()
    assert not at.sidebar.error and "UTC-05:00" in _sidebar(at), _sidebar(at)
