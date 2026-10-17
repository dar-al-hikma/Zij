"""Lane KT2 (wave 5): grazing dips, and the Sect table's domain at sunset.

1. The owner's ruling 74. Beyond 65 degrees swe.rise_trans looks for the
Sun's rising or setting by sampling his altitude every two hours, and it does
not see a short dip below the horizon (or a short rise above it) whose lowest
(highest) point falls near the far end of its window: from an hour before the
moment, about 23.5 to 25 hours ahead. So at 65.7N 25E, 2000-06-21 22:22 UT, a
moment with a real setting 23.95 hours later (2000-06-22 22:19:08 UT; he rises
again at 22:25:09), the engine found no event ahead within its one-day reach,
none behind, and the Chart page said "the Sun is circumpolar here, with no
sunrise or sunset within a day on either side of this moment", which is false
(lane KT's stop; its check, finding 9). The ruling: one extra search finds the
event, so the sentence is said only where it is true. The sect, the day and
hour lords and temporal against equal hours do not move (the check measured
only the sentence changing).

2. The owner's ruling 61 (c), on the blind reading FQ1's D4. The chart's sect
reads the Sun by his visible disk: Gr. Intr. VI.33, 17 (Gr. Intr. p. 403),
"the beginning of the hours of the night are from the disappearance of the
Sun's body from the horizon of the west", with Dykes's fn 357 there, "so long
as any part of the Sun's disk is still above the horizon, it is still
daytime". The Sect table's domain (Gr. Intr. VII.1, 37, Gr. Intr. pp. 411-412:
"a male planet by day is above the earth (and by night below the earth), in a
male sign") read the Sun by his centre against the true horizon, so in the
minutes before his visible setting a Diurnal chart had its Sun "below the
earth" by day (FQ1's Chart S: "Contrary to its domain"). The ruling: the Sun's
domain reads him as the chart's sect does. The same reading holds at his
rising: the owner's ruling 88 (61 (c)'s reach) reads the Sun's domain by the
chart's sect at both ends of the day, everywhere it prints, and
tests/test_repass_l3_2026_10_04.py::test_l3_02_mashaallah_domain_matches_the_sentence_in_every_cell
reads the Sun's hemisphere in its oracle the same way (lane KT3).

The expectations below are counted here, from literal lists (the weekday's
lord and the Chaldean order) and from swe.rise_trans asked directly, not read
from the engine's tables.
"""
import math
import random
from datetime import time

import pytest
import swisseph as swe

from conftest import FLORENCE, assert_no_exception, find_table, make_app

SECOND = 1.0 / 86400.0
MANUAL = "Manual UTC offset"
CIRCUMPOLAR = ("the Sun is circumpolar here, with no sunrise or sunset within a day on either side of "
               "this moment")
SUN_UP_NO_RISE = ("the Sun is up, but no sunrise falls within the day before this moment: the day has no "
                  "beginning to count from")
SUN_DOWN_NO_SET = ("the Sun is down, but no sunset falls within the day before this moment: the night has no "
                   "beginning to count from")

# Monday = 0, as the Julian Day counts it (floor(JD + 0.5) % 7 == 0 is a Monday).
WEEKDAY_LORD = ("Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Sun")
CHALDEAN = ("Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon")
MASCULINE = ("Aries", "Gemini", "Leo", "Libra", "Sagittarius", "Aquarius")
SIGNS = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius",
         "Capricorn", "Aquarius", "Pisces")


def _weekday(jd, off):
    return int(math.floor(jd + off / 24.0 + 0.5)) % 7


def _local_hour(jd, off):
    return int(((jd + 0.5 + off / 24.0) % 1.0) * 24.0)


def _read(engine, jd, lat, lon, off):
    """(the chart's sect, the planetary day and hour), uncached, so that the
    search's settings in force are the ones asked."""
    sect = engine["calculate_traditional_chart_jd"](jd, lat, lon)["sect"]
    return sect, engine["calculate_chronocrats"].__wrapped__(jd, lat, lon, _local_hour(jd, off), off)


def _rise_trans(jd, lat, lon, rising):
    """swe.rise_trans asked directly: the next rising (setting) after jd, or
    None where it reports none within its window."""
    res, tret = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE if rising else swe.CALC_SET, (lon, lat, 0.0))
    return tret[0] if res == 0 else None


def _app(date, hms, page, lat, lon, offset=0.0):
    at = make_app(date=date, page=page, timeout=300)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hms)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = offset
    at.run(timeout=300)
    assert_no_exception(at, f"{date} {hms} {page}")
    return at


def _page_text(at):
    out = []
    for kind in ("markdown", "caption", "info", "warning", "error"):
        out.extend(str(n.value) for n in getattr(at.main, kind))
    return "\n".join(out)


# --- ruling 74: the stop case ---------------------------------------------------------------

STOP = (65.7, 25.0)
STOP_JD = swe.julday(2000, 6, 21, 22.0 + 22.0 / 60.0)
STOP_SET = swe.julday(2000, 6, 22, 22.0 + 19.0 / 60.0 + 8.0 / 3600.0)
STOP_RISE = swe.julday(2000, 6, 22, 22.0 + 25.0 / 60.0 + 9.0 / 3600.0)


def test_kt2_the_stop_case_premise_a_dip_sets_within_the_day():
    """Guard (passes on main and on this lane): the dip is real. Asked from
    2000-06-22 12:00 UT, swe.rise_trans sets the Sun at 22:19:08 and raises him
    at 22:25:09, the setting 23.95 hours after the moment, inside the one-day
    reach; asked from an hour before the moment, it reports no setting."""
    lat, lon = STOP
    start = swe.julday(2000, 6, 22, 12.0)
    sets, rises = _rise_trans(start, lat, lon, False), _rise_trans(start, lat, lon, True)
    assert sets is not None and abs(sets - STOP_SET) < 1.0 * SECOND, sets
    assert rises is not None and abs(rises - STOP_RISE) < 1.0 * SECOND, rises
    assert 23.9 < (sets - STOP_JD) * 24.0 < 24.0, (sets - STOP_JD) * 24.0
    assert _rise_trans(STOP_JD - 1.0 / 24.0, lat, lon, False) is None


def test_kt2_the_stop_case_finds_the_setting_within_the_day(engine):
    """The engine finds the setting the premise names, the Sun is up because
    the next event ahead is a setting (Gr. Intr. VI.33, 4: "by his setting the
    night comes to be"), and the reason the hour is approximate says what is
    true: no sunrise lies within the day behind. The sect, the day and hour
    lords and the equal hours are what they were: Diurnal; the civil
    weekday's Mercury (a Wednesday), flagged; the equal hour's Moon. On main
    (78e95ba) no setting was found, _sun_is_up was None and the reason was
    "circumpolar ... on either side"."""
    lat, lon = STOP
    rise, sets = engine["_next_sun_events"](STOP_JD, lat, lon)
    assert sets is not None and abs(sets - STOP_SET) < 1.0 * SECOND, sets
    assert rise is None, (rise - STOP_JD) * 24.0                 # 24.05 h ahead, beyond the reach
    assert engine["_sun_is_up"](STOP_JD, lat, lon) is True
    sect, c = _read(engine, STOP_JD, lat, lon, 0.0)
    assert c["Hour Reason"] == SUN_UP_NO_RISE, c["Hour Reason"]
    assert sect == "Diurnal", sect
    assert (c["Approximate"], c["Day Lord Civil"], c["Hour Bracketed"]) == (True, True, False), c
    assert (c["Day Lord"], c["Hour Lord"]) == ("Mercury", "Moon"), c


def test_kt2_the_stop_case_page_no_longer_says_no_event_on_either_side():
    """The Chart page, Manual UTC offset 0: the note on the approximate hour
    gives the true reason, and the strip still reads Diurnal. On main the
    note said "The Sun is circumpolar here, with no sunrise or sunset within a
    day on either side of this moment"."""
    at = _app("2000-06-21", (22, 22), "chart", *STOP)
    text = _page_text(at)
    assert "no sunrise or sunset within a day on either side" not in text, text[:2000]
    assert "The Sun is up, but no sunrise falls within the day before this moment" in text, text[:2000]
    strip = next(c.value for c in at.main.caption if " · " in c.value)
    assert "**Diurnal" in strip, strip


# --- ruling 74: a sample of grazing periods -------------------------------------------------

# Short days and nights at their seasons' edges, from KT's check's sample
# (lanes/KT-check/grazes.pkl: periods under two hours at 64.5-72 N and S, 25E
# and 120W, 2000-2001 and 2024-2025), one drawn at random (seed 74) from each
# kind x hemisphere x longitude x year: (latitude, longitude, the period's
# first event, whether it is a rising, its second event, hours before the
# first event of a moment at which main says "circumpolar ... on either side").
# False: the Sun sets and rises again (a dip below); True: he rises and sets
# again (a rise above, at the edge of the polar night).
GRAZING = (
    (68.5, -120.0, 2451745.8267555647, False, 2451745.8492062143, 23.8),   # 2000-07-20 07:50.5 UT, 32.3 min
    (69.0, 25.0, 2451748.4226453593, False, 2451748.447956806, 23.8),      # 2000-07-22 22:08.6 UT, 36.4 min
    (67.8, -120.0, 2451910.32391675, True, 2451910.3475917084, 23.8),      # 2000-12-31 19:46.4 UT, 34.1 min
    (70.5, -120.0, 2451929.3177317474, True, 2451929.3646486383, 23.8),    # 2001-01-19 19:37.5 UT, 67.6 min
    (72.0, 25.0, 2451935.9125426877, True, 2451935.96679873, 23.6),        # 2001-01-26 09:54.1 UT, 78.1 min
    (66.4, 25.0, 2460497.4216245683, False, 2460497.4463751055, 23.9),     # 2024-07-05 22:07.1 UT, 35.6 min
    (67.8, -120.0, 2460507.824459073, False, 2460507.8511566166, 23.8),    # 2024-07-16 07:47.2 UT, 38.4 min
    (69.4, -120.0, 2460689.319229816, True, 2460689.3602642664, 23.8),     # 2025-01-13 19:39.7 UT, 59.1 min
    (70.9, 25.0, 2460696.9156737784, True, 2460696.961824105, 23.8),       # 2025-01-21 09:58.6 UT, 66.5 min
    (-71.7, -120.0, 2451753.3153791074, True, 2451753.360968838, 23.9),    # 2000-07-27 19:34.1 UT, 65.6 min
    (-72.0, 25.0, 2451753.9290955816, True, 2451753.9416977167, 23.9),     # 2000-07-28 10:17.9 UT, 18.1 min
    (-66.8, -120.0, 2451917.8221285404, False, 2451917.854186613, 23.8),   # 2001-01-08 07:43.9 UT, 46.2 min
    (-68.1, 25.0, 2460496.9217349226, True, 2460496.9461563816, 23.8),     # 2024-07-05 10:07.3 UT, 35.2 min
    (-69.7, -120.0, 2460509.3161544497, True, 2460509.35969136, 23.5),     # 2024-07-17 19:35.3 UT, 62.7 min
    (-67.1, -120.0, 2460685.8216317226, False, 2460685.8558988497, 23.8),  # 2025-01-10 07:43.1 UT, 49.3 min
    (-68.2, 25.0, 2460692.4167810027, False, 2460692.45867671, 23.6),      # 2025-01-16 22:00.2 UT, 60.3 min
)


def test_kt2_the_grazing_sample_premise_each_period_is_real():
    """Guard: each period's two events are swe.rise_trans's own, asked from
    six hours before the first, and the sample moment lies within a day of
    the first; both kinds and both hemispheres are in the sample."""
    wrong, checked = [], 0
    for lat, lon, first, rising, second, hours in GRAZING:
        checked += 1
        a = _rise_trans(first - 0.25, lat, lon, rising)
        b = _rise_trans(first - 0.25, lat, lon, not rising)
        jd = first - hours / 24.0
        if (a is None or b is None or abs(a - first) > SECOND or abs(b - second) > SECOND
                or not (0.0 < first - jd < 1.0) or not (0.0 < second - first < 2.0 / 24.0)):
            wrong.append((lat, lon, first, a, b))
    assert checked == 16, checked
    assert wrong == [], wrong
    assert {(r[3], r[0] > 0) for r in GRAZING} == {(True, True), (True, False), (False, True), (False, False)}


def test_kt2_a_sample_of_grazing_periods_finds_the_event_within_the_day(engine):
    """At each sample moment the period's first event lies within the day
    ahead: the engine finds it (to the second), the Sun is up exactly where
    it is a setting, and the reason given is the true one -- no sunrise (or
    sunset) within the day behind -- never "circumpolar ... on either
    side". On main all 16 failed: the event unfound, _sun_is_up None, and
    that sentence."""
    wrong, checked = [], 0
    for lat, lon, first, rising, _second, hours in GRAZING:
        checked += 1
        jd = first - hours / 24.0
        off = float(round(lon / 15.0))
        rise_after, set_after = engine["_next_sun_events"](jd, lat, lon)
        found = rise_after if rising else set_after
        up = engine["_sun_is_up"](jd, lat, lon)
        _sect, c = _read(engine, jd, lat, lon, off)
        want_reason = SUN_DOWN_NO_SET if rising else SUN_UP_NO_RISE
        if (found is None or abs(found - first) > SECOND or up is not (not rising)
                or c["Hour Reason"] != want_reason):
            wrong.append((lat, lon, first, hours, found, up, c["Hour Reason"][:40]))
    assert checked == 16, checked
    assert wrong == [], (len(wrong), wrong)


def test_kt2_at_the_grazing_sample_moments_sect_lords_and_equal_hours_are_the_texts(engine):
    """Guard (passes on main and on this lane): at each sample moment no
    sunrise or sunset lies within the day behind, so the hours are the
    flagged equal hours counted from civil midnight, the day lord is the
    civil weekday's (the owner's ruling 5), and the sect is the side the next
    event closes: Diurnal before a dip below, Nocturnal before a rise above."""
    wrong, checked = [], 0
    for lat, lon, first, rising, _second, hours in GRAZING:
        checked += 1
        jd = first - hours / 24.0
        off = float(round(lon / 15.0))
        sect, c = _read(engine, jd, lat, lon, off)
        day = WEEKDAY_LORD[_weekday(jd, off)]
        want = ("Nocturnal" if rising else "Diurnal", True, True, False, day,
                CHALDEAN[(CHALDEAN.index(day) + _local_hour(jd, off)) % 7])
        got = (sect, c["Approximate"], c["Day Lord Civil"], c["Hour Bracketed"], c["Day Lord"], c["Hour Lord"])
        if got != want:
            wrong.append((lat, lon, first, got, want))
    assert checked == 16, checked
    assert wrong == [], wrong


FIELDS = ("Day Lord", "Hour Lord", "Approximate", "Day Lord Civil", "Day Lord Repeated", "Hour Bracketed")


def _without_the_extra_search(engine, monkeypatch, jd, lat, lon, off):
    """The reading with the extra search beyond 65 degrees turned off (the
    latitude past which it runs set beyond the pole): main's search."""
    with monkeypatch.context() as m:
        m.setitem(engine, "SUN_EVENT_SLOW_LATITUDE", 90.0)
        return _read(engine, jd, lat, lon, off)


def test_kt2_around_grazing_periods_only_the_reason_moves(engine, monkeypatch):
    """Guard: from 22.8 to 24.0 hours before each sample period's first event,
    every tenth of an hour (208 moments), the chart's sect, the day and hour
    lords, temporal against equal hours, and the civil, repeated and
    bracketed flags are the same with the extra search and without it; where
    the reason moves, it moves from "circumpolar ... on either side" to the
    true one. (On main the setting does not exist and the two agree.)"""
    wrong, moments, moved = [], 0, 0
    for lat, lon, first, rising, _second, _hours in GRAZING:
        off = float(round(lon / 15.0))
        for k in range(13):
            jd = first - (22.8 + 0.1 * k) / 24.0
            moments += 1
            sect, c = _read(engine, jd, lat, lon, off)
            sect0, c0 = _without_the_extra_search(engine, monkeypatch, jd, lat, lon, off)
            if (sect, *[c[f] for f in FIELDS]) != (sect0, *[c0[f] for f in FIELDS]):
                wrong.append((lat, lon, first, k, sect, sect0, [(f, c[f], c0[f]) for f in FIELDS if c[f] != c0[f]]))
            if c["Hour Reason"] != c0["Hour Reason"]:
                moved += 1
                if c0["Hour Reason"] != CIRCUMPOLAR or c["Hour Reason"] not in (SUN_UP_NO_RISE, SUN_DOWN_NO_SET):
                    wrong.append((lat, lon, first, k, c0["Hour Reason"][:40], c["Hour Reason"][:40]))
    assert moments == 16 * 13, moments
    assert wrong == [], (len(wrong), wrong[:6])


# --- ruling 74: the extra search never replaces an event already found ----------------------

def _first_after(jd, lat, lon, rising):
    """swe.rise_trans asked directly, from every third hour from two hours
    before jd to a day after it (so that no window's blind end hides an
    event): the first rising (setting) after jd, or None."""
    found = [_rise_trans(jd + (h - 2.0) / 24.0, lat, lon, rising) for h in range(0, 27, 3)]
    after = [e for e in found if e is not None and e > jd]
    return min(after) if after else None


TWO_SUNRISES_PLACE = (71.5, 25.0, 25.0 / 15.0)      # local mean time, +1:40


def test_kt2_the_extra_search_never_replaces_an_event_already_found(engine, monkeypatch):
    """Guard (KT2's check, finding 8): 71.5N 25E in early May 2000, ruling 25's
    season, when the next day's sunrise comes less than a day after this
    one's. Every 5 minutes from 21:50 to 23:50 UT over the short nights of
    2000-05-06 to 05-09 (100 moments): the next rising and setting the engine
    finds are the first after the moment (swe.rise_trans asked directly), the
    chart's sect is the side the next event closes (where none lies within the
    day, the Sun's altitude decides), and every field of the reading is the
    same with the extra search and without it. The extra search
    runs only where no event of the kind lies within the day ahead: run
    wherever the latitude is beyond 65 degrees, from half a day on it found the
    second sunrise and put it in place of the first, and at 2000-05-06 23:20 UT
    the night read as day, with the Moon's hour for Mars's."""
    lat, lon, off = TWO_SUNRISES_PLACE
    wrong, moments, nights = [], 0, 0
    for day in range(6, 10):
        for k in range(25):
            jd = swe.julday(2000, 5, day, 21.0 + 50.0 / 60.0 + k * 5.0 / 60.0)
            moments += 1
            want = []
            for rising in (True, False):
                event = _first_after(jd, lat, lon, rising)
                want.append(event if event is not None and event - jd <= 1.0 else None)
            got = engine["_next_sun_events"](jd, lat, lon)
            if any((g is None) != (w is None) or (g is not None and abs(g - w) > SECOND) for g, w in zip(got, want)):
                wrong.append((day, k, "events", got, want))
                continue
            rise_after, set_after = want
            if rise_after is None and set_after is None:
                want_sect = None                   # no event within the day: the Sun's altitude decides
            else:
                want_sect = "Diurnal" if rise_after is None or (set_after is not None and set_after < rise_after) \
                    else "Nocturnal"
            nights += want_sect == "Nocturnal"
            sect, c = _read(engine, jd, lat, lon, off)
            sect0, c0 = _without_the_extra_search(engine, monkeypatch, jd, lat, lon, off)
            if want_sect not in (None, sect) or (sect, *[c[f] for f in FIELDS + ("Hour Reason",)]) != \
                    (sect0, *[c0[f] for f in FIELDS + ("Hour Reason",)]):
                wrong.append((day, k, sect, want_sect, sect0, c["Hour Lord"], c0["Hour Lord"]))
    assert moments == 4 * 25, moments
    assert nights > 20, nights                     # the nights are in the sample
    assert wrong == [], (len(wrong), wrong[:6])


# --- ruling 74: no ordinary chart moves -----------------------------------------------------

HIGH_PLACES = ((69.65, 18.96, 1.0), (71.29, -156.79, -9.0), (68.97, 33.08, 3.0), (-68.58, 77.97, 7.0),
               (-66.0, 140.0, 10.0), (78.2, 15.6, 1.0))
HIGH_DATES = ((2000, 3, 1), (2000, 3, 20), (2000, 9, 22), (2000, 10, 15), (2024, 2, 29), (1240, 9, 20))


def test_kt2_no_ordinary_hour_moves_beyond_65_degrees(engine):
    """Guard: the middle of each of the 24 temporal hours of 36 days beyond 65
    degrees, in seasons with a day and a night (six places, six dates, one
    before the Gregorian reform): the sect is the hour's half, the hours are
    temporal, the day lord is the weekday's lord of the sunrise that opened
    the day, and the hour lord is counted on from him in the Chaldean order.
    Passes on main and on this lane."""
    wrong, moments = [], 0
    for lat, lon, off in HIGH_PLACES:
        for ymd in HIGH_DATES:
            midnight = engine["civil_to_jd"](*ymd) - off / 24.0
            rise = _rise_trans(midnight, lat, lon, True)
            sett = _rise_trans(rise, lat, lon, False)
            rise2 = _rise_trans(sett, lat, lon, True)
            assert rise < sett < rise2 < rise + 1.1, (lat, lon, ymd)
            day = WEEKDAY_LORD[_weekday(rise, off)]
            for step in range(24):
                start, end = (rise, sett) if step < 12 else (sett, rise2)
                jd = start + ((step % 12) + 0.5) * (end - start) / 12.0
                moments += 1
                sect, c = _read(engine, jd, lat, lon, off)
                got = (sect, c["Approximate"], c["Day Lord"], c["Hour Lord"])
                want = ("Diurnal" if step < 12 else "Nocturnal", False, day,
                        CHALDEAN[(CHALDEAN.index(day) + step) % 7])
                if got != want:
                    wrong.append((lat, lon, ymd, step, got, want))
    assert moments == 6 * 6 * 24, moments
    assert wrong == [], (len(wrong), wrong[:6])


def test_kt2_random_moments_read_the_same_with_and_without_the_extra_search(engine, monkeypatch):
    """Guard: 300 random moments (seed 74) at 60-75 degrees north and south,
    1900-2050, offsets by longitude: every field of the reading, the reason
    included, is the same with the extra search and without it -- it runs
    only where no event lies within the day ahead, and moves nothing but a
    false sentence."""
    rng = random.Random(74)
    wrong, checked = [], 0
    for _ in range(300):
        checked += 1
        lat = rng.choice((-1.0, 1.0)) * rng.uniform(60.0, 75.0)
        lon = rng.uniform(-180.0, 180.0)
        jd = rng.uniform(swe.julday(1900, 1, 1, 0.0), swe.julday(2050, 1, 1, 0.0))
        off = float(round(lon / 15.0))
        sect, c = _read(engine, jd, lat, lon, off)
        sect0, c0 = _without_the_extra_search(engine, monkeypatch, jd, lat, lon, off)
        if (sect, *[c[f] for f in FIELDS + ("Hour Reason",)]) != (sect0, *[c0[f] for f in FIELDS + ("Hour Reason",)]):
            wrong.append((lat, lon, jd))
    assert checked == 300, checked
    assert wrong == [], wrong


# --- ruling 61 (c): the Sect table's domain at sunset ----------------------------------------

# FQ1's Chart S (sample birth 6): 2026-01-01 15:57:43 UT, in the minutes before
# the visible sunset, the Sun's centre about 18' below the true horizon, in
# Capricorn, a female sign.
CHART_S = (2461042.1650830186, -22.705951642146253, 42.053091056617774)
DOMAIN_RULES = ("Abu Ma'shar", "Masha'allah")


def _sun_centre_altitude(engine, chart, lat):
    sun = chart["planetary_data"]["Sun"]
    s = engine["_sin_altitude"](sun["longitude"], sun["latitude"], sun["distance"], chart["obliquity"],
                                chart["armc"], lat)
    return math.degrees(math.asin(s))


def _accidental(engine, chart, jd, lat, rule):
    """evaluate_accidental_dignities under one domain rule, as the Dignities
    page asks it (the chart's horizon supplied); the rule restored after."""
    _none = object()
    prior = getattr(engine["_RUN"], "DOMAIN_RULE", _none)
    engine["set_readings"](DOMAIN_RULE=rule)
    try:
        return engine["evaluate_accidental_dignities"](chart["planetary_data"], chart["houses"], chart["sect"], jd,
                                                      armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    finally:
        if prior is _none:
            delattr(engine["_RUN"], "DOMAIN_RULE")
        else:
            engine["set_readings"](DOMAIN_RULE=prior)


def _florence_band(engine, ymd, setting, seconds):
    """A moment `seconds` before Florence's visible sunset (after its visible
    sunrise) on a date: its Julian Day, swe.rise_trans's own event."""
    lat, lon = FLORENCE
    midnight = swe.julday(*ymd, 0.0)
    event = _rise_trans(midnight + (0.5 if setting else 0.0), lat, lon, not setting)
    return event - seconds * SECOND if setting else event + seconds * SECOND


@pytest.mark.parametrize("rule", DOMAIN_RULES)
def test_kt2_chart_s_the_suns_domain_reads_the_charts_sect(engine, rule):
    """Chart S is Diurnal while the Sun's centre is below the true horizon:
    centre and disk disagree. The Sun's domain reads him above the earth, as
    the chart's sect does, so in Capricorn, a female sign, he is neither in
    nor contrary to his domain (Gr. Intr. VII.1, 39: the contrary is "contrary
    to all of this"), under either rule. On main his centre puts him below the
    earth by day, and he reads "Contrary to its domain" under both."""
    jd, lat, lon = CHART_S
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    assert chart["sect"] == "Diurnal", chart["sect"]
    assert -0.35 < _sun_centre_altitude(engine, chart, lat) < 0.0
    assert SIGNS[int(chart["planetary_data"]["Sun"]["longitude"] // 30)] == "Capricorn"
    sun = _accidental(engine, chart, jd, lat, rule)["Sun"]
    assert sun["Above the earth"] is True, sun
    assert sun["Hayz"] is False and sun["ContraryDomain"] is False, sun
    assert "Contrary to its domain" not in sun["Accidental Labels"], sun["Accidental Labels"]


# Florence's band before the visible sunset and after the visible rising, the
# Sun in a male sign each time: Aries, Gemini, Leo, Libra.
BAND_DATES = ((2000, 4, 10), (2000, 6, 1), (2000, 8, 5), (2000, 10, 10))


@pytest.mark.parametrize("rule", DOMAIN_RULES)
def test_kt2_at_sunset_the_suns_domain_agrees_with_the_charts_sect(engine, rule):
    """Ninety seconds before Florence's visible sunset the chart is Diurnal and
    the Sun's centre is below the true horizon. His domain reads him above the
    earth, as the chart's sect does: in a male sign by day he is in his
    domain (VII.1, 37; On Nativities 1.23, 17), under either rule. On main
    his centre puts him below the earth, and he is not, at all four."""
    lat, lon = FLORENCE
    wrong, checked = [], 0
    for ymd in BAND_DATES:
        checked += 1
        jd = _florence_band(engine, ymd, True, 90.0)
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        assert chart["sect"] == "Diurnal" and _sun_centre_altitude(engine, chart, lat) < 0.0, ymd
        assert SIGNS[int(chart["planetary_data"]["Sun"]["longitude"] // 30)] in MASCULINE, ymd
        sun = _accidental(engine, chart, jd, lat, rule)["Sun"]
        if not (sun["Above the earth"] is True and sun["Hayz"] is True and sun["ContraryDomain"] is False):
            wrong.append((ymd, sun["Above the earth"], sun["Hayz"], sun["ContraryDomain"]))
    assert checked == 4, checked
    assert wrong == [], wrong


def test_kt2_at_sunrise_the_suns_domain_agrees_with_the_charts_sect(engine):
    """The same reading at the rising: 90 seconds after Florence's visible
    sunrise the chart is Diurnal, the Sun's centre below the true horizon, and
    in a male sign he is in his domain. On main he is not, at all four."""
    lat, lon = FLORENCE
    wrong, checked = [], 0
    for ymd in BAND_DATES:
        checked += 1
        jd = _florence_band(engine, ymd, False, 90.0)
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        assert chart["sect"] == "Diurnal" and _sun_centre_altitude(engine, chart, lat) < 0.0, ymd
        sun = _accidental(engine, chart, jd, lat, DOMAIN_RULES[0])["Sun"]
        if not (sun["Above the earth"] is True and sun["Hayz"] is True):
            wrong.append((ymd, sun["Above the earth"], sun["Hayz"]))
    assert checked == 4, checked
    assert wrong == [], wrong


def test_kt2_the_sect_table_at_sunset_on_the_page():
    """The Sect table itself: the Sun is of the chart's sect and in his domain;
    his "Above horizon" stays his centre against the true horizon (No), as the
    table's caption says. On main the row reads Domain (hayz) No."""
    at = _app("2000-04-10", (17, 51, 36), "dignities", *FLORENCE)
    sect = find_table(at, "Sect").value
    sun = sect[sect["Planet"] == "Sun"].iloc[0]
    assert (sun["Above horizon"], sun["Of the chart's sect"], sun["Domain (hayz)"]) == ("No", "Yes", "Yes"), \
        sun.to_dict()


def test_kt2_no_other_planets_hemisphere_and_no_ordinary_suns_domain_moves(engine):
    """Guard (passes on main and on this lane): at 200 random moments (seed 74,
    60S-60N, 1900-2050) and at the band moments above, every planet but the
    Sun is above the earth by its centre against the true horizon, as before;
    and wherever the Sun's centre is more than a degree from the horizon his
    hemisphere is his centre's, which is the chart's sect, and his domain is
    VII.1, 37's: in it on his sect's side (above the earth by day, below it
    by night) in a male sign, contrary to it where neither holds."""
    rng = random.Random(74)
    cases = [(rng.uniform(swe.julday(1900, 1, 1, 0.0), swe.julday(2050, 1, 1, 0.0)),
              rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)) for _ in range(200)]
    cases += [(_florence_band(engine, ymd, setting, 90.0), *FLORENCE) for ymd in BAND_DATES for setting in (True, False)]
    cases.append(CHART_S)
    wrong, ordinary = [], 0
    for jd, lat, lon in cases:
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        acc = _accidental(engine, chart, jd, lat, DOMAIN_RULES[0])
        for planet, row in acc.items():
            data = chart["planetary_data"][planet]
            s = engine["_sin_altitude"](data["longitude"], data["latitude"], data["distance"], chart["obliquity"],
                                        chart["armc"], lat)
            if planet != "Sun":
                if row["Above the earth"] is not (s > 0.0):
                    wrong.append((jd, lat, lon, planet))
                continue
            if abs(math.degrees(math.asin(s))) <= 1.0:
                continue
            ordinary += 1
            day = chart["sect"] == "Diurnal"
            male = SIGNS[int(data["longitude"] // 30)] in MASCULINE
            want = (s > 0.0, (s > 0.0) == day and male, (s > 0.0) != day and not male)
            if (s > 0.0) != day or (row["Above the earth"], row["Hayz"], row["ContraryDomain"]) != want:
                wrong.append((jd, lat, lon, "Sun", row["Above the earth"], row["Hayz"], row["ContraryDomain"], want))
    assert ordinary > 150, ordinary
    assert wrong == [], wrong
