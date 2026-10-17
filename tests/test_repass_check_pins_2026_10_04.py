"""Pins the blind checks of the re-pass's lanes (2026-10-04) asked for, where
they found a repaired behaviour that no test would notice losing.

Each test names the check's item. They are new tests, not edits: the tests
they stand beside are unchanged.
"""
from __future__ import annotations

import json

import swisseph as swe

from conftest import assert_no_exception, make_app
from test_launch_files_2026_10_04 import FLORENCE as FLORENCE_RECORD
from test_launch_files_2026_10_04 import PETOSKEY, _delete, _picker, _prefs_file, prefs_on  # noqa: F401 (a fixture)
from test_repass_l6_2026_10_04 import _read, _save_as, _sidebar_texts, _store, scratch  # noqa: F401 (a fixture)
from test_store_write_2026_10_04 import XY, _copies


# --- G5's check, R3: the lunation's sect where the Sun neither rises nor sets ---------
#
# calculate_prenatal_syzygy divides the lunation's day and night as the chart
# does: by the Sun's visible rising and setting (_sun_is_up), and where he
# neither rises nor sets within a day, by whether any of his disk is above the
# horizon (sun_up_sin_altitude) -- Gr. Intr. VI.33, 17 with Dykes's fn 357, "so
# long as any part of the Sun's disk is still above the horizon, it is still
# daytime". The ordinary-latitude sweep stops at 60 degrees, so nothing reached
# that fallback: put back to the centre against the true horizon, it survived
# every syzygy test.

def test_the_lunations_sect_where_the_sun_does_not_set_is_read_by_his_disk(engine):
    """A birth of 2000-06-05 12:00 UT at 67 N 180 W: the new Moon of 2000-06-02
    12:14 UT, in Gemini, falls in a midnight sun, the Sun's centre below the
    true horizon and his upper limb never setting. The lunation is diurnal, so
    its triplicity lord is Saturn (the airy triplicity's by day), not Mercury."""
    lat, lon = 67.0, -180.0
    jd = swe.julday(2000, 6, 5, 12.0)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    syzygy = engine["calculate_prenatal_syzygy"](jd, lat, lon, chart["houses"])
    when = syzygy["jd_syzygy"]
    assert syzygy["event_type"] == "Conjunctional" and abs(when - swe.julday(2000, 6, 2, 12.233)) < 0.01, syzygy
    assert engine["get_zodiac_sign"](syzygy["syzygy_longitude"]) == "Gemini"
    # Premises, read off swisseph and not the engine: the Sun's centre is below
    # the true horizon (a rule asking the centre would call it night) ...
    sun = swe.calc_ut(when, swe.SUN)[0]
    true_altitude = swe.azalt(when, swe.ECL2HOR, (lon, lat, 0.0), 0.0, 0.0, (sun[0], sun[1], sun[2]))[1]
    assert -0.9 < true_altitude < 0.0, true_altitude
    # ... while the last event of his upper limb before the lunation is a
    # rising, and no setting follows it: his disk has not gone down.
    risen, rise = swe.rise_trans(when - 2.0, swe.SUN, swe.CALC_RISE, (lon, lat, 0.0))
    assert risen == 0 and rise[0] < when, (risen, rise[0])
    sets, _ = swe.rise_trans(rise[0], swe.SUN, swe.CALC_SET, (lon, lat, 0.0))
    assert sets == -2, "premise: no setting after that rising (the midnight sun)"
    # ... and the engine's day test gives no answer here, so its fallback decides.
    assert engine["_sun_is_up"](when, lat, lon) is None
    assert syzygy["sect_diurnal"] is True
    assert syzygy["active_triplicity_label"] == "Day" and syzygy["active_triplicity_lord"] == "Saturn", syzygy


# --- G5's check, R4: the full-Moon charts' sect against the one horizon ---------------
#
# test_b3_preventional_syzygy_takes_the_luminary_that_is_really_up (test_spherical_math)
# asserts the lunation's sect against the Sun's centre and the true horizon, the
# rule the owner's ruling of 2026-10-04 on the one horizon retired for the sect.
# Its two charts lie outside the band where the two rules part, so it passes; this
# asks the same two charts' sect of the ruling's own oracle, the last apparent
# rising or setting of the Sun's upper limb before the lunation. Its luminary
# assertions stay where they are: "above the earth" is the centre's altitude.

def test_the_full_moon_charts_sect_is_the_suns_visible_rising_and_setting(engine):
    from test_spherical_math import SYZYGY_FLIPS, _sun_up_by_events
    assert len(SYZYGY_FLIPS) == 2, "premise: the two charts beside which this stands"
    for dt, lat, lon, _picked in SYZYGY_FLIPS:
        chart = engine["calculate_traditional_chart"](dt, lat, lon)
        syzygy = engine["calculate_prenatal_syzygy"](chart["julian_day"], lat, lon, chart["houses"])
        assert syzygy["event_type"] == "Preventional", (dt, syzygy["event_type"])
        assert syzygy["sect_diurnal"] is _sun_up_by_events(syzygy["jd_syzygy"], lat, lon), (dt, lat, lon)


# --- G2's re-check, R2: the delete itself, beside the last chart it forgets -----------
#
# test_a_delete_forgets_the_last_chart_only_while_the_file_names_it
# (test_launch_files) asserts what a delete does to the preferences' last chart,
# not that the record left the store: with the delete's own pop removed it still
# passed. The same two windows here, and the store read after each delete.

def test_a_delete_in_one_window_takes_the_record_out_of_the_store(prefs_on):
    store = prefs_on / "Zij" / "saved_charts.json"
    store.parent.mkdir()
    store.write_text(json.dumps({"X": PETOSKEY, "D": FLORENCE_RECORD}))
    a = make_app(date="1983-11-19", page="chart").run()
    b = make_app(date="1990-01-01", page="chart").run()
    _picker(a).select("D").run()
    _picker(b).select("X").run()
    assert json.loads(_prefs_file().read_text()).get("last_chart") == "X", "the premise: B opened X last"

    _delete(a, "D")
    held = json.loads(store.read_text())
    assert "D" not in held and set(held) == {"X"}, f"after A's delete of D the store holds {sorted(held)}"
    assert "D" not in _picker(a).options, _picker(a).options
    assert json.loads(_prefs_file().read_text()).get("last_chart") == "X"

    _delete(b, "X")
    held = json.loads(store.read_text())
    assert "X" not in held and "D" not in held, f"after B's delete of X the store holds {sorted(held)}"
    assert "last_chart" not in json.loads(_prefs_file().read_text())


# --- G1's check, note 10: a copy the launch named is not announced again ----------------
#
# A store found malformed at launch is copied aside and the launch says so, naming
# the copy. The first save over those same bytes has nothing new to say about
# them: _store_as_it_stands passes no copy to announce when the load already
# named that copy (its `named`). Nothing pinned it: forced to announce always,
# every store test passed.

def test_a_store_broken_at_launch_is_named_once_not_again_at_the_first_save(scratch):
    broken = json.dumps(XY).rstrip("}") + ",}"
    _store().write_text(broken)
    at = make_app(date="1240-05-23", page="chart").run()
    assert_no_exception(at, "the launch")
    copies = _copies()
    assert len(copies) == 1 and copies[0].read_text() == broken, [p.name for p in copies]
    launch_copy = copies[0]
    said = [v for v in _sidebar_texts(at) if "A copy of the file was kept beside the saved charts" in v]
    assert len(said) == 1 and said[0].startswith("Saved charts could not be read."), said   # the launch names it

    _save_as(at, "Z")
    assert_no_exception(at, "the first save")
    texts = _sidebar_texts(at)
    assert "Saved 'Z'." in texts, texts
    assert [v for v in texts if "could not be read" in v or "A copy of the file was kept" in v] == [], texts
    assert _copies() == [launch_copy], "a second copy of the same bytes"
    assert "Z" in _read(_store())
