"""Lane H8 of the re-pass (owner's ruling 15, 2026-10-05): Sahl, On
Nativities 2.5, 3's grade requires 2.5, 2's configuration whole.

2.5, 2 (Sahl I p. 401): "If you found one of the two planets in square or
sextile to its companion, and they were both in their exaltations or their
houses, or one of them was in its exaltation and the other in its house, or
one of its shares, and each one of the two was casting rays upon its
companion, then that is a strong right-sidedness." 2.5, 3 (Sahl I p. 401):
"And if they were not in their houses nor exaltations, but they were both of
the sect of the day or the sect of the night, then that is also called
right-sidedness (though it is below [the first version])."

3 replaces 2's dignity clause with the sect clause and nothing else: the
pair still needs the square or sextile AND each casting rays upon the other,
the rays read by the same connection rule as 2's. Before the ruling the
engine kept the square or sextile and dropped the rays. The charts are the
blind reading's (process/hostile_pass_2026-10-03/repass/readings/
Q3_READING.md in the corpus, charts Q3-C1, Q3-C2, Q3-C3, Q3-C3b).
"""
from __future__ import annotations

import random

import pytest

from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

_corpus = needs_corpus()

BY_SECT = 'right-sidedness by sect, "below the first" (2.5, 3)'
PROFILES = ("Sahl", "Abu Ma'shar")


def _pdata(**positions):
    """The doctrine fixtures' shape: longitude, latitude 0, distance 1, the
    daily speed given (or 1.0), the other speeds 0."""
    out = {}
    for name, value in positions.items():
        lon, speed = value if isinstance(value, tuple) else (value, 1.0)
        out[name] = {"longitude": float(lon), "latitude": 0.0, "distance": 1.0,
                     "speed_in_lon": float(speed), "speed_in_lat": 0.0, "speed_in_dist": 0.0}
    return out


# The blind reading's common positions: Sun 10 Capricorn, Moon 10 Virgo,
# Mercury 0 Capricorn, Venus 0 Aquarius, Mars 0 Scorpio; daily speeds as the
# doctrine fixtures use them.
_COMMON = dict(Sun=(280.0, 1.0), Moon=(160.0, 13.0), Mercury=(270.0, 1.2), Venus=(300.0, 1.1), Mars=(210.0, 0.7))


def _pair(engine, profile, pair, **positions):
    """The right-sidedness row for one pair, by day, under one connection
    profile (this thread's reading pinned and restored)."""
    run = engine['_RUN']
    had = hasattr(run, 'CONNECTION_PROFILE')
    previous = getattr(run, 'CONNECTION_PROFILE', None)
    try:
        engine['set_readings'](CONNECTION_PROFILE=profile)
        rows = engine['evaluate_right_sidedness'](_pdata(**_COMMON, **positions), "Diurnal")
    finally:
        if had:
            engine['set_readings'](CONNECTION_PROFILE=previous)
        else:
            delattr(run, 'CONNECTION_PROFILE')
    return next(r for r in rows if r['Pair'] == pair)


@pytest.mark.parametrize("profile", PROFILES)
def test_q3_c1_a_sextile_of_one_sect_without_rays_is_not_right_sidedness(engine, profile):
    """Q3-C1: Saturn 10 Leo, Jupiter 25 Libra -- a sextile by sign, 75
    degrees apart and 15 past the sextile; neither in its house or
    exaltation; both diurnal. 3's sect clause holds, 2's rays do not: no
    grade."""
    row = _pair(engine, profile, 'Saturn and Jupiter', Jupiter=(205.0, 0.08), Saturn=(130.0, 0.03))
    assert row['Aspect (whole sign)'] == 'sextile' and row['One sect'] == 'yes', row
    assert 'Domicile' not in row['Dignities'] and 'Exalt' not in row['Dignities'], row
    assert row['Casting rays on each other'] == 'no', row
    assert row['Grade'] == '-', row


@pytest.mark.parametrize("profile", PROFILES)
def test_q3_c2_the_same_pair_casting_rays_keeps_the_by_sect_grade(engine, profile):
    """Q3-C2: Jupiter moved to 10 Libra, the exact sextile -- the rays hold
    and the pair is right-sidedness by sect (2.5, 3)."""
    row = _pair(engine, profile, 'Saturn and Jupiter', Jupiter=(190.0, 0.08), Saturn=(130.0, 0.03))
    assert row['One sect'] == 'yes' and row['Casting rays on each other'].startswith('yes'), row
    assert row['Grade'] == BY_SECT, row


@pytest.mark.parametrize("profile", PROFILES)
def test_q3_c3_and_c3b_leaving_an_exaltation_does_not_raise_a_pair_without_rays(engine, profile):
    """Q3-C3: Jupiter 10 Cancer (his exaltation), Saturn 25 Taurus (his own
    bound): a sextile by sign, 45 degrees apart, no rays -- no grade. Q3-C3b:
    Jupiter moved out of his exaltation to 10 Leo, a square by sign 75
    degrees from Saturn, still no rays -- still no grade. 3 is "below [the
    first version]": a pair cannot rise to it by losing a dignity while the
    rays stay absent."""
    c3 = _pair(engine, profile, 'Saturn and Jupiter', Jupiter=(100.0, 0.08), Saturn=(55.0, 0.03))
    assert 'Exalt' in c3['Dignities'] and c3['Casting rays on each other'] == 'no', c3
    assert c3['Grade'] == '-', c3
    c3b = _pair(engine, profile, 'Saturn and Jupiter', Jupiter=(130.0, 0.08), Saturn=(55.0, 0.03))
    assert c3b['Aspect (whole sign)'] == 'square' and c3b['One sect'] == 'yes', c3b
    assert 'Domicile' not in c3b['Dignities'] and 'Exalt' not in c3b['Dignities'], c3b
    assert c3b['Casting rays on each other'] == 'no', c3b
    assert c3b['Grade'] == '-', c3b


_PLACES = [(51.5074, -0.1278), (30.0444, 31.2357), (33.3152, 44.3661), (40.7128, -74.006),
           (-33.8688, 151.2093), (0.0, 0.0), (43.7792, 11.2463)]


def test_no_by_sect_grade_without_rays_over_seeded_charts(engine):
    """Sixty real charts (seeded, 1900-2050, seven places), the engine's
    readings at their defaults: no row reads 2.5, 3's grade where the pair
    does not cast rays, and every pair that meets 3 whole -- rays, one sect,
    neither in its house or exaltation -- does read it."""
    rng = random.Random(20261005)
    graded, whole, ruled = [], [], []
    for _ in range(60):
        jd = rng.uniform(2415020.5, 2469807.5)
        lat, lon = rng.choice(_PLACES)
        chart = engine['calculate_traditional_chart_jd'](jd, lat, lon)
        for row in engine['evaluate_right_sidedness'](chart['planetary_data'], chart['sect']):
            if not all(isinstance(row[k], str) for k in ('Grade', 'Casting rays on each other', 'One sect')):
                continue                                  # a cell left open between readings
            rays = row['Casting rays on each other'].startswith('yes')
            undignified = 'Domicile' not in row['Dignities'] and 'Exalt' not in row['Dignities']
            if row['Grade'] == BY_SECT:
                graded.append((jd, row['Pair'], rays))
            if row['One sect'] == 'yes' and undignified:
                (whole if rays else ruled).append((jd, row['Pair'], row['Grade']))
    assert len(whole) >= 20 and len(ruled) >= 20, (len(whole), len(ruled))   # both cases occur in the sample
    assert [g for g in graded if not g[2]] == [], "2.5, 3 graded on a pair not casting rays"
    assert [w for w in whole if w[2] != BY_SECT] == [], "a pair meeting 2.5, 3 whole left ungraded"
    assert [r for r in ruled if r[2] != '-'] == [], "3's sect clause met without 2's rays, yet graded"


# --- The page: the Configurations page says what 3 keeps -------------------------

def _right_sidedness_page_text():
    from conftest import assert_no_exception, make_app
    at = make_app(date="1239-12-25", page="configurations")       # Julian; JD UT 2173961.072926944
    at.run(timeout=300)
    assert_no_exception(at)
    return [m.value for m in at.main.markdown]


def test_the_page_states_that_2_5_3_keeps_the_square_or_sextile_and_the_rays():
    bodies = _right_sidedness_page_text()
    summary = [b for b in bodies if b.startswith('On Nativities 2.5, 2: a pair in square or sextile')]
    assert len(summary) == 1, summary
    clause = summary[0].split('; 3: ', 1)[1].split('; 1: ', 1)[0]
    assert 'square or sextile' in clause and 'each casting rays upon the other' in clause, clause
    assert ('"they were not in their houses nor exaltations, but they were both of the sect of the day or '
            'the sect of the night"') in clause, clause
    readings = [b for b in bodies if b.startswith("Readings, this app's: ") and '"casting rays upon its companion"' in b]
    assert len(readings) == 1, readings
    assert ('"casting rays upon its companion" = the pair is Connected under the Configurations page\'s '
            'connection rule, for 2.5, 2 and 2.5, 3 alike') in readings[0], readings[0]
    assert '2.5, 3 states only what replaces 2\'s dignity clause' in readings[0], readings[0]


@_corpus
def test_the_sentences_the_page_quotes_are_sahls():
    text = corpus_file('on_nativities.md').read_text()
    assert ('2 If you found one of the two planets in square or sextile to its companion, and they were both in '
            'their exaltations or their houses, or one of them was in its exaltation and the other in its house, '
            'or one of its shares, and each one of the two was casting rays upon its companion, then that is a '
            'strong right-sidedness.') in text
    assert ('3 And if they were not in their houses nor exaltations, but they were both of the sect<sup>122</sup> '
            'of the day or the sect of the night, then that is also called right-sidedness (though it is below '
            '[the first version]).') in text
