"""The local server's door (the owner's rulings 150 and 157).

The desktop launcher's Streamlit server answered every client that reached
its loopback port with the owner's whole session: another account on the
computer, or a page served from any other local port, could list the saved
charts, read a person's birth data, delete a record and change a preference.
A config file in the home folder or the launch folder, or a STREAMLIT_*
variable, could also switch the server's origin check off. Now:

* the launcher makes a secret for each launch, hands it to the server child
  in its environment (never its command line), and opens the window on a URL
  that carries it. app.py's first act stops any session that has not shown
  it: before the engine loads, before the launch is counted, before any saved
  chart or preference is read, and before any widget exists. A session that
  has shown it is remembered, so a rerun and a page change work, and the
  secret is then taken out of the address (the launcher gives it again to a
  reload of the window);
* the launcher pins, as flags, every server option that bears on who can
  connect, what a client is told, or what the server reads or serves, and
  starts its child with no STREAMLIT_* variable, so no config file and no
  variable can loosen them;
* the checkout's own config serves a source run on loopback only.

The live tests start the launcher's own server child on a free port, with a
hostile config file planted in its working folder and in its home folder and
hostile STREAMLIT_* variables in the launcher's environment, and talk to it
over Streamlit's own protocol, as any local client can. They send nothing
beyond loopback: the server's lookup of its external address, which a
foreign Origin sets off, is sent to a closed loopback port.
"""
import ast
import http.server
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tomllib
import types
import urllib.request
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from conftest import APP_PATH, EXECUTABLE_DIR, sync_engine_to_environment
from loopback_ports import claimed_port, port_taken

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"
CONFIG_PATH = EXECUTABLE_DIR / ".streamlit" / "config.toml"
README_PATH = EXECUTABLE_DIR / "README.md"

# The owner's wording (ruling 160), word for word.
SENTENCE = ("This app can be used only in the window it opens when it starts; "
            "use that window, or start the app again.")

RECORD = "Probenative Qx7"
OTHER = "Othernative Kz2"
RECORDS = {
    RECORD: {"date_string": "1931-07-04", "time_string": "05:17:00",
             "time_standard": "Manual UTC offset", "utc_offset": 1.0,
             "location_query": "Florence", "lat": 43.7696, "lon": 11.2558},
    OTHER: {"date_string": "1988-11-12", "time_string": "23:45:00",
            "time_standard": "Manual UTC offset", "utc_offset": -5.0,
            "location_query": "Boston", "lat": 42.3601, "lon": -71.0589},
}
# What a session must not see: the records' names and the reopened record's
# birth data.
PRIVATE = (RECORD, OTHER, "1931-07-04", "05:17", "Florence", "43.7696")
PREFERENCES = {"last_chart": RECORD, "_launches": 7, "_moon_rays_15": True}

# Every option the launcher pins, with its value (the port's own entries are
# filled in per port). Each bears on who can connect, what a client is told,
# or what the server reads or serves; the runner's are pinned as they stand.
PINNED = {
    "server.address": "127.0.0.1",
    "server.allowedHosts": "127.0.0.1",
    "server.enableCORS": "true",
    "browser.serverAddress": "127.0.0.1",
    "server.enableXsrfProtection": "true",
    "server.xsrfCookieSameSite": "lax",
    "server.sslCertFile": "",
    "server.sslKeyFile": "",
    "server.baseUrlPath": "",
    "global.developmentMode": "false",
    "global.e2eTest": "false",
    "client.showErrorDetails": "full",
    "client.showErrorLinks": "auto",
    "client.toolbarMode": "minimal",
    "server.headless": "true",
    "server.showEmailPrompt": "false",
    "server.disconnectedSessionTTL": "2592000",
    "server.fileWatcherType": "none",
    "server.runOnSave": "false",
    "server.allowRunOnSave": "false",
    "server.enableStaticServing": "false",
    "server.scriptHealthCheckEnabled": "false",
    "browser.gatherUsageStats": "false",
    "runner.magicEnabled": "false",
    "runner.fastReruns": "true",
    "runner.enforceSerializableSessionState": "false",
    "runner.enumCoercion": "nameOnly",
}


def _pinned_for(port):
    return {**PINNED, "server.port": port,
            "server.corsAllowedOrigins": f"http://127.0.0.1:{port}",
            "client.allowedOrigins": f"http://127.0.0.1:{port}"}


# A config file that would open the door if it were read, planted in the
# server's working folder and in its home folder, and the same in variables.
PLANTED_CONFIG = """\
[server]
address = "0.0.0.0"
enableCORS = false
enableXsrfProtection = false
allowedHosts = ["*"]
corsAllowedOrigins = ["http://evil.example"]
enableStaticServing = true
scriptHealthCheckEnabled = true
[browser]
serverAddress = "evil.example"
[global]
developmentMode = true
[client]
allowedOrigins = ["https://*.evil.example"]
"""
PLANTED_VARIABLES = {
    "STREAMLIT_SERVER_ENABLE_CORS": "false",
    "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION": "false",
    "STREAMLIT_SERVER_ALLOWED_HOSTS": "*",
    "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
    "STREAMLIT_BROWSER_SERVER_ADDRESS": "evil.example",
    "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "true",
    "streamlit_server_cors_allowed_origins": "http://evil.example",
}


# --- The launcher, loaded without its window library ------------------------

def _load_launcher(monkeypatch):
    """desktop_launcher.py as a module. pywebview is not in the suite's venv
    and the server half never calls it, so a stand-in is put in its place."""
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_under_test", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pairs(options):
    """['--a.b', 'v', '--c.d', 'w'] -> {'a.b': 'v', 'c.d': 'w'}; refuses a
    flag given twice, or a stray value."""
    assert len(options) % 2 == 0, options
    pairs = {}
    for flag, value in zip(options[::2], options[1::2]):
        assert flag.startswith("--"), (flag, value)
        assert flag[2:] not in pairs, f"{flag} given twice"
        pairs[flag[2:]] = value
    return pairs


def _app_constant(name):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and getattr(node.targets[0], "id", None) == name):
            return ast.literal_eval(node.value)
    raise AssertionError(f"app.py assigns no {name}")


def test_the_server_child_is_started_with_every_door_option_pinned(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    pairs = _pairs(launcher._server_options("8591"))
    want = _pinned_for("8591")
    wrong = {key: (pairs.get(key), value) for key, value in want.items() if pairs.get(key) != value}
    assert not wrong, f"options missing or loosened (got, wanted): {wrong}"
    assert set(pairs) == set(want), f"options pinned but not listed here: {set(pairs) - set(want)}"
    # The server runs exactly these, after `streamlit run <app>`.
    seen = {}

    class _Cli:
        @staticmethod
        def main():
            seen["argv"] = list(sys.argv)
            return 0

    import streamlit.web
    from streamlit.web import bootstrap

    monkeypatch.setattr(streamlit.web, "cli", _Cli, raising=False)
    monkeypatch.setattr(bootstrap, "_set_up_signal_handler", bootstrap._set_up_signal_handler)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setenv("STREAMLIT_SERVER_ENABLE_CORS", "false")
    with pytest.raises(SystemExit):
        launcher._run_as_streamlit_server("8591")
    assert seen["argv"][:3] == ["streamlit", "run", launcher._resource_path("app.py")]
    assert _pairs(seen["argv"][3:]) == pairs
    # A variable set some other way is dropped by the child itself too.
    assert not [name for name in os.environ if name.upper().startswith("STREAMLIT_")]


def test_the_secret_goes_to_the_child_in_its_environment_not_its_argv(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    for name, value in PLANTED_VARIABLES.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ZIJ_DOOR_NEIGHBOUR", "kept")
    started = {}

    def _popen(args, **kwargs):
        started.update(args=args, **kwargs)
        return types.SimpleNamespace(args=args)

    monkeypatch.setattr(launcher.subprocess, "Popen", _popen)
    secret = "door-secret-" + "q" * 31
    launcher._start_server("8591", secret)
    assert not [a for a in started["args"] if secret in str(a)], started["args"]
    environment = started["env"]
    assert environment[launcher.LAUNCH_KEY_VARIABLE] == secret
    assert [name for name in environment if name.upper().startswith("STREAMLIT_")] == []
    assert environment["ZIJ_DOOR_NEIGHBOUR"] == "kept"
    assert environment["PATH"] == os.environ["PATH"]
    # The launcher and the app name the variable and the parameter alike.
    assert launcher.LAUNCH_KEY_VARIABLE == _app_constant("_LAUNCH_KEY_VARIABLE")
    assert launcher.LAUNCH_KEY_PARAMETER == _app_constant("_LAUNCH_KEY_PARAMETER")


def test_the_window_opens_on_the_secret_and_the_log_withholds_it(monkeypatch, tmp_path):
    import logging

    launcher = _load_launcher(monkeypatch)
    given = {}
    monkeypatch.setattr(launcher, "_free_port", lambda: 8591)
    monkeypatch.setattr(launcher, "_start_server",
                        lambda port, secret: given.update(port=port, secret=secret) or types.SimpleNamespace(
                            stdout=iter(()), stdin=None, poll=lambda: 0, wait=lambda *a: 0))
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, *a, **k: given.update(waited=url) or True)
    monkeypatch.setattr(launcher.atexit, "register", lambda *a, **k: None)
    log_file = tmp_path / "window.log"
    handler = logging.FileHandler(log_file)
    root = logging.getLogger()
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: tmp_path)
    monkeypatch.setattr(launcher, "_open_window_log", lambda folder: handler)
    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    window = types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                   destroy=lambda: None)
    monkeypatch.setattr(launcher.webview, "create_window",
                        lambda title, url, **kw: given.update(url=url) or window, raising=False)

    def _start(func, win, **kw):
        logging.getLogger("pywebview").warning("Loading %s", given["url"])

    monkeypatch.setattr(launcher.webview, "start", _start, raising=False)
    try:
        launcher._launch_desktop_window()
    finally:
        root.removeHandler(handler)
        handler.close()
    secret = given["secret"]
    assert len(secret) >= 40
    assert given["url"] == f"http://127.0.0.1:8591/?launch={secret}"
    assert secret not in given["waited"]
    logged = log_file.read_text()
    assert "Loading http://127.0.0.1:8591/?launch=" in logged
    assert secret not in logged


# --- The app's first act ---------------------------------------------------

def test_the_door_is_the_apps_first_act_and_compares_in_constant_time():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    body = [node for node in tree.body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    calls = [i for i, node in enumerate(body) if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call)
             and getattr(node.value.func, "id", None) == "_admit_only_the_window"]
    assert len(calls) == 1, calls
    # Nothing but imports, constants and the door itself comes before it.
    for node in body[:calls[0]]:
        ok = (isinstance(node, (ast.Import, ast.ImportFrom))
              or (isinstance(node, ast.Assign) and isinstance(node.value, (ast.Constant, ast.Tuple, ast.BinOp))
                  and not [n for n in ast.walk(node.value) if isinstance(n, (ast.Call, ast.Name, ast.Attribute))])
              or (isinstance(node, ast.FunctionDef) and node.name == "_admit_only_the_window"))
        assert ok, f"app.py line {node.lineno} runs before the door"
    door = next(node for node in body if isinstance(node, ast.FunctionDef) and node.name == "_admit_only_the_window")
    compared = [n for n in ast.walk(door) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "compare_digest" and getattr(n.func.value, "id", None) == "hmac"]
    assert len(compared) == 1
    plain = [n.lineno for n in ast.walk(door) if isinstance(n, ast.Compare)
             and any(isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)) for op in n.ops)]
    assert plain == [], f"a plain comparison in the door, line(s) {plain}"


def _seed(tmp_path, monkeypatch):
    """Two saved records and a preferences file in a disposable data folder,
    with preferences live; the folder's preferences file is returned."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    import engine as _engine  # noqa: F401  (the harness reloads it for this folder)
    module = sys.modules["engine"]
    module._harness_environment = None
    sync_engine_to_environment()
    module = sys.modules["engine"]
    assert module.write_saved_charts(RECORDS)
    module.PREFERENCES_PATH.write_text(json.dumps(PREFERENCES))
    return module.PREFERENCES_PATH


def _protos(at):
    """Every element an AppTest run rendered, as its message's text."""
    found = []

    def walk(node):
        proto = getattr(node, "proto", None)
        if proto is not None and not isinstance(proto, (str, bytes)):
            found.append(str(proto))
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            for child in children.values():
                walk(child)

    walk(at._tree)
    return found


def _texts(at):
    """Every string an AppTest run rendered, in one blob."""
    return "\n".join(_protos(at))


def test_an_apptest_without_the_secret_renders_one_sentence_and_reads_nothing(tmp_path, monkeypatch):
    prefs = _seed(tmp_path, monkeypatch)
    monkeypatch.setenv("ZIJ_LAUNCH_KEY", "door-secret-" + "w" * 31)
    for query in ({}, {"launch": "door-secret-" + "w" * 30 + "x"}, {"launch": "ŵ" * 43}):
        at = AppTest.from_file(str(APP_PATH), default_timeout=120)
        at.query_params.update(query)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert [i.value for i in at.info] == [SENTENCE], query
        assert len(at.main.children) == 1 and len(at.sidebar.children) == 0, query
        blob = _texts(at)
        assert not [p for p in PRIVATE if p in blob], query
        state = at.session_state.filtered_state
        assert not {"_prefs", "saved_charts", "_launches", "_moon_rays_15", "_launch_key_shown"} & set(state), state
        assert prefs.read_text() == json.dumps(PREFERENCES), "a session without the secret wrote the preferences"


def test_the_window_with_the_secret_renders_as_a_run_with_no_secret_does(tmp_path, monkeypatch):
    prefs = _seed(tmp_path, monkeypatch)
    plain = AppTest.from_file(str(APP_PATH), default_timeout=300).run()
    assert not plain.exception, [e.value for e in plain.exception]
    assert json.loads(prefs.read_text())["_launches"] == 8
    prefs.write_text(json.dumps(PREFERENCES))
    secret = "door-secret-" + "e" * 31
    monkeypatch.setenv("ZIJ_LAUNCH_KEY", secret)
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at.query_params["launch"] = secret
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    picker = [s for s in at.sidebar.selectbox if s.label.endswith("Load saved chart")]
    assert picker and RECORD in picker[0].options and picker[0].value == RECORD
    assert json.loads(prefs.read_text())["_launches"] == 8
    assert SENTENCE not in _texts(at)
    # The time box's default is the clock's time, to the second, and an
    # export's file is named by its contents, which carry the moment it was
    # made.
    def _seen(run):
        return [re.sub(r'url: "/mock/media/[0-9a-f]+\.', 'url: "(an export).',
                       re.sub(r'default: "\d\d:\d\d:\d\d"', 'default: "(now)"', proto))
                for proto in _protos(run)]

    assert _seen(at) == _seen(plain)


def test_a_rerun_and_a_page_change_keep_the_window_in_and_the_secret_out_of_its_address(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    secret = "door-secret-" + "r" * 31
    monkeypatch.setenv("ZIJ_LAUNCH_KEY", secret)
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at.query_params["launch"] = secret
    at.run()
    assert not at.exception and SENTENCE not in _texts(at)
    # Let in, the session's address no longer carries the secret (lane
    # SEC2: the launcher gives it again to a reload of the window).
    assert "launch" not in at.query_params
    # A page change in the browser drops the query string (seen in Chrome
    # against this server); the session is let in all the same.
    at.query_params.clear()
    at._page_hash = calc_hash("dignities")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert SENTENCE not in _texts(at)
    assert "Dignities" in " ".join(h.value for h in [*at.header, *at.subheader, *at.title])
    assert "launch" not in at.query_params
    at.query_params.clear()
    at.run()
    assert not at.exception and SENTENCE not in _texts(at)
    assert "launch" not in at.query_params
    # The session is remembered, not the address: a new session with no
    # secret, on the page the window was on, is told the sentence.
    stranger = AppTest.from_file(str(APP_PATH), default_timeout=120)
    stranger._page_hash = calc_hash("dignities")
    stranger.run()
    assert [i.value for i in stranger.info] == [SENTENCE]


def test_a_run_with_no_secret_in_its_environment_is_not_checked(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.delenv("ZIJ_LAUNCH_KEY", raising=False)
    at = AppTest.from_file(str(APP_PATH), default_timeout=300).run()
    assert not at.exception and SENTENCE not in _texts(at)
    assert at.query_params == {}


# --- The launcher's own server, live ------------------------------------------

# The ports the live servers here are started on: a small fixed pool below
# the range the system hands out for outgoing connections, each held by one
# test at a time among every run of these tests on the machine
# (tests/loopback_ports.py), apart from the window tests' own pool.
PORTS = range(8585, 8589)


@pytest.fixture
def port(tmp_path_factory):
    """A port of PORTS, claimed by this test alone among the runs on the
    machine and free when the test starts; a program outside these tests
    binding it before the server does fails the test by name."""
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "sec1-ports")


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _closed_loopback_port():
    """A loopback address nothing is started on, for the proxies: a request
    sent there is refused, and never leaves the machine."""
    port = _free_port()
    return f"http://127.0.0.1:{port}"


def _held_by(port, pid, proc_root=Path("/proc")):
    """Whether a TCP socket listening on `port` is one of process `pid`'s
    (Linux: the socket tables against the process's open files); None where
    neither socket table can be read (no `/proc`, as off Linux), so that no
    answer is made up."""
    inodes, tables = set(), 0
    for table in ("net/tcp", "net/tcp6"):
        try:
            text = (proc_root / table).read_text()
        except OSError:
            continue
        tables += 1
        for line in text.splitlines()[1:]:
            fields = line.split()
            if int(fields[1].rpartition(":")[2], 16) == port and fields[3] == "0A":
                inodes.add(fields[9])
    if not tables:
        return None
    try:
        fds = os.listdir(proc_root / str(pid) / "fd")
    except OSError:
        return False
    for fd in fds:
        try:
            target = os.readlink(proc_root / str(pid) / "fd" / fd)
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            return True
    return False


def _wait_for_health(port, proc, timeout=120, proc_root=Path("/proc")):
    """Until the server `proc` answers Streamlit's health check on `port`
    from a socket of its own; a port another process took before it fails
    at once, by name. Where the socket tables cannot be read (no `/proc`)
    the owner is not checked: a server that exits or never answers still
    fails with the port's cause, as before the owner check."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            said = proc.stdout.read()
            raise AssertionError(f"the server exited: {said}{port_taken(port, said)}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2)
        except OSError:
            time.sleep(0.25)
            continue
        if _held_by(port, proc.pid, proc_root) is not False:
            return
        raise AssertionError(f"what answered on port {port} is not the server started{port_taken(port)}")
    raise AssertionError(f"the server did not answer{port_taken(port)}")


class _Health(http.server.BaseHTTPRequestHandler):
    """A program outside the tests that answers Streamlit's health check."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _stand_in_server(code):
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)


def test_a_port_another_program_answers_on_first_fails_by_name(port):
    """A program that took the port before the server, and answers the
    health check there, is not taken for the server."""
    taker = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Health)
    threading.Thread(target=taker.serve_forever, daemon=True).start()
    server = _stand_in_server("import time; time.sleep(60)")
    try:
        with pytest.raises(AssertionError) as failed:
            _wait_for_health(port, server, timeout=30)
    finally:
        server.kill()
        server.wait()
        server.stdout.close()
        taker.shutdown()
        taker.server_close()
    assert f"what answered on port {port} is not the server started" in str(failed.value)
    assert f"port {port} was taken by another process between the test's check and the child's bind" \
        in str(failed.value)


_SERVES_HEALTH = """
import http.server, sys
class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args):
        pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), Health).serve_forever()
"""


def _unreadable_proc(tmp_path, how):
    """A stand-in for `/proc` the owner check cannot read: absent, or with
    folders where its socket tables would be."""
    root = tmp_path / "proc"
    if how == "tables-unreadable":
        (root / "net" / "tcp").mkdir(parents=True)
        (root / "net" / "tcp6").mkdir()
    return root


@pytest.mark.parametrize("how", ["absent", "tables-unreadable"])
def test_without_proc_the_owner_is_not_checked_and_no_false_cause_is_given(tmp_path, port, how):
    """The server's own socket answers the health check: with `/proc` read
    the owner check finds it the server's; with `/proc` unreadable (as off
    Linux) the check is not made, so the server is not called another
    program's."""
    proc_root = _unreadable_proc(tmp_path, how)
    server = subprocess.Popen([sys.executable, "-c", _SERVES_HEALTH, str(port)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for_health(port, server, timeout=30, proc_root=proc_root)
        assert _held_by(port, server.pid, proc_root) is None
        if Path("/proc/net/tcp").exists():
            assert _held_by(port, server.pid) is True, "premise: read, /proc finds the server's own socket"
            _wait_for_health(port, server, timeout=30)
        else:
            assert not sys.platform.startswith("linux"), "Linux keeps its socket tables in /proc"
    finally:
        server.kill()
        server.wait()
        server.stdout.close()


@pytest.mark.parametrize("how", ["absent", "tables-unreadable"])
def test_without_proc_a_server_that_could_not_bind_still_fails_by_the_port(tmp_path, port, how):
    """Without the owner check a port taken between the choice and the bind
    still fails with that cause, and only that one."""
    proc_root = _unreadable_proc(tmp_path, how)
    server = _stand_in_server(f"print('Port {port} is not available'); raise SystemExit(1)")
    try:
        with pytest.raises(AssertionError) as failed:
            _wait_for_health(port, server, timeout=30, proc_root=proc_root)
    finally:
        server.wait()
        server.stdout.close()
    said = str(failed.value)
    assert said.startswith(f"the server exited: Port {port} is not available"), said
    assert f"port {port} was taken by another process between the test's check and the child's bind" in said
    assert "is not the server started" not in said


def test_a_server_that_could_not_bind_its_port_fails_by_name(port):
    """A server that exits saying its port is not available (Streamlit's
    words) fails the test with the cause."""
    server = _stand_in_server(f"print('Port {port} is not available'); raise SystemExit(1)")
    try:
        with pytest.raises(AssertionError) as failed:
            _wait_for_health(port, server, timeout=30)
    finally:
        server.wait()
        server.stdout.close()
    said = str(failed.value)
    assert said.startswith(f"the server exited: Port {port} is not available"), said
    assert f"port {port} was taken by another process between the test's check and the child's bind" in said


@pytest.fixture
def launched(tmp_path, monkeypatch, port):
    """The launcher's own server child, on a free port, started from a
    working folder and a home folder that each hold a hostile config file,
    with hostile STREAMLIT_* variables in the launcher's environment."""
    seed = subprocess.run(
        [sys.executable, "-c",
         "import json, sys; sys.path.insert(0, sys.argv[1]); import engine; "
         "assert engine.write_saved_charts(json.loads(sys.argv[2])); "
         "engine.PREFERENCES_PATH.write_text(sys.argv[3])",
         str(EXECUTABLE_DIR), json.dumps(RECORDS), json.dumps(PREFERENCES)],
        env={**{k: v for k, v in os.environ.items() if k != "ALMUTEN_NO_PREFERENCES"},
             "XDG_DATA_HOME": str(tmp_path / "xdg")},
        capture_output=True, text=True, timeout=120)
    assert seed.returncode == 0, seed.stderr
    stub = tmp_path / "stub" / "webview"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("")
    for folder in (tmp_path / "cwd", tmp_path / "home"):
        (folder / ".streamlit").mkdir(parents=True)
        (folder / ".streamlit" / "config.toml").write_text(PLANTED_CONFIG)
    launcher = _load_launcher(monkeypatch)
    secret = "door-secret-" + "z" * 31
    dead = _closed_loopback_port()
    with monkeypatch.context() as m:
        m.chdir(tmp_path / "cwd")
        m.setenv("HOME", str(tmp_path / "home"))
        m.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        m.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
        m.setenv("PYTHONPATH", str(tmp_path / "stub"))
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            m.setenv(name, dead)
        for name in ("no_proxy", "NO_PROXY"):
            m.delenv(name, raising=False)
        for name, value in PLANTED_VARIABLES.items():
            m.setenv(name, value)
        proc = launcher._start_server(str(port), secret)
    try:
        _wait_for_health(port, proc)
        yield types.SimpleNamespace(port=port, secret=secret, proc=proc,
                                    prefs=tmp_path / "xdg" / "Zij" / "preferences.json")
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(20)
        proc.stdout.close()


def _connect(port, origin=None, host=None):
    from websockets.sync.client import connect

    headers = {"Origin": origin} if origin else {}
    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    return connect(f"ws://{host or f'127.0.0.1:{port}'}/_stcore/stream", additional_headers=headers,
                   subprotocols=["streamlit"], open_timeout=30, max_size=2 ** 27, origin=None, sock=sock)


def _session(port, origin=None, query="", widgets=(), timeout=240):
    """One script run over the protocol, as any local client can ask for it:
    every message the server sent, until the run finished."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    ws = _connect(port, origin=origin)
    try:
        back = BackMsg()
        back.rerun_script.query_string = query
        back.rerun_script.page_script_hash = ""
        for widget in widgets:
            back.rerun_script.widget_states.widgets.append(widget)
        ws.send(back.SerializeToString())
        messages, deadline = [], time.time() + timeout
        while time.time() < deadline:
            forward = ForwardMsg()
            forward.ParseFromString(ws.recv(timeout=max(1, deadline - time.time())))
            messages.append(forward)
            if forward.WhichOneof("type") == "script_finished":
                return messages
        raise AssertionError("the run did not finish")
    finally:
        ws.close()


def _elements(messages):
    from google.protobuf.json_format import MessageToDict

    found = []
    for forward in messages:
        if forward.WhichOneof("type") == "delta" and forward.delta.WhichOneof("type") == "new_element":
            element = forward.delta.new_element
            kind = element.WhichOneof("type")
            found.append((kind, MessageToDict(getattr(element, kind), preserving_proto_field_name=True)))
    return found


def _blob(messages):
    from google.protobuf.json_format import MessageToJson

    return "\n".join(MessageToJson(forward, ensure_ascii=False) for forward in messages)


def _told_only_the_sentence(messages, label):
    elements = _elements(messages)
    blob = _blob(messages)
    assert [(kind, body.get("body")) for kind, body in elements] == [("alert", SENTENCE)], (label, elements[:5])
    assert not [p for p in PRIVATE if p in blob], label
    assert "stackTrace" not in blob and "Traceback" not in blob, label


def test_live_a_client_without_the_secret_is_told_one_sentence_and_reads_nothing(launched):
    from streamlit.proto.WidgetStates_pb2 import WidgetState

    port, secret = launched.port, launched.secret
    # Any local client (another account, a script) sends no Origin.
    _told_only_the_sentence(_session(port), "no Origin")
    # A frame of the app on another page loads it under its own origin,
    # without the secret: the framed load stops here.
    _told_only_the_sentence(_session(port, origin=f"http://127.0.0.1:{port}"), "a frame of the app")
    # A page served from any other local port passes the origin check.
    _told_only_the_sentence(_session(port, origin=f"http://localhost:{_free_port()}"), "another local port")
    _told_only_the_sentence(_session(port, query="launch=" + secret[:-1] + "y"), "a wrong secret")
    forged = WidgetState(id="_launch_key_shown")
    forged.bool_value = True
    _told_only_the_sentence(_session(port, widgets=[forged]), "a forged session key")
    assert launched.prefs.read_text() == json.dumps(PREFERENCES), "a client without the secret wrote the preferences"
    # The window itself: everything, the counter included.
    window = _session(port, query="launch=" + secret)
    blob = _blob(window)
    assert RECORD in blob and OTHER in blob and "1931-07-04" in blob and SENTENCE not in blob
    assert json.loads(launched.prefs.read_text())["_launches"] == 8
    # An ill-typed value for each of the window's widgets makes the script
    # raise, with its traceback, in a session that has shown the secret; sent
    # without it, nothing raises and no traceback is told.
    ids = [body["id"] for kind, body in _elements(window) if isinstance(body, dict) and "id" in body]
    assert len(ids) > 10, ids

    def ill_typed():
        widgets = []
        for widget_id in ids:
            widget = WidgetState(id=widget_id)
            widget.json_value = "{"
            widgets.append(widget)
        return widgets

    _told_only_the_sentence(_session(port, widgets=ill_typed()), "ill-typed widgets")
    raised = _session(port, query="launch=" + secret, widgets=ill_typed())
    assert "exception" in [kind for kind, _ in _elements(raised)] and "stackTrace" in _blob(raised), \
        "the ill-typed probe no longer makes the script raise"


def test_live_a_foreign_host_or_origin_is_refused_whatever_is_planted(launched):
    from websockets.exceptions import InvalidStatus

    port = launched.port
    for origin, host in ((None, f"evil.example:{port}"),                       # a rebound name
                         (f"http://evil.example:{port}", f"evil.example:{port}"),
                         ("http://evil.example", None),                          # a foreign page
                         ("null", None),
                         (f"http://127.0.0.1.evil.example:{port}", None)):
        with pytest.raises(InvalidStatus) as refused:
            _connect(port, origin=origin, host=host).close()
        assert refused.value.response.status_code == 403, (origin, host)
    # The server's own lists name only the window's origin.
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/host-config", timeout=10) as reply:
        assert json.loads(reply.read())["allowedOrigins"] == [f"http://127.0.0.1:{port}"]
    request = urllib.request.Request(f"http://127.0.0.1:{port}/_stcore/health",
                                     headers={"Origin": "http://evil.example"})
    with urllib.request.urlopen(request, timeout=10) as reply:
        assert reply.headers.get("Access-Control-Allow-Origin") in (None, f"http://127.0.0.1:{port}")
    # The XSRF cookie is still issued, and no route runs the script outside a
    # session.
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=10) as reply:
        assert "_streamlit_xsrf=" in " ".join(reply.headers.get_all("Set-Cookie") or [])
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/script-health-check", timeout=30) as reply:
        # The page's shell, as for any path the server has no route for.
        assert reply.headers.get_content_type() == "text/html", reply.headers
    # It listens on loopback, the planted "0.0.0.0" notwithstanding.
    assert _listening(port) == ["127.0.0.1"]


def _listening(port):
    """The IPv4 and IPv6 addresses a TCP socket listens on at `port`."""
    found = []
    for table, width in (("/proc/net/tcp", 8), ("/proc/net/tcp6", 32)):
        if not Path(table).exists():
            continue
        for line in Path(table).read_text().splitlines()[1:]:
            fields = line.split()
            address, _, hexport = fields[1].partition(":")
            if int(hexport, 16) == port and fields[3] == "0A":
                if width == 8:
                    found.append(socket.inet_ntop(socket.AF_INET, bytes.fromhex(address)[::-1]))
                else:
                    raw = bytes.fromhex(address)
                    found.append(socket.inet_ntop(socket.AF_INET6, b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))))
    return found


# --- A source run -----------------------------------------------------------

def test_the_checkout_config_serves_a_source_run_on_loopback():
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["server"]["address"] == "127.0.0.1"
    readme = README_PATH.read_text(encoding="utf-8")
    assert "A source run serves this computer only, and other accounts on this computer can reach it." in readme


def test_live_a_source_run_from_another_folder_listens_on_loopback_only(tmp_path, port):
    (tmp_path / "home").mkdir()
    environment = {name: value for name, value in os.environ.items()
                   if not name.upper().startswith("STREAMLIT_") and name != "ZIJ_LAUNCH_KEY"}
    dead = _closed_loopback_port()
    environment.update(HOME=str(tmp_path / "home"), XDG_DATA_HOME=str(tmp_path / "xdg"),
                       http_proxy=dead, https_proxy=dead, HTTP_PROXY=dead, HTTPS_PROXY=dead)
    # The preview command, `streamlit run <checkout>/app.py --server.port N`, run
    # from another folder; headless only so that no browser is opened.
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(APP_PATH), "--server.port", str(port),
                             "--server.headless", "true"],
                            cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for_health(port, proc)
        assert _listening(port) == ["127.0.0.1"]
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(20)
        proc.stdout.close()
