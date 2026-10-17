"""Ruled figures and shared-consumer checks for F1; no new connection rule."""
from itertools import permutations
import pytest


def data(**pairs):
    return {p: {'longitude': lon, 'speed_in_lon': speed} for p, (lon, speed) in pairs.items()}


def collections(e, p):
    return e['evaluate_collections_of_light'](p)


@pytest.mark.parametrize('venus,moon,jupiter,accepted', [
    (10,42,105,True), (340,42,105,True), (10,42,135,True),
])
def test_collection_figures(engine, venus, moon, jupiter, accepted):
    p=data(Venus=(venus,1.2),Moon=(moon,13),Jupiter=(jupiter,.08))
    rows=collections(engine,p)
    assert any(r['Collector']=='Jupiter' and r['Collects']=='Moon & Venus' for r in rows) is accepted


@pytest.mark.parametrize('venus,accepted',[(167.999,True),(168,True),(168.001,True),(166,False),(167,True)])
@pytest.mark.parametrize('profile',['Sahl', "Abu Ma'shar"])
def test_fig70_separation_does_not_exclude(engine,venus,accepted,profile):
    profile=engine['SAHL'] if profile=='Sahl' else engine['ABU_MASHAR']
    with engine['doctrine'](profile):
        rows=collections(engine,data(Venus=(venus,1.2),Mars=(287,.7),Jupiter=(230,.08)))
    assert any(r['Collector']=='Jupiter' and r['Collects']=='Mars & Venus' for r in rows) is accepted
    if venus==167:
        assert rows[0]['Residual connection'] is False


def test_fig128_reflection_destination(engine):
    p=data(Venus=(10,1.2),Moon=(42,13),Jupiter=(135,.08))
    rows=engine['evaluate_reflections_of_light'](p,0)
    assert any(r['Reflection Type']=='I (Collection)' and '8' in r['Detail'] for r in rows)


def test_separating_collection_is_not_type_one_reflection(engine):
    p=data(Venus=(340,1.2),Moon=(42,13),Jupiter=(105,.08))
    assert collections(engine,p)
    assert not any(r['Reflection Type']=='I (Collection)' for r in engine['evaluate_reflections_of_light'](p,0))


@pytest.mark.parametrize('profile_key',['SAHL','ABU_MASHAR'])
def test_mutual_exclusion_uses_exact_f6_membership(engine,profile_key):
    # Venus is beyond her own seven-degree light but received by the Sun.
    p=data(Venus=(10,1.2),Sun=(20,1),Saturn=(21,.03))
    with engine['doctrine'](engine[profile_key]):
        mutual=next(r for r in engine['_pairwise_configurations'](p) if {r['p1'],r['p2']}=={'Sun','Venus'})
        assert mutual['motion']=='Applying' and engine['_is_connected'](mutual)
        assert engine['_applying_connection'](mutual) is True
        if profile_key=='ABU_MASHAR':
            record=next(r for r in engine['_collection_records'](p) if r['Collects']=='Sun & Venus')
            assert record['Editorial exclusion'] is True
        assert not any(r['Collects']=='Sun & Venus' for r in collections(engine,p))


def test_profile_is_respected_and_restored(engine):
    p=data(Venus=(10,1.2),Moon=(42,13),Jupiter=(108,.08))
    with engine['doctrine'](engine['SAHL']):
        assert not collections(engine,p)
        engine['evaluate_reflections_of_light'](p,0)
        assert engine['reading']('CONNECTION_PROFILE')==engine['SAHL']
    with engine['doctrine'](engine['ABU_MASHAR']):
        assert collections(engine,p)


def test_collection_evidence_and_order(engine):
    p=data(Venus=(168,1.2),Mars=(287,.7),Jupiter=(230,.08))
    for names in permutations(p):
        r=collections(engine,{k:p[k] for k in names})[0]
        assert r['Planets']==('Mars','Venus') and r['Admitted'] is True
        assert r['Mutual sight'] is True and r['Mutual application'] is False
        assert r['Editorial exclusion'] is False
        assert r['Applications to collector']==(('Mars','Jupiter'),('Venus','Jupiter'))


def inputs():
    p=data(Moon=(52,13),Sun=(295,1),Mercury=(190,1.3),Venus=(250,1.2),Mars=(130,.5),Jupiter=(200,.08),Saturn=(83,.03))
    return p,90,[90,112,150,180,210,240,270,300,315,0,30,56]


@pytest.mark.parametrize('sect',['Diurnal','Nocturnal'])
def test_cusp_ruler_example_every_consumer(engine,sect):
    p,asc,cusps=inputs(); engine['set_readings'](LOT_HOUSE_CUSP='quadrant cusp')
    assert engine['lot_by_id']('assets_lord2',p,asc,cusps,sect)==150
    row=next(r for r in engine['calculate_topical_lots'](p,asc,cusps,sect) if r['Id']=='assets_lord2')
    assert row['Longitude']==150 and 'Moon (Cancer' in row['Formula'] and engine['get_degree_string'](112) in row['Formula']
    assert engine['lot_by_id']('travel',p,asc,cusps,sect)==pytest.approx((90+315-83)%360)
    assert engine['lot_by_id']('enemies_hermes',p,asc,cusps,sect)==pytest.approx((90+56-250)%360)


def test_endpoint_arithmetic_and_override(engine):
    p,asc,cusps=inputs();p['Moon']['longitude']=190;asc=75;cusps[1]=98
    engine['set_readings'](LOT_HOUSE_CUSP='whole-sign place')
    endpoint=engine['_lot_point']('cusp2',p,asc,cusps,'Diurnal',{})
    assert endpoint==90 and (asc+endpoint-190)%360==335
    assert (asc+105-190)%360==350 # rejected carried-degree oracle
    assert (asc+engine['_lot_point']('cusp2',p,asc,cusps,'Diurnal',{},'quadrant cusp')-190)%360==343
    assert engine['_lot_point']('lord2',p,asc,cusps,'Diurnal',{},'quadrant cusp')==190


@pytest.mark.parametrize('cusp,planet',[(119.999999,'Moon'),(120,'Sun'),(359.999999,'Jupiter'),(0,'Mars')])
def test_cusp_sign_boundaries(engine,cusp,planet):
    p,asc,cusps=inputs();cusps[1]=cusp
    assert engine['_lot_point']('lord2',p,asc,cusps,'Diurnal',{},'quadrant cusp')==p[planet]['longitude']
    del p[planet]
    assert engine['_lot_point']('lord2',p,asc,cusps,'Diurnal',{},'quadrant cusp') is None


def test_killer_unchanged_and_same_sign_control(engine):
    p,asc,cusps=inputs();cusps[1]=125
    vals=[]
    for mode in engine['LOT_HOUSE_CUSP_OPTIONS']:
        engine['set_readings'](LOT_HOUSE_CUSP=mode)
        vals.append(engine['lot_by_id']('killer',p,asc,cusps,'Nocturnal'))
        assert engine['_lot_point']('lord2',p,asc,cusps,'Diurnal',{})==295
    assert vals[0]==vals[1]


def test_tenth_lot_uses_unreversed_witness(engine):
    p,asc,cusps=inputs()
    definition=next(d for d in engine['PN4_TURNING_LOTS'] if d[1]=='authority and rank')
    assert definition[0]=='work_expedition'
    assert engine['lot_by_id'](definition[0],p,asc,cusps,'Nocturnal')==59
    assert engine['lot_by_id']('work_expedition_paul',p,asc,cusps,'Nocturnal')==121
    note=next(d['note'] for d in engine['LOT_DEFINITIONS'] if d['id']=='work_expedition_paul')
    assert 'as reported by Dykes' in note and 'Paul instructs us to reverse it by night' in note


@pytest.mark.parametrize('substitute',[False,True])
@pytest.mark.parametrize('supplement',[False,True])
@pytest.mark.parametrize('mode',['quadrant cusp','whole-sign place'])
def test_image_uses_operative_visible_lots(engine,substitute,supplement,mode):
    p,asc,cusps=inputs(); p['Saturn']['longitude']=300 if substitute else 83
    p['North Node']={'longitude':45,'speed_in_lon':-.05}
    engine['set_readings'](LOT_HOUSE_CUSP=mode)
    chart={'planetary_data':p,'ascendant':asc,'houses':cusps,'sect':'Diurnal'}
    rows,counts=engine['pn4_revolution_image'](chart,chart,{'longitude':asc},1,None,None,None,30,supplement=supplement)
    lots=engine['calculate_topical_lots'](p,asc,cusps,'Diurnal')
    expected={r['Lot']:r['Position'] for r in lots if r['Operative'] and engine['lot_visible'](r,supplement)}
    assert {r['Point']:r['Position'] for r in rows if r['Chart']=='root' and r['Kind']=='Lot'}==expected
    ids={r['Id'] for r in lots if r['Operative'] and engine['lot_visible'](r,supplement)}
    assert ('father_burnt' in ids)==substitute and ('father' in ids)!=substitute
    assert not ids.intersection({'father_burnt_abu','death_ws','work_expedition_paul'})
    assert all(r['Status']=='Comparison — not operative' for r in lots if r['Id'] in ('death_ws','work_expedition_paul'))
    assert counts['Lots']==2*len(expected) and counts['total of I.6, 8']==154


def test_type_two_preserves_separating_alternative(engine):
    p=data(Moon=(72,13),Mars=(10,.5),Mercury=(135,1.4))
    rows=engine['evaluate_reflections_of_light'](p,0)
    assert any(r['Reflection Type']=='II (Transfer)' and 'Mars and Mercury' in r['Detail'] for r in rows)


def test_missing_cusps_do_not_break_independent_lots(engine):
    p=data(Sun=(250,1),Moon=(130,13))
    engine['set_readings'](LOT_HOUSE_CUSP='quadrant cusp')
    assert engine['lot_by_id']('passion',p,0,None,'Nocturnal')==240
    assert engine['lot_by_id']('assets_lord2',p,0,None,'Nocturnal') is None


def test_real_cusp_ruler_fixture(engine):
    c=engine['calculate_traditional_chart_jd'](2159000.027777778,36.2,37.15)
    engine['set_readings'](LOT_HOUSE_CUSP='quadrant cusp')
    args=(c['planetary_data'],c['ascendant'],c['houses'],c['sect'])
    assert engine['lot_by_id']('assets_lord2',*args)==pytest.approx(149.41968859860964)
    assert engine['lot_by_id']('travel',*args)==pytest.approx(83.04933543962807)
    assert engine['lot_by_id']('enemies_hermes',*args)==pytest.approx(250.24472320119008)


def test_real_tenth_lot_night_fixture(engine):
    c=engine['calculate_traditional_chart_jd'](2250406.625914352,18.8277,-35.7828)
    args=(c['planetary_data'],c['ascendant'],c['houses'],c['sect'])
    assert c['sect']=='Nocturnal'
    assert engine['lot_by_id']('work_expedition',*args)//30==1
    assert engine['lot_by_id']('work_expedition_paul',*args)//30==6


def test_unknown_father_does_not_emit_reference(engine):
    p,asc,cusps=inputs();p['Saturn']['longitude']=300;del p['Mars']
    rows=engine['operative_lot_rows'](p,asc,cusps,'Diurnal',True)
    assert not any(r['Id'].startswith('father') for r in rows)


def test_collection_complete_judgment_keeps_first_body_tie(engine):
    # No ordinary connection: Moon's strike must choose just one first body.
    p=data(Moon=(29,13),Saturn=(31,.03),Jupiter=(31,.08),Mercury=(35,-.2))
    def judgment():
        rows=engine['_pairwise_configurations'](p)
        choices=[r for r in rows if r['p1']=='Moon' or r['p2']=='Moon']
        return sum(bool(engine['_is_connected'](r)) for r in choices)>1
    assert engine['evaluate_with_connection_uncertainty'](judgment) is False
    assert engine['evaluate_with_connection_uncertainty'](lambda: len(collections(engine,p))==1) is True
    assert engine['evaluate_with_connection_uncertainty'](lambda: len(collections(engine,p))==2) is False
    def coherent():
        configurations=engine['_pairwise_configurations'](p)
        for record in collections(engine,p):
            for applicant,receiver in record['Applications to collector']:
                r=next(r for r in configurations if {r['p1'],r['p2']}=={applicant,receiver})
                if not engine['_applying_connection'](r):return False
        return True
    assert engine['evaluate_with_connection_uncertainty'](coherent) is True
