"""The city search reads abbreviation words, and a typed region or country.

The atlas keeps GeoNames' own spellings, which mix "St. Louis" with "Saint
Paul" and "Fort Worth" with no "Ft.", and the search matched the typed text
as a prefix of a name, comma and all. So "St. Paul" offered St. Pauli and
three small places but not Saint Paul, MN; "Ft. Worth" found nothing; and
"Saint Paul, MN", "Minneapolis, MN" or "Washington, DC" (whose label the app
itself writes "Washington, DC (US)") found nothing at all.

Now St., St, Saint and Sankt are one word when matching, and so are Ste.,
Ste and Sainte; Ft., Ft and Fort; Mt., Mt and Mount: in both directions,
anywhere in a name, a hyphen after one matching as a space. A typed word
counts only when it is whole, with its period or with a space or hyphen and
more text after it, so a text ending in a bare "St" is still being typed.
Text after a comma narrows the places the text before it finds to those
whose region or country it names, each later part one more qualifier; a
trailing "(XX)" is the country's; the whole text is still looked up, so a
name holding a comma is still found. A text with no such word and no comma
gives what it gave. The atlas is put in the checkout before any test
runs, so nothing here skips.
"""
import ast
import contextlib
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


def _place(name, admin1, country):
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        (place,) = conn.execute("SELECT lat, lon FROM cities WHERE name = ? AND admin1 = ? AND country = ?",
                                (name, admin1, country)).fetchall()
    return place


# --- abbreviation words --------------------------------------------------------

@pytest.mark.parametrize("typed, label", [
    ("St. Paul", "Saint Paul, MN (US)"),
    ("St Paul", "Saint Paul, MN (US)"),
    ("st. paul", "Saint Paul, MN (US)"),
    ("Sankt Paul", "Saint Paul, MN (US)"),
    ("St. Paul", "Saint-Paul, RE (RE)"),            # a hyphen after the word matches as a space
    ("St Paul", "Saint-Paul, RE (RE)"),
    ("St-Paul", "Saint-Paul, RE (RE)"),
    ("Saint Paul", "Saint-Paul, RE (RE)"),
    ("Saint Louis", "St. Louis, MO (US)"),
    ("Saint-Louis", "St. Louis, MO (US)"),
    ("St Louis", "St. Louis, MO (US)"),
    ("St. Gallen", "Sankt Gallen, SG (CH)"),
    ("Ft. Worth", "Fort Worth, TX (US)"),
    ("Ft Worth", "Fort Worth, TX (US)"),
    ("FT. WORTH", "Fort Worth, TX (US)"),
    ("Mt. Vernon", "Mount Vernon, NY (US)"),
    ("Mt Vernon", "Mount Vernon, NY (US)"),
    ("Sault Sainte Marie", "Sault Ste. Marie, 08 (CA)"),
    ("Sault Sainte Marie", "Sault Ste. Marie, MI (US)"),
    ("Sault Ste Marie", "Sault Ste. Marie, MI (US)"),
    # found only by the second, folded look, as a text with no word is
    ("st. étienne", "Saint-Étienne, 84 (FR)"),
])
def test_an_abbreviation_word_finds_its_other_forms(typed, label):
    assert label in _labels(typed), (typed, _labels(typed))


def test_st_paul_offers_saint_paul_minnesota_first():
    for typed in ("St. Paul", "St Paul", "Saint Paul"):
        assert _labels(typed)[0] == "Saint Paul, MN (US)", typed


@pytest.mark.parametrize("typed", ["St", "st", "Ste", "Saint", "Sainte", "Sankt", "Ft", "Fort", "Mt", "Mount",
                                   "  St  ", "Sault Ste", "Port St", "Stuttgart", "Fortaleza", "Mountain View",
                                   "Saintes", "Aust"])
def test_a_text_without_a_whole_word_gives_what_it_gave(atlas_matches, typed):
    """A bare "St" (and its fellows) at the end is still being typed, and a
    form inside a longer word is no word: the options, labels and order of
    before."""
    import time_zones
    assert time_zones._atlas_looks(typed.strip()) is None, typed
    assert atlas_matches(typed)[0] == _as_before(typed), typed


def test_st_alone_gives_todays_options(atlas_matches):
    options, why = atlas_matches("St")
    assert why is None and list(options.items()) == list(_as_before("St").items())
    assert "Stockholm, 26 (SE)" in options and "Stuttgart, 01 (DE)" in options


def test_a_word_is_whole_with_its_period_or_a_space_or_a_hyphen_and_more_text():
    import time_zones
    words = time_zones._atlas_words
    assert words("St. Paul") == [0, "Paul"]
    assert words("St Paul") == words("St-Paul") == words("St.Paul") == words("Saint Paul") == [0, "Paul"]
    assert words("Sankt  Paul") == [0, "Paul"]
    assert words("St.") == [0]
    assert words("St") == ["St"] and words("Saint") == ["Saint"] and words("Stuttgart") == ["Stuttgart"]
    assert words("Foo St, MN") == ["Foo St, MN"]                   # a part that ends in a bare word
    assert words("Foo St , MN") == ["Foo St , MN"]
    assert words("Sault Sainte Marie") == ["Sault ", 1, "Marie"]
    assert words("Ste. Foy") == [1, "Foy"] and words("Ft. Worth") == [2, "Worth"] and words("Mt Hood") == [3, "Hood"]
    assert words("Mountain") == ["Mountain"] and words("Saintes") == ["Saintes"] and words("Aust Paul") == ["Aust Paul"]
    assert words("St. " * 3 + "Paul") == [0, 0, 0, "Paul"]


def test_a_name_s_word_must_be_whole_too():
    """"Saint" is not the start of "Saintes", and "St." is not "Ste.": a
    typed word finds only a name whose word, at that place, is whole and of
    the same group."""
    assert not [label for label in _labels("St. Paul") if label.startswith(("Sainte", "Ste"))]
    assert not [label for label in _labels("St.") if label.startswith(("Saintes", "Stuttgart", "Stockholm"))]
    assert not [label for label in _labels("Mt.") if label.startswith("Mountain")]


# --- a typed region or country ---------------------------------------------------

@pytest.mark.parametrize("typed", ["Saint Paul, MN", "St. Paul, MN", "St Paul, MN", "Saint Paul, Minnesota",
                                   "Saint Paul, Minn.", "Saint Paul, minnesota", "Saint Paul, MN, US",
                                   "Saint Paul, US", "Saint Paul, United States", "Saint Paul, USA",
                                   "Saint Paul, U.S.", "Saint Paul, MN (US)", "St. Paul, MN (US)",
                                   "Saint Paul (US)", "Saint Paul , MN", "Saint Paul,MN"])
def test_a_typed_region_or_country_finds_saint_paul_minnesota_first(typed):
    assert _labels(typed)[0] == "Saint Paul, MN (US)", (typed, _labels(typed))


@pytest.mark.parametrize("typed, label", [
    ("Minneapolis, MN", "Minneapolis, MN (US)"),
    ("Washington, DC", "Washington, DC (US)"),
    ("Washington, DC (US)", "Washington, DC (US)"),
    ("Paris, TN", "Paris, TN (US)"),
    ("Paris, Tennessee", "Paris, TN (US)"),
    ("Paris, Tenn.", "Paris, TN (US)"),
    ("Munich, Bav", "Munich, 02 (DE)"),
    ("Munich, Bavaria", "Munich, 02 (DE)"),
    ("Munich, Germany", "Munich, 02 (DE)"),
    ("Berlin, Germany", "Berlin, 16 (DE)"),
    ("London, UK", "London, ENG (GB)"),
    ("London, U.K.", "London, ENG (GB)"),
    ("London, United Kingdom", "London, ENG (GB)"),
    ("Singapore (SG)", "Singapore (SG)"),
    # the text before the comma found only by the folded look
    ("évora, Portugal", "Évora, 08 (PT)"),
    ("zürich, zh", "Zürich, ZH (CH)"),
])
def test_a_typed_region_or_country_finds_its_place_first(typed, label):
    assert _labels(typed)[0] == label, (typed, _labels(typed))


def test_every_option_holds_every_qualifier():
    """Each later comma part narrows: Paris, TN is Paris, Tennessee alone,
    and a qualifier no Paris holds leaves nothing."""
    assert _labels("Paris, TN") == ["Paris, TN (US)"]
    in_us, in_france, in_minnesota = _labels("Paris, US"), _labels("Paris, France"), _labels("Saint Paul, Minnesota")
    assert set(in_us) >= {"Paris, TX (US)", "Paris, TN (US)"} and in_france[0] == "Paris, 11 (FR)"
    # a qualified complete name now lists its exact matches alone: Saint
    # Paul Park, once offered beside it, is not Saint Paul
    assert in_minnesota == ["Saint Paul, MN (US)"]
    assert [label for label in in_us if not label.endswith("(US)")] == []
    assert [label for label in in_france if not label.endswith("(FR)")] == []
    assert _labels("Paris, TN, FR") == []
    assert _labels("Paris, Zzyzx") == [] and _labels("Saint Paul, MN (FR)") == []


def test_a_code_that_is_a_state_and_a_country_holds_for_both():
    labels = _labels("B, MN")
    # seats of government rank first now, so Mongolia's aimag seats fill the
    # twenty; Minnesota's places are found by their names (on the cities500
    # atlas Bloomington was among the twenty)
    assert len(labels) == 20 and "Bayanhongor, 02 (MN)" in labels       # Mongolia
    assert [label for label in labels if not label.endswith((", MN (US)", "(MN)"))] == []
    assert "Bloomington, MN (US)" in _labels("Bloomington, MN")          # Minnesota
    assert "Bayanhongor, 02 (MN)" in _labels("Bayanhongor, MN")


def test_a_qualifier_that_begins_two_countries_holds_for_both():
    labels = _labels("London, United")
    assert "London, ENG (GB)" in labels and "London, 08 (CA)" not in labels and "London, 08 (CA)" in _labels("London")
    assert [label for label in labels if label.endswith("(US)")]
    assert [label for label in labels if not label.endswith(("(GB)", "(US)", "(AE)"))] == []


def test_the_country_in_brackets_is_the_country_s_alone():
    """"(MN)" is Mongolia, never Minnesota: it is the label's country."""
    assert not [label for label in _labels("B (MN)") if label.endswith("(US)")]
    assert _labels("Saint Paul (MN)") == []


def test_an_empty_qualifier_narrows_nothing(atlas_matches):
    assert atlas_matches("Saint Paul,") == atlas_matches("Saint Paul")
    assert atlas_matches("St. Paul,") == atlas_matches("St. Paul")
    assert atlas_matches("Saint Paul, ") == atlas_matches("Saint Paul")
    assert list(atlas_matches("Paris,")[0].items()) == list(_as_before("Paris").items())


@pytest.mark.parametrize("typed", ["Paris, %", "Paris, _", "Paris, T%", "Paris, T_", "Paris, \\", "Pa%, TN",
                                   "Par_s, TN", "%, TN", "_, MN", "St. P%", "St. Pa_l", "St. %, MN", "Saint Paul, %N",
                                   "Saint Paul, M_", "Paris (_S)", "Paris (%)"])
def test_a_wildcard_in_either_part_is_text(atlas_matches, typed):
    options, why = atlas_matches(typed)
    assert options is None and why == NO_MATCH, (typed, options)


def test_a_name_holding_a_comma_is_still_found_by_its_whole_text():
    """Its whole text is one look, beside the narrowed looks:
    Misato, Saitama is still Misato; and a comma name whose later parts are
    no region or country is reached by its whole text alone."""
    assert _labels("Misato, Saitama")[0] == "Misato, Saitama, 34 (JP)"
    # bare, Misato now finds the places of that name or an other name
    # beginning with it, Saitama's first: these twenty, in this order
    assert _labels("Misato") == [
        "Misato, Saitama, 34 (JP)", "Kogota-ekimae, 24 (JP)", "Samata, 21 (JP)", "Ko-bae, 25 (JP)", "Obara, 36 (JP)",
        "Tenma, 29 (JP)", "Takashimachō-sanrimen, 27 (JP)", "Misato, 47 (JP)", "Misato, 16 (CD)", "Misato, 12 (JP)",
        "Misato, 12 (JP)", "Misato, 12 (JP)", "Misato, 12 (JP)", "Misatochō-kitanagano, 23 (JP)",
        "Misatomachi-wadayama, 10 (JP)", "Misatomachi-nakano, 10 (JP)", "Misatochō-iono, 23 (JP)",
        "Misatochō-ashizaka, 23 (JP)", "Misatochō-katsurahata, 23 (JP)", "Misatochō-misato, 23 (JP)"]
    assert "Ryasno, Рясно, Расна, 06 (BY)" in _labels("Ryasno, Рясно, Расна")
    assert "Brgy. Tinigao, Kalibo, 06 (PH)" in _labels("Brgy. Tinigao, Kalibo")
    assert "Church End, Eversholt, ENG (GB)" in _labels("Church End, Eversholt")
    assert "Mianzhu, Deyang, Sichuan, 32 (CN)" in _labels("Mianzhu, Deyang, Sichuan")


def test_a_label_of_a_name_holding_commas_typed_back_finds_it():
    for label in ("Mianzhu, Deyang, Sichuan, 32 (CN)", "Ryasno, Рясно, Расна, 06 (BY)",
                  "Church End, Eversholt, ENG (GB)", "Misato, Saitama, 34 (JP)"):
        assert _labels(label)[0] == label, (label, _labels(label))


def _search_rows(typed):
    import contextlib
    import time_zones
    with contextlib.closing(sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True)) as conn:
        return time_zones._atlas_search_matches(conn.cursor(), typed)


def _plain(spelling):
    """A spelling as this test compares it with the text typed: its small
    letters, a leading Saint, Sankt or St. (with or without its period, then
    a space or a hyphen) read as Saint and one space."""
    low = spelling.casefold()
    for form in ("saint", "sankt", "st.", "st"):
        if low == form or low.startswith((form + " ", form + "-")):
            rest = low[len(form):].lstrip(". -")
            return "saint " + rest if rest else "saint"
    return low


def test_the_options_are_at_most_twenty_the_most_populous_first_in_one_list():
    """The order read off the places themselves, not through the search's
    own ranking: a place one of whose names is the text typed first, then a
    seat of government (a capital or a first-order seat by GeoNames' feature
    code), then the larger population."""
    with contextlib.closing(sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True)) as conn:
        def spellings(gid):
            return {s for (s,) in conn.execute("SELECT name FROM names WHERE geonameid = ? UNION "
                                               "SELECT name FROM places WHERE geonameid = ? UNION "
                                               "SELECT ascii_name FROM places WHERE geonameid = ?",
                                               (gid, gid, gid)) if s}

        for typed in ("St. Paul", "Saint", "St.", "S, US", "a, b", "Saint Paul, MN (US)", "London, United"):
            rows = _rows(typed)
            # a qualified complete name lists every exact match: London in the
            # United Kingdom, the United States and the United Arab Emirates, 23
            assert len(rows) == {"London, United": 23, "Saint Paul, MN (US)": 1}.get(typed, 20), typed
            assert len(set(rows)) == len(rows), typed
            name = _plain(typed.split(",")[0].split(" (")[0].strip())
            # the places by their GeoNames ids (the search's rows, in the options' order)
            found = _search_rows(typed)
            assert [(r["name"], r["admin1"], r["country"], r["lat"], r["lon"]) for r in found] == rows, typed
            keys = []
            for r in found:
                code, pop = conn.execute("SELECT feature_code, population FROM places WHERE geonameid = ?",
                                         (r["geonameid"],)).fetchone()
                keys.append((any(_plain(s) == name for s in spellings(r["geonameid"])),
                             code in ("PPLC", "PPLG", "PPLA"), pop))
            assert keys == sorted(keys, reverse=True), (typed, keys)
    assert len(_rows("St.")) == 20 and len(_rows("S, US")) == 20


def test_the_region_and_country_tables_hold_every_place():
    """The qualifiers are read from the atlas's own tables of countries and
    regions: every place's country and region is in them, and the codes are
    ASCII."""
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        assert conn.execute("""SELECT count(*) FROM cities c WHERE NOT EXISTS
                               (SELECT 1 FROM admin1_names a WHERE a.country = c.country AND a.admin1 = c.admin1)
                               OR NOT EXISTS (SELECT 1 FROM country_names n WHERE n.country = c.country)
                            """).fetchone() == (0,)
        codes = [code for (code,) in conn.execute("SELECT admin1 FROM admin1_names UNION SELECT country FROM country_names")]
    assert len(codes) > 800
    assert [code for code in codes if not (code.isascii() and code == code.strip())] == []


# --- the labels the app offers, typed back ------------------------------------------

def test_a_seeded_sample_of_labels_typed_back_each_finds_its_own_place(atlas_matches):
    """200 places drawn with a fixed seed, each label as the app writes it
    (without the coordinate suffix a repeated label is given): typed back,
    it offers its own place, unless twenty places or more share its name's
    start, region and country, when the twenty offered are all of them."""
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT name, admin1, country, lat, lon FROM cities ORDER BY id").fetchall()
    sample = random.Random(2210).sample(rows, 200)
    assert len(sample) == 200
    lost, reached = [], 0
    for name, admin1, country, lat, lon in sample:
        region = (admin1 or "").strip()
        label = f"{name}, {region} ({country})" if region else f"{name} ({country})"
        options, why = atlas_matches(label)
        assert why is None, label
        if (lat, lon) in options.values():
            reached += 1
            continue
        crowded = len(options) == 20 and all(option.startswith(name) and option.split(" [")[0].endswith(
            f", {region} ({country})" if region else f" ({country})") for option in options)
        if not crowded:
            lost.append(label)
    assert not lost, lost
    assert reached >= 198, reached


# --- the box ---------------------------------------------------------------------

def _picker_options(at):
    pickers = [s for s in at.sidebar.selectbox if s.label == PICKER]
    return pickers[0].options if pickers else []


def _city_app(text):
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = text
    return at.run()


def test_st_paul_mn_in_the_city_box_offers_saint_paul_and_casts_there():
    at = _city_app("St. Paul, MN")
    assert_no_exception(at, "St. Paul, MN")
    assert _picker_options(at)[0] == "Saint Paul, MN (US)"
    assert NO_MATCH not in [w.value for w in at.sidebar.warning]
    assert [s.value for s in at.sidebar.success][0].startswith("**Saint Paul, MN (US)**")
    assert (at.session_state["_resolved_lat"], at.session_state["_resolved_lon"]) == _place("Saint Paul", "MN", "US")


@pytest.mark.parametrize("typed, label, name, admin1, country", [
    ("New York, NY", "New York City, NY (US)", "New York City", "NY", "US"),
    ("Florence,", "Florence, 16 (IT)", "Florence", "16", "IT"),
    # not a pair: "nan" is no number the box reads, and Nan is a town of Nan
    # province, in Thailand
    ("nan, nan", "Nan, 04 (TH)", "Nan", "04", "TH"),
])
def test_texts_that_found_nothing_now_find_their_place_and_cast_there(typed, label, name, admin1, country):
    at = _city_app(typed)
    assert_no_exception(at, typed)
    assert _picker_options(at)[0] == label
    assert (at.session_state["_resolved_lat"], at.session_state["_resolved_lon"]) == _place(name, admin1, country)


def test_a_latitude_longitude_pair_is_the_box_s_and_is_never_split():
    """The box reads a typed pair before any lookup; a pair is never taken
    for a name and a qualifier."""
    at = _city_app("44.9537, -93.09")
    assert_no_exception(at, "pair")
    assert _picker_options(at) == []
    assert (at.session_state["_resolved_lat"], at.session_state["_resolved_lon"]) == (44.9537, -93.09)
    from conftest import ui_source
    tree = ast.parse(ui_source())
    box = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
               and ast.unparse(n.test) == "_typed" and "_atlas_matches" in ast.unparse(n))
    # the lookup sits only under the branch a parsed pair did not take
    assert "_atlas_matches" not in ast.unparse(box.body)
