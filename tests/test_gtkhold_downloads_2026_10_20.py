"""In the GTK window, a download is held as in the Qt window, and saving over a file asks first.

A run from source on Linux takes pywebview's GTK (WebKitGTK) window. With
downloads on, pywebview connects each download's decide-destination to its
own Save dialog, which it opened for any download at all: a data: link, or a
blob: of any origin. The launcher puts its own handler in that place, and
connects it itself, first, at every download (an emission hook on the web
context's download-started), so it answers however pywebview connects its
own: a download goes on to the dialog only when `_WindowRules.may_download`
would let the Qt window save it, and is otherwise cancelled with no dialog
and nothing written. pywebview's dialog did not ask before a file was replaced,
and choosing an existing file's name either cost the old file and saved
nothing (a download from the server) or wrote over it, through a link to the
file it points to (a blob:, a table's CSV), unasked. The dialog now asks
(GTK's own question), and the download may write over the very file the
reader agreed to replace, and no other (not one made again at its name);
a symbolic link agreed to be replaced is removed, not written through.

pywebview and PyGObject are not in the suite's venv: a stand-in of
pywebview's GTK backend, in the shape of pywebview 6.2.1's, records each
dialog, and a stand-in download writes real files in the test's own folder
as WebKitGTK 2.54 was seen to: over an existing file it may not write over,
a download from the server fails and removes the file, a data: one fails and
leaves it, and a blob: one writes over it anyway; a write follows a link;
the first place named is where it is written, and a cancel after that does
not stop a data: or blob: one; with no destination given and the signal
not handled, WebKitGTK's own handler saves in the downloads folder. The
names the hold relies on are checked against pywebview's own source by
running this file as a script where pywebview is installed
(`python tests/test_gtkhold_downloads_2026_10_20.py`).
"""
import ast
import hashlib
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
ORIGIN = "http://127.0.0.1:8589"
SECRET = "gtkhold-secret-" + "g" * 30
OK, CANCEL = -5, -6                  # Gtk.ResponseType
CONFIRM = 0                          # Gtk.FileChooserConfirmation.CONFIRM
PINNED_PYWEBVIEW = "6.2.1"           # the version whose GTK backend the hold was read against
BODY = b'{"chart": "Florence"}'

REFUSED = [
    "http://127.0.0.2:8589/media/a.json",                 # another origin
    "http://127.0.0.1:8590/media/a.json",                 # another port
    "http://127.0.0.1/media/a.json",                      # no port
    "http://localhost:8589/media/a.json",                 # localhost for 127.0.0.1
    "https://127.0.0.1:8589/media/a.json",                # https for http
    "http://user@127.0.0.1:8589/media/a.json",            # userinfo
    "http://127.0.0.1:8589@127.0.0.2/media/a.json",       # userinfo that names the server
    "http://127.0.0.1.example:8589/media/a.json",         # a host that begins with the server's
    "http://127.0.0.1:85890/media/a.json",                # a port that begins with the server's
    "data:application/json,%7B%7D",
    "blob:http://127.0.0.2:8589/5f0e",                    # a blob: of another origin
    "blob:https://127.0.0.1:8589/5f0e",
    "blob:null/5f0e",
    "file:///etc/hostname",
    "javascript:alert(1)",
    "about:blank",
    "",
    None,
]
LET_THROUGH = [f"{ORIGIN}/media/9a1c.json", f"blob:{ORIGIN}/5f0e-77"]


@pytest.fixture(autouse=True)
def _log_formatters_kept(monkeypatch):
    """The launcher puts a formatter on every root and pywebview handler;
    those of the test run's own are given back after each test."""
    for name in (None, "pywebview"):
        for handler in logging.getLogger(name).handlers:
            monkeypatch.setattr(handler, "formatter", handler.formatter)


def _add_emission_hook(gtype, name, hook):
    """PyGObject's GObject.add_emission_hook: the hook is run, before any
    handler, at each emission of the signal on any instance of the type,
    and kept while it returns true."""
    if not gtype.made or name not in gtype.SIGNALS:          # a type's signals: known once one is made
        raise TypeError(f"unknown signal name: {name}")
    gtype.emission_hooks.setdefault(name, []).append(hook)


def _load_launcher(monkeypatch, webview_module=None):
    monkeypatch.setitem(sys.modules, "webview", webview_module or types.ModuleType("webview"))
    repository = types.ModuleType("gi.repository")
    repository.GObject = types.SimpleNamespace(add_emission_hook=_add_emission_hook)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    spec = importlib.util.spec_from_file_location("desktop_launcher_gtkhold", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Signals:
    def __init__(self):
        self.handlers = {}

    def connect(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    def emit(self, name, *args):
        """As GObject's boolean signals: the type's emission hooks first,
        then handlers in order until one returns true; returns whether one
        did."""
        hooks = getattr(type(self), "emission_hooks", {}).get(name, [])
        for hook in list(hooks):
            if not hook(self, *args):
                hooks.remove(hook)
        for handler in self.handlers.get(name, []):
            if handler(self, *args):
                return True
        return False


class _Uri:
    def __init__(self, uri):
        self._uri = uri

    def get_uri(self):
        return self._uri


class _Download(_Signals):
    """A WebKitGTK download as far as the window goes: its request's and
    response's addresses, cancel, the destination and whether it may write
    over a file; `finish` writes as WebKitGTK does."""

    def __init__(self, request, response, home):
        super().__init__()
        self._request, self._response = _Uri(request), None if response is False else _Uri(response)
        self.home = home
        self.cancelled = False
        self.cancelled_after_a_place = False
        self.destination = None
        self.allow_overwrite = False
        self.written = []
        self.failed = None

    def get_request(self):
        return self._request

    def get_response(self):
        return self._response

    def cancel(self):
        self.cancelled = True
        self.cancelled_after_a_place = self.destination is not None

    def set_destination(self, uri):
        """WebKitGTK 2.54, seen live: the first place named is where the
        download is written, whatever a later handler names."""
        if self.destination is None:
            self.destination = uri

    def set_allow_overwrite(self, allowed):
        self.allow_overwrite = allowed

    def finish(self, downloads, suggested):
        """After decide-destination: WebKitGTK's own handler (the signal's
        last) puts a download with no destination in the downloads folder
        under its suggested name, unasked; then the file is written there.
        A cancel stops it, but not a data: or blob: one cancelled after a
        place was named (seen live: written there all the same)."""
        scheme = (self._request.get_uri() or "").split(":", 1)[0]
        if self.cancelled and not (self.cancelled_after_a_place and scheme in ("data", "blob")):
            return
        path = self.destination and _path_of(self.destination)
        if path is None:
            path = str(downloads / suggested)
        assert Path(path).resolve().is_relative_to(self.home), f"a download outside the test's folder: {path}"
        if os.path.lexists(path) and not self.allow_overwrite and scheme != "blob":
            # WebKitGTK 2.54, seen live: an http(s) download fails "File
            # exists" and then removes what stood there; a data: one fails
            # and leaves it.
            self.failed = "File exists"
            if scheme in ("http", "https"):
                if os.path.isdir(path) and not os.path.islink(path):
                    if not os.listdir(path):
                        os.rmdir(path)
                else:
                    os.unlink(path)
            return
        try:
            # Allowed, or a blob: one allowed or not (seen live): written
            # over in place, through a link to the file it points to.
            with open(path, "wb") as out:
                out.write(BODY)
        except IsADirectoryError:
            self.failed = "Is a directory"
            return
        self.written.append(path)


def _path_of(uri):
    assert uri.startswith("file://"), uri
    return uri[len("file://"):]


class _Context(_Signals):
    SIGNALS = ("download-started",)


def _gtk_backend(downloads, answers, name="webview.platforms.gtk", connects="by name"):
    """pywebview's GTK backend as far as a download goes (6.2.1,
    platforms/gtk.py): the window's web context connects download-started
    to `on_download_started`, which connects each download's
    decide-destination to `on_download_decide_destination` by name; that
    opens pywebview's Save dialog (a Gtk.FileChooserDialog in the downloads
    folder, under the suggested name, with no question before a file is
    replaced). `connects` is how `on_download_started` connects it: "by
    name" (6.2.1), "captured" (pywebview's own handler as the class had it,
    whatever stands under the name later: it names a place and returns
    nothing), or "nothing". `answers` are the reader's, one per dialog: the
    button, the path chosen, and, where GTK asks before replacing it,
    whether the reader agrees; then, optionally, what another program
    writes at the path after the reader picks it, and how: "removed first"
    (the file there removed before the reader picks its name, then made
    again) or "made again" (removed and made again after the question);
    `lib.dialogs` records each dialog."""
    lib = types.ModuleType(name)
    lib.dialogs = []
    response_type = types.SimpleNamespace(OK=OK, CANCEL=CANCEL)

    class FileChooserDialog:
        def __init__(self, title, parent, action, buttons):
            self.title, self.parent, self.action, self.buttons = title, parent, action, buttons
            self.folder = self.name = None
            self.confirms = False
            self.signals = _Signals()
            self.asked = []
            self.destroyed = False
            self.answer = answers.pop(0)
            lib.dialogs.append(self)

        def set_select_multiple(self, multiple):
            pass

        def set_current_folder(self, folder):
            self.folder = folder

        def set_current_name(self, name):
            self.name = name

        def set_do_overwrite_confirmation(self, confirms):
            self.confirms = confirms

        def connect(self, signal, handler):
            self.signals.connect(signal, lambda _s, *args: handler(self, *args))

        def run(self):
            """GTK 3: Save on a file that exists, with the question on,
            emits confirm-overwrite; its handler says CONFIRM and GTK asks;
            a no keeps the dialog open, where the reader picks again."""
            for step in self.answer:
                button, path, agrees = step[:3]
                self.chosen = path
                if button != OK:
                    return button
                if step[4:] == ("removed first",):        # another program, before the reader picks it
                    os.unlink(path)
                if self.confirms and os.path.lexists(path):
                    self.asked.append(path)
                    verdicts = [h(self.signals) for h in self.signals.handlers.get("confirm-overwrite", [])]
                    assert verdicts == [CONFIRM], verdicts
                    if not agrees:
                        continue
                if step[4:] == ("made again",):           # another program, after the question
                    os.unlink(path)
                if step[3:]:                              # another program puts a file there afterwards
                    Path(path).write_bytes(step[3])
                return OK
            return CANCEL

        def get_filename(self):
            return self.chosen

        def destroy(self):
            self.destroyed = True

    lib.gtk = types.SimpleNamespace(
        FileChooserDialog=FileChooserDialog,
        FileChooserAction=types.SimpleNamespace(OPEN=0, SAVE=1, SELECT_FOLDER=2),
        FileChooserConfirmation=types.SimpleNamespace(CONFIRM=CONFIRM, ACCEPT_FILENAME=1, SELECT_AGAIN=2),
        ResponseType=response_type, STOCK_CANCEL="gtk-cancel", STOCK_SAVE="gtk-save", STOCK_OPEN="gtk-open")
    lib.glib = types.SimpleNamespace(
        UserDirectory=types.SimpleNamespace(DIRECTORY_DOWNLOAD=2),
        get_user_special_dir=lambda which: str(downloads) if which == 2 else None,
        filename_to_uri=lambda path: "file://" + path)
    class WebContext(_Context):
        emission_hooks = {}
        made = False

        def __init__(self):
            super().__init__()
            type(self).made = True

    lib.webkit = types.SimpleNamespace(PolicyDecisionType=types.SimpleNamespace(
        NAVIGATION_ACTION=0, NEW_WINDOW_ACTION=1, RESPONSE=2), WebContext=WebContext)
    lib.FileDialog = types.SimpleNamespace(OPEN=10, FOLDER=20, SAVE=30)
    gtk = lib.gtk

    class _WebView:
        def __init__(self, context):
            self.settings = types.SimpleNamespace(props=types.SimpleNamespace(enable_media_stream=True))
            self.handlers = {}
            self.context = context

        def get_settings(self):
            return self.settings

        def get_context(self):
            return self.context

        def connect(self, name, handler):
            self.handlers[name] = handler

    class BrowserView:
        def __init__(self, window):
            self.window = "pywebview's window"
            self.localization = {"global.saveFile": "Save file"}
            self.context = WebContext()
            self.webview = _WebView(self.context)
            self.context.connect("download-started", self.on_download_started)

        def on_navigation(self, webview, decision, decision_type):
            decision.used = True

        def on_download_started(self, session, download):
            if connects == "by name":
                download.connect("decide-destination", self.on_download_decide_destination)
            elif connects == "captured":
                download.connect("decide-destination", lambda d, name: pywebviews_decide(self, d, name))

        def on_download_decide_destination(self, download, suggested_filename):
            destination = self.create_file_dialog(lib.FileDialog.SAVE, lib.glib.get_user_special_dir(
                lib.glib.UserDirectory.DIRECTORY_DOWNLOAD), False, suggested_filename, ())
            if destination:
                download.set_destination(lib.glib.filename_to_uri(destination[0]))
            else:
                download.cancel()

        def create_file_dialog(self, dialog_type, directory, allow_multiple, save_filename, file_types):
            dialog = gtk.FileChooserDialog(self.localization["global.saveFile"], self.window,
                                           gtk.FileChooserAction.SAVE,
                                           (gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL,
                                            gtk.STOCK_SAVE, gtk.ResponseType.OK))
            dialog.set_select_multiple(allow_multiple)
            dialog.set_current_folder(directory)
            dialog.set_current_name(save_filename)
            response = dialog.run()
            file_name = (dialog.get_filename(),) if response == gtk.ResponseType.OK else None
            dialog.destroy()
            return file_name

    lib.BrowserView = BrowserView
    lib.pywebviews_decide = pywebviews_decide = BrowserView.on_download_decide_destination
    lib.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)
    lib.js_bridge_call = lambda *a, **k: "called"
    return lib


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
            self.lines = ["zij-server-listening 8589\n"]

        def readline(self, limit=-1):
            if self.lines:
                return self.lines.pop(0)
            marked.wait(10)
            return ""

        def __iter__(self):
            return iter(self.readline, "")

    proc = types.SimpleNamespace(stdout=_Output(), stdin=io.StringIO(), poll=lambda: None,
                                 wait=lambda *a: 0, kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8589)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: listening.wait(5))
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    try:
        launcher._launch_desktop_window()
    finally:
        marked.set()
    assert seen == ["started"], "the window's loop ran"
    assert webview.settings["ALLOW_DOWNLOADS"] is True
    return launcher


@pytest.fixture
def places(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    return tmp_path, downloads


def _window(monkeypatch, places, answers, connects="by name"):
    home, downloads = places
    lib = _gtk_backend(downloads, answers, connects=connects)
    launcher = _launch(monkeypatch, lib)
    return launcher, lib, lib.BrowserView("the pywebview window")


def _download(view, places, request, response=None, suggested="analysis_Florence_1240-05-23.json"):
    """One download in the window, as WebKitGTK makes it: download-started
    on the web context, then decide-destination, then the write."""
    home, downloads = places
    download = _Download(request, request if response is None else response, home)
    view.context.emit("download-started", download)
    handled = download.emit("decide-destination", suggested)
    download.finish(downloads, suggested)
    return download, handled


def _files(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*"))


# --- The branch ----------------------------------------------------------------

def test_the_gtk_hold_is_taken_for_a_backend_named_gtk_and_only_then(monkeypatch, places):
    launcher, lib, view = _window(monkeypatch, places, [])
    assert lib.BrowserView.on_download_decide_destination is not lib.pywebviews_decide, "the GTK hold was not taken"
    monkeypatch.setattr(launcher, "_hold_the_qt_window", lambda lib, rules: None)
    monkeypatch.setattr(launcher, "_hold_the_cocoa_window", lambda lib: None)
    for name in ("webview.platforms.qt", "webview.platforms.cocoa", "webview.platforms.winforms",
                 "webview.platforms.edgechromium", "webview.platforms.cef", "webview.platforms.gtk_x",
                 "webview.platforms.notgtk", "gtk.platforms.qt", ""):
        other = _gtk_backend(places[1], [], name=name)
        other.is_webengine = True
        launcher._hold_the_backend(other, launcher._WindowRules(ORIGIN, SECRET))
        assert other.BrowserView.on_download_decide_destination is other.pywebviews_decide, name


def test_moved_names_fail_and_the_window_does_not_open(monkeypatch, places):
    launcher = _load_launcher(monkeypatch)
    rules = launcher._WindowRules(ORIGIN, SECRET)
    for gone in ("on_download_started", "on_download_decide_destination"):
        lib = _gtk_backend(places[1], [])
        delattr(lib.BrowserView, gone)
        with pytest.raises(AttributeError, match=gone):
            launcher._hold_the_backend(lib, rules)


# --- The hold --------------------------------------------------------------------

@pytest.mark.parametrize("url", REFUSED, ids=repr)
def test_a_download_the_qt_window_would_refuse_is_cancelled_with_no_dialog(monkeypatch, places, url):
    home, downloads = places
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(downloads / "a.json"), True)]])
    assert launcher._WindowRules(ORIGIN, SECRET).may_download(url) is False, "the predicate moved"
    download, handled = _download(view, places, url)
    assert lib.dialogs == [], "a dialog opened"
    assert download.cancelled and download.destination is None and handled
    assert _files(home) == ["Downloads"], "something was written"


def test_a_response_off_the_server_is_refused_though_the_request_was_on_it(monkeypatch, places):
    home, downloads = places
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(downloads / "a.json"), True)]])
    download, handled = _download(view, places, LET_THROUGH[0], response="http://127.0.0.2:8589/a.json")
    assert lib.dialogs == [] and download.cancelled and handled
    assert _files(home) == ["Downloads"]


@pytest.mark.parametrize("url", LET_THROUGH)
def test_the_servers_own_file_and_its_own_blob_reach_the_dialog_and_are_saved(monkeypatch, places, url):
    home, downloads = places
    chosen = str(downloads / "analysis_Florence_1240-05-23.json")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, chosen, True)]])
    download, handled = _download(view, places, url)
    (dialog,) = lib.dialogs
    assert (dialog.title, dialog.parent, dialog.action) == ("Save file", view.window, 1)
    assert dialog.buttons == ("gtk-cancel", CANCEL, "gtk-save", OK)
    assert (dialog.folder, dialog.name) == (str(downloads), "analysis_Florence_1240-05-23.json")
    assert dialog.confirms is True and dialog.destroyed
    assert handled and not download.cancelled and download.destination == "file://" + chosen
    assert download.allow_overwrite is False and download.written == [chosen]
    assert Path(chosen).read_bytes() == BODY


def test_a_cancelled_dialog_writes_nothing(monkeypatch, places):
    home, downloads = places
    launcher, lib, view = _window(monkeypatch, places, [[(CANCEL, None, False)]])
    download, handled = _download(view, places, LET_THROUGH[0])
    assert len(lib.dialogs) == 1 and lib.dialogs[0].destroyed
    assert download.cancelled and download.destination is None and handled
    assert _files(home) == ["Downloads"], "WebKitGTK's own handler saved it"


def test_a_dialog_that_fails_cancels_the_download_and_says_so_in_one_line(monkeypatch, places, caplog):
    home, downloads = places
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(downloads / "a.json"), True)]])

    def _broken(self):
        raise RuntimeError("no display")

    lib.gtk.FileChooserDialog.run = _broken
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, LET_THROUGH[0])
    assert download.cancelled and handled and lib.dialogs[0].destroyed
    assert _files(home) == ["Downloads"]
    said = [r.getMessage() for r in caplog.records if "not saved" in r.getMessage()]
    assert said == ["The download was not saved (RuntimeError)."], said


# --- However pywebview connects its handler ---------------------------------------

REFUSED_HERE = ["data:application/json,%7B%7D", "blob:http://127.0.0.2:8589/5f0e", "http://127.0.0.2:8589/media/a.json"]
SHAPES = ["by name", "captured", "nothing"]


@pytest.mark.parametrize("connects", SHAPES)
@pytest.mark.parametrize("url", REFUSED_HERE, ids=repr)
def test_a_refused_download_is_cancelled_with_no_dialog_however_pywebview_connects_its_handler(
        monkeypatch, places, connects, url):
    """pywebview's own handler, where it is not the hold, would open its
    dialog and name a place, and WebKitGTK writes at the first place named:
    the hold is connected before it, answers, and ends the emission."""
    home, downloads = places
    picked = str(downloads / "a.json")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, picked, True)], [(OK, picked, True)]], connects)
    for _ in range(2):                                  # the hook stays for the next download
        download, handled = _download(view, places, url)
        assert download.cancelled and handled and download.destination is None
    assert lib.dialogs == [], "a dialog opened"
    assert _files(home) == ["Downloads"], "something was written"


@pytest.mark.parametrize("connects", SHAPES)
def test_the_hold_is_each_downloads_first_handler_and_shows_one_dialog(monkeypatch, places, connects):
    """With pywebview 6.2.1 both connections reach the hold; with a captured
    handler, the hold comes first; with none, the hold's is the only one.
    The first answers and ends the emission: one dialog."""
    home, downloads = places
    chosen = str(downloads / "analysis_Florence_1240-05-23.json")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, chosen, True)], [(OK, chosen, True)]], connects)
    download = _Download(LET_THROUGH[0], LET_THROUGH[0], home)
    view.context.emit("download-started", download)
    assert len(download.handlers["decide-destination"]) == (1 if connects == "nothing" else 2)
    assert download.emit("decide-destination", "analysis_Florence_1240-05-23.json")
    download.finish(downloads, "analysis_Florence_1240-05-23.json")
    (dialog,) = lib.dialogs
    assert dialog.confirms and download.written == [chosen]


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_captured_pywebview_handler_does_not_decide_where_a_download_is_written(monkeypatch, places, url):
    """pywebview's own dialog, which does not ask, would name an existing
    file first; the hold's dialog is the one shown, and its answer stands."""
    home, downloads = places
    old, new = downloads / "a.json", downloads / "b.json"
    old.write_bytes(b"OLD")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(new), True)], [(OK, str(old), True)]],
                                  "captured")
    download, handled = _download(view, places, url)
    (holds,) = lib.dialogs
    assert holds.confirms and handled
    assert download.destination == "file://" + str(new) and download.allow_overwrite is False
    assert old.read_bytes() == b"OLD" and new.read_bytes() == BODY


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_captured_pywebview_handler_then_cancel_in_the_holds_dialog_writes_nothing(monkeypatch, places, url):
    home, downloads = places
    old = downloads / "a.json"
    old.write_bytes(b"OLD")
    launcher, lib, view = _window(monkeypatch, places, [[(CANCEL, None, False)], [(OK, str(old), True)]],
                                  "captured")
    download, handled = _download(view, places, url)
    assert len(lib.dialogs) == 1 and download.cancelled and handled and download.destination is None
    assert old.read_bytes() == b"OLD" and _files(home) == ["Downloads", "Downloads/a.json"]


def test_a_download_from_a_context_no_held_window_has_is_cancelled_and_says_so(monkeypatch, places, caplog):
    home, downloads = places
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(downloads / "a.json"), True)]])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download = _Download(LET_THROUGH[0], LET_THROUGH[0], home)
    lib.webkit.WebContext().emit("download-started", download)
    assert download.cancelled and lib.dialogs == []
    assert _said(caplog) == ["The download was not saved (ValueError)."]


def test_the_hold_hooks_webkits_download_started_once_and_a_moved_signal_fails(monkeypatch, places):
    """WebKitGTK knows a web context's signals once one has been made
    (seen live: at pywebview's start, before any window, the hook is
    refused), so the first window's constructor adds it, once."""
    launcher = _load_launcher(monkeypatch)
    lib = _gtk_backend(places[1], [])
    launcher._hold_the_backend(lib, launcher._WindowRules(ORIGIN, SECRET))
    assert lib.webkit.WebContext.emission_hooks == {}
    lib.BrowserView("the first window")
    lib.BrowserView("a second window")
    assert {name: len(hooks) for name, hooks in lib.webkit.WebContext.emission_hooks.items()} == \
        {"download-started": 1}
    moved = _gtk_backend(places[1], [])
    moved.webkit.WebContext.SIGNALS = ("download-begun",)
    launcher._hold_the_backend(moved, launcher._WindowRules(ORIGIN, SECRET))
    with pytest.raises(TypeError, match="download-started"):
        moved.BrowserView("the window")


# --- Saving over a file ------------------------------------------------------------

@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_saving_over_a_file_asks_and_replaces_it_only_when_the_reader_agrees(monkeypatch, places, url):
    home, downloads = places
    old = downloads / "analysis_Florence_1240-05-23.json"
    old.write_bytes(b"OLD")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(old), True)]])
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(old)], "GTK did not ask"
    assert download.allow_overwrite is True and download.failed is None
    assert old.read_bytes() == BODY


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_no_to_the_question_then_a_new_name_leaves_the_old_file(monkeypatch, places, url):
    home, downloads = places
    old, new = downloads / "a.json", downloads / "b.json"
    old.write_bytes(b"OLD")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(old), False), (OK, str(new), True)]])
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(old)]
    assert download.allow_overwrite is False and download.written == [str(new)]
    assert old.read_bytes() == b"OLD" and new.read_bytes() == BODY


def test_a_no_to_the_question_then_another_file_agreed_replaces_only_that_one(monkeypatch, places):
    home, downloads = places
    first, second = downloads / "a.json", downloads / "b.json"
    first.write_bytes(b"FIRST")
    second.write_bytes(b"SECOND")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(first), False), (OK, str(second), True)]])
    download, handled = _download(view, places, LET_THROUGH[0])
    assert lib.dialogs[0].asked == [str(first), str(second)]
    assert download.allow_overwrite is True
    assert first.read_bytes() == b"FIRST" and second.read_bytes() == BODY


NOT_AGREED = "The download was not saved over a file not agreed to be replaced."


def _said(caplog):
    return [r.getMessage() for r in caplog.records if "not saved" in r.getMessage()]


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_file_the_reader_was_not_asked_about_is_left_and_the_download_cancelled(monkeypatch, places, caplog, url):
    """A file put at the chosen name after the dialog answered (by another
    program): the reader agreed to no replacement. Handed on, WebKitGTK
    would fail and remove it; the download is cancelled instead."""
    home, downloads = places
    chosen = downloads / "a.json"
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(chosen), True, b"made after the dialog")]])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == []
    assert download.cancelled and download.destination is None and handled
    assert chosen.read_bytes() == b"made after the dialog"
    assert _said(caplog) == [NOT_AGREED]


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_no_to_the_question_then_a_new_name_another_program_fills_is_left(monkeypatch, places, url):
    """The question was asked, of another file: that is no agreement to
    replace the one at the name finally chosen."""
    home, downloads = places
    old, new = downloads / "a.json", downloads / "b.json"
    old.write_bytes(b"OLD")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(old), False),
                                                         (OK, str(new), True, b"made after the dialog")]])
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(old)]
    assert download.cancelled and download.destination is None
    assert old.read_bytes() == b"OLD" and new.read_bytes() == b"made after the dialog"


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_no_then_the_same_name_again_after_another_program_made_it_again_is_left(monkeypatch, places, caplog, url):
    """A no to the question about a file; another program removes it, so
    the reader's second pick of its name meets no question; the program
    makes it again before the hold looks. Asked about once, the name was
    never agreed to: the file made again is left."""
    home, downloads = places
    old = downloads / "a.json"
    old.write_bytes(b"OLD")
    os.link(old, home / "the first a.json")         # held, so that its inode is not given to the new one
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(old), False),
                                                         (OK, str(old), True, b"MADE AGAIN", "removed first")]])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(old)]
    assert download.cancelled and download.destination is None and download.allow_overwrite is False
    assert old.read_bytes() == b"MADE AGAIN"
    assert _said(caplog) == [NOT_AGREED]


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_file_agreed_to_then_made_again_by_another_program_is_left(monkeypatch, places, caplog, url):
    """The agreement is to replace the very file GTK asked about, not
    whatever stands at its name when the download is handed on."""
    home, downloads = places
    old = downloads / "a.json"
    old.write_bytes(b"OLD")
    os.link(old, home / "the first a.json")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(old), True, b"MADE AGAIN", "made again")]])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(old)]
    assert download.cancelled and download.destination is None
    assert old.read_bytes() == b"MADE AGAIN" and _said(caplog) == [NOT_AGREED]


@pytest.mark.parametrize("url", LET_THROUGH, ids=["media", "blob"])
def test_a_symbolic_link_agreed_to_be_replaced_is_replaced_and_its_target_is_untouched(monkeypatch, places, url):
    home, downloads = places
    target = home / "elsewhere" / "keep.txt"
    target.parent.mkdir()
    target.write_bytes(b"KEEP")
    link = downloads / "link.json"
    link.symlink_to(target)
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(link), True)]])
    download, handled = _download(view, places, url)
    assert lib.dialogs[0].asked == [str(link)]
    assert download.allow_overwrite is False, "a removed link's name was opened to being written over"
    assert not link.is_symlink() and link.read_bytes() == BODY
    assert target.read_bytes() == b"KEEP"


@pytest.mark.parametrize("full", [True, False], ids=["folder", "empty folder"])
def test_a_folder_at_the_chosen_path_is_left_and_the_download_cancelled(monkeypatch, places, caplog, full):
    home, downloads = places
    folder = downloads / "a.json"
    folder.mkdir()
    if full:
        (folder / "inside").write_bytes(b"IN")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(folder), True)]])
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, LET_THROUGH[0])
    assert download.cancelled and download.destination is None and download.allow_overwrite is False
    assert folder.is_dir() and _files(folder) == (["inside"] if full else [])
    assert _said(caplog) == [NOT_AGREED]


def test_a_link_that_cannot_be_removed_cancels_and_says_so(monkeypatch, places, caplog):
    home, downloads = places
    link = downloads / "link.json"
    link.symlink_to(home / "nowhere")
    launcher, lib, view = _window(monkeypatch, places, [[(OK, str(link), True)]])

    def _refused(path, *args, **kwargs):
        raise PermissionError(13, "refused")

    monkeypatch.setattr(launcher.os, "unlink", _refused)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    download, handled = _download(view, places, LET_THROUGH[0])
    assert download.cancelled and handled and link.is_symlink()
    assert _said(caplog) == ["The download was not saved (PermissionError)."]


# --- The other holds ---------------------------------------------------------------

def _body_digest(source, name):
    """A function's or class's code with its docstrings left out, as ast
    reads it."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            for inner in ast.walk(node):
                if isinstance(inner, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and inner.body and \
                        isinstance(inner.body[0], ast.Expr) and isinstance(inner.body[0].value, ast.Constant):
                    inner.body = inner.body[1:] or [ast.Pass()]
            return hashlib.sha256(ast.dump(node).encode()).hexdigest()[:16]
    raise AssertionError(f"{name} is not in the launcher")


# The code of each hold the GTK hold leaves alone, docstrings aside, as it
# stood when the GTK hold was built: a change to any of them is its own work.
UNCHANGED = {
    # Changed once since: the "Opening…" page let in while the window shows it
    # (is_the_opening), its own work, pinned in test_opening_2026_11_08.py.
    "_WindowRules": "2934bdf195a82aeb",
    "_hold_the_qt_window": "e79834effdc5de9d",
    "_save_the_download": "476437aef1c19b93",
    "_clear_the_chosen_file": "2742ea1c5653811c",
    "_hold_the_cocoa_window": "ff3b7eb2d0f8efdb",
    "_close_the_windows_doors": "ecab4f813a1cedce",
    "_keep_to_the_server": "7b0776006cd2d4a1",
    "_hold_the_backend": "3d1ea3b151a4f5bb",
}


def test_the_qt_and_cocoa_holds_and_the_window_rules_are_unchanged():
    source = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert {name: _body_digest(source, name) for name in UNCHANGED} == UNCHANGED


def test_the_digest_sees_a_changed_line_and_not_a_changed_docstring():
    source = 'def f(x):\n    """Says."""\n    return x\n'
    same = _body_digest(source, "f")
    assert _body_digest(source.replace("Says.", "Says more."), "f") == same
    assert _body_digest(source.replace("return x", "return not x"), "f") != same


def test_the_gtk_window_takes_no_qt_or_cocoa_download_hold(monkeypatch, places):
    launcher, lib, view = _window(monkeypatch, places, [])
    assert not hasattr(lib.BrowserView, "on_download_requested")
    assert not hasattr(lib.BrowserView, "DownloadDelegate")
    assert launcher._cocoa_delegates == {}


# --- The names, against pywebview's own source ------------------------------------

RELIED_ON = {
    "download-started connected to on_download_started":
        re.compile(r"\.connect\('download-started', self\.on_download_started\)"),
    "on_download_started(self, session, download)":
        re.compile(r"^    def on_download_started\(self, session, download\):", re.M),
    "decide-destination connected to on_download_decide_destination by name":
        re.compile(r"download\.connect\('decide-destination', self\.on_download_decide_destination\)"),
    "on_download_decide_destination(self, download, suggested_filename)":
        re.compile(r"^    def on_download_decide_destination\(self, download, suggested_filename\):", re.M),
    "self.window": re.compile(r"^        self\.window = gtk\.", re.M),
    "self.localization": re.compile(r"^        self\.localization = ", re.M),
    "the Save dialog's title": re.compile(r"self\.localization\['global\.saveFile'\]"),
    "Gtk as gtk": re.compile(r"^from gi\.repository import Gtk as gtk\b", re.M),
    "WebKit2 as webkit": re.compile(r"^from gi\.repository import WebKit2 as webkit\b", re.M),
    "self.webview, a WebKit2 WebView": re.compile(r"^        self\.webview = webkit\.WebView\(", re.M),
    "GLib as glib": re.compile(r"^from gi\.repository import GLib as glib\b", re.M),
    "BrowserView": re.compile(r"^class BrowserView\b", re.M),
}


def missing_names(source):
    return [what for what, pattern in RELIED_ON.items() if not pattern.search(source)]


def _pins(text, package):
    return re.findall(rf"^{re.escape(package)}==([^\s;\\]+)", text, re.M)


def test_a_source_run_pins_the_pywebview_whose_gtk_backend_the_hold_was_read_against():
    pins = _pins((ROOT / "requirements-desktop.txt").read_text(encoding="utf-8"), "pywebview")
    assert pins == [PINNED_PYWEBVIEW], (
        f"requirements-desktop.txt pins pywebview {pins}: run this file as a script where that pywebview is "
        "installed, and read its platforms/gtk.py for the names the launcher's GTK hold relies on")


def test_the_text_check_sees_a_moved_name():
    shape = (
        "from gi.repository import GLib as glib\n"
        "from gi.repository import Gtk as gtk\n"
        "from gi.repository import WebKit2 as webkit\n"
        "class BrowserView:\n"
        "    def __init__(self, window):\n"
        "        self.window = gtk.ApplicationWindow()\n"
        "        self.webview = webkit.WebView(user_content_manager=self.manager)\n"
        "        self.localization = window.localization\n"
        "            web_context.connect('download-started', self.on_download_started)\n"
        "    def on_download_started(self, session, download):\n"
        "        download.connect('decide-destination', self.on_download_decide_destination)\n"
        "    def on_download_decide_destination(self, download, suggested_filename):\n"
        "            title = self.localization['global.saveFile']\n"
    )
    assert missing_names(shape) == []
    for old, new in [("'download-started', self.on_download_started", "'download-started', self.on_download"),
                     ("def on_download_started(self, session", "def on_download_begun(self, session"),
                     ("'decide-destination', self.on_download_decide_destination",
                      "'decide-destination', self._decide"),
                     ("def on_download_decide_destination(", "def on_decide_destination("),
                     ("self.window = gtk.", "self.main_window = gtk."),
                     ("self.localization = ", "self.strings = "),
                     ("['global.saveFile']", "['save']"),
                     ("Gtk as gtk", "Gtk"), ("GLib as glib", "GLib"), ("WebKit2 as webkit", "WebKit2"),
                     ("self.webview = webkit.WebView(", "self.view = webkit.WebView("),
                     ("class BrowserView:", "class GtkView:")]:
        assert len(missing_names(shape.replace(old, new))) == 1, old


def _check_installed(path=None):
    """Run as a script where pywebview is installed, or given the path of a
    pywebview's platforms/gtk.py: that pywebview is the pinned version, and
    its GTK backend's source holds every name the launcher's GTK hold
    relies on."""
    if path is None:
        spec = importlib.util.find_spec("webview")
        path = Path(spec.submodule_search_locations[0]) / "platforms" / "gtk.py"
    path = Path(path).resolve()
    records = sorted(path.parents[2].glob("pywebview-*.dist-info/METADATA"))
    versions = [re.search(r"^Version: (\S+)", r.read_text(encoding="utf-8"), re.M).group(1) for r in records]
    missing = missing_names(path.read_text(encoding="utf-8"))
    print(f"pywebview {versions}, {path}: " + ("every name the GTK hold relies on is there" if not missing
                                               else "missing: " + "; ".join(missing)))
    return 0 if not missing and versions == [PINNED_PYWEBVIEW] else 1


if __name__ == "__main__":
    sys.exit(_check_installed(sys.argv[1] if len(sys.argv) > 1 else None))
