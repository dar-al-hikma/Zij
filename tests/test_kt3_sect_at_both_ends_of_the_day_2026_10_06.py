"""Lane KT3 (wave 5): the Sun read by the chart's sect at both ends of the day.

The owner's ruling 88 (the reach of ruling 61 (c)). The Sun is above the earth
exactly while it is day, as the chart's sect reads him, by his visible disk at
his rising and at his setting alike: Gr. Intr. VI.33, 4 (Gr. Intr. p. 402),
"the Sun is the planet by whose rising the day comes to be, and by his setting
the night comes to be"; Gr. Intr. VI.33, 17 (Gr. Intr. p. 403), the hours of the day
begin "from the inception of the Sun's rising from the eastern horizon" and
those of the night "from the disappearance of the Sun's body from the horizon
of the west", with Dykes's fn 357 there, "so long as any part of the Sun's
disk is still above the horizon, it is still daytime". His domain
(Gr. Intr. VII.1, 37) reads him so; the pins of that half are lane KT2's, in
tests/test_kt2_grazing_dips_and_sect_2026_10_06.py.

This file holds the small item of the same ruling: Sahl's short-life
testimony 3, On Nativities 1.18, 3 (Sahl I p. 293), "the handing over of her
management to a planet under the earth while she is above the earth by day".
Its "under the earth ... by day" has VII.1, 37's shape, and her partner can be
the Sun. Read by his centre against the true horizon, a Sun whose disk still
shows was "under the earth" by day in the minutes after his visible rising and
before his visible setting, and met 3; by the chart's sect he is above the
earth all day, so with the Sun as her partner 3 is never met by day.

What the ruling leaves on the Sun's centre is pinned here too: the prenatal
syzygy and fullness, Sahl, On Nativities 1.7, 2 (Sahl I p. 264), "if it was
after the opposition, then take the portion of whichever of the two
luminaries was above the earth", a sentence that asks no sect.

The moments are found here from swe.rise_trans asked directly, and the
altitudes are counted here from each body's own ecliptic position.
"""
import math
import random

import swisseph as swe

from conftest import FLORENCE

SECOND = 1.0 / 86400.0


def _rise_trans(jd, lat, lon, rising):
    res, tret = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE if rising else swe.CALC_SET, (lon, lat, 0.0))
    assert res == 0, (jd, lat, lon, rising)
    return tret[0]


def _centre_altitude(engine, chart, planet):
    row = chart["planetary_data"][planet]
    s = engine["_sin_altitude"](row["longitude"], row["latitude"], row["distance"], chart["obliquity"],
                                chart["armc"], chart["geo_lat"])
    return math.degrees(math.asin(s))


def _first_partner(engine, chart):
    """The Moon's first perfection before she leaves her sign, asked of the
    engine's own forward run (the reading 1.18, 1-3 share)."""
    conns = engine["_pn4_luminary_connections"](chart["planetary_data"], chart["julian_day"], "Moon", 6, 0.25,
                                                applying_only=False)["connections"]
    return conns[0]["planet"] if conns else None


# Florence, a minute inside the band: 2000-01-16, 60 s before the visible
# sunset; 2000-01-28, 60 s after the visible sunrise. Both by day, the Sun's
# centre below the true horizon, the Moon above it, and her first perfection
# in her sign is with the Sun.
BAND = (((2000, 1, 16), True), ((2000, 1, 28), False))


def _band_moment(ymd, setting):
    lat, lon = FLORENCE
    midnight = swe.julday(*ymd, 0.0)
    event = _rise_trans(midnight + (0.5 if setting else 0.0), lat, lon, not setting)
    return event - 60.0 * SECOND if setting else event + 60.0 * SECOND


def test_kt3_testimony_3_reads_the_sun_by_the_charts_sect_in_the_band(engine):
    """With the Sun her partner at either end of the day, the Sun is above the
    earth by day (his disk shows), so 3 is not met and its fact says so. On
    main his centre put him below the earth, and 3 was met at both."""
    lat, lon = FLORENCE
    wrong, checked = [], 0
    for ymd, setting in BAND:
        jd = _band_moment(ymd, setting)
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        assert chart["sect"] == "Diurnal", ymd
        assert -0.9 < _centre_altitude(engine, chart, "Sun") < 0.0, ymd
        assert _centre_altitude(engine, chart, "Moon") > 0.0, ymd
        assert _first_partner(engine, chart) == "Sun", ymd
        row = engine["sahl_short_life_testimonies"](chart, chart["lot_of_fortune"])["rows"][2]
        assert row["Source"] == "1.18, 3", row
        checked += 1
        if not (row["Met"] == "no" and row["Fact"] == "day chart; the Moon above the earth; Sun above"):
            wrong.append((ymd, setting, row["Met"], row["Fact"]))
    assert checked == 2, checked
    assert wrong == [], wrong


def test_kt3_testimony_3_away_from_the_horizon_is_unchanged(engine):
    """Guard (passes on main and on this lane): at 300 random moments (seed
    88, 60S-60N, 1900-2050) where the Sun's centre is more than a degree from
    the horizon, 3 is met exactly when the chart is diurnal, the Moon's centre
    is above the true horizon and her first partner's is below it (the Sun's
    centre there is on the side the chart's sect says, so the two readings
    agree). The other rows of the table are not read here."""
    rng = random.Random(88)
    checked, met, wrong = 0, 0, []
    for _ in range(300):
        jd = rng.uniform(swe.julday(1900, 1, 1, 0.0), swe.julday(2050, 1, 1, 0.0))
        lat, lon = rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        sun_alt = _centre_altitude(engine, chart, "Sun")
        if abs(sun_alt) <= 1.0:
            continue
        assert (sun_alt > 0.0) == (chart["sect"] == "Diurnal"), (jd, lat, lon)
        partner = _first_partner(engine, chart)
        want = (partner is not None and chart["sect"] == "Diurnal" and _centre_altitude(engine, chart, "Moon") > 0.0
                and _centre_altitude(engine, chart, partner) <= 0.0)
        row = engine["sahl_short_life_testimonies"](chart, chart["lot_of_fortune"])["rows"][2]
        checked += 1
        met += want
        if (row["Met"] == "yes") != want:
            wrong.append((jd, lat, lon, partner, row["Met"], row["Fact"]))
    assert checked > 250, checked
    assert met > 10, met
    assert wrong == [], wrong


# A full Moon with both luminaries' centres below the true horizon while the
# Sun's disk still shows (a Diurnal moment, the visible sunset a few minutes
# ahead): 2001-01-09 20:24:26 UT, at 35S 17.7W, the birth three days later.
SYZYGY_PLACE = (-35.0, -17.7)
SYZYGY_BIRTH = 2451922.3503


def test_kt3_the_prenatal_fullness_stays_on_the_suns_centre(engine):
    """Ruling 88 leaves the syzygy and the fullness (On Nativities 1.7, 2) on
    the Sun's centre. Here neither luminary's centre is above the earth, so
    both read the Moon's degree, 19 Cancer 39, by the default ("the Moon
    (neither above, the default)"). Read by the chart's sect the Sun alone
    would be above, and the degree would be his, 19 Capricorn 39."""
    lat, lon = SYZYGY_PLACE
    chart = engine["calculate_traditional_chart_jd"](SYZYGY_BIRTH, lat, lon)
    syz = engine["calculate_prenatal_syzygy"](SYZYGY_BIRTH, lat, lon, chart["houses"])
    jd = syz["jd_syzygy"]
    assert abs(jd - swe.julday(2001, 1, 9, 20.0 + 24.0 / 60.0 + 26.0 / 3600.0)) < 2.0 * SECOND, jd
    assert syz["event_type"] == "Preventional", syz["event_type"]
    # premises: by day at the lunation (the visible sunset still ahead), both centres below the true horizon
    assert engine["_sun_is_up"](jd, lat, lon) is True
    assert syz["sect_diurnal"] is True
    _, ascmc = swe.houses(jd, lat, lon, b"B")
    obliquity = swe.calc_ut(jd, swe.ECL_NUT)[0][0]
    centres = {}
    for name, body in (("Sun", swe.SUN), ("Moon", swe.MOON)):
        pos = swe.calc_ut(jd, body)[0]
        centres[name] = (pos[0], math.degrees(math.asin(engine["_sin_altitude"](pos[0], pos[1], pos[2], obliquity,
                                                                               ascmc[2], lat))))
    assert -0.2 < centres["Sun"][1] < 0.0 and -0.3 < centres["Moon"][1] < 0.0, centres
    moon_lon = centres["Moon"][0]
    assert int(moon_lon // 30) == 3 and int(moon_lon % 30) == 19, moon_lon          # 19 Cancer
    assert abs(syz["syzygy_longitude"] - moon_lon) < 1e-6, (syz["syzygy_longitude"], moon_lon)
    fullness = engine["sahl_prenatal_meeting_and_fullness"](SYZYGY_BIRTH, lat, lon)["fullness"]
    assert abs(fullness["longitude"] - moon_lon) < 1e-6, (fullness["longitude"], moon_lon)
    assert fullness["degree_of"] == "the Moon (neither above, the default)", fullness["degree_of"]
