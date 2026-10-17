"""A source run refuses a session under a rebound Host (the owner's ruling 193).

A web page that makes its own name point at 127.0.0.1 (DNS rebinding) is
loaded by the browser under that name, so the page and the app it reaches
share an origin: Streamlit 1.62 takes Origin == Host as the same origin, and
with `server.allowedHosts` empty it takes any Host. A source run, which has
no launch secret, therefore gave such a page a whole session: the saved
charts, a person's birth data, the preferences. Binding to loopback is no
defence against it, since the browser is on this computer.

Now the checkout's `.streamlit/config.toml` names the one host a source run
is reached by, the address it prints and opens, `127.0.0.1`, and a session
opens under no other Host. Streamlit applies the list to the session's
connection (`/_stcore/stream`) only: plain HTTP routes still answer any Host
with the public page shell, `ok` and the host configuration, which carry no
data (a known issue, accepted with the desktop door). The port is ignored.

The live tests here start a source run with no launch secret -- `streamlit
run app.py` from the checkout, the README's developer's command, and the
preview command `streamlit run <checkout>/app.py --server.port N` from
another folder -- with a stand-in browser that records the address it is
sent to, and the desktop launcher's own server child; then send the
WebSocket opening by hand, header by header, as any client on this computer
can. Nothing they
send leaves the machine: the server's lookup of its external address, which
a foreign Origin sets off, is sent to a closed loopback port.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR
from loopback_ports import claimed_port, port_taken
from test_sec1_server_door_2026_10_13 import (  # noqa: F401  (`launched` and `port` are fixtures)
    CONFIG_PATH, README_PATH, SENTENCE, _blob, _closed_loopback_port, _elements, _held_by,
    _listening, _load_launcher, _pairs, launched, port)

# The ports the source runs here are started on: a pool of their own, apart
# from the door's and the window's (tests/loopback_ports.py).
PORTS = range(8575, 8579)

# The name, and the only one, a source run prints, opens and admits.
ALLOWED = "127.0.0.1"
REBOUND = "evil.example"


@pytest.fixture
def source_port(tmp_path_factory):
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "rebind-ports")


# --- The config ---------------------------------------------------------------

def test_the_checkout_config_admits_only_the_name_a_source_run_is_reached_by():
    server = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["server"]
    assert server["address"] == ALLOWED
    assert server["allowedHosts"] == [ALLOWED]
    # `localhost` is nowhere a reader is told to go.
    told = [README_PATH, *sorted((EXECUTABLE_DIR / "docs").glob("*.md"))]
    assert len(told) > 1
    assert [p.name for p in told if "localhost" in p.read_text(encoding="utf-8").lower()] == []


# --- A source run, live -------------------------------------------------------

_BROWSER = """#!/bin/sh
printf '%s\\n' "$1" >> {opened}
"""


def _environment(tmp_path, home):
    """A reader's environment for a source run: no STREAMLIT_* variable and
    no launch secret, a home and data folder of the test's own, the proxies
    a closed loopback port, and a stand-in browser first on the path (the
    command Streamlit runs to open one: xdg-open on Linux, open on macOS).

    A reader at a desktop has a display; a service, such as the CI runner,
    has none, and on Linux Streamlit then defaults `server.headless` to true
    and opens no browser. So the display variables are the test's own, the
    same wherever it runs: no DISPLAY, and a WAYLAND_DISPLAY naming a socket
    that does not exist, which is enough for Streamlit and reaches no screen
    (the stand-in browser needs none)."""
    browser = tmp_path / "browser"
    browser.mkdir()
    for name in ("xdg-open", "open"):
        (browser / name).write_text(_BROWSER.format(opened=tmp_path / "opened.txt"))
        (browser / name).chmod(0o755)
    # A home that has answered Streamlit's first-run question, so that no
    # prompt waits on the terminal.
    (home / ".streamlit").mkdir(parents=True, exist_ok=True)
    (home / ".streamlit" / "credentials.toml").write_text('[general]\nemail = ""\n')
    environment = {name: value for name, value in os.environ.items()
                   if not name.upper().startswith("STREAMLIT_")
                   and name not in ("ZIJ_LAUNCH_KEY", "DISPLAY", "WAYLAND_DISPLAY")}
    dead = _closed_loopback_port()
    environment.update(WAYLAND_DISPLAY=str(tmp_path / "no-display"), HOME=str(home),
                       XDG_DATA_HOME=str(tmp_path / "xdg"), http_proxy=dead, https_proxy=dead,
                       HTTP_PROXY=dead, HTTPS_PROXY=dead, PATH=f"{browser}{os.pathsep}{environment['PATH']}")
    for name in ("no_proxy", "NO_PROXY"):
        environment.pop(name, None)
    return environment


def test_a_source_run_here_opens_a_browser_with_a_display_or_without_one(tmp_path, monkeypatch):
    # On a desktop and on a service with no display, such as the CI runner,
    # the run gets the same display variables, and Streamlit's own rule for
    # `server.headless`, read from the checkout as a source run reads it,
    # comes out false: the run opens the stand-in browser in both.
    seen = []
    for where, display in (("desktop", {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}), ("service", {})):
        for name in ("DISPLAY", "WAYLAND_DISPLAY"):
            if name in display:
                monkeypatch.setenv(name, display[name])
            else:
                monkeypatch.delenv(name, raising=False)
        (tmp_path / where).mkdir()
        environment = _environment(tmp_path / where, tmp_path / where / "home")
        assert "DISPLAY" not in environment
        assert not Path(environment["WAYLAND_DISPLAY"]).exists()
        seen.append(Path(environment["WAYLAND_DISPLAY"]).name)
        rule = subprocess.run(
            [sys.executable, "-c", "from streamlit import config; print(config.get_option('server.headless'))"],
            cwd=EXECUTABLE_DIR, env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=120)
        assert rule.returncode == 0, rule.stderr
        assert rule.stdout.split()[-1] == "False", (where, rule.stdout, rule.stderr)
    assert seen[0] == seen[1]


class _SourceRun:
    def __init__(self, port, proc, output, opened):
        self.port, self.proc, self.output_path, self.opened_path = port, proc, output, opened

    def output(self):
        return self.output_path.read_text(errors="replace")

    def opened(self, timeout=60):
        """The addresses the stand-in browser was sent to, once it was."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.opened_path.exists() and self.opened_path.read_text().strip():
                return self.opened_path.read_text().split()
            time.sleep(0.25)
        raise AssertionError(f"no browser was opened; the run said: {self.output()[-2000:]}")


def _start(tmp_path, port, how, home=None, cwd=None):
    """A source run with no launch secret: `checkout` is the README's
    developer's command, `streamlit run app.py`, from the checkout, `preview`
    the preview command from another folder (`cwd`, a fresh one if not
    given)."""
    home = home or tmp_path / "home"
    home.mkdir(exist_ok=True)
    environment = _environment(tmp_path, home)
    if how == "checkout":
        argv, cwd = ["app.py", "--server.port", str(port)], EXECUTABLE_DIR
    else:
        cwd = cwd or tmp_path / "elsewhere"
        cwd.mkdir(exist_ok=True)
        argv = [str(APP_PATH), "--server.port", str(port)]
    output = tmp_path / "server-output.txt"
    with open(output, "wb") as out:
        proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", *argv], cwd=cwd, env=environment,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
    run = _SourceRun(port, proc, output, tmp_path / "opened.txt")
    deadline = time.time() + 120
    while True:
        if proc.poll() is not None:
            said = run.output()
            raise AssertionError(f"the source run exited: {said[-2000:]}{port_taken(port, said)}")
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                    f"http://127.0.0.1:{port}/_stcore/health", timeout=2):
                pass
        except OSError:
            assert time.time() < deadline, f"the source run did not answer{port_taken(port)}"
            time.sleep(0.25)
            continue
        assert _held_by(port, proc.pid) is not False, f"what answered on port {port} is not the run{port_taken(port)}"
        return run


def _stop(run):
    run.proc.terminate()
    try:
        run.proc.wait(20)
    except subprocess.TimeoutExpired:
        run.proc.kill()
        run.proc.wait(20)


@pytest.fixture(params=["checkout", "preview"])
def source_run(request, tmp_path, source_port):
    run = _start(tmp_path, source_port, request.param)
    try:
        yield run
    finally:
        _stop(run)


def _opening(port, lines, version="HTTP/1.1"):
    """The status line the server on `port` answers a WebSocket opening of
    the session's route with, the request's own header lines `lines` (Host,
    Origin ...) put before the opening's: sent byte for byte, so that a Host
    no client library would write can be sent."""
    request = (f"GET /_stcore/stream {version}\r\n" + "".join(f"{line}\r\n" for line in lines)
               + "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                 "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: streamlit\r\n\r\n")
    with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
        sock.sendall(request.encode("latin-1"))
        line = sock.makefile("rb").readline(300).decode("latin-1").strip()
    assert line.startswith("HTTP/1.1 "), line
    return int(line.split()[1])


def _script_run(port, host, origin=None, timeout=300):
    """One script run in a session opened under `host` (and `origin`), over
    Streamlit's protocol: every message sent until the run finished."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
    from websockets.sync.client import connect

    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    ws = connect(f"ws://{host}/_stcore/stream", additional_headers={"Origin": origin} if origin else {},
                 subprotocols=["streamlit"], open_timeout=30, max_size=2 ** 27, origin=None, sock=sock)
    try:
        back = BackMsg()
        back.rerun_script.query_string = ""
        back.rerun_script.page_script_hash = ""
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


def _refused(port, origin, host):
    from websockets.exceptions import InvalidStatus
    from websockets.sync.client import connect

    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    with pytest.raises(InvalidStatus) as refused:
        connect(f"ws://{host}/_stcore/stream", additional_headers={"Origin": origin} if origin else {},
                subprotocols=["streamlit"], open_timeout=30, origin=None, sock=sock).close()
    return refused.value.response.status_code


def test_live_a_source_run_opens_a_session_under_its_own_name_alone(source_run, tmp_path):
    """The README's developer's command from the checkout and the preview
    command from another folder: each prints and opens 127.0.0.1 (the name
    allowed), and listens there alone; under that name, with its port, a session opens and
    a script run completes; under a rebound name, with no Origin or with the
    page's own, and under the allowed name with a foreign Origin, the
    session's opening is refused (403)."""
    port = source_run.port
    address = f"http://{ALLOWED}:{port}"
    assert source_run.opened() == [address]
    assert f"URL: {address}" in source_run.output()
    assert "localhost" not in source_run.output()
    assert _listening(port) == [ALLOWED]
    # A whole run of the app, as the reader's own browser gets it (a source
    # run has no launch secret).
    messages = _script_run(port, f"{ALLOWED}:{port}")
    kinds = [kind for kind, _ in _elements(messages)]
    assert len(kinds) > 10 and "exception" not in kinds, kinds[:20]
    assert SENTENCE not in _blob(messages)
    for origin, host in ((None, f"{REBOUND}:{port}"),
                         (f"http://{REBOUND}:{port}", f"{REBOUND}:{port}"),
                         (f"http://{REBOUND}", f"{ALLOWED}:{port}")):
        assert _refused(port, origin, host) == 403, (origin, host)
    # The same opening under the allowed name is admitted: the refusals are
    # the Host's and the Origin's, not the request's.
    assert _opening(port, [f"Host: {ALLOWED}:{port}"]) == 101


# Each Host form, as the header lines sent, and what Streamlit 1.62 answers
# the session's opening with: 101 admits a session, 403 refuses it. Those
# admitted are each a way to write this computer's own loopback address, not
# a name anyone else can make point at it: `127.0.0.1.` (Streamlit strips the
# trailing dot of a name), the allowed name with another port or none
# (Streamlit ignores the port), the header's name in capitals, and two Host
# headers with the allowed one first (Streamlit reads the first). A browser
# sends one Host, the name in its address bar, so a page cannot send two;
# and a client that can write its own headers can as well write the allowed
# Host alone.
def _host_forms(port):
    return [
        ("the allowed name with its port", [f"Host: {ALLOWED}:{port}"], 101),
        ("the allowed name with no port", [f"Host: {ALLOWED}"], 101),
        ("the allowed name with another port", [f"Host: {ALLOWED}:1"], 101),
        ("the allowed name with a trailing dot", [f"Host: {ALLOWED}.:{port}"], 101),
        ("the header's name in capitals", [f"HOST: {ALLOWED}:{port}"], 101),
        ("the header's name in small letters, a rebound name", [f"host: {REBOUND}:{port}"], 403),
        ("two Hosts, the allowed first", [f"Host: {ALLOWED}:{port}", f"Host: {REBOUND}:{port}"], 101),
        ("two Hosts, the foreign first", [f"Host: {REBOUND}:{port}", f"Host: {ALLOWED}:{port}"], 403),
        ("a rebound name", [f"Host: {REBOUND}:{port}"], 403),
        ("an empty Host", ["Host: "], 403),
        ("no Host", [], 403),
        ("localhost", [f"Host: localhost:{port}"], 403),
        ("LOCALHOST", [f"Host: LOCALHOST:{port}"], 403),
        ("localhost with a trailing dot", [f"Host: localhost.:{port}"], 403),
        ("the allowed name as a name's first labels", [f"Host: {ALLOWED}.{REBOUND}:{port}"], 403),
        ("the allowed name as a name's last labels", [f"Host: {REBOUND}.{ALLOWED}:{port}"], 403),
        ("a userinfo before the allowed name", [f"Host: {REBOUND}@{ALLOWED}:{port}"], 403),
        ("[::1]", [f"Host: [::1]:{port}"], 403),
        ("0.0.0.0", [f"Host: 0.0.0.0:{port}"], 403),
        ("127.0.0.2", [f"Host: 127.0.0.2:{port}"], 403),
        ("127.1", [f"Host: 127.1:{port}"], 403),
        ("2130706433", [f"Host: 2130706433:{port}"], 403),
        ("the allowed name with a path", [f"Host: {ALLOWED}:{port}/x"], 403),
        ("the allowed name with a space and a name", [f"Host: {ALLOWED} {REBOUND}:{port}"], 403),
        ("the allowed name with a query", [f"Host: {ALLOWED}:{port}?q"], 403),
        ("the allowed name with a port out of range", [f"Host: {ALLOWED}:99999"], 403),
    ]


def _answers(port, forms):
    return {label: _opening(port, lines) for label, lines, _ in forms}


def test_live_malformed_and_borderline_hosts_on_a_source_run(source_run):
    forms = _host_forms(source_run.port)
    assert _answers(source_run.port, forms) == {label: status for label, _, status in forms}
    # HTTP/1.0 with no Host at all.
    assert _opening(source_run.port, [], version="HTTP/1.0") == 403


def test_live_malformed_and_borderline_hosts_on_the_desktop_child(launched):
    """The launcher's own server child, under its planted config files and
    variables: its pinned flag allows the same one name, and every form is
    answered as on a source run."""
    forms = _host_forms(launched.port)
    assert _answers(launched.port, forms) == {label: status for label, _, status in forms}
    assert _opening(launched.port, [], version="HTTP/1.0") == 403


def test_live_unexpected_origins_on_a_source_run(source_run):
    """Under the allowed Host, a foreign Origin and `null` are refused. Any
    port on `localhost` or `127.0.0.1`, and `https` on either, is admitted:
    Streamlit 1.62 takes every port of those two names for one of its own
    origins whatever the configured lists hold. A run with no launch secret
    is not checked beyond that: a session opened from another local port's
    page runs the whole app. So `streamlit run app.py` stays a developer's
    command, its exposure stated in the README, and the README's way to run
    from source is run_source.py, whose server holds every such session
    behind its launch secret (tests/test_srcrun_door_2026_10_15.py), as the
    desktop window's does."""
    port = source_run.port
    host = f"Host: {ALLOWED}:{port}"
    origins = {
        "a foreign Origin": ("http://evil.example", 403),
        "the allowed name as a foreign name's first labels": (f"http://{ALLOWED}.{REBOUND}:{port}", 403),
        "null": ("null", 403),
        "the allowed name's own": (f"http://{ALLOWED}:{port}", 101),
        "another port on 127.0.0.1": (f"http://{ALLOWED}:1", 101),
        "another port on localhost": ("http://localhost:1", 101),
        "https on the allowed name": (f"https://{ALLOWED}:{port}", 101),
        "https on localhost": (f"https://localhost:{port}", 101),
    }
    got = {label: _opening(port, [host, f"Origin: {origin}"]) for label, (origin, _) in origins.items()}
    assert got == {label: status for label, (_, status) in origins.items()}
    # Unchecked: another local port's page is given the whole app.
    messages = _script_run(port, f"{ALLOWED}:{port}", origin="http://localhost:1")
    kinds = [kind for kind, _ in _elements(messages)]
    assert len(kinds) > 10 and "exception" not in kinds, kinds[:20]
    assert SENTENCE not in _blob(messages)


# --- What a planted setting can loosen ----------------------------------------

# A config file that would let a source run take any Host, and listen on
# every interface, if it were read over the checkout's.
PLANTED_CONFIG = """\
[server]
allowedHosts = ["*"]
address = "0.0.0.0"
"""


def test_live_a_planted_config_does_not_loosen_a_source_runs_hosts(tmp_path, source_port):
    """A home folder's `~/.streamlit/config.toml` and the launch folder's
    `.streamlit/config.toml`, each saying `allowedHosts = ["*"]` and an
    address of every interface, lose to the checkout's own: Streamlit
    reads the home's, then the working folder's, then the one beside the
    script, each later one winning. So a rebound Host is still refused from
    the checkout (the home's planted) and from a planted folder by the
    preview command (both planted)."""
    home = tmp_path / "home"
    planted = tmp_path / "planted"
    for folder in (home, planted):
        (folder / ".streamlit").mkdir(parents=True)
        (folder / ".streamlit" / "config.toml").write_text(PLANTED_CONFIG)
    for how in ("checkout", "preview"):
        where = tmp_path / how
        where.mkdir()
        run = _start(where, source_port, how, home=home, cwd=planted)
        try:
            port = run.port
            assert _opening(port, [f"Host: {REBOUND}:{port}"]) == 403, how
            assert _opening(port, [f"Host: {REBOUND}:{port}", f"Origin: http://{REBOUND}:{port}"]) == 403, how
            assert _opening(port, [f"Host: {ALLOWED}:{port}"]) == 101, how
            # The checkout's address holds too, over the planted 0.0.0.0.
            assert _listening(port) == [ALLOWED], how
        finally:
            _stop(run)


# A config file that would turn Streamlit's Origin check off, if it were read
# over the checkout's: a page from any site could then open a session.
CORS_OFF_CONFIG = """\
[server]
enableCORS = false
"""


def test_the_checkout_config_keeps_the_origin_check_on():
    assert tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["server"]["enableCORS"] is True


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_does_not_turn_a_source_runs_origin_check_off(tmp_path, source_port, where):
    """A home folder's `~/.streamlit/config.toml`, or the run folder's
    `.streamlit/config.toml`, saying `enableCORS = false`, loses to the
    checkout's own `enableCORS = true` (the one beside the script is read
    last). So the preview command run from that folder still refuses, under
    the allowed Host, a session's opening from a foreign page's Origin and
    from `null` (a sandboxed frame or a local file), and admits the app's
    own Origin. Without the checkout's setting the plant admits both."""
    home = tmp_path / "home"
    planted = tmp_path / "planted"
    target = home if where == "home" else planted
    (target / ".streamlit").mkdir(parents=True)
    (target / ".streamlit" / "config.toml").write_text(CORS_OFF_CONFIG)
    planted.mkdir(exist_ok=True)
    run = _start(tmp_path, source_port, "preview", home=home, cwd=planted)
    try:
        port = run.port
        origins = {f"http://{REBOUND}:{port}": 403, "null": 403, f"http://{ALLOWED}:{port}": 101}
        got = {origin: _opening(port, [f"Host: {ALLOWED}:{port}", f"Origin: {origin}"]) for origin in origins}
        assert got == origins, where
    finally:
        _stop(run)


# --- The other door options a planted setting could loosen --------------------
#
# Streamlit takes each option from the last config file that sets it, and the
# checkout's own is read last; so an option the checkout's file leaves out is
# the planted file's to set. The checkout's config sets each of these as the
# desktop launcher pins it by flag, the two lists of origins empty where the
# launcher's name the window's own port (the owner's ruling 200).

# Each option the checkout's config pins, and the value the launcher's flag
# gives it where that value needs no port (None where it does).
DOOR_OPTIONS = {
    "server.corsAllowedOrigins": ([], None),
    "server.enableXsrfProtection": (True, "true"),
    "server.xsrfCookieSameSite": ("lax", "lax"),
    "server.scriptHealthCheckEnabled": (False, "false"),
    "server.enableStaticServing": (False, "false"),
    "browser.serverAddress": (ALLOWED, ALLOWED),
    "browser.gatherUsageStats": (False, "false"),
    "global.developmentMode": (False, "false"),
    "global.e2eTest": (False, "false"),
    "client.allowedOrigins": ([], None),
}


def test_the_checkout_config_pins_a_source_runs_other_door_options(monkeypatch):
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    flagged = _pairs(_load_launcher(monkeypatch)._server_options("8501"))
    got = {}
    for key in DOOR_OPTIONS:
        section, _, name = key.partition(".")
        got[key] = config.get(section, {}).get(name, "(not set)")
    assert got == {key: value for key, (value, _) in DOOR_OPTIONS.items()}
    # Where the launcher's value needs no port, the two agree.
    agree = {key: flagged[key] for key, (_, flag) in DOOR_OPTIONS.items() if flag is not None}
    assert len(agree) == 8
    assert agree == {key: flag for key, (_, flag) in DOOR_OPTIONS.items() if flag is not None}
    # The window's own origin is the launcher's one entry in each list.
    assert flagged["server.corsAllowedOrigins"] == flagged["client.allowedOrigins"] == "http://127.0.0.1:8501"


def _planted_run(tmp_path, port, where, planted_config, how="preview"):
    """The preview command, run from a folder of its own, with
    `planted_config` written to the home folder's `~/.streamlit/config.toml`
    or the run folder's `.streamlit/config.toml` (`where`; "none" plants
    nothing)."""
    home = tmp_path / "home"
    planted = tmp_path / "planted"
    home.mkdir()
    planted.mkdir()
    if where != "none":
        target = home if where == "home" else planted
        (target / ".streamlit").mkdir(exist_ok=True)
        (target / ".streamlit" / "config.toml").write_text(planted_config)
    return _start(tmp_path, port, how, home=home, cwd=planted)


def _get(port, path, headers=None, timeout=60):
    """A plain GET of `path` straight to the run: status, headers (names in
    small letters, every Set-Cookie kept), body."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path, headers=headers or {})
        answer = connection.getresponse()
        body = answer.read()
        heads = {name.lower(): value for name, value in answer.getheaders() if name.lower() != "set-cookie"}
        return answer.status, heads, answer.msg.get_all("Set-Cookie") or [], body
    finally:
        connection.close()


PLANTED_NAMED_SITE = """\
[server]
corsAllowedOrigins = ["http://evil.example"]

[browser]
serverAddress = "evil.example"
"""


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_names_no_site_a_source_run_trusts(tmp_path, source_port, where):
    """A planted `server.corsAllowedOrigins` naming a site, and a planted
    `browser.serverAddress` of that site's name, would each make Streamlit
    take that site for one of its own origins (only the name is compared,
    so any scheme or port of it), and the second would send the reader's
    browser there. The checkout's empty list and its own address win: a
    session's opening from that site, by http with the run's port or by
    https, is refused, its health check is answered with no cross-origin
    grant, and the run prints and opens 127.0.0.1."""
    run = _planted_run(tmp_path, source_port, where, PLANTED_NAMED_SITE)
    try:
        port = run.port
        origins = {f"http://{REBOUND}:{port}": 403, f"https://{REBOUND}": 403, f"http://{ALLOWED}:{port}": 101}
        got = {origin: _opening(port, [f"Host: {ALLOWED}:{port}", f"Origin: {origin}"]) for origin in origins}
        assert got == origins, where
        assert "access-control-allow-origin" not in _get(port, "/_stcore/health", {"Origin": f"http://{REBOUND}"})[1]
        assert run.opened() == [f"http://{ALLOWED}:{port}"]
        assert [line.strip() for line in run.output().splitlines() if "URL:" in line] == [
            f"URL: http://{ALLOWED}:{port}"]
    finally:
        _stop(run)


def _admitted_session_asks_to_stop_the_runtime(port):
    """An admitted session (under the allowed Host, as any program on this
    computer can open one) sends Streamlit's test-only message that stops
    the runtime."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from websockets.sync.client import connect

    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    ws = connect(f"ws://{ALLOWED}:{port}/_stcore/stream", subprotocols=["streamlit"], open_timeout=30, origin=None,
                 sock=sock)
    try:
        back = BackMsg()
        back.debug_shutdown_runtime = True
        ws.send(back.SerializeToString())
        time.sleep(3)
    finally:
        ws.close()


REFUSED_STOP = "Client tried to shut down runtime when not in development mode or e2e testing."


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_test_mode_lets_no_session_stop_a_source_run(tmp_path, source_port, where):
    """A planted `global.e2eTest = true` would let any admitted session stop
    the runtime (the health check then answers 503). The checkout's `false`
    wins: Streamlit refuses the message, says so, and the run stays up."""
    run = _planted_run(tmp_path, source_port, where, "[global]\ne2eTest = true\n")
    try:
        _admitted_session_asks_to_stop_the_runtime(run.port)
        assert _get(run.port, "/_stcore/health")[0] == 200, where
        assert REFUSED_STOP in run.output()
        assert run.proc.poll() is None
    finally:
        _stop(run)


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_development_mode_does_not_take_a_source_run(tmp_path, source_port, where):
    """A planted `global.developmentMode = true` would stop the preview
    command from starting at all (Streamlit refuses a port given on the
    command line in that mode), grant every site cross-origin reads of the
    plain routes, and let any admitted session stop the runtime. The
    checkout's `false` wins: the preview command starts and serves on its
    own port, the health check grants no other site, and a session's
    request to stop the runtime is refused."""
    run = _planted_run(tmp_path, source_port, where, "[global]\ndevelopmentMode = true\n")
    try:
        port = run.port
        assert f"URL: http://{ALLOWED}:{port}" in run.output(), where
        assert _listening(port) == [ALLOWED]
        assert "access-control-allow-origin" not in _get(port, "/_stcore/health", {"Origin": f"http://{REBOUND}"})[1]
        _admitted_session_asks_to_stop_the_runtime(port)
        assert _get(port, "/_stcore/health")[0] == 200
        assert REFUSED_STOP in run.output()
    finally:
        _stop(run)


PLANTED_XSRF = """\
[server]
enableXsrfProtection = false
xsrfCookieSameSite = "none"
"""


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_keeps_a_source_runs_xsrf_cookie(tmp_path, source_port, where):
    """A planted `enableXsrfProtection = false` would drop the token an
    upload must carry (no cookie is set), and a planted `xsrfCookieSameSite
    = "none"` would send its cookie with requests from other sites. The
    checkout's values win: the cookie is set, and kept to this site."""
    run = _planted_run(tmp_path, source_port, where, PLANTED_XSRF)
    try:
        cookies = [c for c in _get(run.port, "/_stcore/health")[2] if c.startswith("_streamlit_xsrf=")]
        assert len(cookies) == 1, (where, cookies)
        attributes = {part.strip().lower() for part in cookies[0].split(";")[1:]}
        assert "samesite=lax" in attributes, cookies
        assert "samesite=none" not in attributes, cookies
    finally:
        _stop(run)


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_opens_no_route_that_runs_the_script(tmp_path, source_port, where):
    """A planted `scriptHealthCheckEnabled = true` would open a route that
    runs the app's script outside any session for whoever asks (and the
    plain routes answer any Host). The checkout's `false` wins: the route is
    not there, and the path is answered with the page shell, as any path is,
    the script not run."""
    run = _planted_run(tmp_path, source_port, where, "[server]\nscriptHealthCheckEnabled = true\n")
    try:
        status, heads, _, body = _get(run.port, "/_stcore/script-health-check", timeout=300)
        shell = _get(run.port, "/")
        assert (status, heads.get("content-type", "").split(";")[0]) == (200, "text/html"), where
        assert body == shell[3] and b"<html" in body.lower()
    finally:
        _stop(run)


@pytest.mark.parametrize("where", ["none", "home", "run folder"])
def test_live_a_source_run_gathers_no_usage_statistics(tmp_path, source_port, where):
    """Streamlit's default on a source run is to gather usage statistics in
    the reader's browser, and a planted `browser.gatherUsageStats = true`
    would turn it on in turn. The checkout's `false` wins over both: the
    session's own handshake tells the browser not to."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
    from websockets.sync.client import connect

    run = _planted_run(tmp_path, source_port, where, "[browser]\ngatherUsageStats = true\n")
    try:
        sock = socket.create_connection(("127.0.0.1", run.port), timeout=30)
        ws = connect(f"ws://{ALLOWED}:{run.port}/_stcore/stream", subprotocols=["streamlit"], open_timeout=30,
                     max_size=2 ** 27, origin=None, sock=sock)
        try:
            back = BackMsg()
            back.rerun_script.query_string = ""
            back.rerun_script.page_script_hash = ""
            ws.send(back.SerializeToString())
            handshake = None
            deadline = time.time() + 120
            while handshake is None and time.time() < deadline:
                forward = ForwardMsg()
                forward.ParseFromString(ws.recv(timeout=max(1, deadline - time.time())))
                if forward.WhichOneof("type") == "new_session":
                    handshake = forward.new_session
        finally:
            ws.close()
        assert handshake is not None, "no handshake came"
        assert handshake.config.gather_usage_stats is False, where
    finally:
        _stop(run)


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_serves_no_folder_of_a_source_run(tmp_path, source_port, where):
    """A planted `enableStaticServing = true` would serve whatever a
    `static` folder beside app.py holds to whoever asks, under any Host (the
    checkout has none today; the route then answers 404). The checkout's
    `false` wins: there is no such route, and its path is answered with the
    page shell, as any path is."""
    run = _planted_run(tmp_path, source_port, where, "[server]\nenableStaticServing = true\n")
    try:
        status, heads, _, body = _get(run.port, "/app/static/app.py")
        assert (status, heads.get("content-type", "").split(";")[0]) == (200, "text/html"), where
        assert body == _get(run.port, "/")[3]
    finally:
        _stop(run)


@pytest.mark.parametrize("where", ["home", "run folder"])
def test_live_a_planted_config_names_no_outer_page_that_may_steer_a_source_run(tmp_path, source_port, where):
    """A planted `client.allowedOrigins` would name the outer pages whose
    messages the app's page obeys when it is framed (stop the script, rerun
    it); with none set, a source run names Streamlit's own hosting sites.
    The checkout's empty list wins: the page is told of none, so it listens
    to no outer page."""
    run = _planted_run(tmp_path, source_port, where, '[client]\nallowedOrigins = ["https://*.evil.example"]\n')
    try:
        status, _, _, body = _get(run.port, "/_stcore/host-config")
        assert (status, json.loads(body)["allowedOrigins"]) == (200, []), where
    finally:
        _stop(run)
