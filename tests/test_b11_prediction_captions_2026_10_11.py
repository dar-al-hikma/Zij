"""The opening captions of the Prediction pages say what each page applies
(ruling 146, B-11 of the third outside pass).

Revolutions, Days and months and Fardar and ages opened with one caption:
"Every rule on this page comes from Abu Ma'shar, *On the Revolutions of the
Years of Nativities* (*Persian Nativities* IV) ...". On Fardar and ages the
always-visible table of the lords of the sect light's triplicity is Sahl's
rule on Sahl's triplicity table, by its own Source and Triplicity-table
cells; on Revolutions the fixed stars are Sahl's list, the twelfth-parts and
the triplicity table the Great Introduction's, the reading checklist runs the
Configurations page's connection rule and reception (Sahl's, The Introduction
Ch. 3, by default), and the planets are directed by al-Qabisi's proportional
semi-arcs. README already says part of it: "Abu Ma'shar, *PN* IV, with the
releaser and house-master from Sahl".

The two pages now open with a frame caption -- PN IV, still "cited as
Book.chapter, sentence", the rule ruling 117 reads bare locators by -- and a
second caption naming the other sources the page applies (one caption would
pass the page's 400-character ceiling).

Ruling 147 (2) brings Days and months under the same form. Its "Also
direct, for the small days (IX.7, 31) and the mighty days (IX.7, 27), from"
selector offers every Lot of the Lots page (Hermes's, Valens's, Paul's,
Masha'allah's ...) and this app's Alchabitius house cusps, and directs the
one chosen, so the page opens with the frame caption and a second caption
naming those two. The selectors' options are now read as the cells are: an
option naming another source is that source applied, or a name to be sorted.
The owner then folded The releaser's caption into the same ruling: its
opening takes the frame form (Sahl's *On Nativities*), and a second caption
names what else it applies (the section at the end).

The blind check found two sources the first wording missed or misplaced, each
on a real chart: al-Andarzaghar's lords of the Ascendant (in al-Qabisi) at
the basic depth when "Also show the Ascendant's triplicity lords" is ticked
(florence, petoskey), and Sahl's connection rule in the checklist's "By
degree (12-13)" cells (petoskey). So the pages are rendered on four charts,
both depths, the box ticked and not, and the structural pins read every
column, heading and line through which a source is applied.

The pins:
- a caption claiming every rule is PN IV's stands only where nothing on the
  page applies another source;
- every applied source found is named in the second caption, and one applied
  at the basic depth is not named only as the supplement's;
- the captions word for word, Days and months' second caption among them;
- no Prediction page keeps "Every rule on this page comes from".

Every app run here uses its own XDG directory.
"""
import os
import re

import pytest

from conftest import assert_no_exception, make_app, table_nodes
from test_pwr2_page_book_names_2026_10_07 import CHARTS, TARGET

DEPTHS = ("Course text", "Course text and supplement")
RENDERED_CHARTS = ("florence", "florence_ladder", "petoskey", "arctic")
# The optional table of the Ascendant's triplicity lords, ticked on the two
# charts the blind check used.
TICKED_CHARTS = ("florence", "petoskey")
# Days and months directs a point chosen in its selector: a Lot of the Lots
# page and a house cusp, each on two charts (the option chosen by its opening
# words; a cusp's label carries its degree).
CHOSEN_CHARTS = ("florence", "petoskey")
CHOICES = ("Lot of siblings (Hermes)", "house 1 (")

PN4_ONLY = ("Every rule on this page comes from Abu Ma'shar, *On the Revolutions of the Years of Nativities* "
            "(*Persian Nativities* IV), cited as Book.chapter, sentence.")
FRAME = ("The frame of this page is Abu Ma'shar, *On the Revolutions of the Years of Nativities* "
         "(*Persian Nativities* IV), cited as Book.chapter, sentence.")
APPLIES = "This page also applies "
# A Prediction page's opening caption: the frame form, or the two it
# replaced (so a page put back as it was is still found, and fails the pins).
OPENING = re.compile(r"The frame of this page is|Every rule on this page comes from|They are taken from")
CAPTIONS = {
    "timing": (FRAME, APPLIES + (
        "Sahl's fixed stars (with Rhetorius's natures), his releaser and his year of the turning; the "
        "Configurations page's connection rule and reception; the Lots of the Lots page; al-Qabisi's "
        "proportional semi-arcs; and the *Great Introduction*'s twelfth-parts, triplicity lords, classes of "
        "signs and degrees, Mercury's phase, and the Moon's connections within her sign.")),
    "days": (FRAME, APPLIES + (
        "the Lots page's Lot of Fortune, and any other of its Lots or this app's Alchabitius house cusps chosen "
        "to be directed for the small and mighty days.")),
    "fardar": (FRAME, APPLIES + (
        "Sahl's lords of the sect light's triplicity, his releaser and his house-master's years; the *Great "
        "Introduction*'s planetary years and solar bands; al-Andarzaghar's triplicity lords (in al-Qabisi), the "
        "Ascendant's on request and the houses' with the supplement; and, with the supplement, Abu 'Ali's ladder "
        "where Sahl is silent.")),
}

# Any source other than PN IV (Dykes, PN IV's editor, is PN IV's).
OTHER = re.compile(r"\bSahl\b|On Nativities|The Introduction\b|[Aa]l-Qab[iī]s[iī]|[Aa]l-Andarzaghar|Gr\. ?Intr\.|"
                   r"Great Introduction|Rhetorius|Valens|Ptolemy|Abu 'Ali|\bJN\b|On Times|Masha'allah|\bITA\b|"
                   r"Carmen|Theophilus|'Umar|\bTBN\b|\bTet\.|Hermes|Dorotheus|Firmicus")
# The columns whose cells carry a rule's source or a value computed by one.
# (A Lot's name and notes, a planet's position, are not read: the Lots are
# found by the image table's Kind column.)
SCANNED = ("Source", "Triplicity table", "Reads", "By degree (12-13)", "Received by (14)", "Root condition",
           "Confirmed by the distribution", "Kind")
# A note inside a cell that reports another author's view beside the value
# applied: the arctic chart's star "Jupiter-Saturn (Sahl, following
# al-Andarzaghar, classifies it with Jupiter-Mars, fn 75)" applies
# Rhetorius's nature, not al-Andarzaghar's.
RELATED_NOTE = re.compile(r"\([^()]*\b(?:following|classifies)\b[^()]*\)")
# Related testimony named in a scanned cell: the applied source's own source
# (Sahl's 2.11 is Theophilus's, its fn 148 Carmen's), a witness beside Abu
# 'Ali ('Umar, TBN I.4.3), a column "for comparison" (On Times 4, 7).
RELATED = re.compile(r"Theophilus|Carmen|'Umar|\bTBN\b|On Times")

# Each applied source: where the page shows it is applied -- a scanned cell,
# a column heading, or a line of the page's text -- and the words naming it
# in the second caption.
APPLIED = (
    ("Sahl", "cell", r"\bSahl\b|On Nativities|The Introduction\b", "Sahl"),
    ("Sahl's lords of the sect light", "cell", r"Sahl, On Nativities 2\.11", "lords of the sect light's triplicity"),
    ("the releaser's distribution", "cell", r"the releaser's distribution", "releaser"),
    ("the connection rule", "cell", r"The Introduction Ch\. 3", "connection rule and reception"),
    ("the Great Introduction", "cell", r"Gr\. ?Intr\.|Great Introduction", "*Great Introduction*"),
    ("the twelfth-parts", "cell", r"Gr\. Intr\. V\.18", "twelfth-parts"),
    ("classes of signs and degrees", "cell", r"Gr\. Intr\. (?:VI\.4|V\.20)", "classes of signs and degrees"),
    ("the solar bands", "cell", r"heart through 16", "solar bands"),
    ("al-Qabisi", "cell", r"[Aa]l-Qab[iī]s[iī]|\bITA\b", "al-Qabisi"),
    ("al-Andarzaghar", "cell", r"[Aa]l-Andarzaghar", "al-Andarzaghar"),
    # The image table's Lot rows, and a Lot named by its author in a checklist cell.
    ("the Lots of the Lots page", "cell", r"^Lot$|\bLot of [^;|]*?\((?:Hermes|Hermetic|Valens|Masha'allah)\)",
     "Lots of the Lots page"),
    ("Rhetorius's natures", "column", r"Rhetorius", "Rhetorius"),
    ("Sahl's fixed stars", "column", r"Rhetorius", "Sahl's fixed stars"),
    ("the house-master's years", "column", r"On Nativities 1\.20 grants", "house-master's years"),
    ("Abu 'Ali's ladder", "column", r"Abu 'Ali|\bJN\b", "Abu 'Ali's ladder"),
    # A selector's options: Days and months offers every Lot of the Lots page
    # and the Alchabitius cusps to direct; the chosen one's lines say so.
    ("the Lots of the Lots page, offered", "option", r"^Lot of .*", "any other of its Lots"),
    ("the Alchabitius cusps, offered", "option", r"^house \d+ \(revolution cusp [^)]*\)",
     "this app's Alchabitius house cusps"),
    ("a Lot of the Lots page, directed", "text", r"^\*\*Small days from the revolution's Lot of ",
     "any other of its Lots"),
    ("an Alchabitius cusp, directed", "text", r"^\*\*Small days from the revolution's house \d",
     "this app's Alchabitius house cusps"),
    ("proportional semi-arcs", "column", r"^Semi-arc$", "al-Qabisi's proportional semi-arcs"),
    ("Sahl's releaser", "text", r"Sahl's chosen longevity releaser", "releaser"),
    ("Sahl's year of the turning", "text", r"Sahl, the year of the turning", "year of the turning"),
    ("the planetary years", "text", r"Gr\. Intr\. VII\.8, Figure 146", "*Great Introduction*'s planetary years"),
    ("Mercury's phase", "text", r"Mercury by his phase \(Gr\. Intr\. IV\.9, 8\)", "Mercury's phase"),
    ("the Moon's connections", "text", r"Gr\. Intr\. VII\.5, 14", "Moon's connections within her sign"),
)
_APPLIED = [(name, kind, re.compile(rx), phrase) for name, kind, rx, phrase in APPLIED]
# Applied on one page only, in a column no other page's pin reads that way:
# Days and months casts the month's indicators #3, #5 and #7 and method 8's
# start by the Lots page's Lot of Fortune on every chart (Revolutions names
# the Lots page whole).
PAGE_APPLIED = {"days": [("the Lots page's Lot of Fortune", re.compile(r"^(?:Indicator|Start): .*Lot of Fortune"),
                          "the Lots page's Lot of Fortune")]}


def runs_of(page):
    """(chart, depth, ticked, choice) for every render of the page."""
    out = [(chart, depth, False, None) for chart in RENDERED_CHARTS for depth in DEPTHS]
    if page == "fardar":
        out += [(chart, depth, True, None) for chart in TICKED_CHARTS for depth in DEPTHS]
    if page == "days":
        out += [(chart, depth, False, choice) for chart in CHOSEN_CHARTS for depth in DEPTHS for choice in CHOICES]
    return out


_RENDERED = {}


def _texts(node, out):
    kind = getattr(node, "type", None)
    if kind != "dataframe":
        for attr in ("value", "label", "body"):
            value = getattr(node, attr, None)
            if isinstance(value, str) and value.strip():
                out.append((kind, value))
                break
    for child in getattr(node, "children", {}).values():
        _texts(child, out)
    return out


def rendered(page, chart, depth, ticked, tmp_path_factory, choice=None):
    """{'opening', 'applies', 'texts', 'cells', 'columns', 'options'} for one render."""
    key = (page, chart, depth, ticked, choice)
    if key not in _RENDERED:
        from streamlit.util import calc_hash

        from engine import TIME_STANDARD_OPTIONS
        before = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp(f"xdg_{page}_{chart}"))
        try:
            standard, keys = CHARTS[chart]
            at = make_app(page=page)
            at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[standard]
            for name, value in keys.items():
                at.session_state[name] = value
            at.session_state["manual_coords_key"] = True
            at.session_state["_reading_depth"] = depth
            at.session_state["_target_mode"] = "Date"
            at.session_state["_target_date"] = TARGET
            at._page_hash = calc_hash(page)
            at.run(timeout=300)
            if ticked:
                at.checkbox(key="life_lords_ascendant").check().run(timeout=300)
            if choice:
                box = next(b for b in at.main.selectbox if b.key == "pn4_day_point")
                chosen = [o for o in box.options if o.startswith(choice)]
                assert len(chosen) == 1, f"premise: one option opens {choice!r}: {chosen}"
                box.set_value(chosen[0]).run(timeout=300)
        finally:
            if before is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = before
        assert_no_exception(at, f"{page}, {chart}, {depth}, ticked={ticked}, choice={choice}")
        captions = [c.value for c in at.main.caption]
        opening = [c for c in captions if OPENING.match(c)]
        applies = [c for c in captions if c.startswith(APPLIES)]
        assert len(opening) == 1, f"premise: one opening caption on {page}: {opening}"
        assert len(applies) <= 1, f"premise: at most one second caption on {page}: {applies}"
        cells, columns, all_cells = [], set(), []
        for _heading, node in table_nodes(at):
            frame = node.value
            for column in frame.columns:
                columns.add(str(column))
                all_cells += [(str(column), str(value)) for value in frame[column]]
                named = bool(OTHER.search(str(column)))
                if column in SCANNED or named:
                    for value in frame[column]:
                        text = RELATED_NOTE.sub("", str(value)).strip()
                        if text and text != "-":
                            cells.append((str(column), f"{column}: {text}" if named else text))
        texts = [text for kind, text in _texts(at.main, []) if text not in opening + applies]
        options = [str(option) for box in at.main.selectbox for option in box.options]
        # The captions in the order the page draws them, for the order pin.
        caption_order = [text for kind, text in _texts(at.main, []) if kind == "caption"]
        try:
            markdown = at.session_state["_analysis_markdown"]
        except KeyError:
            markdown = None
        _RENDERED[key] = {"opening": opening[0], "applies": applies[0] if applies else None,
                          "texts": texts, "cells": cells, "columns": columns, "options": options,
                          "all_cells": all_cells, "page": page, "caption_order": caption_order,
                          "markdown": markdown}
    return _RENDERED[key]


def applied_sources(render):
    """{name: words the caption must carry} for every applied source the render shows."""
    found = {}
    for name, kind, rx, phrase in _APPLIED:
        where = ([text for _c, text in render["cells"]] if kind == "cell" else
                 render["columns"] if kind == "column" else
                 render["options"] if kind == "option" else render["texts"])
        if any(rx.search(text) for text in where):
            found[name] = phrase
    for name, rx, phrase in PAGE_APPLIED.get(render["page"], []):
        if any(rx.search(f"{column}: {text}") for column, text in render["all_cells"]):
            found[name] = phrase
    return found


def stray_names(render):
    """Every other-source name in a scanned cell or a selector's option that
    no applied source covers and that is not related testimony: a new source
    to be sorted."""
    names = set()
    for text in [text for _c, text in render["cells"]] + render["options"]:
        for _n, _kind, rx, _p in _APPLIED:
            text = rx.sub(" ", text)
        names.update(m.group(0) for m in OTHER.finditer(text) if not RELATED.search(m.group(0)))
    return sorted(names)


def basic_clauses(applies):
    """The second caption's clauses that are not the supplement's alone."""
    clauses = applies[len(APPLIES):].split(";")
    return [c for c in clauses if not re.match(r"\s*(?:and,?\s*)?(?:with the supplement|the supplement adds)", c)]


ALL_RUNS = [(page, *run) for page in ("timing", "days", "fardar") for run in runs_of(page)]
# What each page applies at the least: Days and months the Lots and the cusps
# its selector offers.
AT_LEAST = {"timing": 3, "days": 2, "fardar": 3}


@pytest.mark.parametrize("page, chart, depth, ticked, choice", ALL_RUNS)
def test_a_pn_iv_only_caption_stands_only_where_nothing_on_the_page_applies_another_source(
        page, chart, depth, ticked, choice, tmp_path_factory):
    render = rendered(page, chart, depth, ticked, tmp_path_factory, choice)
    assert render["cells"], f"premise: {page} has Source cells"
    others = sorted(applied_sources(render)) + stray_names(render)
    claims = render["opening"].startswith("Every rule on this page comes from")
    assert not (claims and others), f"{page} ({chart}, {depth}) claims every rule is PN IV's, but applies {others}"


@pytest.mark.parametrize("page, chart, depth, ticked, choice", ALL_RUNS)
def test_every_applied_source_is_named_in_the_second_caption(page, chart, depth, ticked, choice, tmp_path_factory):
    render = rendered(page, chart, depth, ticked, tmp_path_factory, choice)
    found = applied_sources(render)
    assert len(found) >= AT_LEAST[page], f"premise: {page} applies sources besides PN IV: {found}"
    applies = render["applies"]
    assert applies is not None, f"{page} ({chart}, {depth}) names none of {sorted(found)}"
    unnamed = sorted(name for name, phrase in found.items() if phrase not in applies)
    assert not unnamed, f"{page} ({chart}, {depth}, ticked={ticked}) applies {unnamed}, unnamed in: {applies}"
    stray = stray_names(render)
    assert not stray, f"{page}'s cells name {stray}: applied (name it in the caption) or related testimony?"


@pytest.mark.parametrize("page, chart, depth, ticked, choice", [r for r in ALL_RUNS if r[2] == DEPTHS[0]])
def test_a_source_applied_without_the_supplement_is_not_named_as_the_supplements(
        page, chart, depth, ticked, choice, tmp_path_factory):
    render = rendered(page, chart, depth, ticked, tmp_path_factory, choice)
    found = applied_sources(render)
    assert len(found) >= AT_LEAST[page], f"premise: {page} applies sources besides PN IV: {found}"
    applies = render["applies"]
    assert applies is not None, f"{page} ({chart}, {depth}) names none of {sorted(found)}"
    basic = basic_clauses(applies)
    assert len(basic) >= 1, "premise: the caption has clauses outside the supplement's"
    only_supplement = sorted(name for name, phrase in found.items() if not any(phrase in c for c in basic))
    assert not only_supplement, (f"{page} ({chart}, Course text, ticked={ticked}) applies {only_supplement} "
                                 f"without the supplement, but the caption names them only as the supplement's")


# The blind check's two breaks, each on the chart it was found on: the
# structural pin above must see the source there, or it guards nothing.
CHECKED = [
    ("fardar", "florence", DEPTHS[0], True, "al-Andarzaghar"),
    ("fardar", "petoskey", DEPTHS[0], True, "al-Andarzaghar"),
    ("timing", "petoskey", DEPTHS[0], False, "the connection rule"),
    ("timing", "petoskey", DEPTHS[1], False, "the connection rule"),
]


@pytest.mark.parametrize("page, chart, depth, ticked, source", CHECKED)
def test_the_blind_checks_sources_are_found_on_their_charts(page, chart, depth, ticked, source, tmp_path_factory):
    render = rendered(page, chart, depth, ticked, tmp_path_factory)
    assert source in applied_sources(render), f"{source} not found on {page} ({chart}, {depth}, ticked={ticked})"


def test_the_ascendants_lords_are_al_andarzaghars_only_when_the_box_is_ticked(tmp_path_factory):
    """The basic depth shows al-Andarzaghar through the ticked box alone; so
    the ticked renders above are what hold the caption to it."""
    plain = rendered("fardar", "florence", DEPTHS[0], False, tmp_path_factory)
    ticked = rendered("fardar", "florence", DEPTHS[0], True, tmp_path_factory)
    assert "al-Andarzaghar" not in applied_sources(plain)
    assert "al-Andarzaghar" in applied_sources(ticked)


@pytest.mark.parametrize("page, chart, depth, ticked, choice", ALL_RUNS)
def test_each_opening_caption_word_for_word(page, chart, depth, ticked, choice, tmp_path_factory):
    render = rendered(page, chart, depth, ticked, tmp_path_factory, choice)
    assert (render["opening"], render["applies"]) == CAPTIONS[page]


# --- Ruling 147 (2): Days and months, and the Sources and readings page ------

@pytest.mark.parametrize("chart, depth, choice", [(c, d, x) for c in CHOSEN_CHARTS for d in DEPTHS for x in CHOICES])
def test_days_and_months_directs_the_point_chosen_and_the_pin_sees_it(chart, depth, choice, tmp_path_factory):
    """A Lot or a cusp chosen is directed: its own lines print, and the
    structural pins above find it applied (not only offered)."""
    render = rendered("days", chart, depth, False, tmp_path_factory, choice)
    directed = "a Lot of the Lots page, directed" if choice.startswith("Lot") else "an Alchabitius cusp, directed"
    assert directed in applied_sources(render), f"{choice!r} chosen on {chart} ({depth}), not found directed"
    plain = rendered("days", chart, depth, False, tmp_path_factory)
    assert directed not in applied_sources(plain), "premise: the default directs the Ascendant alone"


@pytest.mark.parametrize("depth", DEPTHS)
def test_days_and_months_offers_every_lot_of_the_lots_page_and_twelve_cusps(depth, tmp_path_factory):
    """The second caption says "the Lots of the Lots page": the selector
    offers every one of them the depth shows, not a few, and the twelve
    cusps."""
    from engine import operative_lot_definitions
    render = rendered("days", "florence", depth, False, tmp_path_factory)
    supplement = depth == DEPTHS[1]
    lots = [d["name"] for d in operative_lot_definitions() if supplement or not d.get("supplement")]
    offered = [o for o in render["options"] if o.startswith("Lot of")]
    assert len(lots) >= 30, f"premise: the Lots page's Lots: {len(lots)}"
    assert offered == lots
    named = [o for o in offered if re.search(r"Hermes|Hermetic|Valens|Masha'allah|Paul|Abu Ma'shar", o)]
    assert len(named) >= 5, f"premise: the options name their authors: {named}"
    assert len([o for o in render["options"] if o.startswith("house ")]) == 12


def test_no_prediction_page_says_every_rule_comes_from_one_book(tmp_path_factory):
    runs = [(page, *run) for page in ("timing", "days", "fardar") for run in runs_of(page)]
    assert len(runs) >= 24, "premise: every render of the three pages"
    texts = []
    for page, chart, depth, ticked, choice in runs:
        render = rendered(page, chart, depth, ticked, tmp_path_factory, choice)
        texts += [render["opening"], *render["texts"]]
    for chart in RENDERED_CHARTS:
        for depth in DEPTHS:
            render = rendered("releaser", chart, depth, False, tmp_path_factory)
            texts += [render["opening"], *render["texts"]]
    assert len(texts) > len(runs) * 10, "premise: the pages render their text"
    # The releaser's old opening: "They" with no antecedent, "neither book"
    # naming one book.
    claims = [t for t in texts if re.search(r"Every rule on this page comes from|They are taken from|neither book", t)]
    assert claims == []


SOURCES_SENTENCE = ("On the Prediction pages other than The releaser, whose frame is PN IV, its locators are bare "
                    "Book.chapter, sentence; on The releaser, whose frame is Sahl's *On Nativities*, its locators are "
                    "bare chapter, sentence. Any other work cited there is named.")


def _render_page(page, tmp_path_factory):
    from streamlit.util import calc_hash
    before = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp(f"xdg_{page}"))
    try:
        at = make_app(page=page)
        at._page_hash = calc_hash(page)
        at.run(timeout=300)
    finally:
        if before is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = before
    assert_no_exception(at, page)
    return at


def test_the_sources_page_says_which_work_frames_each_prediction_page(tmp_path_factory):
    at = _render_page("sources", tmp_path_factory)
    texts = [text for _kind, text in _texts(at.main, [])]
    key = [t for t in texts if t.startswith("Both of Abu Ma'shar's volumes have a Book VII")]
    assert len(key) == 1, f"premise: the citation key's closing paragraph: {key}"
    assert key[0] == ("Both of Abu Ma'shar's volumes have a Book VII, which is why his name alone no longer locates "
                      "anything. " + SOURCES_SENTENCE)
    assert not [t for t in texts if "rules come from" in t]


# --- The releaser's captions (the owner, folded into ruling 147 (2)) ---------
#
# The releaser opened "They are taken from Sahl, *On Nativities* (...). What
# neither book settles is listed at the foot of the Fardar and ages page
# rather than filled in." -- "They" with no antecedent, "neither book" naming
# one. It now takes the other Prediction pages' form: Sahl's *On Nativities*
# the frame, in the locator form the Sources and readings page states for it,
# and the pointer to the Fardar and ages page worded to what that page's list
# holds; then a second caption naming what else the page applies.

RELEASER_FRAME = ("The frame of this page is Sahl, *On Nativities*, cited as chapter, sentence. What *Persian "
                  "Nativities* IV leaves open here (the choice of releaser and house-master, the house-master's "
                  "years, and how the releaser is directed) is listed at the foot of the Fardar and ages page.")
RELEASER_APPLIES = APPLIES + (
    "PN IV's testimony #3 and turning of the house-master; al-Qabisi's proportional semi-arcs; Sahl's "
    "*Introduction*'s praised places and heart; the *Great Introduction*'s solar bands; Alchabitius divisions; "
    "Valens's fullness degree (in al-Qabisi); and, with the supplement, Abu 'Ali's ladder where Sahl is silent "
    "and, for display, his and 'Umar's additions and subtractions.")

# Each source the page applies besides *On Nativities*: where the page shows
# it producing what it prints, the words naming it in the second caption, and
# whether it is the supplement's alone. (Masha'allah, Nawbakht and
# al-Andarzaghar are reported inside *On Nativities* and are its frame;
# 'Umar, Abu Bakr, On Times, al-Qabisi's own procedure and Ptolemy's opinion
# stand beside the values as witnesses or comparisons, not applied.)
RELEASER_APPLIED = (
    ("PN IV's testimony #3", "text", r"direction method of PN IV III\.1, 12", "PN IV's testimony #3", False),
    ("PN IV's turning", "cell", r"^PN IV IX\.8, 30$", "turning of the house-master", False),
    ("proportional semi-arcs", "text", r"\bby proportional semi-arcs\b", "al-Qabisi's proportional semi-arcs",
     False),
    ("the praised places", "text", r"Sahl's seven praised places \(Introduction 2, 37-44",
     "Sahl's *Introduction*'s praised places", False),
    ("the heart", "text", r"the heart it leaves out is Sahl's one degree \(The Introduction Ch\. 3",
     "praised places and heart", False),
    ("the burned band", "text", r"its widths are Gr\. Intr\. VII\.2's", "the *Great Introduction*'s solar bands",
     False),
    ("Alchabitius divisions", "column", r"^House \(division", "Alchabitius divisions", False),
    ("Valens's fullness degree", "text", r"The Moon default is Valens's", "Valens's fullness degree (in al-Qabisi)",
     False),
    ("Abu 'Ali's ladder", "text", r"the supplement's ladder", "Abu 'Ali's ladder where Sahl is silent", True),
    ("Abu 'Ali's additions", "text", r"^Additions and subtractions to the house-master's years \(Abu 'Ali\)$",
     "his and 'Umar's additions and subtractions", True),
    # The Sun's row of that table: its Reading is computed by 'Umar's solar
    # rule ("'Umar: adds 19 years (sextile)"), not set beside it as a witness.
    ("'Umar's solar rule", "reading", r"^'Umar: (?:adds|subtracts) ", "his and 'Umar's additions and subtractions",
     True),
)
# A work a releaser table cell names that is the frame's, or testimony.
RELEASER_FRAME_NAMES = re.compile(r"\bSahl\b|On Nativities")
# How a cell names an applied work, and how the second caption names it.
CAPTION_NAME = {"Gr. Intr.": "Great Introduction", "GrIntr.": "Great Introduction", "JN": "Abu 'Ali",
                "The Introduction": "Introduction", "Al-Qabisi": "al-Qabisi", "al-Qabīsī": "al-Qabisi"}
RELEASER_RUNS = [(chart, depth) for chart in RENDERED_CHARTS for depth in DEPTHS]


def releaser_applied(render):
    """{name: (phrase, supplement only)} for every source above the render shows."""
    found = {}
    for name, kind, rx, phrase, supplement in RELEASER_APPLIED:
        where = ([text for _c, text in render["cells"]] if kind == "cell" else
                 [text for column, text in render["all_cells"] if column == "Reading"] if kind == "reading" else
                 render["columns"] if kind == "column" else render["texts"])
        if any(re.search(rx, text) for text in where):
            found[name] = (phrase, supplement)
    return found


@pytest.mark.parametrize("chart, depth", RELEASER_RUNS)
def test_the_releasers_captions_word_for_word(chart, depth, tmp_path_factory):
    render = rendered("releaser", chart, depth, False, tmp_path_factory)
    assert (render["opening"], render["applies"]) == (RELEASER_FRAME, RELEASER_APPLIES)


@pytest.mark.parametrize("chart, depth", RELEASER_RUNS)
def test_every_source_the_releaser_applies_is_named_in_its_second_caption(chart, depth, tmp_path_factory):
    render = rendered("releaser", chart, depth, False, tmp_path_factory)
    found = releaser_applied(render)
    assert len(found) >= 7, f"premise: The releaser applies sources besides On Nativities: {sorted(found)}"
    applies = render["applies"]
    assert applies is not None, f"The releaser ({chart}, {depth}) names none of {sorted(found)}"
    unnamed = sorted(name for name, (phrase, _s) in found.items() if phrase not in applies)
    assert not unnamed, f"The releaser applies {unnamed} ({chart}, {depth}); its second caption does not name them"
    basic = " ".join(basic_clauses(applies))
    for name, (phrase, supplement) in found.items():
        assert supplement or phrase in basic, (
            f"{name} is applied at {depth} ({chart}), but the caption names it only as the supplement's")


@pytest.mark.parametrize("chart, depth", RELEASER_RUNS)
def test_every_author_a_releaser_cell_names_is_the_frame_testimony_or_named(chart, depth, tmp_path_factory):
    """A new author in a cell is a source to be sorted: the frame's, related
    testimony, or applied and named in the second caption."""
    render = rendered("releaser", chart, depth, False, tmp_path_factory)
    assert len(render["all_cells"]) > 100, "premise: The releaser's tables"
    applies = render["applies"] or ""
    # Testimony stands in the Witnesses column; a Reading cell is a verdict
    # computed on the chart, so a witness's name there is that witness applied.
    stray = sorted({m.group(0) for column, text in render["all_cells"] for m in OTHER.finditer(text)
                    if not RELEASER_FRAME_NAMES.fullmatch(m.group(0))
                    and not (RELATED.search(m.group(0)) and column != "Reading")
                    and CAPTION_NAME.get(m.group(0), m.group(0)) not in applies})
    assert not stray, f"The releaser's cells name {stray} ({chart}, {depth}): applied (name it) or testimony?"


def test_each_source_the_releaser_caption_names_is_found_on_a_render(tmp_path_factory):
    """None of the structural finds above is dead: each is seen on one of the
    renders, and Abu 'Ali's only with the supplement."""
    seen = {}
    for chart, depth in RELEASER_RUNS:
        for name in releaser_applied(rendered("releaser", chart, depth, False, tmp_path_factory)):
            seen.setdefault(name, set()).add(depth)
    assert sorted(seen) == sorted(name for name, *_r in RELEASER_APPLIED)
    for name, *_r, supplement in RELEASER_APPLIED:
        assert (seen[name] == {DEPTHS[1]}) == supplement, f"{name}: seen at {sorted(seen[name])}"


def test_the_releasers_pointer_names_what_the_fardar_pages_list_holds(tmp_path_factory):
    """"What PN IV leaves open here ... is listed at the foot of the Fardar
    and ages page": that page's last list is PN IV's, and holds the three
    rows the caption names."""
    render = rendered("fardar", "florence", DEPTHS[0], False, tmp_path_factory)
    texts = render["texts"]
    assert "What Persian Nativities IV does not settle" in texts
    table = [t for t in texts if t.startswith("| Topic | State |")]
    assert len(table) == 1, "premise: the list's table"
    rows = [row.split("|")[1].strip() for row in table[0].splitlines()[2:]]
    for row in ("The releaser and the house-master", "Where the greater years are granted",
                "Directing anything that is not the Ascendant or the meridian"):
        assert row in rows, f"{row!r} is not in the list: {rows}"
    assert texts.index("What Persian Nativities IV does not settle") > len(texts) // 2, "premise: at the foot"


# --- The check's fixes (the owner) --------------------------------------------

ORDER_RUNS = [(page, chart, depth) for page in ("timing", "days", "fardar", "releaser")
              for chart in RENDERED_CHARTS for depth in DEPTHS]


@pytest.mark.parametrize("page, chart, depth", ORDER_RUNS)
def test_the_frame_the_sources_line_and_the_second_caption_stand_in_that_order(page, chart, depth,
                                                                              tmp_path_factory):
    """The frame caption, then the "Sources shown" line, then the second
    caption, with nothing between."""
    render = rendered(page, chart, depth, False, tmp_path_factory)
    order = render["caption_order"]
    assert render["applies"] is not None, f"premise: {page} has a second caption"
    at = order.index(render["opening"])
    assert order[at + 1].startswith("Sources shown:"), f"{page}: {order[at:at + 3]}"
    assert order[at + 2] == render["applies"], f"{page}: {order[at:at + 3]}"


def test_days_and_months_casts_the_lots_pages_lot_of_fortune_unchosen(tmp_path_factory):
    """The Lot of Fortune is applied with nothing chosen in the selector: the
    month's indicators and method 8 are cast by it on every chart."""
    for chart in RENDERED_CHARTS:
        render = rendered("days", chart, DEPTHS[0], False, tmp_path_factory)
        assert "the Lots page's Lot of Fortune" in applied_sources(render), chart
        assert "Lot of Fortune" in render["applies"]


@pytest.mark.parametrize("chart, depth", RELEASER_RUNS)
def test_umars_solar_reading_is_shown_only_with_the_supplement(chart, depth, tmp_path_factory):
    render = rendered("releaser", chart, depth, False, tmp_path_factory)
    umar = [text for column, text in render["all_cells"] if column == "Reading" and text.startswith("'Umar:")]
    assert bool(umar) == (depth == DEPTHS[1]), f"{chart}, {depth}: {umar}"


# The father's Lot on The releaser: the second point directed (4.20, 32) is
# the Sun by day and Saturn by night; a planet's name stands bare.
FATHER = {"petoskey": "Saturn", "florence": "the Sun"}


@pytest.mark.parametrize("chart", list(FATHER))
def test_the_fathers_second_point_is_named_with_its_own_article(chart, tmp_path_factory):
    render = rendered("releaser", chart, DEPTHS[0], False, tmp_path_factory)
    point = FATHER[chart]
    line = [t for t in render["texts"] if t.startswith("The Lot of the father stands at")]
    assert len(line) == 1, "premise: the father's Lot line"
    assert f"; the second point directed is **{point}** (32). fn 288" in line[0]
    assert f"*From {point} (32), to the same*" in render["texts"]
    assert render["markdown"] is not None and f"From {point} (32), to the same" in render["markdown"]
    texts = " ".join(render["texts"]) + render["markdown"]
    assert not re.search(r"\bthe (?:\*\*)?(?:Saturn|Jupiter|Mars|Venus|Mercury)\b(?:\*\*)? \(32\)", texts)
