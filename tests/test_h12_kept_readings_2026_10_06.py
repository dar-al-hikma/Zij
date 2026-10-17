"""Lane H12 of the re-pass: two kept readings said on the page (rulings 38, 39).

Ruling 38 (FQ-2): a heavier planet retrograding away over a sign boundary
stays as built -- out of sign the pair is in aversion and its Connection cell
reads "–" unless Sahl's 20 admits the residue; Sahl, The Introduction Ch. 3,
20 is read by his own usage, connecting being the lighter planet's act, and
the page says so; the Great Introduction's sentence for a planet retrograding
over a sign boundary is VII.5, 121 (Gr. Intr. p. 473), not VII.5, 118
(Resistance, Gr. Intr. p. 472).

Ruling 39 (FQ-3): R2's "united in one sign" stays as built, the Moon within
her light; pinned at 11.999, 12 and 12.001 degrees past the planet; the
wording cites Sahl, The Introduction Ch. 2, 51 (Sahl I p. 49).

No engine value moves: the pins below pass as built, and the page's words
are what the rulings add.
"""
from __future__ import annotations

import re

import pytest

from conftest import make_app, assert_no_exception

FLORENCE = (43.7792, 11.2463)
LMT_1430_UT = 14.5 - FLORENCE[1] / 15.0          # the harness's 14:30 LMT at Florence, in UT

RETROGRADATION_FLAG = "(retrogradation"


def body(lon, speed):
    return {'longitude': lon % 360.0, 'latitude': 0.0, 'distance': 1.0,
            'speed_in_lon': speed, 'speed_in_lat': 0.0, 'speed_in_dist': 0.0}


def aspect_row(engine, profile, pd, a, b):
    """The aspects table's row for one pair under one connection profile
    (this thread's reading pinned and restored)."""
    run = engine['_RUN']
    had = hasattr(run, 'CONNECTION_PROFILE')
    previous = getattr(run, 'CONNECTION_PROFILE', None)
    try:
        engine['set_readings'](CONNECTION_PROFILE=profile)
        rows = engine['evaluate_ptolemaic_aspects'](pd)
    finally:
        if had:
            engine['set_readings'](CONNECTION_PROFILE=previous)
        else:
            delattr(run, 'CONNECTION_PROFILE')
    return next(r for r in rows if {r['Light Planet'], r['Heavy Planet']} == {a, b})


def real_chart(engine, y, m, d, hour_ut):
    jd = engine['civil_to_jd'](y, m, d, hour_ut)
    return jd, engine['calculate_traditional_chart_jd'](jd, *FLORENCE)


def sentences(text):
    return [s for s in re.split(r"(?<=[.;])(?<!Gr\.)(?<!Intr\.)\s+(?=[A-Z*])", text) if s]


# --------------------------------------------------------------------------
# FQ-2 (ruling 38): the reading's chart, as built
# --------------------------------------------------------------------------

# The blind reading's frame: Moon 5 Virgo, Sun 15 Scorpio, Mercury 5 Scorpio,
# Venus 20 Scorpio, Jupiter 15 Virgo; then Saturn 29°58' Aries retrograde and
# Mars 0°01' Taurus direct, three minutes apart over the cusp, both widening.
FRAME = dict(Moon=body(155.0, 13.0), Sun=body(225.0, 0.9856), Mercury=body(215.0, 1.3),
             Venus=body(230.0, 1.2), Jupiter=body(165.0, 0.08))
SATURN_AT_THE_CUSP = body(29.0 + 58.0 / 60.0, -0.05)
MARS_OVER_IT = body(30.0 + 1.0 / 60.0, 0.6)


def test_fq2_the_readings_chart_under_sahl_is_the_lighter_planets_residue(engine):
    """Saturn connected with nothing else: the residue of 20 is admitted, the
    lighter Mars is the one named (Sahl, The Introduction Ch. 3, 10, Sahl I
    p. 53: "until the light one departs from the heavy one"), and the Motion
    cell of an aversion row carries no retrogradation. In one sign the same
    kinematics carry it (Gr. Intr. VII.5, 24, Gr. Intr. p. 448: "at the
    assembly")."""
    pd = dict(FRAME, Saturn=SATURN_AT_THE_CUSP, Mars=MARS_OVER_IT)
    row = aspect_row(engine, 'Sahl', pd, 'Saturn', 'Mars')
    assert row['Aspect'] == 'Aversion'
    assert row['Connecting planet'] == 'Mars → Saturn'
    assert row['Motion'] == 'Separating'
    assert row['Strength'].startswith('Completed bodily encounter')
    assert row['Connection'] == 'Under a single blanket'
    in_one_sign = dict(FRAME, Saturn=body(15.0 + 58.0 / 60.0, -0.05), Mars=body(16.0 + 1.0 / 60.0, 0.6))
    one = aspect_row(engine, 'Sahl', in_one_sign, 'Saturn', 'Mars')
    assert one['Aspect'] == 'Conjunction' and one['Connecting planet'] == 'Mars → Saturn'
    assert one['Motion'].startswith('Separating ' + RETROGRADATION_FLAG), one['Motion']
    assert one['Connection'] == 'Under a single blanket'


def test_fq2_a_heavier_planet_only_approached_is_not_connecting_with_anything(engine):
    """Ruling 60, reading (ii): connecting is the lighter planet's act (Sahl,
    The Introduction Ch. 3, 6, Sahl I pp. 52-53: "a light, quick star is going
    straightaway to a heavy star"; 19, 24, 28, 35). The reading's chart C2:
    the Moon 25 Leo applies to Saturn by trine, Saturn only approached, so
    Saturn is still "not connecting with anything" (20, Sahl I pp. 53-54)
    and Mars's residue stands: "Under a single blanket"."""
    pd = dict(FRAME, Saturn=SATURN_AT_THE_CUSP, Mars=MARS_OVER_IT, Moon=body(145.0, 13.0))
    moon = aspect_row(engine, 'Sahl', pd, 'Moon', 'Saturn')
    assert moon['Aspect'] == 'Trine' and moon['Connection'] == 'Applying'                  # premise
    assert moon['Connecting planet'] == 'Moon → Saturn'                                      # premise: the Moon's act
    row = aspect_row(engine, 'Sahl', pd, 'Saturn', 'Mars')
    assert row['Aspect'] == 'Aversion' and row['Connecting planet'] == 'Mars → Saturn'
    assert row['Motion'] == 'Separating'
    assert row['Connection'] == 'Under a single blanket', row
    assert row['Strength'].startswith('Completed bodily encounter'), row


def test_fq2_the_question_as_first_reproduced_under_ruling_60(engine):
    """The finding's own pair: Saturn 29°58' Aries at -0.05, Mercury 0°01'
    Taurus at +0.01, the Sun (lighter than Saturn) applying to Saturn's
    opposition. Saturn is only approached: under Sahl's rule the residue
    stands; under Abu Ma'shar's there is no out-of-sign connection."""
    pd = {'Sun': body(200.0, 0.9856), 'Moon': body(250.0, 13.0), 'Mars': body(130.0, 0.5),
          'Jupiter': body(160.0, 0.08), 'Venus': body(330.0, 1.2),
          'Saturn': SATURN_AT_THE_CUSP, 'Mercury': body(30.0 + 1.0 / 60.0, 0.01)}
    sun = aspect_row(engine, 'Sahl', pd, 'Sun', 'Saturn')
    assert sun['Aspect'] == 'Opposition' and sun['Connection'] == 'Applying'               # premise
    for profile, connection in (("Abu Ma'shar", '–'), ('Sahl', 'Under a single blanket')):
        row = aspect_row(engine, profile, pd, 'Saturn', 'Mercury')
        assert row['Aspect'] == 'Aversion' and row['Connecting planet'] == 'Mercury → Saturn', (profile, row)
        assert row['Motion'] == 'Separating', (profile, row)
        assert row['Connection'] == connection, (profile, row)


def test_fq2_real_sky_saturn_only_approached_keeps_the_moons_residue(engine):
    """JD 2451833.76425 (2000-10-16 06:21 UT), Florence: Saturn 29°59' Taurus
    retrograde, the Moon 0°01' Gemini; Venus applies to Saturn by opposition,
    Saturn's retrogradation closing too (a mutual approach, Venus the one
    connecting). Saturn is not connecting with anything: the residue stands
    under Sahl's rule; Abu Ma'shar's rule has none."""
    c = engine['calculate_traditional_chart_jd'](2451833.76425, *FLORENCE)
    pd = c['planetary_data']
    assert int(pd['Saturn']['longitude'] // 30) == 1 and pd['Saturn']['speed_in_lon'] < 0     # premise
    assert int(pd['Moon']['longitude'] // 30) == 2
    venus = aspect_row(engine, 'Sahl', pd, 'Venus', 'Saturn')
    assert venus['Connecting planet'] == 'Venus → Saturn' and venus['Connection'] == 'Applying'   # premise
    assert aspect_row(engine, "Abu Ma'shar", pd, 'Saturn', 'Moon')['Connection'] == '–'
    row = aspect_row(engine, 'Sahl', pd, 'Saturn', 'Moon')
    assert row['Connecting planet'] == 'Moon → Saturn' and row['Motion'] == 'Separating'
    assert row['Connection'] == 'Under a single blanket', row


C11 = dict(FRAME, Saturn=SATURN_AT_THE_CUSP, Mars=MARS_OVER_IT, Jupiter=body(28.0, -0.02))


def test_fq2_c11_saturn_connecting_by_its_own_retrogradation_refuses_the_residue(engine):
    """The reading's C11: Saturn 29°58' Aries retrograde closes alone on
    Jupiter 28° Aries (retrograde, slower): Saturn is the sole closer by his
    own retrogradation, so he is connecting (Gr. Intr. VII.5, 24, Gr. Intr.
    p. 448) and 20's "not connecting with anything" fails: "–" under both
    readings of 20, and under Abu Ma'shar's rule."""
    jupiter = aspect_row(engine, 'Sahl', C11, 'Jupiter', 'Saturn')
    assert jupiter['Connecting planet'] == 'Saturn → Jupiter (retrogradation)'                # premise
    assert jupiter['Connection'] == 'Applying'
    for profile in ('Sahl', "Abu Ma'shar"):
        row = aspect_row(engine, profile, C11, 'Saturn', 'Mars')
        assert row['Aspect'] == 'Aversion' and row['Connecting planet'] == 'Mars → Saturn', (profile, row)
        assert row['Connection'] == '–', (profile, row)


def test_fq2_a_refused_residue_says_why(engine):
    """A refused residue is not a bare aversion: the Strength cell names 20's
    condition that refuses it -- the striker's own connection (C11, Saturn
    connecting with Jupiter), or another body first in the striker's light."""
    row = aspect_row(engine, 'Sahl', C11, 'Saturn', 'Mars')
    assert row['Connection'] == '–'                                                          # premise
    assert row['Strength'] == ('In Power (out-of-sign); residue refused: Saturn is connecting with Jupiter '
                               '(Sahl 20: "not connecting with anything")'), row['Strength']
    first = {'Saturn': body(29.75, 0.1), 'Venus': body(30.0, 0.0), 'Moon': body(31.0, 13.0)}
    moon = aspect_row(engine, 'Sahl', first, 'Saturn', 'Moon')
    assert moon['Connection'] == '–'                                                         # premise
    assert moon['Strength'] == ('In Power (out-of-sign); residue refused: Venus is first in Saturn\'s light '
                                '(Sahl 20: "the first in that light")'), moon['Strength']
    assert aspect_row(engine, "Abu Ma'shar", C11, 'Saturn', 'Mars')['Strength'] == 'In Power (out-of-sign)'


@pytest.mark.parametrize("jd, sun_sign", [(2454397.28000, 6), (2461454.96001, 10)])
def test_fq2_the_lighter_planet_retrograding_back_over_a_cusp_is_named(engine, jd, sun_sign):
    """Mercury retrograde back onto the direct Sun over a cusp (inferior
    conjunction), Florence: JD 2454397.28000 (2007-10-23 18:43 UT) and JD
    2461454.96001 (2027-02-18 11:03 UT). Both close; in one sign the lighter
    is named ("Mercury → Sun"), and ruling 60 names the lighter over the cusp
    too, as the one connecting (Sahl, The Introduction Ch. 3, 6)."""
    c = engine['calculate_traditional_chart_jd'](jd, *FLORENCE)
    pd = c['planetary_data']
    assert int(pd['Sun']['longitude'] // 30) == sun_sign and int(pd['Mercury']['longitude'] // 30) == sun_sign + 1
    assert pd['Sun']['speed_in_lon'] > 0 > pd['Mercury']['speed_in_lon']                      # premise: both close
    row = aspect_row(engine, 'Sahl', pd, 'Sun', 'Mercury')
    assert row['Aspect'] == 'Aversion' and row['Motion'] == 'Applying'
    assert row['Connection'] == 'Applying'
    assert row['Connecting planet'] == 'Mercury → Sun', row
    moved = {name: dict(data) for name, data in pd.items()}
    for name in ('Sun', 'Mercury'):
        moved[name]['longitude'] -= 10.0
    one = aspect_row(engine, 'Sahl', moved, 'Sun', 'Mercury')
    assert one['Aspect'] == 'Conjunction' and one['Connecting planet'] == 'Mercury → Sun'    # as in one sign


def test_fq2_under_abu_mashars_rule_the_readings_chart_is_not_connected(engine):
    """Gr. Intr. VII.4, 13 (Gr. Intr. p. 426): in two signs they are "*not*
    said to be 'united'"; VII.5, 14 (Gr. Intr. p. 446): "not counted as a
    'connection by assembly,' but they are both 'mixing their natures' in a
    weak way"."""
    for extra in ({}, {'Moon': body(145.0, 13.0)}):
        pd = dict(FRAME, Saturn=SATURN_AT_THE_CUSP, Mars=MARS_OVER_IT, **extra)
        row = aspect_row(engine, "Abu Ma'shar", pd, 'Saturn', 'Mars')
        assert row['Aspect'] == 'Aversion' and row['Motion'] == 'Separating', row
        assert row['Strength'] == 'In Power (out-of-sign)', row
        assert row['Connection'] == '–', row


# --------------------------------------------------------------------------
# FQ-2 (ruling 38): what the page says
# --------------------------------------------------------------------------

def test_fq2_the_sources_page_says_sahl_20_is_read_by_the_lighter_planets_act():
    """Sahl, The Introduction Ch. 3, 6 (Sahl I pp. 52-53): "a light, quick
    star is going straightaway to a heavy star"; 20 (Sahl I pp. 53-54) read by
    that usage. Gr. Intr. VII.5, 24 (Gr. Intr. p. 448): retrogradation "at the
    assembly"; VII.5, 121 (Gr. Intr. p. 473): the planet in the next sign
    "goes retrograde and enters its sign, and conjoins with it"."""
    at = make_app(page="sources").run()
    assert_no_exception(at, "sources")
    notes = None
    for node in at.main:
        if getattr(node, "type", None) == "status" and node.label == "The two rules in full, and the alternative reading":
            notes = [m.value for m in node.markdown]
    assert notes is not None
    sahl = notes[notes.index("**Sahl's rule.**") + 1]                                    # the section's body
    assert "(20-21)" in sahl                                                                # premise: the rule
    assert "the lighter planet's act" in sahl, sahl
    assert '"a light, quick star is going straightaway to a heavy star" (6)' in sahl, sahl
    assert '"at the assembly" (Gr. Intr. VII.5, 24)' in sahl, sahl
    assert '"enters its sign, and conjoins with it" (Gr. Intr. VII.5, 121)' in sahl, sahl
    assert "118" not in sahl, sahl


def test_fq2_the_aspects_note_cites_vii5_121_not_118_at_the_sign_boundary():
    """The Configurations page's note on the connecting planet: its sentences
    on the sign boundary name Gr. Intr. VII.5, 121 (Gr. Intr. p. 473), the
    retrograde planet from the next sign, and not VII.5, 118 (Resistance,
    Gr. Intr. p. 472, which crosses no sign); one-sign retrogradation keeps
    VII.5, 24."""
    at = make_app(date="1240-09-18", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run()
    assert_no_exception(at, "configurations, 1240-09-18")
    md = [m.value for m in at.main.markdown]
    note = md[md.index("**The connecting planet, and retrogradation.**") + 1]          # the section's body
    assert 'Abu Ma\'shar, Gr. Intr. VII.5, 24 ("the connection of one of them' in note             # premise: one sign
    boundary = [s for s in sentences(note) if "boundary" in s.lower() or "out of sign" in s.lower()]
    assert boundary, note
    assert not [s for s in boundary if "118" in s], boundary
    assert [s for s in boundary if "VII.5, 121" in s and '"enters its sign, and conjoins with it"' in s], boundary
    assert [s for s in boundary if "the lighter planet's act" in s and "Ch. 3, 6" in s], boundary
    assert [s for s in boundary if '"–"' in s and "aversion" in s], boundary


def test_fq2_the_readings_notes_name_the_scope_of_not_connecting_with_anything():
    """Ruling 60: the Sources page's Sahl rule says whose connections count
    for 20's "not connecting with anything" -- the lighter planet's act
    (Ch. 3, 6, 19, 24, 28, 35); a planet only approached is not connecting;
    the striker connects as the lighter party or as the sole closer by its
    own retrogradation."""
    at = make_app(page="sources").run()
    assert_no_exception(at, "sources")
    notes = None
    for node in at.main:
        if getattr(node, "type", None) == "status" and node.label == "The two rules in full, and the alternative reading":
            notes = [m.value for m in node.markdown]
    sahl = notes[notes.index("**Sahl's rule.**") + 1]
    assert "the lighter planet's act" in sahl                                                # premise: ruling 38's words
    scope = [s for s in sentences(sahl) if '"not connecting with anything"' in s]
    assert scope, sahl
    assert [s for s in scope if "only approached" in s and "(6, 19, 24, 28, 35)" in s], scope
    assert [s for s in scope if "the lighter party" in s and "the sole closer by its own retrogradation" in s], scope


def test_fq2_the_sources_page_labels_the_residue_reading_as_this_apps_with_9_10():
    """Ruling 70, reading (A): a lighter planet still inside the residue of a
    separation counts as connected for 20's "not connecting with anything".
    The Sources page labels that as this app's reading and cites Sahl, The
    Introduction Ch. 3, 9-10 for it (Sahl I p. 53), quoting 9 as printed --
    not 24, whose light planet "separates from the heavy planet, and is
    connecting with another"."""
    at = make_app(page="sources").run()
    assert_no_exception(at, "sources")
    notes = None
    for node in at.main:
        if getattr(node, "type", None) == "status" and node.label == "The two rules in full, and the alternative reading":
            notes = [m.value for m in node.markdown]
    sahl = notes[notes.index("**Sahl's rule.**") + 1]
    assert '"not connecting with anything"' in sahl                                         # premise: ruling 60
    residue = [s for s in sentences(sahl) if "residue of a separation" in s]
    assert residue, sahl
    assert "this app's reading" in residue[0], residue
    assert "(Sahl, The Introduction Ch. 3, 9-10)" in residue[0], residue
    assert ('"And the planet does not cease to be counted as being connected until it separates from the planet '
            'by a full degree" (9)') in residue[0], residue
    assert "24" not in residue[0], residue
    assert not [s for s in sentences(sahl) if "connected pair" in s], sahl


def test_fq2_the_aspects_note_says_where_the_retrogradation_flag_stands():
    """H12 check note 4: the Motion cell's retrogradation flag is set on
    every configured row, assembly or aspect, and never on an aversion; the
    note says so rather than "in one sign". And the lighter planet
    retrograding back over the cusp is named, as in one sign."""
    at = make_app(date="1240-09-18", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run()
    assert_no_exception(at, "configurations, 1240-09-18")
    md = [m.value for m in at.main.markdown]
    note = md[md.index("**The connecting planet, and retrogradation.**") + 1]
    assert "flags on every configured row, never on an aversion" in note, note
    assert not [s for s in sentences(note) if "Motion cell" in s and "in one sign" in s], note
    assert [s for s in sentences(note) if "the lighter planet retrogrades back" in s and "the lighter one is named" in s], note


# --------------------------------------------------------------------------
# FQ-3 (ruling 39): R2's "united in one sign", the Moon within her light
# --------------------------------------------------------------------------

def _wild(engine, pd, c):
    corruption = engine['evaluate_corruption_of_the_moon'](pd, c['houses'], c['sect'])
    return corruption['testimonies'][111]['matched']


@pytest.mark.parametrize("gap, wild", [(11.999, False), (12.0, True), (12.001, True)])
def test_fq3_the_moon_is_united_in_one_sign_only_within_her_light(engine, gap, wild):
    """Sahl, The Introduction Ch. 2, 51 (Sahl I p. 49): the union "comes to be
    if two planets were in one sign, ... and between the two of them in terms
    of degrees are 12° and what is less than that: for that is the limit of
    the assembly"; Ch. 3, 10-11 (Sahl I p. 53): "not considered to be
    separated ... until the light one departs from the heavy one by one-half
    of its body", and then "it is sundered from it"; 14: the Moon's light is
    12°. 1240-10-13 14:30 LMT Florence (the reading's C2), the Moon set at
    12°30' Virgo and Mars the gap behind her, nothing else in or striking
    into Virgo: at 11.999° she is still uniting, at 12° she has departed by
    half her body, at 12.001° she is past it -- empty (63, 111)."""
    _jd, c = real_chart(engine, 1240, 10, 13, LMT_1430_UT)
    pd = {name: dict(data) for name, data in c['planetary_data'].items()}
    pd['Moon']['longitude'] = 162.5
    pd['Mars']['longitude'] = 162.5 - gap
    others = [p for p in ('Sun', 'Mercury', 'Venus', 'Jupiter', 'Saturn') if int(pd[p]['longitude'] // 30) == 5]
    assert others == []                                                                       # premise: Virgo holds two
    assert pd['Moon']['speed_in_lon'] > pd['Mars']['speed_in_lon'] > 0                     # premise: separating, direct
    assert _wild(engine, pd, c) is wild


@pytest.mark.parametrize("date, other, gap", [((1240, 10, 13), 'Mars', 12.715), ((1240, 3, 28), 'Mercury', 22.050)])
def test_fq3_a_moon_past_her_light_in_one_sign_is_not_uniting(engine, date, other, gap):
    """The reading's two charts, 14:30 LMT Florence: the Moon in one sign with
    a planet and past her 12° (Sahl, The Introduction Ch. 2, 51, Sahl I p. 49),
    so not "uniting with one" (Ch. 3, 63, Sahl I p. 63): 111 fires."""
    _jd, c = real_chart(engine, *date, LMT_1430_UT)
    pd = c['planetary_data']
    assert int(pd['Moon']['longitude'] // 30) == int(pd[other]['longitude'] // 30)            # premise: one sign
    assert abs((pd['Moon']['longitude'] - pd[other]['longitude']) - gap) < 0.01              # premise: past 12°
    assert _wild(engine, pd, c) is True


def test_fq3_the_wild_note_bounds_uniting_by_ch_2_51():
    """The Corruption of the Moon note's sentence on uniting quotes Sahl's
    own limit of the union (The Introduction Ch. 2, 51, Sahl I p. 49) and
    names the work."""
    at = make_app(date="1240-05-26", page="configurations")
    at.run(timeout=300)
    assert_no_exception(at, "1240-05-26 configurations")
    note = next(m.value for m in at.main.markdown if "**Wild (111).**" in m.value)
    assert "uniting with it" in note                                                          # premise: the clause
    assert '12° and what is less than that: for that is the limit of the assembly" (Sahl, The Introduction Ch. 2, 51)' in note, note
    assert "(Sahl, The Introduction Ch. 2, 51)" in note, note


def test_fq3_the_wild_note_says_what_exactly_twelve_degrees_past_is():
    """Sahl, The Introduction Ch. 2, 51 (Sahl I p. 49) states the union with
    "the heavy one in front of the light one" -- the approach -- so its
    inclusive 12° does not reach a Moon past the planet; past it, 10-11
    (Sahl I p. 53): "until the light one departs from the heavy one by
    one-half of its body ... then indeed it is sundered from it". At exactly
    12° past she is wild, and the note must not say otherwise."""
    at = make_app(date="1240-05-26", page="configurations")
    at.run(timeout=300)
    assert_no_exception(at, "1240-05-26 configurations")
    note = next(m.value for m in at.main.markdown if "**Wild (111).**" in m.value)
    assert "(Sahl, The Introduction Ch. 2, 51)" in note                                     # premise: ruling 39
    assert '"the heavy one in front of the light one' in note, note
    twelve = [s for s in sentences(note) if "exactly 12°" in s]
    assert twelve and '"is sundered from it"' in twelve[0] and "(10-11)" in twelve[0], twelve


def test_fq2_a_striker_whose_own_connection_is_unresolved_leaves_its_residue_unresolved(engine):
    """Ruling 60 keeps 20's first condition three-valued: Mars at the end of
    Aries, retrograde, separating from his sextile to the heavier Saturn with
    no encounter evidence (his own act, the lighter party), so whether Mars
    is "not connecting with anything" is not established, and the Moon's
    residue past him over the cusp is unresolved, not settled. (The point the
    F6 test of the unresolved blocker made before ruling 60 settled its chart,
    where the striker was only approached; that test is now
    test_residue_is_settled_where_the_striker_is_only_approached_by_an_unresolved_lighter_planet.)"""
    pd = {'Mars': body(29.75, -0.3), 'Moon': body(30.25, 13.0), 'Saturn': body(89.9, 0.1),
          'Sun': body(200.0, 0.9856)}
    with engine['doctrine'](engine['SAHL']):
        rows = engine['_pairwise_configurations'](pd)
        saturn = next(r for r in rows if {r['p1'], r['p2']} == {'Mars', 'Saturn'})
        assert saturn['aspect_name'] == 'Sextile' and saturn['applicant'] == 'Mars'          # premise: Mars's act
        assert engine['is_unresolved'](engine['_sahl_connection_value'](saturn))            # premise: unresolved
        row = next(r for r in rows if {r['p1'], r['p2']} == {'Mars', 'Moon'})
        assert engine['is_unresolved'](row.get('residue_admission'))
        assert engine['is_unresolved'](engine['_sahl_connection_value'](row))
