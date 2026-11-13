"""The clocks particular places kept before 1970: the shapes a larger table
brings, and the documents read from a file of their own.

The table of places' clocks (data/place_clocks.tsv) is read as its header
says for shapes Minnesota's thirteen places did not have: a year between two
researched years that the research has not settled has no rows, and a
reading in it is cast by the zone's record, with the caution, as at a place
with no clocks of its own; nothing is paired across it, and the first end
after it is read on its own clock. Disputed years that follow one another
are one row, which may run across the end of a year, and the refusal names
that row's own ends; a disputed stretch may be a place's first or last
interval, or meet a year with no rows, and its ends are read on the first
clock after it at the place, else the last before it. A year's clock may
change at 1 January 00:00, a place's standard may change inside a year, and
a year may hold two summers; Hawaii's half hours and Alaska's clocks are
read as any other. Two atlas places at exactly one pair are one place.

The documents the places' years name come from data/place_clock_sources.tsv,
generated with the table, read into PRE1970_SOURCES at import; a malformed
row, an id written twice, a status outside the list or a title in a form a
title here does not take stops the import. Every title and status the
program held before is held as it was.

Each shape is a table written by the test, read by the loader from its
path and put in the table's place for the test alone.
"""
import ast
import hashlib
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment
from engine import TIME_STANDARD_OPTIONS
from test_atlas1_windows_2026_10_14 import BOOKKEEPING
from test_prose_counts import BUILD_PROCESS_MARKERS

ROOT = APP_PATH.parent
DATA = ROOT / "data" / "place_clocks.tsv"
SOURCES = ROOT / "data" / "place_clock_sources.tsv"
CHICAGO = "America/Chicago"
MANUAL = TIME_STANDARD_OPTIONS[2]
CAUTION = ("Before 1970 this zone's record is Chicago's; where the birth record gives the offset, "
           "use Manual UTC offset.")
# A document the program holds, for a written table's rows to name.
DOC = "US1966TIME"
PAGE = "official or library scan, read on the page image"
TIMEOUT = 300


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


# --- the tables written here -------------------------------------------------------------
#
# A place: (its pair, its record's id, its name, its zone). A span: (from, to)
# as the file writes them, the offset and abbreviation, both empty for a
# disputed stretch.

GAPTON = ((45.5, -94.5), "9000001", "Gapton", CHICAGO)
EDGEWOOD = ((45.25, -94.25), "9000002", "Edgewood", CHICAGO)
OPENER = ((45.75, -94.75), "9000003", "Opener", CHICAGO)
RUNVILLE = ((44.5, -95.5), "9000004", "Runville", CHICAGO)
LASTVILLE = ((32.25, -106.75), "9000005", "Lastville", "America/Denver")
FIRSTVILLE = ((45.75, -93.75), "9000006", "Firstville", CHICAGO)
HAWAII = ((19.75, -155.25), "9000007", "Hawaii Town", "Pacific/Honolulu")
ALASKA = ((61.5, -149.5), "9000008", "Alaska Town", "America/Anchorage")
TWO_SUMMERS = ((46.5, -97.5), "9000009", "Twosummers", CHICAGO)
LAKESHORE = ((41.5, -88.25), "9000010", "Lakeshore", CHICAGO)
EDGEYEAR = ((32.75, -114.5), "9000011", "Edgeyear", "America/Phoenix")
EDGEYEAR_EAST = ((32.75, -114.25), "9000012", "Edgeyear East", "America/Phoenix")
# The atlas holds three places at exactly this pair (Hastings, Nebraska, and
# two small places beside it), by their GeoNames ids.
SHARED_PAIR = (40.58612, -98.38839)
SHARED_IDS = (5069802, 5064425, 5066323)
SHARED = (SHARED_PAIR, "9000013", "Sharedpair", CHICAGO)


def _whole(year, offset, abbreviation):
    return (f"{year}-01-01 00:00", f"{year + 1}-01-01 00:00", offset, abbreviation)


SPANS = {
    # Researched in 1950, 1951, 1954 and 1955; 1952 and 1953 not settled.
    # Its standard is not the same either side of them.
    GAPTON: [_whole(1950, "-05:00", "EST"), _whole(1951, "-05:00", "EST"),
             _whole(1954, "-06:00", "CST"), _whole(1955, "-06:00", "CST")],
    # A stretch to the end of a year that a year with no rows follows.
    EDGEWOOD: [("1950-01-01 00:00", "1950-11-01 00:00", "-06:00", "CST"),
               ("1950-11-01 00:00", "1951-01-01 00:00", "", ""),
               _whole(1952, "-05:00", "EST")],
    # A stretch opening a year that follows a year with no rows.
    OPENER: [_whole(1950, "-06:00", "CST"),
             ("1952-01-01 00:00", "1952-03-01 00:00", "", ""),
             ("1952-03-01 00:00", "1953-01-01 00:00", "-05:00", "EST")],
    # A run of disputed years as one row, from the end of a summer into the
    # third year.
    RUNVILLE: [("1960-01-01 00:00", "1960-04-24 02:00", "-06:00", "CST"),
               ("1960-04-24 02:00", "1960-09-25 02:00", "-05:00", "CDT"),
               ("1960-09-25 02:00", "1962-03-01 00:00", "", ""),
               ("1962-03-01 00:00", "1962-04-29 02:00", "-06:00", "CST"),
               ("1962-04-29 02:00", "1962-10-28 02:00", "-05:00", "CDT"),
               ("1962-10-28 02:00", "1963-01-01 00:00", "-06:00", "CST")],
    # The place's last interval disputed, to 1970.
    LASTVILLE: [_whole(1968, "-07:00", "MST"),
                ("1969-01-01 00:00", "1969-04-27 02:00", "-07:00", "MST"),
                ("1969-04-27 02:00", "1970-01-01 00:00", "", "")],
    # The place's first interval disputed.
    FIRSTVILLE: [("1918-01-01 00:00", "1918-03-31 02:00", "", ""),
                 ("1918-03-31 02:00", "1918-10-27 02:00", "-05:00", "CDT"),
                 ("1918-10-27 02:00", "1919-01-01 00:00", "-06:00", "CST")],
    HAWAII: [("1933-01-01 00:00", "1933-04-30 02:00", "-10:30", "HST"),
             ("1933-04-30 02:00", "1933-05-21 12:00", "-09:30", "HDT"),
             ("1933-05-21 12:00", "1934-01-01 00:00", "-10:30", "HST")],
    ALASKA: [("1918-01-01 00:00", "1918-03-31 02:00", "-10:00", "AST"),
             ("1918-03-31 02:00", "1918-10-27 02:00", "-09:00", "AHDT"),
             ("1918-10-27 02:00", "1919-01-01 00:00", "-10:00", "AST")],
    TWO_SUMMERS: [("1960-01-01 00:00", "1960-04-24 02:00", "-06:00", "CST"),
                  ("1960-04-24 02:00", "1960-06-26 02:00", "-05:00", "CDT"),
                  ("1960-06-26 02:00", "1960-07-31 02:00", "-06:00", "CST"),
                  ("1960-07-31 02:00", "1960-09-25 02:00", "-05:00", "CDT"),
                  ("1960-09-25 02:00", "1961-01-01 00:00", "-06:00", "CST")],
    # Its standard moved forward inside 1931 and back inside 1933.
    LAKESHORE: [("1931-01-01 00:00", "1931-06-01 00:00", "-06:00", "CST"),
                ("1931-06-01 00:00", "1932-01-01 00:00", "-05:00", "EST"),
                _whole(1932, "-05:00", "EST"),
                ("1933-01-01 00:00", "1933-09-01 00:00", "-05:00", "EST"),
                ("1933-09-01 00:00", "1934-01-01 00:00", "-06:00", "CST")],
    # The clock changes at 1 January 00:00: back, and (east) forward.
    EDGEYEAR: [_whole(1928, "-07:00", "MST"), _whole(1929, "-08:00", "PST")],
    EDGEYEAR_EAST: [_whole(1928, "-08:00", "PST"), _whole(1929, "-07:00", "MST")],
    SHARED: [_whole(1965, "-06:00", "CST")],
}


def _row(place, span, ids=DOC):
    (lat, lon), geonameid, name, zone = place
    start, end, offset, abbreviation = span
    return "\t".join([repr(lat), repr(lon), geonameid, name, zone, start, end, offset, abbreviation,
                      "clock" if offset else "disputed", ids])


def _write(path, rows, columns):
    path.write_text("# A table written for a test.\n#\n" + "\t".join(columns) + "\n" + "\n".join(rows) + "\n",
                    encoding="utf-8")
    return path


@pytest.fixture
def clocks(tz, tmp_path, monkeypatch):
    """The places above, written as one table, read from its path and put
    in the table's place in time_zones.py, where the cast reads it, for
    this test alone. The engine is brought to the environment first, so
    that no reload of it during the test takes the written table into its
    own names."""
    sync_engine_to_environment()
    rows = [_row(place, span) for place, spans in SPANS.items() for span in spans]
    places = tz._read_place_clocks(_write(tmp_path / "clocks.tsv", rows, tz.PLACE_CLOCK_COLUMNS))
    assert len(places) == len(SPANS) == 13
    monkeypatch.setattr(tz, "PLACE_CLOCKS", places)
    return places


def _state(tz, place, reading):
    (lat, lon), _geonameid, _name, zone = place
    try:
        return tz.named_zone_state(zone, *reading, latitude=lat, longitude=lon)
    except tz.PlaceClockRefusal as refusal:
        return ("clock_choice", refusal.interval)
    except tz.NamedZoneRefusal as refusal:
        return (refusal.kind, refusal.place)


def _ut(interval, end):
    return f"{interval[end]:%Y-%m-%d %H:%M}"


def _record(tz, place, reading):
    return tz.named_zone_state(place[3], *reading)


# --- a year the research has not settled ---------------------------------------------------

def test_a_place_s_researched_years_are_the_years_its_rows_cover(tz, clocks):
    assert clocks[GAPTON[0]]["years"] == frozenset({1950, 1951, 1954, 1955})
    assert clocks[EDGEWOOD[0]]["years"] == frozenset({1950, 1952})
    assert clocks[RUNVILLE[0]]["years"] == frozenset({1960, 1961, 1962})
    assert clocks[LASTVILLE[0]]["years"] == frozenset({1968, 1969})


@pytest.mark.parametrize("year", [1952, 1953])
def test_a_year_with_no_rows_reads_the_zone_s_record_with_the_caution(tz, engine, clocks, year):
    reading = (year, 7, 1, 12, 0, 0)
    assert tz._place_clocks_at(CHICAGO, year, *GAPTON[0]) is None
    assert _state(tz, GAPTON, reading) == _record(tz, GAPTON, reading) == {"offset_seconds": -18000,
                                                                          "abbreviation": "CDT"}
    assert tz.zone_record_place(*GAPTON[0], CHICAGO, reading) == "Chicago"
    assert engine["zone_record_caution"](*GAPTON[0], CHICAGO, reading) == CAUTION


@pytest.mark.parametrize("reading, expected", [
    ((1951, 7, 1, 12, 0, 0), {"offset_seconds": -18000, "abbreviation": "EST", "place_clock": True}),
    ((1951, 12, 31, 23, 30, 0), {"offset_seconds": -18000, "abbreviation": "EST", "place_clock": True}),
    ((1954, 1, 1, 0, 30, 0), {"offset_seconds": -21600, "abbreviation": "CST", "place_clock": True}),
    ((1954, 7, 1, 12, 0, 0), {"offset_seconds": -21600, "abbreviation": "CST", "place_clock": True}),
])
def test_the_years_either_side_are_cast_from_their_rows_with_no_caution(tz, engine, clocks, reading, expected):
    assert _state(tz, GAPTON, reading) == expected
    assert engine["zone_record_caution"](*GAPTON[0], CHICAGO, reading) is None


def test_each_end_at_a_year_with_no_rows_is_read_on_its_own_clock(tz, clocks):
    """1951 ends on its eastern standard, 1954 begins on its central: each
    read on its own clock, neither on the other's across the two years."""
    intervals = clocks[GAPTON[0]]["intervals"]
    assert [(_ut(i, "from"), _ut(i, "to")) for i in intervals] == [
        ("1950-01-01 05:00", "1951-01-01 05:00"), ("1951-01-01 05:00", "1952-01-01 05:00"),
        ("1954-01-01 06:00", "1955-01-01 06:00"), ("1955-01-01 06:00", "1956-01-01 06:00")]


def test_no_change_is_paired_across_a_year_with_no_rows(tz, clocks):
    """Across the two years the clock goes from -05:00 to -06:00; paired,
    the last hour of 1951 would be a fold of the place's own."""
    reading = (1951, 12, 31, 23, 30, 0)
    assert _state(tz, GAPTON, reading)["abbreviation"] == "EST"
    assert tz.clock_change("ambiguous", CHICAGO, *reading, latitude=GAPTON[0][0], longitude=GAPTON[0][1]) is None
    assert tz.clock_change("nonexistent", CHICAGO, 1954, 1, 1, 0, 30, 0, latitude=GAPTON[0][0],
                           longitude=GAPTON[0][1]) is None


def test_a_stretch_before_a_year_with_no_rows_is_beside_its_one_clock(tz, clocks):
    """Edgewood's stretch to the end of 1950: its `to` is read on the first
    clock after it at the place (the file's rule), 1952's eastern standard;
    its clock beside it is the one before it alone. Every reading between
    its ends is refused, the last hour of the year among them, which the
    clock before it would put after it."""
    stretch = clocks[EDGEWOOD[0]]["intervals"][1]
    assert stretch["kind"] == "disputed" and stretch["offsets"] == (-21600,)
    assert (_ut(stretch, "from"), _ut(stretch, "to")) == ("1950-11-01 06:00", "1951-01-01 05:00")
    ends = ((1950, 11, 1, 0, 0, 0), (1951, 1, 1, 0, 0, 0))
    for reading in [(1950, 11, 1, 0, 0, 0), (1950, 12, 1, 12, 0, 0), (1950, 12, 31, 23, 30, 0),
                    (1950, 12, 31, 23, 59, 59)]:
        assert _state(tz, EDGEWOOD, reading) == ("clock_choice", ends), reading
    assert _state(tz, EDGEWOOD, (1950, 10, 31, 23, 59, 59))["abbreviation"] == "CST"
    assert _state(tz, EDGEWOOD, (1951, 6, 1, 12, 0, 0)) == _record(tz, EDGEWOOD, (1951, 6, 1, 12, 0, 0))
    assert _state(tz, EDGEWOOD, (1952, 1, 1, 0, 0, 0))["abbreviation"] == "EST"


def test_a_stretch_after_a_year_with_no_rows_is_beside_the_clock_after_it(tz, clocks):
    stretch = clocks[OPENER[0]]["intervals"][1]
    assert stretch["kind"] == "disputed" and stretch["offsets"] == (-18000,)
    assert (_ut(stretch, "from"), _ut(stretch, "to")) == ("1952-01-01 05:00", "1952-03-01 05:00")
    assert _state(tz, OPENER, (1952, 1, 1, 0, 0, 0)) == ("clock_choice", ((1952, 1, 1, 0, 0, 0), (1952, 3, 1, 0, 0, 0)))
    assert _state(tz, OPENER, (1952, 3, 1, 0, 0, 0))["abbreviation"] == "EST"
    assert _state(tz, OPENER, (1951, 6, 1, 12, 0, 0)) == _record(tz, OPENER, (1951, 6, 1, 12, 0, 0))


# --- a run of disputed years, one row -----------------------------------------------------

RUN_ENDS = ((1960, 9, 25, 2, 0, 0), (1962, 3, 1, 0, 0, 0))


def test_a_run_of_disputed_years_is_one_interval_beside_the_clocks_either_side(tz, clocks):
    intervals = clocks[RUNVILLE[0]]["intervals"]
    assert len(intervals) == 6
    run = intervals[2]
    assert (run["kind"], run["from_local"], run["to_local"]) == ("disputed",) + RUN_ENDS
    # Its start read on the summer time it ends, its end on the standard
    # time after it.
    assert (_ut(run, "from"), _ut(run, "to")) == ("1960-09-25 07:00", "1962-03-01 06:00")
    assert run["offsets"] == (-21600, -18000)


@pytest.mark.parametrize("reading, expected", [
    ((1960, 9, 25, 0, 59, 59), "CDT"),
    # The hour before its start: summer time puts it before, standard time
    # inside, so it is refused.
    ((1960, 9, 25, 1, 30, 0), "refused"),
    ((1960, 9, 25, 2, 0, 0), "refused"),
    ((1961, 1, 1, 0, 0, 0), "refused"),
    ((1961, 7, 4, 12, 0, 0), "refused"),
    ((1962, 2, 28, 23, 59, 59), "refused"),
    # The hour after its end: standard time puts it after, summer time
    # inside, so it is refused.
    ((1962, 3, 1, 0, 30, 0), "refused"),
    ((1962, 3, 1, 1, 0, 0), "CST"),
])
def test_a_run_is_refused_with_its_own_ends_and_cast_either_side(tz, clocks, reading, expected):
    state = _state(tz, RUNVILLE, reading)
    if expected == "refused":
        assert state == ("clock_choice", RUN_ENDS)
    else:
        assert state["abbreviation"] == expected and state["place_clock"] is True, state


def test_a_run_s_refusal_in_the_box_names_its_own_ends(clocks):
    at = _app(RUNVILLE, "1961-07-04").run(timeout=TIMEOUT)
    assert_no_exception(at, "Runville 1961")
    sentence = ("**1961-07-04 12:00**: the sources do not settle which clock was kept at this place between "
                f"1960-09-25 02:00 and 1962-03-01. Choose {MANUAL} and enter the offset of the clock the time "
                "was recorded in.")
    errors = [n.value for n in at.sidebar.error]
    assert sentence in errors, errors


# --- a disputed first or last interval ----------------------------------------------------

def test_a_last_interval_disputed_to_1970_is_read_on_the_clock_before_it(tz, clocks):
    stretch = clocks[LASTVILLE[0]]["intervals"][-1]
    assert stretch["kind"] == "disputed" and stretch["offsets"] == (-25200,)
    assert (_ut(stretch, "from"), _ut(stretch, "to")) == ("1969-04-27 09:00", "1970-01-01 07:00")
    ends = ((1969, 4, 27, 2, 0, 0), (1970, 1, 1, 0, 0, 0))
    assert _state(tz, LASTVILLE, (1969, 12, 31, 23, 59, 59)) == ("clock_choice", ends)
    assert _state(tz, LASTVILLE, (1969, 4, 27, 2, 0, 0)) == ("clock_choice", ends)
    assert _state(tz, LASTVILLE, (1969, 4, 27, 1, 59, 59)) == {"offset_seconds": -25200, "abbreviation": "MST",
                                                                 "place_clock": True}
    reading = (1970, 1, 1, 0, 0, 0)
    assert _state(tz, LASTVILLE, reading) == _record(tz, LASTVILLE, reading) == {"offset_seconds": -25200,
                                                                                 "abbreviation": "MST"}


def test_a_first_interval_disputed_is_read_on_the_clock_after_it(tz, clocks):
    stretch = clocks[FIRSTVILLE[0]]["intervals"][0]
    assert stretch["kind"] == "disputed" and stretch["offsets"] == (-18000,)
    assert (_ut(stretch, "from"), _ut(stretch, "to")) == ("1918-01-01 05:00", "1918-03-31 07:00")
    assert _state(tz, FIRSTVILLE, (1918, 1, 1, 0, 0, 0)) == ("clock_choice", ((1918, 1, 1, 0, 0, 0),
                                                                              (1918, 3, 31, 2, 0, 0)))
    assert _state(tz, FIRSTVILLE, (1918, 3, 31, 2, 0, 0))["abbreviation"] == "CDT"
    assert _state(tz, FIRSTVILLE, (1917, 12, 31, 23, 59, 59)) == _record(tz, FIRSTVILLE, (1917, 12, 31, 23, 59, 59))


# --- Hawaii's half hours, an Alaska summer, two summers in a year ---------------------------

@pytest.mark.parametrize("place, reading, expected", [
    (HAWAII, (1933, 3, 1, 12, 0, 0), (-37800, "HST")),
    (HAWAII, (1933, 5, 1, 12, 0, 0), (-34200, "HDT")),
    (HAWAII, (1933, 7, 1, 12, 0, 0), (-37800, "HST")),
    (ALASKA, (1918, 2, 1, 12, 0, 0), (-36000, "AST")),
    (ALASKA, (1918, 7, 1, 12, 0, 0), (-32400, "AHDT")),
    (ALASKA, (1918, 12, 1, 12, 0, 0), (-36000, "AST")),
])
def test_hawaii_s_half_hours_and_an_alaska_summer_are_cast_as_named(tz, clocks, place, reading, expected):
    assert _state(tz, place, reading) == {"offset_seconds": expected[0], "abbreviation": expected[1],
                                          "place_clock": True}


def test_an_alaska_summer_the_zone_s_record_did_not_keep_is_the_place_s(tz, clocks):
    assert _record(tz, ALASKA, (1918, 7, 1, 12, 0, 0)) == {"offset_seconds": -36000, "abbreviation": "AST"}


@pytest.mark.parametrize("reading, expected", [
    ((1960, 5, 15, 12, 0, 0), "CDT"), ((1960, 7, 15, 12, 0, 0), "CST"),
    ((1960, 8, 15, 12, 0, 0), "CDT"), ((1960, 10, 15, 12, 0, 0), "CST"),
    ((1960, 6, 26, 1, 30, 0), ("ambiguous", "Twosummers")),
    ((1960, 7, 31, 2, 30, 0), ("nonexistent", "Twosummers")),
])
def test_two_summers_in_a_year_are_each_cast_and_their_changes_refused(tz, clocks, reading, expected):
    state = _state(tz, TWO_SUMMERS, reading)
    assert (state if isinstance(expected, tuple) else state["abbreviation"]) == expected


@pytest.mark.parametrize("kind, reading, at, before, after", [
    ("ambiguous", (1960, 6, 26, 1, 30, 0), (1960, 6, 26, 2, 0, 0), (-18000, "CDT"), (-21600, "CST")),
    ("nonexistent", (1960, 7, 31, 2, 30, 0), (1960, 7, 31, 2, 0, 0), (-21600, "CST"), (-18000, "CDT")),
])
def test_the_second_summer_s_changes_are_the_place_s_own(tz, clocks, kind, reading, at, before, after):
    change = tz.clock_change(kind, CHICAGO, *reading, latitude=TWO_SUMMERS[0][0], longitude=TWO_SUMMERS[0][1])
    assert change == {"place": "Twosummers", "zone": CHICAGO, "at": at, "before": before, "after": after}


# --- a standard changed inside a year, and at 1 January -------------------------------------

LAKESHORE_GAP = (1931, 6, 1, 0, 30, 0)
LAKESHORE_FOLD = (1933, 8, 31, 23, 30, 0)


def test_a_standard_changed_inside_a_year_refuses_its_gap_and_fold_by_the_place(tz, clocks):
    assert _state(tz, LAKESHORE, LAKESHORE_GAP) == ("nonexistent", "Lakeshore")
    assert _state(tz, LAKESHORE, LAKESHORE_FOLD) == ("ambiguous", "Lakeshore")
    assert _state(tz, LAKESHORE, (1931, 6, 1, 1, 0, 0))["abbreviation"] == "EST"
    assert _state(tz, LAKESHORE, (1933, 8, 31, 22, 59, 59))["abbreviation"] == "EST"
    assert _state(tz, LAKESHORE, (1933, 9, 1, 0, 0, 0))["abbreviation"] == "CST"


@pytest.mark.parametrize("kind, reading, reason", [
    ("nonexistent", LAKESHORE_GAP,
     "1931-06-01 00:30:00 never occurred in Lakeshore: the clocks moved forward one hour at 00:00 on 1931-06-01"),
    ("ambiguous", LAKESHORE_FOLD,
     "1933-08-31 23:30:00 occurred twice in Lakeshore: the clocks moved back one hour at 00:00 on 1933-09-01; "
     "no occurrence is selected"),
])
def test_a_standard_s_change_is_stated_in_the_anniversary(engine, clocks, kind, reading, reason):
    birth = datetime(reading[0] - 1, *reading[1:])
    result = engine["anniversary_moment"](birth, 1, time_standard="named", zone_name=CHICAGO,
                                          latitude=LAKESHORE[0][0], longitude=LAKESHORE[0][1])
    assert result.status == "unavailable"
    assert result.reason == reason


def test_a_standard_s_change_is_stated_in_the_box(clocks):
    at = _app(LAKESHORE, "1931-06-01", clock=time(0, 30)).run(timeout=TIMEOUT)
    assert_no_exception(at, "Lakeshore 1931")
    sentence = ("At **00:00 on 1931-06-01** the clocks in Lakeshore moved forward one hour, from CST (UTC-06:00) to "
                "EST (UTC-05:00), so **00:30** never occurred there. Check the recorded time.")
    errors = [n.value for n in at.sidebar.error]
    assert sentence in errors, errors


@pytest.mark.parametrize("place, reading, state", [
    # Back at the turn of the year: the last hour of 1928 happens twice.
    (EDGEYEAR, (1928, 12, 31, 22, 59, 59), "MST"),
    (EDGEYEAR, (1928, 12, 31, 23, 30, 0), ("ambiguous", "Edgeyear")),
    (EDGEYEAR, (1929, 1, 1, 0, 0, 0), "PST"),
    # Forward at the turn of the year: the first hour of 1929 never was.
    (EDGEYEAR_EAST, (1928, 12, 31, 23, 59, 59), "PST"),
    (EDGEYEAR_EAST, (1929, 1, 1, 0, 30, 0), ("nonexistent", "Edgeyear East")),
    (EDGEYEAR_EAST, (1929, 1, 1, 1, 0, 0), "MST"),
])
def test_a_change_at_1_january_is_read_on_the_clock_that_ends_there(tz, clocks, place, reading, state):
    got = _state(tz, place, reading)
    assert (got if isinstance(state, tuple) else got["abbreviation"]) == state


@pytest.mark.parametrize("place, kind, reading, before, after", [
    (EDGEYEAR, "ambiguous", (1928, 12, 31, 23, 30, 0), (-25200, "MST"), (-28800, "PST")),
    (EDGEYEAR_EAST, "nonexistent", (1929, 1, 1, 0, 30, 0), (-28800, "PST"), (-25200, "MST")),
])
def test_a_change_at_1_january_is_stated_as_one(tz, clocks, place, kind, reading, before, after):
    change = tz.clock_change(kind, place[3], *reading, latitude=place[0][0], longitude=place[0][1])
    assert change == {"place": place[2], "zone": place[3], "at": (1929, 1, 1, 0, 0, 0), "before": before,
                      "after": after}


# --- one pair, several atlas places -----------------------------------------------------------

def test_every_atlas_place_at_a_researched_pair_takes_its_clocks(tz, clocks):
    with sqlite3.connect(f"file:{ROOT / 'atlas.db'}?mode=ro", uri=True) as atlas:
        pairs = [atlas.execute("SELECT lat, lon FROM cities WHERE id = ?", (i,)).fetchone() for i in SHARED_IDS]
    atlas.close()
    assert pairs == [SHARED_PAIR] * 3, "the premise: the atlas holds three places at the pair"
    reading = (1965, 7, 4, 12, 0, 0)
    assert _record(tz, SHARED, reading)["abbreviation"] == "CDT", "the premise: Chicago kept summer time"
    states = [tz.named_zone_state(CHICAGO, *reading, latitude=lat, longitude=lon) for lat, lon in pairs]
    assert states == [{"offset_seconds": -21600, "abbreviation": "CST", "place_clock": True}] * 3


# --- the load's stops, as the new shapes meet them ----------------------------------------------

def _load_rows(tz, tmp_path, rows):
    return tz._read_place_clocks(_write(tmp_path / "clocks.tsv", rows, tz.PLACE_CLOCK_COLUMNS))


@pytest.mark.parametrize("damage, rows, phrase", [
    ("a clock's row across the end of its year",
     [_row(GAPTON, ("1950-01-01 00:00", "1951-06-01 00:00", "-05:00", "EST")),
      _row(GAPTON, ("1951-06-01 00:00", "1952-01-01 00:00", "-05:00", "EST"))],
     "does not follow the place's last one"),
    ("a year that ends before its end, then a year with no rows",
     [_row(GAPTON, ("1950-01-01 00:00", "1950-12-31 00:00", "-05:00", "EST")),
      _row(GAPTON, _whole(1952, "-05:00", "EST"))],
     "does not follow the place's last one"),
    ("a year with no rows, then a year begun late",
     [_row(GAPTON, _whole(1950, "-05:00", "EST")),
      _row(GAPTON, ("1952-01-02 00:00", "1953-01-01 00:00", "-05:00", "EST"))],
     "does not follow the place's last one"),
    ("rows that run backwards across years",
     [_row(GAPTON, _whole(1952, "-05:00", "EST")), _row(GAPTON, _whole(1950, "-05:00", "EST"))],
     "does not follow the place's last one"),
    ("two disputed rows that meet",
     [_row(GAPTON, ("1950-01-01 00:00", "1950-06-01 00:00", "-05:00", "EST")),
      _row(GAPTON, ("1950-06-01 00:00", "1950-12-01 00:00", "", "")),
      _row(GAPTON, ("1950-12-01 00:00", "1951-01-01 00:00", "", ""))],
     "no clock on either side"),
    ("a place with no clock",
     [_row(GAPTON, ("1950-01-01 00:00", "1951-01-01 00:00", "", ""))],
     "no clock on either side"),
])
def test_the_new_shapes_keep_the_load_s_stops(tz, tmp_path, damage, rows, phrase):
    with pytest.raises(ValueError, match=phrase):
        _load_rows(tz, tmp_path, rows)


def test_the_written_table_is_read_whole_and_twice_alike(tz, tmp_path, clocks):
    rows = [_row(place, span) for place, spans in SPANS.items() for span in spans]
    assert len(rows) == 43
    again = _load_rows(tz, tmp_path, rows)
    assert again == clocks
    assert sum(len(p["intervals"]) for p in again.values()) == 43


# --- the documents' file --------------------------------------------------------------------

def _honest_sources():
    return [line for line in SOURCES.read_text(encoding="utf-8").split("\n") if line and not line.startswith("#")][1:]


def _code_table(tz):
    """PRE1970_SOURCES as time_zones.py writes it, without the file's rows."""
    in_file = {line.split("\t")[0] for line in _honest_sources()}
    return {sid: entry for sid, entry in tz.PRE1970_SOURCES.items() if sid not in in_file}


def _source_row(sid, title="A document, p 3", status=PAGE):
    return "\t".join([sid, title, status])


# Each a file's rows and a phrase of the sentence the import stops with.
SOURCE_STOPS = {
    "a row of two cells": (["NEWDOC1\tA document, p 3"], "has 2 columns, not 3"),
    "a row of four cells": ([_source_row("NEWDOC1") + "\tmore"], "has 4 columns, not 3"),
    "an id twice in the file": ([_source_row("NEWDOC1"), _source_row("NEWDOC1", "Another document")],
                                "a document the program holds already"),
    "an id the program holds for another record": ([_source_row("US1966TIME")], "a document the program holds already"),
    "an id of the program's other documents": ([_source_row("SE1979")], "a document the program holds already"),
    "an id in lower case": ([_source_row("Newdoc1")], "an id not written as this file writes one"),
    "an id with a stroke": ([_source_row("NEW_DOC1")], "an id not written as this file writes one"),
    "an id with a digit first": ([_source_row("1NEWDOC")], "an id not written as this file writes one"),
    "an id of one letter": ([_source_row("N")], "an id not written as this file writes one"),
    "an id of twenty-one characters": ([_source_row("N" * 21)], "an id not written as this file writes one"),
    "a status outside the list": ([_source_row("NEWDOC1", status="read on the page")], "a status outside"),
    "an empty title": ([_source_row("NEWDOC1", "")], "a title in a form"),
    "a title beginning with a space": ([_source_row("NEWDOC1", " A document")], "a title in a form"),
    "a title ending with a space": ([_source_row("NEWDOC1", "A document ")], "a title in a form"),
}
# A title in each refused form, and a phrase of the form.
TITLE_PLANTS = [
    (r"\bpp?\.\s*\d", "A gazette, p. 12"), (r"\bpp?\.\s*\d", "A gazette, pp. 12-13"),
    (r"\d{1,2}\.\d{1,2}\s*,\s*\d", "A treatise 4.12, 3"),
    (r"\brulings?\s+\d", "A statute, as rulings 1 and 2 hold"), (r"\bround\s+\d", "A statute, read in round 3"),
    (r"\bN-\d", "A statute, see N-4"), (r"\bN-?\d+[a-z]", "A statute, see N9z"), (r"\bEN-?\d", "A statute, see EN07"),
    (r"\bR\d+b?\.\d", "A statute, as R12.3 has it"), (r"\bfinding\s+\d", "A statute, by finding 7"),
    (r"\bdecision\s+\d", "A statute, by decision 9"), (r"reproduction", "A statute, a Reproduction"),
    (r"\(\d\.\d\)", "A statute, the bound (1.2)"), (r"\breview[\s-]+clip", "A statute, the review-clip"),
    (r"\blane\s+(?-i:[A-Z])", "A statute, built in lane Q"), (r"\b202[4-9]-\d\d-\d\d", "A statute, read on 2029-01-01"),
]


@pytest.mark.parametrize("damage", sorted(SOURCE_STOPS))
def test_a_malformed_documents_file_stops_the_load(tz, tmp_path, damage):
    rows, phrase = SOURCE_STOPS[damage]
    path = _write(tmp_path / "sources.tsv", rows, tz.PLACE_CLOCK_SOURCE_COLUMNS)
    with pytest.raises(ValueError, match=phrase):
        tz._read_place_clock_sources(path, held=_code_table(tz))


@pytest.mark.parametrize("form, title", TITLE_PLANTS, ids=[title for _form, title in TITLE_PLANTS])
def test_a_title_in_each_refused_form_stops_the_load(tz, tmp_path, form, title):
    assert form in tz.PLACE_CLOCK_SOURCE_LOCATOR_FORMS + tz.PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS
    path = _write(tmp_path / "sources.tsv", [_source_row("NEWDOC1", title)], tz.PLACE_CLOCK_SOURCE_COLUMNS)
    with pytest.raises(ValueError, match="a title in a form"):
        tz._read_place_clock_sources(path, held=_code_table(tz))


@pytest.mark.parametrize("title", [
    # A page written as a title here writes one; a capital P that is not a
    # page; an abbreviation's stop; a law's section; a year alone.
    "A gazette, p 12", "Laws, chapter P. 4", "Statutes of the District of Columbia, D.C.",
    "A statute, section 1.1", "A statute of 1966"])
def test_a_title_in_the_forms_a_title_takes_loads(tz, tmp_path, title):
    path = _write(tmp_path / "sources.tsv", [_source_row("NEWDOC1", title)], tz.PLACE_CLOCK_SOURCE_COLUMNS)
    assert tz._read_place_clock_sources(path, held=_code_table(tz)) == {"NEWDOC1": (title, PAGE)}


def test_the_refused_forms_are_the_ones_the_tests_read_every_title_for(tz):
    """The bookkeeping forms, without regard to case, as the windows test's
    BOOKKEEPING; the two page patterns, as written, as its locator test."""
    assert tz.PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS == BOOKKEEPING
    source = (ROOT / "tests" / "test_atlas1_windows_2026_10_14.py").read_text(encoding="utf-8")
    locators = tz.PLACE_CLOCK_SOURCE_LOCATOR_FORMS
    assert len(locators) == 2
    assert len(TITLE_PLANTS) == 16
    for form in locators:
        assert f'assert not re.search(r"{form}", text), text' in source, form
    planted = {form for form, _title in TITLE_PLANTS}
    assert planted == set(tz.PLACE_CLOCK_SOURCE_LOCATOR_FORMS + tz.PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS)


def test_the_honest_documents_file_loads_as_the_import_did(tz):
    held = _code_table(tz)
    assert len(held) == 52 and "US1966TIME" in held and "TZ2026E" in held
    read = tz._read_place_clock_sources(held=held)
    assert read == {sid: tz.PRE1970_SOURCES[sid] for sid in read}
    assert len(read) == len(_honest_sources()) >= 67
    assert set(read) | set(held) == set(tz.PRE1970_SOURCES)


def _tree(tmp_path, sources_rows):
    """A scratch copy of the zone code and its data, its documents' file
    replaced by `sources_rows` under the header, the file's recorded hash
    moved with it, so that only the rows are read wrong."""
    tree = tmp_path / "tree"
    tree.mkdir()
    shutil.copytree(ROOT / "data", tree / "data")
    data = (SOURCES.read_text(encoding="utf-8").split("id\ttitle\tstatus\n")[0] + "id\ttitle\tstatus\n"
            + "\n".join(sources_rows) + "\n").encode("utf-8")
    (tree / "data" / "place_clock_sources.tsv").write_bytes(data)
    code = (ROOT / "time_zones.py").read_text(encoding="utf-8")
    honest = hashlib.sha256(SOURCES.read_bytes()).hexdigest()
    assert code.count(honest) == 1
    (tree / "time_zones.py").write_text(code.replace(honest, hashlib.sha256(data).hexdigest()), encoding="utf-8")
    return tree


@pytest.mark.parametrize("damage, change, phrase", [
    ("a malformed row", lambda rows: rows[:-1] + [rows[-1].rsplit("\t", 1)[0]], "has 2 columns, not 3"),
    ("an id twice", lambda rows: rows + [rows[0]], "a document the program holds already"),
    ("an id the program holds", lambda rows: rows + [_source_row("US1966TIME")],
     "a document the program holds already"),
    ("a status outside the list", lambda rows: rows[:-1] + [rows[-1].rsplit("\t", 1)[0] + "\tread on the page"],
     "a status outside"),
    ("a refused title", lambda rows: rows + [_source_row("NEWDOC1", "A gazette, p. 12")], "a title in a form"),
])
def test_the_import_stops_on_a_malformed_documents_file(tmp_path, damage, change, phrase):
    tree = _tree(tmp_path, change(_honest_sources()))
    done = subprocess.run([sys.executable, "-I", "-c",
                           f"import sys; sys.path[:0] = [{str(tree)!r}]\nimport time_zones"],
                          cwd=tree, capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode != 0, done.stdout
    assert "ValueError: data/place_clock_sources.tsv:" in done.stderr and phrase in done.stderr, done.stderr


def test_the_honest_rows_in_the_scratch_tree_import(tz, tmp_path):
    """The control of the stops above: the same tree with the file's own rows imports."""
    tree = _tree(tmp_path, _honest_sources())
    assert (tree / "data" / "place_clock_sources.tsv").read_bytes() == SOURCES.read_bytes()
    done = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path[:0] = [{str(tree)!r}]\n"
                           "import time_zones as tz; print(len(tz.PRE1970_SOURCES))"],
                          cwd=tree, capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == str(len(tz.PRE1970_SOURCES)) and len(tz.PRE1970_SOURCES) >= 119


# --- the documents moved, every title and status as it was ----------------------------------

def test_every_title_and_status_the_program_held_is_held_as_it_was(tz):
    assert {sid: tz.PRE1970_SOURCES[sid] for sid in OLD_PLACE_SOURCES} == OLD_PLACE_SOURCES
    assert len(OLD_PLACE_SOURCES) == 67


def test_the_moved_documents_have_one_home(tz):
    """The file's ids are the 67, and none of them is written in the code any
    more; the documents the code keeps for its other records stay there."""
    tree = ast.parse((ROOT / "time_zones.py").read_text(encoding="utf-8"))
    table, = [n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets]
              == ["PRE1970_SOURCES"]]
    written = set(ast.literal_eval(table.value))
    in_file = [line.split("\t")[0] for line in _honest_sources()]
    assert set(OLD_PLACE_SOURCES) <= set(in_file) and len(set(in_file)) == len(in_file) >= 67
    assert not written & set(in_file)
    assert {"US1966TIME", "TZ2026E"} <= written and len(written) == 52
    assert set(tz.PRE1970_SOURCES) == written | set(in_file)


def _cited():
    return {sid for line in DATA.read_text(encoding="utf-8").split("\n")[1:] if line and not line.startswith("#")
            and not line.startswith("lat\t") for sid in line.split("\t")[10].split(";")}


def test_the_file_holds_every_document_the_table_cites_but_the_code_s(tz):
    """Every document the file lists is cited by the table, and every one
    the table cites is in the file but those the code keeps for its other
    records (the act of 1966 and the time-zone release)."""
    cited = _cited()
    in_file = {line.split("\t")[0] for line in _honest_sources()}
    assert len(cited) >= 68 and in_file < cited
    assert "US1966TIME" in cited - in_file <= {"US1966TIME", "TZ2026E"}
    assert cited - in_file <= set(_code_table(tz))


def test_the_file_s_titles_carry_no_mark_of_the_build():
    """The guard of the program's strings (BUILD_PROCESS_MARKERS), which no
    longer meets these titles in the code, reads them in the file. (The id
    guard's forms read them in that guard's own file, which the public tree
    does not carry.)"""
    rows = [line.split("\t") for line in _honest_sources()]
    assert len(rows) >= 67
    marks = [(sid, m.group(0)) for sid, title, _status in rows for m in BUILD_PROCESS_MARKERS.finditer(title)]
    assert marks == []


# The forms a title takes no part of, beside those the import refuses and
# the page form the windows test reads: a year from 2026 on written as one
# (after a month, alone in brackets, after a word that dates a volume, after
# a word that dates a reading of a copy, or opening a date written with
# hyphens), a file's name, a curly quote, and
# "Stat." where the titles write "Stat".
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
TITLE_OTHER_FORMS = {
    "a year from 2026 on": re.compile(
        rf"(?:\b(?:{_MONTHS})(?: \d{{1,2}},)? |\(|\b(?:in|of|Laws|Statutes|[Ss]ession|edition|printing) )"
        r"(?:202[6-9]|20[3-9]\d|2[1-9]\d\d)\b|\b(?:202[6-9]|20[3-9]\d)-\d"
        r"|\b(?i:accessed|retrieved|supplied|viewed)\b[^\d;]{0,40}\b(?:202[6-9]|20[3-9]\d|2[1-9]\d\d)\b"),
    "a file name": re.compile(r"\.(?:pdf|html?|tsv|txt|jpg|png)\b", re.IGNORECASE),
    "a curly quote": re.compile("[\u2018\u2019\u201c\u201d]"),
    "Stat.": re.compile(r"\bStat\."),
}


def test_the_file_s_titles_carry_no_late_year_file_name_curly_quote_or_stat_stop():
    rows = [line.split("\t") for line in _honest_sources()]
    assert len(rows) >= 67
    found = [(sid, form, m.group(0)) for sid, title, _status in rows for form, pattern in TITLE_OTHER_FORMS.items()
             for m in pattern.finditer(title)]
    assert found == []


@pytest.mark.parametrize("form, title", [
    ("a year from 2026 on", "A newspaper, March 3, 2031, p 1"),
    ("a year from 2026 on", "A newspaper, March 2031, p 1"),
    ("a year from 2026 on", "A statute, Laws 2031, ch. 4"),
    ("a year from 2026 on", "A report (2026)"),
    ("a year from 2026 on", "A notice, 2031-03, p 2"),
    ("a year from 2026 on", "A page, accessed 2031"),
    ("a year from 2026 on", "A page, Retrieved in the year 2031"),
    ("a year from 2026 on", "A copy, SUPPLIED by a library, 2031"),
    ("a year from 2026 on", "A scan, viewed 2031"),
    ("a file name", "An archive's copy, notice_1946.PDF"),
    ("a file name", "A page, index.html"),
    ("a curly quote", "A newspaper, p 1, \u201cTime\u201d"),
    ("a curly quote", "A newspaper\u2019s page"),
    ("Stat.", "An act, 40 Stat. 450"),
])
def test_each_other_form_is_found(form, title):
    assert TITLE_OTHER_FORMS[form].search(title), title


@pytest.mark.parametrize("title", ["An act, 40 Stat 450", "Federal Register 2940-2941", "Circular No. 2283",
                                   "A newspaper, May 2, 1947, p 1", "Laws 1968, ch.183", "Opinion 3172, May 21, 1948"])
def test_a_document_s_own_numbers_are_not_taken_for_another_form(title):
    assert not any(pattern.search(title) for pattern in TITLE_OTHER_FORMS.values()), title


# --- the box ---------------------------------------------------------------------------------

def _app(place, date, clock=time(12, 0)):
    at = make_app(date=date, page="sources")
    at.session_state["manual_lat_key"] = place[0][0]
    at.session_state["manual_lon_key"] = place[0][1]
    at.session_state["time_input_key"] = clock
    at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[1]
    return at


# --- the old table's place documents, frozen as the program held them ------------------------
#
# Written out by a script from time_zones.py as it stood before they moved
# (its PRE1970_SOURCES, read by ast), never typed.

OLD_PLACE_SOURCES = {
    'BRANDT19650426': (
        'Lloyd Brandt, Minneapolis Chamber of Commerce, statement to Senate Commerce Committee on S. 1404, '
        'April 26, 1965; reprinted in Congressional Record, House, August 3, 1965, p 19262',
        'official or library scan, read on the page image'),
    'BROADCASTING19590504': (
        'Broadcasting, vol. 56, no. 18, May 4, 1959, p 54, "Daylight time vs. theatre owners," reporting '
        "WCCO's account",
        'official or library scan, read on the page image'),
    'CONCORDIAN19590522': (
        'The Concordian, Concordia College, Moorhead, May 22, 1959, vol. L, p 1, Set Clocks Ahead; Digital '
        'Horizons item p16921coll4/24465',
        'official or library scan, read on the page image'),
    'DULHERALD19640428': (
        'Jerome Marks, Duluth Herald, State to Take No Action on DST Controversy; Law Test In Hands Of '
        'Citizen, April 28, 1964. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19640502': (
        'Duluth Herald, Clocks Go Ahead Sunday, May 2, 1964. Minnesota Historical Society Digital Newspaper '
        'Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19640504': (
        'Duluth Herald, Funeral notices: Savage, Mrs. Marie (Lenroot Funeral Home), May 4, 1964. Minnesota '
        'Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19640908': (
        'Duluth Herald, Weather, Time Factor (primary-election report), September 8, 1964. Minnesota '
        'Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19640926': (
        'Duluth Herald, Turn Clocks Back One Hour, September 26, 1964. Minnesota Historical Society Digital '
        'Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19640928': (
        'Duluth Herald, TV listings, WDSM/KDAL/WDSE, September 28, 1964. Minnesota Historical Society '
        'Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19641001': (
        'Northern Pacific Railway advertisement, Duluth Herald, NP Local Trains on Later Schedules, October '
        '1, 1964. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'DULHERALD19650901': (
        'Roger Skophammer, Duluth Herald, Duluth Clocks to Keep on Ticking to Fast Time, September 1, 1965. '
        'Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'GRHERALD19650428': (
        'Grand Rapids Herald-Review, Daylight Time Confusion Gets Federal Attention, April 28, 1965; '
        'reprinted in Congressional Record, House, August 3, 1965, vol. 111, p 19262. Original newspaper '
        'page number not verified',
        'official or library scan, read on the page image'),
    'KENORAMINER19610922': (
        'Kenora Daily Miner and News, Fort Frances Ends Daylight Saving Time Sunday, September 22, 1961, p 6',
        'official or library scan, read on the page image'),
    'MESABINEWS19650512': (
        'Virginia (Minn.) Mesabi News, Confusion in Time, May 12, 1965, reprinted in Congressional Record, '
        'House, August 3, 1965, vol. 111, p 19263',
        'official or library scan, read on the page image'),
    'MN1901': (
        'Minnesota, General Laws 1901, chapter 15, sections 1-2; approved February 26, 1901, p 16',
        'official or library scan, read on the page image'),
    'MN1941': (
        'Minnesota, Session Laws 1941, chapter 492, section 7, p 909; sections 2 and 46; approved April 28, '
        '1941, pp 907-919',
        'official or library scan, read on the page image'),
    'MN1945': (
        'Minnesota, Session Laws 1945, chapter 393, section 1; approved April 19, 1945, pp 759-760',
        'official or library scan, read on the page image'),
    'MN1957C646': (
        'Minnesota, Session Laws 1957, chapter 646, sections 1-3; approved April 25, 1957, p 877',
        'official or library scan, read on the page image'),
    'MN1959EXC46': (
        'Minnesota, Extra Session Laws 1959, chapter 46, sections 1-4; approved June 15, effective June 30, '
        '1959, p 1518',
        'official or library scan, read on the page image'),
    'MNAG19450609': (
        'J. A. A. Burnquist, Minnesota Attorney General, Opinion 83-F, June 9, 1945, to H. K. Brehmer, '
        'Winona City Attorney, 3 pp',
        'official or library scan, read on the page image'),
    'MNAG19650505': (
        'Robert W. Mattson, Minnesota Attorney General, Opinion 216-J-8 (catalog code), May 5, 1965, to '
        'William H. Joyce, Liquor Control Commissioner, 5 pp',
        'official or library scan, read on the page image'),
    'MNAG19660414': (
        'Robert W. Mattson and John F. Casey Jr., Minnesota Attorney General, Opinion 83-F, April 14, 1966, '
        'to James E. Garrity, Moorhead City Attorney, 3 pp',
        'official or library scan, read on the page image'),
    'MNEO1957': (
        'Orville L. Freeman, Governor of Minnesota, Executive Order 1957 No. 8, signed September 20, 1957; '
        'Minnesota Legislative Reference Library scan',
        'official or library scan, read on the page image'),
    'MNEO1958': (
        'Orville L. Freeman, Governor of Minnesota, Executive Order 1958 No. 2, signed March 18, 1958; '
        'Minnesota Legislative Reference Library scan',
        'official or library scan, read on the page image'),
    'MNEO1959': (
        'Orville L. Freeman, Governor of Minnesota, Executive Order 1959 No. 5, signed May 20, 1959; '
        'Minnesota Legislative Reference Library scan',
        'official or library scan, read on the page image'),
    'MNSC1959AMUSEMENT': (
        'Minnesota Supreme Court, State ex rel. Minnesota Amusement Co. v. County Board of Ramsey County '
        'Commissioners, No. 37,831, May 8 and May 13, 1959, 255 Minn. 413-417, 96 N.W.2d 580',
        'unofficial mirror of the official text'),
    'MNSC1959LORD': (
        'Minnesota Supreme Court, In re Miles Lord et al., No. 37,852, May 28, 1959, 255 Minn. 370-384, 97 '
        'N.W.2d 287',
        'unofficial mirror of the official text'),
    'MNSTAT1947ANNOT': (
        'Minnesota Statutes 1947 Annotations, chapter 645, section 645.07, printed p 1548',
        'official or library scan, read on the page image'),
    'MNSTAT1967': (
        'Minnesota Statutes 1967, chapter 645, section 645.071',
        'official or library scan, read on the page image'),
    'MNSTAT1969': (
        'Minnesota Statutes 1969, chapter 645, section 645.071',
        'official or library scan, read on the page image'),
    'MPLSSTAR19650506': (
        'Minneapolis Star, Biggest Problem: State 3 Weeks Behind Others in Daylight Saving Time Start, by '
        'Dick Caldwell, May 6, 1965; reprinted in Congressional Record, House, August 3, 1965, vol. 111, p '
        '19260. Original newspaper page number not verified',
        'official or library scan, read on the page image'),
    'MPLSSTAR19650510': (
        'Minneapolis Star, Confusion Reigns as St. Paul Goes on Daylight Saving Time, May 10, 1965; '
        'reprinted in Congressional Record, House, August 3, 1965, vol. 111, p 19260. Original newspaper '
        'page number not verified',
        'official or library scan, read on the page image'),
    'MPLSSTAR19650727': (
        'Minneapolis Star, July 27, 1965, Jim Shoop, "St. Paul To Concur With Daylight Saving Time Statute"; '
        "reprinted in Congressional Record, House, August 3, 1965, vol. 111, p 19264 col. 2 (Karth's "
        'extension)',
        'official or library scan, read on the page image'),
    'MPLSTRIB19640614': (
        'Minneapolis Tribune, Fifty-Eight Percent Say Congress Should Decide Dates for Daylight Saving, June '
        '14, 1964; reprinted in Congressional Record, House, August 3, 1965, vol. 111, p 19261. Original '
        'newspaper page number not verified',
        'official or library scan, read on the page image'),
    'MPLSTRIB19650430': (
        'Minneapolis Tribune, Minnesota DST Muddle Deepens, April 30, 1965; reprinted in Congressional '
        'Record, House, May 3, 1965, pp 9186-9187',
        'official or library scan, read on the page image'),
    'MPLSTRIB19650509': (
        'Minneapolis Tribune, Now Is the Hour—Pick One, May 9, 1965; reprinted in Congressional Record, '
        'House, August 3, 1965, vol. 111, pp 19260-19261. Original newspaper page number not verified',
        'official or library scan, read on the page image'),
    'PILLSBURY19650611': (
        'Letter, Tom R. Mulcahy, The Pillsbury Co., Minneapolis, June 11, 1965, to Rep. Joseph E. Karth; '
        'printed in Congressional Record, House, August 3, 1965, p 19266 cols. 1-2',
        'official or library scan, read on the page image'),
    'ROCHPOSTBUL19650501': (
        'Rochester Post Bulletin, Uniform Daylight Saving Time Bill Merits Support, by Charles Withers, May '
        '1, 1965; reprinted in Congressional Record, House, August 3, 1965, vol. 111, p 19262. Original '
        'newspaper page number not verified',
        'official or library scan, read on the page image'),
    'SHANKSAAMN1P269': (
        'Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, table MN #1',
        "commercial facsimile, read on the researcher's retained copy"),
    'SHANKSAAMN2P269': (
        'Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, table MN #2',
        "commercial facsimile, read on the researcher's retained copy"),
    'SHANKSAAMN3P269': (
        'Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, table MN #3',
        "commercial facsimile, read on the researcher's retained copy"),
    'SHANKSAAMN5P269': (
        'Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, table MN #5',
        "commercial facsimile, read on the researcher's retained copy"),
    'SHANKSAAMN7P269': (
        'Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, table MN #7',
        "commercial facsimile, read on the researcher's retained copy"),
    'STCDT19590427DELL': (
        'Associated Press, The St. Cloud Daily Times, Dell Blasts Twin City Defiance on Time Ban, April 27, '
        '1959. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STCDT19590427TCT': (
        'St. Cloud Daily Times, April 27, 1959, p 1, local story "Twin City Time Isn\'t Our Time" (on the '
        'same page as the Associated Press story "Dell Blasts Twin City Defiance on Time Ban"; Minnesota '
        'Historical Society Digital Newspaper Hub)',
        'official or library scan, read on the page image'),
    'STCDT19590509': (
        'United Press (UP), The St. Cloud Daily Times, Freeman Orders Statewide Fast Time May 24-July 1, May '
        '9, 1959. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STCDT19590523': (
        'United Press (UP), The St. Cloud Daily Times, Rural Areas Turn Clocks Ahead One Hour Tonight, May '
        '23, 1959. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STCDT19590525': (
        "Harold Schoelkopf, The St. Cloud Daily Times, Editor's Notebook, May 25, 1959. Minnesota Historical "
        'Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STCDT19640504': (
        'Associated Press, The St. Cloud Daily Times, Few Hitches as Duluth Shifts To Fast Time, May 4, '
        '1964. Minnesota Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STCDT19650501': (
        'Associated Press, The St. Cloud Daily Times, Hibbing Delays Time Switch, May 1, 1965. Minnesota '
        'Historical Society Digital Newspaper Hub',
        'official or library scan, read on the page image'),
    'STPAULDISP19650727': (
        'St. Paul Dispatch, July 27, 1965, Carl G. Langland, "Mayor Asks Repeal of Fast-Time Decree"; '
        'reprinted in Congressional Record, House, August 3, 1965, p 19264 col. 3 to p 19265 col. 1',
        'official or library scan, read on the page image'),
    'STPAULDISP19650728': (
        'St. Paul Dispatch, July 28, 1965, editorial "GVT Mission Accomplished"; reprinted in Congressional '
        'Record, House, August 3, 1965, p 19264 col. 3',
        'official or library scan, read on the page image'),
    'STPAULPP19640430': (
        'St. Paul Pioneer Press, Uniform Time System Required, April 30, 1964; reprinted in Uniform Time, '
        'House hearings, June 18 and August 4, 1964, p 43',
        'official or library scan, read on the page image'),
    'STPAULPP19640513': (
        'St. Paul Pioneer Press, Of Time and Order, May 13, 1964; reprinted in Uniform Time, House hearings, '
        'June 18 and August 4, 1964, p 43',
        'official or library scan, read on the page image'),
    'STPAULPP19650510': (
        'St. Paul Pioneer Press, Time Troubles: Clock Confusion Confounds Cities, May 10, 1965; reprinted in '
        'Congressional Record, House, August 3, 1965, vol. 111, p 19260. Original newspaper page number not '
        'verified',
        'official or library scan, read on the page image'),
    'STPAULRES19640508': (
        'City of St. Paul, council resolution of May 8, 1964, urging uniform federal dates; inserted by Rep. '
        'Karth, Uniform Time hearings, House, 1964, p 42 (text p 43)',
        'official or library scan, read on the page image'),
    'STRINGER19650707': (
        'Letter, Philip Stringer, chairman of the St. Paul Charter Commission, July 7, 1965; printed in '
        'Congressional Record, House, August 3, 1965, p 19265 cols. 2-3',
        'official or library scan, read on the page image'),
    'TVDIGEST19590427': (
        'Table of Summer Time in TV Cities, Weekly Television Digest, vol. 15, no. 17, April 27, 1959, p 13',
        'official or library scan, read on the page image'),
    'US1918': (
        'United States, Act of March 19, 1918, chapter 24, Public No. 106, To save daylight and to provide '
        'standard time for the United States, 40 Stat 450-451, sections 1-5; operative seasonal rule at p 451',
        'official or library scan, read on the page image'),
    'US1919': (
        'United States, Act of August 20, 1919, chapter 51, Public No. 40, For the repeal of the '
        'daylight-saving law, 41 Stat 280-281; repeal effective last Sunday of October 1919',
        'official or library scan, read on the page image'),
    'US1942': (
        'United States, Act of January 20, 1942, chapter 7, Public Law 403, To promote the national security '
        'and defense by establishing daylight saving time, 56 Stat 9, sections 1-2',
        'official or library scan, read on the page image'),
    'US1945': (
        'United States, Act of September 25, 1945, chapter 388, Public Law 187, To provide for termination '
        'of daylight saving time, 59 Stat 537, operative paragraph',
        'official or library scan, read on the page image'),
    'USCR19650503': (
        'United States, Congressional Record, House, May 3, 1965, vol. 111, pp 9186-9187, Donald Fraser, '
        'Minnesota DST Muddle Deepens, with Minneapolis Tribune editorial of April 30, 1965',
        'official or library scan, read on the page image'),
    'USCR19650803': (
        'United States, Congressional Record, House, August 3, 1965, vol. 111, pp 19259-19263, Donald '
        'Fraser, Uniform Daylight Saving Time',
        'official or library scan, read on the page image'),
    'USCR19660330': (
        'United States, Congressional Record, House, March 30, 1966, vol. 112, p 7289, Donald Fraser, An End '
        'to Chaos',
        'official or library scan, read on the page image'),
    'USHR1964TIME': (
        'U.S. House of Representatives, Uniform Time: Hearings before Subcommittee on Commerce and Finance '
        'of Committee on Interstate and Foreign Commerce, 88th Congress, 2nd session, June 18 and August 4, '
        '1964, GPO 36-471, pp 27-29, 43, 58-62',
        'official or library scan, read on the page image'),
    'WINONADN19650423': (
        'Winona Daily News, April 23, 1965, p 3, "City Going on DST"; adjacent "WSC to Conform To City Time; '
        'Clocks Same." Public copy preserved by National Weather Service La Crosse flood archive',
        'official or library scan, read on the page image'),
}
