"""Gr. Intr. VII.6, 46: the inferiors' "beginning of their easternization".

Venus and Mercury are reported only when east of the Sun, retrograde, with
the distance from the Sun increasing, at 7 degrees or more and less than 12
(VII.2, 40-41, read with 3 and 54), and the report is labelled an
interpretation. The band follows no rays setting. The direct return of
VII.2, 43-44 and an exact station do not qualify. The Moon is never tagged
with the clause: it is carried as unresolved, and counted in nothing. The
masculine-quadrant clause of 46 is unchanged for all three.
"""
import pytest

from conftest import assert_no_exception, make_app


JD = 2451545.0
# Cusp 1 at 0 Aries, thirty degrees each: 0-90 and 180-270 are the feminine
# quarters, 90-180 and 270-360 the masculine (MASCULINE_QUADRANT_HOUSES).
CUSPS = [float(v) for v in range(0, 360, 30)]
SUN_FEMININE = 60.0     # a planet 7-12 degrees east of him stands at 48-53: feminine
SUN_MASCULINE = 150.0   # a planet 7-12 degrees east of him stands at 138-143: masculine

EAST_ONLY = "Inferior, beginning of easternization (46, an interpretation through VII.2, 40)"
EAST_AND_MASC = ("Inferior, beginning of easternization and masculine quadrant "
                 "(46; the first an interpretation through VII.2, 40)")
MASC_ONLY = "Inferior, masculine quadrant (46)"
SENTENCE = ("This report interprets Gr. Intr. VII.6,46 through Venus and Mercury's retrograde departure from 7° to less "
            "than 12° in VII.2,40; the text does not locate the Moon's beginning of easternization.")
MOON_UNRESOLVED = ("Unresolved — Inferior, beginning of easternization (46): the text does not locate the "
                   "Moon's beginning of easternization, so this clause is not applied to her and not counted")


def _planetary_data(sun, **positions):
    defaults = {
        'Sun': (sun, 1.0), 'Moon': (200.0, 13.0),
        'Mercury': (250.0, 1.2), 'Venus': (300.0, 1.1),
        'Mars': (170.0, 0.7), 'Jupiter': (280.0, 0.08),
        'Saturn': (310.0, 0.03), 'North Node': (30.0, -0.05),
    }
    defaults.update(positions)
    return {
        name: {
            'longitude': float(lon) % 360.0, 'latitude': 0.0, 'distance': 1.0,
            'speed_in_lon': float(speed), 'speed_in_lat': 0.0,
            'speed_in_dist': 0.0,
        }
        for name, (lon, speed) in defaults.items()
    }


def _condition(engine, sun=SUN_FEMININE, sect='Diurnal', **positions):
    data = _planetary_data(sun, **positions)
    essential = engine['evaluate_essential_dignities'](data, sect)
    accidental = engine['evaluate_accidental_dignities'](data, CUSPS, sect, JD)
    return engine['evaluate_abu_mashar_condition'](
        data, CUSPS, sect, essential, accidental, JD, CUSPS[0])


def _labels_46(result, planet):
    return [label for label in result[planet]['Negative Labels'] if '(46' in label]


def _east(sun, distance):
    return sun - distance


# --- Venus and Mercury: the band, retrograde and departing ----------------

def test_venus_retrograde_east_departing_reported_from_7_to_under_12(engine):
    for distance in (7.0, 11.9):
        result = _condition(engine, Venus=(_east(SUN_FEMININE, distance), -0.5))
        assert _labels_46(result, 'Venus') == [EAST_ONLY], distance
        # Venus's clause is decided, never carried as unresolved.
        assert not [v for v in result['Venus']['Unresolved Negative Labels']
                    if engine['is_unresolved'](v) and '(46)' in v.reason]
    for distance in (12.0, 6.9):
        result = _condition(engine, Venus=(_east(SUN_FEMININE, distance), -0.5))
        assert _labels_46(result, 'Venus') == [], distance


def test_venus_direct_east_is_not_the_beginning(engine):
    # Direct and approaching (VII.2, 43-44's return), and direct but slower
    # than the Sun, so departing: neither is retrograde, neither qualifies.
    for speed in (1.2, 0.9):
        result = _condition(engine, Venus=(_east(SUN_FEMININE, 8.0), speed))
        assert _labels_46(result, 'Venus') == [], speed


def test_mercury_stationary_east_is_not_reported(engine):
    # 0 and the engine's station tolerance on either side
    # (STATION_SPEED_TOLERANCE): an exact station is not retrograde.
    assert engine['STATION_SPEED_TOLERANCE'] == 0.003
    for speed in (0.0, -0.002, 0.002):
        result = _condition(engine, Mercury=(_east(SUN_FEMININE, 9.0), speed))
        assert _labels_46(result, 'Mercury') == [], speed


def test_mercury_retrograde_west_is_not_reported_and_east_is(engine):
    west = _condition(engine, Mercury=(SUN_FEMININE + 9.0, -1.0))
    assert _labels_46(west, 'Mercury') == []
    east = _condition(engine, Mercury=(_east(SUN_FEMININE, 9.0), -1.0))
    assert _labels_46(east, 'Mercury') == [EAST_ONLY]


def test_retrograde_east_but_closing_on_the_sun_is_not_reported(engine):
    # Distance must be increasing: relative speed to the Sun carries the
    # planet away from him. A constructed Sun running backwards faster than
    # Venus makes the pair close though Venus is retrograde and east.
    data_sun = SUN_FEMININE
    result = _condition(engine, sun=data_sun, Venus=(_east(data_sun, 9.0), -0.5),
                        Sun=(data_sun, -1.0))
    assert _labels_46(result, 'Venus') == []
    result = _condition(engine, sun=data_sun, Venus=(_east(data_sun, 9.0), -0.5))
    assert _labels_46(result, 'Venus') == [EAST_ONLY]


# --- The Moon: never tagged, unresolved, uncounted -------------------------

@pytest.mark.parametrize('signed', [-8.0, -3.0, -6.0, -7.0, -10.0, -11.9, -12.0, -15.0, -40.0,
                                    8.0, 10.0, 40.0])
def test_the_moon_is_never_tagged_and_her_clause_is_unresolved(engine, signed):
    result = _condition(engine, Moon=(SUN_FEMININE + signed, 13.0))
    moon = result['Moon']
    assert not any('easternization' in label for label in moon['Negative Labels']), moon['Negative Labels']
    unresolved = [value for value in moon['Unresolved Negative Labels']
                  if engine['is_unresolved'](value) and '(46)' in value.reason]
    assert len(unresolved) == 1
    assert unresolved[0].status == 'unresolved'
    assert 'does not locate the Moon' in unresolved[0].reason
    # Counted in nothing: every tally is a plain number, and the negative
    # score is exactly the labels shown as counted.
    for key in ('Weakness', 'Negative Score', 'Net'):
        assert not engine['is_unresolved'](moon[key]), key
    assert moon['Negative Score'] == len(moon['Negative Labels'])


# --- The masculine-quadrant clause, unchanged for all three ----------------

def test_masculine_quadrant_clause_stands_for_all_three(engine):
    # Each inferior east of a Sun in the masculine quarter at 8-9 degrees.
    result = _condition(engine, sun=SUN_MASCULINE,
                        Venus=(_east(SUN_MASCULINE, 8.0), 1.2),        # direct: quadrant only
                        Mercury=(_east(SUN_MASCULINE, 9.0), -1.0),     # retrograde: both halves, one entry
                        Moon=(_east(SUN_MASCULINE, 8.0), 13.0))        # the Moon: quadrant only
    assert _labels_46(result, 'Venus') == [MASC_ONLY]
    assert _labels_46(result, 'Mercury') == [EAST_AND_MASC]
    assert _labels_46(result, 'Moon') == [MASC_ONLY]
    # West of the Sun in a masculine quarter: the quadrant clause alone, as before.
    west = _condition(engine, sun=SUN_MASCULINE,
                      Venus=(SUN_MASCULINE + 20.0, 1.2), Mercury=(SUN_MASCULINE + 10.0, -1.0),
                      Moon=(SUN_MASCULINE + 5.0, 13.0))
    for planet in ('Venus', 'Mercury', 'Moon'):
        assert _labels_46(west, planet) == [MASC_ONLY], planet
    # In a feminine quarter and not in the band: no 46 at all.
    none = _condition(engine, Venus=(SUN_FEMININE + 20.0, 1.2), Mercury=(SUN_FEMININE - 30.0, 1.2),
                      Moon=(SUN_FEMININE - 8.0, 13.0))
    for planet in ('Venus', 'Mercury', 'Moon'):
        assert _labels_46(none, planet) == [], planet


# --- The band is the text's, not the rays setting's ------------------------

def test_no_rays_setting_moves_the_12_degree_limit(engine, monkeypatch):
    assert engine['INFERIOR_EASTERNIZATION_BAND'] == (7.0, 12.0)
    set_readings = engine['set_readings']
    try:
        set_readings(MOON_RAYS_ORB=15.0)
        for planet in ('Venus', 'Mercury'):
            inside = _condition(engine, **{planet: (_east(SUN_FEMININE, 11.9), -0.5)})
            assert _labels_46(inside, planet) == [EAST_ONLY], planet
            for distance in (12.0, 13.0):
                outside = _condition(engine, **{planet: (_east(SUN_FEMININE, distance), -0.5)})
                assert _labels_46(outside, planet) == [], (planet, distance)
    finally:
        set_readings(MOON_RAYS_ORB=engine['MOON_RAYS_ORB'])
    # Even a rays table widened to 15 east for both leaves the band at 12.
    import engine as module
    monkeypatch.setitem(module.SOLAR_RAYS_ORB, 'Venus', (15.0, 15.0))
    monkeypatch.setitem(module.SOLAR_RAYS_ORB, 'Mercury', (15.0, 15.0))
    for planet in ('Venus', 'Mercury'):
        assert module.solar_rays_orb(planet)[0] == 15.0
        outside = _condition(engine, **{planet: (_east(SUN_FEMININE, 13.0), -0.5)})
        assert _labels_46(outside, planet) == [], planet
        inside = _condition(engine, **{planet: (_east(SUN_FEMININE, 11.9), -0.5)})
        assert _labels_46(inside, planet) == [EAST_ONLY], planet


# --- The page and the export -----------------------------------------------

def _condition_table(at):
    return [df.value for df in at.main.dataframe
            if "Verdict" in df.value.columns and "Moon Defects" in df.value.columns][0]


def test_the_page_shows_the_sentence_the_interpretation_and_the_moon_unresolved(tmp_path, monkeypatch):
    # A real chart where Venus qualifies: 1240-03-31, Florence, 14:30 local
    # mean time -- Venus retrograde about 9.75 degrees east of the Sun.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1240-03-31", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    assert_no_exception(at, "configurations, 1240-03-31")
    assert SENTENCE in [c.value for c in at.main.caption]
    table = _condition_table(at)
    venus = table[table["Planet"] == "Venus"].iloc[0]["Weakness / Misfortune"]
    assert "Inferior, beginning of easternization" in venus and "an interpretation through VII.2, 40" in venus
    moon = table[table["Planet"] == "Moon"].iloc[0]["Weakness / Misfortune"]
    assert MOON_UNRESOLVED in moon
    assert "beginning of easternization" not in moon.replace(MOON_UNRESOLVED, "")
    # The detail panel for the Moon lists her unresolved clause and the sentence.
    box = [s for s in at.main.selectbox if s.key == "planetary_condition_detail"][0]
    box.select("Moon")
    at.run(timeout=300)
    assert_no_exception(at, "the Moon's detail")
    assert any(f"- {MOON_UNRESOLVED}" in m.value for m in at.main.markdown)
    assert SENTENCE in [c.value for c in at.main.caption]


def test_the_export_carries_the_sentence_and_the_moon_unresolved(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1240-03-31", page="sources").run(timeout=300)
    assert_no_exception(at, "sources, 1240-03-31")
    md = at.session_state["_analysis_markdown"]
    section = md.partition("Planetary Condition")[2]
    assert SENTENCE in section
    assert MOON_UNRESOLVED in section
    assert "an interpretation through VII.2, 40" in section
