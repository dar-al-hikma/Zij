"""G09-A's ten fixtures and the readers' two-direction speed regression."""
import pytest
from test_f6_connection_states_2026_09_19 import data


@pytest.mark.parametrize('moon,mars,expected',[(3,119,False),(3,106,True),(29,31,True)])
def test_lunar_daily_motion_and_sign_boundary(engine,moon,mars,expected):
    r=engine['_rhetorius_application']('Moon',data(Moon=(moon,13),Mars=(mars,.5)),'Mars')
    assert r['result'] is expected


@pytest.mark.parametrize('gap', [2,3,4])
def test_nonlunar_limits(engine,gap):
    r=engine['_rhetorius_application']('Mercury',data(Mercury=(10,1),Saturn=(10+gap,.1)),'Saturn')
    assert (r['result'] is True) if gap<=3 else engine['is_unresolved'](r['result'])


def test_kollesis_follows_the_mover_not_signed_speed(engine):
    r=engine['_rhetorius_application']('Mercury',data(Mercury=(12,-1),Saturn=(10,.1)),'Saturn')
    assert r['kollesis'] is True
    r=engine['_rhetorius_application']('Jupiter',data(Jupiter=(10,.2),Mars=(12,-.3)),'Mars')
    assert r['kollesis'] is False and r['result'] is False


@pytest.mark.parametrize('jupiter,relief,interrupted',[(81,True,False),(79,True,True),(82,False,False),(109,False,True)])
def test_friendly_ray_and_structural_interruption_are_separate(engine,jupiter,relief,interrupted):
    p=data(Moon=(15,13),Saturn=(11,.1),Mars=(20,.5),Jupiter=(jupiter,.2))
    e=engine['_rhetorius_siege_evidence']('Moon',p,list(p),('Saturn',4,'Mars',5))
    assert e['Friendly-ray relief'] is relief
    assert e['Structure intact'] is not interrupted
    for r in e['Ray evidence']:
        assert isinstance(r['Distance'],float)
        assert r['Aspect']!='body'


@pytest.mark.parametrize('donor',['Sun','Venus'])
def test_body_is_not_friendly_ray(engine,donor):
    p=data(**{'Moon':(15,13),'Saturn':(11,.1),'Mars':(20,.5),donor:(16,1)})
    e=engine['_rhetorius_siege_evidence']('Moon',p,list(p),('Saturn',4,'Mars',5))
    assert e['Friendly-ray relief'] is False and e['Structure intact'] is True
    assert e['Bodily intervention'][0]['Donor']==donor
    assert e['Dykes interval break'] is True


@pytest.mark.parametrize('moon,mars,expected',[(3,119,False),(3,106,True),(29,31,True)])
def test_public_application_rows_follow_daily_motion(engine,moon,mars,expected):
    rows=engine['evaluate_rhetorius_affliction'](data(Moon=(moon,13),Mars=(mars,.5)),0,'Diurnal')
    hit=any(r['Planet']=='Moon' and r['Condition']=='Afflicted: applying to a destructive star'
            and r.get('Status','Present')=='Present' for r in rows)
    assert hit is expected


def test_public_wider_nonlunar_row_is_unspecified(engine):
    rows=engine['evaluate_rhetorius_affliction'](data(Mercury=(10,1),Saturn=(14,.1)),0,'Diurnal')
    row=next(r for r in rows if r['Planet']=='Mercury' and r['Condition']=='Afflicted: applying to a destructive star')
    assert engine['is_unresolved'](row.get('Status'))


def test_public_retrograde_swifter_has_kollesis(engine):
    rows=engine['evaluate_rhetorius_affliction'](data(Mercury=(12,-1),Saturn=(10,.1)),0,'Diurnal')
    assert any(r['Planet']=='Mercury' and r['Condition']=='Afflicted: in kollesis' for r in rows)


def test_lunar_approach_not_hidden_by_nearer_receding_aspect(engine):
    p={'Moon':{'longitude':109.8,'speed_in_lon':15.4},'Mars':{'longitude':5,'speed_in_lon':.5}}
    result=engine['_rhetorius_application']('Moon',p,'Mars')
    assert result['result'] is True
    assert result['aspect']=='trine'
