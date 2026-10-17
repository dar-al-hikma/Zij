"""F9 source distinctions, scope boundaries and shared display contracts."""
import ast
import json
from pathlib import Path
import pytest
from conftest import make_app, assert_no_exception, ui_source

COL = 'Stated topic condition — app assessment'
NOTE = "Named pairs require both planets and their stated configuration; the eighth-house Jupiter–Venus sentence has uncertain Node scope, Jupiter (PN IV II.9, 15) uses a translator-supplied 'not' with a possible 'even if received' reading, and entries stating no reception or affliction condition are identified as such rather than silently assigned one."
INTRO = "This grid paraphrases Dykes's printed translation of Sahl's Māshā'allāh passages, marks material variants, doubts and conjectural reconstruction, and assesses the eight explicit topic conditions using the app's stated aspect convention (lord only for the seventh), with separate notes for the other four rows."
UNSTATED = {
    1: 'No section-wide neutrality condition stated (1.36, 78–97)',
    2: 'No matching neutrality condition stated; introductory testimony qualification at 2.14, 1',
    5: 'No explicit neutrality gate for the fifth-lord list; 5.1, 91 conditionally turns to the Lot of children (fnn 49–50)',
    8: 'No section-wide neutrality condition stated; local qualification at 8.5, 2',
}

@pytest.fixture(autouse=True)
def isolated_readings(engine):
    old = dict(engine['_RUN'].__dict__)
    engine['_RUN'].__dict__.clear()
    yield
    engine['_RUN'].__dict__.clear()
    engine['_RUN'].__dict__.update(old)


def data(**values):
    return {p: {'longitude': lon} for p, lon in values.items()}


@pytest.mark.parametrize('house,reason',UNSTATED.items())
def test_unstated_topics_do_not_run_an_affliction_test(engine,house,reason):
    # No chart data is needed to decide that the source did not state this gate.
    result=engine['mashaallah_condition'](house,'Mars',{},0.)
    assert isinstance(result,engine['UnresolvedResult'])
    assert result.reason==reason and result.alternatives==()
    with pytest.raises(TypeError): bool(result)


def test_seventh_names_the_lord_not_the_house(engine):
    # Saturn in Libra afflicts the seventh sign; Mercury in Leo is clear.
    p=data(Mercury=125,Saturn=185)
    assert engine['mashaallah_condition'](7,'Mercury',p,5)==('met','')
    # Same geometry, sign-and-lord topic: its sign remains tested.
    assert engine['mashaallah_condition'](3,'Mercury',p,125)[0]=='not met'
    p['Saturn']['longitude']=215
    status,why=engine['mashaallah_condition'](7,'Mercury',p,5)
    assert status=='not met' and why=='Saturn square its lord Mercury'


def test_fortune_targets_and_self_exclusion(engine):
    p=data(Mercury=125,Jupiter=185)
    assert engine['mashaallah_condition'](7,'Mercury',p,5)[0]=='not met' # sextile lord
    p['Jupiter']['longitude']=185
    assert engine['mashaallah_condition'](7,'Jupiter',p,5)==('met','')
    assert engine['mashaallah_condition'](7,'Mars',data(Mars=185),5)==('met','')


def test_fitting_convention_does_not_spread_into_topic_condition(engine):
    p=data(Mercury=125,Saturn=215)
    expected=engine['mashaallah_condition'](7,'Mercury',p,5)
    engine['set_readings'](SOFTENED_INFORTUNE='Saturn')
    assert engine['mashaallah_condition'](7,'Mercury',p,5)==expected


def test_twelve_rows_eight_assessments_and_visible_row_sources(engine):
    p=data(Sun=5,Moon=45,Mercury=125,Venus=275,Mars=215,Jupiter=35,Saturn=185)
    rows=engine['evaluate_house_lords'](p,5)
    assert len(rows)==12
    for row in rows:
        h=row['Topical House'];v=row[COL]
        assert "Masha'allah's condition" not in row
        if h in UNSTATED: assert isinstance(v,engine['UnresolvedResult']) and v.reason==UNSTATED[h]
        else: assert isinstance(v,str) and (v=='Met' or v.startswith('Not met: '))
        assert row["Masha'allah Signification"]
    assert rows[6]['Condition source']=='7.1, 217 — the lord of the seventh; fn 135: \'Omitting "in the seventh"\''
    assert set(engine['MASHAALLAH_CONDITION_SOURCES'])=={3,4,6,7,9,10,11,12}


@pytest.mark.parametrize('house,pair,page,words',[
 (8,('Saturn','Mars'),85,('without Jupiter and Venus','banished')),
 (8,('Jupiter','Venus'),86,('alone','Node scope uncertain; may continue the preceding Ascending Node premise')),
 (9,('Saturn','Mars'),88,('matutine or stationary','Lot of Fortune in the Ascendant')),
 (10,('Saturn','Mars'),92,('aspecting Jupiter, Venus and the Sun','especially with the Moon there')),
])
def test_joint_passage_has_one_identity_and_count(engine,house,pair,page,words):
    ph=engine['PLANETS_IN_HOUSES'];cite=f'Ch. 57, the {engine["HOUSE_ORDINAL"][house]} '
    found=[[e for e in ph[house][p]['Rhetorius'] if e['cite'].endswith(f'p. {page}') and e['conditional']] for p in pair]
    a,b=found[0][0],found[1][0]
    assert a is b and a['axis']=='joint' and a['testimony_id']==b['testimony_id']
    assert all(w in a['text'] for w in words)
    assert 'Joint configuration — both named planets required; no day/night division stated' in engine['rhetorius_entry_text'](a)
    ps=data(**{p:(house-1)*30+5 for p in pair})
    assert engine['topical_testimony_count'](ps,0)==sum(len(ph[house][p]['Rhetorius']) for p in pair)-1
    # One indexed member still exposes the condition; no automatic applicability claim.
    assert engine['topical_testimony_count'](data(**{pair[0]:(house-1)*30+5}),0)==len(ph[house][pair[0]]['Rhetorius'])


@pytest.mark.parametrize('house',[2,6,8,12])
def test_jupiter_shared_reception_dispute_and_separate_affliction(engine,house):
    c=engine['PLANETS_IN_HOUSES'][house]['Jupiter']['PN IV']
    assert len(c['Shared'])==1
    t=c['Shared'][0]['text']
    for w in ('<not> received',"'not' supplied by the translator","possibly 'even if he is received'",'lord of the year','revolution of the year especially','no eminence','no increase in rank','brothers and acquaintances shun','little occupied','II.6, 22'):assert w in t
    assert 'II.9, 15' not in c['Good']['text']+c['Bad']['text']
    assert 'II.9, 16' in c['Bad']['text'] and 'made unfortunate' in c['Bad']['text']


@pytest.mark.parametrize('house',[3,6,9,12])
def test_venus_shared_scope_and_strengthening_clause(engine,house):
    c=engine['PLANETS_IN_HOUSES'][house]['Venus']['PN IV']
    t=c['Shared'][0]['text']
    for w in ('reception/affliction condition not stated','in the revolution','or is harmed','Strengthening only','year terminated','Saturn in the root and Saturn','terminal sign',"revolution's Ascendant",'probably','fn 289','Fn 290',"this app's mapping"):assert w in t
    assert 'II.18, 18' not in c['Good']['text']+c['Bad']['text']


@pytest.mark.parametrize('h,p,cite,flag',[
 (4,'Saturn','Ch. 57, the fourth, pp. 69-70',True),(12,'Saturn','Ch. 57, the twelfth, p. 46',True),
 (3,'Moon','Ch. 57, the third, p. 62',True),(5,'Mars','III.4, 26-28',True),(11,'Venus','III.6, 59-62',True),
 (4,'Saturn','Ch. 57, the fourth, p. 68',False),(4,'Mars','Ch. 57, the fourth, pp. 68-69',False),(5,'Sun','Ch. 57, the fifth, p. 72',False),
])
def test_flag_scope(engine,h,p,cite,flag):
    e=next(e for e in engine['PLANETS_IN_HOUSES'][h][p]['Rhetorius'] if e['cite']==cite and (h != 12 or e['text'].startswith('Squaring or opposing')))
    assert e['conditional'] is flag


def test_flag_counts_and_portional_inheritance(engine):
    entries=[e for row in engine['PLANETS_IN_HOUSES'].values() for cell in row.values() for e in cell['Rhetorius']]
    assert sum(e['conditional'] for e in entries)==62
    assert sum(e['portional'] for e in entries)==36
    assert next(e for e in entries if e['cite']=='III.3, 47')['portional']
    assert not next(e for e in entries if e['cite']=='III.2, 18-20')['portional']


@pytest.mark.parametrize('jd,planet,house,excluded',[(2415090.25,'Saturn',4,'Aspecting the Moon'),(2415048.5,'Moon',3,'Ruling the Ascendant')])
def test_readers_chart_defers_configuration_but_keeps_detail(engine,jd,planet,house,excluded):
    c=engine['calculate_traditional_chart_jd'](jd,43.7792,11.2463)
    assert engine['get_wsh_house'](c['planetary_data'][planet]['longitude'],c['ascendant'])==house
    cond={p:{'Net':0,'Condition':'Good'} for p in c['planetary_data']}
    r=next(r for r in engine['evaluate_planets_in_houses'](c['planetary_data'],cond,c['ascendant']) if r['Planet']==planet)
    assert excluded not in r['Rhetorius and Firmicus, as the texts state it']
    assert any(excluded in e for e in r['Entries'])


@pytest.mark.parametrize('address,word',[
 ((11,5),"fn 48 prefers 'they'"),((2,5),"fn 45 suggests 'he,'"),((8,3),'Translation speculative; fn 115'),
 ((6,1),'fn 489'),((3,4),"E: 'he'; M: 'they,'"),((5,4),'absent from both manuscripts'),
 ((12,6),"'they will not come' [to harm]"),((9,10),"M: 'the good will be strengthened.'"),
 ((10,11),"E's 'youth'"),((8,11),'loss of his neighbors and friends')])
def test_material_markers_live_with_their_cell(engine,address,word):
    h,r=address;cell=engine['MASHAALLAH_LORDS'][h][r]
    assert word in cell['note']


def test_antecedent_and_illegibility_not_resolved(engine):
    cells=engine['MASHAALLAH_LORDS']
    assert "antecedent of 'it' uncertain: either lord" in cells[7][2]['text']
    assert 'servant women' in cells[7][2]['text'] and 'not received' in cells[7][2]['text']
    assert 'instead' not in cells[6][1]['text']
    assert 'Partly illegible' in cells[8][5]['text'] and 'tentative' in cells[8][5]['text']
    assert 'they will survive and will be miscarried' in cells[8][5]['detail']
    assert '<do not>' in cells[12][6]['text']


def test_required_sentences_and_no_yes_no_coercion():
    source=ui_source()
    assert NOTE in source and INTRO in source
    tree=ast.parse(source)
    f=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_yes_no_columns')
    # It configures named columns only; it does not bool() any cell.
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='bool' for n in ast.walk(f))


@pytest.mark.parametrize('page',['dignities','findings','sources'])
def test_unstated_cells_survive_every_page_and_export(engine,page):
    at=make_app(page=page).run();assert_no_exception(at,page)
    for n in at.main:
        if getattr(n,'type',None) in ('markdown','caption','table','dataframe'):assert 'UnresolvedResult(' not in str(n.value)
    results=at.session_state['_analysis_export']['results']['Dignities and places']
    rs=results["Topical House Lords (Masha'allah)"][0]['rows']
    for row in rs:
        if row['Topical House'] in UNSTATED:
            v=row[COL];assert v['result_type']=='UnresolvedResult' and v['reason']==UNSTATED[row['Topical House']]
        assert row["Masha'allah Signification"]
    assert 'UnresolvedResult(' not in at.session_state['_analysis_markdown']
    if page=='dignities':
        grid=next(d.value for d in at.main.dataframe if COL in d.value.columns)
        table=next(t.value for t in at.main.table if COL in t.value.columns)
        assert sum(str(v).startswith('Unresolved —') for v in grid[COL])==4
        assert list(grid[COL])==list(table[COL])
        assert 'fn 135' in grid.iloc[6]['Condition source']
        box=next(b for b in at.main.selectbox if b.key=='topical_house_lords_masha_allah_detail')
        for i in (0,1,4,7):
            box=next(b for b in at.main.selectbox if b.key=='topical_house_lords_masha_allah_detail')
            box.select(box.options[i]);at.run();assert_no_exception(at,'unstated detail')
            assert any(UNSTATED[i+1] in m.value for m in at.main.markdown)
    if page=='sources':assert any(engine['FITTING_INFORTUNE_QUOTE'] in m.value for m in at.main.markdown)


def test_full_choices_quote_and_target_independent_selection(engine):
    assert 'lord of the distribution' in engine['FITTING_INFORTUNE_QUOTE']
    assert engine['FITTING_INFORTUNE_QUOTE'].endswith('lord of the Ascendant of the year.')
    assert "not evaluated here" in engine['FITTING_INFORTUNE_STANDING']
    assert engine['FITTING_INFORTUNE'] is False
    assert engine['fitting_infortune'](275)=='Saturn'
    assert engine['fitting_infortune'](215)=='Mars'
    assert engine['fitting_infortune'](95) is None
    assert engine['INFORTUNES']=={'Saturn','Mars'}
    engine['set_readings'](SOFTENED_INFORTUNE='Saturn')
    assert engine['effective_infortunes']()=={'Mars'} and 'Saturn' in engine['INFORTUNES']


def test_target_date_does_not_change_fitting_natal_results(engine):
    at=make_app(page='configurations',date='1240-10-05',switches={'fitting':True})
    snapshots=[]
    for date in ('1241-10-05','1290-10-05'):
        at.session_state['_target_date']=date
        at.run();assert_no_exception(at,'dated fitting switch')
        cb=next(b for b in at.main.checkbox if b.label.startswith('Fitting infortune:'))
        assert engine['FITTING_INFORTUNE_QUOTE'] in cb.help
        assert 'lord of the distribution' in cb.help and 'Ascendant of the year' in cb.help
        export=at.session_state['_analysis_export']['results']
        snapshots.append((export['Configurations'], export['Dignities and places']))
    assert snapshots[0]==snapshots[1]
    assert any('Fitting infortune in force:' in c.value for c in at.main.caption)


def test_shared_passage_is_read_by_table_detail_and_export(monkeypatch,engine):
    import engine as module
    original=module.evaluate_planets_in_houses
    def two_shared_rows(*args):
        return original(data(Jupiter=35,Venus=65),{'Jupiter':{'Net':5,'Condition':'Good'},'Venus':{'Net':-5,'Condition':'Bad'}},0)
    monkeypatch.setattr(module,'evaluate_planets_in_houses',two_shared_rows)
    at=make_app(page='dignities').run();assert_no_exception(at,'shared source passages')
    table=next(t.value for t in at.main.table if 'Shared PN IV passages' in t.value.columns)
    assert '&lt;not&gt; received' in table.iloc[0]['Shared PN IV passages']
    assert 'reception/affliction condition not stated' in table.iloc[1]['Shared PN IV passages']
    for planet in ('Jupiter','Venus'):
        box=next(b for b in at.main.selectbox if b.key=='topical_planets_in_houses_detail')
        box.select(planet);at.run();assert_no_exception(at,planet+' detail')
        passages=[m.value for m in at.main.markdown if m.value.startswith('**Shared PN IV passages.**')]
        assert len(passages)==1
        if planet=='Jupiter':assert '&lt;not&gt; received' in passages[0] and "possibly 'even if he is received'" in passages[0]
        else:assert 'Strengthening only' in passages[0] and 'probably' in passages[0]
    rows=at.session_state['_analysis_export']['results']['Dignities and places']['Topical Planets in Houses'][0]['rows']
    assert '<not> received' in rows[0]['Shared PN IV passages']
    assert 'II.9, 15' not in rows[0]['If in a bad condition']
    assert '&lt;not&gt; received' in at.session_state['_analysis_markdown']


def test_unrelated_halves_and_class_testimony_remain_controls(engine):
    table=engine['PLANETS_IN_HOUSES']
    for h in range(1,13):
        for p in ('Saturn','Mars','Sun','Mercury','Moon'):
            assert table[h][p]['PN IV']['Shared']==()
    sat=table[2]['Saturn']['PN IV']['Bad']['text']
    assert 'II.6, 22-24' in sat and 'not received as well' in sat and 'retrograde, harsher again' in sat
    assert any(e['axis']=='general malefic' for e in table[1]['Saturn']['Rhetorius'])
    for h in (3,9):
        txt=table[h]['Mercury']['PN IV']['Good']['text']
        assert 'condition not explicitly stated; followed by an expressly adverse case in §9' in txt
        assert 'inferred from that contrast' in txt


def test_reception_does_not_cancel_the_local_moon_clause(engine):
    text=engine['MASHAALLAH_LORDS'][6][1]['text']
    assert 'if received, illnesses occur' in text
    assert 'if the Moon is also corrupted and connects with a planet in a corrupt place, he becomes a slave' in text
    fourth=engine['MASHAALLAH_LORDS'][5][4]['text']
    assert 'if no infortune looks while the fortunes do' in fourth


def test_the_fifth_lord_in_the_eighth_prints_its_locator_once(engine):
    # The check's finding 16: the cell's text had ended with "(5.1, 85 fn 47)"
    # and evaluate_house_lords appended the cite again.
    cell = engine['MASHAALLAH_LORDS'][8][5]
    assert cell['cite'] == '5.1, 85 fn 47'
    assert 'fn 47' not in cell['text']
    # Every cell: the text never carries its own cite in parentheses.
    for placed_in, lords in engine['MASHAALLAH_LORDS'].items():
        for house, c in lords.items():
            assert c['cite'] and f"({c['cite']})" not in c['text'], (placed_in, house)
