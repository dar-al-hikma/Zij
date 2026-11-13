"""The wheel's look, chosen whatever the page's mode; the square wheel at the
page's content width; the note on the wheel under a plain look; two small tables
at a set gap; and two one-line slips the rules did not catch.

Invented charts only: the app's opening chart and the invented ones of the
Options box's tests.
"""
import ast
import json
import re

import pytest

import house_style
import wheel
from conftest import APP_PATH, assert_no_exception, make_app, natal_wheel_envelope, ui_source
from test_wheel_follows_the_page import (DOWNLOAD, GROUND, _choose, _ground, handed, images, prefs,
                                         the_options_stand_as_they_were)
from test_wheel_options_2026_11_05 import THEMES, _assert_one_ink_one_ground, _natal_style, charts, _natal

__all__ = ["handed", "images", "prefs", "the_options_stand_as_they_were", "charts"]

FOLLOW, LIGHT, DARK, PLAIN, PLAIN_DARK = wheel.WHEEL_LOOK_OPTIONS
LIGHT_PALETTE, DARK_PALETTE = house_style.WHEEL_PALETTES["light"], house_style.WHEEL_PALETTES["dark"]
# Each look's ground, on any page.
LOOK_GROUND = {LIGHT: LIGHT_PALETTE["bg"], DARK: DARK_PALETTE["bg"], PLAIN: "#FFFDF6", PLAIN_DARK: DARK_PALETTE["bg"]}
LOOK_THEME = {LIGHT: "light", DARK: "dark", PLAIN: "light", PLAIN_DARK: "dark"}


# --- the control ---------------------------------------------------------------

def test_the_five_looks_in_their_order():
    assert wheel.WHEEL_LOOK_OPTIONS == ("Follow the page", "Light", "Dark", "Plain", "Plain dark")


@pytest.mark.parametrize("page_theme", [None, "light", "dark"])
def test_each_look_asks_for_its_own_palette_whatever_the_page(page_theme):
    assert wheel.wheel_look(FOLLOW, page_theme) == (page_theme, False)
    assert wheel.wheel_look(LIGHT, page_theme) == ("light", False)
    assert wheel.wheel_look(DARK, page_theme) == ("dark", False)
    assert wheel.wheel_look(PLAIN, page_theme) == ("light", True)
    assert wheel.wheel_look(PLAIN_DARK, page_theme) == ("dark", True)
    assert wheel.wheel_look("no such look", page_theme) == (page_theme, False)


def test_the_two_plain_grounds_and_their_inks_are_the_owner_s():
    plain, plain_dark = wheel._wheel_palette("light", plain=True), wheel._wheel_palette("dark", plain=True)
    assert (plain["bg"], plain["ink"]) == ("#FFFDF6", LIGHT_PALETTE["ink"])
    assert (plain_dark["bg"], plain_dark["ink"]) == (DARK_PALETTE["bg"], DARK_PALETTE["ink"])


def test_a_look_chooses_a_palette_and_moves_no_line(engine, charts):
    """Light on a dark page is the very drawing a light page draws, and so on."""
    entry = charts[0]
    for look in (LIGHT, DARK, PLAIN, PLAIN_DARK):
        theme, plain = wheel.wheel_look(look, "dark")
        same_on_a_light_page = wheel.wheel_look(look, "light")
        assert same_on_a_light_page == (theme, plain)
        drawn = _natal(engine, entry, theme=theme, plain=plain)
        assert _natal(engine, entry, theme=same_on_a_light_page[0], plain=same_on_a_light_page[1]) == drawn
        if plain:
            _assert_one_ink_one_ground(drawn, theme)


# --- on the page ----------------------------------------------------------------

@pytest.mark.parametrize("page", ["chart", "timing"])
@pytest.mark.parametrize("layout", ["Square", "Wide"])
def test_each_look_is_one_picture_on_either_page_mode_shown_and_saved_alike(page, layout, prefs, handed):
    at = make_app(page=page, timeout=300)
    at.session_state["_wheel_layout"] = layout
    at.run()
    assert_no_exception(at, page)
    for look in (LIGHT, DARK, PLAIN, PLAIN_DARK):
        at.radio(key="wheel_look").set_value(look).run(timeout=300)
        assert_no_exception(at, look)
        seen = {}
        for word in ("Dark", "Light"):
            _choose(at, word)
            saved = handed[DOWNLOAD[page]]
            seen[word] = saved.decode() if isinstance(saved, bytes) else saved
            assert _ground(seen[word]) == LOOK_GROUND[look], (look, word)
            if page == "chart":
                assert wheel.saved_svg(natal_wheel_envelope(at.main)["svg"]) == seen[word], "shown and saved alike"
        assert seen["Dark"] == seen["Light"], f"{look} moved with the page"
        if look in (PLAIN, PLAIN_DARK):
            _assert_one_ink_one_ground(seen["Light"], LOOK_THEME[look])
        else:
            assert len(set(re.findall(r'#[0-9A-Fa-f]{6}\b', seen["Light"]))) > 2, "a coloured look kept its colours"
    at.radio(key="wheel_look").set_value(FOLLOW).run(timeout=300)
    for word in ("Dark", "Light"):
        _choose(at, word)
        assert _ground(handed[DOWNLOAD[page]]) == GROUND[word], "back to following the page"


def test_the_strips_follow_the_page_and_not_the_look(prefs, images):
    prefs.write_text(json.dumps({"_wheel_look": PLAIN_DARK}))
    at = make_app(page="timing", timeout=300).run()
    assert_no_exception(at, "timing")
    for word in ("Dark", "Light"):
        _choose(at, word)
        images.clear()
        strips = make_app(page="releaser", timeout=300).run()
        assert_no_exception(strips, "releaser")
        pictures = [image for image in images if isinstance(image, str) and "<svg" in image]
        assert pictures and {_ground(picture) for picture in pictures} == {GROUND[word]}, word


def test_the_stored_look_carries_between_the_pages_and_a_new_session(prefs):
    at = make_app(page="timing", timeout=300).run()
    at.radio(key="wheel_look").set_value(DARK).run(timeout=300)
    assert_no_exception(at, "timing")
    assert json.loads(prefs.read_text())["_wheel_look"] == DARK
    again = make_app(page="chart", timeout=300).run()
    assert again.radio(key="wheel_look").value == DARK


@pytest.mark.parametrize("held", [{"_wheel_plain": True}, {"_wheel_look": "Sepia"}, {"_wheel_look": 3}, {"_wheel_look": ["Plain"]}],
                         ids=["the-first-form-s-key", "no-such-look", "a-number", "a-list"])
def test_a_file_holding_what_is_no_look_opens_following_the_page(held, prefs):
    prefs.write_text(json.dumps({"_launches": 3, **held}))
    at = make_app(page="chart", timeout=300).run()
    assert_no_exception(at, "chart")
    assert at.radio(key="wheel_look").value == FOLLOW
    assert "_wheel_plain" not in at.session_state


# --- the note on the wheel under each look ----------------------------------------

def _note_on_the_wheel(at):
    box = next(e for e in at.main.expander if e.label == "How the wheel is drawn")
    return "\n".join(m.value for m in box.markdown)


@pytest.mark.parametrize("look", wheel.WHEEL_LOOK_OPTIONS)
def test_the_note_says_shaded_and_tinted_only_of_a_wheel_that_is(look):
    at = make_app(page="timing", timeout=300)
    at.session_state["_wheel_look"] = look
    at.run()
    assert_no_exception(at, look)
    note = _note_on_the_wheel(at)
    if look in (PLAIN, PLAIN_DARK):
        assert "shaded sign" not in note and "tinted" not in note
        # What the words stood in: the row and the sentence close whole.
        assert "at the revolution's moment, the year's or the month's (PN IV Figures 2, 65) |" in note
        assert "the year's or the month's (PN IV Figures 2, 65)." in note
    else:
        assert "| shaded sign | the sign of the terminal point of the year (fn 33) |" in note
        assert note.count("with its bound tinted") == 2
    # Dykes's own sentence of his figure stands under every look.
    assert 'which I have shaded in grey' in note


# --- the square wheel at the page's content width -----------------------------------

def test_the_square_wheel_is_bounded_by_the_content_width_and_the_window_alone():
    """Neither wheel has a column of its own; the one measure is the page's."""
    source = ui_source()
    assert "with st.container(width=PROSE_WIDTH):\n                picked = NATAL_WHEEL(" not in source
    assert 'st.container(width=PROSE_WIDTH, key="wheel-column")' not in source
    assert "width: min(100%, var(--zij-wheel-window, 100%));" in _natal_style()
    assert "img{display:block;width:min(100%,var(--zij-wheel-window))!important;margin:0 auto;}" in house_style.PAGE_STYLE
    # Streamlit's boxes round the image shrink to its own 1000 pixels without this.
    frame = '.st-key-wheel-column [data-testid="stFullScreenFrame"]:not(:has([aria-label="Close fullscreen"]))'
    assert f'{frame}>div,{frame} [data-testid="stImage"]{{width:100%;}}' in house_style.PAGE_STYLE


def _natal_script():
    tree = ast.parse(ui_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "NATAL_WHEEL_JS":
            return node.value.value
    raise AssertionError("no NATAL_WHEEL_JS")


def test_the_component_takes_the_square_wheel_s_measure():
    """Without this class the natal wheel fills whatever holds it, off the
    window's height: nothing in the page's rules would say so."""
    assert 'wrap.classList.toggle("nw-column", !stretch);' in _natal_script()
    assert 'const stretch = data.width === "stretch";' in _natal_script()
    assert '"width": "stretch" if _picked_wide else "column",' in ui_source()


def test_the_exit_button_stands_inside_its_box():
    """Placed from the box's corner: an offset below nothing puts it out of the window."""
    rule = re.search(r"\.nw-expand\s*\{([^{}]*)\}", _natal_style()).group(1)
    for side in ("top", "right"):
        found = re.search(rf"(?:^|\s){side}:\s*(-?[\d.]+)(rem|px)?;", rule)
        assert found, f"{side} is not stated"
        assert float(found.group(1)) >= 0, rule
    assert "left:" not in rule and "bottom:" not in rule and "transform" not in rule and "margin" not in rule


# --- two small tables at a set gap ---------------------------------------------------

def _block_holding(at, heading):
    """The row and the places in it, for the place whose first child is this subheader."""
    def walk(node):
        for child in getattr(node, "children", {}).values():
            kids = getattr(child, "children", None)
            if not kids:
                continue
            for place in kids.values():
                inner = list(getattr(place, "children", {}).values())
                if inner and getattr(inner[0], "value", None) == heading:
                    return child
            found = walk(child)
            if found is not None:
                return found
        return None
    row = walk(at.main)
    assert row is not None, heading
    return row


def test_the_helper_stands_two_tables_at_a_set_gap_and_lets_them_wrap():
    source = ui_source()
    assert source.count("_two_tables(") == 3, "the helper's two callers, and the line that defines it"
    assert "def _two_tables(name):" in source
    assert 'row = st.container(key=f"zij-two-tables-{name}", horizontal=True, gap="medium")' in source
    assert 'return row.container(width="content"), row.container(width="content")' in source
    assert 'points_col, cusps_col = _two_tables("points")' in source and 'columns = _two_tables("panel")' in source
    assert "points_col, cusps_col = st.columns(2)" not in source


def test_a_caption_or_a_warning_does_not_widen_its_place():
    """Their one long line would take the whole row and put the second table
    under the first at every width."""
    assert ('[class*="st-key-zij-two-tables-"] [data-testid="stElementContainer"]:has([data-testid="stCaptionContainer"],'
            '[data-testid="stAlert"]){contain:inline-size;}') in house_style.PAGE_STYLE


def test_calculated_points_and_quadrant_divisions_stand_in_one_wrapping_row():
    at = make_app(page="chart", timeout=120).run()
    assert_no_exception(at, "chart")
    row = _block_holding(at, "Calculated Points")
    assert row.proto.flex_container.direction == row.proto.flex_container.Direction.HORIZONTAL
    assert row.proto.flex_container.wrap is True
    places = list(row.children.values())
    assert len(places) == 2
    assert all(place.proto.width_config.use_content for place in places), "each as wide as it holds"
    assert list(places[1].children.values())[0].value == "Quadrant divisions (Alchabitius)"
    assert not at.main.columns or not any(
        list(column.children.values()) and getattr(list(column.children.values())[0], "value", "") == "Calculated Points"
        for column in at.main.columns), "a column of the page's half is back"


def test_the_grid_tells_its_place_how_wide_it_is():
    """The place is as wide as what it holds only if the grid's width is pixels."""
    source = APP_PATH.read_text(encoding="utf-8")
    assert 'width = natural + _GRID_FRAME if natural <= _GRID_NARROWEST_PAGE else "content"' in source
