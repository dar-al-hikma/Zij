"""On macOS, a download saved over a file the Save panel agreed to replace replaces it.

pywebview's macOS window turns a link with the `download` attribute (every
download the app offers: the three exports, the eight pictures, a table's
CSV) into a WebKit download, whose delegate runs the Save panel and hands
the chosen path straight to WebKit. WebKit will not write over a file, so
choosing an existing file's name and confirming Replace saved nothing. The
launcher puts a subclass of pywebview's delegate in its place: pywebview's
own method runs (the same panel, folder and suggested name) with its
completion handler wrapped, so that after the panel's answer, and before
WebKit is told it, the chosen file is removed. Only a regular file or a
symbolic link (the link, never its target); a folder is left; a removal that
fails leaves the file, says so in one log line, and the download goes on to
fail as before. A cancelled panel clears nothing.

pywebview and PyObjC are not in the suite's venv: a stand-in of pywebview's
macOS backend, in the shape of pywebview 6.2.1's, records the panel; the
files are real ones in the test's own folder. The names the hold relies on
are checked against pywebview's own source by running this file as a script
where pywebview is installed (`python tests/test_macsave_downloads_2026_10_20.py`);
here, the version the lock pins is held to the one that source was read in.
"""
import ast
import importlib.util
import io
import logging
import os
import re
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_PATH = ROOT / "desktop_launcher.py"
ORIGIN = "http://127.0.0.1:8587"
SECRET = "macsave-secret-" + "m" * 30
OK, CANCEL = 1, 0
PINNED_PYWEBVIEW = "6.2.1"          # the version whose macOS backend the hold was read against


@pytest.fixture(autouse=True)
def _log_formatters_kept(monkeypatch):
    """The launcher puts a formatter on every root and pywebview handler;
    those of the test run's own are given back after each test."""
    for name in (None, "pywebview"):
        for handler in logging.getLogger(name).handlers:
            monkeypatch.setattr(handler, "formatter", handler.formatter)


def _load_launcher(monkeypatch, webview_module=None):
    monkeypatch.setitem(sys.modules, "webview", webview_module or types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_macsave", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NSURL:
    def __init__(self, path):
        self._path = path

    def path(self):
        return self._path


def _cocoa_backend(downloads, answer, name="webview.platforms.cocoa"):
    """pywebview's macOS backend as far as a download goes (6.2.1,
    platforms/cocoa.py): the navigation delegate makes the download's
    delegate by its name on BrowserView at each download, and that
    delegate's one method runs the Save panel in the downloads folder under
    WebKit's suggested name and hands the chosen path's URL, or None, to
    the completion handler. `answer` holds the panel's button and the path
    it returns; `lib.panels` records each panel."""
    lib = types.ModuleType(name)
    lib.panels = []

    class _Panel:
        def __init__(self):
            self.folder = self.name = None
            lib.panels.append(self)

        def setDirectoryURL_(self, url):
            self.folder = url.path()

        def setNameFieldStringValue_(self, name):
            self.name = name

        def runModal(self):
            return answer["button"]

        def filename(self):
            return answer["path"]

    lib.AppKit = types.SimpleNamespace(NSSavePanel=types.SimpleNamespace(savePanel=_Panel),
                                       NSFileHandlingPanelOKButton=OK)
    lib.Foundation = types.SimpleNamespace(
        NSSearchPathForDirectoriesInDomains=lambda which, mask, expand: [str(downloads)],
        NSDownloadsDirectory=15, NSUserDomainMask=1,
        NSURL=types.SimpleNamespace(fileURLWithPath_=_NSURL))

    class _NSObject:
        @classmethod
        def alloc(cls):
            return cls.__new__(cls)

        def init(self):
            return self

        def retain(self):
            return self

    class BrowserView:
        class DownloadDelegate(_NSObject):
            def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
                self, download, decideDestinationUsingResponse, suggestedFilename, completionHandler
            ):
                save_dlg = lib.AppKit.NSSavePanel.savePanel()
                directory = lib.Foundation.NSSearchPathForDirectoriesInDomains(
                    lib.Foundation.NSDownloadsDirectory, lib.Foundation.NSUserDomainMask, True)[0]
                save_dlg.setDirectoryURL_(lib.Foundation.NSURL.fileURLWithPath_(directory))
                save_dlg.setNameFieldStringValue_(suggestedFilename)
                if save_dlg.runModal() == lib.AppKit.NSFileHandlingPanelOKButton:
                    completionHandler(lib.Foundation.NSURL.fileURLWithPath_(save_dlg.filename()))
                else:
                    completionHandler(None)

        class BrowserDelegate(_NSObject):
            def webView_navigationAction_didBecomeDownload_(self, webview, navigationAction, download):
                download.setDelegate_(BrowserView.DownloadDelegate.alloc().init().retain())

    lib.BrowserView = BrowserView
    lib.pywebviews_delegate = BrowserView.DownloadDelegate
    lib.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)
    lib.js_bridge_call = lambda *a, **k: "called"
    return lib


class _Download:
    def __init__(self):
        self.delegate = None

    def setDelegate_(self, delegate):
        self.delegate = delegate


def _download(lib, suggested="analysis_Florence_1240-05-23.json", watch=None):
    """One download in the window as WebKit makes it: the navigation
    delegate gives it a delegate, which WebKit asks for a destination. The
    completion handler records what it is handed and, at that moment, what
    stands at `watch`."""
    download = _Download()
    lib.BrowserView.BrowserDelegate.alloc().init().webView_navigationAction_didBecomeDownload_(None, None, download)
    handed = []

    def completion_handler(url):
        handed.append((url if url is None else url.path(), None if watch is None else _what_is(watch)))

    download.delegate.download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
        download, object(), suggested, completion_handler)
    return download, handed


def _what_is(path):
    if os.path.islink(path):
        return "link"
    if os.path.isdir(path):
        return "folder"
    if os.path.isfile(path):
        return "file"
    return "nothing"


class _Hooks(list):
    def __iadd__(self, hook):
        self.append(hook)
        return self


def _launch(monkeypatch, backend):
    """The launcher's own path to its window, with a stand-in webview whose
    start loads `backend` as webview.start does; returns the launcher."""
    seen = []
    webview = types.ModuleType("webview")
    webview.settings = {"ALLOW_DOWNLOADS": False}
    webview.util = types.SimpleNamespace(js_bridge_call=lambda *a, **k: "called")
    webview.initialize = lambda gui=None: backend

    def create_window(title, url=None, **options):
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=lambda: None)

    def start(*args, **kwargs):
        webview.initialize(kwargs.get("gui"))
        seen.append("started")

    webview.create_window, webview.start = create_window, start
    launcher = _load_launcher(monkeypatch, webview)
    marked = threading.Event()

    class _Output:
        def __init__(self):
            self.lines = ["zij-server-listening 8587\n"]

        def readline(self, limit=-1):
            if self.lines:
                return self.lines.pop(0)
            marked.wait(10)
            return ""

        def __iter__(self):
            return iter(self.readline, "")

    proc = types.SimpleNamespace(stdout=_Output(), stdin=io.StringIO(), poll=lambda: None,
                                 wait=lambda *a: 0, kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8587)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: listening.wait(5))
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    try:
        launcher._launch_desktop_window()
    finally:
        marked.set()
    assert seen == ["started"], "the window's loop ran"
    return launcher


@pytest.fixture
def places(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    return downloads


def _held(monkeypatch, downloads, answer):
    lib = _cocoa_backend(downloads, answer)
    launcher = _launch(monkeypatch, lib)
    assert lib.BrowserView.DownloadDelegate is not lib.pywebviews_delegate, "the Cocoa hold was not taken"
    return launcher, lib


# --- The branch ----------------------------------------------------------------

def test_the_cocoa_hold_is_taken_for_a_backend_named_cocoa_and_only_then(monkeypatch, places):
    answer = {"button": OK, "path": str(places / "a.json")}
    launcher, lib = _held(monkeypatch, places, answer)
    assert issubclass(lib.BrowserView.DownloadDelegate, lib.pywebviews_delegate)
    monkeypatch.setattr(launcher, "_hold_the_qt_window", lambda lib, rules: None)
    monkeypatch.setattr(launcher, "_hold_the_gtk_window", lambda lib, rules: None)
    # The same shape under any other backend's name is left as pywebview made it.
    for name in ("webview.platforms.qt", "webview.platforms.gtk", "webview.platforms.winforms",
                 "webview.platforms.edgechromium", "webview.platforms.cef", "webview.platforms.android",
                 "webview.platforms.cocoa_x", "webview.platforms.notcocoa", "cocoa.platforms.gtk", ""):
        other = _cocoa_backend(places, answer, name=name)
        other.is_webengine = False
        launcher._hold_the_backend(other, launcher._WindowRules(ORIGIN, SECRET))
        assert other.BrowserView.DownloadDelegate is other.pywebviews_delegate, name
    # Held twice in one process: one class made, the same one in place.
    launcher._hold_the_backend(lib, launcher._WindowRules(ORIGIN, SECRET))
    assert lib.pywebviews_delegate.__subclasses__() == [lib.BrowserView.DownloadDelegate]
    assert list(launcher._cocoa_delegates.items()) == [(lib.pywebviews_delegate, lib.BrowserView.DownloadDelegate)]


# --- After the panel's answer --------------------------------------------------

def test_an_existing_file_is_gone_before_the_handler_runs_and_the_handler_gets_its_url(monkeypatch, places):
    target = places / "analysis_Florence_1240-05-23.json"
    target.write_text("the old export", encoding="utf-8")
    answer = {"button": OK, "path": str(target)}
    _launcher, lib = _held(monkeypatch, places, answer)
    _download_, handed = _download(lib, watch=target)
    assert handed == [(str(target), "nothing")], "the old file was still there when WebKit was told the path"
    # A new name: nothing to clear, the handler gets it as before.
    fresh = places / "new name.svg"
    answer["path"] = str(fresh)
    _download_, handed = _download(lib, suggested="wheel.svg", watch=fresh)
    assert handed == [(str(fresh), "nothing")]
    assert sorted(p.name for p in places.iterdir()) == [], "nothing else in the folder was touched"


def test_a_symbolic_link_is_removed_as_a_link_and_its_target_is_untouched(monkeypatch, places, tmp_path):
    kept = tmp_path / "kept.csv"
    kept.write_text("a,b\n1,2\n", encoding="utf-8")
    link = places / "table.csv"
    link.symlink_to(kept)
    folder_target = tmp_path / "a folder"
    folder_target.mkdir()
    (folder_target / "inside.txt").write_text("inside", encoding="utf-8")
    folder_link = places / "folder link.csv"
    folder_link.symlink_to(folder_target, target_is_directory=True)
    dangling = places / "dangling.csv"
    dangling.symlink_to(tmp_path / "not there")
    answer = {"button": OK, "path": str(link)}
    _launcher, lib = _held(monkeypatch, places, answer)
    for chosen in (link, folder_link, dangling):
        answer["path"] = str(chosen)
        _download_, handed = _download(lib, suggested="table.csv", watch=chosen)
        assert handed == [(str(chosen), "nothing")], chosen
    assert kept.read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert (folder_target / "inside.txt").read_text(encoding="utf-8") == "inside"
    assert not (tmp_path / "not there").exists()


def test_a_folder_at_the_path_is_left_and_the_handler_still_gets_the_url(monkeypatch, places):
    folder = places / "analysis.html"
    folder.mkdir()
    (folder / "inside.txt").write_text("inside", encoding="utf-8")
    answer = {"button": OK, "path": str(folder)}
    _launcher, lib = _held(monkeypatch, places, answer)
    _download_, handed = _download(lib, suggested="analysis.html", watch=folder)
    assert handed == [(str(folder), "folder")]
    assert (folder / "inside.txt").read_text(encoding="utf-8") == "inside"


@pytest.mark.parametrize("error", [PermissionError(1, "Operation not permitted"), OSError(30, "Read-only"),
                                   RuntimeError("anything else")])
def test_a_removal_that_raises_leaves_the_file_logs_one_line_and_the_handler_gets_the_url(monkeypatch, places,
                                                                                            caplog, error):
    target = places / "strip.svg"
    target.write_text("<svg/>", encoding="utf-8")
    answer = {"button": OK, "path": str(target)}
    launcher, lib = _held(monkeypatch, places, answer)

    def refuse(path, *args, **kwargs):
        raise error

    monkeypatch.setattr(launcher.os, "unlink", refuse)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    _download_, handed = _download(lib, suggested="strip.svg", watch=target)
    assert handed == [(str(target), "file")]
    assert target.read_text(encoding="utf-8") == "<svg/>"
    lines = [r for r in caplog.records if "Save panel" in r.getMessage()]
    assert len(lines) == 1 and lines[0].levelno == logging.WARNING, [r.getMessage() for r in caplog.records]
    assert str(target) not in lines[0].getMessage() and type(error).__name__ in lines[0].getMessage()


def test_a_cancelled_panel_clears_nothing_and_the_handler_gets_none(monkeypatch, places):
    target = places / "analysis_Florence_1240-05-23.md"
    target.write_text("the old export", encoding="utf-8")
    answer = {"button": CANCEL, "path": str(target)}       # the panel still holds the name it was showing
    _launcher, lib = _held(monkeypatch, places, answer)
    _download_, handed = _download(lib, suggested=target.name, watch=target)
    assert handed == [(None, "file")]
    assert target.read_text(encoding="utf-8") == "the old export"


def test_the_suggested_name_and_the_downloads_folder_reach_the_panel_as_before(monkeypatch, places):
    answer = {"button": CANCEL, "path": ""}
    _launcher, lib = _held(monkeypatch, places, answer)
    for suggested in ("analysis_Florence_1240-05-23.html", "wheel_Florence_1240-05-23.svg",
                      "2026-10-20T10-00_export.csv"):
        _download(lib, suggested=suggested)
    assert [(p.folder, p.name) for p in lib.panels] == [
        (str(places), "analysis_Florence_1240-05-23.html"),
        (str(places), "wheel_Florence_1240-05-23.svg"),
        (str(places), "2026-10-20T10-00_export.csv"),
    ]


# --- A pywebview whose names have moved ------------------------------------------

def test_moved_names_leave_pywebviews_delegate_and_the_window_opens(monkeypatch, places, caplog):
    answer = {"button": OK, "path": str(places / "a.json")}
    no_delegate = _cocoa_backend(places, answer)
    del no_delegate.BrowserView.DownloadDelegate
    _launch(monkeypatch, no_delegate)
    assert not hasattr(no_delegate.BrowserView, "DownloadDelegate")
    renamed = _cocoa_backend(places, answer)
    method = renamed.pywebviews_delegate.__dict__[
        "download_decideDestinationUsingResponse_suggestedFilename_completionHandler_"]
    del renamed.pywebviews_delegate.download_decideDestinationUsingResponse_suggestedFilename_completionHandler_
    renamed.pywebviews_delegate.download_decideDestination_ = method
    _launch(monkeypatch, renamed)
    assert renamed.BrowserView.DownloadDelegate is renamed.pywebviews_delegate
    not_a_function = _cocoa_backend(places, answer)
    not_a_function.pywebviews_delegate.download_decideDestinationUsingResponse_suggestedFilename_completionHandler_ = 3
    _launch(monkeypatch, not_a_function)
    assert not_a_function.BrowserView.DownloadDelegate is not_a_function.pywebviews_delegate
    # A class the runtime refuses to make: pywebview's delegate stays, one line said.
    refused = _cocoa_backend(places, answer)

    def _refuse(cls, **kwargs):
        raise TypeError("a class of that name already exists")

    refused.pywebviews_delegate.__init_subclass__ = classmethod(_refuse)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    _launch(monkeypatch, refused)
    assert refused.BrowserView.DownloadDelegate is refused.pywebviews_delegate
    said = [r.getMessage() for r in caplog.records if "replace" in r.getMessage()]
    assert len(said) == 1 and "TypeError" in said[0], said


# --- The Qt and GTK holds ----------------------------------------------------------

def test_the_qt_and_gtk_holds_are_unchanged_and_take_no_cocoa_hold(monkeypatch, places):
    launcher = _load_launcher(monkeypatch)
    rules = launcher._WindowRules(ORIGIN, SECRET)
    answer = {"button": OK, "path": str(places / "a.json")}
    gtk = _cocoa_backend(places, answer, name="webview.platforms.gtk")
    navigate = lambda self, view, decision, kind: "pywebview's"          # noqa: E731
    make = lambda self, window: None                                     # noqa: E731
    gtk.BrowserView.on_navigation, gtk.BrowserView.__init__ = navigate, make
    gtk.webkit = types.SimpleNamespace(PolicyDecisionType=types.SimpleNamespace(NAVIGATION_ACTION=0))
    calls = []
    monkeypatch.setattr(launcher, "_hold_the_gtk_window", lambda lib, r: calls.append(("gtk", lib, r)))
    monkeypatch.setattr(launcher, "_hold_the_qt_window", lambda lib, r: calls.append(("qt", lib, r)))
    launcher._hold_the_backend(gtk, rules)
    qt = _cocoa_backend(places, answer, name="webview.platforms.qt")
    qt.is_webengine = True
    launcher._hold_the_backend(qt, rules)
    assert calls == [("gtk", gtk, rules), ("qt", qt, rules)]
    assert gtk.BrowserView.DownloadDelegate is gtk.pywebviews_delegate
    assert qt.BrowserView.DownloadDelegate is qt.pywebviews_delegate


# --- The names, against pywebview's own source ----------------------------------------

def launcher_names():
    """The two names the launcher's Cocoa hold looks up, read from its
    source without importing it."""
    found = {}
    for node in ast.parse(LAUNCHER_PATH.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("_COCOA_DELEGATE", "_COCOA_DESTINATION"):
                    found[target.id] = node.value.value
    return found["_COCOA_DELEGATE"], found["_COCOA_DESTINATION"]


def _relied_on(delegate, method):
    """Each name the hold relies on in pywebview's macOS backend, with the
    pattern that finds it in that module's source."""
    return {
        "class BrowserView": re.compile(r"^class BrowserView\b", re.M),
        f"BrowserView.{delegate}, a class inside it": re.compile(rf"^    class {re.escape(delegate)}\(", re.M),
        f"{delegate}.{method}": re.compile(rf"^        def {re.escape(method)}\(", re.M),
        f"the delegate made by name: BrowserView.{delegate}.alloc()":
            re.compile(rf"\bBrowserView\.{re.escape(delegate)}\.alloc\(\)"),
        "the panel's answer handed to completionHandler": re.compile(r"\bcompletionHandler\(url\)"),
    }


def missing_names(source, names=None):
    return [what for what, pattern in _relied_on(*(names or launcher_names())).items() if not pattern.search(source)]


def _pins(text, package):
    return re.findall(rf"^{re.escape(package)}==([^\s;\\]+)", text, re.M)


def test_the_lock_pins_the_pywebview_whose_source_the_hold_was_read_against(monkeypatch):
    for name in ("requirements-desktop.txt", "requirements-build-macos.lock"):
        pins = _pins((ROOT / name).read_text(encoding="utf-8"), "pywebview")
        assert pins == [PINNED_PYWEBVIEW], (
            f"{name} pins pywebview {pins}: run this file as a script where that pywebview is installed, "
            "and read its platforms/cocoa.py for the names the launcher's Cocoa hold relies on")
    launcher = _load_launcher(monkeypatch)
    assert launcher_names() == (launcher._COCOA_DELEGATE, launcher._COCOA_DESTINATION) == (
        "DownloadDelegate", "download_decideDestinationUsingResponse_suggestedFilename_completionHandler_")


def test_the_text_check_sees_a_moved_name():
    shape = (
        "class BrowserView:\n"
        "    class DownloadDelegate(AppKit.NSObject):\n"
        "        def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(\n"
        "            self, download, response, name, completionHandler):\n"
        "                completionHandler(url)\n"
        "            download.setDelegate_(BrowserView.DownloadDelegate.alloc().init().retain())\n"
    )
    assert missing_names(shape) == []
    for old, new in [("class DownloadDelegate(", "class DownloadsDelegate("),
                     ("def download_decideDestinationUsingResponse_", "def download_decideDestinationForResponse_"),
                     ("BrowserView.DownloadDelegate.alloc()", "self.download_delegate()"),
                     ("completionHandler(url)", "completionHandler(destination)"),
                     ("class BrowserView:", "class CocoaView:")]:
        assert len(missing_names(shape.replace(old, new))) == 1, old


def _check_installed(path=None):
    """Run as a script where pywebview is installed (the macOS build's
    environment), or given the path of a pywebview's platforms/cocoa.py:
    that pywebview is the pinned version, and its macOS backend's source
    holds every name the launcher's Cocoa hold relies on."""
    if path is None:
        spec = importlib.util.find_spec("webview")
        path = Path(spec.submodule_search_locations[0]) / "platforms" / "cocoa.py"
    path = Path(path).resolve()
    records = sorted(path.parents[2].glob("pywebview-*.dist-info/METADATA"))
    versions = [re.search(r"^Version: (\S+)", r.read_text(encoding="utf-8"), re.M).group(1) for r in records]
    missing = missing_names(path.read_text(encoding="utf-8"))
    print(f"pywebview {versions}, {path}: " + ("every name the Cocoa hold relies on is there" if not missing
                                               else "missing: " + "; ".join(missing)))
    return 0 if not missing and versions == [PINNED_PYWEBVIEW] else 1


if __name__ == "__main__":
    sys.exit(_check_installed(sys.argv[1] if len(sys.argv) > 1 else None))
