"""The Sky page: its pinned files, the join behind its rows, its colours and words, and its
list and record, on the real grown catalogue. The host's order of calls is in
tests/js/sky_host.test.mjs."""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import shipped_modules  # noqa: E402
import engine  # noqa: E402
import house_style  # noqa: E402
import sky  # noqa: E402
from conftest import component_mounts, make_app  # noqa: E402

PINNED = {
    "sphere-world.js": (32870, "0f4f551a571883111c0cf07af1cb3d5aa1ab62f664f86dd00e4cd30b12faefa6"),
    "tower-view.js": (74213, "5ee767191b355f06ca4754d1a0b10205c4010d9a36111f03ddbccc5fae77ec1b"),
    "figures.js": (20189, "0505e3a4046a68cddffa76f1339cac04398cc1b0edfead1f33139e3f66a76645"),
    "tower-physical.js": (92114, "760b8c0e2edfbc26df573fd7eec2085a792b3e8b3dcf298900b705836da23d5c"),
    "three.r128.js": (603546, "3d43dd920529d6afb363357a559ee32c7916562081bb90349dc850295338da36"),
}
J2000 = 2451545.0
LISTS = {"Sahl's 28": 28, "Curated List": 177, "Significant Stars": 486, "Full Catalogue": 1852}


def _places(jd=J2000):
    stars = engine.fixed_star_places(jd)[0]
    return stars, sky.sources(stars, engine.fixed_star_identity, engine.fixed_star_label, engine.longitude_at_whole_minute, lambda star: None)


def _separation(ra1, dec1, ra2, dec2):
    ra1, dec1, ra2, dec2 = map(math.radians, (ra1, dec1, ra2, dec2))
    half = math.sin((dec2 - dec1) / 2) ** 2 + math.cos(dec1) * math.cos(dec2) * math.sin((ra2 - ra1) / 2) ** 2
    return math.degrees(2 * math.asin(math.sqrt(half)))


def _sky_page(**kwargs):
    at = make_app(page="sky", **kwargs).run()
    assert not at.exception, at.exception
    return at


def _envelope(at):
    mounts = component_mounts(at.main, "fixed_star_sky")
    assert len(mounts) == 1
    return json.loads(mounts[0].proto.json)


@pytest.mark.parametrize("name", PINNED)
def test_each_vendored_file_is_the_pinned_one(name):
    raw = (ROOT / "vendor" / name).read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == PINNED[name]
    assert sky.PINS[name] == PINNED[name][1]


def test_vendor_holds_those_five_and_no_other():
    assert {path.name for path in (ROOT / "vendor").iterdir()} == set(PINNED)


def test_a_changed_byte_takes_the_page_down_and_not_the_app(tmp_path, monkeypatch):
    assert sky.AVAILABLE
    monkeypatch.setitem(sky.PINS, "figures.js", "0" * 64)
    with pytest.raises(ValueError):
        sky._load()
    # What app.py does with it.
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'if sky.AVAILABLE else None' in app and '"The sky is unavailable."' in app


def test_the_bundle_is_the_four_files_byte_for_byte_and_never_the_table():
    at = 0
    for name in ("three.r128.js", "sphere-world.js", "tower-view.js", "figures.js"):
        text = (ROOT / "vendor" / name).read_text(encoding="utf-8")
        found = sky.JS.find(text, at)
        assert found >= at, name
        at = found + len(text)
    assert sky.JS.endswith((ROOT / "sky_host.js").read_text(encoding="utf-8"))
    assert "TowerPhysical" not in sky.JS and '"I/239"' not in sky.JS


def test_each_row_of_the_table_has_one_star_and_the_rows_are_the_catalogues():
    stars, places = _places()
    assert len(stars) == 1852 and len(places["stars"]) == 1845 and len(places["objects"]) == 7
    table = {f"hip:{row[0]}" for row in sky.PHYSICAL["stars"]} | {row[0] for row in sky.PHYSICAL["objects"]}
    assert set(sky.SOURCE_IDS) == table and len(table) == 1686
    assert len(set(sky.SOURCE_IDS.values())) == 1686
    ids = {row["id"] for row in places["stars"] + places["objects"]}
    assert table <= ids and len(ids) == 1852
    assert sum(not number.startswith(("hip:", "ngc:", "messier:", "melotte:")) for number in ids) == 166


def test_each_row_takes_the_engines_place_and_no_other():
    stars, places = _places(2174111.07)
    by_id = {row["id"]: row for row in places["stars"] + places["objects"]}
    for star in stars:
        row = by_id[places["ids"][engine.fixed_star_identity(star)]]
        assert (row["ra"], row["dec"]) == (star.right_ascension, star.declination)
        assert row["vmag"] == star.magnitude or (row["vmag"] is None and star.magnitude is None)
        assert places["back"][row["id"]] == engine.fixed_star_identity(star)


def test_the_join_holds_by_position_at_j2000():
    """Against the engine's apparent places at J2000, so never the tool's own reading: every
    row but the four hand-matched objects lies within what aberration and a 20 arcsecond
    join can part them."""
    stars, places = _places()
    by_id = {row["id"]: row for row in places["stars"] + places["objects"]}
    far = {}
    for number, row in sky._TABLE.items():
        far[number] = _separation(row["ra"], row["dec"], by_id[number]["ra"], by_id[number]["dec"]) * 3600
    allowed = {"messier:44", "messier:6", "messier:7", "ngc:869"}
    assert {number for number, apart in far.items() if apart > 60} <= allowed
    assert len(far) == 1686


def test_eta_ori_stands_once_at_the_physical_rows_place_and_the_figure_takes_it():
    _, places = _places()
    ids = {row["id"] for row in places["stars"]}
    assert "hip:25281" in ids and places["names"]["hip:25281"].startswith("η Ori")
    assert not [name for name in places["names"].values() if name.startswith("Ensis")]
    assert sum("Ori" in name and name.startswith("η") for name in places["names"].values()) == 1
    orion = next(figure for figure in sky.FIGURES if figure["key"] == "orion")
    assert not any(number.startswith("zij:") for line in orion["lines"] for number in line)


@pytest.mark.parametrize("name", ["Melotte 111", "NGC 6441", "κ Cap", "τ Cap", "NGC 884", "φ² Ori", "ν² Sgr"])
def test_the_star_groups_objects_stand_in_the_sky(name):
    _, places = _places()
    named = [number for number, label in places["names"].items() if name in label]
    assert named, name
    rows = {row["id"]: row for row in places["stars"] + places["objects"]}
    assert all(rows[number]["ra"] is not None for number in named)


def test_every_figure_line_names_a_star_the_engine_places():
    _, places = _places()
    ids = {row["id"] for row in places["stars"] + places["objects"]}
    assert len(sky.FIGURES) == 49
    for figure in sky.FIGURES:
        for line in figure["lines"] + figure["extLines"]:
            assert set(line) <= ids, figure["key"]


@pytest.mark.parametrize("jd", [J2000, 2174111.07, 1000000.5])
def test_a_figures_name_stands_where_its_stars_went(jd):
    """Carried by the rotation of the engine's own places: its distance to its figure's first
    star holds, near a pole too, but for that star's own motion (Sirius, some 0.2 degrees by 1240)."""
    _, places = _places(jd)
    by_id = {row["id"]: row for row in places["stars"]}
    for figure in sky.FIGURES:
        first = figure["lines"][0][0]
        then = _separation(figure["label"]["ra"], figure["label"]["dec"], sky._TABLE[first]["ra"], sky._TABLE[first]["dec"])
        now = _separation(places["anchors"][figure["key"]]["ra"], places["anchors"][figure["key"]]["dec"], by_id[first]["ra"], by_id[first]["dec"])
        assert abs(then - now) < (0.3 if jd > 2000000 else 1.5), figure["key"]


def test_every_colour_comes_from_the_house_style():
    dark = house_style.WHEEL_PALETTES["dark"]
    for theme in ("light", "dark", None):
        palette = sky.palette(theme)
        for name, colour in palette["colours"].items():
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", colour), name
    assert sky.palette("dark")["background"] == dark["bg"]
    assert sky.palette("light")["background"] == dark["panel"]
    assert sky.palette("dark")["colours"]["star"] == dark["ink"]
    for name in ("sky_host.js", "sky_host.css"):
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b|0x[0-9A-Fa-f]{6}|rgba?\(", (ROOT / name).read_text(encoding="utf-8")), name
    assert not re.search(r"#[0-9A-Fa-f]{6}", (ROOT / "sky.py").read_text(encoding="utf-8"))


def test_the_sky_is_dark_under_both_themes():
    def light(colour):
        r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return .2126 * r + .7152 * g + .0722 * b
    for theme in ("light", "dark"):
        palette = sky.palette(theme)
        assert light(palette["background"]) < .1
        assert light(palette["colours"]["star"]) > .6
        # Nothing of the page's choice but the ground it stands on; markers stay fixed.
        assert palette["colours"] == sky.palette("dark")["colours"]


def _words():
    return json.loads((ROOT / "sky_words.json").read_text(encoding="utf-8"))


def test_every_key_the_view_asks_for_has_words():
    words = _words()
    text = (ROOT / "vendor" / "tower-view.js").read_text(encoding="utf-8") + (ROOT / "vendor" / "sphere-world.js").read_text(encoding="utf-8")
    asked = set(re.findall(r'''(?:utext|putRow\(dl,|T|statusText)\(?\s*"((?:m4|lbl|sphere|chart|tw)\.[A-Za-z0-9_.]+)"''', text))
    asked = {key for key in asked if not key.endswith(".")}
    assert len(asked) > 40
    assert asked <= set(words), asked - set(words)
    for key, value in words.items():
        assert value != key


def test_every_figure_has_its_name():
    words = _words()
    assert all(words.get(f"figure.{figure['key']}") for figure in sky.FIGURES)


def test_the_words_on_the_page_say_axes_and_name_nothing_of_the_build():
    words = _words()
    assert words["m4.angles"] == "Stars on the axes" and "axis" in words["m4.longitudeCriterion"]
    shown = {key: value for key, value in words.items() if not key.startswith(("m4.form", "m4.status", "m4.co", "m4.foot"))}
    for key, value in shown.items():
        assert not re.search(r"\b(19|20)\d\d\b|\.py\b|\.js\b|Tower|\bbuild\b|\blane\b", value), key
        assert "angle" not in value.casefold() or key.startswith("m4.angle"), key


def test_the_page_opens_on_the_curated_list_and_hands_over_the_catalogue():
    at = _sky_page()
    assert [h.value for h in at.main.header] == ["The Sky"]
    control = next(group for group in at.get("button_group") if group.key == "_sky_population")
    assert control.value == "Curated List" and list(control.options) == list(LISTS)
    data = _envelope(at)
    assert len(data["stars"]) + len(data["objects"]) == 1852
    assert len(data["shown"]) == 177
    assert data["population"] == "Curated List" and data["mode"] == "tower" and data["turn"] is None
    view = next(group for group in at.get("button_group") if group.key == "_sky_view")
    assert view.value == "Within" and list(view.options) == ["Outside", "Within"], "opens Within; the order stands"
    assert data["descriptor"]["mode"] == "apparentOfDate"
    assert len(data["anchors"]) == 49


@pytest.mark.parametrize("name,count", LISTS.items())
def test_the_sky_follows_its_control(name, count):
    at = _sky_page()
    next(group for group in at.get("button_group") if group.key == "_sky_population").set_value(name).run()
    assert not at.exception
    assert len(_envelope(at)["shown"]) == count


def test_one_stored_list_holds_on_both_pages():
    from streamlit.util import calc_hash
    at = _sky_page()
    next(group for group in at.get("button_group") if group.key == "_sky_population").set_value("Significant Stars").run()
    at._page_hash = calc_hash("fixed-stars")
    at.run()
    assert not at.exception
    group = next(group for group in at.get("button_group") if group.key == "_fixed_stars_population")
    assert group.value == "Significant Stars"
    group.set_value("Sahl's 28").run()
    at._page_hash = calc_hash("sky")
    at.run()
    assert not at.exception
    assert next(group for group in at.get("button_group") if group.key == "_sky_population").value == "Sahl's 28"
    assert len(_envelope(at)["shown"]) == 28


def test_the_axes_rows_are_the_tabs_in_the_tabs_own_words():
    at = _sky_page(date="1240-05-23")
    data = _envelope(at)
    names = data["names"]
    stars = engine.fixed_star_places(data["descriptor"]["epoch"])[0]
    assert data["angles"]["status"] == "ok"
    assert {"asc", "dsc", "mc", "ic"} <= set(data["angles"])
    rows = [row for word in ("asc", "dsc", "mc", "ic") for row in data["angles"][word]["byLongitude"]]
    assert all(re.fullmatch(r"[+−]\d\d° \d\d′", row["dlon"]) for row in rows)
    assert all(row["id"] in names for row in rows)
    assert len(stars) == 1852


def test_a_found_star_turns_the_sky_once_and_a_return_turns_nothing():
    at = _sky_page()
    data = _envelope(at)
    at.session_state["_fixed_stars_open"] = "Sirius"
    at.run()
    assert not at.exception
    data = _envelope(at)
    assert data["turn"]["id"] in data["names"] and data["names"][data["turn"]["id"]].startswith("Sirius")
    at.run()
    assert _envelope(at)["turn"] is None


def test_the_finders_answer_reaches_the_sky_only_in_the_run_that_opens_a_record():
    at = _sky_page()
    at.text_input(key="_fixed_stars_query").set_value("Spica")
    next(b for b in at.button if b.label == "Find").click().run()
    assert not at.exception
    data = _envelope(at)
    assert data["names"][data["turn"]["id"]].startswith("Spica"), "one hit"
    at.run()
    assert _envelope(at)["turn"] is None
    at.text_input(key="_fixed_stars_query").set_value("Algedi")
    next(b for b in at.button if b.label == "Find").click().run()
    assert not at.exception
    assert _envelope(at)["turn"] is None, "a choice waiting opens nothing"
    at.button(key="_fixed_stars_choice_open").click().run()
    assert not at.exception
    data = _envelope(at)
    assert data["turn"]["id"] in data["names"], "its own Open record"
    at.run()
    assert _envelope(at)["turn"] is None


def test_the_figures_word_is_the_books_spelling():
    assert _words()["figure.capricornus"] == "Capricorn"
    assert _words()["figure.leo-coma"] == "Leo Coma"


def test_no_moment_goes_into_a_url_and_no_second_window_opens():
    source = (ROOT / "sky.py").read_text(encoding="utf-8") + (ROOT / "sky_host.js").read_text(encoding="utf-8")
    assert "query_params" not in source and "window.open" not in source and "localStorage" not in source and "sessionStorage" not in source
    assert "fetch(" not in (ROOT / "sky_host.js").read_text(encoding="utf-8")


def test_the_view_keeps_no_zoom_hint():
    assert "sourceZoomHint" not in (ROOT / "sky_host.js").read_text(encoding="utf-8")


def test_a_refused_chart_draws_no_sky():
    at = _sky_page()
    assert component_mounts(at.main, "fixed_star_sky")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = ""
    at.run()
    assert not at.exception
    assert not component_mounts(at.main, "fixed_star_sky")


def test_the_download_carries_the_sky_and_its_notices(tmp_path):
    built = shipped_modules.run_spec(ROOT, toc={"pure": [], "binaries": [], "datas": []}, workpath=tmp_path)
    held = {(Path(source).as_posix(), dest) for source, dest in built["datas"]}
    for name in PINNED:
        assert (f"vendor/{name}", "vendor") in held
    for name in ("sky.py", "sky_host.js", "sky_host.css", "sky_words.json"):
        assert (name, ".") in held
    assert ("data/sky_source_ids.tsv", "data") in held and ("ephe/sefstars_added.txt", "ephe") in held
    for name in ("SKY_NOTICES.txt", "three-MIT.txt"):
        assert (f"licenses/{name}", "licenses") in held
    notices = Path(built["toc_datas"][-1][1]).read_text(encoding="utf-8")
    assert "ephe/sefstars_added.txt" in notices and "CC-BY-NC-3.0 IGO" in notices and "Olaf Frohn" in notices


def test_the_notices_keep_the_data_apart_from_the_programs_licence():
    text = (ROOT / "licenses" / "SKY_NOTICES.txt").read_text(encoding="utf-8")
    head, data = text.split("vendor/tower-physical.js and ephe/sefstars_added.txt")
    assert "Dār al-Ḥikma" in head and "GNU Affero" in head
    assert "Not under this program's licence" in data and "GNU Affero" not in data and "AGPL" not in data
    assert "Used under these terms, with attribution and this notice." in " ".join(data.split())
    assert "Olaf Frohn" in (ROOT / "vendor" / "figures.js").read_text(encoding="utf-8")[:60] and "Olaf Frohn" in head
    assert "Permission is hereby granted, free of charge" in (ROOT / "licenses" / "three-MIT.txt").read_text(encoding="utf-8")


def test_the_canvas_takes_its_box_whatever_the_screens_ratio():
    """The world sizes the canvas's backing store by the ratio and leaves its shown
    size to the page, so without this rule a scaled display draws the sphere past
    the box's edge. What it looks like, only a browser sees."""
    css = (ROOT / "sky_host.css").read_text(encoding="utf-8")
    rule = re.search(r"\.zs-sky>canvas\{([^}]*)\}", css)
    assert rule, "the sky's canvas has no rule of its own"
    held = dict(part.split(":") for part in rule.group(1).split(";"))
    assert held == {"display": "block", "width": "100%", "height": "100%"}
    assert 'renderer.setSize(w,h,false)' in (ROOT / "vendor" / "sphere-world.js").read_text(encoding="utf-8")


# --- The second stage: its height and its place on the bar ---------------------------------------

def _style_rule(selector):
    style = house_style.PAGE_STYLE
    assert style.count(selector + "{") == 1, selector
    start = style.index(selector + "{") + len(selector) + 1
    return style[start:style.index("}", start)]


SKY_ROW = ".st-key-zij-sky-controls"


def _keys(block):
    keys = set()
    for child in getattr(block, "children", {}).values():
        keys |= _keys(child) | {getattr(child, "key", None)}
    return keys - {None}


def test_the_sky_alone_gives_up_its_padding_and_its_heading_by_its_own_row():
    held = f'[data-testid="stMainBlockContainer"]:has({SKY_ROW})'
    assert _style_rule(held) == "padding-top:76px;"
    hidden = _style_rule(f'[data-testid="stMain"]:has({SKY_ROW}) :has(>.st-key-zij-sky-heading)')
    # Hidden and not removed: the outline still reads it, and it takes no room.
    assert "position:absolute" in hidden and "display:none" not in hidden and "visibility" not in hidden
    # Nothing but those two rules leans on the row, so no other page has any way to move.
    assert house_style.PAGE_STYLE.count(SKY_ROW) == 2
    assert house_style.PAGE_STYLE.count("sky-heading") == 1


def test_the_page_keeps_its_row_and_heading_under_the_keys_the_stylesheet_names():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    body = source[source.index("def page_sky():"):source.index("def page_timing():")]
    assert 'key="zij-sky-heading"' in body and 'key="zij-sky-controls"' in body
    assert body.index('st.header("The Sky")') < body.index('key="zij-sky-controls"')


def test_a_refused_chart_keeps_its_heading_since_it_has_no_row():
    """The stylesheet hides the heading only where the row stands: a refused chart draws none."""
    at = _sky_page()
    assert _keys(at.main) >= {"zij-sky-heading", "zij-sky-controls"}
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = ""
    at.run()
    assert not at.exception
    assert [h.value for h in at.main.header] == ["The Sky"]
    assert "zij-sky-controls" not in _keys(at.main)


def test_the_plain_link_stands_before_reference_and_reads_as_the_sections_do():
    nav = '[data-testid="stTopNav"]'
    assert _style_rule(f'{nav}>:has([data-testid="stTopNavLinkContainer"])') == "order:3!important;"
    words = _style_rule('[data-testid="stTopNavSection"] :is(p,strong)')
    assert _style_rule('[data-testid="stTopNavLink"] p') == words
    assert "font-weight:400" in words


def test_the_rows_buttons_wrap_only_in_the_column_the_host_marks():
    source = (ROOT / "sky_host.js").read_text(encoding="utf-8")
    assert 'COLUMN_MARK = "data-zij-sky-column"' in source
    assert _style_rule('[data-zij-sky-column] [data-testid="stButtonGroup"] :has(>button)') == "flex-wrap:wrap;"
    assert "[data-testid=\"stButtonGroup\"]{" not in house_style.PAGE_STYLE


# --- One name on the map ---------------------------------------------------------------------------

def test_the_part_before_the_dot_is_the_engines_shown_name_for_every_star():
    """sky_host.js cuts a label at its first " · ": every star's first part must be its shown name."""
    stars = engine.fixed_star_places(2451545.0)[0]
    assert len(stars) == 1852
    for star in stars:
        label = engine.fixed_star_label(star)
        assert label.split(" · ")[0] == engine.fixed_star_shown_name(star), label
        assert label.count(" · ") <= 1, label


def test_the_list_and_the_record_keep_both_forms():
    places = sky.sources(engine.fixed_star_places(2451545.0)[0], engine.fixed_star_identity, engine.fixed_star_label,
                         engine.longitude_at_whole_minute, lambda star: None)
    assert "Spica · α Vir" in places["names"].values()
    source = (ROOT / "sky_host.js").read_text(encoding="utf-8")
    assert "twName: (id) => inst.names[id] || id" in source


def test_a_second_name_is_still_found():
    stars = engine.fixed_star_places(2451545.0)[0]
    spica = next(star for star in stars if star.name == "Spica")
    for name in spica.other_names:
        assert engine.fixed_star_identity(spica) in engine.fixed_star_find(name), name


def test_each_rows_degree_is_this_charts_latitude_and_obliquity():
    at = _sky_page()
    data = _envelope(at)
    latitude, obliquity = data["observer"]["lat"], data["observer"]["obl"]
    rows = data["stars"] + data["objects"]
    assert len(rows) == 1852
    for row in rows:
        degree = engine.fixed_star_co_rising_degree(row["ra"], row["dec"], latitude, obliquity)
        assert row["co"] == (None if degree is None else engine.longitude_at_whole_minute(degree)), row["id"]
    assert data["axes"]["asc"] == engine.longitude_at_whole_minute(data["axes"]["asc"])
    assert [speed["minutes"] for speed in data["speeds"]] == [1, 2, 10, 60, 104]


def test_the_page_passes_the_latitude_and_obliquity_to_the_cached_places():
    source = (Path(sky.__file__).parent / "app.py").read_text(encoding="utf-8")
    assert "def _sky_places(julian_day, latitude, obliquity):" in source
    assert "_sky_places(frame['julian_day'], frame['latitude'], frame['obliquity'])" in source


# --- The first view, the wrapped control, the close button and the labels' face ------------------

def test_the_view_opens_within_and_the_control_keeps_its_order():
    assert sky.FIRST_VIEW == "Within" and list(sky.VIEWS) == ["Outside", "Within"]


def test_a_long_control_in_the_column_stands_as_a_grid_of_whole_buttons():
    """Streamlit joins a control's buttons by sharing a border, which a wrapped row's first loses."""
    long_control = '[data-zij-sky-column] [role="radiogroup"]:has(>button:nth-of-type(3))'
    assert _style_rule(long_control) == "display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px;width:100%;"
    assert _style_rule(f"{long_control}>button") == "width:100%;margin:0;border-radius:0.375rem;"
    # Streamlit makes clear the edge a chosen button's neighbours share with it.
    rule = _style_rule(f"{long_control}>button:not([data-selected])")
    assert rule.startswith("border-color:light-dark(") and rule.endswith("!important;")


def test_the_close_button_stands_in_by_the_text_s_inset():
    """24px of the cross from the right, as the text from the left; the cross stands 4px within its button."""
    rule = _style_rule('[data-testid="stDialog"] [role="dialog"]>button[aria-label="Close"]')
    assert "width:18px;height:18px;margin:24px 20px -42px 0;" in rule


def test_the_labels_face_is_the_house_s_file_under_the_name_the_view_asks_for():
    source = (ROOT / "sky_host.js").read_text(encoding="utf-8")
    assert '"IBM Plex Sans Condensed", Arial' in (ROOT / "vendor" / "sphere-world.js").read_text(encoding="utf-8")
    assert 'new FontFace("IBM Plex Sans Condensed", "url(/zij-font/zij-interface-400.ttf)")' in source
    assert 'url = "/zij-font/zij-interface-400.ttf"' in (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "labelFaceState.then(go);" in source and "labelFace(() => {" in source
