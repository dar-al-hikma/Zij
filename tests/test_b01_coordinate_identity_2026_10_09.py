"""A saved chart's coordinates, compared and carried exactly (ruling 145,
B-01 and B-02 of the third outside pass).

The place is the reproduction's: 40 N, 102.05177 W on 2026-07-15 at 14:30
under the named zone. A line between America/Chicago and America/Denver runs
between -102.05177 (Chicago) and -102.0518 (Denver), and both print as
-102.0518 at four places. Under Chicago the chart is cast at 19:30 UT, under
Denver at 20:30 UT.

B-01: the record holds the pair the chart was cast from, at full precision,
and an edit below the fourth decimal that moves the chart across the line is
an edit: the strip says so, Save asks to replace, and a fresh load casts the
edited chart. The zone and offset each side is cast with are compared too.

B-02: switching the coordinate fields off and on again is a change of input
method, not of place: the chart, its zone and its offset stay as they were.

Every app run here uses its own XDG directory (tmp_path).
"""
import json
import os
from datetime import time
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app

LAT = 40.0
CHICAGO_LON = -102.05177   # America/Chicago, CDT, 19:30 UT
DENVER_LON = -102.0518     # America/Denver, MDT, 20:30 UT
# The line itself lies at about -102.051778: -102.05178 is Denver's side, and
# also prints as -102.0518.
DENVER_NEAR = -102.05178
NAMED = "Standard time (named zone)"
CHICAGO = ("**America/Chicago** · UTC offset -05:00 (CDT)", "UT 2026-07-15 19:30:00")
DENVER = ("**America/Denver** · UTC offset -06:00 (MDT)", "UT 2026-07-15 20:30:00")


def _store_path():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"


def _stored():
    return json.loads(_store_path().read_text())


def _app(lon=CHICAGO_LON, standard=NAMED, offset=None, manual=True, box=None):
    at = make_app(date="2026-07-15", page="chart")
    at.session_state["time_input_key"] = time(14, 30)
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    at.session_state["manual_lat_key"] = LAT
    at.session_state["manual_lon_key"] = lon
    if not manual:
        at.session_state["manual_coords_key"] = False
        at.session_state["location_input_key"] = box
    return at.run()


def _zone(at):
    """The time-standard box: the zone, its offset and the UT moment cast."""
    return "\n".join(n.value for n in at.sidebar.info if "UTC offset" in n.value)


def _casts(at, where):
    text = _zone(at)
    return all(part in text for part in where)


def _strip(at):
    for caption in at.main.caption:
        if " · " in caption.value:
            return caption.value.split(" · ")[0]
    return ""


def _edited_caption(at):
    return "Edited since it was saved." in [c.value for c in at.sidebar.caption]


def _sidebar_says(at):
    return " ".join(w.value for kind in (at.sidebar.info, at.sidebar.warning, at.sidebar.success)
                    for w in kind)


def _save_as(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    return at


def _button(at, label):
    hits = [b for b in at.sidebar.button if b.label == label]
    assert len(hits) == 1, [b.label for b in at.sidebar.button]
    return hits[0]


def _load(name):
    """A fresh session opening the record `name` from the store."""
    fresh = make_app(date="1240-05-23", page="chart").run()
    fresh.sidebar.selectbox(key="chart_picker").select(name).run()
    assert_no_exception(fresh, "the load")
    return fresh


# --- B-01 -----------------------------------------------------------------

@pytest.mark.parametrize("saved, saved_zone, edited, edited_zone", [
    (CHICAGO_LON, CHICAGO, DENVER_LON, DENVER),
    (DENVER_NEAR, DENVER, CHICAGO_LON, CHICAGO),
], ids=["chicago-to-denver", "denver-to-chicago"])
def test_b01_a_zone_line_edit_is_modified_saved_and_loaded(tmp_path, monkeypatch, saved, saved_zone, edited,
                                                         edited_zone):
    """The reproduction's case: -102.05177 saved, -102.0518 typed; and the
    line crossed the other way. At 4563036 the strip named the record
    unmodified, Save said "already saved as it is" and wrote nothing, and a
    fresh load cast the chart saved."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app(lon=saved)
    assert _casts(at, saved_zone), _zone(at)
    _save_as(at, "Boundary saved")
    assert_no_exception(at, "the save")
    assert _strip(at) == "Boundary saved"
    assert _stored()["Boundary saved"]["lon"] == saved

    at.sidebar.number_input(key="manual_lon_key").set_value(edited).run()
    assert _casts(at, edited_zone), _zone(at)
    assert _strip(at) == "Boundary saved (modified)"
    assert _edited_caption(at)

    _save_as(at, "Boundary saved")
    assert "already saved as it is" not in _sidebar_says(at)
    assert "'Boundary saved' exists. Replace it?" in [w.value for w in at.sidebar.warning]
    _button(at, "Replace").click().run()
    assert_no_exception(at, "the replace")
    assert _stored()["Boundary saved"]["lon"] == edited
    assert _strip(at) == "Boundary saved"

    fresh = _load("Boundary saved")
    assert fresh.session_state["manual_lon_key"] == edited
    assert _casts(fresh, edited_zone), _zone(fresh)
    assert _strip(fresh) == "Boundary saved"


def test_b01_a_latitude_edit_below_the_fourth_place_is_an_edit(tmp_path, monkeypatch):
    """Latitude is compared exactly too (no zone line needed: the record
    holds a different place)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app()
    _save_as(at, "Latitude")
    assert _strip(at) == "Latitude"
    at.sidebar.number_input(key="manual_lat_key").set_value(40.00003).run()
    assert _strip(at) == "Latitude (modified)"
    _save_as(at, "Latitude")
    assert "already saved as it is" not in _sidebar_says(at)
    assert "'Latitude' exists. Replace it?" in [w.value for w in at.sidebar.warning]


def test_b01_an_edit_that_changes_nothing_is_unchanged(tmp_path, monkeypatch):
    """The same pair typed again (40.000 is 40.0, -102.051770 is -102.05177)
    is the record: no "(modified)", and Save says it is already saved."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app()
    _save_as(at, "Same place")
    at.sidebar.number_input(key="manual_lat_key").set_value(float("40.000")).run()
    at.sidebar.number_input(key="manual_lon_key").set_value(float("-102.051770")).run()
    assert _casts(at, CHICAGO), _zone(at)
    assert _strip(at) == "Same place"
    assert not _edited_caption(at)
    _save_as(at, "Same place")
    assert "'Same place' is already saved as it is." in _sidebar_says(at)


def test_b01_the_cast_offset_is_compared_where_the_field_rounds(tmp_path, monkeypatch):
    """The offset each side is cast with is compared exactly: a manual
    offset that differs past the fourth decimal of an hour casts another
    moment, and the record is called edited for it. (The field itself is
    still compared to four places; the cast offset is what tells them
    apart.)"""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app(standard="Manual UTC offset", offset=-5.0)
    _save_as(at, "Offset")
    assert _strip(at) == "Offset"
    at.sidebar.number_input(key="utc_offset_key").set_value(-5.00001).run()
    assert_no_exception(at, "the offset edit")
    assert _strip(at) == "Offset (modified)"
    at.sidebar.number_input(key="utc_offset_key").set_value(-5.0).run()
    assert _strip(at) == "Offset"


def test_b01_an_older_record_still_compares_as_before(tmp_path, monkeypatch):
    """A record written before this change, in the shapes the store has held:
    no readings and no stamp, the time standard under its old label, an
    empty place name, the latitude a whole number and the longitude text.
    It opens unmodified, at the place it holds; an edit of it is an edit."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    _store_path().write_text(json.dumps({"Old record": {
        "date_string": "2026-07-15", "time_string": "14:30:00", "time_standard": "Standard time (pytz)",
        "utc_offset": None, "location_query": "", "lat": 40, "lon": "-102.05177"}}))
    at = _load("Old record")
    assert at.session_state["manual_lon_key"] == CHICAGO_LON
    assert _casts(at, CHICAGO), _zone(at)
    assert _strip(at) == "Old record"
    assert not _edited_caption(at)

    at.sidebar.number_input(key="manual_lon_key").set_value(DENVER_LON).run()
    assert _casts(at, DENVER), _zone(at)
    assert _strip(at) == "Old record (modified)"


# --- B-02 -----------------------------------------------------------------

@pytest.mark.parametrize("lon, where", [(CHICAGO_LON, CHICAGO), (DENVER_NEAR, DENVER)],
                         ids=["chicago-side", "denver-side"])
def test_b02_fields_off_then_on_keep_the_chart(tmp_path, monkeypatch, lon, where):
    """At 4563036 switching the fields off wrote '40.0000, -102.0518' into
    the box and cast it: America/Denver, 20:30 UT; on again kept it. From
    Denver's side the four places stay in Denver, but the fields came back
    holding -102.0518, a place 2e-5 degrees from the one switched off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app(lon=lon)
    assert _casts(at, where), _zone(at)

    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert_no_exception(at, "switching off")
    assert at.session_state["location_input_key"] == "40.0000, -102.0518"
    assert _casts(at, where), _zone(at)
    at.run()
    assert _casts(at, where), _zone(at)

    at.sidebar.toggle(key="manual_coords_key").set_value(True).run()
    assert_no_exception(at, "switching on")
    assert at.session_state["manual_lat_key"] == LAT
    assert at.session_state["manual_lon_key"] == lon
    assert _casts(at, where), _zone(at)
    at.run()
    assert _casts(at, where), _zone(at)


def test_b02_fields_on_then_off_keep_the_chart(tmp_path, monkeypatch):
    """The other way round: the place typed into the box at full precision,
    the fields switched on (they take the full pair) and off again."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app(manual=False, box="40, -102.05177")
    assert _casts(at, CHICAGO), _zone(at)

    at.sidebar.toggle(key="manual_coords_key").set_value(True).run()
    assert at.session_state["manual_lon_key"] == CHICAGO_LON
    assert _casts(at, CHICAGO), _zone(at)

    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert_no_exception(at, "switching off")
    assert _casts(at, CHICAGO), _zone(at)
    at.run()
    assert _casts(at, CHICAGO), _zone(at)


def test_b02_a_saved_record_is_unmodified_after_the_round_trip(tmp_path, monkeypatch):
    """With B-01: the round trip neither moves a loaded record's chart nor
    has it called edited, and Save still finds it saved as it is."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app()
    _save_as(at, "Round trip")
    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert _strip(at) == "Round trip"
    at.sidebar.toggle(key="manual_coords_key").set_value(True).run()
    assert _strip(at) == "Round trip"
    assert _casts(at, CHICAGO), _zone(at)
    _save_as(at, "Round trip")
    assert "'Round trip' is already saved as it is." in _sidebar_says(at)


def test_b02_a_box_edited_after_the_switch_is_a_new_place(tmp_path, monkeypatch):
    """The kept pair is the box's only while the box holds the text written
    for it. The same rounded pair typed with a trailing zero is a new text,
    and the place it states (-102.0518, Denver) is cast; the full pair
    typed back is Chicago again, trailing zeros or not."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app()
    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert _casts(at, CHICAGO), _zone(at)
    at.sidebar.text_input(key="location_input_key").set_value("40.0000, -102.05180").run()
    assert _casts(at, DENVER), _zone(at)
    at.sidebar.text_input(key="location_input_key").set_value("40.0000, -102.0518").run()
    assert _casts(at, DENVER), _zone(at)
    at.sidebar.text_input(key="location_input_key").set_value("40.00000, -102.051770").run()
    assert _casts(at, CHICAGO), _zone(at)


# --- Fix round 1 of the blind check ---------------------------------------

def test_b01_a_longitude_edit_inside_one_zone_is_an_edit(tmp_path, monkeypatch):
    """The check's 5c: a longitude edit below the fourth place that crosses
    no zone line (-102.06001 to -102.06004, Denver both) is an edit on the
    coordinate alone: modified, and Save asks to replace and writes it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _app(lon=-102.06001)
    assert _casts(at, DENVER), _zone(at)
    _save_as(at, "In zone")
    assert _strip(at) == "In zone"
    at.sidebar.number_input(key="manual_lon_key").set_value(-102.06004).run()
    assert _casts(at, DENVER), _zone(at)
    assert _strip(at) == "In zone (modified)"
    assert _edited_caption(at)
    _save_as(at, "In zone")
    assert "already saved as it is" not in _sidebar_says(at)
    assert "'In zone' exists. Replace it?" in [w.value for w in at.sidebar.warning]
    _button(at, "Replace").click().run()
    assert _stored()["In zone"]["lon"] == -102.06004


def test_b02_a_loaded_record_is_cast_from_its_own_place_text(tmp_path, monkeypatch):
    """The check's 3d: a record saved before coordinates were stored holds
    its place as text, which the loader writes into the box. Where that text
    is the one the coordinate switch wrote this session, the pair kept for
    it is not the record's: the record casts as a fresh session casts it
    (-102.0518, Denver), and Save then Replace writes the record's place."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    _store_path().write_text(json.dumps({"Old text": {
        "date_string": "2026-07-15", "time_string": "14:30:00", "time_standard": NAMED,
        "utc_offset": None, "location_query": "40.0000, -102.0518"}}))
    fresh = _load("Old text")
    assert _casts(fresh, DENVER), _zone(fresh)

    at = _app()
    at.sidebar.toggle(key="manual_coords_key").set_value(False).run()
    assert at.session_state["location_input_key"] == "40.0000, -102.0518"
    assert _casts(at, CHICAGO), _zone(at)
    at.sidebar.selectbox(key="chart_picker").select("Old text").run()
    assert_no_exception(at, "the load")
    assert at.session_state["location_input_key"] == "40.0000, -102.0518"
    assert _casts(at, DENVER), _zone(at)

    _save_as(at, "Old text")
    _button(at, "Replace").click().run()
    assert_no_exception(at, "the replace")
    assert _stored()["Old text"]["lon"] == DENVER_LON
    assert _stored()["Old text"]["lat"] == LAT
