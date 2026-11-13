"""The local server and what reaches it.

The launcher's server child, started as the launcher starts it, and the
server child of a source run through run_source.py, against what each does
not serve: an Origin from another site (no lookup of this computer's
public address, and no wait on one), a Host it does not answer on any HTTP
route, a file sent to it, and a config file planted in the folder the program
is started from and in the home folder. Then a developer's `streamlit run
app.py`: the checkout's config keeps any client from having Streamlit write
into the app's folder, and app.py empties zoneinfo's search path before any import that can make a zone.

Every server here runs under an audit hook that refuses, and records, any
connection, send or name lookup that leaves this computer; the public-address
lookup is recorded in its place and never made.
"""
import importlib.util
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import types
import urllib.request
from pathlib import Path

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR
from loopback_ports import claimed_port, port_taken

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"
SCRIPT_PATH = EXECUTABLE_DIR / "run_source.py"
LIMITS_PATH = EXECUTABLE_DIR / "server_limits.py"
CONFIG_PATH = EXECUTABLE_DIR / ".streamlit" / "config.toml"
SENTINEL = "--run-streamlit-server"
SENTENCE = ("This page is not the one the app opened; use the window or tab it opened when it started, "
            "or start the app again.")
PORTS = range(8593, 8597)

# Run first in every server child: the audit hook, the record of what the
# server asked for, and the public-address lookup replaced by its record (a
# wait of one second, as an unreachable service's timeout makes). Then the
# command the child was given, as its own __main__.
CHILD = r'''
import ipaddress, json, os, runpy, socket, sys, time
RECORD = sys.argv.pop(1)

def note(kind, what):
    with open(RECORD, "a", encoding="utf-8") as record:
        record.write(json.dumps([kind, what]) + "\n")

def loopback(host):
    if host is None or host in ("", b""):
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").split("%")[0].lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

def hook(event, args):
    if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        address = args[1] if len(args) > 1 else None
        if isinstance(address, tuple) and address and not loopback(address[0]):
            kind = "datagram" if getattr(args[0], "type", None) == socket.SOCK_DGRAM else "stream"
            note("refused", [event, kind, repr(address)])
            raise PermissionError("no connection leaves this computer here")
    elif event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
                   "socket.gethostbyaddr"):
        if args and not loopback(args[0]):
            note("refused", [event, "lookup", repr(args[0])])
            raise PermissionError("no name is looked up here")
    elif event == "open" and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if os.path.basename(path) in ("config.toml", "secrets.toml", "credentials.toml"):
            note("opened", os.path.abspath(path))
        zones = os.environ.get("PYTHONTZPATH")
        if zones and os.path.abspath(path).startswith(zones):
            note("zone", os.path.abspath(path))
    elif event == "exec" and getattr(args[0], "co_filename", "").endswith("app.py"):
        note("script", args[0].co_filename)
    elif event == "import" and os.environ.get("TRACE_IMPORTS"):
        zoneinfo = sys.modules.get("zoneinfo")
        path = getattr(zoneinfo, "TZPATH", "(partial)") if zoneinfo else None
        note("import", [args[0], list(path) if isinstance(path, tuple) else path])

sys.addaudithook(hook)

from streamlit import net_util

def asked(url, timeout=5):
    note("asked", url)
    time.sleep(1)
    return None

net_util._make_blocking_http_get = asked
del sys.argv[0]
if sys.argv[0] == "-m":
    del sys.argv[0]
    runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)
else:
    # As `python <script>` runs it: the script's folder first on the path,
    # not the folder it is started from.
    sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[0]))
    runpy.run_path(sys.argv[0], run_name="__main__")
'''

# A config file planted where the program is started and in the home folder:
# every line would change what the window shows or fetches, or open the door.
PLANTED_CONFIG = """\
[server]
address = "0.0.0.0"
enableCORS = false
allowedHosts = ["*"]
enableStaticServing = true
headless = false
enableXsrfProtection = false
corsAllowedOrigins = ["https://evil.example"]
maxUploadSize = 500
[global]
developmentMode = true
[theme]
base = "light"
textColor = "#FFFFFE"
backgroundColor = "#FFFFFE"
font = "planted"
[[theme.fontFaces]]
family = "planted"
url = "https://example.invalid/digits-swapped.woff2"
[client]
showSidebarNavigation = false
"""
PLANTED_SECRETS = '[auth]\ncookie_secret = "known-to-the-planter"\n'


def _load_launcher(monkeypatch):
    """desktop_launcher.py as a module, with a stand-in for its window
    library (the server half never calls it)."""
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_local_server", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def port(tmp_path_factory):
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "local-server-ports")


def _dead_proxy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def _environment(tmp_path, base):
    """`base`, less any display, with the home and the data folder under
    `tmp_path` and every proxy pointed at a loopback port nothing listens on."""
    dead = _dead_proxy()
    environment = {name: value for name, value in base.items()
                   if name not in ("DISPLAY", "WAYLAND_DISPLAY", "no_proxy", "NO_PROXY", "ALMUTEN_NO_PREFERENCES")}
    environment.update(HOME=str(tmp_path / "home"), XDG_DATA_HOME=str(tmp_path / "xdg"),
                       http_proxy=dead, https_proxy=dead, HTTP_PROXY=dead, HTTPS_PROXY=dead)
    return environment


def _records(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stop(proc):
    if proc.poll() is None:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(20)
    for stream in (proc.stdin, proc.stdout):
        if stream:
            stream.close()


def _wait_for_health(port, proc, timeout=180):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            said = proc.stdout.read()
            raise AssertionError(f"the server exited: {said[-3000:]}{port_taken(port, said)}")
        try:
            with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2):
                return
        except OSError:
            time.sleep(0.25)
    raise AssertionError(f"the server did not answer{port_taken(port)}")


@pytest.fixture(params=["window", "source run"])
def served(request, tmp_path, monkeypatch, port):
    """On `port`, the launcher's server child as the launcher starts it (its
    environment, its secret, its input a pipe held open), or run_source.py's
    server child as the script starts it (its key in the environment, its
    input a pipe), from a working folder and a home folder that each hold a
    planted config file."""
    launcher = _load_launcher(monkeypatch)
    stub = tmp_path / "stub" / "webview"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("")
    for folder in (tmp_path / "cwd", tmp_path / "home"):
        (folder / ".streamlit").mkdir(parents=True)
        (folder / ".streamlit" / "config.toml").write_text(PLANTED_CONFIG)
        (folder / ".streamlit" / "secrets.toml").write_text(PLANTED_SECRETS)
    record = tmp_path / "record.jsonl"
    secret = "launch-secret-" + "q" * 30
    with monkeypatch.context() as m:
        for name, value in _environment(tmp_path, dict(os.environ)).items():
            m.setenv(name, value)
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "no_proxy", "NO_PROXY", "ALMUTEN_NO_PREFERENCES"):
            m.delenv(name, raising=False)
        m.setenv("PYTHONPATH", str(tmp_path / "stub"))
        environment = launcher._server_environment(secret)
    if request.param == "source run":
        environment = {name: value for name, value in environment.items() if name != "PYTHONPATH"}
        command = [str(SCRIPT_PATH), "--serve", str(port)]
    else:
        command = [str(LAUNCHER_PATH), SENTINEL, str(port)]
    proc = subprocess.Popen([sys.executable, "-c", CHILD, str(record), *command],
                            cwd=tmp_path / "cwd", env=environment, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for_health(port, proc)
        yield types.SimpleNamespace(port=port, secret=secret, proc=proc, record=record, root=tmp_path)
    finally:
        _stop(proc)


def _connect(port, origin=None, host=None):
    from websockets.sync.client import connect

    headers = {"Origin": origin} if origin else {}
    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    return connect(f"ws://{host or f'127.0.0.1:{port}'}/_stcore/stream", additional_headers=headers,
                   subprotocols=["streamlit"], open_timeout=30, max_size=2 ** 27, origin=None, sock=sock)


def _run(ws, query="", until="script_finished", timeout=240):
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    back = BackMsg()
    back.rerun_script.query_string = query
    ws.send(back.SerializeToString())
    messages, deadline = [], time.time() + timeout
    while time.time() < deadline:
        forward = ForwardMsg()
        forward.ParseFromString(ws.recv(timeout=max(1, deadline - time.time())))
        messages.append(forward)
        if forward.WhichOneof("type") == until:
            return messages
    raise AssertionError(f"no {until} came")


def _alerts(messages):
    return [forward.delta.new_element.alert.body for forward in messages
            if forward.WhichOneof("type") == "delta" and forward.delta.WhichOneof("type") == "new_element"
            and forward.delta.new_element.WhichOneof("type") == "alert"]


def _raw(port, request, body=b""):
    """`request`, sent as it is to the server, then `body` unless the server
    has answered first (as a server that refuses a request before reading
    its body does): the status code, or 0 where the connection was closed
    without an answer."""
    data = b""
    with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
        s.sendall(request)
        if body:
            s.settimeout(2)
            try:
                data = s.recv(65536)
            except socket.timeout:
                s.settimeout(30)
                s.sendall(body)
        s.settimeout(30)
        while True:
            try:
                chunk = s.recv(65536)
            except (socket.timeout, ConnectionResetError):
                break
            if not chunk:
                break
            data += chunk
    if b"\r\n" not in data:
        return 0, data
    return int(data.split(b" ", 2)[1]), data


def _get(port, path, host, method="GET", extra=""):
    head = f"{method} {path} HTTP/1.1\r\n" + (f"Host: {host}\r\n" if host is not None else "")
    return _raw(port, (head + extra + "Connection: close\r\n\r\n").encode("latin-1"))


# --- What the child replaces is still what Streamlit reaches ---------------

def test_the_names_the_server_child_replaces_are_the_ones_streamlit_looks_up():
    """Each name is looked up by its module when Streamlit uses it, so the
    child's replacement is the one reached; a Streamlit that looks one up
    some other way fails here before any server is started."""
    from streamlit import config
    from streamlit.web.server import server_util
    from streamlit.web.server.starlette import starlette_app

    assert "net_util.get_external_ip" in inspect.getsource(server_util.is_url_from_allowed_origins)
    assert "create_streamlit_middleware()" in inspect.getsource(starlette_app.create_starlette_app)
    assert 'get_config_files("config.toml")' in inspect.getsource(config.get_config_options)
    # The secrets' default places are the same list's, asked again each time.
    assert '    return get_config_files("secrets.toml")\n' in inspect.getsource(config)


def test_a_streamlit_without_a_name_the_child_replaces_starts_no_server(monkeypatch):
    import server_limits
    from streamlit import net_util

    monkeypatch.delattr(net_util, "get_external_ip")
    with pytest.raises(RuntimeError, match="net_util.get_external_ip"):
        server_limits.hold_the_server(str(EXECUTABLE_DIR / "app.py"))


def test_the_window_and_a_source_run_take_the_limits_from_one_place():
    """Both servers call server_limits.hold_the_server, and neither replaces
    any of Streamlit's names itself: a second copy would drift."""
    import ast

    names = ("get_config_files", "get_external_ip", "create_streamlit_middleware", "_is_host_allowed",
             "UPLOAD_ROUTE", "upload_file")
    for path in (LAUNCHER_PATH, SCRIPT_PATH):
        text = path.read_text(encoding="utf-8")
        calls = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call)
                 and ast.unparse(node.func) == "server_limits.hold_the_server"]
        assert len(calls) == 1, path.name
        assert not [name for name in names if name in text], path.name
    assert "def hold_the_server(" in LIMITS_PATH.read_text(encoding="utf-8")


# --- The launcher's server child and a source run's, live ------------------

def test_live_a_foreign_origin_is_refused_without_asking_for_the_public_address(served):
    from websockets.exceptions import InvalidStatus

    port = served.port
    for origin in ("http://evil.example", "https://any-site.example", f"http://evil.example:{port}", "null",
                   f"http://127.0.0.1.evil.example:{port}"):
        started = time.monotonic()
        with pytest.raises(InvalidStatus) as refused:
            _connect(port, origin=origin).close()
        assert refused.value.response.status_code == 403, origin
        assert time.monotonic() - started < 0.9, f"{origin}: the refusal waited"
    records = _records(served.record)
    assert not [r for r in records if r[0] == "asked"], "the server asked an outside service for its address"
    # The one refused connection is the local-address check's datagram
    # socket, which sends nothing; no stream connection, no name looked up.
    assert not [r for r in records if r[0] == "refused" and r[1][1] != "datagram"], records
    # The window's own Origin, with the secret, is let in.
    ws = _connect(port, origin=f"http://127.0.0.1:{port}")
    try:
        messages = _run(ws, query="launch=" + served.secret)
    finally:
        ws.close()
    assert SENTENCE not in _alerts(messages) and len(messages) > 20


ROUTES = ("/", "/_stcore/health", "/_stcore/metrics", "/_stcore/host-config", "/media/0123abcd.png",
          "/_stcore/script-health-check", "/component/natal_wheel/index.html", "/static/js/none.js",
          "/_stcore/stream", "/auth/login", "/oauth2callback", "/no-such-route", "/app/static/x")


def test_live_every_http_route_answers_only_the_servers_own_host(served):
    port = served.port
    for path in ROUTES:
        for host in ("evil.example", f"evil.example:{port}", "EVIL.EXAMPLE", f"[::1]:{port}",
                     f"localhost:{port}", f"127.0.0.1.evil.example:{port}", f"evil@127.0.0.1:{port}", ""):
            status, _ = _get(port, path, host)
            assert status in (400, 403), (path, host, status)
        status, _ = _get(port, path, f"127.0.0.1:{port}")
        assert status not in (0, 400, 403), (path, status)
    # Absent, or given twice: refused.
    assert _raw(port, b"GET /_stcore/metrics HTTP/1.0\r\n\r\n")[0] in (400, 403)
    assert _get(port, "/_stcore/metrics", f"127.0.0.1:{port}", extra="Host: evil.example\r\n")[0] in (400, 403)
    # The window's own host, with or without the port, upper case or a final
    # dot (the same address, which no name lookup can move): answered.
    for host in (f"127.0.0.1:{port}", "127.0.0.1", f"127.0.0.1.:{port}"):
        assert _get(port, "/_stcore/metrics", host)[0] == 200, host


def test_live_a_session_without_the_key_cannot_leave_a_file_in_memory(served):
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    port = served.port
    ws = _connect(port)
    try:
        messages = _run(ws)
        assert _alerts(messages) == [SENTENCE]
        session = next(f.new_session.initialize.session_id for f in messages if f.WhichOneof("type") == "new_session")
        back = BackMsg()
        back.file_urls_request.request_id = "r1"
        back.file_urls_request.file_names.append("chart.json")
        back.file_urls_request.session_id = session
        ws.send(back.SerializeToString())
        deadline, urls = time.time() + 30, None
        while time.time() < deadline and urls is None:
            forward = ForwardMsg()
            forward.ParseFromString(ws.recv(timeout=30))
            if forward.WhichOneof("type") == "file_urls_response":
                urls = forward.file_urls_response
        assert urls is not None and urls.file_urls, "no upload address was handed out"
        upload = urls.file_urls[0].upload_url
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=10) as reply:
            cookie = next(c.split(";")[0] for c in reply.headers.get_all("Set-Cookie") if c.startswith("_streamlit_xsrf="))
        token = cookie.split("=", 1)[1]
        boundary = "formboundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"chart.json\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + b"x" * 262144 + \
            f"\r\n--{boundary}--\r\n".encode()
        path = re.sub(r"^https?://[^/]+", "", upload) if upload.startswith("http") else upload
        if not path.startswith("/"):
            path = "/" + path
        head = (f"PUT {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\n"
                f"Cookie: {cookie}\r\nX-Xsrftoken: {token}\r\n"
                f"Content-Type: multipart/form-data; boundary={boundary}\r\nConnection: close\r\n")
        # Sent in chunks, with no length given, an empty file whose name is
        # kept where its bytes are not: refused.
        empty = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{'n' * 4096}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n\r\n--{boundary}--\r\n").encode()
        chunked = f"{len(empty):x}\r\n".encode() + empty + b"\r\n0\r\n\r\n"
        status, _ = _raw(port, (head + "Transfer-Encoding: chunked\r\n\r\n").encode(), chunked)
        assert status == 403, f"an empty file sent in chunks was answered {status}"
        # A file of 256 KiB, its length given: refused.
        status, _ = _raw(port, (head + f"Content-Length: {len(body)}\r\n\r\n").encode(), body)
        assert status == 403, f"a file of 256 KiB was answered {status}"
    finally:
        ws.close()
    with opener.open(f"http://127.0.0.1:{port}/_stcore/metrics", timeout=10) as reply:
        metrics = reply.read().decode()
    assert 'cache_type="UploadedFileManager"' not in metrics, metrics


def test_live_no_config_file_is_read_from_the_start_folder_or_the_home(served):
    port = served.port
    ws = _connect(port)
    try:
        messages = _run(ws)
    finally:
        ws.close()
    session = next(f.new_session for f in messages if f.WhichOneof("type") == "new_session")
    seen = str(session.custom_theme) + str(session.config)
    assert "FFFFFE" not in seen.upper() and "planted" not in seen and "example.invalid" not in seen, seen
    assert not session.config.hide_sidebar_nav
    opened = sorted({r[1] for r in _records(served.record) if r[0] == "opened"})
    planted = [p for p in opened if p.startswith(str(served.root / "cwd")) or p.startswith(str(served.root / "home"))]
    assert planted == [], planted


# --- A source run ------------------------------------------------------------

def _source_child(tmp_path, record, script, port, extra_env=None, cwd=None):
    environment = _environment(tmp_path, {name: value for name, value in os.environ.items()
                                          if not name.upper().startswith("STREAMLIT_") and name != "ZIJ_LAUNCH_KEY"})
    environment.update(extra_env or {})
    return subprocess.Popen([sys.executable, "-c", CHILD, str(record), "-m", "streamlit", "run", str(script),
                             "--server.port", str(port)],
                            cwd=cwd or script.parent, env=environment, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_live_a_developers_run_cannot_be_made_to_write_into_the_apps_folder(tmp_path, port):
    """`streamlit run app.py` in a folder holding the checkout's own config,
    on a desktop (a display named), with a coding agent's folder in the
    home: an anonymous local client asks the server to install Streamlit's
    agent instructions, and is refused; nothing is written."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    folder = tmp_path / "app"
    (folder / ".streamlit").mkdir(parents=True)
    shutil.copyfile(CONFIG_PATH, folder / ".streamlit" / "config.toml")
    (folder / "app.py").write_text("import streamlit as st\nst.write('a page')\n")
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    # A developer who has run Streamlit before is not asked for an address.
    (tmp_path / "home" / ".streamlit").mkdir()
    (tmp_path / "home" / ".streamlit" / "credentials.toml").write_text('[general]\nemail = ""\n')
    # Where a browser would be opened, a stand-in that only says it was.
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "xdg-open").write_text(f"#!/bin/sh\necho \"$@\" >> {tmp_path / 'opened.txt'}\n")
    (tools / "xdg-open").chmod(0o755)
    record = tmp_path / "record.jsonl"
    proc = _source_child(tmp_path, record, folder / "app.py", port,
                         {"DISPLAY": ":no-display", "PATH": f"{tools}{os.pathsep}{Path(sys.executable).parent}",
                          "BROWSER": str(tools / "xdg-open")})
    try:
        _wait_for_health(port, proc)
        ws = _connect(port)
        try:
            messages = _run(ws)
            session = next(f.new_session.initialize.session_id for f in messages
                           if f.WhichOneof("type") == "new_session")
            back = BackMsg()
            back.backend_operation_request.request_id = "r1"
            back.backend_operation_request.session_id = session
            back.backend_operation_request.install_skills.SetInParent()
            ws.send(back.SerializeToString())
            deadline, answer = time.time() + 60, None
            while time.time() < deadline and answer is None:
                forward = ForwardMsg()
                forward.ParseFromString(ws.recv(timeout=60))
                if forward.WhichOneof("type") == "backend_operation_response":
                    answer = forward.backend_operation_response
        finally:
            ws.close()
    finally:
        _stop(proc)
    assert answer is not None and answer.error_reason == "refused:headless", answer
    assert sorted(p.name for p in folder.iterdir()) == [".streamlit", "app.py"]
    assert not (tmp_path / "opened.txt").exists(), "a browser was opened"


def test_live_a_source_run_empties_the_zone_path_before_any_import_of_the_app(tmp_path, port):
    """`streamlit run app.py`, with zoneinfo's search path pointed at a
    planted database whose UTC is Tokyo's: from the moment the app's script
    starts, every module it imports is imported with the path already
    empty, and no zone is read from the planted database, before or after."""
    planted = tmp_path / "zones"
    shutil.copytree(Path(importlib.util.find_spec("tzdata").submodule_search_locations[0]) / "zoneinfo", planted)
    shutil.copyfile(planted / "Asia" / "Tokyo", planted / "UTC")
    shutil.copyfile(planted / "Asia" / "Tokyo", planted / "Etc" / "UTC")
    record = tmp_path / "record.jsonl"
    proc = _source_child(tmp_path, record, APP_PATH, port,
                         {"PYTHONTZPATH": str(planted), "TRACE_IMPORTS": "1"},
                         cwd=EXECUTABLE_DIR)
    try:
        _wait_for_health(port, proc)
        ws = _connect(port)
        try:
            messages = _run(ws)
        finally:
            ws.close()
    finally:
        _stop(proc)
    assert len(messages) > 20
    records = _records(record)
    starts = [i for i, r in enumerate(records) if r[0] == "script"]
    assert starts, "the app's script was not seen to start"
    late = [r[1] for r in records[starts[0]:] if r[0] == "import" and r[1][1] not in (None, "(partial)", [])]
    assert late == [], f"imported with the planted path still searched: {late[:8]}"
    assert [r for r in records if r[0] == "import" and r[1][0] in ("pandas", "engine")], "the trace saw no import"
    assert [r for r in records if r[0] == "zone"] == []
    assert not [r for r in records if r[0] in ("asked", "refused") and r[1][1] != "datagram"], records
