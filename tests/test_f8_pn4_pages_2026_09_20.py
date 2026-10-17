"""F8 ruled state, identity, tie and endpoint regressions."""
from datetime import datetime, date, timedelta
from pathlib import Path
import pytest
from test_doctrine_fixtures import pdata
from conftest import make_app, assert_no_exception

@pytest.fixture(autouse=True)
def isolated_readings(engine):
    run=engine['_RUN'];saved=dict(run.__dict__)
    run.__dict__.clear()
    yield
    run.__dict__.clear();run.__dict__.update(saved)


START = 184.55


def direction(e, pd, **kw):
    return e['_pn4_distribute'](pd, START, lambda x: x, 100, 'Saturn', **kw)


@pytest.mark.parametrize('method', ['_pn4_distribute','pn4_distribution_from_ascendant',
    'pn4_distribution_from_meridian','pn4_distribution_by_semi_arcs','sahl_releaser_distribution',
    'pn4_small_days','pn4_mighty_days'])
def test_identity_in_every_wrapper(engine, method):
    e=engine; pd=pdata(Saturn=START)
    calls={
        '_pn4_distribute':lambda sig:e[method](pd,START,lambda x:x,100,'Saturn',significator=sig),
        'pn4_distribution_from_ascendant':lambda sig:e[method](pd,START,23.44,30,significator=sig),
        'pn4_distribution_from_meridian':lambda sig:e[method](pd,START,23.44,start_lon=START,label='Saturn',significator=sig),
        'pn4_distribution_by_semi_arcs':lambda sig:e[method](pd,START,23.44,30,100,significator=sig),
        'sahl_releaser_distribution':lambda sig:e[method](pd,START,23.44,30,significator=sig),
        'pn4_small_days':lambda sig:e[method](pd,START,'Saturn',significator=sig),
        'pn4_mighty_days':lambda sig:e[method](pd,START,'Saturn',significator=sig),
    }
    assert calls[method]('Saturn')[0]['partner'] is None
    axis=calls[method](None)[0]
    assert axis['partner']=='Saturn'
    assert 'at the starting degree' in axis['partner_from']
    assert 'behind' not in axis['partner_from']


@pytest.mark.parametrize('contacts,expected',[
    ([(START,'body','Saturn','body')],None),
    ([(183+1/6,'ray','Moon','trine'),(START,'body','Saturn','body')],'Moon'),
    ([(183+1/6,'ray','Moon','trine'),(START,'body','Saturn','body'),(START,'body','Mars','body')],'Mars'),
    ([(180,'ray','Jupiter','trine'),(180-1/60,'ray','Mars','square')],'Jupiter'),
    ([(180-1/60,'body','Mars','body')],None),
    ([(START,'ray','Saturn','square')],None),
])
def test_astra_opening_contacts(engine,monkeypatch,contacts,expected):
    monkeypatch.setitem(engine,'pn4_bodies_and_rays',lambda pd:contacts)
    seg=direction(engine,{},significator='Saturn')[0]
    assert seg['partner']==expected


def test_distributor_unchanged_and_later_self_ray_allowed(engine):
    e=engine; start=28.
    seg=e['_pn4_distribute'](pdata(Saturn=start),start,lambda x:x,100,'Saturn',significator='Saturn')
    assert seg[0]['distributor']=='Saturn' and seg[0]['partner'] is None
    assert any(s['partner']=='Saturn' and s['from']>0 and s['partner_aspect']!='body' for s in seg)


@pytest.mark.parametrize('method',['pn4_mighty_days','pn4_small_days'])
def test_days_whole_bound_window_identity(engine,method):
    pd=pdata(Saturn=183.)
    assert engine[method](pd,START,'Saturn')[0]['partner']=='Saturn'
    assert engine[method](pd,START,'Saturn',significator='Saturn')[0]['partner'] is None
    # The sign contains Moon, but this bound does not: keep the bound window.
    start=190.
    pd=pdata(Saturn=start,Moon=183.)
    assert engine[method](pd,start,'Saturn',significator='Saturn')[0]['partner'] is None


@pytest.mark.parametrize('reverse',[False,True])
def test_tie_preserved_until_next_meeting(engine,monkeypatch,reverse):
    contacts=[(184.,'body','Mars','body'),(184.,'ray','Venus','trine'),(187.,'body','Moon','body')]
    monkeypatch.setitem(engine,'pn4_bodies_and_rays',lambda pd:contacts[::-1] if reverse else contacts)
    segs=direction(engine,{},significator='Saturn'); tie=segs[0]['partner']
    # The owner's ruling 52 (2026-10-06), after rulings 14, 19 and 33
    # (PN IV III.1, 50): the two met at one degree are partners together, each
    # read by its own nature; the assertions about the tie follow.
    assert not engine['is_unresolved'](tie)
    assert set(tie)=={'Mars','Venus'}
    assert 'Venus by trine' in segs[0]['partner_from'] and 'behind' in segs[0]['partner_from']
    assert all(s['partner']==tie for s in segs if s['from']<187-START)
    assert engine['pn4_distribution_at_age'](segs,187-START)['partner']=='Moon'
    assert bool(tie) is True
    rows=engine['_pn4_distribution_rows'](segs,segs[0])
    assert str(rows[0]['Partner'])=='Mars and Venus'
    assert 'Mars and Venus' in engine['generate_distribution_strip_svg'](segs,0)
    assert 'UnresolvedResult(' not in engine['generate_distribution_strip_svg'](segs,0)
    typ=engine['pn4_static_type']('Mars',tie)
    assert not engine['is_unresolved'](typ[0])
    assert set(typ[0])=={3,6}
    gov,summary=engine['pn4_governor']('Saturn','Mars',tie,None,'Jupiter','Sun',30,
        releaser_status='absent')
    assert gov[3]['Planet'].startswith('Mars and Venus;')
    # The Ascendant's share is retained: the count is 'yes', and each
    # partner is credited.
    assert gov[3]['Counted']=='yes'
    assert summary['counted']==6
    assert 'conditional_counted' not in summary
    assert 'tied' not in summary['text']
    assert summary['tally']['Mars']==2 and summary['tally']['Venus']==2
    assert not engine['is_unresolved'](summary['tally']['Mars'])
    # A releaser whose partner is neither planet of the pair: 'not one
    # partner to both' -- a settled 'no', nothing open in the tally, no
    # "unresolved" sentence (the check's finding 20).
    gov2,summary2=engine['pn4_governor']('Saturn','Mars',tie,None,'Jupiter','Sun',30,
        releaser_distributor='Mercury',releaser_partner='Moon')
    assert 'not one partner to both' in gov2[3]['Planet']
    assert gov2[3]['Counted']=='no'
    assert summary2['counted']==6
    assert 'conditional_counted' not in summary2
    assert not engine['is_unresolved'](summary2['text'])
    assert 'unresolved' not in summary2['text']
    # A releaser whose partner is one planet of the pair: that one is the
    # partner to both, credited; settled.
    gov3,summary3=engine['pn4_governor']('Saturn','Mars',tie,None,'Jupiter','Sun',30,
        releaser_distributor='Mercury',releaser_partner='Mars')
    assert gov3[3]['Counted']=='yes'
    assert gov3[3]['Planet'].split(';')[0]=='Mars'
    assert 'unresolved' not in summary3['text']
    # Neither planet is selected alone: both are the opening partners.
    assert tuple(segs[0]['partner'])==('Mars','Venus')


@pytest.mark.parametrize('eps',[0.,5e-10,1e-9,2e-9])
def test_no_epsilon_hole(engine,eps):
    segs=engine['pn4_distribution_from_meridian'](pdata(Sun=40+eps),40.,23.44)
    assert segs[0]['from']==0.
    assert engine['pn4_distribution_at_age'](segs,0.) is not None
    assert all(a['to']==b['from'] for a,b in zip(segs,segs[1:]))


@pytest.mark.parametrize('t,day,hour',[(0,'Aries','Aries'),(1/12,'Aries','Aries'),(5/24,'Aries','Taurus'),
    (1,'Aries','Leo'),(59/24,'Aries','Pisces'),(2.5,'Taurus','Taurus'),(30,'Aries','Aries')])
def test_way_two_declared_origin(engine,t,day,hour):
    rows=engine['pn4_ix7_month_days'](t,[('zero',0.),('late',29.)])
    for row in rows:
        assert row["Way 2: day's sign (2½-day blocks)"]==day
        assert row["Way 2: hour's sign (5-hour steps)"]==hour
        assert 'bound of' not in row['Way 1: a day per degree, now at']
    assert rows[1]['Way 1: a day per degree, now at']==engine['get_degree_string']((29+t%30)%360)


@pytest.mark.parametrize('by_ray',[True,False])
def test_type_two_fortune_conditional_sentence(engine,by_ray):
    key,note=engine['pn4_bound_transit_sentence'](2,'fortune',by_ray)
    assert key==34 and "33's condition" in note and 'not judged' in note
    assert engine['PN4_BOUND_TRANSIT_SENTENCES'][key]==('III.2, 34-35','it indicates a hindered adversity',False)
    assert engine['pn4_bound_transit_sentence'](6,'fortune',False)[0]==43
    assert engine['pn4_bound_transit_sentence'](2,'infortune',True)[0] is None


def test_indicator_fifteen_uses_recorded_heavy_applicant(engine):
    pd=pdata(Mercury=(0,-.1),Venus=(5,-1.))
    chart={'ascendant':65.,'planetary_data':pd}
    rows=engine['pn4_indicator_relationships'](chart,chart,65.)
    r=next(r for r in rows if r['Partner']=='Venus')
    assert r['Connected'] is True and r['Applicant']=='Venus'
    assert 'Venus applies to the indicator' in r['Description']


@pytest.mark.parametrize('profile',['Sahl',"Abu Ma'shar"])
def test_indicator_fifteen_agrees_with_f6(engine,profile):
    engine['set_readings'](CONNECTION_PROFILE=profile)
    pd=pdata(Sun=(130,1),Mars=(245.4,.5),Mercury=(140,1.2),Venus=(175,1),Moon=(50,12),Jupiter=(40,.1),Saturn=(190,.03))
    chart={'ascendant':185.,'planetary_data':pd}
    records=engine['pn4_indicator_relationships'](chart,chart,5.)
    pairs={frozenset((r['p1'],r['p2'])):r for r in engine['_pairwise_configurations'](pd)}
    for r in records:
        pr=pairs[frozenset((r['Indicator'],r['Partner']))]
        connected=engine['_is_connected'](pr)
        assert r['Connected']==connected
        assert r['State']==engine['_connection_state'](pr,connected)
    sun=next(r for r in records if r['Role']=='Lord of the terminal sign' and r['Partner']=='Sun')
    assert 'separating from Sun by trine; 4.6° past exact' in sun['Description']
    assert 'aversion' not in sun['Description']


def test_roles_preserved_and_house_lordships(engine):
    pd=pdata(Sun=130,Moon=50,Mercury=140,Venus=175,Mars=254,Jupiter=40,Saturn=190)
    chart={'ascendant':185.,'planetary_data':pd}
    sr={'ascendant':35.,'planetary_data':pd}
    rs=engine['pn4_indicator_relationships'](chart,sr,275.)
    get=lambda role,partner: next(r for r in rs if r['Role']==role and r['Partner']==partner)
    assert get('Lord of the natal Ascendant','Sun')['Ruled houses']==(11,)
    assert get('Lord of the natal Ascendant','Moon')['Ruled houses']==(10,)
    assert get('Lord of the terminal sign','Mercury')['Ruled houses']==(6,9)
    assert get('Lord of the natal Ascendant','Sun')['Indicator']==get("Lord of the revolution's Ascendant",'Sun')['Indicator']=='Venus'
    same=engine['pn4_indicator_relationships'](chart,chart,185.)
    assert len({r['Ruled houses'] for r in same if r['Partner']=='Sun'})==1


@pytest.mark.parametrize('stake',[0,3,6,9])
@pytest.mark.parametrize('offset,admitted',[(-5.000001,False),(-5.,True),(-4.999999,True),(0,True)])
def test_stakes_allowance_only_at_four_degrees(engine,stake,offset,admitted):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    c['planetary_data']['Mercury']['longitude']=(c['houses'][stake]+offset)%360
    rows=engine['pn4_i7_planets'](c,c)
    r=next(r for r in rows if r['Planet']=='Mercury' and r['Chart']=='root')
    house=stake+1 if admitted else (stake or 12)
    assert r['Stakes (23)'].startswith(f'house {house},')


@pytest.mark.parametrize('node,age',[('Head',71),('Tail',74)])
def test_fardar_nodes_in_image(engine,node,age):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    rows,_=engine['pn4_revolution_image'](c,c,{'longitude':c['ascendant']},age,None,{'lord':node,'sub_lord':None},None,42.3314)
    r=next(r for r in rows if r['Point']==node+', lord of the fardar')
    assert r['Chart']=='root' and r['Source']=='I.6, 6; IV.1, 8'
    assert r['Position']==engine['get_degree_string']((c['planetary_data']['North Node']['longitude']+(180 if node=='Tail' else 0))%360)
    assert not any('dividing the fardar' in r['Point'] for r in rows)


def test_dykes_planetary_directions_do_not_self_partner(engine):
    c=engine['calculate_traditional_chart_jd'](2455444.3021875,44.98,-93.26361)
    for planet in engine['PN4_SEVEN']:
        r=engine['pn4_point_distribution'](c,c['planetary_data'][planet]['longitude'],0,planet,significator=planet)
        assert r['segments'][0]['partner']!=planet
        if planet=='Saturn':
            assert r['segments'][0]['partner']=='Jupiter'
            assert r['segments'][0]['partner_aspect']=='opposition'
            assert "00° Lib 32'" in r['segments'][0]['partner_from']


@pytest.mark.parametrize('page',['timing','releaser','days'])
def test_opening_ties_render_and_export(engine,monkeypatch,page):
    at=make_app(page=page)
    # A target inside the distribution's span, so the tied segment IS the
    # current one on every page (the default target of 2026 on the 1240
    # chart lies past the 120-year table and left the tie unexercised).
    at.session_state['_target_mode']='Date'
    at.session_state['_target_date']='1250-05-23'
    import engine as module
    original=module._pn4_distribute
    def tie_direction(*args,**kwargs):
        segs=original(*args,**kwargs)
        names=("Mars by body at the starting degree", "Venus by trine at the starting degree")
        def unknown(values):
            return module.UnresolvedResult('equally placed eligible opening contacts; no precedence is supplied',
                module.PN4_OPENING_SOURCE,tuple(zip(names,values)))
        # Extend the initialized period to exercise a live unknown at this app's target.
        return [dict(segs[0],to=segs[-1]['to'],partner=unknown(('Mars','Venus')),
                     partner_aspect=unknown(('body','trine')),partner_from=unknown(names),opened_by=unknown(names))]
    monkeypatch.setattr(module,'_pn4_distribute',tie_direction)
    at.run()
    assert_no_exception(at, 'tied opening partners')
    assert any('Unresolved' in str(n.value) for n in at.main if getattr(n,'type',None) in ('markdown','dataframe'))
    for node in at.main:
        if getattr(node,'type',None) in ('markdown','caption','dataframe'):
            assert 'UnresolvedResult(' not in str(node.value)
    assert 'UnresolvedResult(' not in at.session_state['_analysis_markdown']
    tables=at.session_state['_analysis_export']['results']['Prediction']
    table=next(t for t in tables['The distribution from the Ascendant (the *jar bakhtar*)'] if 'Partner' in t['columns'])
    assert table['rows'][0]['Partner']['status']=='unresolved'
    assert {a['value'] for a in table['rows'][0]['Partner']['alternatives']}=={'Mars','Venus'}


@pytest.mark.parametrize('name',['the Sun','the Moon'])
def test_luminary_identity_reaches_both_trajectories(engine,name):
    planet=name[4:]
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    longitude=c['planetary_data'][planet]['longitude']
    p=engine['pn4_releaser_direction'](c,{'releaser':name,'longitude':longitude},0)
    assert p['segments'][0]['partner']!=planet
    q=engine['sahl_releaser_distribution'](c['planetary_data'],longitude,c['obliquity'],c['geo_lat'],significator=planet)
    assert q[0]['partner']!=planet


@pytest.mark.parametrize('axis',['ascendant','mc','ic'])
def test_coincident_planet_dispatch_still_filters_by_identity(engine,axis):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    lon=(c['mc']+180)%360 if axis=='ic' else c[axis]
    c['planetary_data']=pdata(Saturn=lon)
    directed=engine['pn4_point_distribution'](c,lon,0,'Saturn',significator='Saturn')
    control=engine['pn4_point_distribution'](c,lon,0,axis)
    assert directed['current']['partner'] is None
    assert control['current']['partner']=='Saturn'


@pytest.mark.parametrize('cusp',[1,2,4,5,7,8,10,11])
def test_no_allowance_before_intermediate_cusps(engine,cusp):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    x=(c['houses'][cusp]-1)%360
    c['planetary_data']['Mercury']['longitude']=x
    row=next(r for r in engine['pn4_i7_planets'](c,c) if r['Planet']=='Mercury' and r['Chart']=='root')
    assert row['Stakes (23)'].startswith(f"house {engine['get_house_number'](x,c['houses'])},")


def test_indicator_seven_not_forecast_by_fifteen(engine,monkeypatch):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    def forbidden(*a,**k):raise AssertionError('row 15 must not forecast')
    monkeypatch.setitem(engine,'_pn4_luminary_connections',forbidden)
    moon={'void':False,'sign':'Aries','exit_day':2.,'connections':[{'planet':'Mars','aspect':'trine','day':1.}]}
    rows=engine['pn4_further_indicators'](c,c,c['ascendant'],moon,jd_sr=2451545.)
    assert 'Mars by trine on day 1.00' in next(r for r in rows if r['#']==7)['Reads']
    assert all('Not tracked' in r['Reads'] for r in rows if r['#'] in (16,17))


@pytest.mark.parametrize('reading',["Abu Ma'shar","Masha'allah"])
def test_domain_declaration_matches_switch(engine,reading):
    engine['set_readings'](DOMAIN_RULE=reading)
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    y=engine['pn4_sign_of_the_year'](c['ascendant'],30)
    result=engine['pn4_ii3_examination'](c,c,y,c['julian_day'])
    domain=next(r for r in result['lord_rows'] if r['Factor'].startswith('In its own domain'))
    assert 'hayyiz' in domain['Factor'] and 'fn 46 reads it as sect' in domain['Factor']
    # Ruling 37 (2026-10-06): PN IV's domain rows read plain sect (fn 46, 48)
    # and no longer follow the switch; the source no longer names
    # Gr. Intr. VII.1, 37-39, and the note says the switch does not reach it.
    assert domain['Source'] == 'PN IV II.3, 5-6; fn 46, 48'
    text=(Path(__file__).parents[1]/'app.py').read_text()
    assert 'the Domain switch on the Dignities page does not reach it.' in text


def test_type_two_actual_entrant_rows(engine):
    c={'planetary_data':pdata(Sun=190,Jupiter=23,Venus=142),'ascendant':5,'houses':[i*30 for i in range(12)],'sect':'Diurnal'}
    seg={'from_lon':22.,'distributor':'Saturn','partner':None}
    rows=engine['pn4_bound_transits'](c,c,seg,'Mars')
    found=[r for r in rows if r['Source']=='III.2, 34-35']
    assert len(found)==2
    assert all('hindered adversity' in r['Sentence'] and 'not judged' in r['Sentence'] for r in found)


@pytest.mark.parametrize('lon,house',[(185.,12),(193.,12),(194.,1),(199.,1)])
def test_sr35_stakes_oracle(engine,lon,house):
    c=engine['calculate_traditional_chart'](datetime(1990,7,15,12),42.3314,-83.0458)
    sr=dict(c,houses=[198.3619,231.56,262.05,291.79,318.92,348.19,18.3619,51.56,82.05,111.79,138.92,168.189],
        ascendant=198.3619,planetary_data=dict(c['planetary_data']))
    sr['planetary_data']['Mercury']=dict(sr['planetary_data']['Mercury'],longitude=lon)
    row=next(r for r in engine['pn4_i7_planets'](c,sr) if r['Planet']=='Mercury' and r['Chart']=='revolution')
    assert row['Stakes (23)'].startswith(f'house {house},')


def test_unresolved_direction_not_coerced_to_aversion(engine):
    pd=pdata(Sun=(190,1),Mercury=(189,-1))
    c={'planetary_data':pd,'ascendant':65.}
    r=next(r for r in engine['pn4_indicator_relationships'](c,c,65.) if r['Partner']=='Sun')
    assert engine['is_unresolved'](r['State'])
    assert engine['is_unresolved'](r['Description'])
    assert engine['is_unresolved'](r['Applicant'])
    assert r['Whole-sign relation']!='Aversion'


@pytest.mark.parametrize('positions',[(20,20,1,1),(20,22,1,1),(29,31,1,.5)])
def test_exact_stationary_and_cross_sign_keep_f6_state(engine,positions):
    x,y,vx,vy=positions;pd=pdata(Mercury=(x,vx),Venus=(y,vy));c={'planetary_data':pd,'ascendant':65.}
    row=engine['pn4_indicator_relationships'](c,c,65.)[0]
    pair=engine['_pairwise_configurations'](pd)[0]
    assert row['State']==engine['_connection_state'](pair,engine['_is_connected'](pair))
    if x==29:
        assert row['Connected'] is True and 'body connection' in row['Description']
        assert 'in aversion by whole sign' in row['Description']


@pytest.mark.parametrize('target', [None, '1250-05-22', '1243-05-22'])
def test_governor_heading_names_the_one_planet_the_condition_table_is_built_for(engine, target):
    # The check's finding 28: the heading printed every top-tally planet on
    # the default chart ("Jupiter; Mars; Moon; Sun; Venus") above a table
    # computed for primary[0] alone; main printed the one planet.
    # L4-07 of the hostile pass of 2026-10-03: a tie is no longer resolved
    # to primary[0]; the heading then names no planet and each tied
    # planet's table carries its own one-name label. Either way, every
    # table is built for the one planet its heading or label names, and
    # the names are the tally's `primary` -- the one planet when there is
    # one (1243-05-22, Jupiter), each of the tied set when it ties
    # (1250-05-22, three ways; the default target, today, five ways).
    at=make_app(page='timing')
    if target is not None:
        at.session_state['_target_mode']='Date'
        at.session_state['_target_date']=target
    at.run(timeout=120)
    assert_no_exception(at)
    birth=(1240,5,23)
    when=date.today() if target is None else date.fromisoformat(target)
    offset=11.2463/15.0
    jd=engine['civil_local_to_jd_ut'](*birth,14.5,offset)
    chart=engine['calculate_traditional_chart_jd'](jd,43.7792,11.2463)
    bundle=engine['pn4_timing_bundle'](chart,43.7792,11.2463,engine['CivilDate'](*birth),
                                       engine['CivilDate'](when.year,when.month,when.day),
                                       engine['PN4_MONTHLY_TURN_OPTIONS'][0],
                                       engine['calculate_chronocrats'](jd,43.7792,11.2463,14,offset))
    primary=bundle['governor'][1]['primary']
    assert isinstance(primary,list) and primary, primary
    heads=[m.value for m in at.markdown if 'the condition of the primary planet' in m.value]
    assert len(heads)==1, heads
    head=heads[0]
    assert 'UnresolvedResult(' not in head
    if len(primary)==1:
        assert 'the condition of the primary planet (' in head, head
        named=head.split('the condition of the primary planet (')[1].split(')')[0]
        assert ';' not in named and ',' not in named, named
        assert named==primary[0], (named, primary)
        assert not [m.value for m in at.markdown if m.value.startswith('**') and '(the primary is tied between' in m.value]
    else:
        assert 'the primary is tied' in head, head
        labels=[m.value for m in at.markdown if m.value.startswith('**') and '(the primary is tied between' in m.value]
        assert labels, 'a tied primary with no per-planet table labels'
        names=[]
        for label in labels:
            named=label.split('**')[1].split(' (')[0]
            assert ';' not in named and ',' not in named and 'UnresolvedResult(' not in label, label
            names.append(named)
        assert names==primary, (names, primary)


def test_the_timing_wheel_draws_under_a_tied_opening_partner(engine, monkeypatch):
    # The code review of 2026-09-22: the wheel's badge loop tested
    # `if _planet:` on the current segment's partner, which a tie makes an
    # UnresolvedResult whose truth value raises -- the wheel then crashed.
    # The target must lie INSIDE the distribution's span, or the current
    # segment is None and the badge loop never sees the tie (the earlier
    # tie test's target of 2026 on a 1240 birth is past the 120-year table).
    at = make_app(page='timing')
    at.session_state['_target_mode'] = 'Date'
    at.session_state['_target_date'] = '1250-05-23'
    import engine as module
    original = module._pn4_distribute
    def tie_direction(*args, **kwargs):
        segs = original(*args, **kwargs)
        names = ("Mars by body at the starting degree", "Venus by trine at the starting degree")
        def unknown(values):
            return module.UnresolvedResult('equally placed eligible opening contacts; no precedence is supplied',
                                           module.PN4_OPENING_SOURCE, tuple(zip(names, values)))
        return [dict(segs[0], to=segs[-1]['to'], partner=unknown(('Mars', 'Venus')),
                     partner_aspect=unknown(('body', 'trine')), partner_from=unknown(names), opened_by=unknown(names))]
    monkeypatch.setattr(module, '_pn4_distribute', tie_direction)
    at.run()
    assert_no_exception(at, 'the Timing wheel under a tied opening partner')
    export = at.session_state['_analysis_export']['results']['Prediction']
    table = next(t for t in export['The distribution from the Ascendant (the *jar bakhtar*)'] if 'Partner' in t['columns'])
    assert table['rows'][0]['Partner']['status'] == 'unresolved', 'the tie is live at this target'
    assert any(getattr(n, 'type', None) == 'download_button' and 'wheel' in str(getattr(n, 'label', '')).lower()
               for n in at.main) or any('Download this wheel' in str(getattr(n, 'label', '')) for n in at.main), \
        'the Timing wheel and its download button rendered'
