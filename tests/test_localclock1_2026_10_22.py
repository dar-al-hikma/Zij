"""Whose record a full zone keeps before 1970.

The time-zone database records a full zone's history before 1970 for the
place it is named after (America/Chicago: Chicago), and the app casts every
place inside the zone's boundary with that history. A place that kept
another clock then was cast at the named place's with nothing said. Now a
Standard-time cast before 1970 at a place farther than 25 km from its zone's
row in the pinned tzdata's zone1970.tab (anywhere, for a zone with no row
there) says so, under the offset line of the time-standard box and once in
the HTML and Markdown reports' block of the moment and place; the JSON
record is unchanged. LMT and manual casts, 1970 on, the casts the
pre-1970 windows and refusals already speak for, and a cast at a named mean
time that was then the civil clock (whose own sentence says whose clock it
was) carry nothing. Its cases are at Munich, which no research gives clocks of
its own, cast in Europe/Berlin, whose record is Berlin's: a place that has
clocks of its own is cast from them in its researched years and carries
nothing (test_localclock2_2026_10_22.py).
"""
import importlib.resources
import json
import math
from datetime import time

import pytest

from conftest import assert_no_exception, make_app
from engine import TIME_STANDARD_OPTIONS

MUNICH = (48.13743, 11.57549)
BERLIN = (52.52437, 13.41053)
MINNEAPOLIS = (44.97997, -93.26384)
SENTENCE = ("Before 1970 this zone's record is Berlin's; where the birth record gives the offset, "
            "use Manual UTC offset.")
NOON_1965 = (1965, 5, 10, 12, 0, 0)
# The keys of the export's blocks, as the JSON carried them before this
# change: the record gains nothing.
JSON_KEYS = ["schema", "exported", "app", "chart", "input", "entered", "readings", "display", "target",
             "results", "status", "scope", "precision"]
INPUT_KEYS = ["date", "time", "time_standard", "utc_offset_hours", "timezone", "place", "latitude",
              "longitude", "julian_day_ut", "calendar", "ut_calendar"]


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


@pytest.fixture(scope="module")
def zone1970():
    """{zone: (lat, lon)}, read here from the package's own file, apart from
    the module's reading of it."""
    rows = {}
    text = (importlib.resources.files("tzdata") / "zoneinfo" / "zone1970.tab").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("#") or not line:
            continue
        coordinates, zone = line.split("\t")[1:3]
        cut = max(coordinates.rfind("+"), coordinates.rfind("-"))

        def degrees(part, width):
            digits = part[1:]
            value = int(digits[:width]) + int(digits[width:width + 2]) / 60 + int(digits[width + 2:] or 0) / 3600
            return -value if part[0] == "-" else value
        rows[zone] = (degrees(coordinates[:cut], 2), degrees(coordinates[cut:], 3))
    assert len(rows) > 300 and "America/Chicago" in rows and "Europe/Berlin" in rows
    return rows


def _west_of(point, km):
    """The point `km` west of `point` along its parallel, by the haversine on
    the mean Earth radius (6371.0088 km)."""
    lat, lon = point
    step = 2 * math.asin(math.sin(km / (2 * 6371.0088)) / math.cos(math.radians(lat)))
    return lat, lon - math.degrees(step)


# --- the condition ---------------------------------------------------------------

def test_the_named_places_are_the_package_s_rows(tz, zone1970):
    places = tz._zone1970_places()
    assert len(zone1970) > 300
    assert set(places) == set(zone1970)
    assert all(math.isclose(places[z][0], zone1970[z][0]) and math.isclose(places[z][1], zone1970[z][1])
               for z in zone1970)
    assert zone1970["America/Chicago"] == pytest.approx((41.85, -87.65))
    assert tz.ZONE_RECORD_PLACE_KM == 25


def test_munich_1965_is_cast_on_berlin_s_record(tz, engine, zone1970):
    assert tz._distance_km(*MUNICH, *zone1970["Europe/Berlin"]) > 400, "the premise: far from the named place"
    assert not tz._place_clocks_at("Europe/Berlin", 1965, *MUNICH), "the premise: no clocks of its own"
    assert tz.zone_record_place(*MUNICH, "Europe/Berlin", NOON_1965) == "Berlin"
    assert engine["zone_record_caution"](*MUNICH, "Europe/Berlin", NOON_1965) == SENTENCE


def test_chicago_s_own_coordinates_carry_nothing(tz, engine, zone1970):
    assert tz.zone_record_place(*zone1970["America/Chicago"], "America/Chicago", NOON_1965) is None
    assert engine["zone_record_caution"](*zone1970["America/Chicago"], "America/Chicago", NOON_1965) is None


@pytest.mark.parametrize("moment, place", [
    ((1969, 12, 31, 23, 59, 59), "Berlin"),
    ((1970, 1, 1, 0, 0, 0), None),
    ((1970, 6, 1, 12, 0, 0), None),
    ((1971, 5, 10, 12, 0, 0), None),
])
def test_the_bound_is_the_typed_local_1970(tz, moment, place):
    assert tz.zone_record_place(*MUNICH, "Europe/Berlin", moment) == place


def test_a_place_just_inside_the_distance_carries_nothing_and_just_outside_it_does(tz, zone1970):
    chicago = zone1970["America/Chicago"]
    inside, outside = _west_of(chicago, 24.9), _west_of(chicago, 25.1)
    assert tz._distance_km(*chicago, *inside) == pytest.approx(24.9, abs=1e-6)
    assert tz.zone_record_place(*inside, "America/Chicago", NOON_1965) is None
    assert tz.zone_record_place(*outside, "America/Chicago", NOON_1965) == "Chicago"


def test_the_place_is_the_zone_s_last_part_in_words(tz):
    assert tz.zone_record_place(40.8, -74.6, "America/New_York", NOON_1965) == "New York"
    assert tz.zone_record_place(39.0, -86.5, "America/Indiana/Indianapolis", (1950, 1, 1, 12, 0, 0)) == "Indianapolis"


@pytest.mark.parametrize("zone", ["LMT", "UTC-06:00", "UTC+00:00", "Etc/GMT+6", "", None])
def test_lmt_manual_and_sea_names_carry_nothing(tz, zone):
    assert tz.zone_record_place(*MUNICH, zone, NOON_1965) is None


@pytest.mark.parametrize("point", [(float("nan"), 11.57549), (48.13743, float("inf")), (91.0, 11.57549)])
def test_coordinates_that_are_no_place_carry_nothing(tz, point):
    assert tz.zone_record_place(*point, "Europe/Berlin", NOON_1965) is None


@pytest.mark.parametrize("standard", [0, 2])
def test_an_export_block_of_an_lmt_or_manual_cast_carries_nothing(engine, standard):
    """Even with a zone in the block: the time standard decides first."""
    block = {"date": "1965-05-10", "time": "12:00:00", "timezone": "Europe/Berlin",
             "latitude": MUNICH[0], "longitude": MUNICH[1],
             "time_standard": engine["TIME_STANDARD_OPTIONS"][standard]}
    assert engine["export_zone_caution"](block) is None
    block["time_standard"] = engine["TIME_STANDARD_OPTIONS"][1]
    assert engine["export_zone_caution"](block) == SENTENCE
    block["time_standard"] = "Standard time (pytz)"
    assert engine["export_zone_caution"](block) == SENTENCE, "the old label is the same standard"


@pytest.mark.parametrize("block", [{}, {"time_standard": "Standard time (named zone)"},
                                   {"time_standard": "Standard time (named zone)", "date": "1965-05-10",
                                    "time": "noon", "timezone": "Europe/Berlin", "latitude": 48.14,
                                    "longitude": 11.58}])
def test_an_export_block_without_the_moment_carries_nothing(engine, block):
    assert engine["export_zone_caution"](block) is None


def test_a_linked_zone_s_window_refusal_and_disputed_hour_carry_nothing(tz):
    stockholm = (59.33258, 18.0649)
    assert "Europe/Stockholm" in tz.PRE1970_WINDOWS and "Europe/Stockholm" not in tz._zone1970_places()
    # Inside a window: the cast is made, from the window, not the record.
    state = tz.named_zone_state("Europe/Stockholm", 1947, 5, 10, 12, 0, 0)
    assert state["offset_seconds"] == 3600
    assert tz.zone_record_place(*stockholm, "Europe/Stockholm", (1947, 5, 10, 12, 0, 0)) is None
    # The disputed hour, refused.
    with pytest.raises(tz.NamedZoneRefusal, match="disputed"):
        tz.named_zone_state("Europe/Stockholm", 1916, 9, 30, 23, 30, 0)
    assert tz.zone_record_place(*stockholm, "Europe/Stockholm", (1916, 9, 30, 23, 30, 0)) is None
    # A linked zone with no windows, refused before 1970.
    assert "Africa/Accra" in tz.LINKED_ZONES and "Africa/Accra" not in tz.PRE1970_WINDOWS
    assert tz.zone_record_place(5.55602, -0.1969, "Africa/Accra", (1950, 5, 10, 12, 0, 0)) is None
    # From 1970 on, the record holds for both.
    assert tz.zone_record_place(*stockholm, "Europe/Stockholm", (1971, 5, 10, 12, 0, 0)) is None


def test_a_place_the_list_refuses_carries_nothing(tz, zone1970):
    """A Saskatchewan row before 1972-04-30: the area rule refuses the cast,
    although the zone itself would cast it far from its named place."""
    row = (52.73486, -108.3091)
    assert tz.PLACE_ZONES[row]["rule"] == "area:saskatchewan"
    assert "offset_seconds" in tz.named_zone_state("America/Swift_Current", *NOON_1965), "the zone casts it"
    assert tz._distance_km(*row, *zone1970["America/Swift_Current"]) > 200
    with pytest.raises(tz.PlaceClockRefusal):
        tz.place_zone(*row, None, NOON_1965, zone="America/Swift_Current")
    assert tz.zone_record_place(*row, "America/Swift_Current", NOON_1965) is None


def test_a_reading_the_zone_refuses_carries_nothing(tz):
    """Before Berlin kept standard time: no cast, so nothing to caution."""
    with pytest.raises(tz.NamedZoneRefusal):
        tz.named_zone_state("Europe/Berlin", 1850, 1, 1, 12, 0, 0)
    assert tz.zone_record_place(*MUNICH, "Europe/Berlin", (1850, 1, 1, 12, 0, 0)) is None


# --- the box -----------------------------------------------------------------------

def _app(point, date, standard=1, offset=None, page="sources"):
    at = make_app(date=date, page=page)
    at.session_state["manual_lat_key"] = point[0]
    at.session_state["manual_lon_key"] = point[1]
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[standard]
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    return at


def _all_text(at):
    return [n.value for kind in ("info", "success", "warning", "error", "markdown", "caption")
            for n in at.get(kind)]


def test_the_box_says_it_once_under_the_offset_line_for_munich_1965():
    at = _app(MUNICH, "1965-05-10").run(timeout=120)
    assert_no_exception(at, "Munich 1965")
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1, box
    lines = box[0].split("  \n")
    assert lines[0] == "**Europe/Berlin** · UTC offset +01:00 (CET)", lines
    assert lines[1] == SENTENCE, lines
    assert lines[2].startswith("UT 1965-05-10 11:00:00"), lines
    assert sum(text.count("this zone's record is") for text in _all_text(at)) == 1


@pytest.mark.parametrize("point, date", [(BERLIN, "1965-05-10"), (MUNICH, "1971-05-10")])
def test_the_box_says_nothing_for_berlin_1965_or_munich_1971(point, date):
    at = _app(point, date).run(timeout=120)
    assert_no_exception(at, date)
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1 and box[0].startswith("**Europe/Berlin** · UTC offset"), box
    assert box[0].split("  \n")[1].startswith("UT "), box
    texts = _all_text(at)
    assert texts, "the premise: the run printed text"
    assert not any("this zone's record is" in text for text in texts)


@pytest.mark.parametrize("standard, offset, head", [(0, None, "**Exact LMT**"), (2, 1.0, "**Manual offset**")])
def test_the_box_says_nothing_for_an_lmt_or_manual_cast_at_munich_1965(standard, offset, head):
    at = _app(MUNICH, "1965-05-10", standard=standard, offset=offset).run(timeout=120)
    assert_no_exception(at, head)
    box = [n.value for n in at.sidebar.info if n.value.startswith(head)]
    assert len(box) == 1, [n.value for n in at.sidebar.info]
    texts = _all_text(at)
    assert texts, "the premise: the run printed text"
    assert not any("this zone's record is" in text for text in texts)


# --- the exports ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def munich_1965_export():
    at = _app(MUNICH, "1965-05-10").run(timeout=300)
    assert_no_exception(at, "the export")
    return (at.session_state["_analysis_export"], at.session_state["_analysis_html"],
            at.session_state["_analysis_markdown"])


def test_the_html_and_markdown_reports_say_it_once(munich_1965_export, engine):
    analysis, html, markdown = munich_1965_export
    assert html.count(engine["_esc_text"](SENTENCE)) == 1
    assert markdown.count(SENTENCE) == 1
    assert markdown.count("this zone's record is") == 1 and html.count("this zone&") + html.count(
        "this zone's record is") == 1
    assert f"| Time zone | Europe/Berlin |\n| Time zone note | {SENTENCE} |\n" in markdown


def test_the_row_follows_the_zone_s_row_in_the_block_of_the_moment_and_place(munich_1965_export, engine):
    analysis, _html, _markdown = munich_1965_export
    tables = dict(engine["export_header_tables"](analysis))
    rows = tables["The moment and place the chart was cast at"]
    fields = [row["Field"] for row in rows]
    assert fields.count("Time zone note") == 1
    assert fields[fields.index("Time zone") + 1] == "Time zone note"
    assert rows[fields.index("Time zone note")]["Value"] == SENTENCE
    assert len(tables) == 7
    assert all("Time zone note" not in [row.get("Field") for row in r] for t, r in tables.items()
               if t != "The moment and place the chart was cast at")


def test_the_json_record_is_unchanged(munich_1965_export):
    analysis, _html, _markdown = munich_1965_export
    record = json.dumps(analysis, indent=1, ensure_ascii=False)
    assert "zone's record" not in record and "Time zone note" not in record
    assert list(analysis) == JSON_KEYS
    assert list(analysis["input"]) == INPUT_KEYS
    assert analysis["input"]["timezone"] == "Europe/Berlin"
    assert analysis["input"]["time_standard"] == "Standard time (named zone)"


def test_the_reports_say_nothing_for_munich_1971():
    at = _app(MUNICH, "1971-05-10").run(timeout=300)
    assert_no_exception(at, "the export")
    assert at.session_state["_analysis_export"]["input"]["timezone"] == "Europe/Berlin"
    assert "this zone's record is" not in at.session_state["_analysis_markdown"]
    assert "Time zone note" not in at.session_state["_analysis_html"]


# --- a named mean time that was then the civil clock --------------------------------

LYON = (45.7640, 4.8357)
CORK = (51.89797, -8.47061)
# Two sourced civil mean times far from their zones' named places: Paris's
# mean time at Lyon in 1900 and Dublin's at Cork in 1910.
CIVIL_CASES = [(LYON, "Europe/Paris", "1900-05-10", "PMT"), (CORK, "Europe/Dublin", "1910-05-10", "DMT")]


def _moment(date):
    return tuple(int(part) for part in date.split("-")) + (12, 0, 0)


@pytest.mark.parametrize("point, zone, date, abbreviation", CIVIL_CASES, ids=("Lyon-1900", "Cork-1910"))
def test_a_civil_mean_time_far_from_its_named_place_carries_nothing(tz, zone1970, point, zone, date, abbreviation):
    state = tz.named_zone_state(zone, *_moment(date), latitude=point[0], longitude=point[1])
    assert state.get("civil_mean_time") is True and state["abbreviation"] == abbreviation, state
    assert tz._distance_km(*point, *zone1970[zone]) > 150, "the premise: far from the named place"
    assert tz.zone_record_place(*point, zone, _moment(date)) is None


@pytest.mark.parametrize("point, zone, date, place", [
    (LYON, "Europe/Paris", "1925-05-10", "Paris"), (CORK, "Europe/Dublin", "1920-05-10", "Dublin"),
    (MUNICH, "Europe/Berlin", "1965-05-10", "Berlin")], ids=("Lyon-1925", "Cork-1920", "Munich-1965"))
def test_a_standard_time_cast_far_from_its_named_place_still_carries_it(tz, point, zone, date, place):
    """After a civil mean time's window, and in a zone that never had one,
    the condition holds as before: only the civil mean time is excluded."""
    state = tz.named_zone_state(zone, *_moment(date), latitude=point[0], longitude=point[1])
    assert "civil_mean_time" not in state, state
    assert tz.zone_record_place(*point, zone, _moment(date)) == place


def test_the_exclusion_reads_the_state_not_the_year(tz):
    """A pre-1911 Standard-time cast that is no civil mean time keeps the
    caution: Minneapolis in 1900 under Chicago's CST, before the place's
    own clocks begin."""
    moment = (1900, 5, 10, 12, 0, 0)
    assert not tz._place_clocks_at("America/Chicago", 1900, *MINNEAPOLIS), "the premise: no clocks of its own then"
    state = tz.named_zone_state("America/Chicago", *moment, latitude=MINNEAPOLIS[0], longitude=MINNEAPOLIS[1])
    assert state["abbreviation"] == "CST" and "civil_mean_time" not in state, state
    assert tz.zone_record_place(*MINNEAPOLIS, "America/Chicago", moment) == "Chicago"


@pytest.mark.parametrize("point, zone, date, abbreviation", CIVIL_CASES, ids=("Lyon-1900", "Cork-1910"))
def test_the_box_and_the_reports_of_a_civil_mean_time_carry_nothing(point, zone, date, abbreviation, engine):
    at = _app(point, date).run(timeout=300)
    assert_no_exception(at, date)
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1 and box[0].startswith(f"**{zone}** · UTC offset"), box
    assert f"{abbreviation}, a named mean time, was then the civil clock across this area" in box[0], box
    texts = _all_text(at)
    assert texts, "the premise: the run printed text"
    assert not any("this zone's record is" in text for text in texts), texts
    markdown, html = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    assert f"| Time zone | {zone} |" in markdown
    assert "this zone's record is" not in markdown and "Time zone note" not in markdown
    assert "this zone&" not in html and "this zone's record is" not in html and "Time zone note" not in html


def test_the_box_and_the_reports_after_the_window_still_carry_it(engine):
    sentence = SENTENCE.replace("Berlin's", "Paris's")
    at = _app(LYON, "1925-05-10").run(timeout=300)
    assert_no_exception(at, "Lyon 1925")
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1 and box[0].split("  \n")[1] == sentence, box
    assert at.session_state["_analysis_markdown"].count(sentence) == 1
    assert at.session_state["_analysis_html"].count(engine["_esc_text"](sentence)) == 1


# --- the table of named places, read all or nothing ----------------------------------

def test_a_read_that_fails_part_way_leaves_the_table_empty(tz, monkeypatch):
    """A failure mid-parse leaves nothing behind, so a second thread that
    finds the table filled has the whole of it."""
    monkeypatch.setattr(tz, "_ZONE1970_PLACES", {})
    real, calls = tz._iso6709_degrees, []

    def failing(text, digits):
        calls.append(text)
        if len(calls) > 100:
            raise RuntimeError("planted")
        return real(text, digits)
    monkeypatch.setattr(tz, "_iso6709_degrees", failing)
    with pytest.raises(RuntimeError, match="planted"):
        tz._zone1970_places()
    assert len(calls) == 101, "the premise: the failure came part-way through"
    assert tz._ZONE1970_PLACES == {}
    monkeypatch.setattr(tz, "_iso6709_degrees", real)
    places = tz._zone1970_places()
    assert len(places) > 300 and places is tz._ZONE1970_PLACES
