"""A source run goes through the desktop window's door.

`python run_source.py`, the README's way to run from source, makes a key for
that run alone, gives it to the server it starts in that server's
environment (never on a command line, in a file or in a log), and prints the
one address that carries it. app.py's door then keeps that server as it
keeps the desktop app's: a client with no key, a wrong key, or a page served
from another local port is told one sentence and stopped before any saved
chart or preference is read; the printed address opens the whole app. The
server takes the desktop launcher's own options for who can connect, and
the script stops it however the run ends: Ctrl-C, a stop signal, the
server's own end, and the script's death.

`streamlit run app.py` stays a developer's command with no key, unchecked,
as the README says (tests/test_rebind_source_run_2026_10_14.py).

The live tests start the script with a port of their own pool, from a
folder of their own, with a home and a data folder of their own holding two
invented records, hostile config and STREAMLIT_* variables planted, and
proxies sent to a closed loopback port; nothing they send leaves the
machine. Process checks read /proc, as the suite's other live server tests
do.
"""
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from conftest import EXECUTABLE_DIR
from loopback_ports import claimed_port, port_taken
from test_sec1_server_door_2026_10_13 import (
    OTHER, PLANTED_CONFIG, PLANTED_VARIABLES, PREFERENCES, README_PATH, RECORD, RECORDS, SENTENCE, _blob,
    _closed_loopback_port, _free_port, _held_by, _listening, _load_launcher, _pairs, _session,
    _told_only_the_sentence)

SCRIPT = EXECUTABLE_DIR / "run_source.py"
KEY_VARIABLE = "ZIJ_LAUNCH_KEY"

# The ports the script's runs here are started on: a pool of their own
# (tests/loopback_ports.py), apart from the other live tests' pools.
PORTS = range(8589, 8593)

# The script, with its port chosen as the test's pool says; everything else
# is the script's own `main`.
# A third argument, where given, is the key the run makes.
_ON_PORT = ("import sys, types; sys.path.insert(0, sys.argv[1]); import run_source; "
            "port = int(sys.argv[2]); run_source._free_port = lambda: port; "
            "key = sys.argv[3:]; "
            "run_source.secrets = types.SimpleNamespace(token_urlsafe=lambda n: key[0]) if key else run_source.secrets; "
            "sys.argv = [run_source.__file__]; sys.exit(run_source.main())")

_ADDRESS = re.compile(r"Open the app at (http://127\.0\.0\.1:(\d+)/\?launch=(\S+))")


@pytest.fixture
def source_port(tmp_path_factory):
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "srcrun-ports")


@pytest.fixture
def second_port(tmp_path_factory, source_port):
    yield from claimed_port([p for p in PORTS if p != source_port],
                            tmp_path_factory.getbasetemp().parent / "srcrun-ports")


# --- The script, read --------------------------------------------------------

def _load_script():
    spec = importlib.util.spec_from_file_location("run_source_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_pins_the_launchers_options_for_who_can_connect(monkeypatch):
    """Every option the script passes is the launcher's, with the launcher's
    value, but the one that hides Streamlit's own keyless address; and every
    launcher option that bears on who can connect, or on where the printed
    address leads, is among them."""
    run_source = _load_script()
    launcher = _pairs(_load_launcher(monkeypatch)._server_options("8590"))
    script = _pairs(run_source._server_options(8590))
    assert script.pop("logger.hideWelcomeMessage") == "true"
    assert {name: (value, launcher.get(name)) for name, value in script.items()
            if launcher.get(name) != value} == {}
    door = {"server.address", "server.port", "server.allowedHosts", "server.enableCORS",
            "server.corsAllowedOrigins", "browser.serverAddress", "server.enableXsrfProtection",
            "server.xsrfCookieSameSite", "client.allowedOrigins", "server.sslCertFile", "server.sslKeyFile",
            "server.baseUrlPath", "global.developmentMode", "global.e2eTest", "server.enableStaticServing",
            "server.scriptHealthCheckEnabled", "server.headless", "server.disconnectedSessionTTL"}
    assert door <= set(launcher), sorted(door - set(launcher))
    assert sorted(door - set(script)) == []
    assert script["server.headless"] == "true" and script["server.address"] == "127.0.0.1"
    # The names the script passes the key under are app.py's.
    assert (run_source.LAUNCH_KEY_VARIABLE, run_source.LAUNCH_KEY_PARAMETER) == (KEY_VARIABLE, "launch")


def test_the_script_is_standard_library_only_and_imports_no_launcher():
    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    # streamlit is imported in the server child alone, which runs the app.
    assert imported - set(sys.stdlib_module_names) == {"streamlit"}, imported
    assert "desktop_launcher" not in imported and "webview" not in imported


def test_the_readme_runs_from_source_through_the_script():
    readme = README_PATH.read_text(encoding="utf-8")
    section = readme.split("## Running from source", 1)[1].split("\n## ", 1)[0]
    block = section.split("```bash\n", 1)[1].split("```", 1)[0]
    assert block.splitlines() == ["pip install -r requirements.txt", "python run_source.py"], block
    prose = " ".join(section.split("```", 2)[2].split())
    assert ("Open the address it prints, and open it again after reloading the page: the app opens only at that "
            "address, which carries a key made for this run alone.") in prose
    assert ("`streamlit run app.py` is a developer's command, with no key: any program on this computer, a web "
            "page served from it included, can open the app there and read, change or delete its saved charts."
            ) in prose


# --- The script, live --------------------------------------------------------

def _seed(tmp_path):
    """Two invented records and a preferences file in the run's own data
    folder, written by the engine as the app writes them."""
    seed = subprocess.run(
        [sys.executable, "-c",
         "import json, sys; sys.path.insert(0, sys.argv[1]); import engine; "
         "assert engine.write_saved_charts(json.loads(sys.argv[2])); "
         "engine.PREFERENCES_PATH.write_text(sys.argv[3])",
         str(EXECUTABLE_DIR), json.dumps(RECORDS), json.dumps(PREFERENCES)],
        env={**{k: v for k, v in os.environ.items() if k != "ALMUTEN_NO_PREFERENCES"},
             "XDG_DATA_HOME": str(tmp_path / "xdg"), "HOME": str(tmp_path / "home")},
        capture_output=True, text=True, timeout=120)
    assert seed.returncode == 0, seed.stderr
    prefs = tmp_path / "xdg" / "Zij" / "preferences.json"
    assert prefs.read_text() == json.dumps(PREFERENCES)
    return prefs


def _environment(tmp_path):
    """A reader's environment, with a home, data and temporary folder of the
    run's own, hostile STREAMLIT_* variables and a hostile config in the
    home folder, no display, and the proxies a closed loopback port."""
    home = tmp_path / "home"
    # A stand-in browser, under each name a browser is opened by, that
    # records the address it is sent to.
    browser = tmp_path / "browser"
    browser.mkdir(exist_ok=True)
    for name in ("xdg-open", "open", "stand-in-browser"):
        (browser / name).write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" >> {tmp_path / 'opened.txt'}\n")
        (browser / name).chmod(0o755)
    (home / ".streamlit").mkdir(parents=True, exist_ok=True)
    (home / ".streamlit" / "config.toml").write_text(PLANTED_CONFIG)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    environment = {name: value for name, value in os.environ.items()
                   if not name.upper().startswith("STREAMLIT_")
                   and name not in ("ZIJ_LAUNCH_KEY", "ALMUTEN_NO_PREFERENCES", "DISPLAY", "WAYLAND_DISPLAY",
                                    "no_proxy", "NO_PROXY")}
    dead = _closed_loopback_port()
    environment.update(PLANTED_VARIABLES)
    environment.update(HOME=str(home), XDG_DATA_HOME=str(tmp_path / "xdg"), TMPDIR=str(tmp_path / "tmp"),
                       http_proxy=dead, https_proxy=dead, HTTP_PROXY=dead, HTTPS_PROXY=dead,
                       BROWSER=str(browser / "stand-in-browser"),
                       PATH=f"{browser}{os.pathsep}{environment['PATH']}")
    return environment


class _Run:
    """The script, started as a reader starts it, with its output read as it
    comes."""

    def __init__(self, tmp_path, port, key=None):
        self.tmp_path, self.port, self.lines, self.ready = tmp_path, port, [], threading.Event()
        cwd = tmp_path / "elsewhere"
        cwd.mkdir(exist_ok=True)
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _ON_PORT, str(EXECUTABLE_DIR), str(port), *([key] if key else [])], cwd=cwd,
            env=_environment(tmp_path),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.append(line)
            if _ADDRESS.search(line):
                self.ready.set()

    def output(self):
        return "".join(self.lines)

    def address(self, timeout=120):
        """The printed address, its port and its key, once printed."""
        if not self.ready.wait(timeout):
            raise AssertionError(f"no address was printed: {self.output()[-2000:]}{port_taken(self.port)}")
        found = [m.groups() for m in map(_ADDRESS.search, self.lines) if m]
        assert len(found) == 1, found
        url, port, key = found[0]
        assert int(port) == self.port
        return url, key

    def ended(self, timeout=60):
        """The script's exit code, once it has ended."""
        code = self.proc.wait(timeout)
        self.reader.join(10)
        return code

    def stop(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(20)
        for pid in _servers(self.port):
            os.kill(pid, signal.SIGKILL)


def _servers(port):
    """The pids of every process that is the script's server child for
    `port` (its command line names the script, its serve argument and the
    port)."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if str(SCRIPT).encode() in argv and b"--serve" in argv and str(port).encode() in argv:
            found.append(int(entry.name))
    return found


def _gone(port, timeout=30):
    """Whether no server child for `port` is left, within `timeout`."""
    deadline = time.monotonic() + timeout
    while _servers(port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.25)
    return True


@pytest.fixture
def run(tmp_path, source_port):
    prefs = _seed(tmp_path)
    started = _Run(tmp_path, source_port)
    started.prefs = prefs
    try:
        yield started
    finally:
        started.stop()


def test_live_the_printed_address_opens_the_app_and_nothing_else_does(run):
    url, key = run.address()
    port = run.port
    [server] = _servers(port)
    assert _held_by(port, server) is True
    assert _listening(port) == ["127.0.0.1"]
    # Any local client (another account, a script) sends no Origin.
    _told_only_the_sentence(_session(port), "no key")
    _told_only_the_sentence(_session(port, query="launch="), "an empty key")
    _told_only_the_sentence(_session(port, query="launch=" + key[:-1] + ("A" if key[-1] != "A" else "B")),
                            "a wrong key")
    # A page served from another local port passes Streamlit's origin check.
    _told_only_the_sentence(_session(port, origin=f"http://localhost:{_free_port()}"), "another local port")
    _told_only_the_sentence(_session(port, origin="http://127.0.0.1:1"), "another port on 127.0.0.1")
    _told_only_the_sentence(_session(port, origin=f"https://localhost:{port}"), "https on localhost")
    assert run.prefs.read_text() == json.dumps(PREFERENCES), "a client without the key wrote the preferences"
    # The key reached the server in its environment, and no STREAMLIT_*
    # variable did.
    environ = Path(f"/proc/{server}/environ").read_bytes().split(b"\0")
    assert f"{KEY_VARIABLE}={key}".encode() in environ, "the key is not in the server's environment"
    assert not [entry for entry in environ if entry.upper().startswith(b"STREAMLIT_")]
    # The printed address itself: the whole app, the launch counted.
    window = _session(port, query=url.split("?", 1)[1])
    blob = _blob(window)
    assert RECORD in blob and OTHER in blob and "1931-07-04" in blob and SENTENCE not in blob
    assert json.loads(run.prefs.read_text())["_launches"] == PREFERENCES["_launches"] + 1
    # A browser's own load of the address: the page's shell.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=30) as page:
        assert page.status == 200 and page.headers.get_content_type() == "text/html"
    # The key is printed once, on the address (no request log repeats it),
    # and lies on no command line.
    time.sleep(1)
    assert run.output().count(key) == 1
    for pid in (run.proc.pid, server):
        assert key.encode() not in Path(f"/proc/{pid}/cmdline").read_bytes()
    # Streamlit's own address, which carries no key, is not printed.
    assert "You can now view" not in run.output() and "URL:" not in run.output()
    # No browser is opened: one started with the address would hold the key
    # on its command line.
    assert not (run.tmp_path / "opened.txt").exists()


def test_live_the_key_is_written_to_no_file(run, tmp_path):
    """Nothing the run writes, in its home, data, temporary and starting
    folders or in the checkout, holds the key."""
    started = time.time() - 1
    url, key = run.address()
    _session(run.port, query=url.split("?", 1)[1])
    run.proc.send_signal(signal.SIGINT)
    run.ended()
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(written) > 2, written
    written += [p for p in EXECUTABLE_DIR.rglob("*") if ".git" not in p.parts and p.is_file()
                and p.stat().st_mtime >= started]
    assert [str(p) for p in written if key.encode() in p.read_bytes()] == []


def test_live_ctrl_c_stops_the_run_and_its_server(run):
    run.address()
    assert len(_servers(run.port)) == 1
    os.killpg(run.proc.pid, signal.SIGINT)        # a terminal's Ctrl-C reaches the whole group
    assert run.ended() == 130
    assert _gone(run.port)


def _child_started(started, timeout=60):
    """Whether the run's server child has started (before its server is
    up), the script still running."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and started.proc.poll() is None:
        if _servers(started.port):
            return True
        time.sleep(0.05)
    return False


def test_live_ctrl_c_during_start_up_leaves_no_server(tmp_path, source_port):
    started = _Run(tmp_path, source_port)
    try:
        assert _child_started(started), started.output()
        os.killpg(started.proc.pid, signal.SIGINT)
        assert started.ended() == 130
        assert _gone(source_port)
        assert not started.ready.is_set(), started.output()
    finally:
        started.stop()


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGHUP"])
def test_live_a_stop_signal_stops_the_run_and_its_server(run, signal_name):
    run.address()
    number = getattr(signal, signal_name)
    run.proc.send_signal(number)
    assert run.ended() == 128 + number
    assert _gone(run.port)


def test_live_the_run_ends_when_its_server_does(run):
    run.address()
    [server] = _servers(run.port)
    os.kill(server, signal.SIGKILL)
    assert run.ended() != 0
    assert _gone(run.port)


def test_live_a_killed_script_leaves_no_server(run):
    """The script killed outright runs nothing more; its server sees its
    input end and stops itself."""
    run.address()
    [server] = _servers(run.port)
    run.proc.kill()
    run.ended()
    assert _gone(run.port, timeout=40), f"server {server} outlived its script"


def test_live_a_taken_port_prints_no_address(tmp_path, source_port):
    """A program that holds the port first, and answers Streamlit's health
    check there, is sent no key: the server cannot bind, and the run ends
    saying so."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # As the server would bind it: past the last test's closed connections.
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", source_port))
    holder.listen()
    answered = []

    def answer():
        while True:
            try:
                conn, _ = holder.accept()
            except OSError:
                return
            with conn:
                answered.append(conn.recv(4096))
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")

    threading.Thread(target=answer, daemon=True).start()
    started = _Run(tmp_path, source_port)
    try:
        assert started.ended(timeout=120) != 0
        assert not started.ready.is_set()
        assert "launch=" not in started.output()
        assert "The app's server stopped before it was ready." in started.output()
        assert not [request for request in answered if b"launch" in request]
        assert _gone(source_port)
    finally:
        started.stop()
        holder.close()


def test_live_two_runs_each_open_with_their_own_key_alone(tmp_path, source_port, second_port):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _seed(tmp_path / "a")
    _seed(tmp_path / "b")
    first, second = _Run(tmp_path / "a", source_port), _Run(tmp_path / "b", second_port)
    try:
        (url_a, key_a), (url_b, key_b) = first.address(), second.address()
        assert key_a != key_b
        _told_only_the_sentence(_session(second_port, query="launch=" + key_a), "the first run's key")
        _told_only_the_sentence(_session(source_port, query="launch=" + key_b), "the second run's key")
        assert RECORD in _blob(_session(second_port, query="launch=" + key_b))
    finally:
        first.stop()
        second.stop()


def test_live_a_key_a_shell_or_an_address_would_mangle_still_opens_by_the_printed_address(tmp_path, source_port):
    """The script's keys are URL-safe; one that is not is still carried
    whole by the address printed, and nothing else opens the app."""
    _seed(tmp_path)
    mangled = "a b&c=d+e%f/g?h#i'\"$(x)`;\u00e9-"
    started = _Run(tmp_path, source_port, key=mangled)
    try:
        url, _ = started.address()
        query = url.split("?", 1)[1]
        assert query == "launch=" + urllib.parse.quote_plus(mangled)
        assert RECORD in _blob(_session(source_port, query=query))
        _told_only_the_sentence(_session(source_port, query="launch=" + mangled), "the key unquoted")
        _told_only_the_sentence(_session(source_port), "no key")
    finally:
        started.stop()


def test_the_script_takes_no_arguments(tmp_path):
    said = subprocess.run([sys.executable, str(SCRIPT), "--server.port", "8590"], cwd=tmp_path,
                          env=_environment(tmp_path), capture_output=True, text=True, timeout=60)
    assert said.returncode == 1 and said.stderr.strip() == "run_source.py takes no arguments.", said
    assert said.stdout == ""
