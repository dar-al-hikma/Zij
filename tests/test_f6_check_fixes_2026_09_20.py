"""The F6 blind check's defects (BUILD_F6_CONNECTION_STATES_CHECK_REPORT_2026-09-20.md, findings 4, 5, 15, 23, 29),
each pinned: an adjacent-sign pair outside the strike's reach is an aversion and nothing else; a strike is an
approach; the Releaser's testimonies pass the display boundary; the Rhetorius table pins its columns and prints
readable distances; Sahl 3.13 is quoted where its rule is adopted."""
import pytest

from conftest import assert_no_exception, make_app


def data(**pairs):
    return {p: {'longitude': x, 'speed_in_lon': v} for p, (x, v) in pairs.items()}


def _rows(engine, p):
    with engine['doctrine'](engine['SAHL']):
        return engine['evaluate_ptolemaic_aspects'](p)


# --- finding 4: a completed encounter is not read into a far adjacent-sign pair -----------------------------------

@pytest.mark.parametrize('light,heavy', [
    (('Sun', 40.9, 0.98), ('Mars', 25.0, 0.5)),      # the Sun 10.9 deg past the boundary ahead of Mars
    (('Moon', 58.9, 13.0), ('Mercury', 25.0, 1.0)),  # the Moon 28.9 deg past it
    (('Venus', 43.6, 1.2), ('Sun', 1.0, 0.98)),      # Venus 42.6 deg past it (the checker's 1566-01-21 case)
])
def test_far_adjacent_sign_pair_is_an_aversion_and_nothing_else(engine, light, heavy):
    # Adjacent signs, both direct, the light planet ahead and faster: motion "Separating" by the roles, but no
    # ruling makes a pair this far past the boundary a completed encounter -- it is an aversion and nothing else.
    p = data(**{light[0]: (light[1], light[2]), heavy[0]: (heavy[1], heavy[2])})
    row = next(r for r in _rows(engine, p) if r['Aspect'] == 'Aversion')
    assert row['Connection'] == '\u2013'
    assert 'Completed bodily encounter' not in row['Strength']


def test_in_power_note_survives_on_a_far_aversion_row(engine):
    # 1240-05-23 Florence: Sun-Mars 10 deg 55' across the boundary was "In Power (out-of-sign)" on main.
    from conftest import FLORENCE, LOCAL_TIME  # noqa: F401  (the chart the readers used)
    at = make_app(date='1240-05-23', page='configurations').run()
    assert_no_exception(at)
    frames = [el.value for el in list(at.main.dataframe) + list(at.main.table)]
    table = next(df for df in frames if 'Connection' in df.columns)
    aversions = table[table['Aspect'] == 'Aversion']
    assert len(aversions) >= 6
    assert not (aversions['Connection'].astype(str) == 'Separated').any(), aversions[['Light Planet', 'Heavy Planet', 'Connection']]
    assert not aversions['Strength'].astype(str).str.contains('Completed bodily encounter').any()


def test_completed_residue_inside_the_strikers_light_still_reads_separated(engine):
    # Saturn 29.75 Aries direct, Moon 30.25 (Taurus) direct and faster: 0.5 deg past the boundary, within Saturn's
    # 9-degree light -- the ruled residue (G15-A rows 7-8), Separated at >= 1 deg, blanket below it.
    close = data(Saturn=(29.75, 0.1), Moon=(30.25, 13.0))
    row = next(r for r in _rows(engine, close) if r['Aspect'] == 'Aversion')
    assert row['Connection'] == 'Under a single blanket'
    past = data(Saturn=(29.75, 0.1), Moon=(31.0, 13.0))
    row = next(r for r in _rows(engine, past) if r['Aspect'] == 'Aversion')
    assert row['Connection'] == 'Separated'


# --- finding 29: a strike is an approach -------------------------------------------------------------------------

def test_a_separating_adjacent_pair_is_admitted_to_no_strike(engine):
    p = data(Mercury=(29.0, -0.5), Saturn=(31.0, 0.1))
    row = engine['_pairwise_configurations'](p)[0]
    assert row.get('strike_admission', False) is False
    assert not row.get('sahl_body_connection')
    wild = engine['evaluate_abu_wildness'](p)
    assert 'out-of-sign body connection' not in str(wild)


# --- finding 5: the Releaser's testimonies through the display boundary -------------------------------------------

def test_releaser_testimonies_render_without_a_repr_leak():
    at = make_app(date='1240-03-26', page='releaser').run()
    assert_no_exception(at)
    frames = [el.value for el in list(at.main.dataframe) + list(at.main.table)]
    cells = [c for df in frames for c in df.astype(str).values.ravel()]
    assert not [c for c in cells if 'UnresolvedResult(' in c or 'YearsOutcome(' in c]
    assert any(c.startswith('7. The lord of the Ascendant connects') for c in cells)


# --- finding 15: the Rhetorius table's columns and distances ----------------------------------------------------------

def test_rhetorius_table_pins_its_columns_and_prints_readable_distances():
    at = make_app(date='1240-03-10', page='findings', view='supplement').run()
    assert_no_exception(at)
    frames = [el.value for el in list(at.main.dataframe) + list(at.main.table)]
    table = next(df for df in frames if list(df.columns[:2]) == ['Planet', 'Condition'] and 'Chapter' in df.columns)
    assert list(table.columns) == ['Planet', 'Condition', 'By', 'Chapter', 'Text', 'Status']
    import re
    long_floats = [c for c in table.astype(str).values.ravel() if re.search(r'\d\.\d{3,}', c)]
    assert not long_floats, long_floats[:3]


# --- finding 23: Sahl 3.13 quoted where its rule is adopted ---------------------------------------------------------

def test_sahl_3_13_is_quoted_on_the_sources_page():
    at = make_app(date='1240-05-23', page='sources').run()
    assert_no_exception(at)
    text = '\n'.join(node.value for node in at.main.markdown)
    assert 'from a degree to 15° between the Sun and one of the planets' in text
    assert 'Ch. 3, 13' in text


# --- finding 4, the delta: the residue under Sahl 20's two conditions, as the strike is ----------------------------

def test_completed_residue_admitted_where_the_striker_is_only_approached(engine):
    # Saturn 29.75 Aries with the Moon 0.5 deg past it in Taurus, and Jupiter in an exact sextile with Saturn.
    # Ruling 60: connecting is the lighter planet's act, so the sextile is Jupiter's and Saturn, only approached,
    # is "not connecting with anything" (Sahl, The Introduction Ch. 3, 20): the strike stands, and its residue.
    p = data(Saturn=(29.75, 0.1), Moon=(30.25, 13.0), Jupiter=(89.75, 0.2))
    row = next(r for r in _rows(engine, p) if r['Aspect'] == 'Aversion' and 'Moon' in (r['Light Planet'], r['Heavy Planet'])
               and 'Saturn' in (r['Light Planet'], r['Heavy Planet']))
    assert row['Connection'] == 'Under a single blanket'                 # ruling 60: Saturn only approached by Jupiter
    assert 'Completed bodily encounter' in row['Strength']               # ruling 60


def test_completed_residue_refused_where_another_body_is_first_in_the_light(engine):
    # Venus stands first ahead of Saturn in Taurus; the Moon, 1 deg past Saturn's degree, is not "first in that light".
    p = data(Saturn=(29.75, 0.1), Venus=(30.0, 0.0), Moon=(31.0, 13.0))
    rows = _rows(engine, p)
    moon = next(r for r in rows if r['Aspect'] == 'Aversion' and {r['Light Planet'], r['Heavy Planet']} == {'Saturn', 'Moon'})
    assert moon['Connection'] == '–'
    assert 'Completed bodily encounter' not in moon['Strength']


# --- the shared membership honours the residue's admission (Codex's delta review of PR #83) --------------------------

def _pn4_rows(engine, p):
    for v in p.values():
        v.update(latitude=0.0, distance=1.0)
    chart = {'planetary_data': p, 'ascendant': 0.0, 'houses': tuple(range(0, 360, 30)), 'sect': 'Diurnal'}
    return engine['pn4_i7_planets'](chart, chart)


@pytest.mark.parametrize('extra, refused', [
    ({'Jupiter': (89.75, 0.2)}, False),         # ruling 60: Saturn only approached by Jupiter is "not connecting with anything"
    ({'Venus': (30.0, 0.0), 'Moon': (30.5, 13.0)}, True),  # Venus first ahead: the Moon is not "first in that light"
])
def test_refused_residue_is_not_connected_anywhere(engine, extra, refused):
    base = {'Saturn': (29.75, 0.1), 'Moon': (30.25, 13.0)}
    base.update(extra)
    p = data(**base)
    with engine['doctrine'](engine['SAHL']):
        rows = engine['_pairwise_configurations'](p)
        row = next(r for r in rows if {r['p1'], r['p2']} == {'Saturn', 'Moon'})
        assert row.get('residue_admission') is (not refused)
        assert engine['_sahl_connection_value'](row) is (not refused)
        assert engine['_is_connected'](row) is (not refused)
        table = engine['evaluate_ptolemaic_aspects'](p)
    shown = next(r for r in table if {r['Light Planet'], r['Heavy Planet']} == {'Saturn', 'Moon'})
    assert shown['Connection'] == ('–' if refused else 'Under a single blanket')
    assert 'Body connection' not in shown['Strength']
    assert ('Completed bodily encounter' in shown['Strength']) is (not refused)


def test_residue_is_settled_where_the_striker_is_only_approached_by_an_unresolved_lighter_planet(engine):
    # Mars's sextile to Saturn is unresolved (an exceptional motion), but it is Mars's act, the lighter planet's
    # (ruling 60): Saturn, only approached, is "not connecting with anything" (Sahl, The Introduction Ch. 3, 20),
    # so the residue is settled and admitted, in membership and in the label alike.
    p = data(Saturn=(29.75, 0.1), Moon=(30.25, 13.0), Mars=(89.5, -0.3))   # Mars retrograde 0.25 short of Saturn's sextile, receding: exceptional
    with engine['doctrine'](engine['SAHL']):
        rows = engine['_pairwise_configurations'](p)
        row = next(r for r in rows if {r['p1'], r['p2']} == {'Saturn', 'Moon'})
        assert row.get('residue_admission') is True                      # ruling 60: Mars's row is Mars's act, not Saturn's
        assert engine['_sahl_connection_value'](row) is True             # ruling 60
        table = engine['evaluate_ptolemaic_aspects'](p)
    shown = next(r for r in table if {r['Light Planet'], r['Heavy Planet']} == {'Saturn', 'Moon'})
    assert shown['Connection'] == 'Under a single blanket'               # ruling 60


# --- tied residues share the one first-body choice (Codex's second delta review of PR #83) ------------------------

def test_tied_completed_residues_are_one_exclusive_choice(engine):
    # The Moon and Venus both 0.5 deg past Saturn's degree across the boundary, equally placed: 20's "first in that
    # light" supplies no priority, so each row is unresolved -- but as ONE choice: both connected is definitely
    # false, exactly one is definitely true, and PN IV can never list both admitted at once.
    p = data(Saturn=(29.75, 0.1), Moon=(30.25, 13.0), Venus=(30.25, 1.0), Sun=(180.0, 1.0))
    with engine['doctrine'](engine['SAHL']):
        def rows():
            return {frozenset((r['p1'], r['p2'])): r for r in engine['_pairwise_configurations'](p)}
        moon = lambda: engine['_is_connected'](rows()[frozenset(('Saturn', 'Moon'))])
        venus = lambda: engine['_is_connected'](rows()[frozenset(('Saturn', 'Venus'))])
        assert engine['is_unresolved'](engine['evaluate_with_connection_uncertainty'](moon))
        assert engine['evaluate_with_connection_uncertainty'](lambda: bool(moon()) and bool(venus())) is False
        assert engine['evaluate_with_connection_uncertainty'](lambda: bool(moon()) or bool(venus())) is True
        assert engine['evaluate_with_connection_uncertainty'](lambda: bool(moon()) != bool(venus())) is True
        table = _pn4_rows(engine, p)
    saturn = [r for r in table if r.get('Planet') == 'Saturn']
    assert saturn
    for r in saturn:
        for v in r.values():
            if engine['is_unresolved'](v):
                for _name, alt in v.alternatives:
                    text = str(alt)
                    assert not ('Moon body connection' in text and 'Venus body connection' in text), text
