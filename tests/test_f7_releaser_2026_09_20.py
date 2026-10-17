"""Ruled F7 boundaries and agreement between operative consumers."""
from datetime import date
import pytest
from test_doctrine_fixtures import pdata
from conftest import make_app, assert_no_exception


@pytest.mark.parametrize('asc,degree,lord,preferred', [
    (26,24,20,True),(26,24,21,True),(26,24,22,True),(26,24,6,True),
    (3,2,357,False),(3,2,358,False),(3,2,359,False),
    (65,24,20,False),
])
@pytest.mark.parametrize('lot',[False,True])
def test_preference_uses_rising_sign_not_strength(engine,asc,degree,lord,preferred,lot):
    bound=engine['get_essential_rulers'](degree)['term']
    other='Venus' if bound!='Venus' else 'Jupiter'
    pd=pdata(**{bound:lord,other:100,'Sun':140})
    cusps=[(asc+i*30)%360 for i in range(12)]
    # Use actual candidate geometry, retaining its potentially cadent division.
    cand=engine['_sahl_examine_candidate']('the Lot of Fortune' if lot else 'probe', degree,
        pd,cusps,'Diurnal',tuple(range(1,13)),unit='place' if lot else 'division')
    cand['both_at_once']=False
    cand['looking']=[('bound',bound,'in it'),('house',other,'square'),('face',other,'square')]
    rows=engine['_sahl_rank_house_master'](cand,pd,cusps)
    actual=next(r for r in rows if r['Planet']==bound)
    assert ('stronger than the others' in actual['Rank']) is preferred
    assert rows[0]['Planet']==(bound if preferred else other)


@pytest.mark.parametrize('lon,expected',[(1,True),(61,True),(31,False),(359,False)])
def test_fortune_looking_is_sign_based(engine,lon,expected):
    assert bool(engine['_sahl_looks'](lon,2)) is expected


@pytest.mark.parametrize('planet',['Mars','Saturn'])
def test_direction_target_policies_together(engine,planet):
    other='Saturn' if planet=='Mars' else 'Mars'
    pd=pdata(**{planet:0,other:230,'Sun':310,'Moon':200})
    direction=engine['sahl_house_master_direction']
    rows=direction(pd,planet,23.44,30,span_years=360)
    targets={r['Target'] for r in rows}
    assert len(targets)==8
    assert f"{planet}'s body" not in targets
    assert not any('trine' in t for t in targets)
    assert {f"{planet}'s opposition",f"{planet}'s square (left)",f"{planet}'s square (right)"}<=targets
    left=next(r for r in rows if r['Target']==f"{planet}'s square (left)")
    expected=(engine['_oblique_ascension'](90,23.44,30)-engine['_oblique_ascension'](0,23.44,30))%360
    assert float(left['Arc (years)'])==pytest.approx(expected,abs=.005)
    assert abs(expected-90)>1
    assert any(r['Target']==f"{planet}'s square (left)" for r in direction(pd,planet,23.44,0))
    stand=direction(pd,'Moon',23.44,0,span_years=360,target_policy='stand-in')
    assert not any('Sun' in r['Target'] for r in stand)
    father=direction(pd,planet,23.44,0,span_years=360,target_policy='father',sun_target=False,target_planets=(other,))
    assert all(other in r['Target'] for r in father)
    assert any('Sun' in r['Target'] for r in rows)


@pytest.mark.parametrize('planet',['Moon','Mercury','Saturn'])
@pytest.mark.parametrize('gap',[.999999,1,1.000001,7,10,16])
@pytest.mark.parametrize('side',[-1,1])
def test_no_indication_blocks_fallback_including_moon(engine,planet,gap,side):
    """1.21, 13's refusal is keyed on the BURNED band alone (the owner's narrowing of L8-G29-A on the F7 check):
    a house-master under the rays but not burned keeps 1.20's grant (18, 21, 23b, 25, 33, 34 stay reachable);
    a burned one indicates nothing, 1.20's would-be indication shown beside the refusal, and the JN fallback
    is not consulted because Sahl is not silent."""
    pd=pdata(Sun=100,**{planet:100+side*gap})
    pd[planet]['speed_in_lon']=1
    cusps=[i*30 for i in range(12)]
    phase=engine['solar_phase'](planet,pd[planet]['longitude'],100,1,source='Sahl')[0]
    rays=engine['sahl_under_rays'](planet,pd[planet]['longitude'],100,1)
    result=engine['sahl_house_master_years'](planet,pd,cusps,'Diurnal',{})
    if phase=='Burned':
        assert result['grade']=='no indication'
        assert result['years'] is None and result['sentence']=='1.21, 13'
        assert 'The JN fallback is not consulted: Sahl is not silent' in result['text']
        assert '1.20 would have indicated:' in result['text']
        assert engine['jn_years_fallback'](planet,pd,cusps,'Diurnal',{}) is None
    else:
        assert result.get('indication')!='void'
        if rays:
            assert result['sentence']!='1.21, 13'   # under the rays but not burned: 1.20 governs


def test_moon_gate_keeps_own_numeric_interval(engine):
    pd=pdata(Sun=10,Moon=10.5,Mercury=12,Venus=13,Mars=14,Jupiter=15,Saturn=16)
    c=engine['_sahl_examine_candidate']('the Moon',10.5,pd,[i*30 for i in range(12)],'Nocturnal',tuple(range(1,13)),'Moon')
    assert not c['fit']
    assert '1.19, 6' in c['why']


def chart(engine):
    return engine['calculate_traditional_chart_jd'](2250406.625914352,18.827745849999175,-35.78280106166059)


@pytest.mark.parametrize('point',['ascendant','mc','ic','planet'])
def test_pn4_dispatch_matches_existing_calculators(engine,point):
    c=chart(engine);lon={'ascendant':c['ascendant'],'mc':c['mc'],'ic':(c['mc']+180)%360,'planet':c['planetary_data']['Moon']['longitude']}[point]
    r=engine['pn4_point_distribution'](c,lon,30.3,point)
    if point=='ascendant':
        segs=engine['pn4_distribution_from_ascendant'](c['planetary_data'],lon,c['obliquity'],c['geo_lat'])
    elif point in ('mc','ic'):
        segs=engine['pn4_distribution_from_meridian'](c['planetary_data'],c['mc'],c['obliquity'],start_lon=lon,label=point)
    else:
        segs=engine['pn4_distribution_by_semi_arcs'](c['planetary_data'],lon,c['obliquity'],c['geo_lat'],c['armc'],label=point)
    assert r['segments']==segs
    assert r['current']==engine['pn4_distribution_at_age'](segs,30.3)
    assert r['distributor']==r['current']['distributor']
    assert r['partner']==r['current']['partner']


def test_absent_is_not_unavailable_and_retains_ascendant_share(engine,monkeypatch):
    c=chart(engine)
    absent=engine['pn4_releaser_direction'](c,{'releaser':None,'longitude':None},30)
    assert absent['status']=='absent'
    monkeypatch.setitem(engine,'pn4_distribution_by_semi_arcs',lambda *a,**k:None)
    unavailable=engine['pn4_releaser_direction'](c,{'releaser':'the Moon','longitude':c['planetary_data']['Moon']['longitude']},30)
    assert unavailable['status']=='unavailable'
    assert unavailable['distributor'] is None
    for record,counted in [(absent,'yes'),(unavailable,'no')]:
        rows,summary=engine['pn4_governor']('Mars','Saturn','Venus','',None,None,0,
            releaser_note=record['note'],releaser_status=record['status'])
        assert rows[2]['Counted']=='no' and rows[3]['Counted']==counted
        assert len(rows)==8


def test_ascendant_releaser_keeps_two_roles_one_partner(engine):
    rows,summary=engine['pn4_governor']('Mars','Saturn','Venus','',None,None,0,
        releaser_distributor='Saturn',releaser_partner='Venus',releaser_status='available')
    assert rows[1]['Planet']==rows[2]['Planet']=='Saturn'
    assert summary['tally']['Saturn']==2 and summary['tally']['Venus']==1
    assert len(rows)==8


@pytest.mark.parametrize('age',[42,48])
def test_days_have_source_specific_origins(engine,age):
    natal=chart(engine)
    rev=engine['calculate_traditional_chart_jd'](natal['julian_day']+age*365.25,natal['geo_lat'],natal['geo_lon'])
    points=engine['pn4_day_point_origins'](natal,rev)
    for key in ('planet:Moon','house:2','lot:father'):
        p=points[key]
        if key=='planet:Moon':
            assert p['natal']==natal['planetary_data']['Moon']['longitude']
            assert p['revolution']==rev['planetary_data']['Moon']['longitude']
        elif key=='house:2':
            assert p['natal']==natal['houses'][1] and p['revolution']==rev['houses'][1]
        else:
            for field,c in [('natal',natal),('revolution',rev)]:
                assert p[field]==engine['lot_by_id']('father',c['planetary_data'],c['ascendant'],c['houses'],c['sect'])
        assert engine['pn4_profect'](p['natal'],age)!=engine['pn4_profect'](p['revolution'],age)


def test_elapsed_direction_column_keeps_integer_profection(engine):
    c=chart(engine)
    early=engine['pn4_turning_rows'](c,1,elapsed=1.1)
    later=engine['pn4_turning_rows'](c,1,elapsed=1.99)
    assert [r['Turned to'] for r in early]==[r['Turned to'] for r in later]
    assert any(a['Directed a year per degree']!=b['Directed a year per degree'] for a,b in zip(early,later))


def test_releaser_page_discloses_both_methods():
    at=make_app(page='releaser');at.session_state['_target_date']='2026-09-17';at.run()
    assert_no_exception(at)
    text='\n'.join(x.value for x in at.markdown)
    assert 'This testimony uses Sahl' in text
    assert 'unrestricted same-sign looking' in text


@pytest.mark.parametrize('jd,lat,lon,birth,target,kind',[
    (2321798.722928241,33.0336183671692,49.43502262299478,date(1644,10,7),date(1684,10,8),'off-axis'),
    (2281725.835625,-39.531,-20.3498,date(1535,1,10),date(1555,1,11),'ascendant'),
    (2261405.5376157407,-14.995304061019176,105.44351302466606,date(1479,5,24),date(1509,9,1),'absent'),
])
def test_readers_full_pipeline_fixtures(engine,jd,lat,lon,birth,target,kind):
    c=engine['calculate_traditional_chart_jd'](jd,lat,lon)
    b=engine['pn4_timing_bundle'](c,lat,lon,birth,target,engine['PN4_MONTHLY_TURN_OPTIONS'][0])
    r=b['pn4_releaser'];rows,tally=b['governor']
    if kind=='off-axis':
        assert r['identity']=='the Sun' and r['axis'] is None
        sun=next(x for x in b['angle_planets'] if x['planet']=='Sun')
        assert r['current']==sun['current']
        assert r['distributor']!=b['releaser_current']['distributor']
        assert rows[2]['Planet']==r['distributor']
    elif kind=='ascendant':
        assert r['identity']=='the Ascendant'
        assert rows[1]['Planet']==rows[2]['Planet']
        assert r['current']==b['current']
    else:
        assert r['status']=='absent' and b['standin_moon'] is not None
        assert rows[2]['Counted']=='no'
        assert all('Sun' not in x['Target'] for x in b['standin_moon'])
        if b['current']['partner']:
            assert rows[3]['Counted']=='yes' and rows[3]['Planet'].startswith(b['current']['partner']+';')


def test_c1_elapsed_venus_boundary(engine):
    c=engine['calculate_traditional_chart_jd'](2174111.0729166665,43.7792,11.2463)
    elapsed=(engine['civil_to_jd'](1241,11,19,12)-c['julian_day'])/engine['PN4_DIRECTION_YEAR_DAYS']
    rows=engine['pn4_turning_rows'](c,1,elapsed=elapsed)
    old=engine['pn4_turning_rows'](c,1)
    row=next(r for r in rows if r['Point']=='Venus')
    previous=next(r for r in old if r['Point']=='Venus')
    assert 'distributor Saturn' in row['Directed a year per degree']
    assert 'distributor Mars' in previous['Directed a year per degree']


def test_both_above_fullness_names_fallback(engine,monkeypatch):
    monkeypatch.setitem(engine,'_sin_altitude',lambda *a:1)
    r=engine['sahl_prenatal_meeting_and_fullness'](2174111.0729166665,43.7792,11.2463)
    assert r['fullness']['degree_of']=='the Moon (both above, the default)'


def test_days_selector_shows_natal_mighty_and_keeps_saved_choice():
    at=make_app(page='days');at.session_state['_target_date']='1288-09-17'
    at.session_state['pn4_day_point']="Moon"
    at.session_state['_pn4_day_point']="Moon"
    at.run();assert_no_exception(at)
    text='\n'.join(x.value for x in at.markdown)
    assert '**Small days from the revolution\'s Moon**' in text
    assert '**Mighty days from the natal Moon profected**' in text
    at.run();assert_no_exception(at)
    assert at.session_state['pn4_day_point']=="Moon"


@pytest.mark.parametrize('fortune,expected',[(1,True),(61,True),(31,False),(359,False),(None,False)])
def test_ascendant_fallback_one_fortune_with_other_conditions(engine,fortune,expected):
    pd=pdata(Sun=100,Moon=200,Mercury=110,Mars=20,Saturn=300,Venus=31)
    if fortune is not None:
        pd.update(pdata(Jupiter=fortune))
    c=engine['_sahl_ascendant_candidate'](pd,2,[i*30 for i in range(12)],'Diurnal')
    assert c['fit'] is expected


def test_void_reference_cell_carries_reason_not_count_not_restated(engine):
    pd=pdata(Sun=100,Moon=105,Mercury=110,Venus=130,Mars=200,Jupiter=250,Saturn=300)
    rows=engine['evaluate_planetary_years_display'](pd,[i*30 for i in range(12)],0,'Diurnal',{},supplement=True)
    row=next(r for r in rows if r['Planet']=='Moon')
    assert row['On Nativities 1.20 grants (as house-master)'].startswith('1.21, 13: burned, no indication')
    assert 'count not restated' not in row['On Nativities 1.20 grants (as house-master)']
    assert next(v for k,v in row.items() if k.startswith('Where On Nativities 1.20'))=='-'


def test_pn4_releaser_table_is_exported_from_same_rows():
    at=make_app(page='releaser');at.session_state['_target_date']='1270-05-24';at.run();assert_no_exception(at)
    tables=at.session_state['_analysis_export']['results']['Prediction']
    heading='The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)'
    entry=next(t for t in tables[heading] if t.get('citation')=='PN IV III.1, 12; IX.9, 4-5')
    assert entry['rows']
    assert any(df.value.to_dict('records')==entry['rows'] for df in at.dataframe)
