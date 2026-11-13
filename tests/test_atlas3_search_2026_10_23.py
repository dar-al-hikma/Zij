"""The city search reads short forms of regions and countries.

The atlas codes the regions of Canada and Australia by number, so a postal
abbreviation typed after a comma ("Vancouver, BC", "Sydney, NSW") was no
region's code and began no region's name, and found nothing; "Washington,
D.C." was compared as "d.c"; "Great Britain" and "Britain" were no country;
"St. Kitts" in a qualifier was not Saint Kitts; "UK" also began Ukraine and
"USA" a Turkish region; only a trailing bracket of two letters was read; and a
text of many empty parts made one look for each comma.

Now the postal abbreviations of Canada's thirteen and Australia's eight
regions hold for their regions, each resolved from the atlas's own table of
regions, besides wherever they held; a qualifier of single letters each with
its period is its letters; "Great Britain" and "Britain" are Britain; a
country word names its country alone; St., Ste., Ft. and Mt. in a qualifier
stand for their other forms when it is compared with a name; a trailing
bracket of two letters that is a country's code is that country's alone, and
any other trailing bracket is one more part; and each look is made once. The
atlas is put in the checkout before any test runs, so nothing here skips.
"""
import random
import sqlite3

import pytest

from conftest import APP_PATH, assert_no_exception, make_app
from test_b14_atlas_search_fold_2026_10_11 import _as_before, atlas_matches  # noqa: F401  (fixture)

ATLAS = APP_PATH.parent / "atlas.db"
PICKER = "Select specific location:"
NO_MATCH = "No matches found in offline atlas."


def _rows(text):
    import time_zones
    return time_zones.atlas_rows(ATLAS, text)


def _labels(text):
    return [f"{name}, {region} ({country})" if region else f"{name} ({country})"
            for name, region, country, _lat, _lon in _rows(text)]


def _atlas():
    return sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True)


def _region(country, name):
    """The atlas's code of the region of `country` named `name`."""
    with _atlas() as conn:
        (code,) = conn.execute("SELECT admin1 FROM admin1_names WHERE country = ? AND name = ?",
                               (country, name)).fetchall()
    return code[0]


def _holding(*qualifiers):
    import time_zones
    with _atlas() as conn:
        return time_zones._atlas_holding(conn.cursor(), qualifiers)


# --- region abbreviations ------------------------------------------------------

CANADA = {"ab": "Alberta", "bc": "British Columbia", "mb": "Manitoba", "nb": "New Brunswick",
          "nl": "Newfoundland and Labrador", "ns": "Nova Scotia", "nt": "Northwest Territories", "nu": "Nunavut",
          "on": "Ontario", "pe": "Prince Edward Island", "qc": "Quebec", "sk": "Saskatchewan", "yt": "Yukon"}
AUSTRALIA = {"act": "Australian Capital Territory", "nsw": "New South Wales", "nt": "Northern Territory",
             "qld": "Queensland", "sa": "South Australia", "tas": "Tasmania", "vic": "Victoria",
             "wa": "Western Australia"}


def test_the_table_holds_the_twenty_one_abbreviations_each_with_its_region_s_name():
    import time_zones
    table = time_zones.ATLAS_REGION_ABBREVIATIONS
    assert len(table) == 21 and len(set(table)) == 21
    assert {(abbreviation, name) for abbreviation, country, name in table if country == "CA"} == set(CANADA.items())
    assert {(abbreviation, name) for abbreviation, country, name in table if country == "AU"} == set(AUSTRALIA.items())


@pytest.mark.parametrize("country, abbreviation, name",
                         [("CA", a, n) for a, n in CANADA.items()] + [("AU", a, n) for a, n in AUSTRALIA.items()])
def test_each_abbreviation_resolves_to_exactly_one_region_of_its_country(country, abbreviation, name):
    """Read from the atlas's own table of regions, never a region number
    written in the code: exactly one region of the country is held for it,
    the one of that name."""
    _by_country, by_region = _holding(abbreviation)[abbreviation]
    assert [pair for pair in by_region if pair[0] == country] == [(country, _region(country, name))]


@pytest.mark.parametrize("abbreviation, also", [
    ("nl", {"NL"}), ("sa", {"SA"}), ("pe", {"PE"}), ("sk", {"SK"}), ("yt", {"YT"}),
])
def test_an_abbreviation_that_is_a_country_s_code_holds_for_both(abbreviation, also):
    by_country, by_region = _holding(abbreviation)[abbreviation]
    assert also <= by_country
    region = CANADA.get(abbreviation) if abbreviation in CANADA else AUSTRALIA[abbreviation]
    country = "CA" if abbreviation in CANADA else "AU"
    assert (country, _region(country, region)) in by_region


def test_wa_holds_washington_and_western_australia_and_nt_two_territories():
    _countries, wa = _holding("wa")["wa"]
    assert {("US", "WA"), ("AU", _region("AU", "Western Australia"))} <= wa
    _countries, nt = _holding("nt")["nt"]
    assert {("CA", _region("CA", "Northwest Territories")), ("AU", _region("AU", "Northern Territory"))} <= nt


@pytest.mark.parametrize("typed, label", [
    ("Vancouver, BC", "Vancouver, 02 (CA)"),
    ("Vancouver, bc", "Vancouver, 02 (CA)"),
    ("Kelowna, B.C.", "Kelowna, 02 (CA)"),
    ("Calgary, AB", "Calgary, 01 (CA)"),
    ("Montreal, QC", "Montréal, 10 (CA)"),
    ("Winnipeg, MB", "Winnipeg, 03 (CA)"),
    ("Halifax, NS", "Halifax, 07 (CA)"),
    ("Regina, SK", "Regina, 11 (CA)"),
    ("Charlottetown, PE", "Charlottetown, 09 (CA)"),
    ("Yellowknife, NT", "Yellowknife, 13 (CA)"),
    ("Sydney, NSW", "Sydney, 02 (AU)"),
    ("Sydney, N.S.W.", "Sydney, 02 (AU)"),
    ("Brisbane, QLD", "Brisbane, 04 (AU)"),
    ("Canberra, ACT", "Canberra, 01 (AU)"),
    ("Darwin, NT", "Darwin, 03 (AU)"),
    ("Adelaide, SA", "Adelaide, 05 (AU)"),
    ("Perth, WA", "Perth, 08 (AU)"),
    ("Washington, D.C.", "Washington, DC (US)"),
    ("London, Great Britain", "London, ENG (GB)"),
    ("London, Britain", "London, ENG (GB)"),
    ("Basseterre, St. Kitts", "Basseterre, 03 (KN)"),
    ("Basseterre, St Kitts", "Basseterre, 03 (KN)"),
    ("Castries, St. Lucia", "Castries, 03 (LC)"),
    ("Saint Paul (USA)", "Saint Paul, MN (US)"),
    ("Vancouver (BC)", "Vancouver, 02 (CA)"),
    ("Basseterre (St. Kitts)", "Basseterre, 03 (KN)"),
    # Illinois' Springfield, the state's seat, before Missouri's, the more populous
    ("Springfield, U.S.A.", "Springfield, IL (US)"),
])
def test_a_short_form_finds_its_place_first(typed, label):
    assert _labels(typed)[0] == label, (typed, _labels(typed))


def test_st_john_s_nl_offers_st_john_s_in_newfoundland():
    assert f"St. John's, {_region('CA', 'Newfoundland and Labrador')} (CA)" in _labels("St. John's, NL")


def test_perth_wa_offers_perth_in_western_australia_first():
    labels = _labels("Perth, WA")
    assert labels[0] == f"Perth, {_region('AU', 'Western Australia')} (AU)"
    assert [label for label in labels if not label.endswith(("(AU)", ", WA (US)"))] == []


def test_an_abbreviation_still_holds_where_it_held():
    """"NL" is still the Netherlands, "SA" Saudi Arabia, "WA" Washington."""
    assert _labels("Amsterdam, NL")[0] == "Amsterdam, 07 (NL)"
    assert _labels("Riyadh, SA") == ["Riyadh, 10 (SA)"]
    assert _labels("Seattle, WA") == ["Seattle, WA (US)"]
    assert _labels("Lima, PE")[0] == "Lima, LMA (PE)"
    assert _labels("Bratislava, SK")[0] == "Bratislava, 02 (SK)"
    assert _labels("Toronto, ON") == ["Toronto, 08 (CA)"]


# --- initials and country words ------------------------------------------------

@pytest.mark.parametrize("typed, compared", [
    ("D.C.", "dc"), ("d.c.", "dc"), ("B.C.", "bc"), ("N.S.W.", "nsw"), ("U.S.A.", "usa"),
    # the country words as written are read first
    ("U.S.", "u.s"), ("U.K.", "u.k"), ("U.S", "u.s"),
    # no initials: a final period dropped, as before
    ("Minn.", "minn"), ("D.C", "d.c"), ("D. C.", "d. c"), ("Washington", "washington"),
    # a word of the abbreviation forms keeps its period
    ("St.", "st."), ("St. Kitts.", "st. kitts"),
])
def test_a_qualifier_as_it_is_compared(typed, compared):
    import time_zones
    assert time_zones._atlas_qualifier(typed) == compared


@pytest.mark.parametrize("word, country", [
    ("usa", "US"), ("u.s", "US"), ("uk", "GB"), ("u.k", "GB"), ("great britain", "GB"), ("britain", "GB"),
])
def test_a_country_word_names_its_country_alone(word, country):
    import time_zones
    assert time_zones.ATLAS_COUNTRY_ALIASES[word] == country
    assert _holding(word)[word] == ({country}, set())


def test_a_country_word_takes_no_country_or_region_it_begins():
    assert _labels("Kyiv, UK") == [] and _labels("Uzhhorod, Uk") == [] and _labels("Kyiv (UK)") == []
    assert _labels("Uşak, USA") == [] and _labels("Usak, USA") == []
    assert _labels("Kyiv")[0] == "Kyiv, 12 (UA)" and _labels("Uşak")[0] == "Uşak, 64 (TR)"
    assert not [label for label in _labels("London, Britain") if label.endswith("(CA)")]
    london = _labels("London, UK")
    assert london[0] == "London, ENG (GB)" and [label for label in london if not label.endswith("(GB)")] == []
    assert _labels("London, Great Britain") == _labels("London, Britain") == london


def test_four_letters_with_periods_are_not_initials():
    """"St." is a word, not an initial: it is read as its forms, so it holds
    Saint Kitts and Nevis, and as typed against a code, São Tomé's ST."""
    by_country, by_region = _holding("st.")["st."]
    assert {"KN", "LC", "ST"} <= by_country
    with _atlas() as conn:
        stockholm = conn.execute("SELECT country, admin1 FROM admin1_names WHERE name = 'Stockholm'").fetchall()
    assert stockholm and not set(stockholm) & by_region


# --- the word rule in a qualifier ----------------------------------------------

@pytest.mark.parametrize("typed", ["Basseterre, St. Kitts", "Basseterre, St Kitts", "Basseterre, Saint Kitts",
                                   "Basseterre, ST. KITTS", "Basseterre, St.Kitts", "Basseterre, Saint Kitts and Nevis"])
def test_saint_kitts_in_any_form_holds_saint_kitts_and_nevis(typed):
    assert _labels(typed) == ["Basseterre, 03 (KN)"], typed


def test_a_qualifier_is_read_as_typed_against_a_code():
    """The word rule is for names: against a code the qualifier is what was
    typed, so "Paris, Mt" (no whole word) and "Paris, Mt." are compared
    with codes as "mt", Malta's."""
    for typed in ("mt", "mt."):
        by_country, _by_region = _holding(typed)[typed]
        assert "MT" in by_country, typed


# --- the trailing bracket -------------------------------------------------------

@pytest.mark.parametrize("bracketed, comma", [
    ("Saint Paul (USA)", "Saint Paul, USA"),
    ("Vancouver (BC)", "Vancouver, BC"),
    ("Sydney (N.S.W.)", "Sydney, N.S.W."),
    ("Basseterre (St. Kitts)", "Basseterre, St. Kitts"),
    ("London (Great Britain)", "London, Great Britain"),
    ("Kyiv (UK)", "Kyiv, UK"),
    ("Paris (Tennessee)", "Paris, Tennessee"),
    ("Paris ()", "Paris,"),
])
def test_a_bracket_that_is_no_country_code_is_one_more_part(bracketed, comma):
    assert _labels(bracketed) == _labels(comma), bracketed
    assert _labels(bracketed) or bracketed == "Kyiv (UK)"


def test_a_two_letter_bracket_that_is_a_country_s_code_is_that_country_alone():
    """"(NL)" is the Netherlands, never Newfoundland; "(CA)" is no region,
    so never California. (It holds, as before, where it is the country's
    code or begins the country's name.)"""
    assert _labels("St. John's (NL)") == []
    assert _labels("Amsterdam (NL)")[0] == "Amsterdam, 07 (NL)"
    assert not [label for label in _labels("San (CA)") if label.endswith("(US)")]
    assert _labels("Vancouver (CA)")[0] == "Vancouver, 02 (CA)"
    # its exact matches alone, as a qualified complete name now gives
    assert _labels("Saint Paul, MN (US)") == ["Saint Paul, MN (US)"]
    assert not [label for label in _labels("B (MN)") if label.endswith("(US)")]


@pytest.mark.parametrize("name", ["Frankfurt (Oder)", "Halle (Saale)", "Zürich (Kreis 11)", "Halle (Saale)  "])
def test_a_name_holding_a_bracket_gives_what_it_gave(atlas_matches, name):
    import time_zones
    assert time_zones._atlas_looks(name.strip()) is not None
    assert atlas_matches(name) == (_as_before(name), None)


def test_a_seeded_sample_of_names_holding_a_bracket_give_what_they_gave(atlas_matches):
    """Typed whole, a name that ends in a bracket is found by the whole
    text's look as before; the text before its bracket, narrowed by what is
    in it, adds nothing for these."""
    with _atlas() as conn:
        names = sorted({name for (name,) in conn.execute("SELECT name FROM cities WHERE name LIKE '%)'")
                        if "(" in name and not name.startswith("(")})
    assert len(names) > 1000
    for name in random.Random(2310).sample(names, 30):
        options, _why = atlas_matches(name)
        assert options == _as_before(name), name


def test_a_name_holding_a_bracket_typed_with_more_after_it():
    assert _labels("Frankfurt (Oder), DE") == ["Frankfurt (Oder), 11 (DE)"]
    assert _labels("Frankfurt (Oder) (DE)") == ["Frankfurt (Oder), 11 (DE)"]
    assert _labels("Frankfurt (Oder), Brandenburg") == ["Frankfurt (Oder), 11 (DE)"]


@pytest.mark.parametrize("typed", ["Paris (%)", "Paris (_)", "Paris (')", "Paris (\\)", "Paris (T%)", "Paris (_N)",
                                   "Paris (TN, US)", "(USA)", "()"])
def test_a_bracket_s_text_is_never_a_pattern(atlas_matches, typed):
    options, why = atlas_matches(typed)
    assert options is None and why == NO_MATCH, (typed, options)


def test_a_bracket_opened_twice_is_a_name_s_own_bracket_read_as_text(atlas_matches):
    """"Paris (()" finds the names that begin "Paris (" as written, GeoNames'
    "Paris (historical)" places, read as text and not as a pattern; on the
    cities500 atlas no name began so, and it found nothing."""
    options, why = atlas_matches("Paris (()")
    assert why is None and options and all(label.startswith("Paris (historical), ") for label in options), options
    assert len(options) == 7


def test_a_seeded_sample_of_labels_keep_their_country_alone():
    """The app's labels typed back end in their country's code: every option
    is in that country, as before."""
    with _atlas() as conn:
        rows = conn.execute("SELECT name, admin1, country FROM cities ORDER BY id").fetchall()
    sample = random.Random(2210).sample(rows, 60)
    assert len(sample) == 60
    for name, admin1, country in sample:
        region = (admin1 or "").strip()
        label = f"{name}, {region} ({country})" if region else f"{name} ({country})"
        assert [option for option in _labels(label) if not option.endswith(f"({country})")] == [], label


def test_nan_nan_still_finds_nan():
    assert _labels("nan, nan")[0] == "Nan, 04 (TH)"


# --- each look once ------------------------------------------------------------

@pytest.mark.parametrize("text, looks", [
    ("S" + "," * 199, 2), ("S" + ", " * 99, 2), ("a" + "," * 199, 2), ("Saint Paul" + ", " * 50 + "MN", 2),
    ("Saint Paul, , , MN", 2), ("Saint Paul, MN, , MN", 3), ("Paris, MN, MN", 3), ("a, b, c, d, e", 5),
    ("Vancouver, BC", 2), ("Saint Paul (USA)", 2), ("Saint Paul, MN (US)", 3), ("Paris ()", 2),
])
def test_each_look_is_made_once(text, looks):
    """A look whose text and narrowing qualifiers are an earlier look's is
    not made again: a part left empty narrows nothing, so the text before it
    is the same look as the text before its comma."""
    import time_zones
    made = time_zones._atlas_looks(text)
    assert len(made) == looks, (text, made)
    keys = [(tuple(words), frozenset(qualifiers)) for words, qualifiers in made]
    assert len(set(keys)) == len(keys)
    assert all(qualifier for _words, qualifiers in made for qualifier in qualifiers)


def test_each_part_is_read_as_a_qualifier_once(monkeypatch):
    """Two hundred parts are two hundred readings, not one for each part
    after each comma."""
    import time_zones
    calls = []
    real = time_zones._atlas_qualifier

    def counted(text):
        calls.append(text)
        return real(text)
    monkeypatch.setattr(time_zones, "_atlas_qualifier", counted)
    time_zones._atlas_looks("S" + "," * 199)
    assert len(calls) == 200
    calls.clear()
    time_zones._atlas_looks("Saint Paul" + ", MN" * 20 + " (USA)")
    assert len(calls) == 22


def test_many_empty_parts_read_no_more_rows_than_one(monkeypatch):
    """The rows the comparison is handed for "S" and two hundred commas are
    those of "S" and one comma, counted at the comparison itself."""
    import time_zones
    calls = []
    # the indexed search reads each look's rows by its key range: counted
    # there
    real = time_zones._atlas_key_query

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(time_zones, "_atlas_key_query", counted)
    _rows("S,")
    once = len(calls)
    calls.clear()
    _rows("S" + "," * 199)
    assert once and len(calls) == once


def test_a_look_holding_a_comma_folds_only_names_holding_one(monkeypatch):
    """"St. Paul, MN" finds nothing as typed by its whole text, so that look
    is made once more, folded: only the names holding a comma are folded for
    it, not the fifth of the atlas whose names are not ASCII."""
    import time_zones
    calls = []
    real = time_zones._atlas_fold

    def counted(text):
        calls.append(text)
        return real(text)
    monkeypatch.setattr(time_zones, "_atlas_fold", counted)
    _rows("Paris, Texas")                              # the tables, folded once with this fold
    calls.clear()
    assert _rows("St. Paul, MN")
    assert calls and len(calls) < 100, len(calls)
    assert [text for text in calls if text and not text.isascii() and "," not in text] == []


# --- the box -------------------------------------------------------------------

def _picker_options(at):
    pickers = [s for s in at.sidebar.selectbox if s.label == PICKER]
    return pickers[0].options if pickers else []


def test_vancouver_bc_in_the_city_box_offers_vancouver_and_casts_there():
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "Vancouver, BC"
    at.run()
    assert_no_exception(at, "Vancouver, BC")
    label = f"Vancouver, {_region('CA', 'British Columbia')} (CA)"
    assert _picker_options(at)[0] == label
    assert NO_MATCH not in [w.value for w in at.sidebar.warning]
    assert [s.value for s in at.sidebar.success][0].startswith(f"**{label}**")
    with _atlas() as conn:
        (place,) = conn.execute("SELECT lat, lon FROM cities WHERE name = 'Vancouver' AND country = 'CA'"
                                " AND admin1 = ?", (_region("CA", "British Columbia"),)).fetchall()
    assert (at.session_state["_resolved_lat"], at.session_state["_resolved_lon"]) == place
