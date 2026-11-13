"""The release build's stop check asks the launcher's own key hand-off and a
named-zone cast; the launcher keeps a bounded tail of its server's output;
the build's runners and Python are named to the image and the patch release.

* The key hand-off. In the two launches that go through the real launcher,
  once the window's own session has run the app, the check opens a session
  with no key in its address and one with a key it makes (it never knows
  the launcher's): the first run of each must show the sentence a session
  without the key is told and nothing else. Live: the check against a copy
  whose launcher no longer hands its server the key fails at the first
  launch, naming the keyless session; against a stand-in server that lets
  every session in, likewise.
* The named zone. In the third launch, after the place typed: the example's
  city at 1990-06-15 12:00:00 (the time standard's box follows to the zone on
  its own), the example's coordinates typed in the city search, and the
  named zone chosen in the box. Each must show the zone and offset the app
  shows here and no other sentence. The expected values are computed from
  the source app here, and the names the check sends are the app's. Live:
  a copy whose recorded zone-package digest differs fails quoting the
  zone-data sentence; a copy whose box no longer follows (it casts at local
  mean time, as before) fails naming the offset seen.
* The server's output. The launcher reads every line of its child's output
  to the end and sees the listening mark on each, but keeps only the last
  SERVER_OUTPUT_LINES lines, each cut to SERVER_OUTPUT_LINE_CHARS
  characters; a child writing far more than a pipe holds after the mark is
  never left waiting; and a failed start's message carries the last lines.
* The toolchain. No runner the build asks for is a `-latest` label; Python
  is pinned to the patch release; the macOS image's architecture is the
  macOS lock's platform. Each form that would let one float, planted, is
  refused. (That the test workflow pins the same release is asked by a
  companion file of the private suite, which reads that workflow.)
"""
import ast
import importlib.util
import io
import re
import sys
import threading
import types
from datetime import time as clock_time

import pytest

from conftest import EXECUTABLE_DIR
# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import _PASSING, _failure, _fake, _module, _outside
from test_stop_check_atlas_2026_10_15 import APP, _assigned, _calls, _copy, _failure_and_details, _finish, \
    _run_check, _step
from test_sec4_build_workflow_2026_10_13 import WORKFLOW, _build_runners, load_yaml
from test_build2_locked_build_2026_10_15 import SYSTEMS

LAUNCHER = EXECUTABLE_DIR / "desktop_launcher.py"
ENGINE = EXECUTABLE_DIR / "engine.py"
HAND_OFF = "    environment[LAUNCH_KEY_VARIABLE] = secret\n"
FOLLOW = 'if chart_ok and not st.session_state.get("_time_standard_picked"):\n'


def _prose(path):
    """A file's text with its comments' markers taken out, its white space
    one space."""
    return " ".join(re.sub(r"\n\s*# ?", "\n", path.read_text(encoding="utf-8")).split())


def _replaced(program, name, old, new):
    """`program`'s `name` a file of its own: this checkout's with `old`, found
    once, replaced by `new`."""
    text = (EXECUTABLE_DIR / name).read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    (program / name).unlink()
    (program / name).write_text(text.replace(old, new), encoding="utf-8")
    return program


# --------------------------------------------------------------------------
# The key hand-off, asked of the launches through the real launcher.

def test_live_a_launcher_that_hands_its_server_no_key_fails_at_the_first_launch(tmp_path):
    """The launcher's server started without the key in its environment:
    the app then lets every session in, the window's among them, and the
    first launch fails on the session opened with no key, which ran the
    app."""
    program = _replaced(_copy(tmp_path), "desktop_launcher.py", HAND_OFF, "")
    code, out = _run_check(tmp_path, program)
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    found = re.fullmatch(r"stop check FAILED: launch 1: the first run of a session with no key in its address was "
                         r"not refused: the server never told it that the app can be used only in its own window, "
                         r"and showed it (\d+) element\(s\)", failure)
    assert found, out
    assert int(found[1]) > 10, "the whole app, let in"
    assert "launch 1: the window's own session ran the app: " in out
    assert "launch 2:" not in out and "launch 3:" not in out


def test_against_a_server_that_lets_every_session_in_the_first_launch_fails(tmp_path):
    code, out = _fake(tmp_path, "lets-in")
    assert code == 1, out
    assert _failure(out) == ("stop check FAILED: launch 1: the first run of a session with no key in its address was "
                             "not refused: the server never told it that the app can be used only in its own "
                             "window, and showed it 1 element(s)"), out
    assert "launch 1: the window's own session ran the app: " in out


def test_each_window_launch_asks_both_sessions_after_the_window_ran_the_app(tmp_path):
    """Against the stand-in that refuses them: in launches 1 and 2 the two
    sessions are opened after the window's admission and before the stop,
    one with no key and one with a key the check made; its key is printed
    nowhere."""
    code, out = _fake(tmp_path, "obeys", bounds=_PASSING)
    assert code == 0, out
    lines = out.splitlines()
    for n in (1, 2):
        mine = [line for line in lines if line.startswith(f"launch {n}: ")]
        at = [i for i, line in enumerate(mine) if line.startswith(f"launch {n}: then one session opened as the "
                                                                  f"window opens one but with no key")]
        assert len(at) == 1, out
        assert mine[at[0] - 1].startswith(f"launch {n}: timed start: "), out     # read off the same run
        assert "the window's own session ran the app" in mine[at[0] - 2], out
        assert ("closed by" if n == 1 else "ended the launcher") in mine[at[0] + 1], out
    assert "launch=" not in out


def test_the_door_no_longer_hands_the_key_to_the_third_launch():
    source = (EXECUTABLE_DIR / ".github" / "scripts" / "stop_check.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    check = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Check")
    methods = {node.name: node for node in check.body if isinstance(node, ast.FunctionDef)}
    assert "third launch" not in ast.get_docstring(methods["door"])
    reach = [ast.unparse(statement) for statement in methods["reach"].body]
    assert reach.index("self.admitted(launch)") < reach.index(
        "self.strangers_refused(launch, made, 'a key this check made')") < reach.index("return window")
    docstring = ast.get_docstring(module)
    first = docstring.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
    assert "one with no key in the" in first and "a key this check makes" in first, first
    assert "the two\n   sessions without its key as the first's" in docstring


# --------------------------------------------------------------------------
# The named zone: what the check expects, computed from the source app.

def _example_chart():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    [node] = [node for node in tree.body if isinstance(node, ast.Assign)
              and getattr(node.targets[0], "id", None) == "EXAMPLE_CHART"]
    return {key.value: value.value for key, value in zip(node.value.keys, node.value.values)
            if isinstance(value, ast.Constant)}


def _time_standard_options():
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    [node] = [node for node in tree.body if isinstance(node, ast.Assign)
              and getattr(node.targets[0], "id", None) == "TIME_STANDARD_OPTIONS"]
    return ast.literal_eval(node.value)


def _zone_data_sentence():
    """app.py's ZONE_DATA_CHANGED_MESSAGE, evaluated as the app makes it."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    names = {"TIME_STANDARD_OPTIONS": _time_standard_options()}
    for wanted in ("_LMT_OR_MANUAL", "ZONE_DATA_CHANGED_MESSAGE"):
        [node] = [node for node in tree.body if isinstance(node, ast.Assign)
                  and getattr(node.targets[0], "id", None) == wanted]
        names[wanted] = eval(compile(ast.Expression(node.value), "app.py", "eval"), {}, names)
    return names["ZONE_DATA_CHANGED_MESSAGE"]


def test_the_names_the_named_zone_runs_send_are_the_apps():
    module, example = _module(), _example_chart()
    keys = {kind: [kw.value.value for call in _calls(APP, kind) for kw in call.keywords
                   if kw.arg == "key" and isinstance(kw.value, ast.Constant)] for kind in ("text_input", "time_input")}
    assert keys["text_input"].count(module.DATE_KEY) == 1, "the date box"
    assert keys["time_input"].count(module.TIME_KEY) == 1, "the time box"
    labels = [call.args[0].value for call in _calls(APP, "selectbox")
              if call.args and isinstance(call.args[0], ast.Constant)]
    assert labels.count(module.TIME_STANDARD_LABEL) == 1, "the time standard's box"
    assert module.STANDARD_TIME_OPTION == _time_standard_options()[1], "the named-zone option"
    assert module.EXAMPLE_PLACE == example["location_input_key"]
    assert module.ZONE_COORDINATES == f"{example['manual_lat_key']}, {example['manual_lon_key']}"
    # The time box steps by the second, so the window sends its value to it.
    [step] = [kw.value for call in _calls(APP, "time_input") for kw in call.keywords if kw.arg == "step"]
    assert ast.unparse(step) == "timedelta(seconds=1)"
    assert re.fullmatch(r"\d\d:\d\d:\d\d", module.ZONE_TIME) and re.fullmatch(r"\d{4}-\d\d-\d\d", module.ZONE_DATE)


def _elements(at):
    """The run's alerts and exceptions as the check reads them."""
    found = []
    for number, kind in ((1, "error"), (2, "warning"), (3, "info"), (4, "success")):
        found += [("alert", number, element.value) for element in getattr(at, kind)]
    return found + [("exception", "", element.value) for element in at.exception]


def _zone_runs(module):
    from streamlit.testing.v1 import AppTest
    from conftest import APP_PATH, sync_engine_to_environment

    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300).run()
    at.text_input(key=module.DATE_KEY).set_value(module.ZONE_DATE)
    at.time_input(key=module.TIME_KEY).set_value(clock_time.fromisoformat(module.ZONE_TIME))
    runs = [_elements(at.run())]
    at.text_input(key="location_input_key").set_value(module.ZONE_COORDINATES)
    runs.append(_elements(at.run()))
    at.selectbox(key="time_standard_key").set_value(module.STANDARD_TIME_OPTION)
    runs.append(_elements(at.run()))
    return runs


def test_the_zone_and_offset_the_check_expects_are_the_ones_the_app_shows_here():
    """The source app at the check's moment shows, in each of the three runs,
    the time standard's box at ZONE_NAME and ZONE_OFFSET and the place's box,
    and nothing else."""
    module = _module()
    runs = _zone_runs(module)
    assert len(runs) == 3
    for elements in runs:
        assert module._beside_the_zone(elements) == ([], [(module.ZONE_NAME, module.ZONE_OFFSET)]), elements
        assert sorted(element[1] for element in elements) == [3, 4], elements


def test_with_its_zone_data_changed_the_app_says_so_at_the_first_run_and_when_the_zone_is_chosen(monkeypatch):
    """The premise of the check's failure: the box's own follow keeps local
    mean time when the zone data is refused, and the zone-data sentence
    stands under the LMT box; the zone chosen by hand is refused with it."""
    import time_zones

    module = _module()
    name, version, count, _ = time_zones.ZONE_PACKAGES["tzdata"]
    monkeypatch.setitem(time_zones.ZONE_PACKAGES, "tzdata", (name, version, count, "0" * 64))
    monkeypatch.setattr(time_zones, "_ZONE_PACKAGES_SEEN", {})
    followed, typed, chosen = _zone_runs(module)
    for run in (followed, typed):
        assert module._beside_the_zone(run)[0] == [f"warning: {_zone_data_sentence()}"]
        assert [zone for zone, _ in module._beside_the_zone(run)[1]] == ["Exact LMT"]
    assert module._beside_the_zone(chosen)[0][:1] == [f"error: {_zone_data_sentence()}"]


# --------------------------------------------------------------------------
# The named zone, live: the check's own step against a copy of the program.

def test_live_a_download_whose_zone_data_differs_fails_quoting_the_sentence(tmp_path, monkeypatch, capsys):
    import time_zones

    recorded = time_zones.ZONE_PACKAGES["tzdata"][3]
    program = _replaced(_copy(tmp_path), "time_zones.py", f"'{recorded}'", f"'{'0' * 64}'")
    module, check, short = _step(tmp_path, monkeypatch, program)
    out, failure = _finish(module, check, short, capsys)
    # It fails at its first run, which follows the date and says the
    # sentence under the LMT box, before any zone is chosen.
    assert failure == (f"launch 3: the run with {module.EXAMPLE_PLACE!r} in the city search at {module.ZONE_DATE} "
                       f"{module.ZONE_TIME} said, beside the time standard's box and the place's: warning: "
                       f"{_zone_data_sentence()}"), out
    assert f"launch 3: the example chart's wheel puts {module.KNOWN_POINT} at " in out, "the steps before held"


def test_live_a_download_whose_box_casts_at_local_mean_time_fails_naming_the_offset(tmp_path, monkeypatch, capsys):
    """The box no longer follows the date and the place to the named zone,
    as before it did: the first named-zone run casts at local mean time."""
    module, check, short = _step(tmp_path, monkeypatch, _replaced(_copy(tmp_path), "app.py", FOLLOW, "if False:\n"))
    out, failure = _finish(module, check, short, capsys)
    assert failure == (f"launch 3: the run with {module.EXAMPLE_PLACE!r} in the city search at {module.ZONE_DATE} "
                       f"{module.ZONE_TIME}: the time standard's box showed Exact LMT · UTC offset +00:44:59, not "
                       f"{module.ZONE_NAME} · UTC offset {module.ZONE_OFFSET}, where the app casts that moment on "
                       f"the system the suite runs on"), out
    assert "  | info: **Exact LMT** · UTC offset +00:44:59 UT 1990-06-15 11:15:01" in out, out


# --------------------------------------------------------------------------
# The server's output, kept to a bound.

def _launcher(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_under_test", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bound_is_said_and_small():
    constants = _assigned(LAUNCHER)
    lines, chars = constants["SERVER_OUTPUT_LINES"], constants["SERVER_OUTPUT_LINE_CHARS"]
    assert (lines, chars) == (100, 500)
    text = _prose(LAUNCHER)
    assert f"so at most {lines * chars:,} characters, and {4 * lines * chars:,} bytes of text however they are written" \
        in text


def test_the_drain_keeps_the_bound_sees_the_mark_and_keeps_the_last_lines(monkeypatch):
    launcher = _launcher(monkeypatch)
    n, m = launcher.SERVER_OUTPUT_LINES, launcher.SERVER_OUTPUT_LINE_CHARS
    mark = f"{launcher.SERVER_LISTENING_MARK} 54321"
    before = [f"before {i} " + "b" * (20 * m if i % 7 == 0 else 10) for i in range(10 * n)]
    after = [f"after {i} " + "a" * (20 * m if i % 5 == 0 else 10) for i in range(10 * n)]
    output = launcher._ServerOutput(mark)
    output.drain(io.StringIO("\n".join(before + [mark] + after) + "\n"))
    assert output.listening.is_set(), "the mark, among far more lines than are kept"
    kept = output.text().split("\n")
    assert len(kept) == n and max(map(len, kept)) <= m
    assert kept == [line[:m] for line in after[-n:]], "the last lines, each cut"
    # Every line is still looked at: the mark after them is seen too.
    late = launcher._ServerOutput(mark)
    late.drain(io.StringIO("\n".join(before) + "\n" + mark + "  \n"))
    assert late.listening.is_set() and late.text().split("\n")[-1] == mark


@pytest.mark.parametrize("text, seen", [
    (lambda mark, m: mark, True),
    (lambda mark, m: mark + "\r\n", True),
    (lambda mark, m: mark + " " * (2 * m) + "x\n", False),
    (lambda mark, m: "x" * (m - 1) + "\n" + mark + "\n", True),
    (lambda mark, m: "x" * m + mark + "\n", False),
    (lambda mark, m: "x" * (3 * m) + "\n" + mark + "\n", True),
    (lambda mark, m: mark + "0\n", False),
], ids=["at-the-end-without-a-line-end", "a-windows-line-end", "a-longer-line-it-begins", "after-a-line-a-char-short",
        "inside-a-cut-line", "after-a-cut-line", "another-port"])
def test_the_mark_is_seen_only_as_a_whole_line(monkeypatch, text, seen):
    launcher = _launcher(monkeypatch)
    mark = f"{launcher.SERVER_LISTENING_MARK} 54321"
    output = launcher._ServerOutput(mark)
    output.drain(io.StringIO(text(mark, launcher.SERVER_OUTPUT_LINE_CHARS), newline=None))
    assert output.listening.is_set() is seen


_CHILD = r'''import sys
out = sys.stdout.buffer
out.write(b"\xff\xfe not text in any encoding read\n")
out.write(b"zij-server-listening 54321\n")
for i in range(40000):
    out.write(b"%06d " % i + b"y" * 60 + b"\n")
out.write(b"z" * 300000 + b"\n")
out.write(b"the last line\n")
out.flush()
'''


def test_a_child_that_writes_far_more_than_a_pipe_holds_after_the_mark_is_never_left_waiting(monkeypatch, tmp_path):
    """The server child as the launcher starts it (its own pipe settings),
    writing a byte that is not text, the mark, and some 3 MB more: the
    reader drains it to its end, so the child ends; what is kept is the
    bound."""
    launcher = _launcher(monkeypatch)
    script = tmp_path / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    monkeypatch.setattr(launcher, "_self_invoke_command", lambda port: [sys.executable, str(script)])
    proc = launcher._start_server("54321", "a-secret")
    output = launcher._ServerOutput(f"{launcher.SERVER_LISTENING_MARK} 54321")
    reader = threading.Thread(target=output.drain, args=(proc.stdout,), daemon=True)
    reader.start()
    try:
        assert proc.wait(60) == 0, "the child waited on a pipe left full"
        reader.join(30)
        assert not reader.is_alive(), "the reader never reached the pipe's end"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdin.close()
        proc.stdout.close()
    assert output.listening.is_set()
    kept = output.text().split("\n")
    assert len(kept) == launcher.SERVER_OUTPUT_LINES and kept[-1] == "the last line"
    assert kept[-2] == "z" * launcher.SERVER_OUTPUT_LINE_CHARS


def test_a_failed_start_says_the_last_lines_it_kept(monkeypatch, tmp_path):
    """The launcher's own failure: its server never reached, the message
    carries the last lines of what its child wrote, within the bound."""
    launcher = _launcher(monkeypatch)
    script = tmp_path / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    monkeypatch.setattr(launcher, "_self_invoke_command", lambda port: [sys.executable, str(script)])
    monkeypatch.setattr(launcher, "_window_log_folder", lambda: str(tmp_path))
    monkeypatch.setattr(launcher, "_open_window_log", lambda folder: None)
    monkeypatch.setattr(launcher, "_withhold_the_secret", lambda secret: None)
    monkeypatch.setattr(launcher.atexit, "register", lambda function: None)
    # The window opens on its "Opening…" page before the server is waited
    # for; the wait runs in webview.start's function, as pywebview runs it.
    destroyed = []
    hooks = type("Hooks", (list,), {"__iadd__": lambda self, hook: (self.append(hook), self)[1]})
    window = types.SimpleNamespace(events=types.SimpleNamespace(loaded=hooks(), closing=hooks()),
                                   destroy=lambda: destroyed.append(True), load_url=lambda address: None)
    monkeypatch.setattr(launcher.webview, "create_window", lambda title, url=None, **options: window, raising=False)
    monkeypatch.setattr(launcher.webview, "start", lambda func, win, **options: func(win), raising=False)
    monkeypatch.setattr(launcher, "_close_the_windows_doors", lambda rules: None)
    monkeypatch.setattr(launcher, "_fit_window_to_screen", lambda win: None)
    started = []
    real_start = launcher._start_server

    def start(port, secret):
        started.append(real_start(port, secret))
        return started[-1]

    def never_reached(url, proc, listening, timeout=25.0):
        proc.wait(60)
        return False

    monkeypatch.setattr(launcher, "_start_server", start)
    monkeypatch.setattr(launcher, "_wait_for_server", never_reached)
    stop_signals = types.SimpleNamespace(watch=lambda stop: None, close_with=lambda destroy: None)
    try:
        with pytest.raises(RuntimeError) as failed:
            launcher._run_the_window(stop_signals)
    finally:
        for proc in started:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
    assert destroyed, "the window on its opening page is closed when the server never answers"
    message = str(failed.value)
    shown = message.split("---\n", 1)[1].rsplit("\n-----", 1)[0].split("\n")
    assert f"--- Captured server output, its last {launcher.SERVER_OUTPUT_LINES} lines at most ---" in message
    assert len(shown) == launcher.SERVER_OUTPUT_LINES and shown[-1] == "the last line", message[-500:]
    assert len(message) < launcher.SERVER_OUTPUT_LINES * (launcher.SERVER_OUTPUT_LINE_CHARS + 1) + 1000


# --------------------------------------------------------------------------
# The toolchain the build runs on.

# The architecture of each GitHub image name the build may ask for: a macOS
# image is Apple silicon unless its name says Intel; a Windows image is
# x86-64 unless its name says Arm.
def _architecture(label):
    if label.startswith("macos-"):
        return "x86_64" if label.endswith(("-intel", "-large")) else "aarch64"
    if label.startswith("windows-"):
        return "aarch64" if label.endswith("-arm") else "x86_64"
    return None


def _python_version(text):
    """The one Python version a workflow's text asks setup-python for."""
    found = re.findall(r"(?m)^\s+python-version:\s*(.*?)\s*$", text)
    assert len(found) == 1, found
    return found[0].strip("'\"")


def _toolchain_differences(build_text, other_version=None):
    """Every way the build's toolchain floats, as sentences; given
    `other_version`, the Python another workflow asks for, also where the
    two differ."""
    build = load_yaml(build_text)
    off = []
    labels = [job.get("runs-on") for name, job in build["jobs"].items() if name != "build"]
    for private in (True, False):
        labels += [(runner, private) for runner in _build_runners(build, private)]
    for entry in labels:
        label, private = entry if isinstance(entry, tuple) else (entry, None)
        if not isinstance(label, str) or label.endswith("-latest") or "${{" in label:
            off.append(f"a runner is asked for as {label!r}, a label that moves")
    for private in (True, False):
        for label, (system, (_, platform, _)) in zip(_build_runners(build, private), SYSTEMS.items()):
            if label == "colophon":
                continue
            if _architecture(label) is None or not platform.startswith(_architecture(label) + "-"):
                off.append(f"the {system} leg runs on {label!r}, not an image of the lock's platform {platform}")
    versions = [_python_version(build_text)] + ([] if other_version is None else [other_version])
    for version in versions:
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(version)):
            off.append(f"Python is asked for as {version!r}, not a patch release")
    if len(set(versions)) > 1:
        off.append(f"the build runs Python {versions[0]!r} and the tests {versions[1]!r}")
    return off


def test_no_runner_or_python_floats_and_the_mac_is_the_locks_platform():
    build = WORKFLOW.read_text(encoding="utf-8")
    assert _toolchain_differences(build) == []
    assert list(SYSTEMS) == ["Windows", "macOS"], "the matrix's order"
    assert _python_version(build) == "3.14.8"
    assert f"{sys.version_info[0]}.{sys.version_info[1]}" == "3.14", "the suite runs the minor version pinned"


_BUILD_PLANTS = {
    "windows-latest": ("          - windows-2025-vs2026\n", "          - windows-latest\n"),
    "macos-latest": ("|| 'macos-26' }}", "|| 'macos-latest' }}"),
    "macos-intel": ("|| 'macos-26' }}", "|| 'macos-26-intel' }}"),
    "windows-arm": ("          - windows-2025-vs2026\n", "          - windows-11-arm\n"),
    "release-latest": ("    runs-on: ubuntu-24.04\n", "    runs-on: ubuntu-latest\n"),
    "minor-only": ("python-version: '3.14.8'", "python-version: '3.14'"),
    "the-major-and-minor": ("python-version: '3.14.8'", "python-version: '3'"),
}


@pytest.mark.parametrize("plant", list(_BUILD_PLANTS))
def test_a_toolchain_left_to_float_is_caught(plant):
    old, new = _BUILD_PLANTS[plant]
    build = WORKFLOW.read_text(encoding="utf-8")
    assert build.count(old) == 1, old
    assert _toolchain_differences(build.replace(old, new)) != [], plant


def test_the_comments_say_what_must_hold_before_the_pin_moves():
    build = _prose(WORKFLOW)
    assert ("Before this moves, the project's own Mac must hold the same release in its tool cache (put there by "
            "hand, as said below)") in build
    assert ("Every package installed into the build's environment comes from this system's lock and is checked "
            "against the hashes there") in build
    assert "Everything the build installs" not in build
