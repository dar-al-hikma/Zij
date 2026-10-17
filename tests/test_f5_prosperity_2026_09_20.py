"""G13/G14 specification fixtures; synthetic facts are explicitly stipulated.

The twelve historical examples remain observations in their original file.
"""
import ast
from pathlib import Path
import pytest


def chart(**changes):
    positions = dict(Sun=70., Moon=250., Venus=0., Jupiter=300., Saturn=150., Mars=210., Mercury=85.)
    positions.update(changes)
    speeds = dict(Sun=1., Moon=13., Venus=1., Jupiter=.1, Saturn=.03, Mars=.5, Mercury=1.2)
    return dict(planetary_data={p: dict(longitude=lon, speed_in_lon=speeds[p], latitude=0., distance=1.)
                                for p, lon in positions.items()}, ascendant=0., sect='Diurnal', lot_of_fortune=180.)


def assess(e, c, **kw):
    return e['_prosperity_lot_assessments'](c['planetary_data'], c['ascendant'], c['lot_of_fortune'], **kw)


def rows(e, c, key=None):
    result = e['evaluate_prosperity'](c)
    return result if key is None else [r for r in result if r['key'] == key]


def test_g13_angularity_does_not_certify_lifetime(engine):
    c = chart(Sun=300., Saturn=90., Mercury=0., Mars=180., Jupiter=150.)
    top = rows(engine,c)[0]
    assert top['key'] == 'high'
    assert '2.3, 2' not in top['Sahl']
    assert 'Lifelong happiness (2.3, 2): not met' in top['Ground']
    assert 'Mars by square' in top['Ground'] or '— square' in top['Ground']


def test_g13_clean_known_checks_leave_remaining_defects_unknown(engine):
    # Unit inputs stipulate angular/ray-free facts; no statement stipulates
    # exhaustive cleanliness. Saturn/Mercury in benefic domiciles, no contacts.
    n = chart(Sun=60., Saturn=350., Mercury=35., Mars=190.)['planetary_data']
    f = dict(lord='Saturn', house=1, under=False)
    g = dict(lord='Mercury', house=4, under=False)
    pairs = engine['_pairwise_configurations'](n)
    a = engine['_prosperity_lifetime'](f,g,n,pairs)
    assert engine['is_unresolved'](a.result)
    assert 'not fully assessed' in a.evidence


@pytest.mark.parametrize('offset,asc,expected', [(-3.,10.,False),(-3.,2.,True),(-5.,10.,False),(-5.001,10.,True)])
def test_g13_five_before_stake(engine,offset,asc,expected):
    c=chart(Sun=(asc+offset)%360., Jupiter=140., Saturn=220.)
    c.update(ascendant=asc, houses=[(asc+30*i)%360 for i in range(12)], lot_of_fortune=None)
    # For the previous sign choose Sun as first lord via the appropriate sect:
    # Pisces is water, so its first lord Venus is placed on the same point.
    if asc==2.:
        c['planetary_data']['Venus']['longitude']=(asc+offset)%360
    rr=[r for r in rows(engine,c,'by degree') if r['Ground'].startswith('Sun ' if asc!=2. else 'Venus ')]
    assert bool(rr) == expected
    if rr:
        assert ('2.3, 18' if asc==2. else '2.3, 17') in rr[0]['Sahl']
    assert 'raw quadrant' in rows(engine,c,'lords')[0]['Ground']


@pytest.mark.parametrize('distance,ref', [(0.,'48'),(15.,'48'),(15.000001,'49'),(30.,'49'),
    (30.000001,'50'),(45.,'50'),(45.000001,'51'),(89.999,'51'),(90.,'48')])
def test_g13_inclusive_grade_edges_and_next_axis(engine,distance,ref):
    # No obliquity: the tested distance is exactly representable longitude.
    c=chart(Sun=310.,Saturn=distance)
    c.update(armc=270.,obliquity=0.,geo_lat=0.,lot_of_fortune=None)
    # Direct helper edge test is independent of a change in triplicity.
    stake,arc=engine['_prosperity_ascension_from_stake'](distance,0.,270.,0.,0.)
    band=next((i for i,x in enumerate((15.,30.,45.)) if arc<=x),3)
    assert ('48','49','50','51')[band]==ref
    # The actual evaluator gets the same distance on a fixed first lord Saturn.
    g=rows(engine,c,'ascensions')
    assert len(g)==1 and 'first lord Saturn' in g[0]['Ground']
    assert '2.13, '+ref in g[0]['Sahl']


def test_g13_ninth_place_first_lord_receives_grade(engine):
    # Reader's geometry: MC in whole-sign ninth, first lord 8 RA degrees past MC.
    import swisseph as swe
    cusps, angles=swe.houses_armc(1.,55.,23.4393,b'B')
    lon=engine['_lon_with_right_ascension'](9.,23.4393)
    c=chart(Sun=310.,Saturn=lon)
    c.update(ascendant=angles[0],mc=angles[1],armc=1.,geo_lat=55.,obliquity=23.4393,lot_of_fortune=None)
    assert engine['get_wsh_house'](lon,c['ascendant'])==9
    g=rows(engine,c,'ascensions')
    assert len(g)==1 and '2.13, 48' in g[0]['Sahl']
    assert '8.0°' in g[0]['Ground']


@pytest.mark.parametrize('lat',[-55.,0.,55.])
def test_axis_is_zodiacally_preceding_and_agrees_with_existing_view(engine,lat):
    import swisseph as swe
    for armc in range(0,360,30):
        cusps, angles=swe.houses_armc(float(armc),lat,23.4393,b'B')
        asc,mc=angles[:2]
        axes=[asc,(mc+180)%360,(asc+180)%360,mc]
        names=['the Ascendant','the fourth','the seventh','the Midheaven']
        for lon in [*range(0,360,7), *axes]:
            name,arc=engine['_prosperity_ascension_from_stake'](lon,asc,armc,23.4393,lat,mc)
            idx=min(range(4),key=lambda i:(lon-axes[i])%360)
            assert name==names[idx]
            n={'Sun':dict(longitude=float(lon))}
            other=engine['evaluate_ascensional_bands'](n,asc,mc,23.4393,lat,'Diurnal')['rows'][0]
            expected=float(other['Ascensional distance'].split()[0])
            assert abs(arc-expected)<.005001
            if lon in axes:
                assert arc==pytest.approx(0.,abs=1e-10)


@pytest.mark.parametrize('house', [2,8,9])
def test_g13_excellent_excludes_second_eighth_ninth(engine,house):
    c=chart(Sun=310.,Saturn=(house-1)*30.+10.,Mercury=180.,Mars=((house-1)*30.+100.)%360)
    c['lot_of_fortune']=None
    rr=rows(engine,c)
    assert not any('2.17, 2' in r['Sahl'] and r['Ground'].startswith('Saturn,') for r in rr)
    if house in (2,8):
        assert any('2.3, 19' in r['Sahl'] and r['Ground'].startswith('Saturn,') for r in rr)


def test_g13_burned_primary_lord_still_has_falling_indication(engine):
    # Airy Sun selects Saturn/Mercury; Mercury in tenth is burned and squared.
    c=chart(Sun=301.,Mercury=298.,Saturn=208.)
    c['lot_of_fortune']=None
    rr=rows(engine,c)
    assert any('2.17, 2' in r['Sahl'] and r['Ground'].startswith('Mercury,') for r in rr)
    assert 'under the rays' in rows(engine,c,'lords')[0]['Ground']


@pytest.mark.parametrize('lot,venus,saturn,expect_lot,expect_lord',[
    (180.,300.,210.,False,True), # Lot averse Saturn; lord squared
    (0.,150.,240.,False,False), # Lot excellent but unafflicted; lord is Mars in sixth below
    (180.,270.,180.,True,True), # both complete branches; ray weakness is no veto
])
def test_g13_lot_and_lord_complete_subjects(engine,lot,venus,saturn,expect_lot,expect_lord):
    c=chart(Venus=venus,Saturn=saturn,Sun=venus+3.,Mars=150.)
    c['lot_of_fortune']=lot
    rr=[r for r in rows(engine,c) if '2.17, 3' in r['Sahl']]
    assert any(r['Ground'].startswith('the Lot of Fortune ') for r in rr)==expect_lot
    assert any(r['Ground'].startswith("the Lot's lord ") for r in rr)==expect_lord


@pytest.mark.parametrize('separation', [3.,10.])
def test_g14_side_is_not_easternization(engine,separation):
    c=chart(Sun=separation)
    a=assess(engine,c, lord_strength=True,witness_strength={'Jupiter':True})['2.3, 7']
    assert a.result is False
    checks=dict(a.clauses)
    assert checks['Venus easternizes (1.22, second level)'] is False
    if separation==3.:
        assert checks["Venus clear of the Sun's rays"] is False


@pytest.mark.parametrize('jupiter', [150.,270.])
def test_g14_external_witness_must_look_at_both(engine,jupiter):
    # Venus lord in Gemini, Lot Libra: Virgo looks at the lord only;
    # Capricorn looks at the Lot only. Neither witnesses both.
    c=chart(Venus=60.,Jupiter=jupiter,Sun=100.)
    a=assess(engine,c,lord_strength=True,witness_strength={'Jupiter':True})['2.3, 7']
    assert dict(a.clauses)['one external benefic witnessing both'] is False
    assert a.result is False


def test_g14_benefic_lord_cannot_witness_itself(engine):
    c=chart(Jupiter=0.,Venus=150.)
    c['lot_of_fortune']=240.
    a=assess(engine,c,lord_strength=True,witness_strength={'Jupiter':True,'Venus':True})['2.3, 7']
    assert dict(a.clauses)['one external benefic witnessing both'] is False


@pytest.mark.parametrize('lord_strength,witness_strength,unknown',[(None,None,True),(True,None,True),(None,True,True),(True,True,False)])
def test_g14_two_strength_clauses_and_one_sufficient_witness(engine,lord_strength,witness_strength,unknown):
    c=chart()
    kw={'lord_strength':lord_strength}
    if witness_strength is not None: kw['witness_strength']={'Jupiter':witness_strength}
    a=assess(engine,c,**kw)['2.3, 7']
    assert engine['is_unresolved'](a.result)==unknown
    if not unknown: assert a.result is True


@pytest.mark.parametrize('venus,lot',[(120.,180.),(120.,30.),(300.,180.),(300.,330.)])
def test_g14_fifth_eleventh_both_looking_cases(engine,venus,lot):
    c=chart(Venus=venus)
    c['lot_of_fortune']=lot
    # Taurus and Libra are both Venus's houses.
    if lot==330.: c['lot_of_fortune']=30.
    a=assess(engine,c)['2.3, 9']
    assert a.result is True
    rr=[r for r in rows(engine,c) if '2.3, 9' in r['Sahl'] and r['key'].startswith('lot ')]
    assert len(rr)==1
    looking=engine['_prosperity_looks'](venus,c['lot_of_fortune']) is not None
    assert ('more excellent' in rr[0]['Ground'])==looking


@pytest.mark.parametrize('sun,venus,jupiter,fortune_east,lord_east',[
    (10.,15.,300.,True,False), (70.,0.,120.,False,True),
    (70.,0.,300.,True,True), (350.,0.,120.,False,False)])
def test_g14_both_pronoun_readings(engine,sun,venus,jupiter,fortune_east,lord_east):
    c=chart(Sun=sun,Venus=venus,Jupiter=jupiter,Mars=90.)
    a=assess(engine,c)['2.16, 2']
    assert dict(a.readings)=={'fortune eastern':fortune_east,'lord eastern':lord_east}
    if fortune_east==lord_east: assert a.result is fortune_east
    else: assert engine['is_unresolved'](a.result)


def test_g14_ninth_place_benefic_is_not_excellent(engine):
    c=chart(Mars=90.,Jupiter=240.)
    a=assess(engine,c)['2.16, 2']
    assert a.result is False


def test_conditional_lot_is_shared_by_display_and_synthesis(engine):
    c=chart()
    rr=rows(engine,c)
    assert rr[0]['key']=='unresolved'
    assert engine['is_unresolved'](rr[0]['Class'])
    assert any(r['key']=='lot conditional' and engine['is_unresolved'](r['Class']) for r in rr)
    assert 'none of' not in rr[0]['Ground']
    assert any(isinstance(v,str) and 'class 6' in v for _,v in rr[0]['Class'].alternatives)
    assert any(engine['is_unresolved'](v) for _,v in rr[0]['Class'].alternatives)


def test_definite_failed_conjunct_beats_unknown_strength(engine):
    c=chart(Mars=90.)
    a=assess(engine,c)['2.3, 7']
    assert a.result is False
    assert not any(r['key']=='lot conditional' and '2.3, 7:' in r['Sahl'] for r in rows(engine,c))


def test_amended_other_fortune_keeps_predicate_and_names_witnesses(engine):
    c=chart(Sun=180.,Moon=0.,Saturn=210.,Mercury=150.,Jupiter=210.,Venus=210.)
    rr=rows(engine,c,'foreign')
    assert len(rr)==1
    assert "BA's reading (fn 268)" in rr[0]['Ground']
    assert 'referent' in rr[0]['Ground'] and 'open' in rr[0]['Ground']
    assert 'both fortunes looking' in rr[0]['Also'] and 'fn 267' in rr[0]['Also']
    c['planetary_data']['Jupiter']['longitude']=60.
    assert not rows(engine,c,'foreign')


def test_g13_eighth_place_witness_is_not_excellent(engine):
    c=chart(Mars=90.,Jupiter=210.)
    a=assess(engine,c)['2.16, 2']
    assert a.result is False


def test_unassessed_lot_does_not_activate_the_lot_step(engine):
    c=chart(Mercury=0.)
    c['ascendant']=60.
    rr=rows(engine,c)
    assert rr[0]['key']=='high'
    assert '2.3, 6:' not in rr[0]['Sahl']
    conditional=next(r for r in rr if r['key']=='lot conditional')
    assert 'Lot step is inactive' in conditional['Ground']
    assert engine['is_unresolved'](conditional['Class'])


def test_typed_assessment_agrees_in_table_detail_and_export(engine):
    import json
    from math import isfinite
    tree=ast.parse((Path(__file__).parents[1]/'app.py').read_text())
    names={'_display_result','_display_rows','_jsonable'}
    ns={**engine,'isfinite':isfinite}
    selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(selected)==3
    exec(compile(ast.Module(body=selected,type_ignores=[]),'display helpers','exec'),ns)
    rr=rows(engine,chart())
    displayed=ns['_display_rows'](rr)
    exported=ns['_jsonable'](rr)
    for raw,shown,saved in zip(rr,displayed,exported):
        assert shown['Class']==ns['_display_result'](raw['Class'])
        if engine['is_unresolved'](raw['Class']):
            assert saved['Class']['display']==shown['Class']
            assert saved['Class']['reason']==raw['Class'].reason
            assert saved['Class']['alternatives']
    assert 'UnresolvedResult(' not in json.dumps(displayed)
    assert 'UnresolvedResult(' not in json.dumps(exported)


@pytest.mark.parametrize('planet,threshold',[('Saturn',15.),('Jupiter',15.),('Mars',18.),('Venus',12.),('Mercury',12.)])
def test_lot_consumer_uses_second_level_threshold(engine,planet,threshold):
    c=chart(Sun=100.)
    n=c['planetary_data'];n[planet]['longitude']=100.-threshold
    assert engine['_prosperity_eastern'](planet,n) is True
    n[planet]['longitude']+=.000001
    assert engine['_prosperity_eastern'](planet,n) is False


def test_lot_consumer_preserves_lunar_unknown_and_solar_inapplicability(engine):
    n=chart()['planetary_data']
    assert engine['is_unresolved'](engine['_prosperity_eastern']('Moon',n))
    assert engine['is_unresolved'](engine['_prosperity_eastern']('Sun',n))   # G14-A: no criterion for the Sun as lord -- unassessed, never a failure
    assert engine['sahl_eastern_1_22']('Sun',70.,70.,1.).level2.status=='not applicable'


# --- the F5 blind check's four defects (2026-09-20), pinned -------------------------------------------------------

def _lord(engine, n, lord):
    """The lord-facts dict _prosperity_lifetime reads (house by whole sign, the rays fact)."""
    lon = n['planetary_data'][lord]['longitude']
    phase = engine['solar_phase'](lord, lon, n['planetary_data']['Sun']['longitude'],
                                  n['planetary_data'][lord].get('speed_in_lon'), source='Sahl')[0]
    return {'lord': lord, 'house': engine['get_wsh_house'](lon, n['ascendant']),
            'under': phase in ('Burned', 'Under the rays')}


def _life(engine, n, a, b):
    return engine['_prosperity_lifetime'](_lord(engine, n, a), _lord(engine, n, b), n['planetary_data'],
                                          engine['_pairwise_configurations'](n['planetary_data']))


def test_lord_in_a_malefics_sign_is_not_afflicted_by_that_alone(engine):
    # Introduction 3, 81's first configuration is the infortune WITH the planet in one sign (fn 93, assembling),
    # not the planet standing in the infortune's domicile: Mercury 10 Capricorn with Saturn 0 Taurus (a trine by
    # sign, 110 deg, separating) is clear of Saturn.
    n = chart(Sun=300., Mercury=280., Saturn=30., Mars=200., Venus=290., Jupiter=120., Moon=60.)
    life = _life(engine, n, 'Mercury', 'Venus')
    clause = next(v for name, v in life.clauses if name.startswith('Mercury clear of Saturn'))
    assert clause is True


def test_affliction_names_the_configuration_met(engine):
    n = chart(Sun=300., Mercury=280., Saturn=190., Mars=10., Venus=290., Jupiter=120., Moon=60.)   # Mars square Mercury
    life = _life(engine, n, 'Mercury', 'Venus')
    name, value = next((name, v) for name, v in life.clauses if name.startswith('Mercury clear of Mars'))
    assert value is False and name.endswith('square')


def test_middle_state_is_named_when_every_declared_check_passes(engine):
    # Both lords angular, unafflicted, direct, clear of the rays, not in fall: the ruling's middle state is named
    # in the headline, the promise never presented as verified.
    n = chart(Sun=100., Jupiter=10., Venus=190., Saturn=45., Mars=160., Mercury=90., Moon=40.)   # both infortunes averse to both lords
    life = _life(engine, n, 'Jupiter', 'Venus')
    assert life.declared_checks_pass, life.evidence
    assert engine['is_unresolved'](life.result)
    assert life.result.reason.startswith('satisfied under the declared checks')


def test_sun_as_the_lots_lord_is_unassessed_not_failed(engine):
    n = chart(Sun=130., Moon=40., Jupiter=10., Venus=190., Saturn=250., Mars=160., Mercury=120.)
    value = engine['_prosperity_eastern']('Sun', n['planetary_data'])
    assert engine['is_unresolved'](value)
    assert 'Sun' in value.reason
