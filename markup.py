# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The escaping every picture and the HTML export share: the characters XML
1.0 forbids dropped, a value made safe for an SVG attribute or for SVG or HTML
text, and a typed name isolated so that whatever it does to its own direction
ends with it; and the words a page and a report print where the saved-data
file keeps its own. Standard library only: it imports nothing of the program. The
engine takes this module whole.
"""
import html
import re
import unicodedata


# What XML 1.0 forbids anywhere in a document, escaped or not: the C0
# controls other than tab, line feed and carriage return, U+FFFE and U+FFFF,
# and a lone surrogate. A name or place label holding one would make the wheel
# SVG, and so its download, not well-formed.
_XML_ILLEGAL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def _xml_legal(s):
    return _XML_ILLEGAL.sub('', str(s))


def _esc_attr(s):
    """A value on its way into an SVG attribute. Double quotes included: a
    Lot name carrying one would close the attribute and break a whole wheel. The
    characters XML 1.0 forbids are dropped first."""
    return html.escape(_xml_legal(s), quote=True)


def _esc_text(s):
    """A value on its way into SVG text content. The characters XML 1.0
    forbids are dropped first."""
    return html.escape(_xml_legal(s))


# The bidirectional classes that can move text
# outside a name -- right-to-left letters, Arabic digits and the explicit
# embeddings, overrides and isolates (U+202A-U+202E, U+2066-U+2069; the
# marks U+200F and U+061C are right-to-left letters to the algorithm).
# Here, not in app.py: the HTML
# export's heading and Place cells and the wheel's name and place isolate a
# typed name as the page and the Markdown export do.
_BIDI_MOVERS = frozenset(("R", "AL", "AN", "LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"))
_ISOLATE_OPENERS = "\u2066\u2067\u2068"
_ISOLATE_CLOSER = "\u2069"


def _isolated(text):
    """A name the page prints, kept from turning the app's own text around it
    (else "abc", RIGHT-TO-LEFT OVERRIDE, "def" would draw the strip's date,
    time and coordinates backwards, and the readings question would read right to
    left). A name holding a right-to-left letter, an Arabic digit or a
    directional control is set between FIRST STRONG ISOLATE and POP
    DIRECTIONAL ISOLATE: whatever it does to its own letters ends at the
    isolate's end, and the text after it reads in its own direction. Isolated
    rather than stripped, so the name is printed as typed, and so a name
    written right to left -- a Hebrew or an Arabic one, which needs no control
    at all -- cannot pull the separators beside it into its own direction.
    Inside the name, an isolate it opens and never closes is closed before
    the outer one, and a closing isolate with none open (which would end the
    outer isolate early) is dropped: it draws nothing. Every other name is
    returned as it is."""
    if not any(unicodedata.bidirectional(ch) in _BIDI_MOVERS for ch in text):
        return text
    depth, kept = 0, []
    for ch in text:
        if ch in _ISOLATE_OPENERS:
            depth += 1
        elif ch == _ISOLATE_CLOSER:
            if not depth:
                continue
            depth -= 1
        kept.append(ch)
    return "\u2068" + "".join(kept) + _ISOLATE_CLOSER * depth + "\u2069"


# What a page and a report print, beside what the saved-data file keeps. The rows
# keep their keys and words, which the code reads and the file writes; a table's
# headings and words are put in the page's form as they are drawn, here and in
# reader_analysis, so the two cannot part. Spellings are Dykes's printed forms; a
# quotation and a locator ("al-Qabisi IV.4", as the register reads it) stand as printed.
PAGE_COLUMN_NAMES = {'WS place': 'Whole-sign place', 'Placed in (WS place)': 'Whole-sign place',
                     'Sign Dispositor': 'Domicile lord', 'Domicile Lord': 'Domicile lord',
                     'Exaltation Lord': 'Exaltation lord',
                     'Separating From': 'Separates From', 'Connecting To': 'Connects To',
                     'Lot Name': 'Lot', 'Active Point': 'Active point', 'Active Ruler': 'Ruler'}
PAGE_CELL_WORDS = {'Domicile Lord': 'Domicile lord', 'Exaltation Lord': 'Exaltation lord',
                   'Annual Profection': 'Annual profection'}
_PAGE_PHRASES = {"Abu Ma'shar": "Abū Ma'shar", "Masha'allah": "Māshā'allāh",
                 "al-Qabisi": "al-Qabīsī", "Al-Qabisi": "Al-Qabīsī",
                 "the app's": "this app's", "The app's": "This app's",
                 "the Chronocrator Matrix's profection": "the annual profection",
                 "the promittor never rises or sets at this latitude, so it has no semi-arc to proportion":
                     "the star never rises or sets at this latitude",
                 "The releaser directed forward to the fourteen cutting stars":
                     "Each releaser directed forward to the fourteen cutting stars"}
_PAGE_PHRASE = re.compile(r"""(?<![\w'\u00b0])"[^"\n]*"|\u201c[^\u201d\n]*\u201d|"""
                          + "|".join(rf"{re.escape(old)}\b(?![ \u00a0][IVXLC]+\.)" for old in sorted(_PAGE_PHRASES, key=len, reverse=True)))


def page_words(text):
    """A string in the page's words: a quotation stands as printed; anything else as it is."""
    if not isinstance(text, str):
        return text
    return _PAGE_PHRASE.sub(lambda found: _PAGE_PHRASES.get(found.group(0), found.group(0)), text)


def page_column(name, others=()):
    """A column's heading on a page: the row's key where the page's name would
    stand twice in one table."""
    shown = PAGE_COLUMN_NAMES.get(name, name)
    return page_words(str(shown if shown not in others else name))


def page_cell(value):
    """A cell's words on a page or in a report; anything else as it stands."""
    if isinstance(value, str):
        return page_words(PAGE_CELL_WORDS.get(value, value))
    if isinstance(value, dict):
        return {page_words(key) if isinstance(key, str) else key: page_cell(held) for key, held in value.items()}
    if isinstance(value, list):
        return [page_cell(held) for held in value]
    return value


__all__ = ['html', 're', 'unicodedata', 'PAGE_COLUMN_NAMES', 'PAGE_CELL_WORDS', '_PAGE_PHRASES', '_PAGE_PHRASE', 'page_words', 'page_column', 'page_cell', '_XML_ILLEGAL', '_xml_legal', '_esc_attr', '_esc_text', '_BIDI_MOVERS',
           '_ISOLATE_OPENERS', '_ISOLATE_CLOSER', '_isolated']
