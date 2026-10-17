"""Wrong casts refused before the atlas lane (the owner's rulings 97 and 102).

After their named mean times, Europe/Paris and Europe/Rome cast France's and
Italy's clocks on places that then belonged to neither, or whose clocks the
sources do not establish. Ruling 102 (which widens ruling 97) refuses, inside
D1R2's borders (ruling 81 (e)): Alsace-Moselle from Paris's switch to WET
(1911-03-11) to 1921-01-01; Trentino, South Tyrol, Trieste and Gorizia from
the end of Rome mean time in Europe/Rome's record (1893) to 1921-01-01. Each
start is read here from the pinned record, so that the refusal joins D1R2's
mean-time refusal with no gap; 1921-01-01 is a conservative bound. Places
outside the borders, and the cast elsewhere, are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from test_d1r_mean_time_reach_2026_10_06 import _app, _refused_on_the_page, _verdict
from test_d1r2_reach_applied_2026_10_06 import ALSACE_MOSELLE, AROUND_ALSACE_MOSELLE, AROUND_AUSTRIAN, AUSTRIAN

UTC = timezone.utc
END = datetime(1921, 1, 1, tzinfo=UTC)


def _state(zone, moment):
    local = moment.astimezone(zone)
    return local.utcoffset(), local.tzname()


def _transitions(name, start, end, step=timedelta(days=2)):
    """Every change of the zone's (offset, name) state between the two
    instants, to the second: (the first instant of the new state, the old
    state's name, the new state's name)."""
    zone, out, moment = ZoneInfo(name), [], start
    old = _state(zone, moment)
    while moment < end:
        nxt = moment + step
        if _state(zone, nxt) != old:
            lo, hi = moment, nxt
            while hi - lo > timedelta(seconds=1):
                mid = (lo + (hi - lo) / 2).replace(microsecond=0)
                if _state(zone, mid) == old:
                    lo = mid
                else:
                    hi = mid
            out.append((hi, old[1], _state(zone, hi)[1]))
            old = _state(zone, hi)
        moment = nxt
    return out


def _end_of(name, abbreviation, year):
    """The instant the record leaves its named mean time in that year."""
    ends = [t for t, old, _new in _transitions(name, datetime(year, 1, 1, tzinfo=UTC),
                                                datetime(year + 1, 1, 1, tzinfo=UTC)) if old == abbreviation]
    assert len(ends) == 1, ends
    return ends[0]


def test_the_stretches_start_where_the_records_mean_times_end_and_run_to_1921(engine):
    paris, rome = _end_of("Europe/Paris", "PMT", 1911), _end_of("Europe/Rome", "RMT", 1893)
    assert paris == datetime(1911, 3, 10, 23, 50, 39, tzinfo=UTC) and rome == datetime(1893, 10, 31, 23, 0, tzinfo=UTC)
    assert engine["OUTSIDE_STRETCHES"] == {
        "Europe/Paris": {"Alsace-Moselle": ((paris, END),)},
        "Europe/Rome": {"Trentino and South Tyrol": ((rome, END),), "Trieste and Gorizia": ((rome, END),)},
    }


# --- Alsace-Moselle --------------------------------------------------------------------------------------
# One moment either side of each bound: Paris's switch to WET (the record's 1911-03-10 23:50:39 to 23:59:59 local
# is repeated, refused as ambiguous) and 1921-01-01 (local midnight under WET); and dates between.

ALSACE_MOMENTS = (
    ((1911, 3, 10, 23, 50, 38), ("refused", "mean_time_outside"), ("cast", "PMT", True)),
    ((1911, 3, 11, 0, 0, 0), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1915, 6, 1, 12, 0, 0), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1916, 5, 1, 12, 0, 0), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1918, 12, 31, 23, 59, 59), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1919, 1, 1, 0, 0, 0), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1919, 6, 1, 12, 0, 0), ("refused", "outside_clock"), ("cast", "WEST", False)),
    ((1920, 12, 31, 23, 59, 59), ("refused", "outside_clock"), ("cast", "WET", False)),
    ((1921, 1, 1, 0, 0, 0), ("cast", "WET", False), ("cast", "WET", False)),
    ((1921, 6, 1, 12, 0, 0), ("cast", "WEST", False), ("cast", "WEST", False)),
)


@pytest.mark.parametrize("place", sorted(ALSACE_MOSELLE))
def test_alsace_moselle_is_refused_from_1911_to_1921(engine, place):
    lat, lon = ALSACE_MOSELLE[place]
    for local, inside, _outside in ALSACE_MOMENTS:
        assert _verdict(engine, "Europe/Paris", local, lat, lon) == inside, local


@pytest.mark.parametrize("place", sorted(AROUND_ALSACE_MOSELLE))
def test_the_places_around_alsace_moselle_are_unchanged(engine, place):
    lat, lon = AROUND_ALSACE_MOSELLE[place]
    for local, _inside, outside in ALSACE_MOMENTS:
        assert _verdict(engine, "Europe/Paris", local, lat, lon) == outside, local


def _strasbourg_refused(day):
    sentence = _refused_on_the_page(_app(day, (12, 0), *ALSACE_MOSELLE["Strasbourg"]), day, (
        "Europe/Paris", "the time-zone database's notes speak of France's clocks and say nothing of what "
        "Alsace-Moselle kept then"))
    assert "a mean time" not in sentence and "kept its own time" not in sentence, sentence


@pytest.mark.parametrize("day", ("1915-06-01", "1916-05-01"))
def test_strasbourg_in_1915_and_on_1916_05_01_is_refused_on_the_page(day):
    _strasbourg_refused(day)


def test_strasbourg_in_1920_is_refused_on_the_page():
    _strasbourg_refused("1920-06-01")


def test_an_anniversary_in_alsace_moselle_in_1915_is_unavailable(engine):
    birth = engine["CivilMoment"](1916, 6, 1, 12, 0, 0)
    past = engine["anniversary_moment"](birth, -1, time_standard="named", zone_name="Europe/Paris",
                                        latitude=ALSACE_MOSELLE["Strasbourg"][0], longitude=ALSACE_MOSELLE["Strasbourg"][1])
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert "say nothing of what Alsace-Moselle kept then" in past.reason, past.reason


# --- Trentino, South Tyrol, Trieste and Gorizia -------------------------------------------------------------
# Local Rome readings: the last second of Rome mean time (1893-10-31 23:49:55; the next ten minutes are
# skipped) and the first of CET -- the joint with D1R2's refusal, which must leave no gap; dates between,
# including the summers of 1916-1918 in which Rome's and Vienna's clocks agreed; the last second before
# 1921-01-01 00:00 UT (local 01:00 CET) and the first after.

ROME_MOMENTS = (
    ((1893, 10, 31, 23, 49, 55), ("refused", "mean_time_outside")),
    ((1893, 11, 1, 0, 0, 0), ("refused", "outside_clock")),
    ((1900, 6, 1, 12, 0, 0), ("refused", "outside_clock")),
    ((1915, 6, 1, 12, 0, 0), ("refused", "outside_clock")),
    ((1916, 5, 15, 12, 0, 0), ("refused", "outside_clock")),
    ((1917, 6, 15, 12, 0, 0), ("refused", "outside_clock")),
    ((1918, 11, 15, 12, 0, 0), ("refused", "outside_clock")),
    ((1919, 6, 1, 12, 0, 0), ("refused", "outside_clock")),
    ((1920, 12, 31, 12, 0, 0), ("refused", "outside_clock")),
    ((1921, 1, 1, 0, 59, 59), ("refused", "outside_clock")),
    ((1921, 1, 1, 1, 0, 0), ("cast", "CET", False)),
    ((1921, 6, 1, 12, 0, 0), ("cast", "CET", False)),
)


@pytest.mark.parametrize("place", sorted(AUSTRIAN))
def test_the_austrian_provinces_are_refused_from_1893_to_1921(engine, place):
    lat, lon = AUSTRIAN[place]
    for local, want in ROME_MOMENTS:
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == want, local


@pytest.mark.parametrize("place", sorted(AROUND_AUSTRIAN))
def test_the_places_around_the_austrian_provinces_are_unchanged(engine, place):
    """Outside the provinces (Verona, Belluno, Udine ...) every moment is cast as Rome's record has it."""
    lat, lon = AROUND_AUSTRIAN[place]
    rome = ZoneInfo("Europe/Rome")
    for local, _want in ROME_MOMENTS:
        name = datetime(*local, tzinfo=rome).tzname()
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("cast", name, name == "RMT"), local


def _trento_refused(day):
    sentence = _refused_on_the_page(_app(day, (12, 0), *AUSTRIAN["Trento"]), day, (
        "Europe/Rome", "the time-zone database's notes speak of Italy's clocks and say nothing of what "
        "Trentino and South Tyrol kept then"))
    assert "a mean time" not in sentence, sentence


def test_trento_in_may_1916_is_refused_on_the_page():
    _trento_refused("1916-05-15")


@pytest.mark.parametrize("day", ("1900-06-01", "1919-06-01"))
def test_trento_in_1900_and_1919_is_refused_on_the_page(day):
    _trento_refused(day)


def test_without_coordinates_nothing_changes(engine):
    assert _verdict(engine, "Europe/Paris", (1915, 6, 1, 12, 0, 0)) == ("cast", "WET", False)
    assert _verdict(engine, "Europe/Rome", (1900, 6, 1, 12, 0, 0)) == ("cast", "CET", False)
