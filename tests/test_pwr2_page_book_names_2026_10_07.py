"""Lane PWR2 of the re-pass's wave 5 (2026-10-07): the book named where a
locator is printed on a page -- its prose, its help and its labels.

The owner's ruling 86: where the caption or the sentence already names the
work, a bare locator stays (the house form); elsewhere the work is named.
Ruling 117 reads "the caption" to include a page's opening caption: where a
page opens by naming the one book its rules come from (the three Prediction
pages, PN IV; The releaser, Sahl's On Nativities), that book's locators on
the page keep the bare house form; a citation on such a page that is not that
book's is cited with its title; on a page whose opening names no book, every
bare locator names its work.

Lane PWR pinned the export (R01) with a sentence rule; this file reads the
page with the same rule (``test_pwr_book_names_2026_10_07``), and adds the
page's own structure -- a Markdown table's cell, a list item or a paragraph
ends a sentence -- and the opening caption. Tables (their cells and columns),
pictures and the wheel are the export's pin's, not this one's.

Each class was a strict xfail on b5e0e9d before its fix; the plan is the
corpus's ``process/hostile_pass_2026-10-03/repass/WAVE5_LANES.md`` (PWR2).
"""
from __future__ import annotations

import re
from datetime import time
from pathlib import Path

import pytest

from conftest import SWITCHES, apply_switches, assert_no_exception, make_app
from test_pwr_book_names_2026_10_07 import LOC as _EXPORT_LOC
from test_pwr_book_names_2026_10_07 import WORK as _EXPORT_WORK
from test_pwr_book_names_2026_10_07 import _ABBREV, _END, _FORMS, _open_part

# The export pin's works, with names the page uses that the export did not:
# Abu Bakr's *On Nativities* is another book than Sahl's of the same title,
# cited by a roman book and chapter ("Abu Bakr, On Nativities II.7.3"), so
# the pair is one work and "On Nativities" inside it is not Sahl's; "*Tet.*",
# the translator's abbreviation of the Tetrabiblos, as PN IV's fn 47 cites
# it ("Cf. the classic account in *Tet.* IV.10"); "BW", ITA's abbreviation
# of ibn Ezra's *Beginning of Wisdom* ("[BW VIII.76]", ITA IV.4.2); and two
# titles written out, Abu Ma'shar's *Abbreviation* and Dykes's
# *Introductions to Traditional Astrology* (ITA). Abu 'Ali al-Khayyat, the
# author of one work in this corpus (*Judgments of Nativities*, JN), names it
# where he is written at its chapter ("The principal rows state Abu 'Ali,
# Ch. 4.", ruling 129); his name and the title written out are one naming
# ("Abu 'Ali al-Khayyat, Judgments of Nativities Ch. 4", the Sources key's
# form). "ITA Introduction" is ITA's own introduction, not Sahl's.
_ABU_ALI = (r"Abu 'Ali(?: al-Khayyat)?,? \*?Judgments of Nativities\*?|"
            r"Abu 'Ali(?: al-Khayyat)?(?=,? ?(?:JN\b|Ch\.)|,? ?$)")
WORK = re.compile(_ABU_ALI + r"|\bITA Introduction\b|Abu Bakr,? (?:\*?On Nativities\*?)?|\bTet\.|\bBW\b|"
                  r"\bAbbreviation\b|Introductions to Traditional Astrology|" + _EXPORT_WORK.pattern)
# The forms each work's citations take (the export pin's), with those works'
# roman books and chapters, and Abu 'Ali's chapters.
FORMS = (_FORMS[0], (_FORMS[1][0], re.compile(_FORMS[1][1].pattern + r"|\bTet\.|\bBW\b|\bAbbreviation\b|"
                                                r"Introductions to Traditional Astrology")),
         (_FORMS[2][0], re.compile(_FORMS[2][1].pattern + r"|Abu 'Ali")))
_NAMED_RIGHT_AFTER = re.compile(r"\s*(?:\(\s*|,\s+)(?:in\s+)?(?:" + WORK.pattern + ")")

# The export pin's locator grammar, with one guard the page needs: a place's
# coordinates in the chart strip ("43.78, 11.25") are not a decimal chapter
# and sentence -- a locator is not followed by a digit or a decimal point
# and a digit.
LOC = re.compile(_EXPORT_LOC.pattern + r"(?!\d)(?!\.\d)")

# A chapter cited with no sentence: Sahl's dotted chapter ("1.20 is silent",
# "Sahl's 1.29", "1.8's", "10.2.7"), or a "Ch. N" ("Ch. 57's sentences",
# "Abu 'Ali, Ch. 4."). A number is not one: a decimal of a unit ("2.5
# degrees", "12.0°", "on day 2.31", "day 1.96" -- On Nativities has no
# chapter past 45 in a book), a longer number ("365.24"), a coordinate
# ("43.78, 11.25"), or the
# Book of Aristotle's item in brackets after its roman locator ("BA III.2.1
# [1.7]", "III.2.5 [5.1]-[5.5]"; see locators).
CHAPTER = re.compile(
    r"(?<![\w.,/°'′\-])(?:1[0-2]|[1-9])\.(?:[1-3]\d|4[0-5]|[1-9])(?:\.[1-9]\d?)?"
    r"(?!\d|\.\d|\s*,\s*\d|\s*(?:°|′|'(?!s\b)|%|degrees?\b|days?\b|d\b|h\b|hours?\b|years?\b|minutes?\b|x\b))"
    r"|(?<![\w.])Ch\.\s*\d{1,2}(?!\d|\.\d|\s*,\s*\d)")
_COORDINATE_BEFORE = re.compile(r"\d\.\d+,\s*$")
_UNIT_BEFORE = re.compile(r"\bdays?\s+$")
_ITEM_BEFORE = re.compile(r"[IVX]+\.\d+(?:\.\d+)*\s*(?:\[\d+\.\d+\]\s*[-–]\s*)?\[$")


def locators(text):
    """Every locator `text` prints, in order: the export pin's grammar, and a
    chapter cited alone where that grammar reads none."""
    found = list(LOC.finditer(text))
    spans = [(m.start(), m.end()) for m in found]
    for m in CHAPTER.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in spans):
            continue
        if _COORDINATE_BEFORE.search(text[max(0, m.start() - 16):m.start()]):
            continue
        if _ITEM_BEFORE.search(text[max(0, m.start() - 24):m.start()]):
            continue
        if _UNIT_BEFORE.search(text[max(0, m.start() - 8):m.start()]):
            continue
        found.append(m)
    return sorted(found, key=lambda m: m.start())

# The page's own sentence ends, besides a full stop: a Markdown table's cell
# ("| ... |"), a list item, a heading, a quotation's line or a paragraph. A
# reader takes each cell and each item as a unit of its own.
_BREAK = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*+] |\d+\. |#|>|\|))|\|")


# The export pin's abbreviations, with "Tet." (the Tetrabiblos) and "Chs."
# ("Rhetorius Chs. 23-25 (...) and Ch. 53").
ABBREV = _ABBREV | {"tet", "chs"}


def sentence_start(text, at):
    """Where the sentence holding offset `at` begins: after the last full
    stop (not an abbreviation's, not a roman numeral's) before it, or the
    last break of the page's own structure, whichever is later."""
    start = 0
    for m in _END.finditer(text[:at + 2]):
        if m.end() > at:
            break
        tok = m.group(1).lstrip("(\"'“*_[").lower()
        if m.group(2) == "." and (tok in ABBREV or re.fullmatch(r"[ivxlc]+|[a-z]", tok)):
            continue
        start = m.end()
    for m in _BREAK.finditer(text, start, at):
        start = m.end()
    return start


# A quotation is the book's own words (a sentence, or the translator's
# note: "as in Carmen I.12, and in Ch. 1.30, 28 below"): a locator inside one
# is printed as the page quotes it, and the house form does not reach it.
_QUOTED = re.compile(r'"[^"\n]*(?:\n(?!\s*\n)[^"\n]*)*"|“[^”]*”')


def quoted(text, at):
    """Offset `at` stands inside a quotation (paired double quotes, within
    one paragraph)."""
    return any(q.start() < at < q.end() for q in _QUOTED.finditer(text))


_TABLE_ROW = re.compile(r"^[ \t]*\|.*\|[ \t]*$", re.M)


def column_head(text, at):
    """The head of the Markdown table column whose cell holds offset `at`
    ("| Passage of On Nativities | ... |" over "| 2.3, 8 | Not read |"), or ""
    where `at` stands in no table's body: a column that names its work
    covers its cells, as a column does in the export."""
    rows = list(_TABLE_ROW.finditer(text))
    for i, row in enumerate(rows):
        if not row.start() <= at < row.end():
            continue
        first = i                       # the table's first row: rows run on line by line
        while first and rows[first - 1].end() + 1 == rows[first].start():
            first -= 1
        if first == i or i == first + 1:
            return ""                   # the head itself, or its |---| line
        column = text[row.start():at].count("|") - 1
        heads = [c.strip() for c in rows[first].group(0).strip().strip("|").split("|")]
        return heads[column] if 0 <= column < len(heads) else ""
    return ""


def named_before(text, at):
    """A work is named earlier in the sentence that holds offset `at`,
    outside any parenthesis closed before it."""
    return WORK.search(_open_part(text, sentence_start(text, at), at)) is not None


_AT_THE_LOCATOR = re.compile(r"(?:'s)?[\s,*_]*")


def _takes(work, loc):
    """The work's citations take the locator's form (FORMS)."""
    return next(w for form, w in FORMS if form.match(loc)).search(work) is not None


def _at_a_locator(text, w):
    """The work `w` is named at a locator ("JN Ch. 3", "PN IV's IV.1, 2"),
    not only mentioned ("ITA Introduction §6", "PN IV does not")."""
    return any(l.start() >= w.end() and _AT_THE_LOCATOR.fullmatch(text, w.end(), l.start())
               for l in locators(text[:w.end() + 40]))


def aside_work(text, m):
    """Where no work is named earlier in the locator's sentence outside a
    closed parenthesis, the last one named at a locator inside one, whose
    citations take the locator's form: the sentence already names it (ruling
    129: "(JN Ch. 3), its count from Ch. 4's table"). A work of another form
    is not carried ("2.11, 1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39"), nor
    one only mentioned ("..., ITA Introduction §6); IX.2, 8-11")."""
    start = sentence_start(text, m.start())
    if WORK.search(_open_part(text, start, m.start())):
        return None
    for w in reversed(list(WORK.finditer(text, start, m.start()))):
        if _takes(w.group(0), m.group(0)) and _at_a_locator(text, w):
            return w.group(0)
    return None


def names_its_work(text, m):
    """The locator `m` names its work: earlier in its sentence, or at once
    after it ("al-Qabisi I.57b (ITA I.13)")."""
    return (named_before(text, m.start()) or _NAMED_RIGHT_AFTER.match(text, m.end()) is not None
            or aside_work(text, m) is not None)


def assigned_work(text, m, page_book=None, over=""):
    """The work a reader assigns to the locator `m`: the one named at once
    after it, else the last one named earlier in its sentence, else the one
    the label or heading it stands under names (`over`), else the page's
    opening caption's book; None where nothing names one."""
    after = _NAMED_RIGHT_AFTER.match(text, m.end())
    if after:
        return WORK.search(after.group(0)).group(0)
    before = list(WORK.finditer(_open_part(text, sentence_start(text, m.start()), m.start())))
    if before:
        return before[-1].group(0)
    aside = aside_work(text, m)
    if aside:
        return aside
    named = list(WORK.finditer(column_head(text, m.start()) + " " + over))
    if named:
        return named[-1].group(0)
    return page_book


def test_the_page_sentence_reader_reads_the_pages_structure():
    # a Markdown table's cell is a unit of its own
    text = "| Within one year | Sahl's On Nativities 1.24, 2 agrees | | Across years | (III.2, 2-3) |"
    assert named_before(text, text.index("1.24, 2"))
    assert not named_before(text, text.index("III.2, 2-3"))
    # so is a list item, and a paragraph
    text = "- Gr. Intr. VII.5, 24 holds it\n- VII.5, 121 says it"
    assert not named_before(text, text.index("VII.5, 121"))
    text = "Gr. Intr. VII.5, 24 holds it\n\nVII.5, 121 says it"
    assert not named_before(text, text.index("VII.5, 121"))
    # a line that runs on inside one paragraph does not end the sentence
    text = "Gr. Intr. VII.5, 24 holds it\nand VII.5, 121 says it"
    assert named_before(text, text.index("VII.5, 121"))
    # the export pin's rules hold: a full stop, an abbreviation, a closed aside
    assert not named_before("PN IV I.6, 3 writes it. I.6, 4 likewise", 25)
    assert named_before("Sahl, The Introduction Ch. 3, 91-100", 23)
    text = "2.11, 1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39"
    assert not named_before(text, text.index("2.13, 39"))
    # a work named at once after the locator names it, in a parenthesis or after a comma
    t = "al-Qabisi I.57b (ITA I.13) gives"
    assert names_its_work(t, LOC.search(t))
    assert assigned_work(t, LOC.search(t), "PN IV") == "ITA"
    t = "VII.5, 121, in Gr. Intr., gives"
    assert names_its_work(t, LOC.search(t))
    t = "the lords of I.57b (as the text has it) give"
    assert not names_its_work(t, LOC.search(t))
    # a work named in a parenthesis the sentence has closed names a later
    # locator of its form (ruling 129), and no other
    t = "the class Abu 'Ali's ladder gives the planet (JN Ch. 3), its count from Ch. 4's table"
    assert assigned_work(t, locators(t)[-1], "PN IV") == "JN"
    t = "2.11, 1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39"
    assert not names_its_work(t, LOC.search(t, t.index("2.13")))
    t = "IX.9, 11-13 are shown (12 allows it (PN IV VIII.1, 1-2); 13's half, ITA Introduction §6); IX.2, 8-11, the rest"
    assert assigned_work(t, LOC.search(t, t.index("IX.2")), "PN IV") == "PN IV"
    # Abu 'Ali at his chapter names JN; with the title written out, one naming
    t = "The principal rows state Abu 'Ali, Ch. 4. A fortune's square"
    assert names_its_work(t, locators(t)[0]) and _canon(assigned_work(t, locators(t)[0], "On Nativities")) == "JN"
    assert [w.group(0) for w in WORK.finditer("Abu 'Ali al-Khayyat, Judgments of Nativities Ch. 4")] == [
        "Abu 'Ali al-Khayyat, Judgments of Nativities"]
    assert [w.group(0) for w in WORK.finditer("Abu 'Ali's ladder (JN Ch. 3)")] == ["JN"]
    # redundant namings: a work named again in its sentence; an author and his title are one naming
    t = "the planet (JN Ch. 3), its count from JN Ch. 4's table"
    assert [(n[0], n[2]) for n in _redundant(t, None)] == [("Ch. 4", "sentence")]
    t = "The principal rows state Abu 'Ali, JN Ch. 4. Next"
    assert [(n[0], n[2]) for n in _redundant(t, None)] == [("Ch. 4", "sentence")]
    assert _redundant("Firmicus, Mathesis III.7 (Dykes), fn 194", None) == []
    assert _redundant("Valens, Anthologies II.36 (Riley)", None) == []
    assert _redundant("(ITA Introduction §6, quadrant divisions) -- the word (The Introduction Ch. 2, 31)", None) == []
    # a naming that also names the locator before it is not redundant
    assert _redundant("Al-Qabisi I.16c (ITA I.7) supplies the lords (al-Qabisi I.57b, ITA I.13)", None) == []
    # another work named between keeps the naming needed
    assert _redundant("Sahl's On Nativities 1.23, 2; Carmen I.28; On Nativities 1.23, 46", None) == []
    # the caption's book named on its own page
    t = "the years are granted from On Nativities 1.20, 7-34 read in full"
    assert [(n[0], n[2]) for n in _redundant(t, "On Nativities")] == [("1.20, 7-34", "caption book")]
    t = "Carmen's rule, and On Nativities 1.20, 10 says"
    assert _redundant(t, "On Nativities") == []
    # a Markdown table's column head that names a work covers the cells under it
    text = "| Passage of On Nativities | Extent |\n|---|---|\n| 2.3, 8 | Not read |\n| 2.16, 3 | read as 2.3, 7 |"
    assert column_head(text, text.index("2.3, 8")) == "Passage of On Nativities"
    assert column_head(text, text.index("2.3, 7")) == "Extent"
    assert column_head(text, text.index("Passage")) == ""
    assert assigned_work(text, LOC.search(text, text.index("2.16")), None) == "On Nativities"
    # a place's coordinates are not a locator
    assert not LOC.search("Unsaved chart · 1240-05-23 14:30:00 · 43.78, 11.25")
    assert not locators("Unsaved chart · 1240-05-23 14:30:00 · 43.78, 11.25")
    # a chapter cited alone is one; a decimal of a unit, or a long number, is not
    assert [m.group(0) for m in locators("Abu 'Ali's ladder, where 1.20 is silent; Sahl's 1.29 and 10.2.7")] == [
        "1.20", "1.29", "10.2.7"]
    assert [m.group(0) for m in locators("Dykes's notes to Ch. 57's sentences and JN Ch. 3")] == ["Ch. 57", "Ch. 3"]
    assert [m.group(0) for m in locators("1.8's three divisions. The rows state Abu 'Ali, Ch. 4. As 1.20.")] == [
        "1.8", "Ch. 4", "1.20"]
    assert not locators("within 2.5 degrees, 12.0° from exact, on day 1.96, 365.24 days, 12.175 d a degree")
    assert not locators("The revolution's Moon at 00° Lib 50' leaves Libra on day 2.31; before that")
    assert [m.group(0) for m in locators("BA III.2.1 [1.7]: the eleventh; BA III.2.5 [5.1]-[5.5]")] == [
        "III.2.1", "III.2.5"]
    text = "Rhetorius Chs. 23-25 (the doryphory; the out-of-sect kind) and Ch. 53 (what it gives)"
    assert named_before(text, text.index("Ch. 53"))
    assert [m.group(0) for m in locators("On Nativities 1.20, 7-34 and 1.23.12")] == ["1.20, 7-34", "1.23.12"]
    assert LOC.search("the lord of the year (II.1, 25); On Nativities 1.24, 2.")
    # the opening caption's book is the last resort
    text = "IX.8, 30's turning"
    assert assigned_work(text, LOC.search(text), "PN IV") == "PN IV"
    text = "Sahl's On Nativities 1.23, 2; IX.8, 123 defers the years"
    assert assigned_work(text, LOC.search(text, text.index("IX.8")), "PN IV") == "On Nativities"
    # a widget's help and options stand under its label, as a caption's table does
    text = "'hemisphere': the whole half, excluding the rays (VII.2, 2; VII.6, 34)"
    assert assigned_work(text, LOC.search(text), None, "Gr. Intr. VII.6, 27/45 eastern/western") == "Gr. Intr."
    assert assigned_work(text, LOC.search(text), "PN IV", "Fitting infortune") == "PN IV"


# --- The pages --------------------------------------------------------------------

# The four charts the instruments' page-text scan renders: each a
# time standard (an index into the sidebar's own options: LMT, the named
# zone, a manual offset) and its inputs, rendered at both reading depths
# with a fixed target date.
TARGET = "2026-10-03"
CHARTS = {
    # The Moon the house-master and no sentence of 1.20 reaching her: the
    # releaser page draws Abu 'Ali's ladder note (test_readability_c's
    # LADDER_CHART).
    "florence_ladder": (0, dict(date_input_key="1240-02-02", time_input_key=time(14, 30),
                                manual_lat_key=43.7792, manual_lon_key=11.2463)),
    "florence": (0, dict(date_input_key="1240-05-23", time_input_key=time(14, 30),
                         manual_lat_key=43.7792, manual_lon_key=11.2463)),
    "petoskey": (1, dict(date_input_key="1982-11-19", time_input_key=time(5, 18),
                         manual_lat_key=45.3733, manual_lon_key=-84.9553)),
    "arctic": (2, dict(date_input_key="2000-06-21", time_input_key=time(14, 30), utc_offset_key=2.0,
                       manual_lat_key=70.0, manual_lon_key=25.0)),
    "florence_undecided": (0, dict(date_input_key="1240-04-01", time_input_key=time(14, 30),
                                   manual_lat_key=43.7792, manual_lon_key=11.2463)),
}
DEPTHS = ("Course text", "Course text and supplement")
# Each reading switch at its alternative: some page text prints only then
# (the Sources page's "In force:" line under a flipped reading). Rendered for
# the first chart, at both depths.
FLIPPED = {name: alternatives[1] for name, (_store, alternatives, *_rest) in SWITCHES.items()}
PAGES = ("chart", "dignities", "findings", "configurations", "lots", "victors", "timing", "releaser", "days",
         "fardar", "reference", "sources")

# The pages whose opening caption names the one book their rules come from
# (ruling 117): the caption's opening words, the book as the pin's WORK reads
# it, and the form that book's locators take (PN IV a roman book and
# chapter, On Nativities a dotted chapter).
# B-11 (ruling 146): Revolutions and Fardar and ages apply other sources too,
# so their caption names PN IV as the frame and goes on to name the others;
# its opening sentence still says how PN IV is cited (the whole caption is
# pinned in test_b11_prediction_captions_2026_10_11.py). Ruling 147 (2):
# Days and months follows them; its "Every rule on this page comes from Abu
# Ma'shar" caption is gone.
PN4_FRAME_CAPTION = ("The frame of this page is Abu Ma'shar, *On the Revolutions of the Years of "
                     "Nativities* (*Persian Nativities* IV), cited as Book.chapter, sentence.")
CAPTIONED = {
    "timing": (PN4_FRAME_CAPTION, "PN IV", re.compile(r"[IVX]")),
    "days": (PN4_FRAME_CAPTION, "PN IV", re.compile(r"[IVX]")),
    "fardar": (PN4_FRAME_CAPTION, "PN IV", re.compile(r"[IVX]")),
    # Ruling 147 (2), with the owner's addition: The releaser opens with the
    # frame form too, "They are taken from Sahl ..." gone.
    "releaser": ("The frame of this page is Sahl, *On Nativities*, cited as chapter, sentence.", "On Nativities",
                 re.compile(r"\d")),
}
UNCAPTIONED = tuple(p for p in PAGES if p not in CAPTIONED)

# Not page prose: a table (its columns and cells: the export's pin), a
# picture, the wheel.
_NOT_PROSE = {"Dataframe", "Table", "Json", "Image", "UnknownElement", "PlotlyChart", "VegaLiteChart"}


def page_texts(at):
    """(kind, text, over) for every text the page's main area shows outside
    its tables and pictures, in the page's order: headers, Markdown,
    captions, alerts, a widget's label, help and options, an expander's or a
    tab's label. `over` is what the text stands under: a widget's label for
    its help and options, a heading for its help (ruling 86: "where the
    caption ... already names the work"), a finding's caption for its row
    picker's options; empty for the rest."""
    out = []
    # The caption a finding prints under its heading ("Sahl, On Nativities
    # 2.1-2.21"): the first caption after a subheader.
    finding = {"caption": "", "awaited": False}

    def walk(node):
        kind = type(node).__name__
        if kind in _NOT_PROSE:
            return
        proto = getattr(node, "proto", None)
        if proto is not None:
            head = ""
            for attr in ("body", "label"):
                value = getattr(proto, attr, None)
                if isinstance(value, str) and value:
                    out.append((f"{kind}.{attr}", value, ""))
                    head = head or value
            if kind == "Subheader":
                finding.update(caption="", awaited=True)
            elif kind == "Caption" and finding["awaited"]:
                finding.update(caption=head, awaited=False)
            for attr in ("help", "caption", "placeholder"):
                value = getattr(proto, attr, None)
                if isinstance(value, str) and value:
                    out.append((f"{kind}.{attr}", value, head))
            options = getattr(proto, "options", None)
            # The row picker under a finding's table lists that table's own
            # cells as its options ("Read details for"; the options equal the
            # table's column, test_readability_a): they stand, with the table,
            # under the finding's caption, and are read under it, not under
            # the picker's label (ruling 123: "Sahl, On Nativities 2.1-2.21"
            # covers the prosperity picker's bare options).
            if options:
                over = finding["caption"] if kind == "Selectbox" and head == "Read details for" else head
                try:
                    out.extend((f"{kind}.option", o, over) for o in options if isinstance(o, str))
                except TypeError:
                    pass
        children = getattr(node, "children", None)
        if children:
            for child in children.values():
                walk(child)

    walk(at.main)
    return out


_TEXTS = {}


def render_texts(page, runs, target):
    """Every (chart, depth, kind, text, over) the page shows for each
    (chart, (standard, keys), switches) of `runs` at `target`, both depths."""
    from streamlit.util import calc_hash

    from engine import TIME_STANDARD_OPTIONS
    out = []
    for chart, (standard, keys), switches in runs:
        for depth in DEPTHS:
            at = make_app(page=page)
            apply_switches(at, switches)
            at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[standard]
            for key, value in keys.items():
                at.session_state[key] = value
            at.session_state["manual_coords_key"] = True
            at.session_state["_reading_depth"] = depth
            at.session_state["_target_mode"] = "Date"
            at.session_state["_target_date"] = target
            at._page_hash = calc_hash(page)
            at.run(timeout=300)
            assert_no_exception(at, f"{chart}, {page}, {depth}")
            out.extend((chart, depth, kind, text, over) for kind, text, over in page_texts(at))
    return out


def texts_of(page):
    """Every (chart, depth, kind, text, over) the page shows for the charts
    above, rendered once per process; the first chart again with every
    reading switch flipped."""
    if page not in _TEXTS:
        runs = [(chart, spec, {}) for chart, spec in CHARTS.items()]
        runs.append(("florence, switches flipped", CHARTS["florence"], FLIPPED))
        _TEXTS[page] = render_texts(page, runs, TARGET)
    return _TEXTS[page]


def page_book(page, texts):
    """The book the page's opening caption names (ruling 117), or None; a
    captioned page must still open with its caption."""
    if page not in CAPTIONED:
        return None
    caption, book, _form = CAPTIONED[page]
    shown = [text for _c, _d, kind, text, _o in texts if kind.startswith("Caption")]
    assert any(text.startswith(caption) for text in shown[:3]), (
        f"premise: the {page} page opens with its caption naming {book}: {shown[:3]}")
    return book


def _context(text, m):
    lo = max(0, m.start() - 60)
    return " ".join(text[lo:m.end() + 40].split())


def bare_locators(page):
    """(locator, kind, the text around it) for every locator the page shows
    that names no work in its sentence and is not its opening caption's
    book's (ruling 117: a locator of that book, in that book's form, stays
    bare; PAGE_WORKS keys the ones of another work in the same form)."""
    texts = texts_of(page)
    book = page_book(page, texts)
    bare = set()
    for _chart, _depth, kind, text, over in texts:
        for m in locators(text):
            if (names_its_work(text, m) or quoted(text, m.start()) or WORK.search(over)
                    or WORK.search(column_head(text, m.start()))):
                continue
            if book is not None and CAPTIONED[page][2].match(m.group(0)):
                want = PAGE_WORKS.get((page, m.group(0)))
                if want is None or re.fullmatch(want, book):
                    continue
            if (page, m.group(0)) in RULED_BARE or (page, m.group(0)) in LEFT_AS_FOUND:
                continue
            bare.add((m.group(0), kind, _context(text, m)))
    return sorted(bare)


# Bare by the owner's ruling 115: the Revolutions count line names the II.3
# table by its chapter ("... governor, II.3, shifts"), under the page's
# opening caption. (Its form is PN IV's, so the caption covers it here too;
# the entry keeps the ruling beside the line.)
RULED_BARE = {("timing", "II.3"): "ruling 115"}

# Read in the corpus and found in no book as printed, or in a form the book
# does not print for its work: reported, and left as it stands (the lane's
# brief: a locator in no book, or in another, is a finding, and nothing is
# changed for it).
LEFT_AS_FOUND: dict[tuple[str, str], str] = {}

# Each locator below was read in the corpus in the work named beside it (the
# lane's report, PWR2_BUILD.md, gives the file and line of each). On a
# captioned page it has the caption's book's form but is another work's; on
# any page a reader could take it for another work's. Each must be assigned
# its own work where the page prints it.
GI, PN4, NAT, ITA = r"Gr\. ?Intr\.|Great Introduction", r"PN ?IV", r"On Nativities", r"\bITA\b"
PAGE_WORKS: dict[tuple[str, str], str] = {
    # Revolutions (PN IV's caption)
    ("timing", "IX.2, 33"): PN4,       # II.3's fn 38, after "Gr. Intr. VI.4, 4-6" in its sentence
    ("timing", "V.20"): GI,            # II.3's fn 39, 41: bright and dark degrees
    ("timing", "VII.5, 14"): GI,       # "mixing their natures in a weak way": no out-of-sign connection
    ("timing", "IV.12"): ITA,          # PN IV's fn 4 on III.1, 3: al-Qabisi IV.12, in ITA VIII.2.2
    ("timing", "IV.12c"): ITA,         # al-Qabisi's directions across quarters, ITA VIII.2.2
    ("timing", "1.23, 23"): NAT, ("timing", "1.23, 33"): NAT, ("timing", "1.24, 2"): NAT,
    # Fardar and ages (PN IV's caption)
    ("fardar", "I.16c"): ITA,          # al-Qabisi's triplicity lords, ITA I.7
    ("fardar", "I.57b"): ITA,          # al-Andarzaghar through al-Qabisi, ITA I.13
    ("fardar", "I.58"): ITA,           # the house of assets, ITA I.13
    ("fardar", "VII.8, 3-8"): GI,      # the fardars' and the planets' years restated in prose
    ("fardar", "III.7"): PN4,          # after "if we follow Valens" (Dykes's fn 191)
    ("fardar", "IV.10"): r"Tet\.",    # PN IV's fn 47: "Cf. the classic account in *Tet.* IV.10"
    ("fardar", "IX.8, 123"): PN4,      # after Sahl's 1.23, 2 in its cell
    ("fardar", "2.13, 39"): NAT, ("fardar", "2.19, 5"): NAT, ("fardar", "1.20, 15"): NAT,
    ("fardar", "1.23, 2"): NAT, ("fardar", "1.23, 68"): NAT,
    # The releaser (On Nativities' caption)
    ("releaser", "II.3"): PN4,         # the examination of the sign of the terminal point
    ("releaser", "III.1, 5"): PN4,     # "all of the planets and Lots are also directed"
    ("releaser", "IX.8, 30"): PN4, ("releaser", "IX.8, 32"): PN4, ("releaser", "VI.2, 1"): PN4,
    ("releaser", "1.15, 6"): NAT,      # fn 109, after Carmen's p. 108 fn 187
    ("releaser", "1.20, 10"): NAT, ("releaser", "1.18, 19"): NAT, ("releaser", "1.22, 9"): NAT,
    ("releaser", "1.30, 71"): NAT,     # after "Introduction 2, 37-44"
    ("releaser", "1.23, 46-50"): NAT, ("releaser", "1.23, 53"): NAT, ("releaser", "1.23, 68"): NAT,
    ("releaser", "1.16, 4"): NAT,      # after "PN IV IX.8, 32" in its sentence
}


@pytest.mark.parametrize("page", list(CAPTIONED))
def test_r02_another_works_locator_under_a_pages_opening_caption_names_its_work(page):
    """Ruling 117: under an opening caption naming one book, a citation
    that does not belong to that book is cited with its title."""
    texts = texts_of(page)
    assert sum(len(locators(t)) for *_x, t, _o in texts) > 20, "premise: the page prints locators"
    bare = bare_locators(page)
    assert bare == [], f"{len(bare)} locator(s) on the {page} page name no work:\n  " + "\n  ".join(
        f"{loc!r} [{kind}] :: {ctx}" for loc, kind, ctx in bare[:80])


@pytest.mark.parametrize("page", UNCAPTIONED)
def test_r02_every_locator_on_a_page_whose_opening_names_no_book_names_its_work(page):
    """Ruling 117: on a page whose opening names no book, every bare
    locator names its work (at its first locator in the sentence)."""
    texts = texts_of(page)
    assert page_book(page, texts) is None
    assert any(locators(t) for *_x, t, _o in texts), "premise: the page prints locators"
    bare = bare_locators(page)
    assert bare == [], f"{len(bare)} locator(s) on the {page} page name no work:\n  " + "\n  ".join(
        f"{loc!r} [{kind}] :: {ctx}" for loc, kind, ctx in bare[:80])


def form_misfits(page):
    """(locator, the work a reader assigns it, the text around it) for every
    locator whose form is not one that work's citations take in this app
    (On Nativities a dotted chapter; the roman-numbered works a roman book
    and chapter; The Introduction, On Choices, On Questions ... a "Ch.") --
    a list after a named work continues it, so a locator of another work
    there is read as the named one's."""
    texts = texts_of(page)
    book = page_book(page, texts)
    out = set()
    for _chart, _depth, _kind, text, over in texts:
        for m in locators(text):
            work = assigned_work(text, m, book, over)
            if work is None or quoted(text, m.start()) or (page, m.group(0)) in LEFT_AS_FOUND:
                continue
            takes = next(w for form, w in FORMS if form.match(m.group(0)))
            if not takes.search(work):
                out.add((m.group(0), work, _context(text, m)))
    return sorted(out)


@pytest.mark.parametrize("page", PAGES)
def test_r03_a_locator_on_the_page_has_a_form_its_assigned_work_takes(page):
    misfits = form_misfits(page)
    assert misfits == [], "\n  ".join(f"{loc!r} read as {work!r} :: {ctx}" for loc, work, ctx in misfits[:60])


@pytest.mark.parametrize("page", sorted({p for p, _l in PAGE_WORKS}))
def test_r03_a_locator_read_in_the_corpus_is_assigned_its_own_work_on_the_page(page):
    keyed = {loc: want for (p, loc), want in PAGE_WORKS.items() if p == page}
    texts = texts_of(page)
    book = page_book(page, texts)
    printed = {m.group(0) for *_x, text, _o in texts for m in locators(text)}
    assert set(keyed) <= printed, f"premise: the page prints them all: {set(keyed) - printed}"
    wrong = sorted({(m.group(0), assigned_work(text, m, book, over), _context(text, m))
                    for *_x, text, over in texts for m in locators(text)
                    if m.group(0) in keyed
                    and not re.fullmatch(keyed[m.group(0)], assigned_work(text, m, book, over) or "")}, key=str)
    assert wrong == [], "\n  ".join(f"{loc!r} read as {got!r} :: {ctx}" for loc, got, ctx in wrong[:60])


# --- After the check: the owner's rulings 123-126 ---------------------------------


def test_ruling_123_the_findings_row_pickers_options_stand_under_the_findings_caption():
    """The prosperity finding's picker lists bare On Nativities sentences
    ("(2.1, 9)"); the caption "Sahl, On Nativities 2.1-2.21" stands over the
    table and the picker, and it is what covers them, not the picker's
    label."""
    options = [(text, over) for _c, _d, kind, text, over in texts_of("findings")
               if kind == "Selectbox.option" and locators(text)]
    assert options, "premise: a finding's row picker lists locators"
    assert any(over.endswith("Sahl, On Nativities 2.1-2.21") for _t, over in options), {o for _t, o in options}
    # without the caption they would be bare: the caption is what names their work
    assert any(not names_its_work(text, m) for text, _o in options for m in locators(text))
    assert all(WORK.search(over) for _t, over in options), options


def _page_prose(page):
    return [text for _c, _d, _k, text, _o in texts_of(page)]


# Ruling 124's sentence as ruling 128 places it: it replaces the key's old
# closing sentence, keeping "other than The releaser". Ruling 147 (2): each
# page's work is its frame, not the source of all its rules (the pages apply
# others, which their captions name).
RULING_124 = ("On the Prediction pages other than The releaser, whose frame is PN IV, its locators are bare "
              "Book.chapter, sentence; on The releaser, whose frame is Sahl's *On Nativities*, its locators "
              "are bare chapter, sentence. Any other work cited there is named.")


def test_ruling_124_the_sources_key_says_which_pages_leave_which_locators_bare():
    prose = _page_prose("sources")
    assert prose, "premise: the page renders"
    assert any(RULING_124 in text for text in prose)
    assert not any("On the Prediction pages, whose rules" in text for text in prose)


def test_ruling_125_the_configurations_page_cites_vii5_121_in_the_house_form():
    prose = _page_prose("configurations")
    assert prose, "premise: the page renders"
    assert any("(Gr. Intr. VII.5, 121)" in text for text in prose)
    assert not any("Great Introduction VII.5" in text for text in prose)


def test_ruling_126_the_three_house_forms():
    dignities = _page_prose("dignities")
    assert dignities, "premise: the page renders"
    assert any("Jupiter (PN IV II.9, 15) uses a translator-supplied 'not'" in text for text in dignities)
    assert not any("II.9.15" in text for text in dignities)
    sources = _page_prose("sources")
    assert sources, "premise: the page renders"
    assert any("| ITA I.18, al-Qabisi I.22 |" in text for text in sources)
    assert not any("ITA I.22" in text for text in sources)
    from conftest import engine_source as _engine_source
    engine_source = _engine_source()                  # every engine module, not engine.py alone
    assert "al-Qabisi I.22, in ITA I.18 (ITA p. 81)" in engine_source
    assert "ITA I.22 (p. 81)" not in engine_source


# --- After the check: the owner's rulings 129-131 ---------------------------------

# Ruling 129: notes, help and prose name the work at their first locator,
# unless their own sentence already names it; under a page's opening
# caption that book's locators stay bare (ruling 117). A naming that a
# reader does not need -- the same work named earlier in the locator's
# sentence, or the caption's book on its own page with nothing else named
# before it -- is redundant.
_CANON = (
    (r"Abu Bakr", "Abu Bakr"), (r"Abu 'Ali|Judgments of Nativities|\bJN\b", "JN"),
    (r"Gr\. ?Intr\.|Great Introduction", "Gr. Intr."), (r"PN ?IV\b|Persian Nativities IV", "PN IV"),
    (r"\bPN ?III\b", "PN III"), (r"\bPN ?II\b", "PN II"), (r"\bPN ?I\b", "PN I"),
    (r"Introductions to Traditional Astrology|\bITA\b", "ITA"), (r"On Nativities", "On Nativities"),
    (r"\bIntroduction\b|\bIntro\b", "Introduction"), (r"Mathesis|Firmicus", "Mathesis"), (r"Carmen", "Carmen"),
    (r"Fifty Aphorisms", "Fifty Aphorisms"), (r"\bTBN\b|Book of (?:the )?Nativities", "TBN"),
    (r"Book of Aristotle|\bBA\b", "BA"), (r"Anthologies|Valens", "Anthologies"), (r"Rhetorius", "Rhetorius"),
    (r"Tetrabiblos|\bTet\.", "Tetrabiblos"), (r"Almagest", "Almagest"), (r"\bAbbr\.|Abbreviation", "Abbr."),
    (r"On Questions", "On Questions"), (r"On Choices|\bChoices\b", "On Choices"), (r"On Times", "On Times"),
    (r"Morin|Astrologia Gallica", "Morin"), (r"\bBW\b", "BW"), (r"Persian Nativities", "Persian Nativities"),
)


def _canon(work):
    """One name for a work however it is written ("Great Introduction",
    "Gr. Intr."; "Abu 'Ali", "JN")."""
    for pattern, name in _CANON:
        if re.search(pattern, work or ""):
            return name
    return work


# An author written before his title, or the house abbreviation of it: "JN"
# after "Abu 'Ali," is the work named twice; "Mathesis" after "Firmicus," is
# one naming.
_ABBREVIATED = re.compile(r"\bJN\b|\bBA\b|\bTBN\b|\bPN\b|Gr\. ?Intr\.|\bITA\b|\bAbbr\.|\bTet\.|\bBW\b")
_JOINED = re.compile(r"(?: al-Khayyat)?(?:'s)?,?\s*")


def _redundant(text, book, over=""):
    """(locator, naming, why, context) for each locator named at once before
    it ("Gr. Intr. VII.2", "Sahl, On Nativities 1.15") where a reader would
    assign it that work without the naming."""
    out = []
    found = locators(text)
    for i, m in enumerate(found):
        if quoted(text, m.start()):
            continue
        start = sentence_start(text, m.start())
        names = list(WORK.finditer(text, start, m.start()))
        if not names or not _AT_THE_LOCATOR.fullmatch(text, names[-1].end(), m.start()):
            continue
        naming = names[-1]
        # it also names the locator before it, written at once after that one
        if i and found[i - 1].end() <= naming.start():
            after = _NAMED_RIGHT_AFTER.match(text, found[i - 1].end())
            if after and after.end() >= naming.end():
                continue
        earlier = names[:-1]
        if (earlier and _JOINED.fullmatch(text, earlier[-1].end(), naming.start())
                and not _ABBREVIATED.fullmatch(naming.group(0))):
            earlier = earlier[:-1]
        work = _canon(naming.group(0))
        opened = _open_part(text, start, naming.start())
        open_names = [w for w in earlier if opened[w.start() - start:w.end() - start] == w.group(0)]
        if open_names:
            prior = open_names[-1].group(0)
        else:
            fitting = [w.group(0) for w in earlier if _takes(w.group(0), m.group(0)) and _at_a_locator(text, w)]
            prior = fitting[-1] if fitting else None
        if prior is not None:
            if _canon(prior) == work:
                out.append((m.group(0), naming.group(0), "sentence", _context(text, m)))
        elif (not earlier and book is not None and _canon(book) == work
              and not WORK.search(over or "") and not WORK.search(column_head(text, m.start()))):
            out.append((m.group(0), naming.group(0), "caption book", _context(text, m)))
    return out


# The page's headings are the export's section headings (the re-pass's
# L5-10: every export heading is a heading on its page), and the export opens
# with no book, so a heading names its work there and the page shows the same
# heading: under the caption it names that book as the export must.
_EXPORT_HEADINGS = {"Subheader.body"}

# Ruled to be named, under a later ruling's general rule: the connecting-
# planet note's "(Gr. Intr. VII.5, 121)", ruling 125, in the same sentence as
# "(Gr. Intr. VII.5, 24)"; the Sources page prints the same sentence.
RULED_NAMED = {("configurations", "VII.5, 121"): "ruling 125", ("sources", "VII.5, 121"): "ruling 125",
               # The citation register holds the bare form unsettled (in two
               # works, or by its neighbours), and a pending locator in such a
               # form names its volume (test_citation_register, lane TL's TL-09).
               ("timing", "II.3, 6"): "TL-09", ("timing", "VIII.1, 1-2"): "TL-09",
               # Ruling 132's TL-09 class: round 2026-10-07 registered these
               # bare forms unsettled, so each names its volume though its
               # sentence names the work earlier.
               ("timing", "VI.4, 4-6"): "TL-09", ("fardar", "VII.8, 3"): "TL-09",
               ("sources", "II.3, 5"): "TL-09",
               # A figure number names its volume before it
               # (test_no_new_bare_page_or_figure_number): "Gr. Intr. V.5 (Figure 38)".
               ("reference", "V.5"): "a figure's volume"}

# PN IV named at its own locators on the Prediction pages, under PN IV's
# caption: held for the owner. Rulings 117 and 129 reach them (the caption's
# book, or PN IV named again in its sentence), but the round-25f tightenings
# pin several as naming the volume (test_tightenings_r25f's A1, A2 and B;
# test_locators_r25e's fn 13), and the instruction for this commit named The
# releaser's book. Each is the page's text as it stood before this lane, but
# the count line's "(PN IV I.2, 1-3)" and "(PN IV IV.1, 11)", one sentence
# for all four Prediction pages (pn4_count_line) that the export prints too.
HELD_PN4: set[tuple[str, str]] = {
    ("days", "I.2, 1-3"), ("days", "IX.1, 26-34"),
    ("fardar", "I.2, 1-3"), ("fardar", "II.3, 1"), ("fardar", "III.1, 12"), ("fardar", "IV.1, 11"),
    ("fardar", "IX.2, 4-5"), ("fardar", "IX.8, 123"), ("fardar", "IX.9, 10"), ("fardar", "VI.2, 21"),
    ("fardar", "VI.2, 4"),
    ("releaser", "I.2, 1-3"),
    ("timing", "I.2, 1-3"), ("timing", "I.4, 23-31"), ("timing", "I.6"), ("timing", "I.6, 3"), ("timing", "I.6, 6"),
    ("timing", "I.7, 17"), ("timing", "II.1, 6-7, 25"), ("timing", "II.23, 1"), ("timing", "II.3, 3"),
    ("timing", "II.3, 3-18"), ("timing", "II.3, 5"), ("timing", "II.3, 5-8"), ("timing", "III.1, 10"),
    ("timing", "III.1, 12"), ("timing", "III.1, 13"), ("timing", "III.1, 16"), ("timing", "III.1, 50"),
    ("timing", "III.2, 2-3"), ("timing", "III.2, 69"), ("timing", "III.2, 93"), ("timing", "III.8, 9"),
    ("timing", "IV.1, 11"), ("timing", "IV.7, 24"), ("timing", "IX.3, 4"), ("timing", "IX.3, 8"),
    ("timing", "IX.9, 10"), ("timing", "IX.9, 12"), ("timing", "IX.9, 4"), ("timing", "VI.2, 2-17"),
    ("timing", "VI.2, 21"), ("timing", "VI.2, 21-24"),
}


def redundant_namings(page, texts=None):
    texts = texts_of(page) if texts is None else texts
    book = page_book(page, texts)
    out = set()
    for _chart, _depth, kind, text, over in texts:
        for loc, naming, why, ctx in _redundant(text, book, over):
            if why == "caption book" and kind in _EXPORT_HEADINGS:
                continue
            if _canon(naming) == "PN IV" and (page, loc) in HELD_PN4:
                continue
            if (page, loc) in RULED_NAMED:
                continue
            out.add((loc, naming, why, kind, ctx))
    return sorted(out)


# Ruling 132: rulings 86, 117 and 129 let a locator stay bare where something
# already names its work, and require no name to be removed. A work named
# again is therefore not a fault, and the exemptions above (HELD_PN4,
# RULED_NAMED, the headings) now only record why each such naming stands.
# What the rulings do hold bare is ruling 129's own list ("under any reading
# these are fixed"), and each item on it is one sentence, not the page: a
# naming the reader above finds fails the pin only where it stands in one
# of those sentences, with a work written into it.
#
# A site is the sentence's own words with "{}" where a naming would stand.


def _site(*templates):
    """One pattern for the sites `templates`: each matches its words with
    one to four words written in at "{}", and not the bare site."""
    return re.compile("|".join(re.escape(before) + r"(?:\S+ ){1,4}" + re.escape(after)
                               for before, after in (t.split("{}") for t in templates)))


def _sites_in(text, form):
    """A template for each place `form` stands in `text`: the two words
    before it, "{}", and the locator with the word after it."""
    return tuple(" ".join(text[:m.start()].split()[-2:]) + " {}" + re.match(r"\S+(?: \S+)?", text[m.start():]).group(0)
                 for m in form.finditer(text))


# Ruling 129's sentences. "On Nativities 1.20" on The releaser is Abu
# 'Ali's ladder note (JN_YEARS_NOTE: "no sentence of 1.20, 10-34", "as 1.20
# is placed", "'Umar's and 1.20, 15's"), read off the note itself; Fardar's
# is the Planetary years table's last-column caption ("the class Abu 'Ali's
# ladder gives the planet (JN Ch. 3), its count from JN Ch. 4's table"),
# and The releaser's the additions note's "The principal rows state Abu
# 'Ali, JN Ch. 4." (JN_CH4_ADDITIONS_NOTE).
_FORM_1_20 = re.compile(r"1\.20(?![\d.])")


def _jn_years_note():
    from engine import JN_YEARS_NOTE
    return JN_YEARS_NOTE


SITES_1_20 = _sites_in(_jn_years_note(), _FORM_1_20)
SITE_FARDAR_JN = "its count from {}Ch. 4's table"
SITE_RELEASER_JN = "The principal rows state Abu 'Ali, {}Ch. 4."

#   (pages, the locator's form, the work named again, the site, ruling 129's words)
RULED_BARE_129 = (
    (("chart", "dignities", "findings", "configurations", "lots"), re.compile(r"VII\.2$"), "Gr. Intr.",
     re.compile(r"VII\.2 band"), "the readings note naming Gr. Intr. twice in one line"),
    (("fardar",), re.compile(r"Ch\. 4$"), "JN", _site(SITE_FARDAR_JN),
     "Fardar's \"(JN Ch. 3) ... JN Ch. 4's table\""),
    (("releaser",), re.compile(r"Ch\. 4$"), "JN", _site(SITE_RELEASER_JN), "The releaser's \"Abu 'Ali, JN Ch. 4.\""),
    (("releaser",), _FORM_1_20, "On Nativities", _site(*SITES_1_20),
     "\"On Nativities 1.20\" on The releaser, which ruling 117 keeps bare"),
)


def ruled_bare(page, loc, naming, ctx):
    """Ruling 129's words for the fixed site a redundant naming falls on, or
    None where ruling 132 lets the naming stand."""
    for pages, form, work, site, words in RULED_BARE_129:
        if page in pages and form.match(loc) and _canon(naming) == work and site.search(ctx):
            return words
    return None


@pytest.mark.parametrize("page", PAGES)
def test_ruling_129_no_locator_is_named_where_its_sentence_or_its_pages_caption_already_names_its_work(page):
    """Ruling 129's fixed sites stay bare; any other naming of a work its
    sentence or its page's caption already names is let stand (ruling 132)."""
    texts = texts_of(page)
    assert any(locators(t) for *_x, t, _o in texts), "premise: the page prints locators"
    found = [(loc, naming, why, kind, ctx, words) for loc, naming, why, kind, ctx in redundant_namings(page)
             if (words := ruled_bare(page, loc, naming, ctx))]
    assert found == [], f"{len(found)} naming(s) on the {page} page that ruling 129 made bare:\n  " + "\n  ".join(
        f"{naming} {loc!r} ({why}; {words}) [{kind}] :: {ctx}" for loc, naming, why, kind, ctx, words in found[:80])


def test_ruling_132_the_redundancy_pin_catches_ruling_129s_sites_and_lets_other_namings_stand():
    """The reader finds both plants redundant; ruling 129 fixed the first
    bare, and ruling 132 lets the second stand."""
    caught = "the class Abu 'Ali's ladder gives the planet (JN Ch. 3), its count from JN Ch. 4's table"
    (loc, naming, why, ctx), = _redundant(caught, "PN IV")
    assert (loc, why) == ("Ch. 4", "sentence")
    assert ruled_bare("fardar", loc, naming, ctx) == "Fardar's \"(JN Ch. 3) ... JN Ch. 4's table\""
    allowed = ("**Figure 146 (Gr. Intr. VII.8, p. 487)**, verified against the prose restatement at Gr. Intr. "
               "VII.8, 3-8 and the fardar total")
    (loc, naming, why, ctx), = _redundant(allowed, "PN IV")
    assert (loc, why) == ("VII.8, 3-8", "sentence")
    assert ruled_bare("fardar", loc, naming, ctx) is None
    # the readings note: its value bare passes the reader; named again it is ruling 129's site
    note = "Gr. Intr. VII.6, 27/45 'eastern/western relative to the Sun' = Gr. Intr. VII.2 band"
    (loc, naming, why, ctx), = _redundant(note, None)
    assert ruled_bare("configurations", loc, naming, ctx) == "the readings note naming Gr. Intr. twice in one line"
    assert _redundant(note.replace("= Gr. Intr. VII.2", "= VII.2"), None) == []
    # The releaser's own book named at 1.20 (the caption's book), and the same naming on Fardar
    ladder = "Read: the place by the division, as On Nativities 1.20 is placed"
    (loc, naming, why, ctx), = _redundant(ladder, "On Nativities")
    assert ruled_bare("releaser", loc, naming, ctx) and ruled_bare("fardar", loc, naming, ctx) is None


def test_ruling_132_each_ruled_site_is_its_sentence_not_its_page():
    """Ruling 129's sites are sentences: the "1.20" row is read off Abu
    'Ali's ladder note and holds its three places there, named or bare; any
    other "On Nativities 1.20, N" on The releaser stands (ruling 132), and
    the JN rows hold their own sentences only."""
    from engine import JN_CH4_ADDITIONS_NOTE, JN_YEARS_NOTE, PN4_RELEASER_UNRESOLVED
    assert SITES_1_20 == ("sentence of {}1.20, 10-34", "division, as {}1.20 is", "'Umar's and {}1.20, 15's);")
    assert len(_FORM_1_20.findall(JN_YEARS_NOTE)) == 3
    for template in SITES_1_20:
        assert template.format("") in JN_YEARS_NOTE
        (loc, naming, why, ctx), = _redundant(template.format("On Nativities "), "On Nativities")
        assert ruled_bare("releaser", loc, naming, ctx), template
    # the whole note, each place named, as Fardar prints the first two (ruling 129)
    named = JN_YEARS_NOTE.replace("1.20", "On Nativities 1.20")
    caught = [(loc, ruled_bare("releaser", loc, naming, ctx)) for loc, naming, _w, ctx in _redundant(named, "On Nativities")]
    assert [loc for loc, words in caught if words] == ["1.20, 10-34", "1.20", "1.20, 15"], caught
    # The open election's sentence names its 1.20, 6: read as redundant, and let stand
    (loc, naming, why, ctx), = [r for r in _redundant(PN4_RELEASER_UNRESOLVED, "On Nativities") if r[0] == "1.20, 6"]
    assert (naming, why) == ("On Nativities", "caption book")
    assert ruled_bare("releaser", loc, naming, ctx) is None
    # the JN rows: their own sentences, bare in the source; JN Ch. 4 named elsewhere on the page stands
    assert "planet (JN Ch. 3), " + SITE_FARDAR_JN.format("") in (Path(__file__).parent.parent / "app.py").read_text()
    assert SITE_RELEASER_JN.format("") in JN_CH4_ADDITIONS_NOTE
    (loc, naming, why, ctx), = _redundant(JN_CH4_ADDITIONS_NOTE.replace("Abu 'Ali, Ch. 4", "Abu 'Ali, JN Ch. 4"),
                                          "On Nativities")
    assert ruled_bare("releaser", loc, naming, ctx) == "The releaser's \"Abu 'Ali, JN Ch. 4.\""
    elsewhere = "Abu 'Ali's sextile rule (JN Ch. 3), and his count from JN Ch. 4's other column"
    (loc, naming, why, ctx), = _redundant(elsewhere, "PN IV")
    assert ruled_bare("fardar", loc, naming, ctx) is None and ruled_bare("releaser", loc, naming, ctx) is None


# The open election (lane WL's A3 chart): Florence, 1900-04-27 08:00 UT, at
# 1960-06-01. The releaser page then prints PN4_RELEASER_UNRESOLVED, whose
# "On Nativities 1.20, 6" is not ruling 129's site.
OPEN_ELECTION = ("florence, the election open",
                 (2, dict(date_input_key="1900-04-27", time_input_key=time(8, 0), utc_offset_key=0.0,
                          manual_lat_key=43.7792, manual_lon_key=11.2463)), {})


def test_ruling_132_the_open_elections_named_1_20_6_stands_on_the_releaser():
    from engine import TIME_STANDARD_OPTIONS
    assert TIME_STANDARD_OPTIONS[OPEN_ELECTION[1][0]] == "Manual UTC offset"
    texts = render_texts("releaser", [OPEN_ELECTION], "1960-06-01")
    shown = {d for _c, d, _k, t, _o in texts if "(On Nativities 1.20, 6, as this app reads it)" in t}
    assert shown == set(DEPTHS), f"premise: both depths show the open election's sentence: {shown}"
    found = redundant_namings("releaser", texts)
    named = [r for r in found if r[0] == "1.20, 6" and r[1] == "On Nativities"]
    assert named, f"premise: the reader finds the naming: {found}"
    assert [r for r in found if ruled_bare("releaser", r[0], r[1], r[4])] == [], found


def test_ruling_129_the_ladder_note_is_named_on_fardar_and_bare_on_the_releaser():
    fardar = " ".join(t for *_x, t, _o in texts_of("fardar"))
    releaser = " ".join(t for *_x, t, _o in texts_of("releaser"))
    assert "Read: the place by the division, as On Nativities 1.20 is placed" in fardar
    assert "Read: the place by the division, as 1.20 is placed" in releaser
    assert "as On Nativities 1.20 is placed" not in releaser


def test_ruling_130_the_triplicity_tables_sources():
    from engine import TRIPLICITY_TABLE_SOURCES
    assert TRIPLICITY_TABLE_SOURCES["Sahl"] == "Sahl, The Introduction Ch. 1, 35-41, Figure 4"
    assert TRIPLICITY_TABLE_SOURCES["Great Introduction"] == "Gr. Intr. V.14, 6-9, Figure 53, fn 100"
    reference = [t for *_x, t, _o in texts_of("reference")]
    assert reference, "premise: the page renders"
    assert any("Source selection: Sahl, The Introduction Ch. 1, 35-41, Figure 4 supplies" in t for t in reference)
    assert not any("Introduction 1.37" in t for t in reference)


def test_ruling_131_the_sources_key_has_rows_for_jn_and_rhetorius():
    sources = [t for *_x, t, _o in texts_of("sources")]
    assert sources, "premise: the page renders"
    key = next(t for t in sources if t.startswith("| Citation form | Work | Example |"))
    rows = {r.split("|")[1].strip(): r.split("|")[3].strip() for r in key.splitlines()[2:]}
    assert rows["JN"] == "JN Ch. 3"
    assert rows["Rhetorius"] == "Rhetorius Ch. 57"
