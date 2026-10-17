"""The cloud review of F10's diff (review-only PR #97, 2026-09-22): the two
findings, each pinned so it cannot return.

1. The Planetary Condition detail line wrote row['Weakness'] raw while its
   siblings went through _display_result; under the Mercury-sect
   alternatives the engine makes Weakness an UnresolvedResult, so the line
   printed the dataclass's repr.
2. The Sect table's fallback to planet_sect_is_diurnal was evaluated on
   every row as the eager default of dict.get, though the engine always
   supplies PlanetSect.
"""
from conftest import assert_no_exception, make_app


def _mercury_weakness_unresolved(module):
    """Wrap the evaluator so Mercury's Weakness is unresolved as the
    exact-conjunction case makes it, on any chart."""
    original = module.evaluate_abu_mashar_condition

    def patched(*args, **kwargs):
        results = original(*args, **kwargs)
        mercury = results['Mercury']
        n = mercury['Weakness']
        mercury['Weakness'] = module.UnresolvedResult(
            f'known subtotal {n}; the contrary-domain testimony depends on Mercury sect',
            'Firmicus, Mathesis III.7',
            (('if Mercury is diurnal', n), ('if Mercury is nocturnal', n + 1)),
            status='unassigned')
        return results
    return patched


def test_the_condition_detail_line_prints_an_unresolved_weakness_as_the_page_does(monkeypatch):
    at = make_app(page='configurations')
    import engine as module
    monkeypatch.setattr(module, 'evaluate_abu_mashar_condition', _mercury_weakness_unresolved(module))
    at.run()
    assert_no_exception(at, 'the Configurations page under an unresolved Weakness')
    box = [node for node in at.main.selectbox if node.key == 'planetary_condition_detail'][0]
    box.select(next(option for option in box.options if option == 'Mercury'))
    at.run()
    assert_no_exception(at, 'the Planetary Condition detail for Mercury')
    line = [node.value for node in at.main.markdown if node.value.startswith('**Mercury.**')]
    assert line, 'the detail line rendered'
    assert 'UnresolvedResult(' not in line[0], line[0]
    assert 'Weakness Unresolved' in line[0] or 'Weakness Unassigned' in line[0], line[0]


def test_the_sect_table_does_not_recompute_a_sect_the_engine_supplied(monkeypatch):
    # Every call to planet_sect_is_diurnal during the Dignities page must
    # come from the engine's own evaluators, none from the page's Sect
    # table loop: the engine's accidental row already carries PlanetSect.
    import sys
    at = make_app(page='dignities')
    import engine as module
    original = module.planet_sect_is_diurnal
    callers = []

    def counting(*args, **kwargs):
        callers.append(sys._getframe(1).f_code.co_filename)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'planet_sect_is_diurnal', counting)
    at.run()
    assert_no_exception(at, 'the Dignities page')
    assert callers, 'the engine called it'
    from_page = [c for c in callers if c.endswith('app.py')]
    assert not from_page, f'{len(from_page)} calls from the page'
