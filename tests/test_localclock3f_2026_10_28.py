"""A place's two year rows that meet on one clock make no change of the clocks.

A place's rows in data/place_clocks.tsv are cut at every 1 January, so a
year's last row meets the next year's first, most often with the same clock
either side. Such a meeting is no change: clock_change does not list it, and
a skipped or repeated hour whose reach holds it is stated as the one change
it is, naming the place, as the zone's record states it, at 1 January or
inside a year. A meeting where only the abbreviation changes, or only the
offset, is still a change, and a disputed stretch's ends still fall inside a
reach, so a stretch whose reach holds any of them is still not one
change and nothing is said of it.

The tables are written by the test, read by the loader from their path and
put in the table's place for the test alone; the shipped file is read at run
time, its values never written here.
"""
from datetime import datetime, time, timedelta

import pytest

from conftest import assert_no_exception, make_app, sync_engine_to_environment
from engine import TIME_STANDARD_OPTIONS

CHICAGO = "America/Chicago"
# A document the program holds, for a written table's rows to name.
DOC = "US1966TIME"
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

FOLDTOWN = ((45.25, -93.25), "9100001", "Foldtown", CHICAGO)
GAP_AFTER = ((45.25, -93.75), "9100002", "Gap After", CHICAGO)
GAP_BEFORE = ((44.75, -93.25), "9100003", "Gap Before", CHICAGO)
NAMETOWN = ((44.75, -93.75), "9100004", "Nametown", CHICAGO)
DISPUTOWN = ((44.25, -93.25), "9100005", "Disputown", CHICAGO)
OFFSETTOWN = ((44.25, -93.75), "9100006", "Offsettown", CHICAGO)
MIDYEAR = ((45.75, -93.25), "9100007", "Midyear", CHICAGO)


def _whole(year, offset, abbreviation):
    return (f"{year}-01-01 00:00", f"{year + 1}-01-01 00:00", offset, abbreviation)


SPANS = {
    # Summer time to the end of 1957, then back to standard time half an
    # hour into 1958: the repeated hour runs across midnight, where the two
    # years' rows meet on one clock.
    FOLDTOWN: [_whole(1957, "-05:00", "CDT"),
               ("1958-01-01 00:00", "1958-01-01 00:30", "-05:00", "CDT"),
               ("1958-01-01 00:30", "1959-01-01 00:00", "-06:00", "CST")],
    # Forward half an hour into 1958: the skipped hour begins half an hour
    # after the meeting.
    GAP_AFTER: [_whole(1957, "-06:00", "CST"),
                ("1958-01-01 00:00", "1958-01-01 00:30", "-06:00", "CST"),
                ("1958-01-01 00:30", "1959-01-01 00:00", "-05:00", "CDT")],
    # Forward an hour and a half before 1958: the skipped hour ends half an
    # hour before the meeting.
    GAP_BEFORE: [("1957-01-01 00:00", "1957-12-31 22:30", "-06:00", "CST"),
                 ("1957-12-31 22:30", "1958-01-01 00:00", "-05:00", "CDT"),
                 _whole(1958, "-05:00", "CDT")],
    # As Foldtown, but the clock that meets the year's last is named anew:
    # the same offset, another abbreviation.
    NAMETOWN: [_whole(1957, "-05:00", "CDT"),
               ("1958-01-01 00:00", "1958-01-01 00:30", "-05:00", "CWT"),
               ("1958-01-01 00:30", "1959-01-01 00:00", "-06:00", "CST")],
    # A disputed stretch begins twenty minutes after a change forward, on
    # the same clock either side of it.
    DISPUTOWN: [("1960-01-01 00:00", "1960-04-24 02:00", "-06:00", "CST"),
                ("1960-04-24 02:00", "1960-04-24 03:20", "-05:00", "CDT"),
                ("1960-04-24 03:20", "1960-05-01 00:00", "", ""),
                ("1960-05-01 00:00", "1961-01-01 00:00", "-05:00", "CDT")],
    # As Foldtown, but the clock that meets the year's last keeps its
    # abbreviation and is set back one minute: a change of offset, made
    # thirty-one minutes before the fold's change, inside its reach.
    OFFSETTOWN: [_whole(1957, "-05:00", "CDT"),
                 ("1958-01-01 00:00", "1958-01-01 00:30", "-05:01", "CDT"),
                 ("1958-01-01 00:30", "1959-01-01 00:00", "-06:00", "CST")],
    # Two rows meeting on one clock inside a year, not at 1 January, half
    # an hour before a change forward.
    MIDYEAR: [("1960-01-01 00:00", "1960-10-01 00:00", "-06:00", "CST"),
              ("1960-10-01 00:00", "1960-10-01 00:30", "-06:00", "CST"),
              ("1960-10-01 00:30", "1961-01-01 00:00", "-05:00", "CDT")],
}


def _row(place, span, ids=DOC):
    (lat, lon), geonameid, name, zone = place
    start, end, offset, abbreviation = span
    return "\t".join([repr(lat), repr(lon), geonameid, name, zone, start, end, offset, abbreviation,
                      "clock" if offset else "disputed", ids])


@pytest.fixture
def clocks(tz, tmp_path, monkeypatch):
    """The places above, written as one table, read from its path and put
    in the table's place in time_zones.py for this test alone. The engine
    is brought to the environment first, so that no reload of it during the
    test takes the written table into its own names."""
    sync_engine_to_environment()
    rows = [_row(place, span) for place, spans in SPANS.items() for span in spans]
    path = tmp_path / "clocks.tsv"
    path.write_text("# A table written for a test.\n#\n" + "\t".join(tz.PLACE_CLOCK_COLUMNS) + "\n"
                    + "\n".join(rows) + "\n", encoding="utf-8")
    places = tz._read_place_clocks(path)
    assert len(places) == len(SPANS)
    monkeypatch.setattr(tz, "PLACE_CLOCKS", places)
    return places


def _refusal(tz, place, reading):
    (lat, lon), _geonameid, _name, zone = place
    with pytest.raises(tz.NamedZoneRefusal) as refused:
        tz.named_zone_state(zone, *reading, latitude=lat, longitude=lon)
    assert not isinstance(refused.value, tz.PlaceClockRefusal)
    return refused.value.kind, refused.value.place


def _change(tz, place, kind, reading):
    (lat, lon), _geonameid, _name, zone = place
    return tz.clock_change(kind, zone, *reading, latitude=lat, longitude=lon)


CDT, CST, CWT = (-18000, "CDT"), (-21600, "CST"), (-18000, "CWT")

STATED = [
    # The repeated hour across midnight, on either side of it.
    (FOLDTOWN, "ambiguous", (1957, 12, 31, 23, 30, 0), (1958, 1, 1, 0, 30, 0), CDT, CST),
    (FOLDTOWN, "ambiguous", (1957, 12, 31, 23, 45, 0), (1958, 1, 1, 0, 30, 0), CDT, CST),
    (FOLDTOWN, "ambiguous", (1958, 1, 1, 0, 0, 0), (1958, 1, 1, 0, 30, 0), CDT, CST),
    (FOLDTOWN, "ambiguous", (1958, 1, 1, 0, 29, 0), (1958, 1, 1, 0, 30, 0), CDT, CST),
    (GAP_AFTER, "nonexistent", (1958, 1, 1, 0, 30, 0), (1958, 1, 1, 0, 30, 0), CST, CDT),
    (GAP_AFTER, "nonexistent", (1958, 1, 1, 1, 29, 0), (1958, 1, 1, 0, 30, 0), CST, CDT),
    (GAP_BEFORE, "nonexistent", (1957, 12, 31, 22, 30, 0), (1957, 12, 31, 22, 30, 0), CST, CDT),
    (GAP_BEFORE, "nonexistent", (1957, 12, 31, 23, 29, 0), (1957, 12, 31, 22, 30, 0), CST, CDT),
    # A one-clock meeting inside a year is no change either.
    (MIDYEAR, "nonexistent", (1960, 10, 1, 0, 30, 0), (1960, 10, 1, 0, 30, 0), CST, CDT),
    (MIDYEAR, "nonexistent", (1960, 10, 1, 1, 29, 0), (1960, 10, 1, 0, 30, 0), CST, CDT),
]


def test_a_year_s_rows_meeting_on_one_clock_are_read_as_the_rows_say(tz, clocks):
    # The written tables load, the meeting at 1 January is where the file
    # puts it, and the readings either side of each stretch are cast once.
    for place, spans in SPANS.items():
        intervals = clocks[place[0]]["intervals"]
        assert len(intervals) == len(spans)
    (lat, lon), _geonameid, _name, zone = FOLDTOWN
    for reading, abbreviation in [((1957, 12, 31, 23, 29, 0), "CDT"), ((1958, 1, 1, 0, 30, 0), "CST")]:
        assert tz.named_zone_state(zone, *reading, latitude=lat, longitude=lon)["abbreviation"] == abbreviation


@pytest.mark.parametrize("place, kind, reading, at, before, after", STATED)
def test_a_stretch_whose_reach_holds_a_one_clock_meeting_is_stated_as_its_change(
        tz, clocks, place, kind, reading, at, before, after):
    assert _refusal(tz, place, reading) == (kind, place[2])
    assert _change(tz, place, kind, reading) == {"place": place[2], "zone": place[3], "at": at,
                                                  "before": before, "after": after}


def test_a_one_clock_meeting_is_not_listed_as_a_change(tz, clocks):
    # Read at the meeting's own hour, Foldtown's repeated reading is placed
    # in the one change after it, not in the meeting.
    change = _change(tz, FOLDTOWN, "ambiguous", (1958, 1, 1, 0, 0, 0))
    assert change["at"] != (1958, 1, 1, 0, 0, 0)
    assert change["before"] != change["after"]


@pytest.mark.parametrize("place, kind, reading, words", [
    (FOLDTOWN, "ambiguous", (1957, 12, 31, 23, 45, 0),
     {"where": "Foldtown", "time": "00:30", "date": "1958-01-01", "amount": "one hour",
      "before": "CDT (UTC-05:00)", "after": "CST (UTC-06:00)", "before_offset": "UTC-05:00",
      "after_offset": "UTC-06:00", "reading": "1957-12-31 23:45"}),
    (GAP_AFTER, "nonexistent", (1958, 1, 1, 1, 0, 0),
     {"where": "Gap After", "time": "00:30", "date": "1958-01-01", "amount": "one hour",
      "before": "CST (UTC-06:00)", "after": "CDT (UTC-05:00)", "before_offset": "UTC-06:00",
      "after_offset": "UTC-05:00", "reading": "01:00"}),
    (GAP_BEFORE, "nonexistent", (1957, 12, 31, 23, 0, 0),
     {"where": "Gap Before", "time": "22:30", "date": "1957-12-31", "amount": "one hour",
      "before": "CST (UTC-06:00)", "after": "CDT (UTC-05:00)", "before_offset": "UTC-06:00",
      "after_offset": "UTC-05:00", "reading": "23:00"}),
])
def test_the_change_sentence_s_words_are_written(tz, clocks, place, kind, reading, words):
    assert tz.clock_change_words(_change(tz, place, kind, reading), reading) == words


def test_the_box_states_the_change_of_a_repeated_hour_across_midnight(clocks):
    at = make_app(date="1957-12-31", page="sources")
    at.session_state["manual_lat_key"] = FOLDTOWN[0][0]
    at.session_state["manual_lon_key"] = FOLDTOWN[0][1]
    at.session_state["time_input_key"] = time(23, 45)
    at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[1]
    at.run(timeout=TIMEOUT)
    assert_no_exception(at, "Foldtown 1957")
    sentence = ("At **00:30 on 1958-01-01** the clocks in Foldtown moved back one hour, from CDT (UTC-05:00) to "
                "CST (UTC-06:00), so **1957-12-31 23:45** occurred twice: first at UTC-05:00, then at UTC-06:00. "
                f"Choose {TIME_STANDARD_OPTIONS[2]} and enter the one the birth record gives.")
    errors = [n.value for n in at.sidebar.error]
    assert sentence in errors, errors


@pytest.mark.parametrize("reading", [(1957, 12, 31, 23, 30, 0), (1957, 12, 31, 23, 45, 0),
                                     (1958, 1, 1, 0, 15, 0)])
def test_a_meeting_where_only_the_abbreviation_changes_still_leaves_the_stretch_unsaid(tz, clocks, reading):
    assert _refusal(tz, NAMETOWN, reading) == ("ambiguous", "Nametown")
    assert _change(tz, NAMETOWN, "ambiguous", reading) is None


@pytest.mark.parametrize("reading", [(1960, 4, 24, 2, 0, 0), (1960, 4, 24, 2, 30, 0), (1960, 4, 24, 2, 59, 0)])
def test_a_disputed_end_inside_a_reach_still_leaves_the_stretch_unsaid(tz, clocks, reading):
    assert _refusal(tz, DISPUTOWN, reading) == ("nonexistent", "Disputown")
    assert _change(tz, DISPUTOWN, "nonexistent", reading) is None


@pytest.mark.parametrize("reading", [(1957, 12, 31, 23, 31, 0), (1957, 12, 31, 23, 45, 0),
                                     (1958, 1, 1, 0, 15, 0), (1958, 1, 1, 0, 29, 0)])
def test_a_meeting_with_one_abbreviation_and_another_offset_still_leaves_the_stretch_unsaid(tz, clocks, reading):
    # The meeting is a change of offset under one abbreviation: listed, it
    # falls inside the fold's reach, and the fold is not one change.
    meeting = [interval for interval in clocks[OFFSETTOWN[0]]["intervals"]
               if interval["from_local"][:3] == (1958, 1, 1)]
    assert meeting[0]["abbreviation"] == "CDT" and meeting[0]["offset_seconds"] == -18060
    assert _refusal(tz, OFFSETTOWN, reading) == ("ambiguous", "Offsettown")
    assert _change(tz, OFFSETTOWN, "ambiguous", reading) is None


# --- the shipped file ----------------------------------------------------------------------

def _one_clock_new_years(tz):
    """Every 1 January midnight where a place's two year rows meet on one
    clock, the same offset and abbreviation either side: (place's pair, the
    place, that midnight as a naive local datetime)."""
    found = []
    for pair, place in tz.PLACE_CLOCKS.items():
        intervals = place["intervals"]
        for earlier, later in zip(intervals, intervals[1:]):
            meeting = later["from_local"]
            if (earlier["to_local"] == meeting and meeting[1:] == (1, 1, 0, 0, 0)
                    and earlier["kind"] == later["kind"] == "clock"
                    and (earlier["offset_seconds"], earlier["abbreviation"])
                    == (later["offset_seconds"], later["abbreviation"])):
                found.append((pair, place, datetime(*meeting)))
    return found


def test_the_shipped_file_s_folds_and_gaps_by_a_one_clock_new_year_are_stated_as_the_record_states_them(tz):
    """Every reading the place refuses as skipped or repeated within 61
    minutes of such a midnight is stated as one change, naming the town,
    with the clocks and the moment the zone's record gives. A mismatch is
    named by place and year alone."""
    meetings = _one_clock_new_years(tz)
    assert meetings
    refused, wrong, places = 0, [], set()
    for (lat, lon), place, midnight in meetings:
        for minute in range(-61, 62):
            moment = midnight + timedelta(minutes=minute)
            reading = (moment.year, moment.month, moment.day, moment.hour, moment.minute, 0)
            try:
                tz.named_zone_state(place["zone"], *reading, latitude=lat, longitude=lon)
            except tz.PlaceClockRefusal:
                continue
            except tz.NamedZoneRefusal as refusal:
                if refusal.kind not in ("ambiguous", "nonexistent"):
                    continue
                refused += 1
                places.add(place["name"])
                own = tz.clock_change(refusal.kind, place["zone"], *reading, latitude=lat, longitude=lon)
                record = tz.clock_change(refusal.kind, place["zone"], *reading)
                if (refusal.place != place["name"] or own is None or record is None
                        or own["place"] != place["name"] or record["place"] is not None
                        or any(own[part] != record[part] for part in ("before", "after", "at"))):
                    wrong.append((place["name"], moment.year))
    assert refused, "no fold or gap lies by a one-clock new year in the shipped file"
    assert {"Flagstaff", "Phoenix", "Tucson", "Yuma"} <= places, sorted(places)
    assert not wrong, sorted(set(wrong))
