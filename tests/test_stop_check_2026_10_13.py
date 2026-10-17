"""The stop check the desktop build runs on each download it has built.

`.github/scripts/stop_check.py` starts the packaged app from its zip with a fresh data
folder, reaches it (its server answers on its own local address and its
window is open), requires the window log the launcher makes in the data
folder only the engine gives it (a file, not a link: the download loaded its
engine), closes its window as a reader does and, on a second launch,
ends its launcher alone; each time no process of that launch may remain
once the launcher's own bound and a margin have passed. The build job runs
it on both systems, after packaging and before any upload, on both
triggers, so a failure leaves the release job (which needs the build)
nothing to draft.

Here: the workflow pins, the script's bounds against the launcher's own,
and the script's verdicts on Linux against stand-in launchers (one whose
server obeys the stop, one whose server outlives its launcher, one whose
server never answers, one that leaves its server behind after a clean exit,
one whose server opens a session under a rebound Host or from another
site's Origin, one that shows no window, one whose server is slow but within
the margin,
one that makes no window log, one with a link, a FIFO, a link to a FIFO or a
folder at the log's name) and against the real launcher run from source, its
window a stand-in; and the failure report's tail, which reads a regular file
alone and never waits.

And what a failure says of why a launch ended before it was reached: a
launcher that ends at once with lines on its standard error has them
printed, bounded and with the fresh home and the launch's key written over;
one that hands off to a successor and leaves is reported as a hand-off; on
the macOS path (run here with a recorded process table and a recorded
`open`) the bundle's standard streams are kept in the fresh folder and a
crash report written for its executable is read to its header.

And, with every attempt to end or signal a process or to run a program
recorded rather than made: the macOS parent-only stop makes one attempt
only, SIGKILL to the launcher, sent only while a fresh look still finds it
by its id and start stamp; a process whose start stamp cannot be read is
never taken below a parent link. The script is loaded for that test only
once every recorder is in place.

And the third launch, the server entry started on its own to type a place
in the city search: here it is the checkout's own launcher's, behind every
stand-in launcher that gets that far (its verdicts against the app itself
are in a test file of their own).

And, read from the script's syntax tree: its imports, and every way it has
to a process, a program, a thread, a hook or a foreign function, each at its
place, are today's; at import it binds only its constants.
"""
import ast
import importlib.util
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import types
from collections import Counter

import pytest

from conftest import EXECUTABLE_DIR
from test_sec4_build_workflow_2026_10_13 import WORKFLOW, evaluate, load_yaml

SCRIPT = EXECUTABLE_DIR / ".github" / "scripts" / "stop_check.py"
LAUNCHER = EXECUTABLE_DIR / "desktop_launcher.py"
RELEASING = EXECUTABLE_DIR / "docs" / "RELEASING.md"
FIXTURES = EXECUTABLE_DIR / "tests" / "fixtures" / "stop_check"
FAKE = FIXTURES / "fake_launcher.py"
STAND_IN_WEBVIEW = FIXTURES / "stand_in"
STAND_IN_MODULE = STAND_IN_WEBVIEW / "webview.py"

# Every proxy variable a launch is given points at a closed port of this
# computer. The app's server, asked to open a session from another site's
# Origin, looks up this computer's outside address before it refuses; with
# these, that lookup fails here at once and nothing leaves the machine.
NO_WAY_OUT = {name: "http://127.0.0.1:9" for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
NO_WAY_OUT.update(NO_PROXY="", no_proxy="")
# The stand-in window loads its page as a real window does: a session under
# the window's own address with the window address's query, held open.
LOADS_ITS_PAGE = {"STAND_IN_LOADS_THE_PAGE": "1"}


class _Watch:
    """A listener on this computer that every proxy variable a test inherits
    points at: a process the test starts without the dead proxies sends its
    requests for the outside here, not off the machine, and each is kept by
    its first line. It answers 502 and closes."""

    def __init__(self):
        self.seen = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self.address = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                try:
                    first = connection.recv(4096).split(b"\r\n", 1)[0].decode("latin-1")
                except OSError:
                    first = ""
                self.seen.append(first or "a connection that sent nothing")
                try:
                    connection.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass

    def close(self):
        """Stop listening once the connection in hand, if any, is kept."""
        self._stop.set()
        self._thread.join(10)
        self._listener.close()


@pytest.fixture(autouse=True)
def _outside(monkeypatch):
    """Every test of the stop check's files runs watched: what its processes
    would send off this computer through a proxy variable they inherit
    comes to a `_Watch` here instead, and the test fails naming it. Each
    launch is to be given NO_WAY_OUT, which leaves the watch nothing; this
    computer's own addresses are reached straight."""
    watch = _Watch()
    for name in NO_WAY_OUT:
        monkeypatch.setenv(name, "127.0.0.1,localhost" if name.lower() == "no_proxy" else watch.address)
    try:
        yield watch
    finally:
        watch.close()
    assert not watch.seen, f"sent for the outside, past the dead proxies a launch is given: {watch.seen}"


def test_a_request_for_the_outside_reaches_the_watch_and_past_the_dead_proxies_nothing(_outside, monkeypatch):
    """The watch is not vacuous: a request for an outside name, made as the
    app's server makes its lookup of this computer's outside address (with
    requests, from the environment's proxies), reaches the watch; made with
    the dead proxies a launch is given, it reaches nothing, the watch
    included."""
    import requests

    outside = "http://outside.invalid/"
    # Nothing is sent unless the environment's proxies are the watch's.
    proxies = requests.utils.get_environ_proxies(outside)
    assert [proxies.get(kind) for kind in ("http", "https", "no")] == [_outside.address, _outside.address,
                                                                      "127.0.0.1,localhost"]
    assert requests.get(outside, timeout=10).status_code == 502
    for name, value in NO_WAY_OUT.items():
        monkeypatch.setenv(name, value)
    assert requests.utils.get_environ_proxies(outside)["http"] == NO_WAY_OUT["HTTP_PROXY"]
    with pytest.raises(requests.exceptions.ProxyError):
        requests.get(outside, timeout=10)
    seen, _outside.seen[:] = list(_outside.seen), []
    assert seen == ["GET http://outside.invalid/ HTTP/1.1"]


def test_every_test_file_that_takes_these_helpers_runs_watched():
    """A test file that starts launches with the stop check's test helpers
    imports the watch with them, so that every test in it runs watched."""
    files, unwatched = [], []
    for path in sorted((EXECUTABLE_DIR / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        taken = {alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
                 and (node.module or "").startswith("test_stop_check") for alias in node.names}
        if taken:
            files.append(path.name)
            if "_outside" not in taken:
                unwatched.append(path.name)
    assert len(files) >= 4, files
    assert unwatched == [], unwatched


TRIGGERS = [
    {"github.event_name": "push", "github.ref": "refs/tags/v1.0.0"},
    {"github.event_name": "workflow_dispatch", "github.ref": "refs/heads/main"},
    {"github.event_name": "workflow_dispatch", "github.ref": "refs/tags/v1.0.0"},
]
SYSTEMS = ("Windows", "macOS")


def _module():
    spec = importlib.util.spec_from_file_location("stop_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The workflow.

def _build_steps():
    return load_yaml(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build"]["steps"]


def _is_check(step):
    return ".github/scripts/stop_check.py" in str(step.get("run", ""))


def _is_package(step):
    return str(step.get("name", "")).startswith("Package")


def _is_upload(step):
    return str(step.get("uses", "")).startswith("actions/upload-artifact@")


def _runs(step, trigger, system):
    condition = step.get("if")
    return condition is None or evaluate(condition, dict(trigger, **{"runner.os": system}))


def _order(trigger, system):
    """The kinds of the build steps that run under `trigger` on `system`,
    in order: 'check', 'package', 'upload' or None."""
    kinds = []
    for step in _build_steps():
        if _runs(step, trigger, system):
            kinds.append("check" if _is_check(step) else "package" if _is_package(step)
                         else "upload" if _is_upload(step) else None)
    return kinds


@pytest.mark.parametrize("system", SYSTEMS)
@pytest.mark.parametrize("trigger", TRIGGERS, ids=["tag push", "manual on a branch", "manual on a tag"])
def test_the_check_runs_once_on_each_system_after_packaging_and_before_every_upload(trigger, system):
    kinds = _order(trigger, system)
    assert kinds.count("check") == 1, kinds
    assert kinds.count("package") == 1, kinds
    check = kinds.index("check")
    assert kinds.index("package") < check, kinds
    uploads = [i for i, kind in enumerate(kinds) if kind == "upload"]
    assert uploads, "every trigger hands on or keeps a zip"
    assert check < min(uploads), kinds


def test_the_check_step_runs_the_script_as_published_with_a_timeout():
    [step] = [step for step in _build_steps() if _is_check(step)]
    assert "if" not in step, "the check runs on every runner and every trigger"
    assert shlex.split(step["run"]) == ["python", ".github/scripts/stop_check.py"], \
        "the runner's check uses the script's own bounds and the real desktop"
    assert step.get("continue-on-error") in (None, False)
    assert "uses" not in step and "env" not in step and "with" not in step
    minutes = int(step["timeout-minutes"])
    module = _module()
    # Two launches, each found and reached within the reach bound, its
    # server's door tried by two WebSocket openings, then stopped within its
    # bound and the margin, and (Windows) the folder's removal within the
    # margin again; a third, the server alone, reached within the reach
    # bound, its session opened (two requests), two runs each within the
    # run bound, then stopped within the orphan bound and the margin, the
    # reader of its output given its own bound, and its folder removed;
    # unpacking three times besides; and after a failure its explanation's
    # waits, for what the launcher started and for a crash report.
    worst = (3 * module.REACH_SECONDS + 6 * module.PROBE_SECONDS + 2 * module.RUN_SECONDS + module.STOP_SECONDS
             + 2 * module.ORPHAN_SECONDS + 6 * module.MARGIN_SECONDS + module.DRAIN_SECONDS
             + module.ORPHAN_SECONDS + 2 * module.MARGIN_SECONDS)
    assert worst + 120 < minutes * 60 <= 30 * 60, (worst, minutes)


def test_the_script_and_its_stand_ins_ship_with_the_workflow_that_runs_them():
    """The release tag builds on the public repository, so the script the
    build runs, and what its tests run, are published files."""
    assert SCRIPT.is_file() and FAKE.is_file() and STAND_IN_MODULE.is_file()
    assert SCRIPT.parent.relative_to(EXECUTABLE_DIR).as_posix() == ".github/scripts"


def test_the_release_still_needs_the_build_and_every_action_is_pinned_by_its_commit():
    workflow = load_yaml(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["jobs"]["release"]["needs"] == "build"
    assert workflow["jobs"]["build"]["permissions"] == {"contents": "read"}
    uses = [str(step["uses"]) for job in workflow["jobs"].values() for step in job["steps"] if "uses" in step]
    assert len(uses) >= 4
    assert [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)] == []


def test_no_leg_of_the_build_is_left_out_or_let_fail():
    """The build's matrix has no other key (no `exclude` dropping a system)
    and no failure of the build job is forgiven: each download is checked
    on its own runner, or the build fails."""
    build = load_yaml(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build"]
    assert set(build["strategy"]["matrix"]) == {"os"}
    assert "continue-on-error" not in build


# --------------------------------------------------------------------------
# The script's bounds and refusals.

def _launcher_constants():
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant):
                found[node.targets[0].id] = node.value.value
        if isinstance(node, ast.FunctionDef) and node.name == "_wait_for_server":
            found["server wait"] = node.args.defaults[-1].value
    return found


def test_the_scripts_bounds_are_the_launchers_own():
    module, launcher = _module(), _launcher_constants()
    assert module.STOP_SECONDS == launcher["STOP_WAIT_SECONDS"] + launcher["KILL_WAIT_SECONDS"]
    assert module.ORPHAN_SECONDS == launcher["ORPHAN_WAIT_SECONDS"]
    assert module.REACH_SECONDS > launcher["server wait"]
    assert module.MARGIN_SECONDS == 10.0
    args = module.parse_args([])
    assert (args.reach_seconds, args.stop_seconds, args.orphan_seconds, args.margin_seconds) == (
        module.REACH_SECONDS, module.STOP_SECONDS, module.ORPHAN_SECONDS, module.MARGIN_SECONDS)
    assert module.APP_DIR_NAME == "Zij"
    assert module.WINDOW_LOG_NAME == launcher["WINDOW_LOG_NAME"], "the log the launcher makes is the one required"


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_off_linux_the_check_takes_no_stand_in(monkeypatch, platform):
    module = _module()
    monkeypatch.setattr(module.sys, "platform", platform)
    for argv in (["--stand-in-windows", "w", "--command", "x"], ["--stand-in-windows", "w"]):
        with pytest.raises(module.CheckFailed):
            module.Check(module.parse_args(argv))


def test_on_linux_without_a_stand_in_the_check_fails_rather_than_skips():
    module = _module()
    with pytest.raises(module.CheckFailed, match="a check that skips is not a check"):
        module.Check(module.parse_args([]))
    assert module.main(["--zip", os.devnull]) == 1


# What the published text may not carry beyond what the release's own scans
# refuse in every published file: a ruling or lane, a finding's or lane's
# identifier, a date, a folder of a person's own.
_PRIVATE = re.compile(r"\bruling|\blane\b|\b20\d\d-\d\d-\d\d\b|\bSTOP\d|\bSEC\d|\bLS-\d|"
                      r"[\\/]Users[\\/]|~/", re.IGNORECASE)


def test_the_published_text_names_nothing_private():
    texts = {"script": SCRIPT.read_text(encoding="utf-8"),
             "fixtures": "".join(p.read_text(encoding="utf-8") for p in sorted(FIXTURES.rglob("*.py")))}
    steps = [s for s in _build_steps() if _is_check(s)]
    assert steps
    workflow = WORKFLOW.read_text(encoding="utf-8")
    block = workflow[workflow.index("# Each download, as built"):workflow.index("run: python .github/scripts/stop_check.py")]
    texts["workflow"] = block
    doc = RELEASING.read_text(encoding="utf-8")
    texts["doc"] = doc[doc.index("Before either zip is handed on"):doc.index("A build started by hand")]
    found = {name: _PRIVATE.findall(text) for name, text in texts.items()}
    assert found == {name: [] for name in texts}


# --------------------------------------------------------------------------
# The script's verdicts on Linux.

def _download(tmp_path, name="download"):
    """A folder holding a copy of this interpreter named as the app is, so
    that the processes of a launch run an executable inside it."""
    folder = tmp_path / name
    folder.mkdir()
    exe = folder / "Zij"
    shutil.copy2(os.path.realpath(sys.executable), exe)
    return folder, exe


def _check(tmp_path, command, folder=None, bounds=("5", "1", "1", "2"), extra_env=None, timeout=120, run=None):
    windows = tmp_path / "windows"
    windows.mkdir(exist_ok=True)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.pop("ZIJ_LAUNCH_KEY", None)
    env["FAKE_SERVER_PYTHON"] = sys.executable
    env.update(NO_WAY_OUT, **LOADS_ITS_PAGE)
    env.update(extra_env or {})
    reach, stop, orphan, margin = bounds
    argv = [sys.executable, str(SCRIPT), "--work", str(work), "--reach-seconds", reach, "--stop-seconds", stop,
            "--orphan-seconds", orphan, "--margin-seconds", margin, "--stand-in-windows", str(windows)]
    if folder is not None:
        argv += ["--folder", str(folder)]
    if run is not None:
        argv += ["--run-seconds", run]
    done = subprocess.run(argv + ["--command", *map(str, command)], capture_output=True, text=True,
                          env=env, timeout=timeout)
    assert done.stderr == "", done.stderr
    assert str(work) not in done.stdout and str(tmp_path) not in done.stdout
    assert os.listdir(work) == [], "the check leaves nothing in its working folder"
    return done.returncode, done.stdout


def _running_from(folder):
    """Processes whose executable lies inside `folder`."""
    found = []
    for name in os.listdir("/proc"):
        try:
            exe = os.readlink(f"/proc/{name}/exe")
        except OSError:
            continue
        if name.isdigit() and exe.startswith(str(folder) + os.sep):
            found.append(int(name))
    return found


def _fake(tmp_path, mode, **kwargs):
    folder, exe = _download(tmp_path)
    code, out = _check(tmp_path, [exe, FAKE, mode], folder=folder, **kwargs)
    assert _running_from(folder) == [], "the check left a process of its launch running"
    return code, out


# Bounds for a stand-in launch that passes the two stops: the third launch
# then runs the checkout's real server, which is given time to start and to
# stop on a loaded machine (reach 30 s; its stop is the orphan bound, 10 s,
# and the margin). The first two launches keep their tight stop bound.
_PASSING = ("30", "1", "10", "2")


def _failure(output):
    lines = [line for line in output.splitlines() if line.startswith("stop check FAILED: ")]
    assert len(lines) == 1, output
    return lines[0]


def test_a_launcher_whose_server_obeys_the_stop_passes(tmp_path):
    code, out = _fake(tmp_path, "obeys", bounds=_PASSING)
    assert code == 0, out
    lines = out.splitlines()
    assert [line.split(":", 1)[0] for line in lines] == (["launch 1"] * 6 + ["launch 2"] * 6 + ["launch 3"] * 8
                                                         + ["stop check passed"])
    assert [line for line in lines if "the window's own session ran the app" in line] == [
        f"launch {n}: the window's own session ran the app: the server holds 1314176 byte(s) of files the app's "
        f"page hands its window, which only a session it lets in is given, and 1 result(s) of the engine's "
        f"(calculate_prenatal_syzygy); this check opened no session that ran the app" for n in (1, 2)], out
    assert [line for line in lines if "WebSocket" in line] == [
        f"launch {n}: a WebSocket opening under a rebound Host was refused (403), one under the window's own "
        f"address from another site's Origin was refused (403), and one under the window's own address opened "
        f"(101)" for n in (1, 2, 3)], out
    # Tried once the server answers: next after the line that says so.
    assert lines[1].startswith("launch 1: reached after ") and "WebSocket" in lines[2], out
    found = [line for line in lines if "window log" in line]
    assert found == [f"launch {n}: window log found in the app's data folder: the download loaded its engine"
                     for n in (1, 2)], out
    assert "a line the fake launcher's window log holds" not in out, "the log's contents are never printed"
    assert "launch 1: closed by the stand-in window's close; after " in out
    assert "launch 2: ended the launcher Zij (" in out and "alone by SIGKILL; its server Zij (" in out
    assert out.count("no process of this launch remains (2 seen") == 2
    assert "the server answered on 127.0.0.1:" in out and "the launcher's child" in out
    # The third launch: the command's own server entry (here the real one),
    # a place typed in its city search and found, the server stopped.
    third = [line for line in lines if line.startswith("launch 3: ")]
    assert third[0].startswith("launch 3: started: the command's server entry run with a fresh home"), out
    assert "offered 'Évora, 08 (PT)' among its 3 option(s)" in third[4], out
    assert third[5].startswith("launch 3: the example chart's wheel puts Jupiter at 20.87632"), out
    assert "were each told only 'This app can be used only in the window" in third[6], out
    assert third[7].startswith("launch 3: stopped as the launcher stops it, by the end of its input; after "), out
    assert "no process of this launch remains (1 seen" in third[7] and "server exit 0" in third[7], out


def test_a_server_that_outlives_its_launcher_fails(tmp_path):
    code, out = _fake(tmp_path, "survives")
    assert code == 1
    failure = _failure(out)
    assert failure.startswith("stop check FAILED: launch 2: 1 s + 2 s after the launcher alone was ended, "
                              "still running: Zij ("), failure
    assert "launch 1: closed by" in out          # the ordinary stop held


def test_a_server_that_opens_a_session_under_a_rebound_host_fails(tmp_path):
    """The door the app's server keeps, and the one way a page whose own
    name points at this computer could reach a session: a server that opens
    a WebSocket under the rebound Host fails the first launch, once reached,
    before its window is closed."""
    code, out = _fake(tmp_path, "rebinds")
    assert code == 1
    failure = _failure(out)
    assert re.fullmatch(r"stop check FAILED: launch 1: a WebSocket opening under the rebound Host "
                        r"evil\.example:\d+ was answered 101, not refused with 403: a page whose own name points "
                        r"at this computer could open a session", failure), failure
    assert "launch 1: reached after " in out and "closed by" not in out


def test_a_server_that_opens_a_session_from_another_sites_origin_fails(tmp_path):
    """A server that opens a WebSocket under its own Host whatever Origin
    sends it, which is how a page of another site would reach a session,
    fails the first launch, once reached, before its window is closed."""
    code, out = _fake(tmp_path, "any-origin")
    assert code == 1
    failure = _failure(out)
    assert re.fullmatch(r"stop check FAILED: launch 1: a WebSocket opening under the window's own address from "
                        r"the Origin http://evil\.example was answered 101, not refused with 403: a page of another "
                        r"site could open a session", failure), failure
    assert "launch 1: reached after " in out and "closed by" not in out


def test_a_window_whose_session_the_server_never_lets_in_fails(tmp_path):
    """The window opens and its server answers, but its metrics never show a
    file the app's page hands its window, as when the window shows the
    refusal (a refused session's own state is there): the first
    launch fails once the bound for a run has passed, before its window is
    closed."""
    code, out = _check(tmp_path, [_download(tmp_path)[1], FAKE, "refused-window"], run="3")
    assert code == 1
    assert re.fullmatch(r"stop check FAILED: launch 1: the window's own session never ran the app within 3 s: the "
                        r"server holds no file the app's page hands its window, which a session it lets in is given "
                        r"on its first run \(1 session\(s\) open, \? opened in all\): the window shows the refusal, "
                        r"or never loaded the page", _failure(out)), out
    assert "launch 1: window log found" in out and "closed by" not in out


def test_a_server_that_refuses_its_own_windows_session_fails(tmp_path):
    """The probe under the window's own address must open: a server that
    refuses every Host (the probe's request itself, say, refused) does not
    pass for one that refuses the rebound one."""
    code, out = _fake(tmp_path, "shut")
    assert code == 1
    assert re.fullmatch(r"stop check FAILED: launch 1: a WebSocket opening under the window's own address "
                        r"127\.0\.0\.1:\d+ was answered 403, not opened with 101", _failure(out)), out


def test_a_server_that_gives_the_opening_no_status_is_not_taken_for_a_refusal(tmp_path, monkeypatch):
    """The opening's answer is read from its status line alone: a server
    that closes the connection, or answers what is not a status line, gives
    None, which the check refuses as it refuses an admission."""
    import socket
    import threading

    module = _module()
    answers = [b"", b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n", b"no status here\r\n",
               b"HTTP/1.1 101 Switching Protocols\r\n\r\n", b"HTTP/1.1 403 Forbidden\r\n\r\n"]
    seen = []
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        port = server.getsockname()[1]

        def serve():
            for answer in answers:
                connection, _ = server.accept()
                with connection:
                    seen.append(connection.recv(4096))
                    connection.sendall(answer)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        got = [module._opening_status(port, f"{module.REBOUND_HOST}:{port}") for _ in answers[:-1]]
        got.append(module._opening_status(port, f"127.0.0.1:{port}", module.FOREIGN_ORIGIN))
        thread.join(10)
    assert got == [None, 403, None, 101, 403]
    request = seen[0].decode("ascii")
    assert request.startswith("GET /_stcore/stream HTTP/1.1\r\nHost: evil.example:%d\r\n" % port), request
    assert "\r\nUpgrade: websocket\r\n" in request and "\r\nSec-WebSocket-Version: 13\r\n" in request
    assert "Origin" not in request, "the rebound Host alone is what is refused"
    foreign = seen[-1].decode("ascii")
    assert foreign.startswith("GET /_stcore/stream HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: http://evil.example\r\n"
                              % port), foreign


def test_a_server_that_never_answers_fails(tmp_path):
    code, out = _fake(tmp_path, "deaf")
    assert code == 1
    assert "launch 1: the server did not answer on its own local address within 5 s" in _failure(out)
    assert "reached" not in out


def test_a_launcher_that_exits_cleanly_leaving_its_server_fails(tmp_path):
    code, out = _fake(tmp_path, "leaves")
    assert code == 1
    failure = _failure(out)
    assert "launch 1: 1 s + 2 s after the window was closed, still running: Zij (" in failure
    assert "still answers" in failure


def test_a_window_that_never_opens_fails(tmp_path):
    code, out = _fake(tmp_path, "no-window")
    assert code == 1
    failure = _failure(out)
    assert "no window opened within 5 s" in failure and "a check that skips is not a check" in failure


_LINK = " (a link stands at its name)"
_UNREAD = "the window log could not be read: only a regular file, not a link, is read"


@pytest.mark.parametrize("mode, held, unread", [("no-log", "", False), ("log-link", _LINK, True),
                                                ("log-fifo", "", True), ("log-link-to-fifo", _LINK, True),
                                                ("log-folder", "", True)])
def test_a_launcher_that_makes_no_window_log_fails_by_name(tmp_path, mode, held, unread):
    """Reached -- the server answers, the window is open, the data folder
    is made -- but no window log, or a link, a FIFO or a folder at its name:
    the download was not shown to load its engine, and the check fails
    saying so, within the test's time and with no process left. What it
    then says of why reads only a regular file at that name: of a link it
    prints not its target's lines, and on a FIFO it does not wait, but says
    in one line that the log could not be read."""
    code, out = _fake(tmp_path, mode, timeout=60)
    assert code == 1
    assert "launch 1: reached after " in out and "window log found" not in out
    assert _failure(out) == (f"stop check FAILED: launch 1: the launcher made no window log in the app's data "
                             f"folder{held}, so the download could not be shown to load its engine"), out
    assert out.count(_UNREAD) == (1 if unread else 0), out
    assert "a file the link names" not in out and "the window log, last" not in out, out
    if unread:
        lines = [line.strip() for line in out.splitlines()]
        assert lines.index(_failure(out)) < lines.index(_UNREAD), "the sentence, then what is seen of why"
    else:
        assert "the window log" not in out, out


@pytest.mark.parametrize("kind", ["link", "fifo", "link-to-fifo", "folder"])
def test_the_failure_reports_tail_reads_a_regular_file_alone_and_never_waits(tmp_path, monkeypatch, kind):
    """`_tail`, run here with every attempt to end or signal a process or run
    a program recorded, never made: a link at the log's name is not followed,
    a FIFO there (or a link to one) is not waited on, a folder is not read;
    each gives None at once. A regular file is still read."""
    import threading

    attempts = []
    _record_every_attempt(monkeypatch, attempts)
    monkeypatch.setattr(os, "kill", lambda *args: attempts.append(("os.kill", *args)))
    module = _module()
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "elsewhere.log").write_text("a file the link names\n")
    log = folder / "webview_debug.log"
    fifo = folder / ("elsewhere.fifo" if kind == "link-to-fifo" else "webview_debug.log")
    if kind in ("fifo", "link-to-fifo"):
        os.mkfifo(fifo)
    if kind == "link":
        log.symlink_to("elsewhere.log")
    elif kind == "link-to-fifo":
        log.symlink_to("elsewhere.fifo")
    elif kind == "folder":
        log.mkdir()
    said = []
    reader = threading.Thread(target=lambda: said.append(module._tail(str(log))), daemon=True)
    reader.start()
    reader.join(10)
    waited = reader.is_alive()
    if waited:                                      # let the reader go: a writer opens the FIFO and leaves
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        reader.join(10)
    assert not waited, "the tail waited on what stands at the log's name"
    assert said == [None], said
    assert module._tail(str(folder / "elsewhere.log")) == ["a file the link names"]
    assert not attempts, attempts


def test_a_stop_slower_than_the_bound_but_within_the_margin_passes_and_beyond_it_fails(tmp_path):
    # The server ends 2 s after its launcher asks: past the 1 s bound, inside
    # its 3 s margin.
    (tmp_path / "within").mkdir()
    (tmp_path / "beyond").mkdir()
    code, out = _fake(tmp_path / "within", "obeys", bounds=("30", "1", "10", "3"), extra_env={"FAKE_STOP_DELAY": "2"})
    assert code == 0, out
    code, out = _fake(tmp_path / "beyond", "obeys", bounds=("5", "1", "1", "0.5"), extra_env={"FAKE_STOP_DELAY": "2"})
    assert code == 1
    assert "launch 1: 1 s + 0.5 s after the window was closed, still running" in _failure(out)


def _sleeper(exe):
    return subprocess.Popen([str(exe), "-c", "import time; time.sleep(120)"])


def test_a_process_of_the_same_name_outside_the_launch_is_not_counted(tmp_path):
    _, decoy_exe = _download(tmp_path, "elsewhere")
    decoy = _sleeper(decoy_exe)
    try:
        code, out = _fake(tmp_path, "obeys", bounds=_PASSING)
        assert decoy.poll() is None, "the decoy ran throughout"
    finally:
        decoy.kill()
        decoy.wait()
    assert code == 0, out
    assert f"({decoy.pid})" not in out


def test_a_process_running_from_the_download_but_outside_the_tree_is_counted_and_not_ended(tmp_path):
    """Counted, since it runs the download's executable; but it is not in
    the launch's tree (no parent link leads to it from the launcher the
    check started), so the check's clean-up after the failure spares it:
    the clean-up ends nothing outside that tree, whatever is counted."""
    folder, exe = _download(tmp_path)
    stray = _sleeper(exe)
    try:
        code, out = _check(tmp_path, [exe, FAKE, "obeys"], folder=folder)
        assert stray.poll() is None, "the check ended a process older than its launch"
    finally:
        stray.kill()
        stray.wait()
    assert code == 1
    assert f"launch 1: 1 s + 2 s after the window was closed, still running: Zij ({stray.pid})" in _failure(out)


def test_the_real_launcher_from_source_passes_with_its_own_bounds(tmp_path):
    # The launcher's own short temporary folder: the engine refuses one whose
    # name is long, and pytest's base folder may be.
    short = tempfile.mkdtemp(dir="/tmp")
    try:
        code, out = _check(tmp_path, [sys.executable, LAUNCHER], bounds=("120", "15", "10", "10"),
                           extra_env={"PYTHONPATH": str(STAND_IN_WEBVIEW), "TMPDIR": short}, timeout=400)
    finally:
        shutil.rmtree(short, ignore_errors=True)
    assert code == 0, out
    assert out.count("window log found in the app's data folder: the download loaded its engine") == 2, out
    # The app's own server refuses a rebound Host and another site's Origin,
    # and opens its window's: in each of the three launches.
    assert out.count("a WebSocket opening under a rebound Host was refused (403), one under the window's own "
                     "address from another site's Origin was refused (403), and one under the window's own "
                     "address opened (101)") == 3, out
    assert "(bound 15 s + 10 s margin); launcher exit 0" in out
    assert "(bound 10 s + 10 s margin)" in out
    assert out.count("no process of this launch remains (2 seen") == 2


# --------------------------------------------------------------------------
# The check ends nothing but the tree below the launcher it started.

def _check_with_intruders(tmp_path, command, folder, after_launch, bounds=("5", "1", "1", "2")):
    """The check run as `_check` runs it; once launch `after_launch` has
    begun (its launcher has made its data folder), this test starts two
    processes the launch did not: one running the download's own executable
    (so the check counts it against the stop) and one running this
    interpreter. Both are the test's children, never the launch's. Returns
    the check's exit status and output, and whether each intruder outlived
    the check."""
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.pop("ZIJ_LAUNCH_KEY", None)
    env["FAKE_SERVER_PYTHON"] = sys.executable
    env.update(NO_WAY_OUT, **LOADS_ITS_PAGE)
    if command[0] == sys.executable:
        env["PYTHONPATH"] = str(STAND_IN_WEBVIEW)
    reach, stop, orphan, margin = bounds
    argv = [sys.executable, str(SCRIPT), "--work", str(work), "--reach-seconds", reach, "--stop-seconds", stop,
            "--orphan-seconds", orphan, "--margin-seconds", margin, "--stand-in-windows", str(windows)]
    if folder is not None:
        argv += ["--folder", str(folder)]
    short, check, intruders = None, None, []
    try:
        # A short temporary folder of the launch's own (the engine refuses a
        # long one), made inside the `try` so that it is removed even when
        # the check cannot be started.
        short = tempfile.mkdtemp(dir="/tmp")
        env["TMPDIR"] = short
        check = subprocess.Popen(argv + ["--command", *map(str, command)], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=env)
        begun = None
        for _ in range(2400):
            begun = next(iter(work.glob(f"stop-check-*/data-{after_launch}/Zij")), None)
            if begun is not None or check.poll() is not None:
                break
            try:
                check.wait(0.05)
            except subprocess.TimeoutExpired:
                pass
        assert begun is not None, "launch %d never began" % after_launch
        own = [folder / "Zij"] if folder is not None else []
        intruders = [_sleeper(exe) for exe in own + [os.path.realpath(sys.executable)]]
        out, err = check.communicate(timeout=400)
        outlived = [intruder.poll() is None for intruder in intruders]
    finally:
        if check is not None and check.poll() is None:
            check.kill()
            check.wait()
        for intruder in intruders:
            intruder.kill()
            intruder.wait()
        if short is not None:
            shutil.rmtree(short, ignore_errors=True)
    assert err == "", err
    assert len(outlived) == len(own) + 1
    return check.returncode, out, outlived


VERDICTS = [
    # (mode, the launch during which the intruders start, the check's verdict)
    ("obeys", 1, 1),         # the intruder running the download's executable fails the ordinary stop
    ("obeys", 2, 1),         # ... or the parent-only one
    ("survives", 2, 1),
    ("deaf", 1, 1),
    ("leaves", 1, 1),
    ("no-window", 1, 1),
]


@pytest.mark.parametrize("mode, launch, verdict", VERDICTS,
                         ids=[f"{mode}-launch{launch}" for mode, launch, _ in VERDICTS])
def test_a_process_started_after_the_launch_by_another_parent_outlives_the_checks_clean_up(
        tmp_path, mode, launch, verdict):
    folder, exe = _download(tmp_path)
    code, out, outlived = _check_with_intruders(tmp_path, [exe, FAKE, mode], folder, launch)
    assert code == verdict, out
    assert outlived == [True, True], out
    assert _running_from(folder) == [], "the launch's own processes were ended"


def test_on_a_passing_verdict_a_process_started_after_the_launch_outlives_the_check(tmp_path):
    _, exe = _download(tmp_path)
    code, out, outlived = _check_with_intruders(tmp_path, [exe, FAKE, "obeys"], None, 1, bounds=_PASSING)
    assert code == 0, out
    assert outlived == [True], out


def test_with_the_real_launcher_a_process_started_after_the_launch_outlives_the_check(tmp_path):
    code, out, outlived = _check_with_intruders(tmp_path, [sys.executable, LAUNCHER], None, 2,
                                                bounds=("120", "15", "10", "10"))
    assert code == 0, out
    assert outlived == [True], out


def test_the_intruders_short_folder_is_removed_even_when_the_check_cannot_start(tmp_path, monkeypatch):
    """The helper's own temporary folder does not outlive a check that could
    not be started (nothing is started here: `Popen` raises)."""
    made, mkdtemp = [], tempfile.mkdtemp

    def _mkdtemp(*args, **kwargs):
        made.append(mkdtemp(dir=tmp_path))
        return made[-1]

    def _popen(*args, **kwargs):
        raise OSError(24, "Too many open files")

    monkeypatch.setattr(tempfile, "mkdtemp", _mkdtemp)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    with pytest.raises(OSError, match="Too many open files"):
        _check_with_intruders(tmp_path, [sys.executable, LAUNCHER], None, 1)
    assert len(made) == 1 and not os.path.exists(made[0]), "the short folder was left behind"


# --------------------------------------------------------------------------
# What a failure says of why a launch ended before it was reached.

def _details(output):
    """The lines that follow the failure: what the outside could see."""
    lines = output.splitlines()
    at = [i for i, line in enumerate(lines) if line.startswith("stop check FAILED: ")]
    assert len(at) == 1, output
    return lines[at[0] + 1:]


def test_a_launcher_that_ends_at_once_says_what_it_wrote_scrubbed_and_bounded(tmp_path):
    folder, exe = _download(tmp_path)
    code, out = _check(tmp_path, [exe, FAKE, "ends"], folder=folder)
    assert code == 1
    failure = _failure(out)
    assert ("launch 1: the launcher ended at once (exit 3)" in failure
            or "launch 1: the launcher ended (exit 3) " in failure), failure
    details = _details(out)
    assert details and all(line.startswith("  ") for line in details), details
    text = "\n".join(details)
    assert "the launcher's exit status: 3" in text
    assert "the app's data folder in the fresh folder: not made" in text
    assert "a hand-off" not in text
    # Its standard error: the last forty lines, each bounded, the fresh home
    # written over, the launch key withheld, no terminal code.
    assert "the launcher's standard error, last 40 line(s):" in text
    assert "line 22: the home folder <fresh>" in text and "line 21:" not in text
    assert "line 59: the home folder <fresh>" in text
    assert "?launch=<withheld> failed" in text and "Fake-Launch-Key" not in text
    assert "\x1b" not in out and "[31m" not in out
    assert "  | " + "x" * 300 + "\n" in out + "\n" and "x" * 301 not in out
    assert "the launcher's standard output, last 1 line(s):\n    | the standard output's one line" in out
    assert _running_from(folder) == []


def test_a_launcher_that_hands_off_and_leaves_is_reported_as_a_hand_off(tmp_path):
    folder, exe = _download(tmp_path)
    code, out = _check(tmp_path, [exe, FAKE, "hands-off"], folder=folder)
    assert code == 1
    assert "launch 1: the launcher ended (exit 0) " in _failure(out), out
    text = "\n".join(_details(out))
    launcher = re.search(r"Zij \((\d+)\) \[the launcher; ", text)
    assert launcher, text
    pid = launcher.group(1)
    assert re.search(r"  a hand-off: the launcher started Zij \(\d+\) and ended by [\d.]+ s after the start; "
                     r"[\d.]+ s after its end that still runs", text), text
    assert f"parent {pid}, the launcher; seen from" in text
    assert "the app's data folder in the fresh folder: made" in text
    assert "the launcher's standard error: empty" in text
    # The successor is the launcher's own child, so the tree's clean-up
    # ended it: nothing of the launch is left.
    assert _running_from(folder) == []


def test_a_launcher_whose_server_ends_soon_after_it_did_not_hand_off(tmp_path):
    """A launcher that ends abruptly before it is reached leaves its server
    for a moment, until the server sees the end of its input: that server
    ending within the wait is an end, not a hand-off."""
    folder, exe = _download(tmp_path)
    code, out = _check(tmp_path, [exe, FAKE, "crashes"], folder=folder, extra_env={"FAKE_STOP_DELAY": "1"})
    assert code == 1
    assert "launch 1: the launcher ended (exit 9) " in _failure(out), out
    text = "\n".join(_details(out))
    assert re.search(r"  the launcher ended by [\d.]+ s after the start, and nothing it started was still "
                     r"running [\d.]+ s after its end: it ended, it did not hand off", text), text
    assert "a hand-off" not in text
    pid = re.search(r"Zij \((\d+)\) \[the launcher; ", text).group(1)
    assert re.search(rf"Zij \(\d+\) \[parent {pid}, the launcher; seen from [\d.]+ s, gone by [\d.]+ s\]", text), text
    assert "the app's data folder in the fresh folder: made" in text
    assert _running_from(folder) == []


def test_a_launcher_that_ends_leaving_nothing_is_not_called_a_hand_off(tmp_path):
    """The launcher of a reached launch ended alone (the parent-only stop's
    fake that leaves its server) is no hand-off either way: the analysis is
    for a launch that ended before it was reached."""
    code, out = _fake(tmp_path, "leaves")
    assert code == 1
    text = "\n".join(_details(out))
    assert "a hand-off" not in text and "did not hand off" not in text
    assert "processes of this launch seen (parent at first sight; seconds after the start): " in text


class _Recorder:
    """A process table for the macOS path's unit tests: what `snapshot`
    returns is set by the test; `kill` only records."""

    def __init__(self, module):
        self.module, self.table, self.killed = module, {}, []

    def snapshot(self):
        return dict(self.table)

    def listening(self, pids):
        return {}

    def kill(self, proc):
        self.killed.append(proc.pid)


def _mac_check(module, tmp_path, monkeypatch):
    """A check on the macOS path with no Mac: the process table a recorder,
    unpacking and `open` recorded rather than run."""
    zipped = tmp_path / "Zij-macos.zip"
    zipped.write_bytes(b"")
    check = module.Check.__new__(module.Check)
    check.args = module.parse_args(["--zip", str(zipped), "--orphan-seconds", "0.5", "--margin-seconds", "0.5"])
    check.platform, check.desktop, check.current = "darwin", None, None
    check.processes = _Recorder(module)
    check.work = str(tmp_path / "work")
    os.makedirs(check.work)
    ran = []

    def _run(argv, what):
        ran.append(list(argv))
        if argv[0] == "/usr/bin/open":
            exe = os.path.join(argv[-1], "Contents", "MacOS", "Zij")
            check.processes.table = {700: module.Proc(700, 1, exe, 1.0)}

    monkeypatch.setattr(module, "_run", _run)
    return check, ran


def test_on_macos_the_bundle_is_opened_with_its_streams_kept_in_the_fresh_folder(tmp_path, monkeypatch):
    module = _module()
    check, ran = _mac_check(module, tmp_path, monkeypatch)
    launch, made = check.start(1)
    data = os.path.join(check.work, "data-1")
    bundle = os.path.join(check.work, "download-1", "Zij.app")
    assert ran[-1] == ["/usr/bin/open", "-n", "--stdout", os.path.join(data, "launcher-stdout.txt"),
                       "--stderr", os.path.join(data, "launcher-stderr.txt"), "--env", f"HOME={data}", bundle]
    assert made == os.path.join(data, "Library", "Application Support", "Zij")
    assert launch.launcher.pid == 700 and launch.popen is None
    assert check.processes.killed == []


def _ips(path, proc_path, mtime=None):
    header = {"app_name": "Zij", "bug_type": "309", "name": "Zij"}
    body = {"pid": 700, "parentPid": 1, "parentProc": "launchd", "procPath": proc_path,
            "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"},
            "termination": {"namespace": "DYLD", "indicator": "Library missing", "code": 1,
                            "details": ["Library not loaded: @rpath/libsomething.dylib"]},
            "asi": {"dyld": ["missing symbol called"]}}
    import json
    path.write_text(json.dumps(header) + "\n" + json.dumps(body, indent=2), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.mark.parametrize("successor", [False, True], ids=["ended", "handed off"])
def test_on_macos_an_early_end_says_its_streams_crash_report_and_processes(tmp_path, monkeypatch, successor):
    module = _module()
    home = tmp_path / "home"
    reports = home / "Library" / "Logs" / "DiagnosticReports"
    reports.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    check, _ = _mac_check(module, tmp_path, monkeypatch)
    launch, _ = check.start(1)
    exe = launch.launcher.exe
    data = os.path.join(check.work, "data-1")
    # The app writes, and starts a child; then the launcher is gone.
    with open(os.path.join(data, "launcher-stderr.txt"), "w") as f:
        f.write(f"Traceback (most recent call last):\n  File \"{data}/x.py\"\nRuntimeError: no server\n")
    os.makedirs(os.path.join(data, "Library", "Application Support", "Zij"))
    with open(os.path.join(data, "Library", "Application Support", "Zij", "webview_debug.log"), "w") as f:
        f.write("2031-01-02 03:04:05,678 pywebview ERROR: the window could not be made\n")
    check.processes.table[701] = module.Proc(701, 700, exe, 2.0)
    launch.live()
    del check.processes.table[700]
    if not successor:
        del check.processes.table[701]
    _ips(reports / "Zij-crash.ips", exe)
    _ips(reports / "Other-crash.ips", "/Applications/Other.app/Contents/MacOS/Other")
    _ips(reports / "Zij-old.ips", exe, mtime=launch.wall_started - 3600)
    (reports / "Zij-text.crash").write_text(f"Process: Zij [702]\nPath: {exe}\nIdentifier: zij\n"
                                            "Exception Type: EXC_BAD_ACCESS (SIGKILL (Code Signature Invalid))\n"
                                            "Termination Reason: Namespace CODESIGNING, Code 2\nThread 0:\n")
    lines = [module.scrub(line) for line in check.explain(launch)]
    text = "\n".join(lines)
    if successor:
        assert re.search(r"^a hand-off: the launcher started Zij\.app/Contents/MacOS/Zij \(701\) and ended", text,
                         re.M), text
    else:
        assert "and nothing it started was still running" in text and "it did not hand off" in text
    assert ("Zij.app/Contents/MacOS/Zij (700) [the launcher; parent 1, outside this launch; seen from" in text)
    assert "Zij.app/Contents/MacOS/Zij (701) [parent 700, the launcher; seen from" in text
    assert "the app's data folder in the fresh folder: made" in text
    assert "the window log, last 1 line(s):\n  | pywebview ERROR: the window could not be made" in text
    assert "2031" not in text
    assert "the launcher's standard error, last 3 line(s):\n  | Traceback" in text
    assert '  |   File "<fresh>/x.py"' in text and "  | RuntimeError: no server" in text
    assert "the launcher's standard output: empty" in text
    assert text.count("a crash report for the bundle's executable:") == 2, text
    assert "  | exception: type EXC_CRASH, signal SIGABRT" in text
    assert ("  | termination: namespace DYLD, indicator Library missing, code 1, details "
            "['Library not loaded: @rpath/libsomething.dylib']") in text
    assert "  | application note: dyld: missing symbol called" in text
    assert "  | process Zij.app/Contents/MacOS/Zij (700), parent 1 (launchd)" in text
    assert "  | Exception Type: EXC_BAD_ACCESS (SIGKILL (Code Signature Invalid))" in text
    assert "Other" not in text and str(tmp_path) not in text and "Zij-crash" not in text
    assert check.processes.killed == []
    launch.end_everything()
    assert check.processes.killed == [], "nothing on macOS is ended by the check"


def test_what_a_failure_prints_has_the_launch_key_and_a_forge_token_withheld():
    module = _module()
    assert module.scrub("GET /?launch=abc-DEF_123&x=1 ZIJ_LAUNCH_KEY=s3cr3t") == \
        "GET /?launch=<withheld>&x=1 ZIJ_LAUNCH_KEY=<withheld>"
    assert module.scrub("token ghs_" + "A" * 36 + " end") == "token <withheld> end"
    assert module.scrub("relaunch=1") == "relaunch=1"


@pytest.mark.parametrize("form, scrubbed", [
    ("ZIJ_LAUNCH_KEY=s3cr3t", "ZIJ_LAUNCH_KEY=<withheld>"),
    ("{'ZIJ_LAUNCH_KEY': 's3cr3t', 'HOME': '/x'}", "{'ZIJ_LAUNCH_KEY': '<withheld>', 'HOME': '/x'}"),
    ('{"ZIJ_LAUNCH_KEY": "s3cr3t", "HOME": "/x"}', '{"ZIJ_LAUNCH_KEY": "<withheld>", "HOME": "/x"}'),
], ids=["bare", "repr", "json"])
def test_the_launch_key_is_withheld_in_its_bare_repr_and_json_forms(form, scrubbed):
    module = _module()
    assert module.scrub(form) == scrubbed
    assert "s3cr3t" not in module.scrub(form)


# --------------------------------------------------------------------------
# Which processes are signalled: every attempt to end or signal a process, or
# to run a program, recorded in the order made, and never made.

# The calls by which Python ends or signals a process, or runs a program,
# each recorded in `os` and in `posix` (the module whose functions `os`
# hands out under the same names).
_ENDING = ("kill", "killpg")
_RUNNING = ("system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp", "execv", "execve", "execl",
            "execle", "execlp", "execlpe", "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe",
            "spawnv", "spawnve", "spawnvp", "spawnvpe")


class _NotRun:
    """What a recorded `subprocess.Popen` hands back: a program that was
    never started and reports a clean exit."""

    pid, returncode, stdout, stderr, stdin, args = None, 0, None, None, None, None

    def __init__(self, attempts):
        self._attempts = attempts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def communicate(self, input=None, timeout=None):
        return "", ""

    def kill(self):
        self._attempts.append(("Popen.kill",))

    def terminate(self):
        self._attempts.append(("Popen.terminate",))

    def send_signal(self, number):
        self._attempts.append(("Popen.send_signal", number))


class _Foreign:
    """Whatever is reached through ctypes, recorded: loading a library and
    each function called on it is an attempt, never made (the script reaches
    `kill`, `TerminateProcess` and Quit through ctypes)."""

    def __init__(self, attempts, path):
        self._attempts, self._path = attempts, path

    def __getattr__(self, symbol):
        if symbol.startswith("__"):
            raise AttributeError(symbol)
        return _Foreign(self._attempts, f"{self._path}.{symbol}")

    def __call__(self, *args, **kwargs):
        self._attempts.append(("ctypes", self._path, *args))
        return _Foreign(self._attempts, f"{self._path}()")


def _record_every_attempt(monkeypatch, attempts):
    """For one test, before the script is loaded: every call by which the
    script could end or signal a process or run a program appends to
    `attempts` and returns, never made. `os.kill` is left to the caller,
    which models what reaches the kernel."""
    import _ctypes
    import _signal
    import ctypes
    import posix

    def _recorder(how, result=None, raises=False):
        def _record(*args, **kwargs):
            attempts.append((how, *args))
            if raises:
                raise OSError(f"{how}: recorded, not made")
            return result
        return _record

    for owner, label in ((os, "os"), (posix, "posix")):
        for name in _ENDING + _RUNNING:
            if (label, name) != ("os", "kill") and hasattr(owner, name):
                raises = name in ("fork", "forkpty")           # no stand-in for a child
                monkeypatch.setattr(owner, name, _recorder(f"{label}.{name}", 0, raises))
    for owner, label in ((signal, "signal"), (_signal, "_signal")):
        for name in ("pidfd_send_signal", "pthread_kill"):
            if hasattr(owner, name):
                monkeypatch.setattr(owner, name, _recorder(f"{label}.{name}"))
    monkeypatch.setattr(subprocess, "Popen", lambda args, *a, **k: attempts.append(("subprocess.Popen", args))
                        or _NotRun(attempts))
    monkeypatch.setattr(subprocess, "run", lambda args, *a, **k: attempts.append(("subprocess.run", args))
                        or subprocess.CompletedProcess(args, 0, "", ""))
    for name, result in (("call", 0), ("check_call", 0), ("check_output", ""), ("getoutput", ""),
                         ("getstatusoutput", (0, ""))):
        monkeypatch.setattr(subprocess, name, _recorder(f"subprocess.{name}", result))
    # `subprocess` starts a program through the `fork_exec` it bound at its
    # own import, not through `_posixsubprocess`'s: both are recorders.
    if hasattr(subprocess, "_fork_exec"):
        monkeypatch.setattr(subprocess, "_fork_exec", _recorder("subprocess._fork_exec", raises=True))
    try:
        import _posixsubprocess
    except ImportError:
        pass
    else:
        monkeypatch.setattr(_posixsubprocess, "fork_exec", _recorder("_posixsubprocess.fork_exec", raises=True))
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL", "cdll", "pydll", "windll", "oledll", "pythonapi",
                 "CFUNCTYPE", "PYFUNCTYPE", "WINFUNCTYPE"):
        if hasattr(ctypes, name):
            monkeypatch.setattr(ctypes, name, _Foreign(attempts, f"ctypes.{name}"))
    for name in ("dlopen", "dlsym", "LoadLibrary"):
        if hasattr(_ctypes, name):
            monkeypatch.setattr(_ctypes, name, _recorder(f"_ctypes.{name}", raises=True))


def _mac_parent_only(tmp_path, monkeypatch):
    """The script, loaded only once every recorder is in place (so whatever
    it binds at import is a recorder), and a check on its macOS path, run to
    its parent-only stop with no Mac:
    `open` makes a launcher (700, stamp 1.0) and its server (701, stamp 2.0)
    in a recorded table. Every attempt the check makes to end or signal a
    process or to run a program goes, in order, to `attempts`, and none is
    made: each call to `_signal_if_same` (its pid, signal and the stamp it
    was given) before it looks at the table; each `os.kill` other than the
    one signal a re-checked call may send; every call `_record_every_attempt`
    names; each command given to `_run` past the one unpacking `ditto` and
    the one `open`; each call to the table's `kill`, to the desktop's
    `close` and to `Launch.end_everything`.

    What reaches the kernel goes to `delivered`: a SIGKILL ends its target
    in the table. The launcher's watcher ends the server once the stop
    waits for the launch to be gone (when `gone_within` begins), so no look
    the stop takes of its own can change what is recorded."""
    attempts, delivered, ran, being_sent, tables = [], [], [], [], []

    def _kill(pid, number):
        if being_sent and being_sent[-1] == (pid, number):
            being_sent[-1] = None                  # the one signal a re-checked call may send
        else:
            attempts.append(("os.kill", pid, number))
        delivered.append((pid, number))
        if number == signal.SIGKILL and tables:
            tables[0].table.pop(pid, None)

    _record_every_attempt(monkeypatch, attempts)
    monkeypatch.setattr(os, "kill", _kill)
    module = _module()
    check, _ = _mac_check(module, tmp_path, monkeypatch)
    table = check.processes
    tables.append(table)

    def _run(argv, what):
        if argv[0] in ("/usr/bin/ditto", "/usr/bin/open") and argv[0] not in (done[0] for done in ran):
            ran.append(list(argv))
        else:
            attempts.append(("_run", *argv))
            return
        if argv[0] == "/usr/bin/open":
            data = argv[argv.index("--env") + 1].split("=", 1)[1]
            os.makedirs(os.path.join(data, "Library", "Application Support", "Zij"))
            open(os.path.join(data, "Library", "Application Support", "Zij", "webview_debug.log"), "w").close()
            exe = os.path.join(argv[-1], "Contents", "MacOS", "Zij")
            table.table = {700: module.Proc(700, 1, exe, 1.0), 701: module.Proc(701, 700, exe, 2.0)}

    signal_if_same = module._signal_if_same

    def _signal_if_same(processes, proc, number):
        attempts.append(("_signal_if_same", proc.pid, number, proc.stamp))
        being_sent.append((proc.pid, number))
        try:
            return signal_if_same(processes, proc, number)
        finally:
            being_sent.pop()

    gone_within, kill, end_everything = check.gone_within, table.kill, module.Launch.end_everything

    def _gone_within(launch, began, bound, what):
        if (700, signal.SIGKILL) in delivered:
            table.table.pop(701, None)
        return gone_within(launch, began, bound, what)

    def _table_kill(proc):
        attempts.append(("processes.kill", proc.pid))
        kill(proc)

    def _end_everything(launch):
        attempts.append(("end_everything", launch.number))
        return end_everything(launch)

    monkeypatch.setattr(module, "_signal_if_same", _signal_if_same)
    monkeypatch.setattr(module, "_run", _run)
    monkeypatch.setattr(check, "gone_within", _gone_within)
    monkeypatch.setattr(table, "kill", _table_kill)
    monkeypatch.setattr(module.Launch, "end_everything", _end_everything)
    monkeypatch.setattr(module, "_answers_health", lambda port: True)
    monkeypatch.setattr(module, "_opening_status",
                        lambda port, host, origin=None: 101 if host == f"127.0.0.1:{port}" and not origin else 403)
    monkeypatch.setattr(module, "_accepts", lambda port: 701 in table.table)
    monkeypatch.setattr(module, "_sessions_seen",
                        lambda port: (1314176, ["calculate_prenatal_syzygy"], "1 session(s) open, 1 opened in all"))
    table.listening = lambda pids: {54321: 701} if 701 in pids else {}
    check.desktop = types.SimpleNamespace(find=lambda launcher: (1, "a window of the launcher"), closing="Quit",
                                          close=lambda proc, window: attempts.append(("desktop.close", proc.pid)))
    return module, check, attempts, delivered, ran


def test_on_macos_the_parent_only_stop_sends_sigkill_to_the_launcher_alone(tmp_path, monkeypatch, capsys):
    module, check, attempts, delivered, ran = _mac_parent_only(tmp_path, monkeypatch)
    check.launcher_alone_ended()
    assert attempts == [("_signal_if_same", 700, signal.SIGKILL, 1.0)], \
        "the only attempt: SIGKILL to the launcher, re-checked by its start stamp"
    assert delivered == [(700, signal.SIGKILL)]
    assert check.processes.killed == []
    assert [argv[0] for argv in ran] == ["/usr/bin/ditto", "/usr/bin/open"]
    out = capsys.readouterr().out
    assert ("launch 2: ended the launcher Zij.app/Contents/MacOS/Zij (700) alone by SIGKILL; its server "
            "Zij.app/Contents/MacOS/Zij (701) went too: after ") in out, out


def test_on_macos_a_launcher_whose_start_stamp_no_longer_matches_is_not_signalled(tmp_path, monkeypatch):
    module, check, attempts, delivered, _ = _mac_parent_only(tmp_path, monkeypatch)
    reach = check.reach

    def _reach_then_replaced(launch, made):
        window = reach(launch, made)
        # Between the last look and the signal, the launcher's id now
        # belongs to a later process.
        check.processes.table[700] = module.Proc(700, 1, launch.launcher.exe, 9.0)
        return window

    check.reach = _reach_then_replaced
    with pytest.raises(module.CheckFailed) as failed:
        check.launcher_alone_ended()
    assert attempts == [("_signal_if_same", 700, signal.SIGKILL, 1.0)], "the only attempt, re-checked"
    assert delivered == [] and check.processes.killed == [], "nothing was signalled"
    assert str(failed.value) == ("launch 2: the launcher Zij.app/Contents/MacOS/Zij (700) was not signalled: "
                                 "its id and start stamp no longer matched the process found")


def test_below_a_parent_link_a_process_whose_start_stamp_cannot_be_read_is_not_taken(tmp_path, monkeypatch):
    """Windows keeps an ended parent's id as a later process's parent link;
    a process whose start stamp (or whose parent's) cannot be read has no
    age to compare, so it is not the launch's, and it is never ended."""
    module = _module()
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    processes = _Recorder(module)
    elsewhere = "/elsewhere/program"
    processes.table = {
        10: module.Proc(10, 1, elsewhere, 100.0),          # the launcher this check started
        11: module.Proc(11, 10, elsewhere, 200.0),         # its child
        12: module.Proc(12, 10, elsewhere, None),          # linked to it, its stamp unreadable
        13: module.Proc(13, 10, elsewhere, 50.0),          # linked to it, older: a stale link
        14: module.Proc(14, 12, elsewhere, 300.0),         # below the unreadable one
    }
    assert set(module._walk_down({10: processes.table[10]}, processes.table)) == {10, 11}
    unread = {20: module.Proc(20, 1, elsewhere, None)}
    assert set(module._walk_down(dict(unread), {**unread, 21: module.Proc(21, 20, elsewhere, 5.0)})) == {20}
    ended = []
    launch = module.Launch(processes, str(tmp_path / "download"), 1)
    launch.popen = types.SimpleNamespace(pid=10, poll=lambda: None, kill=lambda: ended.append(10))
    launch.adopt(processes.table[10])
    launch.live()
    assert set(launch.tree) == {10, 11}
    launch.end_everything()
    assert set(ended + processes.killed) == {10, 11}, "only the launcher and its child were ended"


@pytest.mark.parametrize("failures, tries", [(0, "1 try"), (2, "3 tries")])
def test_the_downloads_removal_says_how_many_tries_it_took(tmp_path, monkeypatch, capsys, failures, tries):
    module = _module()
    folder = tmp_path / "download"
    folder.mkdir()
    calls = []

    def _rmtree(path):
        calls.append(path)
        if len(calls) <= failures:
            raise PermissionError(13, "in use", os.path.join(path, "Zij.exe"))
        shutil.rmtree(path)

    monkeypatch.setattr(module, "shutil", types.SimpleNamespace(rmtree=_rmtree))
    check = module.Check.__new__(module.Check)
    check.args = module.parse_args(["--margin-seconds", "10"])
    launch = types.SimpleNamespace(folder=str(folder), number=1)
    check.remove(launch)
    out = capsys.readouterr().out
    assert re.fullmatch(rf"launch 1: removed the unpacked download after \d+\.\d s \({tries}\): no file in it "
                        rf"was held open\n", out), out
    assert not folder.exists() and len(calls) == failures + 1


# --------------------------------------------------------------------------
# The script's imports and its ways to a process, pinned by its syntax tree.
#
# A test of the script's behaviour sees only what the script does on the
# paths the test drives; these pins see the text. They are tripwires for
# edits: a change to the script's imports, or to how or where it ends,
# signals or starts a process, runs a program or calls a foreign function,
# must update the pin below in the same commit, with its reason in the
# commit message, so that a later change is made on purpose.

# Imports, anywhere in the script, each by the function it stands in ("" is
# the module) and in the form it is written.
_IMPORTS = [
    ("", "import argparse"), ("", "import base64"), ("", "import hashlib"), ("", "import json"), ("", "import os"),
    ("", "import re"), ("", "import secrets"), ("", "import shutil"), ("", "import signal"), ("", "import socket"), ("", "import stat"), ("", "import subprocess"), ("", "import sys"),
    ("", "import tempfile"), ("", "import threading"), ("", "import time"), ("", "import urllib.error"),
    ("", "import urllib.request"), ("", "import zipfile"),
    ("MacProcesses.__init__", "import ctypes"),
    ("WindowsProcesses.__init__", "import ctypes"), ("WindowsProcesses.__init__", "from ctypes import wintypes"),
    ("WindowsDesktop.__init__", "import ctypes"), ("WindowsDesktop.__init__", "from ctypes import wintypes"),
    ("MacDesktop.__init__", "import ctypes"),
]
# Modules every use of which is pinned to its place: what signals a process,
# runs a program or calls a foreign function goes through them.
_PLACED_MODULES = ("signal", "subprocess", "sys", "ctypes", "wintypes", "threading")
# `os` is pinned to its place where it is named bare or by one of its process
# names. Its other uses, and every use of the script's other modules, must be
# one the script makes today, wherever it stands: `shutil.os`, `tempfile._os`
# and `os.path.os` reach `os` by a way no use of today's takes.
_OS_PROCESS_NAMES = re.compile(r"kill\w*|fork\w*|system|popen|posix_spawnp?|exec\w*|spawn\w*|abort|pidfd_\w+|"
                               r"register_at_fork|_\w*")
_OTHER_MODULES = ("os", "argparse", "base64", "hashlib", "json", "re", "secrets", "shutil", "socket", "stat",
                  "tempfile", "time", "urllib", "zipfile")
# Names whose every use is pinned to its place: a lookup by a name made at
# run time, the namespaces themselves, code made from text, and the
# script's own ways to signal a process and to run a program.
_PLACED_NAMES = ("getattr", "setattr", "delattr", "globals", "vars", "locals", "eval", "exec", "compile",
                 "__import__", "__builtins__", "breakpoint", "type", "_signal_if_same", "_run")
# Attributes whose every use is pinned to its place, whatever they are read
# from: the ways to end a process through an object, `sys.modules` by any
# road, and the ways to a frame's names. (Every `__dunder__` too.)
_PLACED_ATTRIBUTES = ("kill", "killpg", "terminate", "send_signal", "end_everything", "close", "TerminateProcess",
                      "PostMessageW", "pidfd_send_signal", "pthread_kill", "modules", "f_globals", "f_locals",
                      "f_builtins", "f_back", "tb_frame", "gi_frame", "cr_frame", "ag_frame")
# What makes a foreign library, or a foreign function, from ctypes.
_FOREIGN_MAKERS = ("CDLL", "PyDLL", "WinDLL", "OleDLL", "LoadLibrary", "CFUNCTYPE", "WINFUNCTYPE", "PYFUNCTYPE")


def _chain(node):
    """`a.b.c` as its root name and its attribute names, or None."""
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    return (node.id, *reversed(names)) if isinstance(node, ast.Name) else None


def _script_uses(source):
    """What the stop check's syntax tree says of its imports and of every way
    it has to a process, a program or a foreign function.

    Each node is placed by the qualified name of the function or class it
    stands in ("" for the module). A name or attribute chain is *followed*
    when it starts from `os` or one of `_PLACED_MODULES`, or from what the
    script binds to one of them, or to a foreign library or function made
    by ctypes (`c` and `self.ctypes`; `self._libc`, `k32`, `self.send_bool`
    ...), by any assignment it makes. Bound names are followed in the place
    they are bound in and the places inside it; bound attributes by their
    name, whatever they are read from (`self.processes._libc` too)."""
    tree = ast.parse(source)
    place, parent = {}, {}

    def visit(node, where):
        for child in ast.iter_child_nodes(node):
            place[child], parent[child] = where, node
            inner = where
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{where}.{child.name}" if where else child.name
            visit(child, inner)

    visit(tree, "")
    names = {("", module): module for module in _PLACED_MODULES + ("os",)}
    attributes = {}

    def followed(node):
        chain, where = _chain(node), place.get(node, "")
        if chain is None:
            return None
        while True:
            if (where, chain[0]) in names:
                return names[(where, chain[0])]
            if not where:
                break
            where = where.rpartition(".")[0]
        return next((attributes[name] for name in chain[1:] if name in attributes), None)

    def made_foreign(value):
        while isinstance(value, ast.Call):
            chain = _chain(value.func)
            if chain and chain[-1] in _FOREIGN_MAKERS and followed(value.func):
                return True
            value = value.func
        return False

    def bound_to(value):
        """The module, or "foreign", that `value` is itself (not something
        read from a module), if any."""
        chain = _chain(value)
        if chain is None:
            return "foreign" if made_foreign(value) else None
        if len(chain) == 1 or chain[-1] in attributes:
            return followed(value)
        return "foreign" if followed(value) == "foreign" else None

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            pairs = []
            for target in node.targets:
                if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                        and len(target.elts) == len(node.value.elts):
                    pairs += zip(target.elts, node.value.elts)
                else:
                    pairs.append((target, node.value))
            for target, value in pairs:
                what = bound_to(value)
                if isinstance(target, ast.Name):
                    key, table = (place[node], target.id), names
                elif isinstance(target, ast.Attribute):
                    key, table = target.attr, attributes
                else:
                    continue
                if what is not None and table.get(key) != what:
                    table[key], changed = what, True

    def how(node):
        up = parent.get(node)
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            return "bound"
        if isinstance(up, ast.Call) and up.func is node:
            return "called " + ast.unparse(up)
        if isinstance(up, ast.Call):
            return "passed to " + ast.unparse(up.func)
        if isinstance(up, ast.Subscript) and up.value is node:
            return "indexed " + ast.unparse(up)
        return "read in " + type(up).__name__

    imports, placed, elsewhere, statements = [], [], set(), []
    for node in ast.walk(tree):
        where = place.get(node, "")
        if isinstance(node, ast.Import):
            imports += [(where, f"import {a.name}" + (f" as {a.asname}" if a.asname else "")) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports += [(where, f"from {'.' * node.level}{node.module or ''} import {a.name}"
                         + (f" as {a.asname}" if a.asname else "")) for a in node.names]
        elif isinstance(node, (ast.Match, ast.Global, ast.Nonlocal)):
            statements.append((where, type(node).__name__))
        elif isinstance(node, ast.arg) or isinstance(node, ast.ExceptHandler) and node.name \
                or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.arg if isinstance(node, ast.arg) else node.name
            if name in _PLACED_MODULES + _OTHER_MODULES + _PLACED_NAMES or name in attributes \
                    or any(key[1] == name for key in names):
                placed.append((where, name, f"bound by {type(node).__name__}"))
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        chain = _chain(node)
        if chain is None:                               # read from a call or an index
            if node.attr in _PLACED_ATTRIBUTES or node.attr.startswith("__"):
                placed.append((where, ast.unparse(node), how(node)))
            continue
        if isinstance(parent.get(node), ast.Attribute):
            continue                                    # inside a longer chain: taken with it
        text, module = ".".join(chain), followed(node)
        if chain[0] in _PLACED_NAMES or chain[0].startswith("__") \
                or any(name in _PLACED_ATTRIBUTES or name.startswith("__") for name in chain[1:]):
            placed.append((where, text, how(node)))
        elif module == "os" and chain[0] == "os":
            if len(chain) == 1 or any(_OS_PROCESS_NAMES.fullmatch(name) for name in chain[1:]):
                placed.append((where, text, how(node)))
            else:
                elsewhere.add(text)
        elif module is not None:
            placed.append((where, text, how(node)))
        elif chain[0] in _OTHER_MODULES:
            elsewhere.add(text)
    return tree, imports, placed, elsewhere, statements


def _placed(pinned):
    """`_PLACED_USES` as (place, text, how) entries, each as often as it
    occurs."""
    out = []
    for where, lines in pinned.items():
        for line in lines.strip().splitlines():
            count, times, rest = line.strip().partition(" × ")
            if not times:
                count, rest = "1", line.strip()
            text, how = rest.split(" | ", 1)
            out += [(where, text, how)] * int(count)
    return out


# Today's uses, by the function each stands in: "its text | how it is used",
# with "N × " before one that occurs N times there.
_PLACED_USES = {
    '': """
        __name__ | read in Compare
        _run | bound by FunctionDef
        _signal_if_same | bound by FunctionDef
        sys.exit | called sys.exit(main())
    """,
    'Check.__init__': """
        sys.platform | read in Assign
    """,
    'Check._unpack': """
        _run | called _run(['/usr/bin/ditto', '-x', '-k', self.args.zip, folder], 'unpacking the zip')
    """,
    'Check.launcher_alone_ended': """
        _signal_if_same | called _signal_if_same(self.processes, launch.launcher, signal.SIGKILL)
        launch.popen.kill | called launch.popen.kill()
        signal.SIGKILL | passed to _signal_if_same
    """,
    'Check._one_run': """
        type | called type(error)
        type(error).__name__ | read in FormattedValue
    """,
    'Check.ordinary_stop': """
        self.desktop.close | called self.desktop.close(launch.launcher, window)
    """,
    'Check.run': """
        self.current.end_everything | called self.current.end_everything()
        type | called type(error)
        type(error).__name__ | read in FormattedValue
    """,
    'Check.start': """
        _run | called _run(['/usr/bin/open', '-n', '--stdout', streams[0][1], '--stderr', streams[1][1], '--env', f'HOME={data}', bundle], 'opening the bundle')
        open(path, 'wb').close | called open(path, 'wb').close()
        4 × subprocess.DEVNULL | read in keyword
        subprocess.Popen | called subprocess.Popen([os.path.join(folder, 'Zij.exe')], cwd=folder, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen | called subprocess.Popen(self.args.command, env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    """,
    # The place step's server: its input a pipe only the check holds, closed
    # to stop it as the launcher stops its child; its output and errors a
    # pipe that one thread, a daemon, reads into a file as it comes.
    # A session is opened in one place, which says why one could not be.
    'Check._open': """
        type | called type(error)
        type(error).__name__ | read in FormattedValue
    """,
    'Check.typed_place': """
        launch.popen.stdin.close | called launch.popen.stdin.close()
        other.close | called other.close()
        session.close | called session.close()
        2 × subprocess.PIPE | read in keyword
        subprocess.Popen | called subprocess.Popen(command, cwd=cwd, env=_server_environment(environment, key), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        subprocess.STDOUT | read in keyword
        threading.Thread | called threading.Thread(target=_drain, args=(launch.popen.stdout, output), daemon=True)
    """,
    'Launch.end_everything': """
        self.popen.kill | called self.popen.kill()
        self.processes.kill | called self.processes.kill(proc)
    """,
    'LinuxProcesses.kill': """
        _signal_if_same | called _signal_if_same(self, proc, signal.SIGKILL)
        signal.SIGKILL | passed to _signal_if_same
    """,
    'MacDesktop.__init__': """
        c | bound
        c.CDLL | called c.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        c.CDLL | called c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        c.CDLL | called c.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        c.CDLL | called c.CDLL('/usr/lib/libobjc.A.dylib')
        c.CFUNCTYPE | called c.CFUNCTYPE(c.c_byte, c.c_void_p, c.c_void_p)
        c.CFUNCTYPE | called c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_int32)
        c.c_bool | read in Assign
        c.c_byte | passed to c.CFUNCTYPE
        2 × c.c_char_p | read in List
        c.c_int | read in List
        c.c_int32 | passed to c.CFUNCTYPE
        c.c_long | read in Assign
        c.c_long | read in List
        2 × c.c_uint32 | read in List
        5 × c.c_void_p | passed to c.CFUNCTYPE
        c.c_void_p | passed to c.cast
        5 × c.c_void_p | read in Assign
        7 × c.c_void_p | read in List
        c.c_void_p.in_dll | called c.c_void_p.in_dll(self.cg, 'kCGWindowLayer')
        c.c_void_p.in_dll | called c.c_void_p.in_dll(self.cg, 'kCGWindowOwnerPID')
        c.cast | called c.cast(self.objc.objc_msgSend, c.c_void_p)
        ctypes | read in Assign
        self.cf | bound
        self.cf.CFArrayGetCount.argtypes | bound
        self.cf.CFArrayGetCount.restype | bound
        self.cf.CFArrayGetValueAtIndex.argtypes | bound
        self.cf.CFArrayGetValueAtIndex.restype | bound
        self.cf.CFDictionaryGetValue.argtypes | bound
        self.cf.CFDictionaryGetValue.restype | bound
        self.cf.CFNumberGetValue.argtypes | bound
        self.cf.CFNumberGetValue.restype | bound
        self.cf.CFRelease.argtypes | bound
        self.cg | bound
        2 × self.cg | passed to c.c_void_p.in_dll
        self.cg.CGWindowListCopyWindowInfo.argtypes | bound
        self.cg.CGWindowListCopyWindowInfo.restype | bound
        self.ctypes | bound
        self.objc | bound
        self.objc.objc_getClass.argtypes | bound
        self.objc.objc_getClass.restype | bound
        self.objc.objc_msgSend | passed to c.cast
        self.objc.sel_registerName.argtypes | bound
        self.objc.sel_registerName.restype | bound
        self.send_bool | bound
        self.send_int | bound
    """,
    'MacDesktop._number': """
        self.cf.CFDictionaryGetValue | called self.cf.CFDictionaryGetValue(dictionary, key)
        self.cf.CFNumberGetValue | called self.cf.CFNumberGetValue(value, 4, self.ctypes.byref(out))
        self.ctypes.byref | called self.ctypes.byref(out)
        self.ctypes.c_int64 | called self.ctypes.c_int64()
    """,
    'MacDesktop.close': """
        objc | bound
        objc.objc_getClass | called objc.objc_getClass(b'NSRunningApplication')
        objc.sel_registerName | called objc.sel_registerName(b'runningApplicationWithProcessIdentifier:')
        objc.sel_registerName | called objc.sel_registerName(b'terminate')
        self.objc | read in Assign
        self.send_bool | called self.send_bool(app, objc.sel_registerName(b'terminate'))
        self.send_int | called self.send_int(objc.objc_getClass(b'NSRunningApplication'), objc.sel_registerName(b'runningApplicationWithProcessIdentifier:'), launcher.pid)
    """,
    'MacDesktop.find': """
        self.cf.CFArrayGetCount | called self.cf.CFArrayGetCount(windows)
        self.cf.CFArrayGetValueAtIndex | called self.cf.CFArrayGetValueAtIndex(windows, i)
        self.cf.CFRelease | called self.cf.CFRelease(windows)
        self.cg.CGWindowListCopyWindowInfo | called self.cg.CGWindowListCopyWindowInfo(1 | 16, 0)
    """,
    'MacProcesses.__init__': """
        ctypes.CDLL | called ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        ctypes.create_string_buffer | called ctypes.create_string_buffer(4096)
        self._libc | bound
    """,
    'MacProcesses._path': """
        self._libc.proc_pidpath | called self._libc.proc_pidpath(pid, self._buffer, len(self._buffer))
    """,
    'MacProcesses.kill': """
        _signal_if_same | called _signal_if_same(self, proc, signal.SIGKILL)
        signal.SIGKILL | passed to _signal_if_same
    """,
    'MacProcesses.listening': """
        subprocess.run | called subprocess.run(['/usr/sbin/lsof', '-nP', '-a', '-p', ','.join(map(str, sorted(pids))), '-iTCP', '-sTCP:LISTEN', '-Fpn'], capture_output=True, text=True)
    """,
    'MacProcesses.snapshot': """
        subprocess.run | called subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,stat=,lstart='], capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'), check=True)
    """,
    'Proc': """
        __slots__ | bound
    """,
    'Session.close': """
        self.sock.close | called self.sock.close()
    """,
    'Sighting': """
        __slots__ | bound
    """,
    'WindowsDesktop.__init__': """
        ctypes | read in Tuple
        ctypes.POINTER | called ctypes.POINTER(wintypes.DWORD)
        ctypes.POINTER | called ctypes.POINTER(wintypes.RECT)
        ctypes.WINFUNCTYPE | called ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        ctypes.WinDLL | called ctypes.WinDLL('user32', use_last_error=True)
        self.WNDENUMPROC | bound
        self.WNDENUMPROC | read in List
        self.ctypes | bound
        self.u32 | bound
        self.wintypes | bound
        u32 | bound
        u32.EnumWindows.argtypes | bound
        u32.GetWindow.argtypes | bound
        u32.GetWindow.restype | bound
        u32.GetWindowRect.argtypes | bound
        u32.GetWindowThreadProcessId.argtypes | bound
        u32.GetWindowThreadProcessId.restype | bound
        u32.IsWindowVisible.argtypes | bound
        u32.PostMessageW.argtypes | bound
        wintypes | read in Tuple
        wintypes.BOOL | passed to ctypes.WINFUNCTYPE
        wintypes.DWORD | passed to ctypes.POINTER
        wintypes.DWORD | read in Assign
        wintypes.HWND | passed to ctypes.WINFUNCTYPE
        wintypes.HWND | read in Assign
        5 × wintypes.HWND | read in List
        wintypes.LPARAM | passed to ctypes.WINFUNCTYPE
        2 × wintypes.LPARAM | read in List
        wintypes.RECT | passed to ctypes.POINTER
        2 × wintypes.UINT | read in List
        wintypes.WPARAM | read in List
    """,
    'WindowsDesktop.close': """
        self.ctypes.get_last_error | called self.ctypes.get_last_error()
        self.u32.PostMessageW | called self.u32.PostMessageW(window[0], 16, 0, 0)
    """,
    'WindowsDesktop.find': """
        ctypes | bound
        self.WNDENUMPROC | called self.WNDENUMPROC(each)
        self.ctypes | read in Tuple
        self.u32 | read in Tuple
        self.wintypes | read in Tuple
        u32 | bound
        u32.EnumWindows | called u32.EnumWindows(self.WNDENUMPROC(each), 0)
        wintypes | bound
    """,
    'WindowsDesktop.find.each': """
        ctypes.byref | called ctypes.byref(owner)
        ctypes.byref | called ctypes.byref(rect)
        u32.GetWindow | called u32.GetWindow(hwnd, 4)
        u32.GetWindowRect | called u32.GetWindowRect(hwnd, ctypes.byref(rect))
        u32.GetWindowThreadProcessId | called u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        u32.IsWindowVisible | called u32.IsWindowVisible(hwnd)
        wintypes.DWORD | called wintypes.DWORD()
        wintypes.RECT | called wintypes.RECT()
    """,
    'WindowsProcesses.__init__': """
        ctypes | read in Tuple
        ctypes.POINTER | called ctypes.POINTER(PROCESSENTRY32W)
        ctypes.POINTER | called ctypes.POINTER(ctypes.c_ulonglong)
        ctypes.POINTER | called ctypes.POINTER(wintypes.DWORD)
        ctypes.WinDLL | called ctypes.WinDLL('iphlpapi')
        ctypes.WinDLL | called ctypes.WinDLL('kernel32', use_last_error=True)
        ctypes.c_ulonglong | passed to ctypes.POINTER
        k32 | bound
        k32.CloseHandle.argtypes | bound
        k32.CreateToolhelp32Snapshot.argtypes | bound
        k32.CreateToolhelp32Snapshot.restype | bound
        k32.GetProcessTimes.argtypes | bound
        k32.OpenProcess.argtypes | bound
        k32.OpenProcess.restype | bound
        k32.Process32FirstW.argtypes | bound
        k32.Process32NextW.argtypes | bound
        k32.QueryFullProcessImageNameW.argtypes | bound
        k32.TerminateProcess.argtypes | bound
        k32.WaitForSingleObject.argtypes | bound
        k32.WaitForSingleObject.restype | bound
        self.ctypes | bound
        self.iphlpapi | bound
        self.k32 | bound
        self.wintypes | bound
        wintypes | read in Tuple
        wintypes.BOOL | read in List
        wintypes.DWORD | passed to ctypes.POINTER
        wintypes.DWORD | read in Assign
        6 × wintypes.DWORD | read in List
        2 × wintypes.HANDLE | read in Assign
        6 × wintypes.HANDLE | read in List
        wintypes.LPWSTR | read in List
        wintypes.UINT | read in List
    """,
    'WindowsProcesses.__init__.PROCESSENTRY32W': """
        ctypes.Structure | read in ClassDef
        ctypes.c_long | read in Tuple
        ctypes.c_size_t | read in Tuple
        ctypes.c_wchar | read in BinOp
        7 × wintypes.DWORD | read in Tuple
    """,
    'WindowsProcesses._identity': """
        ctypes | bound
        ctypes.byref | called ctypes.byref(created)
        ctypes.byref | called ctypes.byref(size)
        ctypes.byref | passed to map
        2 × ctypes.c_ulonglong | called ctypes.c_ulonglong()
        ctypes.create_unicode_buffer | called ctypes.create_unicode_buffer(size.value)
        self.ctypes | read in Tuple
        self.k32.GetProcessTimes | called self.k32.GetProcessTimes(handle, ctypes.byref(created), *map(ctypes.byref, rest))
        self.k32.QueryFullProcessImageNameW | called self.k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        self.wintypes | read in Tuple
        wintypes | bound
        wintypes.DWORD | called wintypes.DWORD(32768)
    """,
    'WindowsProcesses._open': """
        self.k32.OpenProcess | called self.k32.OpenProcess(access, False, pid)
    """,
    'WindowsProcesses.alive': """
        self.k32.CloseHandle | called self.k32.CloseHandle(handle)
        self.k32.WaitForSingleObject | called self.k32.WaitForSingleObject(handle, 0)
    """,
    'WindowsProcesses.kill': """
        self.k32.CloseHandle | called self.k32.CloseHandle(handle)
        self.k32.TerminateProcess | called self.k32.TerminateProcess(handle, 1)
    """,
    'WindowsProcesses.listening': """
        ctypes | bound
        ctypes.POINTER | called ctypes.POINTER(wintypes.DWORD)
        ctypes.byref | called ctypes.byref(size)
        ctypes.c_int | read in List
        ctypes.c_void_p | read in List
        ctypes.create_string_buffer | called ctypes.create_string_buffer(max(size.value, 4))
        ctypes.sizeof | called ctypes.sizeof(wintypes.DWORD)
        get | bound
        get | called get(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0)
        get.argtypes | bound
        self.ctypes | read in Tuple
        self.iphlpapi.GetExtendedTcpTable | read in Assign
        self.wintypes | read in Tuple
        wintypes | bound
        wintypes.BOOL | read in List
        wintypes.DWORD | called wintypes.DWORD(0)
        wintypes.DWORD | passed to ctypes.POINTER
        wintypes.DWORD | passed to ctypes.sizeof
        wintypes.DWORD.from_buffer | called wintypes.DWORD.from_buffer(buffer)
        2 × wintypes.ULONG | read in List
    """,
    'WindowsProcesses.listening.ROW': """
        ctypes.Structure | read in ClassDef
        wintypes.DWORD | read in Tuple
    """,
    'WindowsProcesses.snapshot': """
        ctypes | bound
        2 × ctypes.byref | called ctypes.byref(entry)
        ctypes.c_void_p | called ctypes.c_void_p(-1)
        ctypes.get_last_error | called ctypes.get_last_error()
        ctypes.sizeof | called ctypes.sizeof(entry)
        self.ctypes | read in Assign
        self.k32.CloseHandle | called self.k32.CloseHandle(handle)
        self.k32.CloseHandle | called self.k32.CloseHandle(snap)
        self.k32.CreateToolhelp32Snapshot | called self.k32.CreateToolhelp32Snapshot(2, 0)
        self.k32.Process32FirstW | called self.k32.Process32FirstW(snap, ctypes.byref(entry))
        self.k32.Process32NextW | called self.k32.Process32NextW(snap, ctypes.byref(entry))
    """,
    '_exit_code': """
        subprocess.TimeoutExpired | read in ExceptHandler
    """,
    '_run': """
        subprocess.TimeoutExpired | read in Tuple
        subprocess.run | called subprocess.run(argv, capture_output=True, text=True, timeout=60)
    """,
    '_say_details': """
        getattr | called getattr(check, 'details', None)
    """,
    '_signal_if_same': """
        os.kill | called os.kill(proc.pid, number)
    """,
    '_walk_down': """
        type | called type(parent.stamp)
        type | called type(proc.stamp)
    """,
    'main': """
        sys.stdout.reconfigure | called sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
        type | called type(error)
        type(error).__name__ | read in FormattedValue
    """,
    'parse_args': """
        sys.platform | passed to ZIPS.get
    """,
}
_USED_ANYWHERE = {
    'argparse.ArgumentParser', 'argparse.REMAINDER', 'argparse.SUPPRESS', 'base64.b64encode', 'hashlib.sha1',
    'json.loads', 'os.SEEK_END', 'os.environ',
    'os.O_BINARY', 'os.O_NOFOLLOW', 'os.O_NONBLOCK', 'os.O_RDONLY', 'os.fstat', 'os.name', 'os.open',
    'os.environ.get', 'os.getcwd', 'os.getpid', 'os.listdir', 'os.makedirs', 'os.path.abspath', 'os.path.basename',
    'os.path.exists', 'os.path.expanduser', 'os.path.getmtime', 'os.path.isdir', 'os.path.isfile', 'os.path.islink',
    'os.path.join',
    'os.path.normcase', 'os.path.realpath', 'os.path.relpath', 'os.read', 'os.readlink', 'os.sep', 'os.urandom', 're.compile',
    're.findall',
    'secrets.token_urlsafe', 'shutil.rmtree', 'socket.AF_INET', 'socket.SOCK_STREAM', 'socket.create_connection',
    'socket.ntohs', 'socket.socket', 'stat.S_ISREG', 'tempfile.mkdtemp', 'time.mktime',
    'time.monotonic',
    'time.sleep', 'time.strptime', 'time.time', 'urllib.error.URLError', 'urllib.request.ProxyHandler',
    'urllib.request.Request', 'urllib.request.build_opener', 'zipfile.ZipFile',
}

# The one place the script sends a signal, and the re-check it makes first,
# each by its whole text.
_SIGNAL_IF_SAME = '''def _signal_if_same(processes, proc, number):
    """Signal `proc` only if a fresh look still finds it by its id and start
    stamp; whether the signal was sent."""
    if proc.same(processes.snapshot().get(proc.pid)):
        try:
            os.kill(proc.pid, number)
            return True
        except OSError:
            pass
    return False'''
_SAME = '''def same(self, other):
    return other is not None and other.pid == self.pid and (other.stamp == self.stamp)'''

_CONSTANTS = ("STOP_SECONDS", "ORPHAN_SECONDS", "MARGIN_SECONDS", "REACH_SECONDS", "POLL_SECONDS", "REBOUND_HOST",
              "FOREIGN_ORIGIN",
              "PROBE_SECONDS", "TAIL_LINES", "LINE_CHARS", "TAIL_BYTES", "APP_DIR_NAME", "WINDOW_LOG_NAME",
              "METRICS_PATH", "_MEDIA", "_ENGINE_RESULT", "ZIPS",
              "SERVER_SENTINEL", "LISTENING_MARK", "LAUNCH_KEY_VARIABLE", "LAUNCH_KEY_PARAMETER", "LAUNCH_KEY_REFUSAL",
              "CITY_SEARCH_KEY", "PLACE_CHOICE_LABEL", "PLACE_TYPED", "PLACE_FOUND",
              "WHEEL_COMPONENT", "KNOWN_POINT", "KNOWN_LONGITUDE", "KNOWN_TOLERANCE", "RUN_SECONDS", "DRAIN_SECONDS",
              "MESSAGE_BYTES",
              "SAID_SHOWN", "OPTIONS_SHOWN", "OPTION_CHARS", "_WITHHELD", "_KEYS", "_TOKENS", "_CONTROL", "_STAMP",
              "FINISHED", "FINISHED_WITH_COMPILE_ERROR", "_ALERT_KINDS", "_REPORT_FIELDS")


def _difference(found, pinned):
    found, pinned = Counter(found), Counter(pinned)
    return "\n".join([f"not in the pin: {entry}" for entry in sorted((found - pinned).elements())]
                     + [f"in the pin, not in the script: {entry}" for entry in sorted((pinned - found).elements())])


def test_the_scripts_imports_are_todays_each_in_its_form_and_place():
    """The script imports exactly today's modules, each where it does today
    and as it is written today: a new import (`multiprocessing`, `atexit`,
    `_ctypes` ...), an `as` alias, a `from X import Y` of another name, or a
    module reached without an import statement fails. A change to the
    script's imports must update `_IMPORTS` in the same commit, with its
    reason."""
    tree, imports, _, _, _ = _script_uses(SCRIPT.read_text(encoding="utf-8"))
    assert Counter(imports) == Counter(_IMPORTS), _difference(imports, _IMPORTS)
    other_ways = [(node.lineno, ast.unparse(node)) for node in ast.walk(tree)
                  if isinstance(node, ast.Name) and node.id in ("__import__", "importlib", "builtins", "__builtins__",
                                                                "__loader__", "__spec__")
                  or isinstance(node, ast.Attribute) and node.attr in ("__import__", "import_module", "__loader__",
                                                                      "__spec__", "modules")]
    assert other_ways == [], "a module reached without an import statement"


def test_the_scripts_ways_to_a_process_are_todays_each_at_its_place():
    """Every way the script has to end or signal a process, run a program,
    start a thread, leave a hook, or call a foreign function is one of
    today's, in the function it stands in today, in the form it has today
    (a call by its whole text), read through its module: `os.kill` in
    `_signal_if_same` alone, `subprocess.run` and `subprocess.Popen` where
    they are, every use of `signal`, `subprocess`, `sys`, `ctypes` and
    `wintypes`, every foreign library and function the script makes and
    every use of each, every lookup by name (`getattr` ...), namespace
    (`globals`, `vars`, any `__dunder__`) and frame; and `_signal_if_same`
    and `Proc.same`, the one place a signal is sent and its re-check, by
    their whole text. A binding of any of
    them at import (`_Popen = subprocess.Popen`), a new use anywhere, or a
    use moved to another function fails, with the entries that differ.
    A change to the script's process calls must update `_PLACED_USES` (and
    `_USED_ANYWHERE`) in the same commit, with its reason."""
    tree, _, placed, elsewhere, statements = _script_uses(SCRIPT.read_text(encoding="utf-8"))
    pinned = _placed(_PLACED_USES)
    assert Counter(placed) == Counter(pinned), _difference(placed, pinned)
    assert elsewhere <= _USED_ANYWHERE, f"not in the pin: {sorted(elsewhere - _USED_ANYWHERE)}"
    assert statements == [], "a match, global or nonlocal statement reaches names the pin does not follow"
    helpers = {node.name: ast.unparse(node) for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name in ("_signal_if_same", "same")}
    assert helpers == {"_signal_if_same": _SIGNAL_IF_SAME, "same": _SAME}, \
        "the one place a signal is sent, or the re-check it makes first, changed"


def test_at_import_the_script_binds_only_its_constants_and_definitions():
    """At import the script binds today's forty-five constants, none to anything
    from a module but a compiled pattern, and defines its functions and
    classes; it makes no other statement at module level and decorates
    nothing it defines, so nothing it binds at import holds a process call.
    A change here must update the pin in the same commit, with its reason."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    first, *body, last = tree.body
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant), "the module's docstring"
    assert ast.unparse(last) == "if __name__ == '__main__':\n    sys.exit(main())"
    assigned, other = [], []
    for statement in body:
        if isinstance(statement, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 \
                and isinstance(statement.targets[0], ast.Name):
            assigned.append(statement.targets[0].id)
            calls = {ast.unparse(node.func) for node in ast.walk(statement.value) if isinstance(node, ast.Call)}
            names = {node.id for node in ast.walk(statement.value) if isinstance(node, ast.Name)}
            if calls <= {"re.compile"} and names <= {"re"}:
                continue
        other.append((statement.lineno, ast.unparse(statement)[:80]))
    assert other == [], "a module-level statement other than an import, a definition or a constant (bound to a " \
                        "value or a compiled pattern alone)"
    assert assigned == list(_CONSTANTS)
    decorated = [(node.lineno, node.name) for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.decorator_list]
    assert decorated == [], "a decorator runs at import"
