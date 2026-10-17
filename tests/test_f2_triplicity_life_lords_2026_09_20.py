"""Source identity, distinct reference points and qualitative life stages."""
import ast
from pathlib import Path
import pytest
from conftest import make_app, assert_no_exception
from test_doctrine_fixtures import _two_charts

NOTE = "Virgo's partnering lord follows the source named above: Sahl, al-Qabīsī, and Valens give Mars, while Abū Maʿshar's Great Introduction favors Mercury (Gr. Intr. V.14, 7, with Figure 53 and fn 100)."
SOURCE = "Al-Andarzaghar, reported by al-Qabīsī I.57b (ITA I.13): the Ascendant's triplicity lords signify the beginning, middle, and end of life at death; the third also shares its companions' significations. These are qualitative life-stage attributions, with no numerical boundaries given. Sahl, On Nativities 1.29, separately uses these lords to judge upbringing."
HEADING = 'Ascendant triplicity lords: life-stage significations'
STAGES = ['Beginning of life; no numerical boundary specified.', 'Middle of life; no numerical boundary specified.', 'End of the matter at death; also signifies what its companions signify. No numerical boundary specified.']
PARAGRAPH = "No numerical age ranges are calculated here. The sources give life-stage indications with differing roles for the triplicity lords. Sahl, On Nativities 2.11 gives two luminary triplicity lords their respective times, with a partner supporting both; Sahl 2.19, 5 conditionally connects the third lord with good fortune at life's end. Al-Qabīsī I.57b (ITA I.13) separately assigns life-stage significations to the Ascendant's triplicity lords. Valens II.2 relates transitions to sign rising times or a chronocrator's return, but the supplied excerpt does not provide a complete calculation. Dykes's note 14 to PN IV VI.2, 4 mentions a second or third lord for an older native without specifying ages. None of these passages prescribes three thirty-year periods."

@pytest.fixture(autouse=True)
def isolated_readings(engine):
    old = dict(engine['_RUN'].__dict__)
    engine['_RUN'].__dict__.clear()
    yield
    engine['_RUN'].__dict__.clear(); engine['_RUN'].__dict__.update(old)

@pytest.mark.parametrize('table',['Sahl','al-Qabisi','Valens','Great Introduction'])
@pytest.mark.parametrize('sect',['Diurnal','Nocturnal'])
def test_named_tables_all_signs_and_sect_order(engine,table,sect):
    # Independent four triples; Virgo is the only divergence.
    triples=[['Sun','Jupiter','Saturn'],['Venus','Moon','Mars'],['Saturn','Mercury','Jupiter'],['Venus','Mars','Moon']]
    for i,sign in enumerate(engine['SIGN_ORDER']):
        expected=list(triples[i%4])
        if sect=='Nocturnal':expected[:2]=reversed(expected[:2])
        if sign=='Virgo' and table=='Great Introduction':expected[2]='Mercury'
        assert engine['_triplicity_lords_in_sect_order'](sign,sect,table=table)==expected
        assert len(set(expected))==3

def test_invalid_source_rejected_and_lookup_cannot_mutate_base(engine):
    with pytest.raises(ValueError):engine['triplicity_rulers']('Virgo',table='Abbreviation')
    r=engine['triplicity_rulers']('Virgo',table='Great Introduction');r['Participating']='Jupiter'
    assert engine['triplicity_rulers']('Virgo',table='Great Introduction')['Participating']=='Mercury'
    assert engine['TRIPLICITY']['Earth']['Participating']=='Mars'

@pytest.mark.parametrize('sect',['Diurnal','Nocturnal'])
@pytest.mark.parametrize('light_virgo,mars_virgo',[(True,False),(False,True),(True,True),(False,False)])
def test_pn4_assets_and_siblings_independently_select_and_describe_lord(engine,sect,light_virgo,mars_virgo):
    light='Sun' if sect=='Diurnal' else 'Moon'
    root,sr,_=_two_charts(engine,natal={light:155 if light_virgo else 35,'Mars':165 if mars_virgo else 275,'Mercury':15},rev={'Mercury':95,'Mars':215})
    root['sect']=sect
    rows=engine['pn4_turning_triplicity_lords'](root,sr)
    for topic,changed,cite in [('assets',light_virgo,'VI.2, 4'),('siblings',mars_virgo,'VI.2, 5')]:
        rs=[r for r in rows if r['Topic']==topic];partner=rs[2];lord='Mercury' if changed else 'Mars'
        assert [r['Lord'] for r in rs[:2]]==(['Venus','Moon'] if sect=='Diurnal' else ['Moon','Venus'])
        assert partner['Lord']==lord and cite in partner['Source'] and 'table assumed' in partner['Source']
        assert partner['Root condition']==engine['_pn4_condition_string'](root['planetary_data'],lord)
        assert partner['Revolution condition']==engine['_pn4_condition_string'](sr['planetary_data'],lord)
        assert all(r['Virgo source note']==(NOTE if changed else '') for r in rs)
        assert len(rs)==3

@pytest.mark.parametrize('mercury,retrograde',[(5,False),(155,False),(160,True),(315,True)])
def test_mercury_position_condition_and_missing_data_never_change_partner(engine,mercury,retrograde):
    root,sr,_=_two_charts(engine,natal={'Sun':155,'Mars':165,'Mercury':mercury})
    root['planetary_data']['Mercury']['speed_in_lon']=-1 if retrograde else 1
    for missing in (False,True):
        if missing:root['planetary_data'].pop('Mercury')
        rows=engine['pn4_turning_triplicity_lords'](root,sr)
        assert [r['Lord'] for r in rows if r['Order']=='third']==['Mercury','Mercury']
        assert engine['triplicity_lords_of_life'](root)[2]['Lord']=='Mars'

@pytest.mark.parametrize('sect',['Diurnal','Nocturnal'])
def test_ascendant_prescription_is_distinct_with_verbatim_record(engine,sect):
    root,_,_=_two_charts(engine,natal={'Sun':155,'Moon':155});root.update(sect=sect,ascendant=155)
    asc=engine['triplicity_lords_of_life'](root,'Ascendant');lum=engine['triplicity_lords_of_life'](root)
    assert [r['Life-stage signification'] for r in asc]==STAGES
    assert [r['Lord'] for r in asc]==[r['Lord'] for r in lum]
    assert all(r['Source']==SOURCE and 'I.16c' in r['Triplicity table'] and 'Time of life' not in r for r in asc)
    assert all('35-41' in r['Triplicity table'] and r['Virgo source note']==NOTE for r in lum)
    first=lum[0]['Time of life']
    assert "'first' supplied" in first and 'fn 181' in first and 'unclear' in first and 'second lord' in first
    assert 'supports them both' in lum[2]['Time of life'] and 'if in the seventh' in lum[2]['Time of life']
    assert 'Life-stage signification' not in lum[0]

@pytest.mark.parametrize('asc',[5,155,335])
def test_andarzaghar_note_belongs_to_virgo_house_only(engine,asc):
    rows=engine['evaluate_andarzaghar_triplicity_lords'](asc,'Diurnal')
    assert len(rows)==12
    assert sum(r['Virgo source note']==NOTE for r in rows)==1
    for r in rows:
        assert 'I.16c' in r['Source'] and 'I.16c' in r['Triplicity table']
        assert r['Virgo source note']==(NOTE if r['Sign']=='Virgo' else '')
        if r['Sign']=='Virgo':assert r['Third lord']=='Mars'

def test_great_introduction_reference_rulers_keep_single_partner(engine):
    for sect in ['Diurnal','Nocturnal']:
        s=engine['sign_summary'](5,sect)
        assert s['lords'][3]['Lord']=='Mercury' and s['Virgo source note']==NOTE
        assert 'Gr. Intr.' in s['Triplicity table']
    assert engine['get_essential_rulers'](155)['triplicity_participating']=='Mercury'
    assert engine['sign_summary'](4)['Virgo source note']==''

def test_prosperity_source_is_separate_and_first_grade_stays_sahl(engine):
    c=engine['calculate_traditional_chart_jd'](2174172.1,43.7792,11.2463)
    c['planetary_data']['Sun']['longitude']=155;c['sect']='Diurnal'
    rows=engine['evaluate_prosperity'](c)
    assert all('35-41' in r['Triplicity table'] for r in rows)
    for r in rows:
        if r['key'] in ('lords','third') or r is rows[0]:assert r['Virgo source note']==NOTE
        assert r['Triplicity table'] not in r['Sahl']
    band=engine['evaluate_ascensional_bands'](c['planetary_data'],c['ascendant'],c['mc'],c['obliquity'],43.7792,c['sect'])
    assert band['first_lord']=='Venus'
    assert all('35-41' in r['Triplicity table'] for r in band['rows'])

def test_all_production_triplicity_consumers_select_a_table():
    from conftest import engine_files
    trees=[ast.parse(p.read_text()) for p in engine_files()]     # every engine module
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('triplicity_rulers','_triplicity_lords_in_sect_order'):
                assert any(k.arg=='table' for k in n.keywords),n.lineno
    direct=[n for tree in trees for n in ast.walk(tree) if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Name) and n.value.id=='TRIPLICITY']
    assert len(direct)==1

@pytest.mark.parametrize('page',['fardar','timing','findings','reference','victors','chart'])
def test_pages_exports_keep_sources_and_separate_ascendant_heading(engine,page):
    at=make_app(page=page,date='1240-09-18')
    at.session_state['_reading_depth']='Course text and supplement'
    at.session_state['_target_date']='2026-09-17'
    at.run();assert_no_exception(at,page)
    markdown=at.session_state['_analysis_markdown']
    assert HEADING in markdown and SOURCE in markdown
    assert 'Life-stage signification' in markdown and 'not prescribed in any text in hand' not in markdown
    assert 'Great Introduction V.14 table assumed' in markdown
    if page=='fardar':
        # The ruling prints its first sentence bold; the engine string is plain.
        rendered='**No numerical age ranges are calculated here.**'+PARAGRAPH[len('No numerical age ranges are calculated here.'):]
        assert any(rendered==m.value for m in at.main.markdown)
        cb=next(c for c in at.main.checkbox if c.key=='life_lords_ascendant')
        assert 'I.57b' in cb.help
        before=at.session_state['_analysis_export']['results']
        cb.check();at.run();assert_no_exception(at,'Ascendant stages')
        grid=next(d.value for d in at.main.dataframe if 'Life-stage signification' in d.value.columns)
        assert list(grid['Life-stage signification'])==STAGES
        assert all(v==SOURCE for v in grid['Source'])
        assert at.session_state['_analysis_export']['results']==before
        andar=next(d.value for d in at.main.dataframe if 'Third lord' in d.value.columns)
        assert list(andar['Virgo source note']).count(NOTE)==1
    if page=='reference':
        grid=next(d.value for d in at.main.dataframe if 'Partner — Great Introduction' in d.value.columns)
        v=grid[grid['Sign']=='Virgo'].iloc[0]
        assert v['Partner — Great Introduction']=='Mercury' and v['Partner — Sahl / al-Qabisi / Valens']=='Mars'
        assert list(grid['Virgo source note']).count(NOTE)==1
        assert any('relation unspecified' in m.value for m in at.main.markdown)


def test_wheel_virgo_hover_and_selected_panel_name_same_table(monkeypatch):
    from conftest import natal_wheel_envelope
    import streamlit as st
    from types import SimpleNamespace
    at=make_app(page='chart').run();assert_no_exception(at,'Virgo hover')
    signs=natal_wheel_envelope(at.main)['signs']
    assert NOTE in signs[5] and 'Mercury partnering' in signs[5]
    assert all(NOTE not in s for i,s in enumerate(signs) if i!=5)
    original=st.components.v2.component
    def register(name,*args,**kwargs):
        if name=='natal_wheel':return lambda **params:SimpleNamespace(picked='sign:5')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(st.components.v2,'component',register)
    at=make_app(page='chart').run();assert_no_exception(at,'Virgo panel')
    assert any(NOTE in c.value and 'Great Introduction' in c.value for c in at.main.caption)
    panel=next(d.value for d in at.main.dataframe if list(d.value.columns)==['Dignity','Lord'])
    assert panel.iloc[3]['Lord']=='Mercury'


# Since the hostile pass of 2026-10-03 (L5-05) the table named is the one
# Sources shown shows: Sahl's under Course text, the Great Introduction's
# with the supplement; the note names both in either case.
@pytest.mark.parametrize('depth,partner,table',[('Course text','Mars','Sahl, The Introduction Ch. 1, 35-41'),
                                                 ('Course text and supplement','Mercury','Gr. Intr. V.14, 6-9')])
def test_virgo_syzygy_reference_discloses_source_in_page_and_export(depth,partner,table):
    # Real Virgo prenatal conjunction; the shared degree rulers feed page and export.
    at=make_app(page='victors',date='1240-09-01');at.session_state['_reading_depth']=depth
    at.run();assert_no_exception(at,'Virgo syzygy')
    frame=next(d.value for d in at.main.dataframe if 'Metric' in d.value.columns and 'Triplicity Lords' in list(d.value['Metric']))
    assert f'Partner: {partner}' in frame[frame['Metric']=='Triplicity Lords'].iloc[0]['Value']
    assert frame[frame['Metric']=='Virgo source note'].iloc[0]['Value']==NOTE
    assert table in frame[frame['Metric']=='Triplicity table'].iloc[0]['Value']
    assert NOTE in at.session_state['_analysis_markdown']
