"""The opening page: the launcher's window shows it from its first paint
until its server answers, and the app's server writes the same look into the
page's own document, where it stands from the first paint until a session's
first run ends; and the timed start the stop check prints.

A browser alone shows: the html= page under Qt WebEngine and macOS's WebKit,
the cover's lifting in a real window, and the icon's beat (a style on transform,
which only a real window shows holding while the page is busy)."""
import base64
import importlib.util
import json
import os
import subprocess
import sys
import types
import urllib.parse

import pytest

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app
from test_house_style_2026_11_04 import _ask, font_port, font_server  # noqa: F401 (fixtures)

SCRIPT = EXECUTABLE_DIR / ".github" / "scripts" / "stop_check.py"


def _texts(at):
    """Every html body the app's page holds, in its tree."""
    found = []

    def walk(node):
        proto = getattr(node, "proto", None)
        body = getattr(getattr(proto, "html", None), "body", None) or getattr(proto, "body", None)
        if isinstance(body, str):
            found.append(body)
        for child in getattr(node, "children", {}).values() if isinstance(getattr(node, "children", None), dict) else []:
            walk(child)
    walk(at._tree)
    return found


def _covered(at):
    import opening

    return any(f'class="{opening.CLASS}"' in text for text in _texts(at))


def _held_lifted(at):
    import opening

    return sum(text == opening.LIFTED for text in _texts(at))


def _index():
    import streamlit

    with open(os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html"), encoding="utf-8") as f:
        return f.read()


# --- The look ------------------------------------------------------------------------------

def test_the_page_carries_the_icon_read_as_bytes_and_no_visible_text_but_the_name():
    import re

    import opening

    page = opening.page("Light")
    icon = (EXECUTABLE_DIR / opening.ICON_NAME).read_bytes()
    assert base64.b64encode(icon).decode("ascii") in page
    assert "<script" not in page.lower()
    assert opening.NAME == "Z\u012bj"
    assert re.sub(r"<[^>]*>", "", opening._body()) == opening.NAME, "the program's name, and no other text"
    assert re.sub(r"<[^>]*>", "", page.split("<body>", 1)[1]) == opening.NAME
    # No script by a handler either: no on<name>= attribute in either cover.
    handler = r"\son[a-z]+\s*="
    index = _index()
    for choice in ("Light", "Dark"):
        assert re.search(handler, opening.page(choice), re.I) is None, choice
        served = opening.served(index, choice)
        assert len(re.findall(handler, served, re.I)) == len(re.findall(handler, index, re.I)), choice
        assert re.search(handler, opening._body(), re.I) is None, choice
    # No text drawn by style: no content: in the cover's style, guarded or not.
    drawn = r"(?<![a-z-])content\s*:"  # not justify-content:, align-content:
    assert re.search(drawn, opening._css("#000", "#fff", "#c90", opening.FACE_URL, guarded=True), re.I) is None
    assert re.search(drawn, opening._css("#000", "#fff", "#c90", None), re.I) is None


def _cover_style(served):
    return served[served.index("<style>html,body"):served.index("</style>")]


def test_the_cover_s_face_is_the_italic_file_alone_and_the_launchers_page_stays_small():
    """The name's face: the italic file the app ships, as a data: URI in the
    launcher's page and by the app's own font route in the served cover; no
    roman face, in either."""
    import opening
    import server_limits

    assert opening.FACE_FILE == os.path.join("fonts", "eb-garamond-400-italic.ttf")
    assert opening.FACE_URL == server_limits.FONT_ROUTE + "eb-garamond-400-italic.ttf"
    assert opening.FACE_URL.rsplit("/", 1)[1] in server_limits.FONT_FILES
    page = opening.page("Light")
    served = _cover_style(opening.served(_index(), "Light"))
    italic = base64.b64encode((EXECUTABLE_DIR / opening.FACE_FILE).read_bytes()).decode("ascii")
    assert page.count("@font-face") == 1 and served.count("@font-face") == 1
    assert f"src:url(data:font/ttf;base64,{italic})" in page
    assert f"src:url({opening.FACE_URL})" in served and "font/ttf" not in served
    for made in (page, served):
        assert "font-style:italic" in made
        assert "eb-garamond-400.ttf" not in made and "eb-garamond-600" not in made, "no roman face"
    roman = base64.b64encode((EXECUTABLE_DIR / "fonts" / "eb-garamond-400.ttf").read_bytes()).decode("ascii")
    assert roman[:2000] not in page
    assert len(page.encode("utf-8")) < 600_000, len(page)


def test_the_name_stands_beneath_the_icon_still_in_the_italic_swash_and_the_pages_gold():
    """The name sits outside the beating element, 12 px under the icon at 30
    px, in the accent each palette has in the configuration, its swash forms on
    (the face has a swash Z); nothing animates it."""
    import re
    import tomllib

    import opening

    theme = tomllib.loads((EXECUTABLE_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    assert (opening.NAME_PIXELS, opening.NAME_GAP_PIXELS) == (30, 12)
    for choice, palette in (("Light", "light"), ("Dark", "dark"), (None, "light")):
        gold = theme[palette]["primaryColor"]
        assert opening.accent(choice) == gold
        for made in (opening.page(choice), opening.served(_index(), choice)):
            rule = re.search(r"\.zij-opening \.zij-opening-name\{([^}]*)\}", made).group(1)
            assert f"color:{gold};" in rule and "font-style:italic;" in rule and "font-size:30px;" in rule
            assert "margin:12px 0 0;" in rule and 'font-feature-settings:"swsh" 1;' in rule
            assert "animation" not in rule and "transform" not in rule
            # The one animated element is the icon: the name is a sibling, not inside it.
            assert re.search(r"\.zij-opening img\{[^}]*animation:zij-opening-beat", made)
            assert made.count("animation:") == 2  # the icon's beat and the reduced-motion rule's none
    assert theme["light"]["primaryColor"] != theme["dark"]["primaryColor"]
    body = opening._body()
    assert re.search(r'<img alt="" src="data:image/png;base64,[^"]*"><div class="zij-opening-name" aria-hidden="true">Z\u012bj</div></div>$', body)


def test_the_face_has_the_swash_z_and_the_i_with_macron_the_name_is_written_in():
    from fontTools.ttLib import TTFont

    import opening

    font = TTFont(EXECUTABLE_DIR / opening.FACE_FILE)
    assert "swsh" in {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    assert "Z.swsh" in font.getGlyphOrder()
    cmap = font.getBestCmap()
    assert all(ord(c) in cmap for c in opening.NAME)


def test_a_screen_reader_hears_opening_and_the_icon_stays_silent():
    import opening

    for made in (opening.page("Dark"), opening.served(_index(), "Dark")):
        assert f'<div class="{opening.CLASS}" role="status" aria-label="Opening">' in made
        assert '<img alt=""' in made
        # The visible name is only seen: the reader hears the one word.
        assert '<div class="zij-opening-name" aria-hidden="true">' in made
    assert opening.SPOKEN == "Opening"


def test_the_icon_beats_by_transform_alone_and_is_still_under_reduced_motion():
    import re

    import opening

    assert (opening.BEAT_SECONDS, opening.BEAT_SCALE) == (2.5, 1.08)
    served = opening.served(_index(), "Light")
    for made in (opening.page("Light"), served):
        assert (f".{opening.CLASS} img{{width:128px;height:128px;"
                "animation:zij-opening-beat 1.25s ease-in-out infinite alternate;}") in made
        frames = re.search(r"@keyframes zij-opening-beat\{(.*?)\}\}", made).group(1) + "}"
        assert frames == "from{transform:scale(1);}to{transform:scale(1.08);}"
        assert re.findall(r"([\w-]+):", frames) == ["transform", "transform"], "transform only"
        assert (f"@media (prefers-reduced-motion: reduce){{.{opening.CLASS} img{{animation:none;}}}}") in made
        assert made.index("@keyframes") < made.index("prefers-reduced-motion")


def test_both_pages_are_one_look_in_the_saved_colours_light_when_none():
    import tomllib

    import opening

    theme = tomllib.loads((EXECUTABLE_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    for choice, palette in (("Light", "light"), ("Dark", "dark"), (None, "light"), ("Purple", "light")):
        ground, text = theme[palette]["backgroundColor"], theme[palette]["textColor"]
        for made in (opening.page(choice), opening.served(_index(), choice)):
            assert f"background:{ground};color:{text};" in made, (choice, made[:200])
            assert f"html,body{{margin:0;background:{ground};}}" in made, choice
    launcher_body = opening.page("Light").split("<body>", 1)[1][:-len("</body></html>")]
    served = opening.served(_index(), "Light")
    assert served.split("<body>", 1)[1].startswith(launcher_body)


def test_the_icon_is_one_reduction_of_the_owner_s_emblem_and_only_the_reduction_is_shipped():
    """app_icon_opening.png is what icon.py makes of app_icon_opening_source.png,
    byte for byte; the source stays in the repository and is not carried into a
    download."""
    import io

    from PIL import Image

    import opening

    assert (opening.ICON_NAME, opening.ICON_SOURCE, opening.ICON_PIXELS) == (
        "app_icon_opening.png", "app_icon_opening_source.png", 256)
    with Image.open(EXECUTABLE_DIR / opening.ICON_SOURCE) as source:
        assert source.size == (1024, 1024) and source.mode == "RGBA"
        assert source.getpixel((0, 0))[3] == 0, "the emblem's corners are transparent"
        made = io.BytesIO()
        source.convert("RGBA").resize((opening.ICON_PIXELS,) * 2, Image.LANCZOS).save(made, "PNG", optimize=True)
    assert (EXECUTABLE_DIR / opening.ICON_NAME).read_bytes() == made.getvalue()
    with Image.open(EXECUTABLE_DIR / opening.ICON_NAME) as image:
        assert image.size == (256, 256) and image.mode == "RGBA"
    spec = (EXECUTABLE_DIR / "build.spec").read_text(encoding="utf-8")
    assert f'("{opening.ICON_NAME}", ".")' in spec and opening.ICON_SOURCE not in spec
    code = (EXECUTABLE_DIR / "icon.py").read_text(encoding="utf-8")
    assert f'Image.open("{opening.ICON_SOURCE}")' in code and f'save("{opening.ICON_NAME}"' in code
    assert 'Image.open("app_icon_source.png")' in code, "the program's own icon is made as before"


def test_the_launcher_s_read_loads_neither_the_engine_nor_streamlit(tmp_path):
    import page_colours
    import opening

    assert opening.PREFERENCE == page_colours.PREFERENCE and (opening.LIGHT, opening.DARK) == page_colours.CHOICES
    code = ("import json, os, sys; sys.path.insert(0, os.environ['ZIJ_TEST_TREE']); import user_data;"
            "user_data.PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True);"
            "user_data.PREFERENCES_PATH.write_text(json.dumps({'_page_colours': 'Dark'}), encoding='utf-8');"
            "import importlib.util, types; sys.modules['webview'] = types.ModuleType('webview');"
            "spec = importlib.util.spec_from_file_location('launcher', os.path.join(os.environ['ZIJ_TEST_TREE'], 'desktop_launcher.py'));"
            "launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher);"
            "page = launcher.opening.page(launcher._saved_colours());"
            "print(json.dumps([launcher._saved_colours(), 'engine' in sys.modules, 'streamlit' in sys.modules]))")
    env = {name: value for name, value in os.environ.items()
           if name != "ALMUTEN_NO_PREFERENCES" and not name.upper().startswith("STREAMLIT_")}
    env.update(HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "xdg"), APPDATA=str(tmp_path / "appdata"),
               ZIJ_TEST_TREE=str(EXECUTABLE_DIR))
    done = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(tmp_path), capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout.splitlines()[-1]) == ["Dark", False, False]


# --- The launcher's window -----------------------------------------------------------------

def _rules(monkeypatch):
    from test_polish3_launcher_2026_10_14 import _load_launcher

    desktop_launcher = _load_launcher(monkeypatch)
    rules = desktop_launcher._WindowRules("http://127.0.0.1:8581", "key")
    rules.opening = "<!doctype html><p>Opening…</p>"
    return desktop_launcher, rules


def test_the_window_admits_its_opening_page_and_nothing_wider(monkeypatch):
    launcher, rules = _rules(monkeypatch)
    for form in ("data:text/html;charset=UTF-8," + urllib.parse.quote(rules.opening),
                 "data:text/html;charset=UTF-8;base64," + base64.b64encode(rules.opening.encode()).decode(),
                 "about:blank", ""):
        assert rules.verdict(form, True) == launcher._GO, form
    for other in ("data:text/html;charset=UTF-8," + urllib.parse.quote("<p>Another</p>"),
                  "data:text/plain," + urllib.parse.quote(rules.opening),
                  "data:text/html;base64,not base64!",
                  "http://127.0.0.2:8581/", "http://example.com/", "file:///etc/hosts"):
        assert rules.verdict(other, True) == launcher._REFUSE, other
    rules.opening = None
    for form in ("data:text/html;charset=UTF-8," + urllib.parse.quote("<!doctype html><p>Opening…</p>"),
                 "about:blank"):
        assert rules.verdict(form, True) == launcher._REFUSE, "the page is let in only while the window shows it"


def _stand_in(seen, calls_func=True):
    webview = types.ModuleType("webview")

    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    def create_window(title, url=None, **options):
        seen.append(("window", url, options.get("html")))
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=lambda: seen.append(("destroyed",)),
                                     load_url=lambda address: seen.append(("load_url", address)))

    def start(func=None, window=None, **options):
        seen.append(("started",))
        if calls_func and func is not None:
            func(window)

    webview.create_window, webview.start = create_window, start
    return webview


@pytest.mark.parametrize("answers", [True, False], ids=["the server answers", "it never does"])
def test_the_window_opens_on_the_page_and_goes_to_the_server_once_it_answers(monkeypatch, answers):
    from test_polish3_launcher_2026_10_14 import _load_launcher

    seen = []
    launcher = _load_launcher(monkeypatch, _stand_in(seen))
    proc = types.SimpleNamespace(stdout=None, stdin=None, poll=lambda: None, wait=lambda *a: 0, kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8581)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_stop_server", lambda proc: None)
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher, "_withhold_the_secret", lambda secret: None)
    monkeypatch.setattr(launcher, "_fit_window_to_screen", lambda window: None)
    monkeypatch.setattr(launcher, "_close_the_windows_doors", lambda rules: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    monkeypatch.setattr(launcher.threading, "Thread", lambda *a, **k: types.SimpleNamespace(start=lambda: None,
                                                                                         join=lambda **k: None))
    monkeypatch.setattr(launcher, "_ServerOutput", lambda mark: types.SimpleNamespace(listening=None, text=lambda: ""))
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: (seen.append(("waited",)), answers)[1])
    stop_signals = types.SimpleNamespace(watch=lambda stop: None, close_with=lambda destroy: None)
    if answers:
        launcher._run_the_window(stop_signals)
    else:
        with pytest.raises(RuntimeError, match="did not start within the timeout"):
            launcher._run_the_window(stop_signals)
    kind, url, page = seen[0]
    assert kind == "window" and url is None and 'aria-label="Opening"' in page, "the window opens on the page, not the server"
    assert seen[1:3] == [("started",), ("waited",)], "it waits for the server only with the window up"
    if answers:
        assert seen[3][0] == "load_url" and seen[3][1].startswith("http://127.0.0.1:8581/?launch=") and len(seen) == 4
    else:
        assert seen[3:] == [("destroyed",)]


# --- The app's cover -----------------------------------------------------------------------

def test_the_served_document_holds_the_cover_and_the_saved_ground(font_server):
    """The page's own document, as the app's server answers it, at its root and
    at a page's address alike, and to a request that names a copy it holds:
    the cover's style first in the head, the ground on the body, the cover
    first in the body, and not one script more than Streamlit's own."""
    import opening

    index = _index()
    for target, extra in (("/", ()), ("/sources", ()), ("/", ('If-None-Match: "x"', "If-Modified-Since: "
                                                               "Sat, 01 Jan 2000 00:00:00 GMT"))):
        status, headers, body = _ask(font_server, target, extra=extra)
        assert status == 200 and headers["content-type"].startswith("text/html"), (target, status, headers)
        assert headers["cache-control"] == "no-cache"
        document = body.decode("utf-8")
        assert document == opening.served(index, opening.LIGHT), target
        head = document.split("</head>", 1)[0]
        assert head.index("html,body{margin:0;background:") < head.index("<link"), target
        assert document.split("<body>", 1)[1].startswith(f'<div class="{opening.CLASS}" role="status" aria-label="Opening">')
        assert document.lower().count("<script") == index.lower().count("<script"), target
    assert _ask(font_server, "/", method="HEAD")[0] == 200


def test_the_served_cover_adds_its_style_and_markup_and_nothing_else():
    """Taking out the cover's one style and its one markup gives Streamlit's
    document back exactly; neither holds a script; each saved choice gives its
    own ground, Light for anything but Dark."""
    import opening

    index = _index()
    for choice in ("Light", "Dark", None, "Purple"):
        ground, text = opening.colours(choice)
        style = (f"<style>html,body{{margin:0;background:{ground};}}"
                 f"{opening._css(ground, text, opening.accent(choice), opening.FACE_URL, guarded=True)}</style>")
        markup = opening._body()
        served = opening.served(index, choice)
        assert served.count(style) == 1 and served.count(markup) == 1, choice
        assert served.replace(style, "", 1).replace(markup, "", 1) == index, choice
        assert "<script" not in (style + markup).lower()
    assert opening.colours("Dark") != opening.colours("Light") == opening.colours(None)
    assert opening.served("<html>no head, no body</html>", "Dark") == "<html>no head, no body</html>"


def test_no_element_of_the_cover_stands_in_the_page_and_a_later_run_holds_it_lifted():
    """The cover is the document's, not the page's: no run puts it among the
    page's elements. The first run's end writes the one style that holds it
    lifted, and every later run writes it again at its top."""
    import opening

    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the first run")
    assert not _covered(at) and _held_lifted(at) == 1
    at.run(timeout=300)
    assert_no_exception(at, "the second run")
    assert not _covered(at) and _held_lifted(at) == 1, "a later run holds it lifted, once"
    assert opening.SHOWN in at.session_state


def test_a_whole_first_run_leaves_the_mark(monkeypatch):
    import opening

    marked = []
    real = opening.mark_the_whole_run
    monkeypatch.setattr(opening, "mark_the_whole_run", lambda: (marked.append(1), real())[1])
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the first run")
    assert marked == [1]
    at.run(timeout=300)
    assert marked == [1], "the mark is the first run's"


def test_a_first_run_that_raises_still_holds_the_cover_lifted(monkeypatch):
    import streamlit

    class Raising:
        def run(self):
            raise RuntimeError("a page that fails")

    monkeypatch.setattr(streamlit, "navigation", lambda *args, **kwargs: Raising())
    at = make_app(page="sources")
    # The suite's own guard says the run raised before its page.
    with pytest.raises(pytest.fail.Exception, match="the run did not reach the page"):
        at.run(timeout=300)
    assert not _covered(at) and _held_lifted(at) == 1, "the first run's end holds it lifted"


def test_the_cover_lifts_itself_when_a_run_stops_and_the_app_holds_it_lifted_after():
    """Two rules lift it, by style alone: the page's run state reading stopped
    (an exception's end too), and the style the app writes at the first run's
    end and at the top of every later run."""
    import opening

    served = opening.served(_index(), "Light")
    for state in ('="notRunning"', '^="compilation"'):
        assert f'body:has([data-testid="stApp"][data-test-script-state{state}]) .{opening.CLASS}' in served
    assert opening.LIFTED == f"<style>.{opening.CLASS}{{display:none !important;}}</style>"
    app = (EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8")
    top = app.index("_OPENING_FIRST_RUN = opening.first_run(st)\n")
    assert app.index("st.set_page_config(") < top < app.index("st.navigation(pages")
    tail = app[app.rindex("try:\n    st.navigation(pages"):]
    assert "finally:\n" in tail
    assert tail.split("finally:\n", 1)[1].lstrip("\n").split("\n# ", 1)[0].strip().endswith(
        "if _OPENING_FIRST_RUN:\n        opening.keep_lifted(st)")
    assert "_event" not in (EXECUTABLE_DIR / "opening.py").read_text(encoding="utf-8")


# --- The timed start -----------------------------------------------------------------------

def _stop_check():
    spec = importlib.util.spec_from_file_location("stop_check_for_opening", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stands", [True, False], ids=["it stands", "it never does"])
def test_the_timed_start_prints_one_line_and_fails_nothing_on_time(monkeypatch, capsys, stands):
    check = _stop_check()
    seen = iter([False, False] + [stands] * 1000)
    monkeypatch.setattr(check, "_whole_run_seen", lambda port: next(seen))
    monkeypatch.setattr(check, "POLL_SECONDS", 0.001)
    runner = types.SimpleNamespace(args=types.SimpleNamespace(run_seconds=0.2 if not stands else 30))
    launch = types.SimpleNamespace(number=1, port=8581, started=check.time.monotonic() - 2.0)
    seconds = check.Check.timed_start(runner, launch) if hasattr(check, "Check") else None
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("launch 1: timed start: ")]
    assert len(lines) == 1, lines
    if stands:
        assert seconds >= 2.0 and lines[0].endswith("s from the download's start to the end of its window's "
                                                   "first whole run")
    else:
        assert seconds is None and "had not stood whole" in lines[0]


def test_the_mark_is_the_one_the_app_leaves():
    check = _stop_check()
    import opening

    name = f"{opening.first_whole_run.__module__}.{opening.first_whole_run.__qualname__}"
    assert check._WHOLE_RUN.search(f'cache_memory_bytes{{cache_type="st_cache_data",cache="{name}"}} 4\n')
    assert not check._WHOLE_RUN.search('cache_memory_bytes{cache_type="st_cache_data",cache="engine.x"} 4\n')


def test_a_download_whose_first_run_never_stands_whole_still_passes_and_says_so(tmp_path):
    """No threshold: the timed start fails nothing. A window whose session is
    never let in still fails the step as before
    (test_stop_check_2026_10_13's test_a_window_whose_session_the_server_never_lets_in_fails)."""
    from test_stop_check_2026_10_13 import _PASSING, _fake

    code, out = _fake(tmp_path, "obeys", bounds=_PASSING, extra_env={"FAKE_NO_WHOLE_RUN": "1"}, run="8")
    assert code == 0, out
    timed = [line for line in out.splitlines() if ": timed start: " in line]
    assert timed == [f"launch {n}: timed start: the window's first run had not stood whole 8 s after it ran the app"
                     for n in (1, 2)], out


def _bundle():
    import streamlit

    folder = os.path.join(os.path.dirname(streamlit.__file__), "static", "static", "js")
    return "".join(open(os.path.join(folder, name), encoding="utf-8", errors="replace").read()
                   for name in os.listdir(folder) if name.startswith("index") and name.endswith(".js"))


def _run_state_misses(bundle, css):
    """What the cover's CSS keys on that the bundle does not write."""
    import re

    misses = []
    if not re.search(r'"data-testid":`stApp`,"data-test-script-state":', bundle):
        misses.append("the attribute on stApp")
    at = bundle.find("NOT_RUNNING=")
    states = dict(re.findall(r"\b([A-Z_]+)=`(\w+)`", bundle[at:at + 400])) if at >= 0 else {}
    if states.get("NOT_RUNNING") != "notRunning" or not states.get("COMPILATION_ERROR", "").startswith("compilation"):
        misses.append("the stopped states' values")
    if 'body:has([data-testid="stApp"][data-test-script-state="notRunning"])' not in css or \
            'body:has([data-testid="stApp"][data-test-script-state^="compilation"])' not in css:
        misses.append("the cover's own rule")
    return misses


def test_streamlit_s_own_bundle_still_writes_the_run_state_the_cover_keys_on():
    """The cover lifts by the page's run state, an attribute Streamlit's
    front end writes on its app element: an upgrade that renames the
    attribute or its values fails here, not in a reader's window."""
    import opening

    assert _run_state_misses(_bundle(), opening.served(_index(), "Light")) == []


@pytest.mark.parametrize("old, new", [('"data-test-script-state":', '"data-test-run-state":'),
                                      ("NOT_RUNNING=`notRunning`", "NOT_RUNNING=`idle`")])
def test_a_bundle_that_renames_the_run_state_is_caught(old, new):
    import opening

    bundle = _bundle()
    assert old in bundle
    assert _run_state_misses(bundle.replace(old, new), opening.served(_index(), "Light")) != []


# --- Streamlit's handler, the one wrapped ---------------------------------------------------

def _handler_misses(app_source, static_source):
    """What server_limits.py's wrap of Streamlit's index.html relies on that
    Streamlit's own server no longer does."""
    misses = []
    if "routes.extend(create_streamlit_static_assets_routes(base_url=base_url))" not in app_source:
        misses.append("the app's routes are not made by the wrapped name")
    if "from streamlit.web.server.starlette.starlette_static_routes import (\n    create_streamlit_static_assets_routes," \
            not in app_source:
        misses.append("the wrapped name is not the one the app module looks up")
    for needed in ('self._index_path = os.path.join(directory, "index.html")', "html=True",
                   "response = FileResponse(self._index_path)", "async def get_response(",
                   "response = await super().get_response(path, scope)", "app=static_assets,"):
        if needed not in static_source:
            misses.append(f"the static handler lacks {needed!r}")
    return misses


def _handler_sources():
    from streamlit.web.server.starlette import starlette_app, starlette_static_routes

    return (open(starlette_app.__file__, encoding="utf-8").read(),
            open(starlette_static_routes.__file__, encoding="utf-8").read())


def test_streamlit_s_own_handler_still_serves_the_index_the_server_wraps():
    """An upgrade that moves the index.html's handler fails here: the served
    document's test above fails with it, where the cover is not written."""
    assert _handler_misses(*_handler_sources()) == []


@pytest.mark.parametrize("which, old, new", [
    (0, "routes.extend(create_streamlit_static_assets_routes(base_url=base_url))", "routes.extend(make_static(base_url))"),
    (1, "response = FileResponse(self._index_path)", "response = FileResponse(self._spa_path)"),
    (1, 'self._index_path = os.path.join(directory, "index.html")', 'self._index = os.path.join(directory, "index.html")'),
])
def test_a_streamlit_that_moves_the_handler_is_caught(which, old, new):
    sources = list(_handler_sources())
    assert old in sources[which]
    sources[which] = sources[which].replace(old, new)
    assert _handler_misses(*sources) != []


def test_a_streamlit_without_the_static_routes_name_does_not_start(monkeypatch):
    import server_limits
    from streamlit.web.server.starlette import starlette_app

    monkeypatch.delattr(starlette_app, "create_streamlit_static_assets_routes")
    with pytest.raises(RuntimeError, match="create_streamlit_static_assets_routes"):
        server_limits.hold_the_server(str(EXECUTABLE_DIR / "app.py"))


def test_an_engine_that_cannot_read_has_never_shows_the_served_cover():
    """The served cover lifts only by :has(). Its showing stands inside one
    @supports block on that selector, after a rule that hides it, so a window
    whose engine cannot read :has() opens the page with no cover at all. The
    launcher's own page, which nothing has to lift, is not guarded."""
    import re

    import opening

    served = opening.served(_index(), "Light")
    style = served[served.index("<style>html,body"):]
    style = style[:style.index("</style>")]
    assert opening.SUPPORTS == "@supports selector(:has(*))"
    guarded = f"{opening.SUPPORTS}{{.{opening.CLASS}{{position:fixed;"
    # The rule that hides it stands right before the block that shows it.
    assert style.count(f"}}.{opening.CLASS}{{display:none;}}{guarded}") == 1 and style.count(guarded) == 1
    # Outside that block, no rule gives the cover a display but none.
    outside = style.replace(style[style.index(guarded):style.index("}}", style.index(guarded)) + 2], "")
    assert re.findall(r"display:(?!none)\w+", outside) == [], outside
    assert opening.SUPPORTS not in opening.page("Light")
