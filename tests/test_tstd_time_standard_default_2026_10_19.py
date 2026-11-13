"""The Time standard box follows the date and the place until it is picked.

Until the person picks a standard by hand, the sidebar takes Standard time
(named zone) wherever the place's zone casts the date, and LMT where the date
is before the zone's record keeps standard time there; any other refusal of
the zone (a skipped or repeated hour, a linked zone, a place whose clock the
sources leave open) keeps the named zone, with its own sentence. A standard
picked by hand stays, a loaded chart keeps its own (one saved before the
standard was stored holds none, and the box follows its date and place), Here
& Now keeps its own, and a new chart (the example) follows again. The example nativity, Florence
1240, opens on LMT and is cast as before.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from pathlib import Path

import pytest

import engine
from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

LMT, STANDARD, MANUAL = engine.TIME_STANDARD_OPTIONS
NEW_CHART = "-- New Chart --"
FLORENCE_ATLAS = (43.77925, 11.24626)          # the atlas's Florence, the city box's first match
NEW_YORK = (40.71427, -74.00597)
ACCRA = (5.55602, -0.1969)                     # Africa/Accra, kept only as a link before 1970
KASHGAR = (39.46718, 75.98675)                 # a place whose clock the sources leave open


def _standard(at):
    return at.session_state["time_standard_key"]


def _box(at):
    """What the box under the selectbox says: its info or its error."""
    return "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])


def _ut(at):
    calc = [df.value for df in at.main.dataframe if "Quantity" in df.value.columns]
    assert calc, "no Calculation table"
    return str(calc[0][calc[0]["Quantity"] == "Universal time"].iloc[0]["Value"])


def _set_date(at, text):
    at.sidebar.text_input(key="date_input_key").set_value(text).run()
    assert_no_exception(at, f"date {text}")
    return at


def _set_time(at, hh, mm):
    at.sidebar.time_input(key="time_input_key").set_value(time(hh, mm)).run()
    assert_no_exception(at, f"time {hh}:{mm}")
    return at


def _pick(at, standard):
    at.sidebar.selectbox(key="time_standard_key").select(standard).run()
    assert_no_exception(at, f"pick {standard}")
    return at


def _set_coords(at, lat, lon):
    at.sidebar.number_input(key="manual_lat_key").set_value(lat)
    at.sidebar.number_input(key="manual_lon_key").set_value(lon).run()
    assert_no_exception(at, f"coords {lat}, {lon}")
    return at


def _florence_by_city(page="chart"):
    """The example with Florence found through the atlas by its name."""
    at = make_app(page=page)
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "Florence"
    at.run()
    assert_no_exception(at, "open")
    return at


def _hand_coords(page="chart"):
    """The example with the place entered as coordinates (the harness's own
    Florence pair), no city."""
    at = make_app(page=page).run()
    assert_no_exception(at, "open")
    return at


# --- A fresh session ---------------------------------------------------------

def test_a_fresh_session_opens_on_the_example_at_lmt_and_casts_it_as_before():
    sync_engine_to_environment()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
    assert_no_exception(at, "fresh")
    assert at.session_state["date_input_key"] == "1240-05-23"
    assert _standard(at) == LMT
    box = _box(at)
    assert "**Exact LMT** · UTC offset +00:44:59" in box, box
    assert "UT 1240-05-23 13:45:01" in box, box
    assert _ut(at).startswith("1240-05-23 13:45:01"), _ut(at)
    assert not at.sidebar.error, box


# --- The box follows the date ------------------------------------------------

def test_a_modern_date_at_florence_takes_the_zone_and_back_to_1240_takes_lmt():
    at = _florence_by_city()
    assert _standard(at) == LMT
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    box = _box(at)
    assert "**Europe/Rome** · UTC offset +02:00 (CEST)" in box, box
    assert _ut(at).startswith("1990-06-15 10:00:00"), _ut(at)
    _set_date(at, "1240-05-23")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at), _box(at)
    assert not at.sidebar.error, _box(at)


def test_coordinates_entered_by_hand_follow_as_a_city_does():
    at = _hand_coords()
    assert _standard(at) == LMT
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    assert "**Europe/Rome** · UTC offset +02:00 (CEST)" in _box(at), _box(at)
    assert _ut(at).startswith("1990-06-15 10:00:00"), _ut(at)
    _set_date(at, "1240-05-23")
    assert _standard(at) == LMT


def test_a_date_crossing_new_yorks_first_standard_time_moves_the_box_at_the_line():
    # The record keeps local mean time until 1883-11-18 12:03:58 local, when
    # the clocks were set back to EST: 11:59 is before the line, 12:02 is
    # the repeated stretch, 12:05 is EST.
    at = _hand_coords()
    _set_time(at, 11, 59)
    _set_date(at, "1883-11-18")
    _set_coords(at, *NEW_YORK)
    assert _standard(at) == LMT, _box(at)
    assert "**Exact LMT**" in _box(at), _box(at)
    _set_time(at, 12, 5)
    assert _standard(at) == STANDARD
    assert "**America/New_York** · UTC offset -05:00 (EST)" in _box(at), _box(at)
    _set_time(at, 11, 59)
    assert _standard(at) == LMT
    # The repeated stretch keeps the zone, with its own sentence.
    _set_time(at, 12, 2)
    assert _standard(at) == STANDARD
    assert ("At **12:03:58 on 1883-11-18** the clocks in the America/New_York time zone moved back 3 minutes "
            "58 seconds, from local mean time (UTC-04:56:02) to EST (UTC-05:00), so **12:02** occurred twice"
            in _box(at)), _box(at)


def test_a_change_of_place_reaches_the_box_on_the_same_run():
    at = _florence_by_city()
    _set_time(at, 12, 5)
    _set_date(at, "1883-11-18")
    # Florence then kept Rome's mean time, which is not its civil clock: LMT.
    assert _standard(at) == LMT, _box(at)
    at.sidebar.text_input(key="location_input_key").set_value("New York City").run()
    assert_no_exception(at, "New York")
    assert _standard(at) == STANDARD
    assert "**America/New_York** · UTC offset -05:00 (EST)" in _box(at), _box(at)
    assert _ut(at).startswith("1883-11-18 17:05:00"), _ut(at)


# --- Refusals that keep the zone ---------------------------------------------

def test_the_skipped_hour_keeps_the_zone_with_its_refusal():
    at = _florence_by_city()
    _set_time(at, 2, 30)
    _set_date(at, "1990-03-25")
    assert _standard(at) == STANDARD
    assert ("At **02:00 on 1990-03-25** the clocks in the Europe/Rome time zone moved forward one hour, from CET "
            "(UTC+01:00) to CEST (UTC+02:00), so **02:30** never occurred there" in _box(at)), _box(at)
    assert at.sidebar.error


def test_a_linked_zone_before_1970_keeps_the_zone_with_its_refusal():
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1960-06-15")
    assert _standard(at) == STANDARD
    _set_coords(at, *ACCRA)
    assert _standard(at) == STANDARD
    assert "only as a link to Africa/Abidjan" in _box(at), _box(at)


def test_a_place_whose_clock_the_sources_leave_open_keeps_the_zone_with_its_refusal():
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "2026-01-15")
    _set_coords(at, *KASHGAR)
    assert _standard(at) == STANDARD
    assert f"Choose {MANUAL} and enter the offset of the clock" in _box(at), _box(at)


# --- What counts as picked, and what ends it ---------------------------------

def test_lmt_picked_by_hand_stays_through_a_modern_date():
    at = _florence_by_city()
    _pick(at, MANUAL)
    _pick(at, LMT)
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at), _box(at)


def test_the_zone_picked_by_hand_after_following_it_stays_through_1240():
    # The pick is the person's even where it names the standard the box
    # had followed to: the next date does not undo it.
    at = _florence_by_city()
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    _pick(at, LMT)
    _pick(at, STANDARD)
    _set_date(at, "1240-05-23")
    assert _standard(at) == STANDARD
    assert "is before Europe/Rome kept any standard time" in _box(at), _box(at)


def test_a_manual_offset_picked_stays():
    at = _florence_by_city()
    _pick(at, MANUAL)
    _set_date(at, "1990-06-15")
    assert _standard(at) == MANUAL
    _set_date(at, "1240-05-23")
    assert _standard(at) == MANUAL


def _store(tmp_path, monkeypatch, records):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(records))


def _record(date, standard=None):
    record = {"date_string": date, "time_string": "12:00:00", "location_query": "Florence, 16 (IT)",
              "lat": FLORENCE_ATLAS[0], "lon": FLORENCE_ATLAS[1]}
    if standard is not None:
        record["time_standard"] = standard
    return record


def _load(at, name):
    at.sidebar.selectbox(key="chart_picker").select(name).run()
    assert_no_exception(at, f"load {name}")
    return at


def test_a_loaded_chart_keeps_its_own_standard_whatever_the_date(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, {"Modern at LMT": _record("1990-06-15", LMT),
                                   "Modern zoned": _record("1990-06-15", STANDARD)})
    at = _hand_coords()
    assert _standard(at) == LMT
    _load(at, "Modern at LMT")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at), _box(at)
    _set_date(at, "1991-06-15")
    assert _standard(at) == LMT
    _load(at, "Modern zoned")
    assert _standard(at) == STANDARD
    _set_date(at, "1240-05-23")
    assert _standard(at) == STANDARD
    assert "is before Europe/Rome kept any standard time" in _box(at), _box(at)


LEGACY_WARNING = "was saved before the time standard was stored with a chart. Check it, then save the chart again."


def _legacy_warned(at, name):
    return any(w.value == f"'{name}' {LEGACY_WARNING}" for w in at.sidebar.warning)


def test_a_chart_saved_before_the_standard_was_stored_is_followed_from_a_session_followed_the_other_way(
        tmp_path, monkeypatch):
    # Such a record holds no pick, so its load is not one: the box follows
    # the loaded chart's own date and place, whatever it held before.
    _store(tmp_path, monkeypatch, {"Old 1240": _record("1240-05-23"), "Old 1990": _record("1990-06-15")})
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    _load(at, "Old 1240")
    assert _standard(at) == LMT, _box(at)
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    assert _legacy_warned(at, "Old 1240"), [w.value for w in at.sidebar.warning]
    # From the example at LMT, the modern record takes the zone.
    at = _hand_coords()
    assert _standard(at) == LMT
    _load(at, "Old 1990")
    assert _standard(at) == STANDARD, _box(at)
    assert "**Europe/Rome** · UTC offset +02:00 (CEST)" in _box(at), _box(at)
    assert _ut(at).startswith("1990-06-15 10:00:00"), _ut(at)
    assert _legacy_warned(at, "Old 1990"), [w.value for w in at.sidebar.warning]
    # Not a pick: the box goes on following the date.
    _set_date(at, "1240-05-23")
    assert _standard(at) == LMT, _box(at)


def test_a_chart_saved_before_the_standard_was_stored_is_followed_after_a_pick_by_hand(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, {"Old 1240": _record("1240-05-23"), "Old 1990": _record("1990-06-15")})
    at = _hand_coords()
    _pick(at, MANUAL)
    _load(at, "Old 1240")
    assert _standard(at) == LMT, _box(at)
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    at = _hand_coords()
    _pick(at, MANUAL)
    _pick(at, LMT)
    _load(at, "Old 1990")
    assert _standard(at) == STANDARD, _box(at)
    assert "+02:00 (CEST)" in _box(at), _box(at)
    assert _legacy_warned(at, "Old 1990"), [w.value for w in at.sidebar.warning]


def _launch_on(tmp_path, monkeypatch, records, last):
    _store(tmp_path, monkeypatch, records)
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    prefs = Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "preferences.json"
    prefs.write_text(json.dumps({"last_chart": last}))
    sync_engine_to_environment()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
    assert_no_exception(at, "launch")
    return at


def test_a_chart_saved_before_the_standard_was_stored_restored_at_launch_is_followed(tmp_path, monkeypatch):
    at = _launch_on(tmp_path, monkeypatch, {"Old 1990": _record("1990-06-15")}, "Old 1990")
    assert at.session_state["date_input_key"] == "1990-06-15"
    assert _standard(at) == STANDARD, _box(at)
    assert "**Europe/Rome** · UTC offset +02:00 (CEST)" in _box(at), _box(at)
    assert _legacy_warned(at, "Old 1990"), [w.value for w in at.sidebar.warning]
    _set_date(at, "1240-05-23")
    assert _standard(at) == LMT, _box(at)


def test_the_chart_restored_at_launch_is_a_load(tmp_path, monkeypatch):
    at = _launch_on(tmp_path, monkeypatch, {"Modern at LMT": _record("1990-06-15", LMT)}, "Modern at LMT")
    assert at.session_state["date_input_key"] == "1990-06-15"
    assert _standard(at) == LMT
    _set_date(at, "1991-06-15")
    assert _standard(at) == LMT


def test_here_and_now_keeps_its_own_standard(monkeypatch):
    at = make_app(page="chart")
    at.session_state["home_place"] = {"label": "Florence", "lat": FLORENCE_ATLAS[0], "lon": FLORENCE_ATLAS[1]}
    at.run()
    # The box has followed to the zone, the standard Here & Now writes, so
    # only its pick keeps it there when the date moves.
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    monkeypatch.setattr(engine, "now_utc", lambda: datetime(2026, 9, 17, 12, 34, 56, tzinfo=timezone.utc))
    at.sidebar.button(key="_here_and_now").click().run()
    assert_no_exception(at, "here and now")
    assert _standard(at) == STANDARD
    assert at.session_state["date_input_key"] == "2026-09-17"
    _set_date(at, "1240-05-23")
    assert _standard(at) == STANDARD
    assert "is before Europe/Rome kept any standard time" in _box(at), _box(at)


def test_a_new_chart_follows_again(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, {"Modern at LMT": _record("1990-06-15", LMT)})
    at = _hand_coords()
    _load(at, "Modern at LMT")
    assert _standard(at) == LMT
    _load(at, NEW_CHART)
    assert at.session_state["date_input_key"] == "1240-05-23"
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at), _box(at)
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    assert "+02:00 (CEST)" in _box(at), _box(at)


def test_a_new_chart_follows_again_after_the_box_had_followed_to_the_zone(tmp_path, monkeypatch):
    # The reset marks the example's standard as the follow's own: without
    # that mark, the box left holding the zone (followed, or kept under a
    # pick) would read the example's LMT as a pick and keep it.
    _store(tmp_path, monkeypatch, {"Modern at LMT": _record("1990-06-15", LMT)})
    for pick in (None, MANUAL):
        at = _hand_coords()
        _set_time(at, 12, 0)
        _set_date(at, "1990-06-15")
        assert _standard(at) == STANDARD
        if pick:
            _pick(at, pick)
        _load(at, "Modern at LMT")
        assert _standard(at) == LMT
        _load(at, NEW_CHART)
        assert at.session_state["date_input_key"] == "1240-05-23"
        assert _standard(at) == LMT
        _set_time(at, 12, 0)
        _set_date(at, "1990-06-15")
        assert _standard(at) == STANDARD, (pick, _box(at))
        assert "+02:00 (CEST)" in _box(at), _box(at)


def test_a_standard_seeded_into_the_session_is_kept():
    # A standard the follow did not put in the box (the harness seeds one
    # before the first run) is a pick.
    at = make_app(date="1990-06-15", page="chart")
    at.session_state["time_standard_key"] = LMT
    at.run()
    assert_no_exception(at, "seeded")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at), _box(at)
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["time_standard_key"] = STANDARD
    at.run()
    assert _standard(at) == STANDARD
    assert "is before Europe/Rome kept any standard time" in _box(at), _box(at)


# --- Refusals raised whatever the date ---------------------------------------
# A zone kept only as a link is refused for every date before 1970, a point
# with no zone and a place the sources leave unsettled at every date: the
# date is read against the record behind them.

AMSTERDAM = (52.374, 4.8897)                   # Europe/Amsterdam, its own stretches from 1909
BRATISLAVA = (48.1486, 17.1077)                # Europe/Bratislava, its own stretches from 1946
LONGWA = (26.66172, 95.22004)                  # listed: no source settles its clock
AT_SEA = (1.0, 5.0)


def test_a_linked_zone_before_it_keeps_standard_time_takes_lmt():
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1700-06-15")
    _set_coords(at, *AMSTERDAM)
    assert _standard(at) == LMT, _box(at)
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    _set_coords(at, *ACCRA)
    _set_date(at, "1880-06-15")
    assert _standard(at) == LMT, _box(at)
    # From the record it links to keeping standard time, the zone and its
    # refusal: Accra in 1930 and 1960.
    _set_date(at, "1930-06-15")
    assert _standard(at) == STANDARD
    assert "only as a link to Africa/Abidjan" in _box(at), _box(at)


def test_a_linked_zone_whose_own_stretches_start_late_keeps_the_zone_once_its_link_keeps_standard_time():
    # Bratislava's own stretches begin in 1946; Prague's record keeps
    # standard time long before, so 1930 is the zone with its refusal, not
    # a modern date cast at LMT.
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1930-06-15")
    _set_coords(at, *BRATISLAVA)
    assert _standard(at) == STANDARD
    assert "only inside the stretches it takes from the sources" in _box(at), _box(at)
    _set_date(at, "1850-06-15")
    assert _standard(at) == LMT, _box(at)


def test_a_point_with_no_zone_leaves_the_box_as_it_is():
    at = _hand_coords()
    _set_coords(at, *AT_SEA)
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    _set_coords(at, *FLORENCE_ATLAS)
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    _set_coords(at, *AT_SEA)
    assert _standard(at) == STANDARD
    assert "no standard-time zone at these coordinates" in _box(at), _box(at)
    _set_date(at, "1240-05-23")
    assert _standard(at) == STANDARD


def test_an_unsettled_place_takes_lmt_only_where_neither_clock_places_the_moment():
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1850-06-15")
    _set_coords(at, *LONGWA)
    assert _standard(at) == LMT, _box(at)
    assert not at.sidebar.error, _box(at)
    _set_date(at, "1990-06-15")
    assert _standard(at) == STANDARD
    assert "do not settle which clock this place keeps" in _box(at), _box(at)


def test_a_place_the_zone_boundaries_give_no_zone_leaves_the_box_as_it_is(monkeypatch):
    from timezonefinder import TimezoneFinder
    monkeypatch.setattr(TimezoneFinder, "timezone_at", lambda self, **kw: None)
    at = _hand_coords()
    assert _standard(at) == LMT
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    _pick(at, STANDARD)
    assert "no standard-time zone at these coordinates" in _box(at), _box(at)


@pytest.mark.parametrize("package", ["tzdata", "timezonefinder-data"])
def test_zone_data_that_is_not_the_apps_leaves_the_box_as_it_is(monkeypatch, package):
    # A changed zone package is refused for the process (ShippedDataChanged):
    # the follow reads no zone and keeps no answer for it, and the page
    # raises nothing; the zone picked by hand says the zone data's sentence.
    import time_zones as tz
    monkeypatch.setitem(tz._ZONE_PACKAGES_SEEN, package, f"the {package} package's data files are not those ...")
    at = _hand_coords()
    assert _standard(at) == LMT
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    assert _standard(at) == LMT
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)
    assert "_time_standard_follow_memo" not in at.session_state
    _pick(at, STANDARD)
    assert "The time-zone data is not the one this app supplies" in _box(at), _box(at)


# --- Each refusal kind the follow reads --------------------------------------
# The kind each case raises is asserted first, so a pin cannot pass on a case
# that no longer reaches its kind.

TRENTO = (46.0679, 11.1211)
STOCKHOLM = (59.3293, 18.0686)
LAGOS = (6.4541, 3.3947)
PALERMO = (38.1157, 13.3615)
VENICE = (45.4408, 12.3155)


def _refusal_kind(place, date, hhmm):
    from timezonefinder import TimezoneFinder
    moment = (*(int(part) for part in date.split("-")), *hhmm, 0)
    try:
        zone = engine.place_zone(*place, TimezoneFinder(), moment)
        engine.named_zone_state(zone, *moment, latitude=place[0], longitude=place[1])
    except engine.NamedZoneRefusal as refusal:
        return refusal.kind
    return None


@pytest.mark.parametrize("kind, place, date, hhmm, said", [
    ("outside_clock", TRENTO, "1900-06-15", (12, 0), "notes speak of Italy's clocks and say nothing of what"),
    ("disputed", STOCKHOLM, "1916-09-30", (23, 30),
     "falls where the sources disagree on when Europe/Stockholm's clocks were turned back"),
])
def test_a_refusal_of_a_date_after_standard_time_keeps_the_zone_with_its_sentence(kind, place, date, hhmm, said):
    assert _refusal_kind(place, date, hhmm) == kind
    at = _hand_coords()
    _set_time(at, *hhmm)
    _set_coords(at, *place)
    assert _standard(at) == LMT
    _set_date(at, date)
    assert _standard(at) == STANDARD, _box(at)
    assert said in _box(at) and at.sidebar.error, _box(at)


@pytest.mark.parametrize("kind, place, date", [
    ("julian", FLORENCE_ATLAS, "1300-02-29"),
    ("later_lmt", LAGOS, "1910-06-15"),
    ("mean_time_exception", PALERMO, "1890-06-15"),
    ("mean_time_city", VENICE, "1870-06-15"),
    ("mean_time_outside", TRENTO, "1890-06-15"),
])
def test_a_date_before_standard_time_takes_lmt_from_a_box_followed_to_the_zone(kind, place, date):
    assert _refusal_kind(place, date, (12, 0)) == kind
    at = _hand_coords()
    _set_time(at, 12, 0)
    _set_date(at, "1990-06-15")
    _set_coords(at, *place)
    assert _standard(at) == STANDARD, _box(at)
    _set_date(at, date)
    assert _standard(at) == LMT, _box(at)
    assert "**Exact LMT**" in _box(at) and not at.sidebar.error, _box(at)


# --- The follow's cost ---------------------------------------------------------

def test_a_rerun_that_moves_neither_date_nor_place_builds_no_finder(monkeypatch):
    # The finder takes a fifth of a second to build; a run cast at LMT
    # builds none for the cast, and the follow reads the zone again only
    # when the date or the place has moved.
    from timezonefinder import TimezoneFinder
    built = []
    real_init = TimezoneFinder.__init__

    def counting_init(self, *args, **kwargs):
        built.append(1)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(TimezoneFinder, "__init__", counting_init)
    at = _hand_coords()
    assert _standard(at) == LMT
    assert len(built) == 1, built
    at.run()
    assert_no_exception(at, "rerun")
    assert len(built) == 1, built
    _set_date(at, "1241-05-23")
    assert len(built) == 2, built
    assert _standard(at) == LMT
