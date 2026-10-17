"""Page text that credits Sahl only with what he says.

On Nativities 1.22, 1 gives Saturn and Jupiter their 6-degree "considered
eastern" floor; for Mars, 1.22, 3 gives only his easternizing at 18, and the
15-degree floor is Dykes's inference in fn 174 on that sentence. Dykes's
fn 175 works Mars's 18 in the west out from the 22 degrees of 1.22, 2 and
Mars's daily motion and cites no Abu Ma'shar, so the agreement with
Gr. Intr. VII.2, 30 is this app's own observation. The prosperity row's
footnote label names the sentence fn 149 sits on (2.11, 1). What is
computed does not change: the floors stay 6 and 15.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app.py"


def _planets(**longitudes):
    defaults = {'Sun': 180.0, 'Moon': 40.0, 'Mercury': 200.0, 'Venus': 215.0,
                'Mars': 164.0, 'Jupiter': 200.0, 'Saturn': 172.0}
    defaults.update(longitudes)
    speeds = {'Sun': 1.0, 'Moon': 13.0, 'Mercury': 1.2, 'Venus': 1.1,
              'Mars': .5, 'Jupiter': .08, 'Saturn': .03}
    return {name: {'longitude': lon, 'latitude': 0.0, 'distance': 1.0,
                   'speed_in_lon': speeds[name], 'speed_in_dist': -0.01}
            for name, lon in defaults.items()}


LABEL_84 = ('Masculine planet, eastern, {floor}+ deg from the Sun (84; Saturn and Jupiter '
            '"considered to be eastern" from 6 deg, On Nativities 1.22, 1; Mars from 15 deg, '
            "Dykes's fn 174 to On Nativities 1.22, 3)")


def _testimony_84(engine, p):
    cusps = [(170.0 + 30.0 * n) % 360.0 for n in range(12)]
    essential = engine['evaluate_essential_dignities'](p, 'Diurnal')
    accidental = engine['evaluate_accidental_dignities'](p, cusps, 'Diurnal')
    rows = engine['evaluate_strength_of_planets'](p, essential, accidental, 170.0, 'Diurnal', cusps)
    return {row['Planet']: next((t for t in row['Testimonies'] if t['n'] == '84'), None) for row in rows}


def test_testimony_84_names_each_floor_with_its_own_witness(engine):
    # Saturn 8 degrees and Mars 16 degrees before the Sun: both past their
    # floors. Jupiter 20 degrees after him, on the western side.
    found = _testimony_84(engine, _planets())
    assert found['Saturn']['sentence'] == LABEL_84.format(floor=6)
    assert found['Mars']['sentence'] == LABEL_84.format(floor=15)
    for planet, floor in (('Saturn', '6'), ('Mars', '15')):
        facts = [str(f) for f in found[planet]['facts']]
        assert any(f.startswith('Considered-eastern floor: ' + floor) for f in facts), facts
        assert not any('Visible floor' in f for f in facts)
    assert found['Jupiter'] is None


def test_testimony_84_floors_are_unchanged(engine):
    # Mars 14 degrees before the Sun stays short of the 15; Saturn 5 short of the 6.
    found = _testimony_84(engine, _planets(Mars=166.0, Saturn=175.0))
    assert found['Mars'] is None and found['Saturn'] is None
    found = _testimony_84(engine, _planets(Mars=165.0, Saturn=174.0))
    assert found['Mars'] is not None and found['Saturn'] is not None


def test_the_prosperity_strength_label_names_where_fn_149_is(engine):
    positions = dict(Sun=70., Moon=250., Venus=0., Jupiter=300., Saturn=150., Mars=210., Mercury=85.)
    speeds = dict(Sun=1., Moon=13., Venus=1., Jupiter=.1, Saturn=.03, Mars=.5, Mercury=1.2)
    natal = {p: dict(longitude=lon, speed_in_lon=speeds[p], latitude=0., distance=1.)
             for p, lon in positions.items()}
    clauses = dict(engine['_prosperity_lot_assessments'](natal, 0., 180.)['2.3, 7'].clauses)
    strong = clauses['Venus strong position']
    assert engine['is_unresolved'](strong)
    assert strong.source == 'Sahl, On Nativities 2.3, 7; fn 149 on 2.11, 1'


def _app_strings():
    return [n.value for n in ast.walk(ast.parse(APP.read_text())) if isinstance(n, ast.Constant)
            and isinstance(n.value, str)]


def test_fn_175_is_not_given_abu_mashar():
    strings = _app_strings()
    assert not any("reads VII.2, 30's westernizing boundary" in s or "fn 175 reading VII.2, 30" in s
                   for s in strings)
    notes = [s for s in strings if s.startswith("Dykes's table for Sahl (the chapter head of On Nativities 1.22")]
    assert notes == [
        "Dykes's table for Sahl (the chapter head of On Nativities 1.22, with fn 175, which works the 18 out "
        "from the 22 degrees of 1.22, 2 and Mars's daily motion) has Mars under the rays at 18 west; Sahl's own "
        "sentences are silent on Mars west. The same 18 is Gr. Intr. VII.2, 30's westernizing boundary for Mars, "
        "an agreement this app notes; fn 175 does not cite it. Gr. Intr. VII.2, 31 puts him under the rays at 15 "
        "on the western side. With the reading on, Dykes's paired 22-degree figure keeps the setting band from "
        "above 18 through 22. Both give 18 east. Affects: the Solar phase column here and every test that reads "
        "it (Weakness 93, Planetary Condition 27/34/45)."]
    sources = [s for s in strings if "Gr. Intr. VII.2, 31 has Mars under the rays at 15" in s]
    assert len(sources) == 1
    assert (
        "Gr. Intr. VII.2, 31 has Mars under the rays at 15 on the western side; Dykes's chapter-head table for "
        "Sahl, with fn 175 working the 18 out from the 22 degrees of On Nativities 1.22, 2 and Mars's daily motion, has him at "
        "18 (the same figure as Gr. Intr. VII.2, 30's westernizing boundary for Mars, which fn 175 does not cite); Sahl's "
        "own sentences are silent on Mars west. With this reading on, the table's paired 22-degree figure is the "
        "outer edge of the setting band. Both agree on 18 east.") in sources[0]
