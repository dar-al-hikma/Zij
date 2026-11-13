"""The page's colours: Light from a launch's first message until the reader presses
the one button, whatever the computer says, then Light or Dark, kept in the
preferences file, and shown by writing one palette into
both of Streamlit's theme sections.

The options are the server's, for the whole process, so what reads them runs in a
child of its own, through the real hold_the_server. A test here that moves them in
this process is put back by the fixture, or it would poison whatever this worker
runs next.

A browser alone shows: that the page applies a theme whose hash changed, how long
a press and a launch's first paint take, the colours a dialog or a popover
resolves, a canvas grid's colours, the button's look at rest and under a pointer,
what the button says at a session's first run on a dark computer, and that the
button is in view when a page opens. A run under AppTest has no launch's server
before it, so no choice is in force there and the browser's report decides."""
import ast
import json
import os
import re
import subprocess
import sys
import types

import pytest
from streamlit.testing.v1.element_tree import Block

from conftest import APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app, sync_engine_to_environment

SECTIONS = ("theme.light", "theme.dark", "theme.light.sidebar", "theme.dark.sidebar")
KEY = "page_theme"


@pytest.fixture(autouse=True)
def the_options_stand_as_they_were():
    import page_colours
    from streamlit import config

    assert page_colours.showing() is None
    before = {section: config.get_options_for_section(section) for section in SECTIONS}
    yield
    page_colours._parsed, page_colours._showing = None, None
    for section, options in before.items():
        for name, value in options.items():
            config.set_option(f"{section}.{name}", value)
    assert {section: config.get_options_for_section(section) for section in SECTIONS} == before


# --- What a launch does: a child holding the server, as both servers do --------------

LAUNCH = r"""
import json, os, sys
from unittest import mock
sys.path.insert(0, os.environ["ZIJ_TEST_TREE"])
import user_data
planted = os.environ.get("ZIJ_TEST_PLANT")
user_data.PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
if os.environ.get("ZIJ_TEST_FOLDER_IN_ITS_PLACE"):
    user_data.PREFERENCES_PATH.mkdir()
elif planted is not None:
    user_data.PREFERENCES_PATH.write_bytes(bytes.fromhex(planted))
before = user_data.PREFERENCES_PATH.read_bytes() if user_data.PREFERENCES_PATH.is_file() else None
reads = []
real_read = user_data._read_preferences_file
def read():
    reads.append(1)
    if os.environ.get("ZIJ_TEST_READ_RAISES"):
        raise RuntimeError("no read")
    return real_read()
user_data._read_preferences_file = read
if os.environ.get("ZIJ_TEST_ANOTHERS"):
    user_data._not_this_accounts = lambda folder: True

import server_limits
server_limits.hold_the_server(os.path.join(os.environ["ZIJ_TEST_TREE"], "app.py"))
from streamlit import config
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.runtime.app_session import AppSession
from google.protobuf.json_format import MessageToDict
import page_colours
written = []
real_set = config.set_option
def spy(key, value, *rest):
    written.append((key, value))
    return real_set(key, value, *rest)
config.set_option = spy

def message():
    "The first message of a run, as a session builds it."
    session = mock.MagicMock()
    session._script_data.name = session._script_data.main_script_path = ""
    session._pages_manager.main_script_path = session._pages_manager.main_script_hash = ""
    session.id = ""
    session._run_on_save = session._script_data.is_hello = False
    session._compute_skills_nudge_state.return_value = (False, "")
    new = AppSession._create_new_session_message(session, page_script_hash="")
    theme = new.new_session.custom_theme
    return {"light": MessageToDict(theme.light), "dark": MessageToDict(theme.dark)}

out = {"parses": []}
for step in os.environ.get("ZIJ_TEST_STEPS", "parse").split(","):
    if step == "parse":
        config.get_config_options(force_reparse=True)
    elif step == "config moved":
        moved = os.path.join(os.getcwd(), "moved.toml")
        with open(moved, "w", encoding="utf-8") as f:
            f.write('[theme.light]\nbackgroundColor = "#123456"\n[theme.dark]\nbackgroundColor = "#654321"\n')
        config.get_config_files = lambda name: [moved]
        config.get_config_options(force_reparse=True)
    else:
        page_colours.show(step)
    out["parses"].append({"step": step, "showing": page_colours.showing(), "message": message()})
out["reads"] = len(reads)
out["written_words"] = sorted({v for _, v in written if v in ("Light", "Dark", "System", "Purple")})
out["written_keys"] = sorted({k for k, _ in written})
out["writes"] = len(written)
out["engine_loaded"] = "engine" in sys.modules
out["ephemeris_loaded"] = "swisseph" in sys.modules
out["file_unmoved"] = before == (user_data.PREFERENCES_PATH.read_bytes() if user_data.PREFERENCES_PATH.is_file() else None)
print("RESULT " + json.dumps(out))
"""


def _launch(tmp_path, plant=None, steps="parse", **flags):
    """Run a launch in a child with its own data folder; what it found."""
    env = {name: value for name, value in os.environ.items()
           if name != "ALMUTEN_NO_PREFERENCES" and not name.upper().startswith("STREAMLIT_")}
    env.update(HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "xdg"), APPDATA=str(tmp_path / "appdata"),
               ZIJ_TEST_TREE=str(EXECUTABLE_DIR), ZIJ_TEST_STEPS=steps)
    if plant is not None:
        env["ZIJ_TEST_PLANT"] = plant.hex()
    env.update({name: value for name, value in flags.items()})
    done = subprocess.run([sys.executable, "-c", LAUNCH], env=env, cwd=str(tmp_path), capture_output=True,
                          text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    found = json.loads(next(line for line in done.stdout.splitlines() if line.startswith("RESULT "))[7:])
    assert all(key.startswith("theme.") for key in found["written_keys"]), found["written_keys"]
    return found


def _held(word):
    return json.dumps({"_page_colours": word, "_launches": 3}).encode("utf-8")


@pytest.fixture(scope="module")
def own_palettes(tmp_path_factory):
    """The two palettes the configuration gives, as a first message carries them:
    the light one from a saved Light, the dark one from a saved Dark."""
    held = {word: _launch(tmp_path_factory.mktemp(word), _held(word))["parses"][-1] for word in ("Light", "Dark")}
    assert [held[word]["showing"] for word in ("Light", "Dark")] == ["Light", "Dark"]
    palettes = {"light": held["Light"]["message"]["light"], "dark": held["Dark"]["message"]["dark"]}
    assert held["Light"]["message"]["dark"] == palettes["light"] and held["Dark"]["message"]["light"] == palettes["dark"]
    assert palettes["light"]["backgroundColor"] != palettes["dark"]["backgroundColor"]
    assert palettes["light"]["sidebar"]["backgroundColor"] != palettes["dark"]["sidebar"]["backgroundColor"]
    return palettes


def _light(own_palettes):
    return {"light": own_palettes["light"], "dark": own_palettes["light"]}


def test_a_first_launch_with_no_file_opens_light_whatever_the_computer_says(tmp_path, own_palettes):
    found = _launch(tmp_path)
    last = found["parses"][-1]
    assert last["showing"] == "Light" and found["reads"] == 1
    assert last["message"] == _light(own_palettes), "both palettes written light: no dark first paint"
    assert found["written_words"] == [] and found["file_unmoved"]


@pytest.mark.parametrize("word, kind", [("Light", "light"), ("Dark", "dark")])
def test_a_launch_s_first_message_carries_the_saved_palette_in_both_sections(tmp_path, own_palettes, word, kind):
    found = _launch(tmp_path, _held(word))
    last = found["parses"][-1]
    assert last["showing"] == word
    assert last["message"] == {"light": own_palettes[kind], "dark": own_palettes[kind]}
    assert found["file_unmoved"], "the read writes nothing"


def test_a_launch_and_a_press_write_theme_options_and_nothing_else(tmp_path):
    found = _launch(tmp_path, _held("Dark"), steps="parse,Light,Dark")
    assert found["writes"] and all(key.startswith("theme.") for key in found["written_keys"])


READ_AT_THE_PARSE = r"""
import os, sys
sys.path.insert(0, os.environ["ZIJ_TEST_TREE"])
import page_colours
assert "user_data" not in sys.modules
page_colours.show_the_saved_choice()
assert "user_data" in sys.modules
"""


def test_the_launch_read_makes_the_data_folder_and_moves_a_former_one(tmp_path, monkeypatch):
    """Importing the data layer at the parse does this, before the socket binds,
    as the app's first session would a moment later."""
    import user_data

    for name, value in (("HOME", tmp_path), ("XDG_DATA_HOME", tmp_path / "xdg"), ("APPDATA", tmp_path / "appdata")):
        monkeypatch.setenv(name, str(value))
    folder = user_data._user_data_path()
    former = folder.parent / user_data._LEGACY_APP_DIR_NAME
    former.mkdir(parents=True, mode=0o700)
    (former / "saved_charts.json").write_text("{}", encoding="utf-8")
    assert not folder.exists()
    env = {name: value for name, value in os.environ.items()
           if name != "ALMUTEN_NO_PREFERENCES" and not name.upper().startswith("STREAMLIT_")}
    env["ZIJ_TEST_TREE"] = str(EXECUTABLE_DIR)
    done = subprocess.run([sys.executable, "-c", READ_AT_THE_PARSE], env=env, cwd=str(tmp_path), capture_output=True,
                          text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    assert (folder / "saved_charts.json").is_file() and not former.exists()


def test_the_launch_read_does_not_load_the_engine_or_the_ephemeris(tmp_path):
    found = _launch(tmp_path, _held("Dark"))
    assert found["parses"][-1]["showing"] == "Dark"
    assert not found["engine_loaded"] and not found["ephemeris_loaded"]


@pytest.mark.parametrize("raw", [
    json.dumps({"_page_colours": value}).encode("utf-8")
    for value in ("Purple", "System", "dark", "DARK", " Dark", "", 1, True, None, ["Dark"], {"Dark": 1})
] + [b"{not json", b"\xff\xfe\x00", b"[]", b'"Dark"', b'{"_page_colours": "Dark", "_page_colours": "Dark"}'],
    ids=lambda raw: raw.decode("latin-1")[:32])
def test_anything_but_the_two_words_opens_light_and_writes_no_word(tmp_path, own_palettes, raw):
    found = _launch(tmp_path, raw)
    last = found["parses"][-1]
    assert last["showing"] == "Light" and last["message"] == _light(own_palettes)
    assert found["written_words"] == []
    assert found["file_unmoved"], "an unreadable file is the first run's to keep aside"


def test_a_file_with_a_byte_order_mark_is_read_as_a_load_reads_it(tmp_path):
    assert _launch(tmp_path, b"\xef\xbb\xbf" + _held("Dark"))["parses"][-1]["showing"] == "Dark"


def test_no_file_and_a_folder_at_its_name_open_light(tmp_path, own_palettes):
    for flags in ({}, {"ZIJ_TEST_FOLDER_IN_ITS_PLACE": "1"}):
        run = tmp_path / ("a" if flags else "b")
        run.mkdir()
        found = _launch(run, **flags)
        assert found["parses"][-1]["showing"] == "Light", flags
        assert found["parses"][-1]["message"] == _light(own_palettes) and found["written_words"] == [], flags


def test_a_read_that_raises_opens_light_not_the_saved_dark(tmp_path, own_palettes):
    found = _launch(tmp_path, _held("Dark"), ZIJ_TEST_READ_RAISES="1")
    assert found["reads"] == 1
    assert found["parses"][-1]["showing"] == "Light" and found["parses"][-1]["message"] == _light(own_palettes)


@pytest.mark.parametrize("flags", [{"ALMUTEN_NO_PREFERENCES": "1"}, {"ZIJ_TEST_ANOTHERS": "1"}],
                         ids=["preferences off", "another account's folder"])
def test_the_file_is_not_opened_past_the_checks_a_load_makes_first(tmp_path, own_palettes, flags):
    found = _launch(tmp_path, _held("Dark"), **flags)
    assert found["reads"] == 0, "the checks stand before the read"
    assert found["parses"][-1]["showing"] == "Light" and found["parses"][-1]["message"] == _light(own_palettes)


def test_the_same_checks_stand_in_load_preferences():
    """The launch read's two checks are the load's: if the load's change, read this."""
    import inspect

    import user_data

    assert ("if not preferences_enabled() or _not_this_accounts(PREFERENCES_PATH.parent):"
            in inspect.getsource(user_data.load_preferences))


def test_each_press_s_message_carries_its_palette_and_no_other_word_moves_it(tmp_path, own_palettes):
    found = _launch(tmp_path, steps="parse,Dark,Light,Purple,System,Dark")
    seen = [(step["step"], step["showing"], step["message"]) for step in found["parses"]]
    dark, light = {"light": own_palettes["dark"], "dark": own_palettes["dark"]}, _light(own_palettes)
    assert seen == [("parse", "Light", light), ("Dark", "Dark", dark), ("Light", "Light", light),
                    ("Purple", "Light", light), ("System", "Light", light), ("Dark", "Dark", dark)]
    assert found["written_words"] == [], "the choice's word is never an option's value"


def test_a_second_parse_takes_the_configuration_s_palettes_afresh(tmp_path, own_palettes):
    found = _launch(tmp_path, _held("Dark"), steps="parse,parse,Light,Dark")
    assert [step["showing"] for step in found["parses"]] == ["Dark", "Dark", "Light", "Dark"]
    assert found["parses"][2]["message"] == {"light": own_palettes["light"], "dark": own_palettes["light"]}
    assert found["parses"][3]["message"] == {"light": own_palettes["dark"], "dark": own_palettes["dark"]}


def test_palettes_parsed_anew_are_the_ones_a_choice_then_uses(tmp_path):
    found = _launch(tmp_path, _held("Dark"), steps="parse,config moved,Light")
    grounds = [(step["showing"], step["message"]["light"].get("backgroundColor"),
                step["message"]["dark"].get("backgroundColor")) for step in found["parses"][1:]]
    assert grounds == [("Dark", "#654321", "#654321"), ("Light", "#123456", "#123456")]


def test_a_parse_with_no_entry_writes_the_configuration_s_light_palette_in_both(tmp_path):
    found = _launch(tmp_path, steps="config moved")
    only = found["parses"][-1]
    assert only["showing"] == "Light" and found["written_words"] == []
    assert only["message"]["light"]["backgroundColor"] == "#123456"
    assert only["message"]["dark"]["backgroundColor"] == "#123456"


@pytest.mark.parametrize("name", ["on_config_parsed", "set_option", "get_options_for_section"])
def test_a_streamlit_without_a_name_this_needs_does_not_start(monkeypatch, name):
    import server_limits
    from streamlit import config

    monkeypatch.delattr(config, name)
    with pytest.raises(RuntimeError, match=f"config.{name}"):
        server_limits.hold_the_server(str(APP_PATH))


def test_the_server_s_guard_has_the_read_by_two_lines_and_no_launcher_a_flag():
    source = (EXECUTABLE_DIR / "server_limits.py").read_text(encoding="utf-8")
    hold = source[source.index("def hold_the_server"):]
    assert hold.count("page_colours") == 4 and "    import page_colours\n" in hold
    assert "    config.on_config_parsed(page_colours.show_the_saved_choice, force_connect=True)\n" in hold
    # The served page's cover asks which colours are in force, and nothing more.
    assert "opening.served(f.read(), page_colours.showing())" in hold
    assert '"""Five things' in hold
    for name in ("run_source.py", "desktop_launcher.py"):
        assert "page_colours" not in (EXECUTABLE_DIR / name).read_text(encoding="utf-8"), name


def test_the_module_touches_nothing_but_the_options_and_the_data_layer():
    source = (EXECUTABLE_DIR / "page_colours.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(f"{node.module}.{node.names[0].name}")
    assert imported == {"streamlit.config", "user_data", "logging"}    # logging: the one line a failed read writes
    assert "page_colours.py" in (EXECUTABLE_DIR / "source_modules.txt").read_text(encoding="utf-8").split()


# --- The file ------------------------------------------------------------------------

def test_the_file_holds_one_of_two_words_and_no_entry_means_light_at_a_launch():
    import engine
    import page_colours

    assert page_colours.PREFERENCE in engine.PREFERENCE_KEYS
    assert engine._preference_option_tuples()[page_colours.PREFERENCE] == (page_colours.LIGHT, page_colours.DARK)
    for word in ("Light", "Dark"):
        assert engine._loadable_preferences({page_colours.PREFERENCE: word}) == {page_colours.PREFERENCE: word}
    for value in ("System", "Purple", "dark", "", 1, True, None, ["Dark"], {"Dark": 1}):
        assert engine._loadable_preferences({page_colours.PREFERENCE: value}) == {}, value


def test_a_third_value_never_moves_an_option(monkeypatch):
    import page_colours
    from streamlit import config

    written = []
    real = config.set_option
    monkeypatch.setattr(config, "set_option", lambda key, value, *rest: written.append((key, value)))
    for value in ("Purple", "System", "dark", None, 1, ["Dark"], {"Dark": 1}):
        page_colours.show(value)
        assert page_colours.showing() is None
    assert not written
    monkeypatch.setattr(config, "set_option", real)
    page_colours.show("Dark")
    monkeypatch.setattr(config, "set_option", lambda key, value, *rest: written.append((key, value)))
    for value in ("Purple", "System", None, ["Light"]):
        page_colours.show(value)
        assert page_colours.showing() == "Dark"
    assert not written, "a choice once made holds"


@pytest.mark.parametrize("shown, target", [("dark", "Light"), ("light", "Dark"), (None, "Dark")])
def test_a_press_is_offered_the_other_colours(shown, target):
    import page_colours

    assert page_colours.offered(shown) == target
    assert target in page_colours.CHOICES and page_colours.CHOICES == ("Light", "Dark")


def test_the_module_has_no_third_choice():
    """A press writes Light or Dark and the page has no way back to no entry."""
    import page_colours

    assert not hasattr(page_colours, "SYSTEM")
    assert not re.search(r"\bSystem\b", (EXECUTABLE_DIR / "page_colours.py").read_text(encoding="utf-8"))
    source = APP_PATH.read_text(encoding="utf-8")
    assert "_forget(page_colours" not in source and "page_colours.SYSTEM" not in source


# --- The control ---------------------------------------------------------------------

@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    yield tmp_path / "Zij" / "preferences.json"
    monkeypatch.undo()
    sync_engine_to_environment()


def _control(at):
    return at.button(key=KEY)


def _file_word(path):
    return json.loads(path.read_text(encoding="utf-8")).get("_page_colours")


class _Reporting:
    """st.context, with a browser that reports `kind` as the colours it shows."""

    def __init__(self, real, kind):
        self._real, self.theme = real, types.SimpleNamespace(type=kind)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _emitted(monkeypatch):
    import streamlit

    calls, real = [], streamlit.html

    def capturing(body, *args, **kwargs):
        calls.append(body)
        return real(body, *args, **kwargs)

    monkeypatch.setattr(streamlit, "html", capturing)
    return calls


def test_the_button_stands_first_in_the_sidebar_and_names_where_a_press_goes():
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the button")
    first = next(node for node in at.sidebar if not isinstance(node, Block))
    assert first.type == "button" and first.key == KEY
    assert first.label == "Dark theme", "no browser in a test: nothing says the page is dark"
    assert not first.help and not first.proto.icon
    assert not [radio for radio in at.sidebar.radio if radio.key == "page_colours"]


def test_the_words_of_the_old_control_have_left_the_page():
    at = make_app(page="sources").run(timeout=300)
    text = "\n".join(str(node.proto) for node in at.sidebar if not isinstance(node, Block))
    assert not re.search(r"\bSystem\b|Page colours", text)
    assert "Page colours" not in APP_PATH.read_text(encoding="utf-8")


def _drawn_button():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    drawn = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and ast.unparse(node.value.func) == "_page_theme_slot.button"]
    assert len(drawn) == 1
    return tree, drawn[0].value


def test_the_button_is_drawn_at_the_module_s_level_with_its_target_in_hand():
    tree, call = _drawn_button()
    assert [ast.unparse(arg) for arg in call.args] == ["f'{_theme_offered} theme'"]
    assert {word.arg: ast.unparse(word.value) for word in call.keywords} == {
        "key": repr(KEY), "on_click": "_page_theme_pressed", "args": "(_theme_offered,)"}, \
        "no icon, no help, no width: no wider than its label"
    slot = next(index for index, node in enumerate(tree.body) if isinstance(node, ast.Assign)
                and ast.unparse(node.targets[0]) == "_page_theme_slot")
    assert ast.unparse(tree.body[slot].value) == "st.sidebar.container()", "at the sidebar's left edge"
    here_now = next(index for index, node in enumerate(tree.body) if isinstance(node, ast.Assign)
                    and ast.unparse(node.targets[0]) == "(_here_now_slot, _home_slot)")
    assert slot < here_now, "above Here & Now"


@pytest.mark.parametrize("held, reported, label", [
    (None, "dark", "Light theme"), (None, "light", "Dark theme"), (None, None, "Dark theme"),
    ("Dark", "light", "Light theme"), ("Light", "dark", "Dark theme"), ("Dark", None, "Light theme"),
])
def test_the_label_names_the_other_colours_than_those_shown(monkeypatch, held, reported, label):
    import streamlit

    import page_colours

    page_colours.show(held)
    monkeypatch.setattr(streamlit, "context", _Reporting(streamlit.context, reported))
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the label")
    assert _control(at).label == label


def test_a_press_with_no_entry_on_a_dark_computer_goes_light(prefs_on, monkeypatch):
    import streamlit

    import page_colours

    monkeypatch.setattr(streamlit, "context", _Reporting(streamlit.context, "dark"))
    at = make_app(page="sources").run(timeout=300)
    _control(at).click().run(timeout=300)
    assert_no_exception(at, "the press")
    assert page_colours.showing() == "Light" and _file_word(prefs_on) == "Light"
    assert _control(at).label == "Dark theme", "the choice decides now, not the computer"


def test_a_press_keeps_its_choice_in_the_file_and_nothing_takes_the_entry_away(prefs_on, monkeypatch):
    calls = _emitted(monkeypatch)
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the first run")
    import house_style
    import page_colours

    assert set(house_style.PAGE_COLOUR_SCHEME.values()).isdisjoint(calls)
    assert page_colours.showing() is None
    for word, then in (("Dark", "Light theme"), ("Light", "Dark theme"), ("Dark", "Light theme")):
        calls.clear()
        _control(at).click().run(timeout=300)
        assert_no_exception(at, word)
        assert page_colours.showing() == word and _control(at).label == then
        assert _file_word(prefs_on) == word
        assert calls.count(house_style.PAGE_COLOUR_SCHEME[word]) >= 1
        assert calls.index(house_style.PAGE_STYLE) + 1 == calls.index(house_style.PAGE_COLOUR_SCHEME[word])


def test_a_stale_tab_goes_where_its_label_says(prefs_on):
    """The second tab still reads "Dark theme" when the first has gone Dark. Its press
    goes Dark and stays there, where a press that flipped what it found would go Light."""
    import page_colours

    stale = make_app(page="sources").run(timeout=300)
    other = make_app(page="sources").run(timeout=300)
    _control(other).click().run(timeout=300)
    assert page_colours.showing() == "Dark" and _file_word(prefs_on) == "Dark"
    assert _control(stale).label == "Dark theme", "nothing reaches it until it runs"
    _control(stale).click().run(timeout=300)
    assert_no_exception(stale, "the stale press")
    assert page_colours.showing() == "Dark" and _file_word(prefs_on) == "Dark"
    assert _control(stale).label == "Light theme"
    # Back to Light from the stale tab; the other takes it at its next full run, its own
    # copy of the file still saying Dark. Its press to Dark is written all the same.
    _control(stale).click().run(timeout=300)
    assert page_colours.showing() == "Light" and _file_word(prefs_on) == "Light"
    other.run(timeout=300)
    assert _control(other).label == "Dark theme"
    _control(other).click().run(timeout=300)
    assert_no_exception(other, "the press its own copy agreed with")
    assert page_colours.showing() == "Dark" and _file_word(prefs_on) == "Dark"


def test_a_press_repeats_the_run_so_that_the_theme_goes_out(monkeypatch):
    """A session's theme goes out before a callback runs: without this the page
    would stay as it was until the reader's next move, which only a browser shows."""
    import streamlit

    asked, real = [], streamlit.rerun

    def rerun(*args, **kwargs):
        asked.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(streamlit, "rerun", rerun)
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the first run")
    assert not asked
    _control(at).click().run(timeout=300)
    assert_no_exception(at, "the press")
    assert len(asked) == 1


def _name_box(at):
    return next(box for box in at.sidebar.text_input if box.label == "Chart name (for saving)")


def test_the_session_s_chart_and_a_typed_name_stand_across_a_press():
    at = make_app(date="1240-05-23", page="sources").run(timeout=300)
    assert_no_exception(at, "the first run")
    _name_box(at).set_value("An invented chart").run(timeout=300)
    _control(at).click().run(timeout=300)
    assert_no_exception(at, "the press")
    assert at.session_state["date_input_key"] == "1240-05-23"
    assert _name_box(at).value == "An invented chart"


def test_another_session_s_choice_shows_at_this_one_s_next_full_run():
    """The options are the process's, as the file is the computer's: one reader,
    with a second tab."""
    first = make_app(page="sources").run(timeout=300)
    second = make_app(page="sources").run(timeout=300)
    _control(second).click().run(timeout=300)
    assert _control(first).label == "Dark theme", "nothing reaches it until it runs"
    first.run(timeout=300)
    assert_no_exception(first, "the other tab")
    assert _control(first).label == "Light theme"
    _control(first).click().run(timeout=300)
    second.run(timeout=300)
    assert _control(second).label == "Dark theme"


# --- What the choice decides ---------------------------------------------------------

def _viewer_theme(context):
    """The app's own reading, lifted out of its source and run on the choice in
    force and a browser's report."""
    import page_colours

    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_viewer_theme"]
    assert len(found) == 1, "one reading"
    scope = {"page_colours": page_colours, "_CHOICE_THIS_RUN": page_colours.showing(),
             "st": types.SimpleNamespace(context=types.SimpleNamespace(theme=context))}
    exec(compile(ast.Module(found, []), "_viewer_theme", "exec"), scope)
    return scope["_viewer_theme"]()


@pytest.mark.parametrize("choice, reported, expected", [
    ("Light", "dark", "light"), ("Dark", "light", "dark"), ("Light", None, "light"), ("Dark", None, "dark"),
    (None, "dark", "dark"), (None, "light", "light"), (None, None, None),
])
def test_the_viewer_s_theme_is_the_choice_and_else_the_browser_s_report(monkeypatch, choice, reported, expected):
    import page_colours

    monkeypatch.setattr(page_colours, "_showing", choice)
    context = types.SimpleNamespace(type=reported)
    assert _viewer_theme(context) == expected


@pytest.mark.parametrize("choice, expected", [("Light", "light"), ("Dark", "dark"), (None, None)])
def test_a_context_with_no_theme_at_all_leaves_the_choice_or_nothing(monkeypatch, choice, expected):
    import page_colours

    monkeypatch.setattr(page_colours, "_showing", choice)
    assert _viewer_theme(None) == expected


def test_the_page_s_colour_rule_is_a_rule_per_choice_outside_the_stylesheet():
    import house_style

    assert house_style.PAGE_COLOUR_SCHEME == {"Light": "<style>body{color-scheme:light;}</style>",
                                              "Dark": "<style>body{color-scheme:dark;}</style>"}
    assert "@media (prefers-color-scheme:dark){body{color-scheme:dark;}}" in house_style.PAGE_STYLE
    assert "}body{color-scheme" not in house_style.PAGE_STYLE


def test_the_button_s_rule_stands_in_the_page_s_stylesheet_keyed_to_this_button():
    import house_style

    style = house_style.PAGE_STYLE
    button = ".st-key-page_theme button"
    assert "st-emotion-cache" not in style
    assert ".st-key-page_theme{position:relative;top:-8px;}" in style, "a little above its place, the row under it unmoved"
    assert (f"{button},{button}:focus:not(:active){{background:light-dark(#FFFDF6,#0D1220);"
            "border:1px solid light-dark(#8A806E,#606B86);border-radius:6px;padding:9px 14px;"
            "color:light-dark(#242733,#EAE3D2);}") in style
    assert (f"{button}:is(:hover,:active),{button}:hover:focus:not(:active){{background:light-dark(#FFFDF6,#0D1220);"
            "border-color:light-dark(#895D16,#E3AA3E);color:light-dark(#895D16,#E3AA3E);}") in style
    assert (f"{button}:focus-visible{{outline:3px solid light-dark(#895D16,#E3AA3E);outline-offset:3px;"
            "box-shadow:none;}") in style
    assert button + ' [data-testid="stMarkdownContainer"]{line-height:20px;}' in style, "Here & Now's 40px, by a browser"


def test_no_script_reaches_the_page_for_this():
    """One component and two style emissions, as ever; the choice travels by the options."""
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    emissions = [ast.unparse(node) for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.html"
                 and "house_style" in ast.unparse(node)]
    assert emissions == ["st.html(house_style.PAGE_STYLE)",
                         "st.html(house_style.PAGE_COLOUR_SCHEME[page_colours.showing()])"]
    for name in ("app.py", "page_colours.py", "house_style.py", "server_limits.py"):
        text = (EXECUTABLE_DIR / name).read_text(encoding="utf-8")
        assert "unsafe_allow_javascript" not in text and "st.iframe(" not in text, name
    colours = (EXECUTABLE_DIR / "page_colours.py").read_text(encoding="utf-8")
    assert "<script" not in colours and "st.components" not in colours and "st.query_params" not in colours
    assert "page_colours" not in source[:source.index("def _admit_only_the_window")]


def _handed_over(monkeypatch):
    """What each download button is handed at its latest drawing, by its key: the harness
    cannot read a button's bytes."""
    import streamlit

    handed, real = {}, streamlit.download_button

    def capturing(label, data, *args, **kwargs):
        handed[kwargs["key"]] = data
        return real(label, data, *args, **kwargs)

    monkeypatch.setattr(streamlit, "download_button", capturing)
    return handed


def _exports(at, handed):
    analysis = at.session_state["_analysis_export"]
    stamp = str(analysis["exported"])
    pieces = {"html": at.session_state["_analysis_html"], "markdown": at.session_state["_analysis_markdown"],
              "json": json.dumps(analysis, indent=1, ensure_ascii=False)}
    assert stamp and all(stamp in piece for piece in pieces.values())
    buttons = {"html": "_export_html", "markdown": "_export_md", "json": "_export_json"}
    return {name: (piece.replace(stamp, "<stamp>"), handed[buttons[name]].decode("utf-8").replace(stamp, "<stamp>"))
            for name, piece in pieces.items()}


def test_the_exports_do_not_follow_the_choice(monkeypatch):
    handed = _handed_over(monkeypatch)
    at = make_app(page="chart").run(timeout=300)
    assert_no_exception(at, "no entry")
    states = {"no entry": _exports(at, handed)}
    for name in ("html", "markdown", "json"):
        store, button = states["no entry"][name]
        assert store == button, name
    for word in ("Dark", "Light"):
        handed.clear()
        _control(at).click().run(timeout=300)
        assert_no_exception(at, word)
        states[word] = _exports(at, handed)
    assert states["Dark"] == states["no entry"] and states["Light"] == states["no entry"]


def test_the_wheel_s_svg_follows_the_choice(monkeypatch):
    """The saved wheel is what the page shows."""
    handed = _handed_over(monkeypatch)
    at = make_app(page="chart").run(timeout=300)
    assert_no_exception(at, "no entry")
    states = {"no entry": handed["dl_chart_wheel"]}
    assert states["no entry"]
    for word in ("Dark", "Light"):
        handed.clear()
        _control(at).click().run(timeout=300)
        assert_no_exception(at, word)
        states[word] = handed["dl_chart_wheel"]
    assert states["Light"] == states["no entry"], "the light palette is what a page that has not said is drawn in"
    import wheel

    ground = f'fill="{wheel._PALETTE_DARK["bg"]}"'
    assert ground in states["Dark"] and ground not in states["Light"]
