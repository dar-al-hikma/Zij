"""The engine wording, second pass: page text that says what the sentences say.

1. The Configurations connection help cites Sahl's Introduction Ch. 3 by name
   where it stands beside Gr. Intr. VII.5, 9-11: "(Sahl 10)" is the half-body
   rule in one sign, "(Sahl 9)" the full degree (Sahl I p. 53). The
   caption, and the Sources page's same sentence, say "this app's reading";
   the Motion help beside it names "Sahl 22".
4. The Days selector serves two methods: the small days from the revolution's
   point, the mighty days from the natal point profected (IX.7, 27). Its
   options name the point plainly; a house's cusp is given as the
   revolution's.
"""
import pytest

from conftest import assert_no_exception, find_page_widget, find_table, make_app, ui_source


# --- 1. the connection help and caption ------------------------------------

@pytest.fixture(scope="module")
def configurations():
    at = make_app(page="configurations")
    at.run()
    assert_no_exception(at, "configurations")
    return at


def test_the_connection_help_names_sahl_beside_the_great_introduction(configurations):
    import json
    config = json.loads(find_table(configurations, "Aspects, aversions and connections").proto.columns)
    help_ = config["Connection"]["help"]
    assert ("less than half of its body in one sign (Sahl 10), or a full degree across signs (Sahl 9)."
            in help_), help_
    assert "(Sahl 7; Gr. Intr. VII.5, 9-11)" in help_
    assert "(10)" not in help_ and "(9)" not in help_


def test_the_caption_says_this_apps_reading(configurations):
    captions = [c.value for c in configurations.main.caption]
    assert any(c.startswith("Under this app's reading of Sahl, the Sun's 15° counts") for c in captions), captions


def test_no_page_says_our_reading():
    src = ui_source()
    assert "our reading" not in src.lower()
    assert src.count("Under this app's reading of Sahl, the Sun's 15° counts for same-sign application") == 2


def test_the_motion_help_names_sahl_22(configurations):
    import json
    config = json.loads(find_table(configurations, "Aspects, aversions and connections").proto.columns)
    assert "Recession in Sahl 22 names the light planet in more degrees." in config["Motion"]["help"]


# --- 4. the Days selector's options ----------------------------------------

@pytest.fixture(scope="module")
def day_point_box():
    at = make_app(page="days")
    at.run(timeout=300)
    assert_no_exception(at, "days")
    return find_page_widget(at, "selectbox", "Also direct, for the small days")


def test_the_day_point_options_name_the_point_plainly(day_point_box):
    options = list(day_point_box.options)
    assert options[0] == "the Ascendant (the tables below)"
    assert not any(o.startswith("the revolution's") for o in options), options
    for planet in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        assert planet in options, options


def test_a_house_option_gives_the_revolution_cusp(day_point_box):
    houses = [o for o in day_point_box.options if o.startswith("house ")]
    assert len(houses) == 12, houses
    assert all(" (revolution cusp " in o and "(cusp " not in o for o in houses), houses
    assert houses[9].startswith("house 10 (revolution cusp ")
