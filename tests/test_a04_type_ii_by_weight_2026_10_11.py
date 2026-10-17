"""Type II transfer of light runs light to heavy by weight (ruling 146 (2),
A-04 of the third outside pass).

Gr. Intr. VII.5, 85: "a light planet connects with a planet slower than
itself, and that slow one connects with [yet] another planet". "Slower" is
read by weight (WEIGHT_ORDER), as the note on 85 reads its example (Venus,
Mars, Saturn): the directed (retrograde) reading the Connecting-planet column
carries does not reach Type II. Each leg is still today's directed applying
connection (applicant -> receiver, the owner's reading (A) of 2026-10-12),
kept only when it runs from the lighter planet to the heavier; legs are not
read from the light/heavy column, so a pair whose heavier planet applies
gives Type II nothing in either direction. Type I, collection, reflection
and every other reader of the connection columns are unchanged.

Every chart is a real one, 12:00 UT at Florence (43.7792 N, 11.2463 E), as
the reproduction's chart is. They were found by running the engine itself,
before and after the change, over every day from 1900-01-01 to 1919-12-31 at
that hour and place (7304 charts): Type I identical on all of them; the new
Type II rows exactly the old ones that run lighter to heavier on all of
them; 409 charts lose a row. From those 409, one chart of each kind: one
that keeps a row by weight the day's speeds would refuse (1905-04-13,
Mercury stationary) and loses one carried by a retrograde Venus; one whose
only row goes because the third is lighter than the medium, by the medium's
retrogradation (1901-08-17) and by its own motion (1900-07-09); one whose
only row goes because the carrier is heavier than the medium, both direct
(1903-06-17).
The three charts on which reading the legs from the light/heavy column would
differ are the first build's (1901-08-26, 1903-06-16, 1903-01-17).
"""
from datetime import datetime

import pytest

from conftest import ui_source

PLACE = (43.7792, 11.2463)

REPRO = (1903, 6, 15)              # REPRO_HIGH_A's A-04 chart
KEPT_NOT_BY_SPEED = (1905, 4, 13)  # Moon -> Mercury (stationary) -> Sun stands
THIRD_LIGHTER_RETRO = (1901, 8, 17)  # Moon -> Saturn, Saturn retrograde onto Jupiter
THIRD_LIGHTER_OWN = (1900, 7, 9)   # Moon -> Mars, Mars onto Mercury by its own motion
CARRIER_HEAVIER = (1903, 6, 17)    # Mars onto Mercury by its own motion, Mercury -> Saturn
LH_RETRO = (1901, 8, 26)           # Saturn retrograde onto Jupiter
LH_OWN = (1903, 6, 16)             # Mars onto Mercury by its own motion
LH_DIRECT = (1903, 1, 17)          # Venus overtaking Mercury, both direct

# Type I on each chart, as the engine gave it before the change (carrier,
# separates from, connects to, the row's status if it carries one).
TYPE_I = {
    REPRO: [('Moon', 'Mercury', 'Sun', None), ('Moon', 'Venus', 'Sun', None),
            ('Moon', 'Mars', 'Sun', None), ('Moon', 'Saturn', 'Sun', None),
            ('Mercury', 'Sun', 'Venus', 'unresolved'), ('Mercury', 'Sun', 'Mars', 'unresolved'),
            ('Mercury', 'Jupiter', 'Venus', 'unresolved'), ('Mercury', 'Jupiter', 'Mars', 'unresolved'),
            ('Venus', 'Mars', 'Saturn', None)],
    KEPT_NOT_BY_SPEED: [('Mercury', 'Jupiter', 'Sun', 'unresolved'), ('Venus', 'Mars', 'Mercury', 'unresolved'),
                        ('Venus', 'Mars', 'Jupiter', 'unresolved')],
    THIRD_LIGHTER_RETRO: [],
    THIRD_LIGHTER_OWN: [('Moon', 'Jupiter', 'Mercury', None), ('Moon', 'Jupiter', 'Mars', None),
                        ('Mars', 'Jupiter', 'Mercury', None)],
    CARRIER_HEAVIER: [('Moon', 'Mercury', 'Sun', None), ('Moon', 'Mercury', 'Jupiter', None)],
    LH_RETRO: [('Moon', 'Sun', 'Mars', None), ('Moon', 'Mercury', 'Mars', None), ('Moon', 'Venus', 'Mars', None),
               ('Moon', 'Jupiter', 'Mars', None), ('Moon', 'Saturn', 'Mars', None),
               ('Venus', 'Jupiter', 'Saturn', None)],
    LH_OWN: [('Venus', 'Mercury', 'Saturn', 'unresolved'), ('Venus', 'Mars', 'Saturn', None)],
    LH_DIRECT: [('Sun', 'Mars', 'Saturn', None)],
}


def _pd(engine, day):
    return engine['calculate_traditional_chart'](datetime(*day, 12, 0), *PLACE)['planetary_data']


def _type_ii(engine, pd):
    """(carrier, medium, third) for each Type II row, in the engine's order."""
    return [(r['Carrier'], r['Separates From'][len('(via '):-1], r['Connects To'])
            for r in engine['evaluate_transfers_of_light'](pd) if r['Type'] == 'II']


def _legs(engine, pd):
    """The directed applying connections the transfer reads (applicant, receiver)."""
    with engine['doctrine'](engine['SAHL']):
        return {(r['applicant'] or r['light_name'], r['receiver'] or r['heavy_name'])
                for r in engine['_pairwise_configurations'](pd)
                if not (r['aspect_name'] == 'Aversion' and not engine['_sahl_body_row'](r))
                and r['motion'] == 'Applying' and engine['_is_connected'](r)}


def _lighter(engine, a, b):
    order = engine['WEIGHT_ORDER']
    return order.index(a) > order.index(b)


def test_reproduction_rows_run_light_to_heavy_and_saturn_carries_none(engine):
    pd = _pd(engine, REPRO)
    # Saturn's retrograde leg onto Mercury is still found: it is the reading
    # that no longer reaches Type II.
    assert ('Saturn', 'Mercury') in _legs(engine, pd)
    assert pd['Saturn']['speed_in_lon'] < 0
    rows = _type_ii(engine, pd)
    assert rows == [('Mercury', 'Venus', 'Saturn'), ('Mercury', 'Mars', 'Saturn')]
    for carrier, medium, third in rows:
        assert _lighter(engine, carrier, medium) and _lighter(engine, medium, third)
    assert not [r for r in rows if r[0] == 'Saturn']


def test_a_row_standing_by_weight_is_kept_where_the_days_speed_would_refuse_it(engine):
    pd = _pd(engine, KEPT_NOT_BY_SPEED)
    assert {('Moon', 'Mercury'), ('Mercury', 'Sun')} <= _legs(engine, pd)
    # Mercury all but stationary: by the day's speed the Sun is not slower than him.
    assert abs(pd['Mercury']['speed_in_lon']) < 0.01 < abs(pd['Sun']['speed_in_lon'])
    # Venus retrograde onto Mercury is the heavier applying: no Venus-Mercury-Sun.
    assert ('Venus', 'Mercury') in _legs(engine, pd)
    assert _type_ii(engine, pd) == [('Moon', 'Mercury', 'Sun')]


@pytest.mark.parametrize('day, carrier_leg, onward_leg', [
    (THIRD_LIGHTER_RETRO, ('Moon', 'Saturn'), ('Saturn', 'Jupiter')),
    (THIRD_LIGHTER_OWN, ('Moon', 'Mars'), ('Mars', 'Mercury')),
], ids=['retrograde', 'own-motion'])
def test_medium_heavier_but_third_lighter_gives_no_row(engine, day, carrier_leg, onward_leg):
    pd = _pd(engine, day)
    legs = _legs(engine, pd)
    assert carrier_leg in legs and onward_leg in legs
    assert _lighter(engine, *carrier_leg) and not _lighter(engine, *onward_leg)
    assert _type_ii(engine, pd) == []


def test_carrier_heavier_than_medium_gives_no_row(engine):
    pd = _pd(engine, CARRIER_HEAVIER)
    legs = _legs(engine, pd)
    assert ('Mars', 'Mercury') in legs and ('Mercury', 'Saturn') in legs
    assert pd['Mercury']['speed_in_lon'] > 0 and pd['Mars']['speed_in_lon'] > 0
    assert _type_ii(engine, pd) == []


@pytest.mark.parametrize('day, rows, light_heavy_only', [
    (LH_RETRO, [('Mercury', 'Sun', 'Jupiter'), ('Mercury', 'Sun', 'Saturn')],
     [('Mercury', 'Jupiter', 'Saturn'), ('Sun', 'Jupiter', 'Saturn')]),
    (LH_OWN, [('Moon', 'Mercury', 'Saturn')],
     [('Mercury', 'Mars', 'Saturn'), ('Moon', 'Mercury', 'Mars')]),
    (LH_DIRECT, [('Moon', 'Sun', 'Saturn')],
     [('Mercury', 'Venus', 'Mars')]),
], ids=['retrograde', 'own-motion', 'both-direct'])
def test_legs_are_the_directed_ones_not_the_light_heavy_column(engine, day, rows, light_heavy_only):
    got = _type_ii(engine, _pd(engine, day))
    assert got == rows
    assert not set(got) & set(light_heavy_only)


@pytest.mark.parametrize('day', list(TYPE_I), ids=lambda d: '%04d-%02d-%02d' % d)
def test_type_i_rows_are_unchanged(engine, day):
    rows = [(r['Carrier'], r['Separates From'], r['Connects To'],
             getattr(r.get('Status'), 'status', None))
            for r in engine['evaluate_transfers_of_light'](_pd(engine, day)) if r['Type'] == 'I']
    assert rows == TYPE_I[day]


def test_the_connecting_planet_note_says_type_ii_runs_lighter_to_heavier():
    text = ui_source()
    assert ("Reception, transfer, collection, returning, revoking, emptiness of course and enclosure all read "
            "this column, not the light/heavy one, though a Type II transfer also needs each leg to run from "
            "the lighter planet to the heavier.") in text
    assert "enclosure all read this column, not the light/heavy one.\"" not in text
