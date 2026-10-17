"""Sahl 3.22 decides ordinary separation without injected encounter history."""
import pytest
from conftest import FLORENCE, LOCAL_TIME, make_app, find_table, assert_no_exception


def chart(engine,date):
    y,m,d=map(int,date.split('-'))
    jd=engine['civil_local_to_jd_ut'](y,m,d,LOCAL_TIME.hour+LOCAL_TIME.minute/60,FLORENCE[1]/15)
    return engine['calculate_traditional_chart_jd'](jd,*FLORENCE)


@pytest.mark.parametrize('date',['1240-05-23','1240-09-18','1566-01-21'])
def test_direct_separations_are_decided_on_review_charts(engine,date):
    p=chart(engine,date)['planetary_data']
    rows=engine['_pairwise_configurations'](p)
    examined=0
    for row in rows:
        if row['motion']=='Separating' and row['light_speed']>0:
            assert engine['_encounter_phase'](row)=='completed', row
            assert not engine['is_unresolved'](engine['_connection_state'](row,engine['_is_connected_sahl'](row))),row
            examined+=1
    assert examined
    transfers=engine['evaluate_transfers_of_light'](p)
    assert transfers
    if date=='1240-05-23':
        assert all(not engine['is_unresolved'](r.get('Status')) for r in transfers)


@pytest.mark.parametrize('light,heavy',[(11,10),(71,10),(71,130),(193,100),(1,359),(181,0),(359,178),(30.25,29.75)])
def test_contact_geometry_handles_both_rays_and_wraparound(engine,light,heavy):
    p={'Moon':{'longitude':light,'speed_in_lon':13},'Saturn':{'longitude':heavy,'speed_in_lon':.1}}
    row=engine['_pairwise_configurations'](p)[0]
    assert row['motion']=='Separating'
    assert engine['_encounter_phase'](row)=='completed'
    assert engine['_sahl_has_separated'](row) is True


@pytest.mark.parametrize('speed,longitude',[(0,9),(-1,9),(.05,9)])
def test_widening_before_contact_is_not_positional_separation(engine,speed,longitude):
    p={'Mercury':{'longitude':longitude,'speed_in_lon':speed},'Sun':{'longitude':10,'speed_in_lon':1}}
    row=engine['_pairwise_configurations'](p)[0]
    assert row['motion']=='Separating'
    assert engine['_encounter_phase'](row) is None
    assert engine['is_unresolved'](engine['_is_connected_sahl'](row))


@pytest.mark.parametrize('date',['1240-05-23','1240-09-18','1566-01-21'])
def test_review_charts_render_without_internal_result_repr(date):
    at=make_app(date=date,page='configurations')
    at.run()
    assert_no_exception(at,'configurations')
    table=find_table(at,'Aspects, aversions and connections').value
    assert not table.astype(str).apply(lambda col:col.str.contains('UnresolvedResult',regex=False)).any().any()
    if date=='1240-05-23':
        transfer=find_table(at,'Transfer of Light').value
        assert 'Status' not in transfer.columns or not transfer['Status'].astype(str).str.contains('Unresolved').any()
