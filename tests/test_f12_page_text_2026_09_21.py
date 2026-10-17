"""Display changes retain boundary information and structured testimony results."""
import ast
import copy
import json
import math
from pathlib import Path
import pytest

@pytest.mark.parametrize('value', [4.9973, math.nextafter(5.0, 0), 5.0, math.nextafter(5.0, math.inf), -0.0001])
def test_detail_keeps_exact_value_beside_rounding(engine, value):
    text = engine['_fact']('Distance', value)
    assert text.startswith(f'Distance: {value:.2f} (unrounded: ')
    assert float(text.split('(unrounded: ')[1][:-1]) == value


def test_readable_export_testimonies_keep_uncertainty_without_dict_repr(engine):
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_markdown_table')
    # The cell printer moved to engine.py on 2026-09-22, when the HTML
    # export began sharing it; _markdown_table calls it, so the namespace
    # this is exec'd in must hold it.
    ns = {'json': json, '_export_cell': engine['_export_cell']}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'app.py', 'exec'), ns)
    # The engine's own shape: {'n', 'sentence', 'facts'} (engine.py, the
    # weakness testimonies' _add); 'result' where the answer is typed.
    rows = [{'Planet': 'Moon', 'Testimonies': [{'n': '93', 'sentence': 'Under the rays',
             'facts': ['Distance: 4.9973'], 'result': {'result_type': 'UnresolvedResult',
             'display': 'Unresolved — either condition', 'alternatives': [True, False]}}]}]
    before = copy.deepcopy(rows)
    text = ns['_markdown_table'](rows)
    assert 'Under the rays: Distance: 4.9973: Unresolved — either condition' in text
    assert '"facts"' not in text and '"result_type"' not in text
    assert rows == before


def test_meeting_refusal_names_its_own_sentence(engine):
    pd = {p: {'longitude': 120.0} for p in ('Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn')}
    row = engine['_sahl_examine_candidate']('the meeting (the last New Moon)', 0.0,
            pd, [i*30.0 for i in range(12)], 'Diurnal', (1,10,11,7,8))
    # Every dignity lord in Leo looks at Aries, so use averse Taurus for all.
    for p in pd: pd[p]['longitude'] = 30.0
    row = engine['_sahl_examine_candidate']('the meeting (the last New Moon)', 0.0,
            pd, [i*30.0 for i in range(12)], 'Diurnal', (1,10,11,7,8))
    assert not row['fit'] and '1.15, 15' in row['why']


def test_named_editorial_emphasis_is_also_removed_from_rare_result_branches():
    from conftest import engine_files
    trees = [ast.parse(p.read_text()) for p in engine_files()]   # each engine module by itself
    docstrings = {id(n.body[0].value) for tree in trees for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    phrases = ('ALONE is the governor', 'ALONE here', 'NOT JUDGED', 'NOT READ',
               'NOT computed', 'NOT tracked', 'THE RELEASER --', 'UNDERMINED after', 'BY SCOPE')
    bad = [(n.lineno, phrase) for tree in trees for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
           for phrase in phrases if phrase in n.value]
    assert not bad, bad


def test_the_real_export_renders_testimonies_readably():
    # The check's finding 17: the branch keyed on a 'label' the engine never
    # writes, so the exported Testimonies column still printed dict JSON.
    from conftest import make_app
    at = make_app(page='dignities')
    at.run(timeout=180)
    md = at.session_state['_analysis_markdown']
    assert '"facts"' not in md and '"sentence"' not in md and '"result_type"' not in md
    assert 'In its own share of dignity (79)' in md
