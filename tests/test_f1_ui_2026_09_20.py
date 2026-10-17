"""The same selected Lot values in the Lots grid, exported analysis and image."""
import pytest
from conftest import make_app, assert_no_exception


@pytest.mark.parametrize('mode',['quadrant cusp','whole-sign place'])
@pytest.mark.parametrize('depth',['Course text','Course text and supplement'])
def test_lots_grid_export_and_image_agree(mode,depth):
    at=make_app(page='lots',switches={'lot_cusp':mode})
    at.session_state['_reading_depth']=depth
    at.session_state['_target_date']='2026-09-17'
    at.run()
    assert_no_exception(at)
    analysis=at.session_state['_analysis_export']
    topical=analysis['results']['Lots']['Topical Lots (Sahl, On Nativities)'][0]['rows']
    grid=next(df.value for df in at.main.dataframe if {'Lot','Formula','Status'}<=set(df.value.columns))
    assert grid[['Lot','Position','Formula','Status']].to_dict('records')==[
        {k:r[k] for k in ('Lot','Position','Formula','Status')} for r in topical]
    assert all(not {'Id','Operative','Longitude'}.intersection(r) for r in topical)
    tables=analysis['results']['Prediction']
    image=next(v[0]['rows'] for k,v in tables.items() if k.startswith('The image of the revolution'))
    emitted={r['Point']:r['Position'] for r in image if r['Chart']=='root' and r['Kind']=='Lot'}
    for r in topical:
        if r['Status'] in ('Available','Selected — read and directed'):
            assert emitted[r['Lot']]==r['Position']
        else:
            assert r['Lot'] not in emitted
    assert at.session_state['_lot_house_cusp']==mode
    assert next(r for r in analysis['readings'] if r['label']=='House-based Lot construction')['value']==mode  # ruling 28: no store_key


def test_new_chart_default_is_whole_sign_and_a_saved_cusp_choice_is_kept():
    # The owner's ruling on the F1 build (2026-09-20): whole-sign 0° stays the default -- the app's fallback
    # convention where the source is silent; the calculated cusp is the declared alternative, and a source that
    # prescribes its construction (the Lot of death, "by equation") ignores the control either way.
    fresh=make_app(page='lots').run()
    assert_no_exception(fresh)
    assert fresh.session_state['_lot_house_cusp']=='whole-sign place'
    explicit=make_app(page='lots',switches={'lot_cusp':'quadrant cusp'}).run()
    assert_no_exception(explicit)
    assert explicit.session_state['_lot_house_cusp']=='quadrant cusp'
