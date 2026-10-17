"""F3's ruled thresholds, complete judgments and actual prenatal pipeline."""
import math
import pytest
from conftest import assert_no_exception, make_app
from test_doctrine_fixtures import _governor, _sahl_chart, _syzygy_of


CASES = [
    ('Saturn', 5+59/60, 1, 'below adopted threshold', 'below adopted threshold'),
    ('Jupiter', 6, 1, 'yes', 'below adopted threshold'),
    ('Saturn', 10, -1, 'yes', 'below adopted threshold'),
    ('Jupiter', 15, 1, 'yes', 'yes'),
    ('Mars', 14+59/60, 1, 'below adopted threshold', 'below adopted threshold'),
    ('Mars', 15, 1, 'yes', 'below adopted threshold'),
    ('Mars', 18, 1, 'yes', 'yes'),
    ('Venus', 11+59/60, 1, 'below adopted threshold', 'below adopted threshold'),
    ('Mercury', 12, 1, 'yes', 'yes'),
    ('Venus', 15, -1, 'unresolved', 'unresolved'),
    ('Mercury', 15, 0, 'unresolved', 'unresolved'),
    ('Mercury', .5, 1, 'below adopted threshold', 'below adopted threshold'),
    ('Saturn', 180, 1, 'yes', 'yes'),
    ('Saturn', 180+1/60, 1, 'evening side', 'evening side'),
    ('Moon', 100, 13, 'unresolved', 'unresolved'),
    ('Moon', 180, 13, 'unresolved', 'unresolved'),
    ('Sun', 0, 1, 'not applicable', 'not applicable'),
    ('Saturn', 0, 1, 'below adopted threshold', 'below adopted threshold'),
]


@pytest.mark.parametrize('planet,gap,speed,first,second', CASES)
def test_astra_cases_both_levels(engine, planet, gap, speed, first, second):
    # Sun at 360 avoids loss of the nearest representable threshold values.
    result = engine['sahl_eastern_1_22'](planet, 360-gap, 360, speed)
    assert (result.level1.status, result.level2.status) == (first, second)
    if first == 'unresolved':
        with pytest.raises(TypeError):
            bool(result.level1.value)
    if planet == 'Mars' and gap == 15:
        assert 'Dykes fn 174' in result.level1.source
        assert result.level2.threshold == 18


@pytest.mark.parametrize('planet,threshold,level', [
    ('Saturn',6,1), ('Jupiter',6,1), ('Saturn',15,2), ('Jupiter',15,2),
    ('Mars',15,1), ('Mars',18,2), ('Venus',12,1), ('Mercury',12,2),
])
def test_unrounded_threshold_neighbors(engine,planet,threshold,level):
    for gap,expected in [(threshold-1e-9,False),(threshold,True),(threshold+1e-9,True)]:
        result=engine['sahl_eastern_1_22'](planet,360-gap,360,1)
        assert getattr(result, f'level{level}').value is expected


@pytest.mark.parametrize('gap,expected',[(math.nextafter(180,0),True),(180,True),(math.nextafter(180,360),False)])
def test_opposition_has_no_minute_tolerance(engine,gap,expected):
    assert engine['sahl_eastern_1_22']('Jupiter',360-gap,360,1).level1.value is expected


def test_wrap_and_unrelated_phase_unchanged(engine):
    f=engine['sahl_eastern_1_22']
    assert f('Saturn',359,5,1).level1.value is True
    assert f('Saturn',-1,365,1)==f('Saturn',359,5,1)
    before=engine['solar_phase']('Mercury',99.5,100,1)
    assert f('Mercury',99.5,100,1).level1.status=='below adopted threshold'
    assert before[1]=='eastern'


@pytest.mark.parametrize('planet,gap,speed,first,second', CASES)
def test_astra_cases_reach_governor_cells(engine,planet,gap,speed,first,second):
    data,cusps=_sahl_chart(0,Sun=360,**({planet:360-gap} if planet!='Sun' else {}))
    data[planet]['speed_in_lon']=speed
    syz=_syzygy_of(engine,0,'Diurnal')
    syz['rulers']={key:planet for key in syz['rulers']}
    result=engine['sahl_syzygy_governor'](syz,data,cusps,'Diurnal')
    cell=result['rows'][0]['Eastern (1.7, 3)']
    if first=='unresolved':
        assert engine['is_unresolved'](cell)
    elif first=='yes':
        assert cell=='yes (considered eastern)'
    elif first=='not applicable':
        assert cell=='not applicable — Sun'
    else:
        assert cell=='no — '+first


@pytest.mark.parametrize('mercury', [99.99,97,100])
def test_cazimi_or_burned_claimant_does_not_set_aside_stake_lord(engine,mercury):
    g=_governor(engine,Sun=100,Mars=130,Mercury=mercury)
    rows={r['Planet']:r for r in g['rows']}
    assert rows['Mercury']['Eastern (1.7, 3)']=='no — below adopted threshold'
    assert not rows['Mars']['Verdict'].startswith('set aside by 1.7, 3')


def test_real_pipeline_uses_natal_claimant_but_preserves_weighted_almuten(engine):
    jd,lat,lon=2281725.835625,-39.53098722184141,-20.349830411272734
    c=engine['calculate_traditional_chart_jd'](jd,lat,lon)
    syz=engine['calculate_prenatal_syzygy'](jd,lat,lon,c['houses'])
    before=dict(syz)
    g=engine['sahl_syzygy_governor'](syz,c['planetary_data'],c['houses'],c['sect'])
    assert c['sect']=='Diurnal' and syz['sect_diurnal'] is False
    assert g['triplicity_lord']=='Venus' and g['triplicity_sect']=='day'
    assert g['governor']=='unresolved between Mars and Venus'
    assert 'triplicity' in next(r for r in g['rows'] if r['Planet']=='Venus')['Claim on the degree (1.7, 3)']
    assert syz==before and (syz['almuten'],syz['almuten_score'])==('Saturn',7)


@pytest.mark.parametrize('sect,claimant',[('Diurnal','Sun'),('Nocturnal','Jupiter')])
def test_sagittarius_claimant_and_approximation_share_natal_sect(engine,sect,claimant):
    p,c=_sahl_chart(215,Sun=260,Jupiter=250,Mercury=270)
    syz=_syzygy_of(engine,255,'Nocturnal' if sect=='Diurnal' else 'Diurnal')
    g=engine['sahl_syzygy_governor'](syz,p,c,sect)
    assert g['triplicity_lord']==claimant
    assert 'triplicity' in next(r for r in g['rows'] if r['Planet']==claimant)['Claim on the degree (1.7, 3)']
    assert set(g['model_pick'].split(' / ')) <= {r['Planet'] for r in g['rows']}


def _moon_pair(engine,moon=100,venus=130):
    p,c=_sahl_chart(215,Sun=340,Moon=moon,Venus=venus)
    syz=_syzygy_of(engine,45,'Nocturnal')
    # Two named claimants to isolate 1.7's preference from other claims.
    syz['rulers'].update(domicile='Venus',exaltation='Moon',triplicity_night='Moon',term='-',face='-')
    return engine['sahl_syzygy_governor'](syz,p,c,'Nocturnal')


def test_unknown_moon_consequential_and_routes_shared(engine):
    g=_moon_pair(engine)
    assert engine['is_unresolved'](g['governor']) and g['unresolved']
    routes=dict(g['alternative_routes'])
    assert len(routes)==2
    assert {r['governor'] for r in routes.values()}=={'Moon','unresolved between Venus and Moon'}
    for label,value in g['governor'].alternatives:
        assert value==routes[label]['governor']
    for key in ('model_pick','model_how','how'):
        if engine['is_unresolved'](g[key]):
            assert all(value==routes[label][key] for label,value in g[key].alternatives)
    for i,row in enumerate(g['rows']):
        for key in ('Verdict','Model'):
            if engine['is_unresolved'](row[key]):
                assert all(value==routes[label]['rows'][i][key] for label,value in row[key].alternatives)


def test_unknown_moon_dropped_by_looking_does_not_infect_winner(engine):
    g=_moon_pair(engine,moon=60)
    assert g['governor']=='Venus' and g['unresolved'] is False
    assert engine['is_unresolved'](next(r for r in g['rows'] if r['Planet']=='Moon')['Eastern (1.7, 3)'])
    assert g['alternative_routes']==()


def test_known_winner_with_conditional_explanation_is_named(engine):
    g=_governor(engine,sect='Nocturnal',syzygy_lon=45,Sun=340,Moon=100,Jupiter=290,Venus=130)
    assert g['governor']=='Moon' and g['unresolved'] is False
    assert g['summary'].display_label.startswith('Moon — explanation conditional')
    assert all(route['governor']=='Moon' for _,route in g['alternative_routes'])


@pytest.mark.parametrize('speed,kind',[(0,'no (stationary)'),(0.003,'no (stationary)'),(-0.0031,'no (retrograde)'),(-1,'no (retrograde)'),(1,'yes'),(0.0031,'yes'),(-0.002,'no (stationary)')])
def test_direct_course_is_motion_states_one_rule(engine,speed,kind):
    """The row's own exact-zero rule is gone (owner, 2026-10-03): a planet
    at its station under STATION_SPEED_TOLERANCE is not direct, as every
    other motion reading has it, and nothing is left open for it."""
    g=_governor(engine,Sun=40,Mars=(130,speed),Mercury=45)
    cell=next(r for r in g['rows'] if r['Planet']=='Mars')['Direct (1.7, 4)']
    assert cell==kind
    assert not engine['is_unresolved'](g['governor'])
    assert g['alternative_routes']==()


def test_stationary_inferior_uses_one_direct_condition(engine):
    """A stationary inferior is not direct (the one rule), so 1.7, 4 drops
    it and the eastern preference 1.22, 7 leaves open for it opens no route."""
    g=_governor(engine,Sun=110,Mars=130,Mercury=(90,0))
    assert not engine['is_unresolved'](g['governor'])
    assert g['alternative_routes']==()
    row=next(r for r in g['rows'] if r['Planet']=='Mercury')
    assert row['Direct (1.7, 4)']=='no (stationary)'
    assert engine['is_unresolved'](row['Eastern (1.7, 3)'])
    assert row['Verdict']=='dropped by 1.7, 4'


def test_retrograde_inferior_unknown_preference_cannot_restore_eligibility(engine):
    g=_governor(engine,Sun=110,Mars=130,Mercury=(90,-1))
    assert not engine['is_unresolved'](g['governor'])
    assert g['alternative_routes']==()
    row=next(r for r in g['rows'] if r['Planet']=='Mercury')
    assert engine['is_unresolved'](row['Eastern (1.7, 3)'])
    assert row['Verdict']=='dropped by 1.7, 4'


@pytest.mark.parametrize('sun',[100,110])
def test_g03_20_and_two_qualifying_easterns_credit_actual_actor(engine,sun):
    g=_governor(engine,syzygy_lon=347,Sun=sun,Jupiter=70,Mercury=95,Venus=220)
    assert g['governor']=='Jupiter'
    assert "for the eastern Jupiter set aside Venus" in g['how']
    assert 'Jupiter, Mercury set aside' not in g['how']
    assert g['preference_eliminations']['Venus']==('Jupiter',)
    if sun==110:
        assert next(r for r in g['rows'] if r['Planet']=='Mercury')['Eastern (1.7, 3)']=='yes (considered eastern)'


def test_victors_page_shows_natal_label_and_separate_almuten_convention():
    at=make_app(page='victors').run()
    assert_no_exception(at,'F3 victors')
    cells=' '.join(str(df.value.to_dict()) for df in at.dataframe)
    assert '★ (Natal sect:' in cells
    assert "the lunation's sect, this app's convention for the degree's almuten" in cells
    assert 'UnresolvedResult(' not in cells
    prose=' '.join(n.value for n in at.main.markdown)
    assert "The star marks the triplicity lord selected by the nativity's sect" in prose
    assert 'Exactly zero speed' not in prose
    assert 'stationary, neither direct nor retrograde' in prose


@pytest.mark.parametrize('sect', ['Diurnal','Nocturnal'])
def test_conditional_governor_is_shared_by_page_findings_and_export(monkeypatch,sect):
    import engine as module
    from conftest import sync_engine_to_environment
    from streamlit.util import calc_hash
    sync_engine_to_environment()
    g=_moon_pair(vars(module))
    g['triplicity_sect']='day' if sect=='Diurnal' else 'night'
    monkeypatch.setattr(module,'sahl_syzygy_governor',lambda *args:g)
    at=make_app(page='victors').run()
    assert_no_exception(at,'conditional governor page')
    frames=[df.value for df in at.dataframe]
    syz=next(df for df in frames if 'Metric' in df and 'Triplicity Lords' in list(df['Metric']))
    values=dict(zip(syz['Metric'],syz['Value']))
    assert f'★ (Natal sect: {g["triplicity_sect"]})' in values['Triplicity Lords']
    governor=next(v for k,v in values.items() if k.startswith('Governor of'))
    assert 'Unresolved —' in governor and 'UnresolvedResult(' not in governor
    report=at.session_state['_analysis_export']['results']['Lunation and victors']
    exported=report['Prenatal Lunation (Syzygy)'][0]['rows']
    encoded=next(r['Value'] for r in exported if r['Metric'].startswith('Governor of'))
    assert encoded['result_type']=='UnresolvedResult'
    assert [(a['name'],a['value']) for a in encoded['alternatives']]==list(g['summary'].alternatives)
    candidates=report['Governor of the syzygy degree: the five lords under On Nativities 1.7, 3-7'][0]['rows']
    for original,encoded_row in zip(g['rows'],candidates):
        if module.is_unresolved(original['Verdict']):
            assert [(a['name'],a['value']) for a in encoded_row['Verdict']['alternatives']]==list(original['Verdict'].alternatives)
    assert 'UnresolvedResult(' not in at.session_state['_analysis_markdown']
    at._page_hash=calc_hash('findings')
    at.run()
    assert_no_exception(at,'conditional governor Findings')
    assert governor in [node.value for node in at.main.markdown]
