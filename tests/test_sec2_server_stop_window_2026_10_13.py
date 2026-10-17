"""The server's stop and the window (the owner's rulings 140, 150 and 157).

The desktop launcher starts a Streamlit server child on a loopback port and
shows it in a pywebview window. Before this lane:

* the server outlived its launcher whenever the launcher ended without
  closing its window -- SIGTERM, SIGHUP, a kill, macOS's Quit -- and the
  orphan ignored SIGTERM itself (its output went to a pipe nobody read); a
  normal close sent the child one terminate() and never waited, which on
  Windows ends it at once, its own cleanup skipped;
* the window opened whatever answered on the port with any HTTP status, so
  a process that bound the port first was shown as the app;
* the window gave any page a bridge into Python, went anywhere it was sent,
  handed any link to the system's opener and, on Qt, granted the camera and
  microphone without asking;
* its log was written beside the program, at DEBUG, through any link;
* the launch's secret stayed in the window's address for the whole launch;
* the atlas's connection was left open, and a comment said a quarter of a
  second bounded more than the wait for a lock.

Now the launcher asks its child to stop by closing the child's input, waits,
kills and reaps; SIGTERM and SIGHUP to the launcher do the same; the child
ends with its launcher however that ends; the window opens only once the
child has said, on the pipe only it writes to, that it is listening on the
port; the window has no bridge, stays on the server's origin, opens only
https links in the system's browser and refuses every permission; the log
is in the data folder, owner-only; the address drops the secret once the
first page is in.

The live tests start servers only on loopback, on a small fixed pool of
ports, and send nothing beyond it. A port is claimed for the machine, so
that another run of these tests, another user's included, does not start a
server on it at the same time.
"""
import ast
import enum
import http.server
import importlib.util
import io
import logging
import os
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, ENGINE_PATH, EXECUTABLE_DIR, engine_files
from loopback_ports import bindable, claim, claimed_port, port_taken

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"
SECRET = "stop-secret-" + "k" * 31
# A small fixed pool, so that every server these tests start is on a port
# known beforehand, and below the range the system hands out for outgoing
# connections; a test holds its port alone while it runs, against every run
# of these tests on the machine (port's claim).
PORTS = range(8581, 8585)


@pytest.fixture(autouse=True)
def _log_formatters_kept(monkeypatch):
    """The launcher puts a formatter on every root and pywebview handler;
    those of the test run's own are given back after each test."""
    for name in (None, "pywebview"):
        for handler in logging.getLogger(name).handlers:
            monkeypatch.setattr(handler, "formatter", handler.formatter)


def _load_launcher(monkeypatch, webview_module=None):
    """desktop_launcher.py as a module. pywebview is not in the suite's
    venv; a stand-in is put in its place."""
    monkeypatch.setitem(sys.modules, "webview", webview_module or types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_sec2", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The pool's claims, shared with the other tests that start a server on a
# loopback port (tests/loopback_ports.py).
_bindable, _claim, _port_taken = bindable, claim, port_taken


@pytest.fixture
def port(tmp_path_factory):
    """A port of PORTS, claimed by this test alone among the runs on the
    machine (_claim) and free when the test starts. The claim keeps every
    run of these tests off it until the test ends; what is left is a
    program outside them binding the port between this check and the
    child's bind, which fails the test by name (_port_taken)."""
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "sec2-ports")


def _alive(pid):
    """Whether `pid` is a live process (a zombie is not)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(") ", 1)[1][0] != "Z"
    except (FileNotFoundError, IndexError):
        return False


def _gone_within(pid, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _end(*pids):
    for pid in pids:
        if pid and _alive(pid):
            os.kill(pid, signal.SIGKILL)


# --- A launcher run whole, its window a stand-in --------------------------

STUB_WEBVIEW = '''\
import os, threading

class _Hooks(list):
    def __iadd__(self, hook):
        self.append(hook)
        return self

class _Window:
    def __init__(self):
        self.events = type("Events", (), {})()
        self.events.loaded, self.events.closing = _Hooks(), _Hooks()
        self.closed = threading.Event()
    def destroy(self):
        self.closed.set()

def create_window(title, url, **options):
    with open(os.environ["ZIJ_STUB_RECORD"], "a") as f:
        f.write("window " + url.split("?")[0] + "\\n")
    return _Window()

def start(func=None, window=None, **options):
    if os.environ.get("ZIJ_STUB_CLOSE"):
        for hook in window.events.closing:
            hook()
        return
    window.closed.wait()
'''

DRIVER = '''\
import os, subprocess, sys
sys.path.insert(0, sys.argv[1])
import desktop_launcher as launcher
port, record = int(sys.argv[2]), sys.argv[3]

def note(text):
    with open(record, "a") as f:
        f.write(text + "\\n")

launcher._free_port = lambda: port
start, stop = launcher._start_server, launcher._stop_server

def _start(p, secret):
    proc = start(p, secret)
    note(f"child {proc.pid}")
    if os.environ.get("ZIJ_HOLD_THE_PIPE"):
        # Another process holds the child's input open, so that only the
        # death signal can tell the child its launcher is gone.
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                  pass_fds=[proc.stdin.fileno()])
        note(f"holder {holder.pid}")
    return proc

def _stop(proc):
    stop(proc)
    note(f"stopped {proc.returncode}")

launcher._start_server, launcher._stop_server = _start, _stop
launcher._launch_desktop_window()
'''


def _stub(tmp_path):
    folder = tmp_path / "stub"
    (folder / "webview").mkdir(parents=True, exist_ok=True)
    (folder / "webview" / "__init__.py").write_text(STUB_WEBVIEW)
    return folder


# --- A child's temporary folder ---------------------------------------------
#
# The engine makes its ephemeris folder in the temporary folder it is given
# (its prefix and mkdtemp's eight characters) and refuses a folder name over
# its limit in bytes, saying so on the page. A folder under tmp_path grows
# with the temporary folder the run inherits, the worker's name and
# pytest's own count, so a child given one fails or passes by how long that
# is. Every child here is given a short folder of its own instead, made
# under /tmp (or the platform's own temporary folder, where /tmp will not
# do and that one is short) and removed when its test ends.

def _engine_constants(*names):
    """Constants of the engine, read from its source: importing the engine
    here would make an ephemeris folder in this process's own temporary
    folder, and refuse where that is long."""
    found = {}
    for path in engine_files():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        found[target.id] = ast.literal_eval(node.value)
    missing = [name for name in names if name not in found]
    assert not missing, f"no module of the engine assigns {missing}"
    return [found[name] for name in names]


EPHEMERIS_PREFIX, EPHEMERIS_FOLDER_BYTES, EPHEMERIS_FOLDER_REFUSAL = _engine_constants(
    "_EPHEMERIS_PREFIX", "_EPHEMERIS_FOLDER_BYTES", "EPHEMERIS_FOLDER_REFUSAL")
CHILD_TMP_PREFIX = "zij-child-"
# The longest base a child's folder is made under: with the child's folder
# and the engine's own under it, at most 64 + 19 + 23 = 106 bytes.
SHORT_BASE_BYTES = 64
_MADE = []


def _ephemeris_bytes(temporary):
    """The length in bytes of the folder the engine makes in `temporary`."""
    return len(os.fsencode(os.path.join(temporary, EPHEMERIS_PREFIX + "x" * 8)))


def _short_base():
    for base in ("/tmp", tempfile.gettempdir()):
        if (os.path.isabs(base) and os.path.isdir(base) and os.access(base, os.W_OK | os.X_OK)
                and len(os.fsencode(base)) <= SHORT_BASE_BYTES):
            return base
    pytest.fail(f"neither /tmp nor the temporary folder {tempfile.gettempdir()!r} is a writable folder of at most "
                f"{SHORT_BASE_BYTES} bytes, so no child here can be given a short temporary folder")


@pytest.fixture(scope="module", autouse=True)
def _child_folders_removed():
    """Every child's temporary folder this module made is gone by its end."""
    yield
    left = [folder for folder in _MADE if os.path.lexists(folder)]
    assert not left, f"a child's temporary folder outlived its test: {left}"


@pytest.fixture
def child_tmp():
    """A short temporary folder of this test's own for the children it
    starts, removed at its end, pass or fail."""
    folder = Path(tempfile.mkdtemp(prefix=CHILD_TMP_PREFIX, dir=_short_base()))
    _MADE.append(folder)
    assert _ephemeris_bytes(folder) <= EPHEMERIS_FOLDER_BYTES
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():                     # a child still ending, writing as it goes
            time.sleep(1)
            shutil.rmtree(folder)


def _ephemeris_folders(temporary):
    """The engine's ephemeris folders in a child's temporary folder, which
    must be one child_tmp made: a look in a folder no child was given finds
    nothing, whatever the children left."""
    assert temporary in _MADE and temporary.is_dir(), f"{temporary} is not a temporary folder a child here was given"
    return sorted(temporary.glob(EPHEMERIS_PREFIX + "*"))


def _the_folder_given(temporary):
    """What a test that failed says of the temporary folder its child was
    given (read from the environment the child had, not from child_tmp)."""
    return (f"the child's temporary folder {str(temporary)!r} is {len(os.fsencode(str(temporary)))} bytes, so the "
            f"engine's ephemeris folder in it is {_ephemeris_bytes(temporary)}, against the "
            f"{EPHEMERIS_FOLDER_BYTES} it takes")


def _environment(tmp_path, temporary, **extra):
    environment = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith("STREAMLIT_") and k.lower() not in ("http_proxy", "https_proxy")}
    environment.update(PYTHONPATH=str(_stub(tmp_path)), HOME=str(tmp_path / "home"), TMPDIR=str(temporary),
                       XDG_DATA_HOME=str(tmp_path / "xdg"), ZIJ_STUB_RECORD=str(tmp_path / "record"))
    environment.pop("ZIJ_LAUNCH_KEY", None)
    environment.update(extra)
    return environment


def _record(tmp_path):
    path = tmp_path / "record"
    return path.read_text().splitlines() if path.exists() else []


def _recorded(tmp_path, what):
    return [int(line.split()[1]) for line in _record(tmp_path) if line.startswith(what + " ")]


def _launch(tmp_path, temporary, port, **extra):
    """The launcher run whole in a process of its own, its window a
    stand-in that stays open; returned once the window is made, and once
    the engine the launcher loaded for the data folder has made its
    ephemeris folder in the child's temporary folder, so that a look there
    for one left behind looks where one was."""
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)
    environment = _environment(tmp_path, temporary, **extra)
    errors = open(tmp_path / "driver.err", "w")
    proc = subprocess.Popen([sys.executable, str(driver), str(EXECUTABLE_DIR), str(port), str(tmp_path / "record")],
                            env=environment, stdout=subprocess.DEVNULL, stderr=errors,
                            cwd=tmp_path)
    errors.close()
    deadline = time.monotonic() + 120
    while not any(line.startswith("window ") for line in _record(tmp_path)):
        if proc.poll() is not None or time.monotonic() > deadline:
            _end(proc.pid, *_recorded(tmp_path, "child"), *_recorded(tmp_path, "holder"))
            said = (tmp_path / "driver.err").read_text()
            raise AssertionError("the launcher did not open its window:\n" + said + _port_taken(port, said))
        time.sleep(0.1)
    assert f"window http://127.0.0.1:{port}/" in _record(tmp_path)
    if not _ephemeris_folders(temporary):
        _end(proc.pid, *_recorded(tmp_path, "child"), *_recorded(tmp_path, "holder"))
        raise AssertionError(f"the launcher's engine made no ephemeris folder in {str(temporary)!r}; "
                             + _the_folder_given(environment["TMPDIR"]))
    return proc


def test_every_child_here_is_given_a_short_folder_and_every_look_for_leftovers_reads_it():
    """No child is handed a temporary folder under tmp_path, nor does any
    look for the engine's folders read one: each goes through
    _environment and _ephemeris_folders, which take a child_tmp folder."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def within(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, ast.FunctionDef):
                return node.name
        return None

    under_tmp_path = [node.lineno for node in ast.walk(tree)
                      if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                      and isinstance(node.left, ast.Name) and node.left.id == "tmp_path"
                      and isinstance(node.right, ast.Constant) and node.right.value in ("tmp", "temp")]
    globs = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in ("glob", "rglob", "iterdir") and within(node) != "_ephemeris_folders"]
    handed = [node.lineno for node in ast.walk(tree)
              if isinstance(node, ast.keyword) and node.arg in ("TMPDIR", "TEMP", "TMP")
              and within(node) != "_environment"]
    assert not under_tmp_path, f"a temporary folder under tmp_path, at lines {under_tmp_path}"
    assert not globs, f"a look in a folder other than through _ephemeris_folders, at lines {globs}"
    assert not handed, f"a temporary folder handed to a child other than by _environment, at lines {handed}"


@pytest.mark.parametrize("name", ["SIGTERM", "SIGHUP"])
def test_live_a_stop_signal_to_the_launcher_alone_stops_and_reaps_its_server(tmp_path, child_tmp, port, name):
    number = getattr(signal, name)
    launcher = _launch(tmp_path, child_tmp, port)
    [child] = _recorded(tmp_path, "child")
    try:
        os.kill(launcher.pid, number)
        # The launcher stopped the server, reaped it, and ended as the
        # signal's own end would be told (128 plus its number).
        assert launcher.wait(30) == 128 + number
        assert _gone_within(child, 5), f"the server child outlived its launcher's {name}"
        assert "stopped 0" in _record(tmp_path), _record(tmp_path)
        # It ended as a program ends: its exit hooks ran, and the engine it
        # loaded for the data folder took its temporary folder away.
        assert not _ephemeris_folders(child_tmp)
    finally:
        _end(launcher.pid, child)


def test_live_a_normal_close_stops_and_reaps_the_server(tmp_path, child_tmp, port):
    launcher = _launch(tmp_path, child_tmp, port, ZIJ_STUB_CLOSE="1")
    [child] = _recorded(tmp_path, "child")
    try:
        assert launcher.wait(30) == 0
        assert not _alive(child)
        # Stopped as Streamlit stops on SIGTERM, not killed; the window's
        # closing event stopped it first.
        assert _record(tmp_path).count("stopped 0") >= 2, _record(tmp_path)
        assert not _ephemeris_folders(child_tmp)
    finally:
        _end(launcher.pid, child)


def test_live_a_killed_launcher_leaves_no_server_by_the_death_signal(tmp_path, child_tmp, port):
    """SIGKILL to the launcher, while another process holds the child's
    input open: only the death signal can end the child."""
    launcher = _launch(tmp_path, child_tmp, port, ZIJ_HOLD_THE_PIPE="1")
    [child], [holder] = _recorded(tmp_path, "child"), _recorded(tmp_path, "holder")
    try:
        os.kill(launcher.pid, signal.SIGKILL)
        launcher.wait(10)
        assert _gone_within(child, 3), "the server child outlived its killed launcher"
    finally:
        _end(launcher.pid, child, holder)


def _read_until_listening(proc, port, seconds=120):
    seen, found, ended = [], threading.Event(), threading.Event()

    def _read():
        try:
            for line in proc.stdout:
                seen.append(line.rstrip())
                if line.strip() == f"zij-server-listening {port}":
                    found.set()
                    return
        finally:
            ended.set()

    threading.Thread(target=_read, daemon=True).start()
    deadline = time.monotonic() + seconds
    while not ended.is_set() and time.monotonic() < deadline:
        ended.wait(0.1)
    if not found.is_set():
        raise AssertionError("the child never said it was listening:\n" + "\n".join(seen)
                             + _port_taken(port, "\n".join(seen)))


def test_live_the_server_stops_itself_when_its_launcher_goes(tmp_path, child_tmp, port, monkeypatch):
    """The pipe's end, as a launcher gone without a word leaves it on every
    platform: the child's input closed and its output unread. The child
    stops as Streamlit stops on SIGTERM -- exit 0, its cleanup run -- well
    within its own bound, though its output has nowhere to go."""
    launcher = _load_launcher(monkeypatch)
    for name, value in _environment(tmp_path, child_tmp).items():
        monkeypatch.setenv(name, value)
    proc = launcher._start_server(str(port), SECRET)
    try:
        _read_until_listening(proc, port)
        proc.stdout.close()
        proc.stdin.close()
        assert proc.wait(timeout=5) == 0
    finally:
        _end(proc.pid)
        proc.wait()


DEAF_ORPHAN = '''\
import ctypes, importlib.util, signal, sys, time, types
sys.modules["webview"] = types.ModuleType("webview")
spec = importlib.util.spec_from_file_location("desktop_launcher_orphan", sys.argv[1])
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
launcher.ORPHAN_WAIT_SECONDS = float(sys.argv[2])
# No death signal, as on macOS and Windows: the child sets one only where
# the platform is Linux.
launcher.sys = types.SimpleNamespace(platform="darwin")
signal.signal(signal.SIGTERM, signal.SIG_IGN)
launcher._end_with_the_launcher()
death = ctypes.c_int(-1)
ctypes.CDLL(None).prctl(2, ctypes.byref(death), 0, 0, 0)        # PR_GET_PDEATHSIG
print("up", death.value, flush=True)
while True:
    time.sleep(1)
'''


def test_live_an_orphan_deaf_to_sigterm_and_with_no_death_signal_ends_itself_within_its_bound():
    """The orphan of the reproduction ignored SIGTERM, so nothing may rely
    on signalling it; on macOS and Windows there is no death signal either.
    Its launcher gone, its input and output pipes closed, the child's own
    end after ORPHAN_WAIT_SECONDS is what ends it: exit status 1, no signal,
    not before its wait and well within the bound."""
    wait = 2.0
    child = subprocess.Popen([sys.executable, "-c", DEAF_ORPHAN, str(LAUNCHER_PATH), str(wait)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().split() == ["up", "0"], "the child has a death signal, or did not start"
        child.stdin.close()
        child.stdout.close()
        closed = time.monotonic()
        try:
            status = child.wait(timeout=wait + 10)
        except subprocess.TimeoutExpired:
            raise AssertionError("an orphan deaf to SIGTERM, with no death signal, outlived its bound")
        assert status == 1, f"ended by something other than its own end: {status}"
        assert time.monotonic() - closed >= wait - 0.5
    finally:
        _end(child.pid)
        child.wait()


class _ServerOnTheSide:
    """A server child that ignores the end of its input and SIGTERM, or one
    that stops at the end of its input."""

    STUBBORN = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('up', flush=True); time.sleep(120)"
    WILLING = "import sys; print('up', flush=True); sys.stdin.read()"

    def __init__(self, code):
        self.proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True)
        assert self.proc.stdout.readline().strip() == "up"


def test_a_normal_close_waits_escalates_and_reaps(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    monkeypatch.setattr(launcher, "STOP_WAIT_SECONDS", 1.0)
    monkeypatch.setattr(launcher, "KILL_WAIT_SECONDS", 5.0)
    willing = _ServerOnTheSide(_ServerOnTheSide.WILLING).proc
    started = time.monotonic()
    launcher._stop_server(willing)
    assert willing.returncode == 0 and time.monotonic() - started < 1.0
    stubborn = _ServerOnTheSide(_ServerOnTheSide.STUBBORN).proc
    try:
        started = time.monotonic()
        launcher._stop_server(stubborn)
        waited = time.monotonic() - started
        # It waited its bound, then killed, then reaped: the child's status
        # is collected, and no process of that id is left.
        assert stubborn.returncode == -signal.SIGKILL
        assert 1.0 <= waited < 6.0
        assert not _alive(stubborn.pid)
        with pytest.raises(ChildProcessError):
            os.waitpid(stubborn.pid, os.WNOHANG)
        # A second stop is a no-op.
        launcher._stop_server(stubborn)
    finally:
        _end(stubborn.pid)


# --- Only this launch's own server ------------------------------------------

class _Squatter(http.server.BaseHTTPRequestHandler):
    echo = False

    def do_GET(self):
        body = (self.requestline + "\n" + str(self.headers)).encode() if self.echo else b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _window_stand_in(opened):
    webview = types.ModuleType("webview")

    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    def create_window(title, url, **options):
        opened.append(url)
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=lambda: None)

    webview.create_window = create_window
    webview.start = lambda *args, **kwargs: None
    return webview


@pytest.mark.parametrize("echo", [False, True], ids=["answers ok", "echoes the request"])
def test_live_a_squatter_on_the_port_is_refused(tmp_path, child_tmp, port, monkeypatch, echo):
    handler = type("Squatter", (_Squatter,), {"echo": echo})
    squatter = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=squatter.serve_forever, daemon=True).start()
    opened = []
    launcher = _load_launcher(monkeypatch, _window_stand_in(opened))
    monkeypatch.setattr(launcher, "_free_port", lambda: port)
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *args, **kwargs: None)
    for name, value in _environment(tmp_path, child_tmp).items():
        monkeypatch.setenv(name, value)
    try:
        with pytest.raises(RuntimeError, match="not this launch's own server"):
            launcher._launch_desktop_window()
    finally:
        squatter.shutdown()
        squatter.server_close()
    assert not opened, f"the window opened a page the launcher's own child does not serve: {opened}"


# --- The window's doors -------------------------------------------------------

class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class _QUrl:
    def __init__(self, text):
        self.text = text

    def toString(self):
        return self.text


class _History:
    def __init__(self, urls):
        self.urls = list(urls)

    def items(self):
        return [types.SimpleNamespace(url=lambda u=u: _QUrl(u)) for u in self.urls]

    def clear(self):
        self.urls = self.urls[-1:]


def _qt_backend():
    """pywebview's Qt backend as far as the launcher touches it: its page
    grants camera and microphone, its window adds the Chromium switch that
    says yes to them without asking, and the engine's page lets every
    navigation through."""
    lib = types.ModuleType("webview.platforms.qt")
    navigation = enum.Enum("NavigationType", {"NavigationTypeLinkClicked": 0, "NavigationTypeTyped": 1,
                                              "NavigationTypeReload": 3, "NavigationTypeRedirect": 6})
    policy = enum.Enum("PermissionPolicy", {"PermissionGrantedByUser": 1, "PermissionDeniedByUser": 2})

    class QWebPage:
        NavigationType, PermissionPolicy = navigation, policy

        def acceptNavigationRequest(self, url, kind, is_main_frame):
            return True

    class WebPage(QWebPage):
        def __init__(self, parent=None, profile=None):
            self.permissionRequested, self.urlChanged = _Signal(), _Signal()
            self.loads, self.answers = [], []
            self._history = _History([])

        def onFeaturePermissionRequested(self, url, feature):
            self.setFeaturePermission(url, feature, policy.PermissionGrantedByUser)

        def setFeaturePermission(self, url, feature, answer):
            self.answers.append(answer)

        def setUrl(self, url):
            self.loads.append(url.toString())

        def history(self):
            return self._history

    def environ_append(key, *values, sep=" "):
        existing = os.environ.get(key, "")
        os.environ[key] = sep.join([existing, *values] if existing else values)

    lib.BrowserView = types.SimpleNamespace(WebPage=WebPage)
    lib.QWebPage, lib.is_webengine = QWebPage, True
    lib.QtCore = types.SimpleNamespace(QUrl=_QUrl, QTimer=types.SimpleNamespace(singleShot=lambda ms, f: f()))
    lib.environ_append = environ_append
    lib.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)
    lib.js_bridge_call = lambda *a, **k: "called"
    return lib


def _gtk_backend():
    lib = types.ModuleType("webview.platforms.gtk")
    lib.webkit = types.SimpleNamespace(PolicyDecisionType=types.SimpleNamespace(
        NAVIGATION_ACTION=0, NEW_WINDOW_ACTION=1, RESPONSE=2))

    class _View:
        def __init__(self):
            self.uri, self.loads, self.handlers = None, [], {}
            self.settings = types.SimpleNamespace(props=types.SimpleNamespace(enable_media_stream=True))

        def get_uri(self):
            return self.uri

        def load_uri(self, uri):
            self.loads.append(uri)

        def get_settings(self):
            return self.settings

        def connect(self, name, handler):
            self.handlers[name] = handler

    class BrowserView:
        def __init__(self, window):
            self.webview = _View()

        def on_navigation(self, webview, decision, decision_type):
            decision.used = True

    lib.BrowserView = BrowserView
    lib.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)
    lib.js_bridge_call = lambda *a, **k: "called"
    return lib


def _decision(url):
    decision = types.SimpleNamespace(used=False, ignored=False)
    decision.get_navigation_action = lambda: types.SimpleNamespace(
        get_request=lambda: types.SimpleNamespace(get_uri=lambda: url))
    decision.ignore = lambda: setattr(decision, "ignored", True)
    return decision


ORIGIN = "http://127.0.0.1:8581"


def test_the_window_is_made_with_no_bridge_and_its_backend_held(monkeypatch):
    backend = _qt_backend()
    made = {}
    webview = types.ModuleType("webview")
    webview.util = types.SimpleNamespace(js_bridge_call=lambda *a, **k: "called")
    webview.initialize = lambda gui=None: backend

    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    def create_window(title, url, **options):
        made.update(url=url, options=options)
        window = types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                       exposed=[], destroy=lambda: None)
        window.expose = lambda *functions: window.exposed.extend(functions)
        made["window"] = window
        return window

    def start(func=None, window=None, **options):
        webview.initialize(options.get("gui"))     # as webview.start loads its backend

    webview.create_window, webview.start = create_window, start
    launcher = _load_launcher(monkeypatch, webview)
    marked = threading.Event()

    def _output():
        yield "zij-server-listening 8581\n"
        marked.wait(10)

    proc = types.SimpleNamespace(stdout=_output(), stdin=io.StringIO(), poll=lambda: None,
                                 wait=lambda *a: 0, kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8581)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: listening.wait(5))
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    try:
        launcher._launch_desktop_window()
    finally:
        marked.set()
    assert made["options"].get("js_api") is None, "the window was given a Python bridge"
    assert made["window"].exposed == []
    assert webview.util.js_bridge_call is launcher._no_bridge
    assert backend.js_bridge_call is launcher._no_bridge
    assert backend.js_bridge_call(None, "__class__.__name__.upper", [], "1") is None
    assert backend.webbrowser is launcher._OnlyHttpsLinks
    page = backend.BrowserView.WebPage()
    assert page.acceptNavigationRequest(_QUrl("https://elsewhere.example/"), None, True) is False
    # The window's closing event stops the server; each load is checked.
    assert len(made["window"].events.closing) == 1 and len(made["window"].events.loaded) == 1


def test_navigation_is_held_to_the_servers_origin(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    rules = launcher._WindowRules(ORIGIN, SECRET)
    with_secret = f"{ORIGIN}/?launch={SECRET}"
    go, refuse, give = launcher._GO, launcher._REFUSE, launcher._GIVE_THE_SECRET
    for url, main, want in [
        (with_secret, True, go),
        (f"{ORIGIN}/dignities?launch={SECRET}", True, go),
        (f"{ORIGIN}/", True, give),                         # a reload once the address is bare
        (f"{ORIGIN}/dignities", True, give),
        (f"{ORIGIN}/component/x/index.html", False, go),      # a frame on the server's origin
        (f"{ORIGIN}/component/x/index.html", None, go),
        ("http://127.0.0.2:8581/", True, refuse),
        ("http://127.0.0.1:8582/", True, refuse),
        ("https://example.org/", True, refuse),
        ("https://example.org/", False, refuse),
        ("file:///etc/hostname", True, refuse),
        ("file:///etc/hostname", None, refuse),
        ("javascript:alert(1)", True, refuse),
        ("data:text/html,x", True, refuse),
        ("about:srcdoc", False, go),
        ("data:text/html,x", None, go),
        ("blob:http://127.0.0.1:8581/1", False, go),
    ]:
        assert rules.verdict(url, main) == want, (url, main)
    assert rules.with_the_secret(f"{ORIGIN}/dignities?x=1&launch=wrong") == f"{ORIGIN}/dignities?x=1&launch={SECRET}"
    # Qt: held before any request leaves; a reload is given the secret.
    backend = _qt_backend()
    launcher._hold_the_backend(backend, rules)
    page = backend.BrowserView.WebPage()
    assert page.acceptNavigationRequest(_QUrl(with_secret), None, True) is True
    assert page.acceptNavigationRequest(_QUrl("http://127.0.0.2:8584/elsewhere"), None, True) is False
    assert page.acceptNavigationRequest(_QUrl(f"{ORIGIN}/"), None, True) is False
    assert page.loads == [with_secret]
    assert page.acceptNavigationRequest(_QUrl("https://example.org/frame"), None, False) is False
    # GTK: the same, a navigation taken for the main frame's when it is to
    # the page the window shows.
    gtk = _gtk_backend()
    launcher._hold_the_backend(gtk, rules)
    view = gtk.BrowserView(None)
    away = _decision("http://127.0.0.2:8584/elsewhere")
    assert view.on_navigation(view.webview, away, 0) is True and away.ignored and not away.used
    view.webview.uri = with_secret
    again = _decision(f"{ORIGIN}/")
    assert view.on_navigation(view.webview, again, 0) is True and again.ignored
    assert view.webview.loads == [with_secret]
    home = _decision(with_secret)
    view.on_navigation(view.webview, home, 0)
    assert home.used and not home.ignored
    # Any backend: a main frame found off the origin after a load is sent
    # back to the server.
    loads = []
    window = types.SimpleNamespace(get_current_url=lambda: "https://example.org/", load_url=loads.append)
    launcher._keep_to_the_server(window, rules, with_secret)()
    window.get_current_url = lambda: f"{ORIGIN}/"
    launcher._keep_to_the_server(window, rules, with_secret)()
    assert loads == [with_secret]


def test_new_windows_open_only_https_links_in_the_system_browser(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    opened = []
    monkeypatch.setattr(launcher, "webbrowser", types.SimpleNamespace(
        open=lambda url, new=0, autoraise=True: opened.append(url) or True))
    for link in ["http://127.0.0.1:9/x", "file:///etc/hostname", "javascript:alert(1)", "ms-settings:privacy",
                 "data:text/html,x", "https:///no-host", "ftp://example.org/", "", None,
                 "https://example.org/a", "HTTPS://Example.org/b"]:
        launcher._OnlyHttpsLinks.open(link, 2, True)
    launcher._OnlyHttpsLinks.open_new_tab("http://example.org/c")
    assert opened == ["https://example.org/a", "HTTPS://Example.org/b"]
    for lib in (_qt_backend(), _gtk_backend()):
        launcher._hold_the_backend(lib, launcher._WindowRules(ORIGIN, SECRET))
        assert lib.webbrowser is launcher._OnlyHttpsLinks


def test_camera_and_microphone_are_refused(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    rules = launcher._WindowRules(ORIGIN, SECRET)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --use-fake-ui-for-media-stream")
    backend = _qt_backend()
    launcher._hold_the_backend(backend, rules)
    assert os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--no-sandbox"
    backend.environ_append("QTWEBENGINE_CHROMIUM_FLAGS", "--use-fake-ui-for-media-stream",
                           "--enable-features=AutoplayIgnoreWebAudio")
    assert "--use-fake-ui-for-media-stream" not in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
    page = backend.BrowserView.WebPage()
    page.onFeaturePermissionRequested(_QUrl(ORIGIN), "MediaAudioVideoCapture")
    assert page.answers == [backend.QWebPage.PermissionPolicy.PermissionDeniedByUser]
    asked = types.SimpleNamespace(denied=False)
    asked.deny = lambda: setattr(asked, "denied", True)
    page.permissionRequested.emit(asked)
    assert asked.denied
    gtk = _gtk_backend()
    launcher._hold_the_backend(gtk, rules)
    view = gtk.BrowserView(None).webview
    assert view.settings.props.enable_media_stream is False
    request = types.SimpleNamespace(denied=False)
    request.deny = lambda: setattr(request, "denied", True)
    assert view.handlers["permission-request"](view, request) is True and request.denied


def test_the_address_no_longer_holds_the_secret_after_the_first_page(monkeypatch):
    monkeypatch.setenv("ZIJ_LAUNCH_KEY", SECRET)
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at.query_params["launch"] = SECRET
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert "launch" not in at.query_params
    assert not any("use that window" in i.value for i in at.info) and len(list(at.sidebar)) > 10
    at.run()
    assert not at.exception and "launch" not in at.query_params
    # Qt: once the address no longer carries the secret, the history entry
    # that did is dropped.
    launcher = _load_launcher(monkeypatch)
    backend = _qt_backend()
    launcher._hold_the_backend(backend, launcher._WindowRules(ORIGIN, SECRET))
    page = backend.BrowserView.WebPage()
    page._history = _History([f"{ORIGIN}/?launch={SECRET}", f"{ORIGIN}/"])
    page.urlChanged.emit(_QUrl(f"{ORIGIN}/"))
    assert page._history.urls == [f"{ORIGIN}/"]


def test_the_window_closes_when_its_server_ends_unasked(monkeypatch):
    destroyed, made = threading.Event(), threading.Event()
    webview = types.ModuleType("webview")

    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    def create_window(title, url, **options):
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=destroyed.set)

    def start(*args, **kwargs):
        made.set()
        destroyed.wait(10)

    webview.create_window, webview.start = create_window, start
    launcher = _load_launcher(monkeypatch, webview)

    def _output():
        yield "zij-server-listening 8581\n"
        made.wait(10)                   # the server ends once the window is up

    proc = types.SimpleNamespace(stdout=_output(), stdin=io.StringIO(), poll=lambda: 1, wait=lambda *a: 1,
                                 kill=lambda: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8581)
    monkeypatch.setattr(launcher, "_start_server", lambda port, secret: proc)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: listening.wait(5))
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    launcher._launch_desktop_window()
    assert destroyed.is_set(), "the window stayed open on a port its server had left"


# --- The window's session across a lost connection ---------------------------

TTL_FLAG = "--server.disconnectedSessionTTL"


def test_the_server_keeps_a_disconnected_session_for_at_least_a_week(monkeypatch):
    """The window's session was let in by the secret its first address
    carried, and the address no longer carries it: a window that comes back
    to a session Streamlit has dropped (two minutes by default) is refused.
    The launcher keeps a disconnected session long enough for a computer's
    sleep."""
    launcher = _load_launcher(monkeypatch)
    options = launcher._server_options("8581")
    assert options.count(TTL_FLAG) == 1, "the server drops a disconnected window's session after two minutes"
    assert int(options[options.index(TTL_FLAG) + 1]) >= 7 * 24 * 3600


def test_live_a_window_that_reconnects_to_its_session_is_let_in_without_the_secret(tmp_path, child_tmp, port,
                                                                                     monkeypatch):
    """The launcher's own server child: the window's first run shows the
    secret and is let in; its connection is lost; it reconnects to that
    session, its address bare, and is let in again. A new session with the
    same bare address is told the sentence: what lets the window back in is
    its session still being kept."""
    from websockets.sync.client import connect
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    launcher = _load_launcher(monkeypatch)
    for name, value in _environment(tmp_path, child_tmp).items():
        monkeypatch.setenv(name, value)
    proc = launcher._start_server(str(port), SECRET)

    def run(query, session=None):
        protocols = ["streamlit", "x", session] if session else ["streamlit"]
        with connect(f"ws://127.0.0.1:{port}/_stcore/stream", subprotocols=protocols, open_timeout=30,
                     max_size=2 ** 27, origin=f"http://127.0.0.1:{port}") as ws:
            back = BackMsg()
            back.rerun_script.query_string = query
            back.rerun_script.page_script_hash = ""
            ws.send(back.SerializeToString())
            seen = {"session": None, "elements": 0, "refused": False}
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                forward = ForwardMsg()
                forward.ParseFromString(ws.recv(timeout=max(1, deadline - time.monotonic())))
                kind = forward.WhichOneof("type")
                if kind == "new_session":
                    seen["session"] = forward.new_session.initialize.session_id
                elif kind == "delta" and forward.delta.WhichOneof("type") == "new_element":
                    element = forward.delta.new_element
                    seen["elements"] += 1
                    body = str(getattr(getattr(element, element.WhichOneof("type")), "body", ""))
                    if body == EPHEMERIS_FOLDER_REFUSAL:
                        raise AssertionError(f"the page is the engine's ephemeris folder refusal "
                                             f"({EPHEMERIS_FOLDER_REFUSAL!r}); "
                                             + _the_folder_given(os.environ["TMPDIR"]))
                    if "used only in the window" in body:
                        seen["refused"] = True
                elif kind == "script_finished":
                    return seen
            raise AssertionError("the run did not finish")

    try:
        _read_until_listening(proc, port)
        threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()
        first = run(f"launch={SECRET}")
        assert first["session"] and not first["refused"] and first["elements"] > 10, first
        time.sleep(1.0)                         # the connection lost
        again = run("", first["session"])
        assert again["session"] == first["session"] and not again["refused"] and again["elements"] > 10, again
        stranger = run("")
        assert stranger["session"] != first["session"] and stranger["refused"] and stranger["elements"] == 1
    finally:
        launcher._stop_server(proc)
        _end(proc.pid)


# --- The window's log -------------------------------------------------------

def test_the_window_log_is_in_the_data_folder_owner_only_and_not_through_a_link(tmp_path, monkeypatch):
    launcher = _load_launcher(monkeypatch)
    import engine

    assert Path(launcher._window_log_folder()) == engine._user_data_dir()
    assert Path(launcher._window_log_folder()) != LAUNCHER_PATH.parent
    folder = tmp_path / "data"
    folder.mkdir()
    previous = os.umask(0)
    try:
        handler = launcher._open_window_log(folder)
    finally:
        os.umask(previous)
    try:
        assert handler is not None
        log = folder / launcher.WINDOW_LOG_NAME
        assert stat.S_IMODE(log.stat().st_mode) == 0o600
        assert handler.level == logging.INFO
    finally:
        handler.stream.close()
    monkeypatch.setenv("PYWEBVIEW_LOG", "debug")
    handler = launcher._open_window_log(folder)
    assert handler.level == logging.DEBUG
    handler.stream.close()
    monkeypatch.delenv("PYWEBVIEW_LOG")
    # A link, a hard link, a FIFO or a folder at the name: no log, and
    # nothing written where it points.
    target = tmp_path / "elsewhere.txt"
    target.write_text("kept\n")
    for kind in ("link", "hard link", "fifo", "folder"):
        planted = tmp_path / kind.replace(" ", "-")
        planted.mkdir()
        name = planted / launcher.WINDOW_LOG_NAME
        if kind == "link":
            name.symlink_to(target)
        elif kind == "hard link":
            os.link(target, name)
        elif kind == "fifo":
            os.mkfifo(name)
        else:
            name.mkdir()
        assert launcher._open_window_log(planted) is None, kind
    assert target.read_text() == "kept\n"
    gitignore = (EXECUTABLE_DIR / ".gitignore").read_text().splitlines()
    assert launcher.WINDOW_LOG_NAME in gitignore


def test_no_handler_writes_the_secret(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    root, pywebview = logging.getLogger(), logging.getLogger("pywebview")
    root_stream, console = io.StringIO(), io.StringIO()
    root_handler, console_handler = logging.StreamHandler(root_stream), logging.StreamHandler(console)
    console_handler.setFormatter(logging.Formatter("[pywebview] %(message)s"))
    root.addHandler(root_handler)
    pywebview.addHandler(console_handler)
    monkeypatch.setattr(pywebview, "propagate", False)
    monkeypatch.setattr(pywebview, "level", logging.DEBUG)
    try:
        launcher._withhold_the_secret(SECRET)
        url = f"{ORIGIN}/?launch={SECRET}"
        pywebview.info("Loading URL: %s", url)
        try:
            raise RuntimeError(url)
        except RuntimeError:
            pywebview.exception("failed on %s", url)
        root.warning("opening %s", url)
    finally:
        root.removeHandler(root_handler)
        pywebview.removeHandler(console_handler)
    written = console.getvalue() + root_stream.getvalue()
    assert SECRET not in written
    assert "[pywebview] Loading URL: http://127.0.0.1:8581/?launch=(withheld)" in console.getvalue()
    assert "opening http://127.0.0.1:8581/?launch=(withheld)" in root_stream.getvalue()


# --- The atlas's connection and the lock's bound ------------------------------

def test_the_atlas_connection_is_closed_on_the_error_path(tmp_path):
    # The lookup moved to time_zones.py (ruling 175 (7)); _atlas_matches,
    # which calls it, stays in app.py.
    wanted = {"_atlas_matches", "atlas_rows", "_atlas_fold", "_like_prefix"}
    functions = [node for path in (APP_PATH, APP_PATH.parent / "time_zones.py")
                 for node in ast.parse(path.read_text(encoding="utf-8")).body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert sorted(f.name for f in functions) == sorted(wanted)
    made = []

    class _Connection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def _connect(path, **kwargs):
        made.append(sqlite3.connect(path, factory=_Connection, **kwargs))
        return made[-1]

    (tmp_path / "atlas.db").touch()                 # an atlas with no table: the query fails
    import contextlib
    import unicodedata

    space = {"__file__": str(tmp_path / "app.py"), "Path": Path, "contextlib": contextlib,
             "unicodedata": unicodedata, "sqlite3": types.SimpleNamespace(connect=_connect),
             "ATLAS_MISSING_MESSAGE": "missing", "ATLAS_NO_MATCH_MESSAGE": "none"}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(APP_PATH), "exec"), space)
    with pytest.raises(sqlite3.OperationalError):
        space["_atlas_matches"]("Florence")
    assert len(made) == 1 and made[0].closed


def test_the_stray_wait_is_said_to_bound_the_wait_for_the_lock_alone():
    from conftest import engine_source
    text = engine_source()                            # every engine module, joined
    assert "_STRAY_TEMP_WAIT = 0.25" in text
    assert "That\n# moment bounds the wait for the lock and nothing else" in text
    assert "waits no more than a moment)" not in text
    tree = ast.parse(text)
    lock = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "saved_charts_lock")
    doc = " ".join(ast.get_docstring(lock).split())
    assert "bounds the wait for the lock" in doc and "it bounds nothing done once the lock is held" in doc
