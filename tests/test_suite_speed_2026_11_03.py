"""What keeps the whole suite short without dropping a test.

* pytest.ini asks xdist for worksteal scheduling, so an idle worker takes tests from a
  busy one instead of waiting while one worker finishes a long block.
* conftest.py gives a test process one TimezoneFinder: the app builds one on every run,
  which is about half of a render, and a finder only reads its data.
"""
import configparser
import re

from timezonefinder import TimezoneFinder

from conftest import make_app, assert_no_exception, EXECUTABLE_DIR


def test_the_ini_asks_xdist_for_worksteal_scheduling():
    ini = configparser.ConfigParser()
    ini.read(EXECUTABLE_DIR / "pytest.ini", encoding="utf-8")
    addopts = ini["pytest"]["addopts"]
    assert re.search(r"(?:^|\s)--dist worksteal(?:\s|$)", addopts), addopts
    assert "-p skip_guard" in addopts, addopts


def test_plain_constructions_in_a_test_process_give_one_finder():
    assert TimezoneFinder() is TimezoneFinder()


def test_a_subclass_is_built_as_ever():
    class Mine(TimezoneFinder):
        pass

    mine = Mine()
    assert type(mine) is Mine
    assert mine is not TimezoneFinder()


def test_the_one_finder_answers_as_a_finder_does():
    finder = TimezoneFinder()
    assert finder.timezone_at(lng=11.2463, lat=43.7792) == "Europe/Rome"
    assert finder.timezone_at(lng=-0.1278, lat=51.5074) == "Europe/London"


def test_a_page_renders_with_the_shared_finder():
    at = make_app(page="chart").run()
    assert_no_exception(at, "chart under the shared finder")
    again = make_app(page="dignities").run()
    assert_no_exception(again, "dignities under the shared finder")
