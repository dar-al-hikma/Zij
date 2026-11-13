"""Downloads in the desktop window, and the sidebar's one export button.

The desktop window is pywebview's. Its setting for downloads is off unless
the launcher turns it on, and with it off macOS's window went to the
downloaded file as a page of its own (a JSON export shown as text, with no
way back), and Windows' Qt window dropped the download. The launcher turns
it on before webview.start, and the window's rules still refuse every
navigation they refused before. In the Qt window, a download is saved only
when it is the server's own file (or content the page made on the server's
origin), and goes through the system's Save dialog under the name the
download carries.

The sidebar's analysis export is one button that, clicked, offers the three
formats -- HTML, JSON and Markdown, HTML first -- each with the file name,
type and bytes its own button had, and a click reruns nothing. With no
chart it is one disabled button and the caption that says why. The other
downloads, the wheels' and the strips' pictures, rerun nothing on a click
either.

pywebview is not in the suite's venv: a stand-in records the window, the
server child is a stand-in object, so no process is started or ended.
"""
import ast
import enum
import importlib.util
import io
import json
import logging
import re
import sys
import threading
import types

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"
ORIGIN = "http://127.0.0.1:8583"
SECRET = "export-secret-" + "e" * 30


@pytest.fixture(autouse=True)
def _log_formatters_kept(monkeypatch):
    """The launcher puts a formatter on every root and pywebview handler;
    those of the test run's own are given back after each test."""
    for name in (None, "pywebview"):
        for handler in logging.getLogger(name).handlers:
            monkeypatch.setattr(handler, "formatter", handler.formatter)


def _load_launcher(monkeypatch, webview_module=None):
    monkeypatch.setitem(sys.modules, "webview", webview_module or types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_export1", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Hooks(list):
    def __iadd__(self, hook):
        self.append(hook)
        return self


class _QUrl:
    def __init__(self, text):
        self.text = text

    def toString(self):
        return self.text


def _qt_backend():
    """pywebview's Qt backend as far as the launcher touches it, with its
    own download handler: the one that names the file by the address and
    calls setPath, which Qt 6's download has not got. Its window connects
    the profile's downloadRequested in its constructor, when downloads are
    allowed, to the handler the class has then (pywebview 6.2.1's
    BrowserView.__init__); `settings` is the stand-in webview's own."""
    lib = types.ModuleType("webview.platforms.qt")
    lib.settings, lib.windows = {"ALLOW_DOWNLOADS": False}, []

    class QWebPage:
        PermissionPolicy = enum.Enum("PermissionPolicy", {"PermissionDeniedByUser": 2})

        def acceptNavigationRequest(self, url, kind, is_main_frame):
            return True

    class _Signal:
        def __init__(self):
            self.slots = []

        def connect(self, slot):
            self.slots.append(slot)

    class WebPage(QWebPage):
        def __init__(self, parent=None, profile=None):
            self.permissionRequested, self.urlChanged = _Signal(), _Signal()
            self.loads = []

        def setUrl(self, url):
            self.loads.append(url.toString())

    class BrowserView:
        def __init__(self):
            self.downloadRequested = _Signal()            # the profile's downloadRequested
            if lib.settings["ALLOW_DOWNLOADS"]:
                self.downloadRequested.connect(self.on_download_requested)

        def on_download_requested(self, download):
            download.setPath(download.url().toString().rsplit("/", 1)[-1])
            download.accept()

    BrowserView.WebPage = WebPage
    lib.BrowserView, lib.QWebPage, lib.is_webengine = BrowserView, QWebPage, True
    lib.QtCore = types.SimpleNamespace(QUrl=_QUrl, QTimer=types.SimpleNamespace(singleShot=lambda ms, f: f()))
    lib.environ_append = lambda key, *values, **kwargs: None
    lib.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)
    lib.js_bridge_call = lambda *a, **k: "called"
    lib.QFileDialog = types.SimpleNamespace(getSaveFileName=None)
    return lib


class _Download:
    """Qt 6's download request, as far as the handler touches it: no setPath."""

    def __init__(self, url, name="analysis_Florence_1240-05-23.json", folder="/Downloads"):
        self._url, self._name, self._folder = url, name, folder
        self.accepted = self.cancelled = False

    def url(self):
        return _QUrl(self._url)

    def downloadFileName(self):
        return self._name

    def downloadDirectory(self):
        return self._folder

    def setDownloadFileName(self, name):
        self._name = name

    def setDownloadDirectory(self, folder):
        self._folder = folder

    def accept(self):
        self.accepted = True

    def cancel(self):
        self.cancelled = True


def _webview_stand_in(seen, backend=None):
    webview = types.ModuleType("webview")
    webview.settings = {"ALLOW_DOWNLOADS": False, "OPEN_EXTERNAL_LINKS_IN_BROWSER": True}
    webview.util = types.SimpleNamespace(js_bridge_call=lambda *a, **k: "called")
    webview.initialize = lambda gui=None: backend
    if backend is not None:
        backend.settings = webview.settings              # the backend reads the same object

    def create_window(title, url=None, **options):
        seen.append(("window", dict(webview.settings)))
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=lambda: None)

    def start(*args, **kwargs):
        seen.append(("started", dict(webview.settings)))
        if backend is not None:
            webview.initialize(kwargs.get("gui"))      # as webview.start loads its backend
            backend.windows.append(backend.BrowserView())   # and then makes the window

    webview.create_window, webview.start = create_window, start
    return webview


def _launch(monkeypatch, webview):
    launcher = _load_launcher(monkeypatch, webview)
    marked = threading.Event()

    class _Output:
        """A server child's output, read a line at a time or by iteration: the mark, then nothing until
        `marked` is set, then the pipe's end."""

        def __init__(self):
            self.lines = ["zij-server-listening 8583\n"]

        def readline(self, limit=-1):
            if self.lines:
                return self.lines.pop(0)
            marked.wait(10)
            return ""

        def __iter__(self):
            return iter(self.readline, "")

    proc = types.SimpleNamespace(stdout=_Output(), stdin=io.StringIO(), poll=lambda: None,
                                 wait=lambda *a: 0, kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8583)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: listening.wait(5))
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    try:
        launcher._launch_desktop_window()
    finally:
        marked.set()
    return launcher


# --- The setting, on the launcher's own path ----------------------------------

def test_downloads_are_allowed_before_the_window_starts(monkeypatch):
    seen = []
    webview = _webview_stand_in(seen)
    _launch(monkeypatch, webview)
    started = [entry for entry in seen if entry[0] == "started"]
    assert len(started) == 1, seen
    assert started[0][1]["ALLOW_DOWNLOADS"] is True, "the setting was not on when webview.start was called"
    assert started[0][1]["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True, "no other setting is changed"
    assert seen[0] == ("window", started[0][1]), "set before the window was made, and left as it was"


# --- The window's rules, with downloads on -------------------------------------

NAVIGATIONS = [
    (f"{ORIGIN}/?launch={SECRET}", True, "go"),
    (f"{ORIGIN}/dignities?launch={SECRET}", True, "go"),
    (f"{ORIGIN}/", True, "give the secret"),
    (f"{ORIGIN}/media/0123abcd.json", True, "give the secret"),
    (f"{ORIGIN}/media/0123abcd.json", None, "go"),
    (f"{ORIGIN}/component/x/index.html", False, "go"),
    ("http://127.0.0.2:8583/", True, "refuse"),
    ("http://127.0.0.1:8584/media/0123abcd.json", True, "refuse"),
    ("http://127.0.0.1:8584/media/0123abcd.json", None, "refuse"),
    ("https://example.org/analysis.json", True, "refuse"),
    ("https://example.org/analysis.json", False, "refuse"),
    ("file:///etc/hostname", True, "refuse"),
    ("file:///etc/hostname", None, "refuse"),
    ("javascript:alert(1)", True, "refuse"),
    ("data:application/json,{}", True, "refuse"),
    (f"blob:{ORIGIN}/1", True, "refuse"),
    ("about:srcdoc", False, "go"),
    ("data:text/html,x", None, "go"),
    (f"blob:{ORIGIN}/1", False, "go"),
]

DOWNLOADS = [
    (f"{ORIGIN}/media/0123abcd.json", True),
    (f"{ORIGIN}/media/0123abcd.html", True),
    (f"{ORIGIN}/media/0123abcd.svg?x=1", True),
    (f"blob:{ORIGIN}/6f1e", True),                       # a table's own download, made in the page
    ("http://127.0.0.1:8584/media/0123abcd.json", False),
    ("http://127.0.0.2:8583/media/0123abcd.json", False),
    ("https://127.0.0.1:8583/media/0123abcd.json", False),
    (f"{ORIGIN}@example.org/media/0123abcd.json", False),        # the server's address as userinfo
    (f"{ORIGIN}.example.org/media/0123abcd.json", False),        # a host that begins with the server's
    (f"blob:{ORIGIN}.example.org/6f1e", False),
    ("http://x.127.0.0.1:8583/media/0123abcd.json", False),      # a host that only ends with the server's
    ("https://example.org/analysis.json", False),
    ("blob:https://example.org/6f1e", False),
    ("blob:null/6f1e", False),
    ("data:application/json,{}", False),
    ("file:///etc/hostname", False),
    ("javascript:alert(1)", False),
    ("", False),
    (None, False),
]


def test_the_window_rules_refuse_what_they_refused_with_downloads_on(monkeypatch):
    seen = []
    backend = _qt_backend()
    webview = _webview_stand_in(seen, backend)
    launcher = _launch(monkeypatch, webview)
    assert seen[-1][1]["ALLOW_DOWNLOADS"] is True, "the premise: downloads are on"
    rules = launcher._WindowRules(ORIGIN, SECRET)
    for url, main, want in NAVIGATIONS:
        assert rules.verdict(url, main) == want, (url, main)
    for url, want in DOWNLOADS:
        assert rules.may_download(url) is want, url
    # The Qt window, held as webview.start loaded it: navigation off the
    # server refused before any request leaves, with downloads on.
    page = backend.BrowserView.WebPage()
    for away in ("https://example.org/analysis.json", "http://127.0.0.1:8584/media/0123abcd.json",
                 "file:///etc/hostname"):
        assert page.acceptNavigationRequest(_QUrl(away), None, True) is False, away
        assert page.acceptNavigationRequest(_QUrl(away), None, False) is False, away
    # The window on macOS: a page found off the server after a load is
    # sent back; a download is not a load, and the window stays.
    loads = []
    window = types.SimpleNamespace(get_current_url=lambda: "https://example.org/analysis.json",
                                   load_url=loads.append)
    launcher._keep_to_the_server(window, rules, f"{ORIGIN}/?launch={SECRET}")()
    assert loads == [f"{ORIGIN}/?launch={SECRET}"]


def test_a_qt_download_goes_through_the_save_dialog_and_off_the_server_is_refused(monkeypatch):
    seen = []
    backend = _qt_backend()
    asked = []
    answer = {"path": "/Documents/my chart.json"}

    def getSaveFileName(parent, title, proposed, filter_):
        asked.append((title, proposed, filter_))
        return answer["path"], filter_

    backend.QFileDialog = types.SimpleNamespace(getSaveFileName=getSaveFileName)
    _launch(monkeypatch, _webview_stand_in(seen, backend))
    # The window webview.start made, after the launcher's holds: what its
    # constructor connected is what Qt calls on a download.
    (view,) = backend.windows
    assert len(view.downloadRequested.slots) == 1, "one handler connected, with downloads on"
    on_download_requested = view.downloadRequested.slots[0]
    # The server's own file: offered under the server's name, in the
    # downloads folder, and saved where the dialog says.
    saved = _Download(f"{ORIGIN}/media/0123abcd.json")
    on_download_requested(saved)
    assert asked == [("Save file", "/Downloads/analysis_Florence_1240-05-23.json", "*.json")]
    assert saved.accepted and not saved.cancelled
    assert (saved.downloadDirectory(), saved.downloadFileName()) == ("/Documents", "my chart.json")
    # A table's own download, made in the page on the server's origin.
    table = _Download(f"blob:{ORIGIN}/6f1e", name="table.csv")
    on_download_requested(table)
    assert table.accepted and asked[-1][2] == "*.csv"
    # A cancelled dialog: nothing saved, nothing else done.
    answer["path"] = ""
    dropped = _Download(f"{ORIGIN}/media/0123abcd.json")
    on_download_requested(dropped)
    assert dropped.cancelled and not dropped.accepted
    # Off the server: refused, and no dialog is shown.
    for url in ("https://example.org/analysis.json", "http://127.0.0.1:8584/media/0123abcd.json",
                "blob:https://example.org/6f1e", "data:application/json,{}", "file:///etc/hostname"):
        away = _Download(url)
        on_download_requested(away)
        assert away.cancelled and not away.accepted, url
    assert len(asked) == 3, "a dialog was shown for a download off the server"


# --- The one export button -------------------------------------------------------

FORMATS = [("HTML", ".html", "text/html", "_export_html"),
           ("JSON", ".json", "application/json", "_export_json"),
           ("Markdown", ".md", "text/markdown", "_export_md")]


def _popovers(at):
    """The sidebar's export buttons (it has other popovers: Set home)."""
    return [node for node in at.sidebar if getattr(node, "type", None) == "popover"
            and "export" in node.proto.popover.label.lower()]


def _drawn_downloads(monkeypatch):
    import streamlit
    drawn = []
    real = streamlit.download_button

    def capturing(label, data, *args, **kwargs):
        drawn.append(dict(kwargs, label=label, data=data))
        return real(label, data, *args, **kwargs)

    monkeypatch.setattr(streamlit, "download_button", capturing)
    return drawn


def test_one_export_button_offers_html_json_and_markdown(monkeypatch):
    drawn = _drawn_downloads(monkeypatch)
    at = make_app(page="chart").run(timeout=300)
    assert_no_exception(at, "the export")
    popovers = _popovers(at)
    assert [p.proto.popover.label for p in popovers] == ["Export analysis"], "one export button"
    assert not popovers[0].proto.popover.disabled
    inside = [node for node in popovers[0] if getattr(node, "type", None) == "download_button"]
    assert [b.label for b in inside] == [f[0] for f in FORMATS], "the three formats, HTML first, in the button"
    exported = [b for b in at.sidebar.download_button]
    assert [b.label for b in exported] == [f[0] for f in FORMATS], "no other download in the sidebar"
    assert inside[0].proto.help == "One file: opens in your browser, prints to PDF, keeps nothing beside it."
    assert [b.proto.ignore_rerun for b in inside] == [True, True, True], "a click reruns nothing"
    analysis = at.session_state["_analysis_export"]
    stem = f"analysis_{re.sub(r'[^\w.-]+', '-', analysis['chart']).strip('-')}_{analysis['input']['date']}"
    payloads = {"_export_html": at.session_state["_analysis_html"].encode("utf-8"),
                "_export_json": json.dumps(analysis, indent=1, ensure_ascii=False).encode("utf-8"),
                "_export_md": at.session_state["_analysis_markdown"].encode("utf-8")}
    ours = [d for d in drawn if d.get("key", "").startswith("_export_")]
    assert [d["label"] for d in ours] == [f[0] for f in FORMATS], ours
    assert [(d["key"], d["mime"], d["file_name"], bool(d.get("disabled"))) for d in ours] == [
        (key, mime, f"{stem}{suffix}", False) for _label, suffix, mime, key in FORMATS]
    assert [d["data"] for d in ours] == [payloads[key] for *_rest, key in FORMATS], \
        "the bytes differ from the session's export"
    assert json.loads(payloads["_export_json"])["input"]["date"] == "1240-05-23"


def test_with_no_chart_the_export_is_one_disabled_button_and_the_caption(monkeypatch):
    drawn = _drawn_downloads(monkeypatch)
    at = make_app(page="chart").run(timeout=300)
    assert "_analysis_export" in at.session_state, "the premise: the chart's export is in the session"
    at.session_state["date_input_key"] = "1240-05-23"
    at.session_state["manual_lat_key"] = 43.7792
    at.session_state["manual_lon_key"] = 11.2463
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = ""
    drawn.clear()
    at.run(timeout=300)
    assert_no_exception(at, "no chart")
    popovers = _popovers(at)
    assert [(p.proto.popover.label, p.proto.popover.disabled) for p in popovers] == [("Export analysis", True)]
    assert len(popovers[0].children) == 0, "nothing inside the disabled button"
    assert not at.sidebar.download_button and not [d for d in drawn if d.get("key", "").startswith("_export_")]
    assert "There is no chart to export; the input above says why." in [c.value for c in at.sidebar.caption]
    for key in ("_analysis_export", "_analysis_markdown", "_analysis_html"):
        assert key not in at.session_state, key


# --- Every download reruns nothing -----------------------------------------------

# Fourteen calls: the three exports, the Fixed stars page's copy of them, and
# eight calls that draw nine pictures -- the Chart page's wheel, the Timing
# page's wheel, its Ascendant's strip and one call in a loop over the two
# meridian points (two strips), the Releaser page's two strips and the Days
# page's two.
DOWNLOAD_CALLS = 14
SVG_CALLS = 8


def _download_calls(tree=None):
    """Every call in app.py whose callee is named download_button
    (st.download_button, or that name alone)."""
    tree = tree or ast.parse(APP_PATH.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and (getattr(node.func, "attr", None) == "download_button"
                 or getattr(node.func, "id", None) == "download_button")]


def _download_name_elsewhere(tree):
    """Each place in `tree` the name download_button is read, imported or
    bound other than as the callee of a call (an alias would be one), by
    line."""
    callees = {id(call.func) for call in _download_calls(tree)}
    return [node.lineno for node in ast.walk(tree) if id(node) not in callees and (
        (isinstance(node, ast.Attribute) and node.attr == "download_button")
        or (isinstance(node, ast.Name) and node.id == "download_button")
        or (isinstance(node, ast.alias) and "download_button" in (node.name.split(".")[-1], node.asname)))]


def _keyword(call, name):
    found = [kw.value for kw in call.keywords if kw.arg == name]
    return ast.literal_eval(found[0]) if len(found) == 1 and isinstance(found[0], ast.Constant) else found


def test_every_download_button_in_the_app_reruns_nothing():
    """Read from the source: every call on every page and branch, whether
    or not a chart drawn below reaches it. A button reached through another
    name is also seen where it is drawn, by
    test_every_download_button_drawn_reruns_nothing."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    assert _download_name_elsewhere(tree) == [], "download_button is named other than as a call's callee"
    calls = _download_calls(tree)
    assert len(calls) == DOWNLOAD_CALLS, [(c.lineno, ast.unparse(c.func)) for c in calls]
    assert [c.lineno for c in calls if any(kw.arg is None for kw in c.keywords)] == [], \
        "a ** argument could carry on_click"
    assert [(c.lineno, _keyword(c, "on_click")) for c in calls if _keyword(c, "on_click") != "ignore"] == [], \
        "a click on each saves the file and reruns nothing"
    assert sum(_keyword(c, "mime") == "image/svg+xml" for c in calls) == SVG_CALLS


def test_the_name_read_otherwise_is_found():
    """The instrument itself: an alias, an import of the name and the
    name's own call are told apart."""
    tree = ast.parse("import streamlit as st\n_dl = st.download_button\n_dl('a', b'')\n"
                     "from streamlit import download_button as grab\nst.download_button('b', b'')\n")
    assert _download_name_elsewhere(tree) == [2, 4] and len(_download_calls(tree)) == 1


# The download buttons each page draws, beside the three exports every page's
# sidebar holds: what runs, so a button reached through any name is counted.
PAGE_DOWNLOADS = {
    "chart": ["Download the wheel (SVG)"],
    "timing": ["Download this wheel (SVG)"] + ["Download this strip (SVG)"] * 3,
    "releaser": ["Download this strip (SVG)"] * 2,
    "days": ["Download this strip (SVG)"] * 2,
    # The page's own copy of the one export button, under its three formats.
    "fixed-stars": [f[0] for f in FORMATS],
    "sky": [],
    **{page: [] for page in ("dignities", "delineations", "configurations", "lots", "victors", "fardar", "reference",
                             "sources")},
}
NEW_YORK = (40.7128, -74.006)


def test_the_pages_run_below_are_every_page_of_the_app():
    pages = [kw.value.value for node in ast.walk(ast.parse(APP_PATH.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "Page"
             for kw in node.keywords if kw.arg == "url_path"]
    assert sorted(pages) == sorted(PAGE_DOWNLOADS)


@pytest.mark.parametrize("date, place", [("1240-05-23", None), ("1990-05-05", NEW_YORK)],
                         ids=["the example chart", "a modern chart"])
def test_every_download_button_drawn_reruns_nothing(date, place):
    """Run: on every page of the app, of two charts, each download button
    drawn -- the exports and the pictures, by whatever name its call was
    made -- is one whose click reruns nothing."""
    from streamlit.util import calc_hash
    at = make_app(date=date, page="chart")
    if place:
        at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = place
    pictures = 0
    for page, drawn in PAGE_DOWNLOADS.items():
        at._page_hash = calc_hash(page)
        at.run(timeout=300)
        assert_no_exception(at, f"the {page} page")
        buttons = at.get("download_button")
        assert sorted(b.label for b in buttons) == sorted([f[0] for f in FORMATS] + drawn), page
        assert [b.label for b in buttons if b.proto.ignore_rerun is not True] == [], \
            f"a click on these reruns the {page} page"
        pictures += len(buttons) - len(FORMATS)
    assert pictures == 9 + len(FORMATS)


def test_the_wheels_download_on_the_chart_page_reruns_nothing():
    at = make_app(page="chart").run(timeout=300)
    assert_no_exception(at, "the Chart page")
    wheel = [b for b in at.main.download_button if b.label == "Download the wheel (SVG)"]
    assert len(wheel) == 1, [b.label for b in at.main.download_button]
    assert wheel[0].proto.ignore_rerun is True, "a click on the wheel's download reruns its fragment"
