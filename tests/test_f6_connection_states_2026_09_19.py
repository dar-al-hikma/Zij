"""G15-A acceptance cases: source limits, phase evidence, and strike scope."""
import pytest


def data(**pairs):
    return {p: {'longitude': x, 'speed_in_lon': v} for p, (x, v) in pairs.items()}


def pair(e, p, phase=None, events=()):
    if phase:
        p = {name: dict(value) for name, value in p.items()}
        a, b = p
        p[a]['encounter_history'] = {b: {'phase': phase, 'events': events}}
    return e['_pairwise_configurations'](p)[0]


def state(e, r):
    return e['_connection_state'](r, e['_is_connected_sahl'](r))


@pytest.mark.parametrize('planet,gap', [('Venus',10), ('Moon',14), ('Venus',15)])
def test_sun_receives_in_its_own_fifteen_degrees(engine, planet, gap):
    r=pair(engine,data(**{planet:(20-gap,2),'Sun':(20,1)}))
    assert state(engine,r)=='Applying'


def test_sun_entry_does_not_change_departure_or_other_planets(engine):
    assert state(engine,pair(engine,data(Venus=(4.999,2),Sun=(20,1))))=='Not yet'
    assert state(engine,pair(engine,data(Venus=(20,2),Sun=(12,1)), 'completed'))=='Separated'
    assert state(engine,pair(engine,data(Venus=(10,2),Saturn=(18,.1))))=='Not yet'


def test_revocation_requires_all_three_events(engine):
    p=data(Mercury=(8,-1),Sun=(10,1))
    r=pair(engine,p,'revoked',('approach','retrograde turn before contact','departure'))
    assert state(engine,r)=='Revoked — Abū Maʿshar, Gr. Intr. VII.5, 117'
    assert engine['is_unresolved'](state(engine,pair(engine,p,'revoked')))
    assert engine['is_unresolved'](state(engine,pair(engine,p)))


def test_known_uncompleted_station_is_not_blanket(engine):
    assert state(engine,pair(engine,data(Mercury=(8,0),Sun=(10,1)), 'uncompleted'))=='Not applying — gap widening'


def test_same_snapshot_different_supported_histories(engine):
    p=data(Mercury=(8,-1),Sun=(10,1))
    assert state(engine,pair(engine,p,'completed'))=='Under a single blanket'
    assert state(engine,pair(engine,p,'uncompleted'))=='Not applying — gap widening'
    assert engine['is_unresolved'](state(engine,pair(engine,p)))


def test_retrograde_application_and_exact_contact(engine):
    r=pair(engine,data(Mars=(12,-.5),Saturn=(10,.1)))
    assert state(engine,r)=='Applying'
    r=pair(engine,data(Mars=(10,-.5),Saturn=(10,.1)))
    assert r['motion']=='Exact'
    assert state(engine,r)=='Exact — connection completed'


@pytest.mark.parametrize('gap,expected',[(6.999999,'Under a single blanket'),(7,'Separated'),(7.000001,'Separated')])
def test_same_sign_departure_exclusive(engine,gap,expected):
    assert state(engine,pair(engine,data(Venus=(10+gap,1.2),Saturn=(10,.1)), 'completed'))==expected


@pytest.mark.parametrize('gap,expected',[(.999999,'Under a single blanket'),(1,'Separated'),(1.000001,'Separated')])
def test_aspect_departure_full_degree_exclusive(engine,gap,expected):
    assert state(engine,pair(engine,data(Venus=(10+gap,1.2),Saturn=(130,.1)), 'completed'))==expected


def test_forward_strike_and_blocker(engine):
    r=pair(engine,data(Moon=(29,13),Saturn=(31,.1)))
    assert r['aspect_name']=='Aversion' and state(engine,r)=='Applying'
    p=data(Moon=(29,13),Saturn=(31,.1),Jupiter=(149,.2))
    r=next(r for r in engine['_pairwise_configurations'](p) if {r['p1'],r['p2']}=={'Moon','Saturn'})
    assert engine['_is_connected_sahl'](r) is False


@pytest.mark.parametrize('gap,expected',[(.5,'Under a single blanket'),(1,'Separated'),(4,'Separated')])
def test_completed_strike_uses_one_degree_not_striker_light(engine,gap,expected):
    p=data(Saturn=(29.75,.1),Moon=(29.75+gap,13))
    assert state(engine,pair(engine,p,'completed'))==expected


def test_equal_motion_does_not_invent_history(engine):
    p=data(Venus=(11,1),Saturn=(10,1))
    r=pair(engine,p)
    assert r['motion']=='No relative motion'
    assert engine['is_unresolved'](state(engine,r))
    assert state(engine,pair(engine,p,'completed'))=='Under a single blanket'
    r=pair(engine,data(Venus=(10,1),Saturn=(10,1)))
    assert state(engine,r)=='Exact — connection completed'


def test_no_out_of_sign_aspect(engine):
    r=pair(engine,data(Venus=(29,1.2),Saturn=(150,.1)))
    assert r['aspect_name']=='Aversion' and engine['_is_connected_sahl'](r) is False


def test_unknown_can_neither_vote_nor_hide_independent_result(engine):
    r=pair(engine,data(Mercury=(8,-1),Sun=(10,1)))
    query=lambda: engine['_is_connected'](r)
    value=engine['evaluate_with_connection_uncertainty'](query)
    assert engine['is_unresolved'](value)
    with pytest.raises(TypeError): bool(value)
    assert engine['evaluate_with_connection_uncertainty'](lambda: query() or True) is True
    assert engine['evaluate_with_connection_uncertainty'](lambda: query() and False) is False
    assert engine['evaluate_with_connection_uncertainty'](lambda: query() == query()) is True


def test_first_strike_ties_are_not_iteration_priorities(engine):
    p=data(Moon=(29,13),Saturn=(31,.1),Jupiter=(31,.2))
    rows=engine['_pairwise_configurations'](p)
    pending=[r for r in rows if r['aspect_name']=='Aversion']
    assert len(pending)==2
    assert all(engine['is_unresolved'](engine['_is_connected_sahl'](r)) for r in pending)
    def both():
        rows=engine['_pairwise_configurations'](p)
        return all(engine['_is_connected'](r) for r in rows if r['aspect_name']=='Aversion')
    assert engine['evaluate_with_connection_uncertainty'](both) is False


def test_lights_are_not_halved_a_second_time(engine):
    r=pair(engine,data(Moon=(17,13),Saturn=(10,.1)),'completed')
    assert state(engine,r)=='Under a single blanket'  # Seven is inside twelve, not six.


def test_all_boolean_completions_and_thread_cleanup(engine):
    a=pair(engine,data(Moon=(9,-13),Saturn=(10,.1)))
    b=pair(engine,data(Venus=(19,-1.2),Mars=(20,.5)))
    call=engine['evaluate_with_connection_uncertainty'];query=engine['_is_connected']
    # Both uniform completions give False, but mixed histories give True.
    assert engine['is_unresolved'](call(lambda: query(a) != query(b)))
    assert call(lambda: query(a) or not query(a)) is True
    def failed():
        query(a)
        raise ValueError('probe')
    with pytest.raises(ValueError,match='probe'): call(failed)
    assert engine['is_unresolved'](query(a))


def test_same_sign_sun_rule_and_strike_do_not_change_abu_profile(engine):
    r=pair(engine,data(Moon=(29,13),Saturn=(31,.1)))
    assert engine['_is_connected_abu_mashar'](r) is False
    r=pair(engine,data(Venus=(10,1),Saturn=(11,1)))
    assert engine['_is_connected_abu_mashar'](r) is False


@pytest.mark.parametrize('profile,admitted', [('Sahl',True),("Abu Ma'shar",False)])
def test_pn4_by_degree_carries_only_admitted_strike(engine,profile,admitted):
    p=data(Venus=(29,1.2),Saturn=(31,.1),Sun=(200,1))
    for v in p.values(): v.update(latitude=0.,distance=1.)
    chart={'planetary_data':p,'ascendant':0.,'houses':tuple(range(0,360,30)), 'sect':'Diurnal'}
    engine['set_readings'](CONNECTION_PROFILE=profile)
    try:
        rows=engine['pn4_i7_planets'](chart,chart)
        venus=next(r for r in rows if r['Planet']=='Venus' and r['Chart']=='revolution')
        text=venus['By degree (12-13)']
        assert ('Saturn body connection' in text) is admitted
        assert 'in aversion to Saturn' in venus['Whole sign (10-11)']
    finally:
        engine['set_readings'](CONNECTION_PROFILE='Sahl')


def test_uncertainty_merge_preserves_distinct_rows_and_multiplicity(engine):
    a={'Planet':'Moon','Manner':'I','Returned By':'Saturn'}
    b={'Planet':'Moon','Manner':'I','Returned By':'Mars'}
    c={'Planet':'Venus','Manner':'I','Returned By':'Jupiter'}
    rows=engine['_connection_merge']([[a,b,a],[a,b,a,c]])
    assert sum(r.get('Returned By')=='Saturn' for r in rows)==2
    assert sum(r.get('Returned By')=='Mars' for r in rows)==1
    assert engine['is_unresolved'](next(r for r in rows if r['Planet']=='Venus')['Status'])
    assert all('Status' not in r for r in rows if r['Planet']=='Moon')


def test_reordered_pair_is_the_same_missing_fact(engine):
    a=pair(engine,data(Moon=(9,-13),Saturn=(10,.1)))
    b=pair(engine,data(Saturn=(10,.1),Moon=(9,-13)))
    query=engine['_is_connected']
    assert engine['evaluate_with_connection_uncertainty'](lambda: query(a)==query(b)) is True


def test_existing_exception_fallback_cannot_swallow_a_missing_fact(engine):
    r=pair(engine,data(Moon=(9,-13),Saturn=(10,.1)))
    def judgment():
        try: return engine['_is_connected'](r)
        except Exception: return False
    assert engine['is_unresolved'](engine['evaluate_with_connection_uncertainty'](judgment))


def test_completed_cross_sign_residue_stands_under_the_strikes_own_conditions(engine):
    # The residue is the strike's post-exact phase (G15-A rows 7-8), so Sahl 20's "not connecting with anything"
    # refuses it as it refuses a fresh strike: with Saturn in an exact trine to Jupiter the Saturn-Moon residue is
    # not connected, positionally or with supplied completion; with Jupiter away it is (the fix round of 2026-09-20).
    blocked=data(Saturn=(29.75,.1),Moon=(30.25,13),Jupiter=(149.75,.2))
    def membership(p):
        r=next(r for r in engine['_pairwise_configurations'](p) if {r['p1'],r['p2']}=={'Saturn','Moon'})
        return engine['_is_connected'](r)
    assert engine['evaluate_with_connection_uncertainty'](lambda: membership(blocked)) is True   # ruling 60: Saturn only approached
    blocked['Moon']['encounter_history']={'Saturn':{'phase':'completed'}}
    assert membership(blocked) is True   # ruling 60
    free=data(Saturn=(29.75,.1),Moon=(30.25,13))
    assert membership(free) is True


def test_completed_first_body_still_blocks_farther_strike(engine):
    p=data(Saturn=(29.75,.1),Moon=(30.25,13),Venus=(31,0))
    p['Moon']['encounter_history']={'Saturn':{'phase':'completed'}}
    r=next(r for r in engine['_pairwise_configurations'](p) if {r['p1'],r['p2']}=={'Saturn','Venus'})
    assert engine['_is_connected_sahl'](r) is False


@pytest.mark.parametrize('phase', ['uncompleted','revoked','completed'])
def test_transfer_requires_completed_separation_not_retained_blanket(engine,phase):
    p=data(Mercury=(8,-1),Sun=(10,1),Saturn=(6,.1))
    p['Mercury']['encounter_history']={'Sun':{'phase':phase,'events':('approach','retrograde turn before contact','departure')}}
    rows=engine['evaluate_transfers_of_light'](p)
    matches=[r for r in rows if r.get('Carrier')=='Mercury' and r.get('Separates From')=='Sun']
    assert bool(matches)==(phase=='completed')


@pytest.mark.parametrize('phase', ['completed','uncompleted','revoked',None])
def test_sahl_enclosure_separation_requires_history(engine,phase):
    p=data(Moon=(193,13),Mars=(100,.5),Saturn=(18,.1))
    if phase:
        p['Moon']['encounter_history']={'Mars':{'phase':phase,'events':('approach','retrograde turn before contact','departure')}}
    rows=[r for r in engine['evaluate_enclosure'](p) if r['Planet']=='Moon' and r['Enclosed By']=='Infortunes']
    if phase in ('uncompleted','revoked'):
        assert rows==[]
    else:
        assert len(rows)==1
        assert not engine['is_unresolved'](rows[0].get('Status'))


def test_sahl_source_transfer_survives_expired_blanket(engine):
    p=data(Moon=(70,13),Mercury=(128,1),Jupiter=(343,.2))
    rows=engine['evaluate_transfers_of_light'](p)
    assert any(r.get('Carrier')=='Moon' and r.get('Separates From')=='Mercury' and r.get('Connects To')=='Jupiter' for r in rows)
