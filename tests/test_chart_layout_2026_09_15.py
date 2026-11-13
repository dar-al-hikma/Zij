"""The Chart page with the wheel at centre stage.

The layout: the wheel's controls in one Options box above it, the wheel
centred in the reading column, the three introductory sentences beneath it, and the
header metrics row gone -- its lunation moved into the chart strip, which
every page carries.

These tests read the rendered page's element order, not only its source, so the
arrangement itself is pinned: the box, then the wheel block, then
the four sentences (body text at reading width in one container; captions
before).
"""
import pytest

from conftest import (PAGES, READING_DEPTHS, assert_no_exception, make_app,
                      natal_wheel_envelope, ui_source)

# The four paragraphs, verbatim, as the page prints them. The first is the
# README's opening word for word: one description of what this
# is, wherever a reader meets it, and no course reference in page text.
INTRO = (
    "A *z\u012bj* is a set of astronomical tables with the rules for using them. This one is a "
    "study companion for traditional natal astrology: cast a chart, then check, table by "
    "table, what the texts say about it.",
    "The texts are *The Astrology of Sahl b. Bishr*, vol. I, and Abū Ma'shar's *On the "
    "Revolutions of the Years of Nativities* (*Persian Nativities* IV), in Benjamin Dykes's "
    "translations, with his *Great Introduction* as the supplement. Every rule applied on "
    "a page names its sentence.",
    "Enter or load a nativity in the sidebar. The Nativity sets out what the chart contains, "
    "Prediction what the year holds; the reference tables and the sources close the page "
    "list. The judgment is the astrologer's.",
    "Click a planet or a sign on the wheel for what the tables say of it; hover a sign for its bounds and triplicity lords.",
)
LAYOUTS = ["Square", "Wide"]


def _chart(layout=None, view=None, **state):
    at = make_app(page="chart", view=view)
    if layout is not None:
        at.session_state["_wheel_layout"] = layout
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at, f"chart, {layout or 'default'} layout")
    return at


def _kids(at):
    return list(at.main.children.values())


def _kinds(block):
    return [type(child).__name__ for child in block.children.values()]


# The wheel and its controls are one @st.fragment now,
# and a fragment renders as a block of its own: main's third child is that
# block, and the Options box and the picture are ITS two children. Every
# element the fragment draws is inside it, which is what a fragment requires
# -- it may not write to a container outside itself -- and it is why the
# four captions and the circumpolar warning, which stay outside, moved up
# one index in main's own children.
def _fragment(at):
    # After the header, the strip and the readings note's fixed slot
    # (an unfilled st.empty() on the default chart).
    return _kids(at)[3]


def _frag_kids(at):
    return list(_fragment(at).children.values())


# --- The metrics row is gone ---------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("view", READING_DEPTHS)
def test_the_chart_page_renders_no_metric(layout, view):
    """The four st.metric calls under the wheel -- lunation, sect, day lord,
    hour lord -- were the header row. Three of the four were already in the
    chart strip; the fourth joined it."""
    at = _chart(layout=layout, view=view)
    assert len(at.main.metric) == 0, [m.label for m in at.main.metric]


def test_no_page_carries_the_old_header_metrics():
    src = ui_source()
    for gone in ('.metric("Prenatal lunation"', '.metric("Sect"',
                 '.metric("Lord of the Day"', '.metric("Lord of the Hour"',
                 'hdr1, hdr2, hdr3, hdr4'):
        assert gone not in src, gone


# --- The lunation in the strip -------------------------------------------

@pytest.mark.parametrize("page", PAGES)
def test_the_strip_names_the_lunation_after_the_sect(page):
    at = make_app(page=page).run()
    assert_no_exception(at, page)
    # Line one is the nativity as entered, line two what the app reads from
    # it, and the lunation is on the second, after the sect.
    entered, read = at.main.caption[0].value.split("  \n")
    assert len(entered.split(" · ")) == 4, entered
    parts = read[2:-2].split(" · ")          # line two is bold; strip the markers
    assert len(parts) == 4, parts
    # The harness's chart: 1240-05-23, Florence. Its prenatal syzygy is a
    # conjunction, and the strip says so in one word.
    assert parts[0] == "Diurnal"
    assert parts[1] == "Conjunctional lunation", parts[1]
    assert parts[2].startswith("Day lord ")
    assert parts[3].startswith("Hour lord ")


def test_the_strip_takes_the_first_word_of_the_event_label():
    """"Conjunctional (New Moon)" and "Preventional (Full Moon)" are the two
    labels; the strip prints the first word and " lunation", and the degree
    and house stay on the lunation and victors page."""
    src = ui_source()
    assert "syzygy['event_label'].partition(' ')[0]" in src
    assert 'f"{lunation} lunation"' in src


def test_the_strip_breaks_between_the_nativity_and_the_reading():
    """Eight parts on one line wrapped wherever the window width fell, which
    put the break in a different place on every page. The two groups are
    joined with a caption hard break instead -- two spaces and a newline, as
    the sidebar's own boxes break a caption."""
    at = _chart()
    entered, read = at.main.caption[0].value.split("  \n")
    assert entered == "Unsaved chart · 1240-05-23 14:30:00 · LMT +00:44:59 · 43.78, 11.25"
    # Line two is bold: the four are measurements the app made, and nothing
    # else above the fold states them. One pair of markers round the joined
    # line, not one pair per part.
    assert read == "**Diurnal · Conjunctional lunation · Day lord Mercury · Hour lord Moon**"
    assert read.count("*") == 4
    assert '"  \\n".join((entered, f"**{read}**"))' in ui_source()


# --- The wheel, centred --------------------------------------------------

def test_the_square_wheel_stands_in_the_page_s_content_width():
    """No column of its own: the mount spans the page's content width, and the
    component centres the picture there and holds it to the window's height.
    A column capped it, by the page's fraction (the middle of [1, 2, 1] drew it
    at 394 px at 1280) and by the reading column (680, at a 3840 window)."""
    at = _chart(layout="Square")
    assert type(_frag_kids(at)[1]).__name__ == "UnknownElement"
    assert natal_wheel_envelope(_fragment(at))["width"] == "column"
    src = ui_source()
    assert "with st.container(width=PROSE_WIDTH):\n                picked = NATAL_WHEEL(" not in src
    assert '"width": "stretch" if _picked_wide else "column",' in src
    assert "PROSE_WIDTH = 680" in src
    assert "st.columns([1, 2, 1])" not in src


def test_the_wide_wheel_still_runs_the_full_width():
    at = _chart(layout="Wide")
    assert type(_frag_kids(at)[1]).__name__ == "UnknownElement"
    assert natal_wheel_envelope(_fragment(at))["width"] == "stretch"


# --- The controls, in one box --------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_controls_stand_in_one_box_above_the_wheel(layout):
    """Every control of the wheel's, in the box's order; the box first, and
    the picture after it."""
    at = _chart(layout=layout)
    box = _frag_kids(at)[0]
    assert box.proto.popover.label == "Options"
    assert [type(child).__name__ for child in box.children.values()][:2] == ["Radio", "Checkbox"]
    assert at.main.radio[0].label == "Wheel layout"
    assert [c.label for c in at.main.checkbox][0] == "Bounds ring"
    assert at.main.radio[1].label == "Wheel look"


def test_the_chart_pages_layout_radio_keeps_its_label_in_the_box():
    """In a row beside a checkbox the radio hid its label so as not to stand a
    tier above it. In the box it stands on its own line, as on Timing."""
    at = _chart(layout="Square")
    radio = at.main.radio[0]
    assert radio.label == "Wheel layout"
    assert radio.proto.label_visibility.value != radio.proto.label_visibility.COLLAPSED
    assert not radio.help, repr(radio.help)
    assert radio.options == ["Square", "Wide"]


def test_the_timing_pages_copy_of_the_radio_keeps_its_label():
    at = make_app(page="timing").run()
    assert_no_exception(at, "timing")
    wheel = [r for r in at.main.radio if r.label == "Wheel layout"]
    assert len(wheel) == 1
    assert wheel[0].proto.label_visibility.value != wheel[0].proto.label_visibility.COLLAPSED


def test_the_controls_are_drawn_before_the_wheel():
    """Each control's own return is its rerun's value, so nothing is read ahead of it."""
    src = ui_source()
    control = src.index('wheel_layout = _reading_radio("Wheel layout"')
    wheel = src.index('"svg": svg_wide if _picked_wide else svg_code,')
    assert control < wheel
    assert "wheel_layout = st.session_state.get(" not in src


# --- The four sentences, under the wheel ------------------------------

def _intro_block(at):
    """The four sentences' container: main's fifth child (after the header,
    the strip, the readings note's fixed slot and the wheel fragment), a
    _prose() container holding four markdown paragraphs."""
    block = _kids(at)[4]
    assert type(block).__name__ == "Block", type(block).__name__
    return block


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_four_sentences_follow_the_controls_in_order_at_reading_width(layout):
    at = _chart(layout=layout)
    kids = _kids(at)
    # kids[2] is the readings note's fixed slot (empty on the default chart);
    # the four sentences stand in one container after the
    # fragment, as body text.
    block = _intro_block(at)
    assert _kinds(block) == ["Markdown"] * 4
    assert [k.value for k in block.children.values()] == list(INTRO)
    assert block.proto.width_config.pixel_width == 680          # PROSE_WIDTH
    # And the Calculation section is what follows them, as before.
    assert kids[5].value == "Calculation"


def test_both_layouts_print_the_same_four_sentences_and_not_one_joined():
    """Wide used to join the three with hard breaks in a single caption."""
    square = [k.value for k in _intro_block(_chart(layout="Square")).children.values()]
    wide = [k.value for k in _intro_block(_chart(layout="Wide")).children.values()]
    assert square == wide == list(INTRO)
    assert '"  \\n".join(_intro)' not in ui_source()


def test_the_sentences_carry_their_italics_as_markdown_asterisks():
    text = INTRO[1]
    for title in ("*The Astrology of Sahl b. Bishr*", "*Persian Nativities* IV",
                  "*On the Revolutions of the Years of Nativities*",
                  "*Great Introduction*"):
        assert title in text


# --- The circumpolar warning ---------------------------------------------

def test_the_circumpolar_caption_is_absent_on_the_default_chart():
    at = _chart()
    assert not any("not a temporal hour" in c.value for c in at.main.caption)


def test_the_circumpolar_caption_stands_directly_under_the_controls_row():
    """A chart with no sunrise or sunset: the notice is the first thing
    under the controls, its notes expander next, then the four sentences.
    The notice keeps saying what is shown is an approximation and, no
    sunrise lying within a day behind the moment, that the day lord is the
    civil weekday's; the reason stands whole in the notes."""
    at = _chart(manual_lat_key=78.2, manual_lon_key=15.6)
    kids = _kids(at)
    assert type(kids[4]).__name__ == "Caption"
    assert kids[4].value == ("**The Lord of the Hour here is not a temporal hour.** What is shown is an explicitly modern "
                             "approximation: the civil day divided into 24 equal hours, continuing the Chaldean cycle. "
                             "The Lord of the Day is the civil weekday's lord, this app's stand-in, since no sunrise lies "
                             "within a day behind this moment, and \"the Sun is the planet by whose rising the day comes "
                             "to be\" (Gr. Intr. VI.33, 4).")
    assert kids[5].type == "expander" and kids[5].label == "Why the hour lord is approximate here"
    assert kids[5].icon == ":material/menu_book:"
    notes = [m.value for m in kids[5].markdown]
    # The reason is the engine's own sentence (one horizon): it names
    # which bounding sunrise or sunset is missing, so it is true on the edge
    # days of a polar night as well as inside one.
    assert notes == ["**No temporal hour exists at this moment at this location.**",
                     "The Sun is circumpolar here, with no sunrise or sunset within a day on either side of this "
                     "moment. The temporal hour is *defined* by the interval from a sunrise to the sunset that "
                     "follows it, or from a sunset to the sunrise that follows -- so it has no value at all, and no "
                     "source in hand contemplates the case."]
    assert type(kids[6]).__name__ == "Block"
    assert [k.value for k in kids[6].children.values()] == list(INTRO)
    assert kids[7].value == "Calculation"
