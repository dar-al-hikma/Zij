"""Editorial capitals are not emphasis. Quoted exceptions are fixed and cited.
No corpus access is performed at test time.
"""
import re
import pytest
from conftest import PAGES, CHARTS, READING_DEPTHS, make_app, assert_no_exception

ACRONYMS = frozenset('UT UTC LMT JD MC IC ASC DSC OA OD RA AD ARMC RAMC MSS WSM TP EST CDT IST DST IANA YYYY MM DD JN PN BA ITA GI WS TNAC E M H L B BW TBN ISBN JSON HTML CSV PDF PNG SVG API'.split())
# Exact printed fragments, not a blanket exemption for quotation marks.
QUOTED_CAPITALS = {
    "SR be the inner wheel": "PN IV, editor's introduction, p. 12 (Dykes's wheel convention)",
}
ROMAN = re.compile(r'(?=[MDCLXVI]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$')
WORD = re.compile(r'(?<![\w])[A-Z]{2,}(?![\w])')

def editorial_capitals(text):
    for fragment in QUOTED_CAPITALS:
        text = text.replace(fragment, '')
    return sorted({word for word in WORD.findall(text)
                   if word not in ACRONYMS and not ROMAN.fullmatch(word)})

def rendered_texts(node):
    """Include disclosures, table headers/cells, prose and widget help."""
    kind = getattr(node, 'type', '')
    if kind in {'markdown', 'caption', 'text', 'info', 'warning', 'error', 'success', 'title', 'header', 'subheader'}:
        yield str(node.value)
    if kind in {'dataframe', 'table'}:
        frame = node.value
        yield ' '.join(map(str, frame.columns))
        for row in frame.itertuples(index=False, name=None):
            for cell in row:
                yield str(cell)
    proto = getattr(node, 'proto', None)
    for field in ('help', 'label'):
        value = getattr(proto, field, '')
        if isinstance(value, str) and value:
            yield value
    for child in getattr(node, 'children', {}).values():
        yield from rendered_texts(child)

@pytest.mark.parametrize('date', CHARTS)
@pytest.mark.parametrize('depth', READING_DEPTHS)
@pytest.mark.parametrize('page', PAGES)
def test_rendered_editorial_capitals(page, depth, date):
    at = make_app(page=page, date=date)
    at.session_state['_reading_depth'] = depth
    at.session_state['_target_date'] = '2026-09-17'
    at.run()
    assert_no_exception(at, page)
    assert list(rendered_texts(at.main)), "The guard must inspect rendered content"
    bad = [(editorial_capitals(text), text[:400]) for text in list(rendered_texts(at.main)) + list(rendered_texts(at.sidebar)) if editorial_capitals(text)]
    assert not bad, bad

def test_capitals_guard_does_not_exempt_arbitrary_quotes_or_apostrophes():
    assert editorial_capitals('"UNTESTED" is this app\'s CLAIM') == ['CLAIM', 'UNTESTED']
    assert editorial_capitals('PN IV, MC, UTC; XVII') == []
    assert editorial_capitals('CIVIL MIXED') == ['CIVIL', 'MIXED']
