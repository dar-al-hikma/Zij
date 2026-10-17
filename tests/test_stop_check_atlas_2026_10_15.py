"""The stop check's third launch: a place typed in the download's city search.

After its two stops, `.github/scripts/stop_check.py` starts the download's own
server entry as the launcher starts its child (the sentinel and a port after
the executable, no STREAMLIT_* variable, a key of the check's own in the
environment), opens a session as the window opens one, asks the first run
with the key in its address, types a place in the city search -- spelt so
that only the search's second, folded look finds it -- and requires the
place's label among the choices the run offers. It then stops the server by
the end of its input, and no process of that launch may remain.

Here: the step's names are the launcher's and the app's; the place typed is
found by the folded look alone and its label is unique; the protocol buffers
the step writes and reads are Streamlit's, by Streamlit's own classes, fixed-
width fields skipped whole; the WebSocket frames it reads; what a failure says
of a run, each sentence on one line and scrubbed before it is cut; and, live
against the app run from source on a copy of this checkout, the whole check
passing, and failing by name without the atlas, with an atlas that lacks the
place, with a key the server does not hold, against a server whose run never
ends, with another program on the port, and with an app that shows its key
past the width printed; and, against a stand-in server entry, failing when
it says it listens on a port another program holds and when it never says
it listens. The key is never printed, and the step stands where it does in
the check's run.
"""
import ast
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading

import pytest

from conftest import EXECUTABLE_DIR
# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import (LAUNCHER, LOADS_ITS_PAGE, NO_WAY_OUT, SCRIPT, STAND_IN_WEBVIEW, _module,
                                        _outside)

APP = EXECUTABLE_DIR / "app.py"
ATLAS = EXECUTABLE_DIR / "atlas.db"
# What the copies leave out: the repository's own records and tools, which
# no download carries.
_NOT_COPIED = {".git", "tests", "tools", "docs", "__pycache__"}


# --------------------------------------------------------------------------
# The step's names are the launcher's and the app's.

def _assigned(path):
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant):
            found[node.targets[0].id] = node.value.value
    return found


def _calls(path, name):
    """Every call of a method `name` in the file at `path`."""
    return [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name]


def test_the_steps_names_are_the_launchers_and_the_apps():
    module, launcher, app = _module(), _assigned(LAUNCHER), _assigned(APP)
    assert module.SERVER_SENTINEL == launcher["_SERVER_SENTINEL"]
    assert module.LISTENING_MARK == launcher["SERVER_LISTENING_MARK"]
    assert module.LAUNCH_KEY_VARIABLE == launcher["LAUNCH_KEY_VARIABLE"] == app["_LAUNCH_KEY_VARIABLE"]
    assert module.LAUNCH_KEY_PARAMETER == launcher["LAUNCH_KEY_PARAMETER"] == app["_LAUNCH_KEY_PARAMETER"]
    assert module.LAUNCH_KEY_REFUSAL == app["_LAUNCH_KEY_REFUSAL"], "the sentence a session without the key is told"
    keys = [kw.value.value for call in _calls(APP, "text_input") for kw in call.keywords
            if kw.arg == "key" and isinstance(kw.value, ast.Constant)]
    assert keys.count(module.CITY_SEARCH_KEY) == 1, "the city search is the one text box with that key"
    labels = [call.args[0].value for call in _calls(APP, "selectbox")
              if call.args and isinstance(call.args[0], ast.Constant)]
    assert labels.count(module.PLACE_CHOICE_LABEL) == 1, "the choice of place under the search box"
    assert module.RUN_SECONDS >= module.REACH_SECONDS
    assert module.parse_args([]).run_seconds == module.RUN_SECONDS


def test_the_widget_id_is_never_written_in_the_script():
    """The city search's widget id is read from the first run: the script
    names the app's key, never an id Streamlit makes from it."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "$$ID" not in source and "$$WIDGET" not in source


# --------------------------------------------------------------------------
# The place typed.

def _labels(rows):
    """Labels as app.py's _atlas_matches makes them, for the rows here."""
    return [f"{name}, {region.strip()} ({country})" if (region or "").strip() else f"{name} ({country})"
            for name, region, country, _, _ in rows]


def test_the_place_typed_is_found_only_by_the_folded_look_and_its_label_is_unique(monkeypatch):
    import time_zones

    module = _module()
    typed = module.PLACE_TYPED
    assert not typed.isascii() and typed == typed.strip()
    rows = time_zones.atlas_rows(ATLAS, typed)
    labels = _labels(rows)
    assert labels.count(module.PLACE_FOUND) == 1, labels
    assert labels[0] == module.PLACE_FOUND, "the most populous place of the name"
    assert len(set(labels)) == len(labels), "no label is given a coordinate suffix among these options"
    name = rows[0][0]
    assert name != typed and time_zones._atlas_fold(name) == typed, "typed in the other case"
    # Without the fold the search has only its first look, and the text
    # typed finds nothing there.
    monkeypatch.setattr(time_zones, "_atlas_fold", lambda text: text)
    assert time_zones.atlas_rows(ATLAS, typed) == []


# --------------------------------------------------------------------------
# The protocol buffers, against Streamlit's own classes.

def test_the_rerun_messages_written_are_streamlits():
    from streamlit.proto.BackMsg_pb2 import BackMsg

    module = _module()
    cases = [("launch=" + "K" * 43, []),
             ("", [("$$ID-0123abcd-location_input_key", "évora")]),
             ("a=1&b=2", [("first", ""), ("second", "x" * 300), ("é", "İstanbul")])]
    assert len(cases) == 3
    for query, widgets in cases:
        written = module.rerun_message(query, widgets)
        expected = BackMsg()
        expected.rerun_script.query_string = query
        expected.rerun_script.widget_states.SetInParent()
        for wid, text in widgets:
            state = expected.rerun_script.widget_states.widgets.add()
            state.id, state.string_value = wid, text
        assert written == expected.SerializeToString(), (query, widgets)
        parsed = BackMsg.FromString(written)
        assert parsed.WhichOneof("type") == "rerun_script"
        assert parsed.rerun_script.query_string == query
        assert [(w.id, w.WhichOneof("value"), w.string_value) for w in parsed.rerun_script.widget_states.widgets] \
            == [(wid, "string_value", text) for wid, text in widgets]


def test_the_server_messages_read_are_streamlits():
    from streamlit.proto.Alert_pb2 import Alert
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    module = _module()
    assert (module.FINISHED, module.FINISHED_WITH_COMPILE_ERROR) == (
        ForwardMsg.FINISHED_SUCCESSFULLY, ForwardMsg.FINISHED_WITH_COMPILE_ERROR)
    assert module._ALERT_KINDS == {Alert.ERROR: "error", Alert.WARNING: "warning", Alert.INFO: "info",
                                   Alert.SUCCESS: "success"}
    seen = []

    def message(build):
        msg = ForwardMsg()
        msg.metadata.delta_path.extend([1, 0, 3])
        build(msg)
        seen.append(module.read_forward(msg.SerializeToString()))

    message(lambda m: m.new_session.SetInParent())
    for status in (ForwardMsg.FINISHED_SUCCESSFULLY, ForwardMsg.FINISHED_WITH_COMPILE_ERROR,
                   ForwardMsg.FINISHED_EARLY_FOR_RERUN):
        message(lambda m, status=status: setattr(m, "script_finished", status))

    def text_input(m):
        element = m.delta.new_element.text_input
        element.id, element.label, element.default, element.max_chars = "$$ID-ab-location_input_key", "City", "x", 9

    def selectbox(m):
        element = m.delta.new_element.selectbox
        element.id, element.label, element.default = "$$ID-cd-None", "Select specific location:", 0
        element.options.extend(["Évora, 08 (PT)", "Évora, 13 (PT)", "y" * 200])

    def alert(kind):
        def build(m):
            m.delta.new_element.alert.body = "The offline place atlas is missing é"
            m.delta.new_element.alert.format = kind
        return build

    def exception(m):
        m.delta.new_element.exception.type = "KeyError"
        m.delta.new_element.exception.message = "'x'"
        m.delta.new_element.exception.stack_trace.extend(["a", "b"])

    message(text_input)
    message(selectbox)
    for kind in (Alert.ERROR, Alert.WARNING, Alert.INFO):
        message(alert(kind))
    message(exception)
    message(lambda m: setattr(m.delta.new_element.markdown, "body", "**not read**"))
    message(lambda m: setattr(m.page_info_changed, "query_string", "launch=hidden"))
    message(lambda m: setattr(m.session_status_changed, "script_is_running", True))
    assert seen == [
        ("new_session",), ("finished", 0), ("finished", 1), ("finished", 2),
        ("element", ("text_input", "$$ID-ab-location_input_key", "City")),
        ("element", ("selectbox", "$$ID-cd-None", "Select specific location:",
                     ["Évora, 08 (PT)", "Évora, 13 (PT)", "y" * 200])),
        ("element", ("alert", 1, "The offline place atlas is missing é")),
        ("element", ("alert", 2, "The offline place atlas is missing é")),
        ("element", ("alert", 3, "The offline place atlas is missing é")),
        ("element", ("exception", "KeyError", "'x'")),
        None, None, None,
    ]


def test_fixed_width_fields_are_skipped_whole():
    """A double (eight bytes) and a float (four), each skipped whole: the
    fields after them are read as Streamlit wrote them."""
    from streamlit.proto.AutoRerun_pb2 import AutoRerun
    from streamlit.proto.NumberInput_pb2 import NumberInput

    module = _module()
    number = NumberInput(id="$$ID-n", label="Degrees", format="%.4f", has_min=True, has_max=True, default=1.5,
                         step=0.25, min=-90.0, max=90.0, help="help", value=12.75, set_value=True, placeholder="p")
    assert module._fields(number.SerializeToString()) == [
        (1, b"$$ID-n"), (2, b"Degrees"), (8, b"%.4f"), (11, 1), (12, 1), (18, b"help"), (20, 1), (23, b"p")]
    rerun = AutoRerun(interval=2.5, fragment_id="fragment")
    assert module._fields(rerun.SerializeToString()) == [(2, b"fragment")]


def test_a_message_cut_short_is_refused_not_misread():
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    module = _module()
    msg = ForwardMsg()
    msg.delta.new_element.selectbox.options.extend(["a" * 50])
    data = msg.SerializeToString()
    for cut in (len(data) - 1, len(data) - 20):
        with pytest.raises(ValueError):
            module.read_forward(data[:cut])


def test_each_sentence_of_a_run_is_one_line():
    """An alert whose body holds a line break (the app's own, "**Exact LMT**
    ...  \\nUT ...") prints on one line, its white space folded."""
    module = _module()
    elements = [("alert", 3, "**Exact LMT** 12:00  \nUT 11:40\t(x)"), ("exception", "KeyError", "a\r\nb")]
    assert module.sentences(elements) == ["info: **Exact LMT** 12:00 UT 11:40 (x)", "exception KeyError: a b"]
    notes = module._run_notes(elements)
    assert len(notes) == 4 and [line for line in notes if "\n" in line] == [], notes


def test_a_key_standing_across_a_cut_is_withheld_whole():
    """The details are scrubbed before they are cut: a key whose start
    stands before a cut and its end after is never printed in part."""
    module = _module()
    key = "Key-Made-For-This-Test_0123456789abcdefABCDEF"
    module._WITHHELD.insert(0, (key, "<withheld>"))
    try:
        said = module.sentences([("alert", 1, "x" * 270 + key)])
        offered = module.options_text(["y" * 70 + key])
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "out.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("z" * 280 + key + "\n")
            tail = module._tail(path)
        finally:
            shutil.rmtree(folder)
    finally:
        module._WITHHELD.remove((key, "<withheld>"))
    for text in (*said, offered, *tail):
        assert key[:6] not in text, text
    assert said == ["error: " + "x" * 270 + "<withheld>"]
    assert tail == ["z" * 280 + "<withheld>"]


# --------------------------------------------------------------------------
# The frames the session reads.

def _frame(opcode, payload, fin=True, masked=False):
    head = bytes([(0x80 if fin else 0) | opcode])
    size = len(payload)
    mask_bit = 0x80 if masked else 0
    if size < 126:
        head += bytes([mask_bit | size])
    elif size < 65536:
        head += bytes([mask_bit | 126]) + size.to_bytes(2, "big")
    else:
        head += bytes([mask_bit | 127]) + size.to_bytes(8, "big")
    if masked:
        mask = b"\x01\x02\x03\x04"
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        head += mask
    return head + payload


def _unmask(data):
    """The frames a client sent, as (opcode, payload)."""
    out = []
    while data:
        opcode, size = data[0] & 0x0F, data[1] & 0x7F
        at = 2
        if size == 126:
            size, at = int.from_bytes(data[2:4], "big"), 4
        elif size == 127:
            size, at = int.from_bytes(data[2:10], "big"), 10
        assert data[1] & 0x80, "a client's frame is masked"
        mask = data[at:at + 4]
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(data[at + 4:at + 4 + size]))
        out.append((opcode, payload))
        data = data[at + 4 + size:]
    return out


def test_the_session_reads_fragmented_long_and_pinged_messages_and_answers_a_ping():
    module = _module()
    session = module.Session(1)
    ours, theirs = socket.socketpair()
    with ours, theirs:
        session.sock = ours
        big = bytes(range(256)) * 300
        theirs.sendall(_frame(9, b"ping!") + _frame(2, b"ab", fin=False) + _frame(0, b"cd" * 100, fin=False)
                       + _frame(0, b"ef") + _frame(2, big) + _frame(2, b"m", masked=True) + _frame(8, b"\x03\xe8"))
        deadline = module.time.monotonic() + 10
        assert session.receive(deadline) == b"ab" + b"cd" * 100 + b"ef"
        assert session.receive(deadline) == big
        assert session.receive(deadline) == b"m"
        with pytest.raises(module.CheckFailed, match=r"closed the session \(code 1000\)"):
            session.receive(deadline)
        session.send(b"\x00" * 70000)
        theirs.settimeout(5)
        got = b""
        while len(got) < 6 + 4 + 10 + 4 + 70000:
            got += theirs.recv(1 << 20)
        assert _unmask(got) == [(10, b"ping!"), (2, b"\x00" * 70000)]


def test_a_session_given_nothing_by_its_bound_says_its_run_did_not_end():
    module = _module()
    session = module.Session(1)
    ours, theirs = socket.socketpair()
    with ours, theirs:
        session.sock = ours
        with pytest.raises(module.RunUnfinished):
            session.run(module.rerun_message("q"), 0.5)


# --------------------------------------------------------------------------
# Live: the app from source, on a copy of this checkout.

def _copy(tmp_path, atlas="whole", app=None):
    """A copy of this checkout's program: each file a link to this
    checkout's, but the atlas (`whole`: a link; `missing`; `without the
    place`: a copy with the pinned label's place deleted) and, given
    `app`, the app's script."""
    folder = tmp_path / "program"
    folder.mkdir()
    for entry in EXECUTABLE_DIR.iterdir():
        if entry.name in _NOT_COPIED or entry.name == "atlas.db" or (app is not None and entry.name == "app.py"):
            continue
        (folder / entry.name).symlink_to(entry)
    if atlas == "whole":
        (folder / "atlas.db").symlink_to(ATLAS)
    elif atlas == "without the place":
        shutil.copyfile(ATLAS, folder / "atlas.db")
        name, _, rest = _module().PLACE_FOUND.partition(", ")
        region, country = rest[:-1].split(" (")
        with sqlite3.connect(folder / "atlas.db") as conn:
            gone = conn.execute("DELETE FROM cities WHERE name = ? AND admin1 = ? AND country = ?",
                                (name, region, country)).rowcount
        assert gone == 1
    else:
        assert atlas == "missing"
    if app is not None:
        (folder / "app.py").write_text(app, encoding="utf-8")
    return folder


def _environment(short):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.pop("ZIJ_LAUNCH_KEY", None)
    env.update(PYTHONPATH=str(STAND_IN_WEBVIEW), TMPDIR=short, **NO_WAY_OUT, **LOADS_ITS_PAGE)
    return env


def _run_check(tmp_path, program, *extra):
    """The whole check, run as the runner runs it but on a command: the
    copy's launcher run from source, its window a stand-in."""
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    short = tempfile.mkdtemp(dir="/tmp")
    try:
        argv = [sys.executable, str(SCRIPT), "--work", str(work), "--reach-seconds", "120", "--stop-seconds", "15",
                "--orphan-seconds", "10", "--margin-seconds", "10", *extra, "--stand-in-windows", str(windows),
                "--command", sys.executable, str(program / "desktop_launcher.py")]
        done = subprocess.run(argv, capture_output=True, text=True, env=_environment(short), timeout=600)
    finally:
        shutil.rmtree(short, ignore_errors=True)
    assert done.stderr == "", done.stderr
    assert str(tmp_path) not in done.stdout and str(work) not in done.stdout
    assert os.listdir(work) == [], "the check leaves nothing in its working folder"
    return done.returncode, done.stdout


def _third(out):
    return [line for line in out.splitlines() if line.startswith("launch 3: ")]


def _failure_and_details(out):
    lines = out.splitlines()
    at = [i for i, line in enumerate(lines) if line.startswith("stop check FAILED: ")]
    assert len(at) == 1, out
    return lines[at[0]], "\n".join(lines[at[0] + 1:])


def test_the_whole_check_passes_on_a_copy_of_the_checkout(tmp_path):
    module = _module()
    code, out = _run_check(tmp_path, _copy(tmp_path))
    assert code == 0, out
    third = _third(out)
    assert len(third) == 8, out
    assert third[0].startswith("launch 3: started: the command's server entry run with a fresh home and data "
                               "folder, on 127.0.0.1:"), out
    assert ("with a key of this check's own, its input a pipe only this check holds and its output a pipe it reads "
            "as it comes, as the launcher gives them; server ") in third[0], out
    assert third[1].startswith("launch 3: reached after ") and "the server said it was listening, holds" in third[1]
    assert third[2] == ("launch 3: a WebSocket opening under a rebound Host was refused (403), one under the window's "
                        "own address from another site's Origin was refused (403), and one under the window's own "
                        "address opened (101)"), out
    assert "a session opened as the window opens one (its own Host and Origin, the XSRF cookie and token)" in third[3]
    assert "the city search, holding the example's city, offered " in third[3] and "'Florence, " in third[3]
    assert third[4].startswith(f"launch 3: with {module.PLACE_TYPED!r} typed in the city search, the run ended after ")
    assert f"offered {module.PLACE_FOUND!r} among its 3 option(s): " in third[4], out
    assert third[5].startswith(f"launch 3: the example chart's wheel puts {module.KNOWN_POINT} at "), out
    assert third[6] == ("launch 3: while that session was open, one opened as the window opens one but with no key in "
                        "its address, and one with a key one letter off the launch's, were each told only "
                        f"{module.LAUNCH_KEY_REFUSAL!r}: the first run of each showed that sentence and nothing "
                        "else"), out
    assert third[7].startswith("launch 3: stopped as the launcher stops it, by the end of its input; after "), out
    assert "no process of this launch remains (1 seen" in third[7] and "(bound 10 s + 10 s margin); server exit 0" \
        in third[7], out
    assert out.splitlines()[-1].endswith("and its server, started on its own, offered the place typed in its city "
                                         "search")


def test_without_the_atlas_the_check_fails_saying_the_atlas_is_missing(tmp_path):
    module = _module()
    missing = _assigned(APP)["ATLAS_MISSING_MESSAGE"]
    code, out = _run_check(tmp_path, _copy(tmp_path, atlas="missing"))
    assert code == 1
    failure, details = _failure_and_details(out)
    assert failure == (f"stop check FAILED: launch 3: with {module.PLACE_TYPED!r} typed in the city search, the run "
                       f"offered no choice of place, not {module.PLACE_FOUND!r} once among them"), out
    assert f"  | error: {missing}" in details, out
    assert "the run's choice of place: no choice of place" in details
    assert "offered no choice of place" in _third(out)[3], "the example's city found nothing either"
    assert "launch 2: ended the launcher" in out, "the first two launches held"


def test_with_an_atlas_that_lacks_the_place_the_check_fails_naming_what_was_offered(tmp_path):
    module = _module()
    code, out = _run_check(tmp_path, _copy(tmp_path, atlas="without the place"))
    assert code == 1
    failure, details = _failure_and_details(out)
    assert failure == (f"stop check FAILED: launch 3: with {module.PLACE_TYPED!r} typed in the city search, the run "
                       f"offered 2 option(s): 'Évora, 13 (PT)', 'Évora Monte, 08 (PT)', not "
                       f"{module.PLACE_FOUND!r} once among them"), out
    assert "the run's choice of place: 2 option(s): " in details


_NEVER_ENDS = '''import time

import streamlit as st

st.sidebar.text_input("City, or latitude, longitude", key="location_input_key")
# A file handed to the page, as the app's own first run hands its window
# some: the window's session is seen to be let in before the run stalls.
st.download_button("Save", b"x")
while True:
    time.sleep(0.2)
'''


def test_against_a_server_whose_run_never_ends_the_check_fails_by_its_bound(tmp_path):
    code, out = _run_check(tmp_path, _copy(tmp_path, app=_NEVER_ENDS), "--run-seconds", "5")
    assert code == 1
    failure, details = _failure_and_details(out)
    assert failure.startswith("stop check FAILED: launch 3: the first run did not end within 5 s: it started (the "
                              "session's start "), out
    assert failure.endswith(" s after the request) and stalled after 2 element(s)"), out
    assert ("  the last element(s): a text box 'City, or latitude, longitude'; an element of another kind (field "
            "43") in details, details
    assert "  the server still answered its health check after the bound" in details
    assert "the run said nothing in an alert or an exception" in details
    assert "the server's output" in details and "processes of this launch seen" in details


_SHOWS_ITS_KEY = '''import os

import streamlit as st

key = os.environ["ZIJ_LAUNCH_KEY"]
print("z" * 280 + key, flush=True)
st.error("x" * 270 + key)
st.sidebar.text_input("City, or latitude, longitude", key="location_input_key")
st.selectbox("Select specific location:", ["y" * 70 + key])
'''


# In-process runs of the step alone, so that what it is given can be watched.

def _step(tmp_path, monkeypatch, program):
    module = _module()
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    short = tempfile.mkdtemp(dir="/tmp")
    monkeypatch.setenv("PYTHONPATH", str(STAND_IN_WEBVIEW))
    monkeypatch.setenv("TMPDIR", short)
    monkeypatch.setenv("STREAMLIT_SERVER_PORT", "1")
    monkeypatch.delenv("ZIJ_LAUNCH_KEY", raising=False)
    for name, value in NO_WAY_OUT.items():
        monkeypatch.setenv(name, value)
    check = module.Check(module.parse_args(["--work", str(work), "--stand-in-windows", str(windows), "--command",
                                            sys.executable, str(program / "desktop_launcher.py")]))
    check.work, check.current = tempfile.mkdtemp(dir=work), None
    return module, check, short


def _finish(module, check, short, capsys):
    """The step run; its printed lines, a failure's line and what the
    outside saw (None on a pass), as main prints them."""
    failure = None
    try:
        check.typed_place()
    except module.CheckFailed as error:
        module.say(f"stop check FAILED: {error}")
        for line in check.explain(check.current):
            module.say(f"  {line}")
        failure = str(error)
    finally:
        if check.current is not None and failure is not None:
            check.current.end_everything()
        shutil.rmtree(check.work, ignore_errors=True)
        shutil.rmtree(short, ignore_errors=True)
    return capsys.readouterr().out, failure


def test_the_key_goes_to_the_server_alone_and_the_widget_id_is_the_servers(tmp_path, monkeypatch, capsys):
    module, check, short = _step(tmp_path, monkeypatch, _copy(tmp_path))
    key = "Key-Made-For-This-Test_0123456789abcdefABCDEF"
    monkeypatch.setattr(module, "secrets", type("Secrets", (), {"token_urlsafe": staticmethod(lambda n: key)}))
    started, sent, ids = [], [], []
    real_popen, real_run, real_message = subprocess.Popen, module.Session.run, module.rerun_message

    def popen(argv, **kwargs):
        started.append((list(argv), dict(kwargs.get("env") or {})))
        return real_popen(argv, **kwargs)

    def run(session, message, seconds):
        status, elements, took = real_run(session, message, seconds)
        ids.append({e[1] for e in elements if e[0] == "text_input"})
        return status, elements, took

    def rerun(query, widgets=()):
        sent.append((query, list(widgets)))
        return real_message(query, widgets)

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.Session, "run", run)
    monkeypatch.setattr(module, "rerun_message", rerun)
    out, failure = _finish(module, check, short, capsys)
    assert failure is None, out
    [(argv, env)] = started
    assert argv[-2] == module.SERVER_SENTINEL and argv[-1].isdigit() and key not in " ".join(argv)
    assert env[module.LAUNCH_KEY_VARIABLE] == key
    assert not [name for name in env if name.upper().startswith("STREAMLIT_")], "the launcher gives its child none"
    assert len(sent) == 4, sent
    assert sent[0] == (f"{module.LAUNCH_KEY_PARAMETER}={key}", [])
    assert sent[1][0] == "", "the window's address no longer carries the key once the session is let in"
    [(widget, text)] = sent[1][1]
    assert text == module.PLACE_TYPED
    assert widget in ids[0] and widget.endswith("-" + module.CITY_SEARCH_KEY), "the id the first run gave"
    # Then two sessions the server must refuse: no key, and a key one letter off.
    assert sent[2] == ("", []) and sent[3] == (f"{module.LAUNCH_KEY_PARAMETER}={key[:-1]}A", []), sent[2:]
    assert ids[2] == ids[3] == set(), "a refused session is shown no text box"
    assert key not in out and "launch=" not in out
    assert module.scrub(f"a line holding {key}.") == "a line holding <withheld>."


def test_a_key_the_server_does_not_hold_fails_the_check_and_neither_key_is_printed(tmp_path, monkeypatch, capsys):
    module, check, short = _step(tmp_path, monkeypatch, _copy(tmp_path))
    key, held = "Key-The-Check-Sends_0123456789abcdefABCDEFGH", "Key-The-Server-Holds_0123456789abcdefABCDEF"
    monkeypatch.setattr(module, "secrets", type("Secrets", (), {"token_urlsafe": staticmethod(lambda n: key)}))
    real = module._server_environment
    monkeypatch.setattr(module, "_server_environment", lambda environment, _key: real(environment, held))
    out, failure = _finish(module, check, short, capsys)
    assert failure == ("launch 3: the first run was refused: the server told the session that the app can be used "
                       "only in its own window, so the key this check gave it was not accepted; the check failed, "
                       "it did not pass"), out
    assert f"  | info: {module.LAUNCH_KEY_REFUSAL}" in out
    assert key not in out and held not in out


def test_an_app_that_shows_its_key_across_a_cut_has_it_withheld_whole(tmp_path, monkeypatch, capsys):
    """An app that shows the key it was given past the width a failure
    prints (in an alert, a choice of place and its output) has it withheld
    whole: what is withheld does not rest on what the app shows."""
    module, check, short = _step(tmp_path, monkeypatch, _copy(tmp_path, app=_SHOWS_ITS_KEY))
    key = "Key-Made-For-This-Test_0123456789abcdefABCDEF"
    monkeypatch.setattr(module, "secrets", type("Secrets", (), {"token_urlsafe": staticmethod(lambda n: key)}))
    out, failure = _finish(module, check, short, capsys)
    assert failure is not None and failure.startswith(f"launch 3: with {module.PLACE_TYPED!r} typed in the city "
                                                      f"search, the run offered 1 option(s): "), out
    assert "  | error: " + "x" * 270 + "<withheld>" in out
    assert "'" + "y" * 70 + "<withheld>'" in out
    assert "    | " + "z" * 280 + "<withheld>" in out
    assert key[:6] not in out, out


class _Impostor:
    """A program outside the launch holding a port of 127.0.0.1 and
    answering Streamlit's health check there; `asked` what it was asked."""

    def __init__(self):
        import http.server

        asked = self.asked = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                asked.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _stand_in_server(tmp_path, mode, monkeypatch):
    folder = tmp_path / "program"
    folder.mkdir()
    shutil.copyfile(EXECUTABLE_DIR / "tests" / "fixtures" / "stop_check" / "stand_in_server.py",
                    folder / "desktop_launcher.py")
    monkeypatch.setenv("STAND_IN_SERVER_MODE", mode)
    return folder


def test_a_server_that_says_it_listens_on_a_port_another_program_holds_is_not_reached(tmp_path, monkeypatch, capsys):
    """The server entry writes the listening mark for its port and never
    listens, while a program outside the launch answers the health check
    on that port: the check fails, saying no process of this launch holds
    the port, and asks the program nothing."""
    impostor = _Impostor()
    try:
        module, check, short = _step(tmp_path, monkeypatch, _stand_in_server(tmp_path, "liar", monkeypatch))
        monkeypatch.setattr(module, "_free_port", lambda: impostor.port)
        check.args.reach_seconds = 4
        out, failure = _finish(module, check, short, capsys)
    finally:
        impostor.close()
    assert failure == (f"launch 3: the server was not reached on 127.0.0.1:{impostor.port} within 4 s: no process "
                       f"of this launch holds port {impostor.port}"), out
    assert impostor.asked == [], f"the program on the port was asked for {impostor.asked}"


def test_a_server_that_listens_but_never_says_so_is_not_reached(tmp_path, monkeypatch, capsys):
    """The server entry listens and answers, but never writes the listening
    mark: the check fails, saying it never said it was listening."""
    module, check, short = _step(tmp_path, monkeypatch, _stand_in_server(tmp_path, "mute", monkeypatch))
    check.args.reach_seconds = check.args.run_seconds = 4
    out, failure = _finish(module, check, short, capsys)
    assert failure is not None and failure.startswith("launch 3: the server was not reached on 127.0.0.1:"), out
    assert failure.endswith(" within 4 s: it never said it was listening"), out


def test_another_program_answering_on_the_port_is_not_taken_for_the_server(tmp_path, monkeypatch, capsys):
    """A program that holds the port first, and answers Streamlit's health
    check there, is never asked for a session: the server, which cannot
    bind the port, has not said it listens, and holds no port."""
    impostor = _Impostor()
    try:
        module, check, short = _step(tmp_path, monkeypatch, _copy(tmp_path))
        monkeypatch.setattr(module, "_free_port", lambda: impostor.port)
        check.args.reach_seconds = 60
        out, failure = _finish(module, check, short, capsys)
    finally:
        impostor.close()
    assert failure is not None and failure.startswith("launch 3: the server "), out
    assert ("before it answered" in failure or "it never said it was listening" in failure), failure
    assert impostor.asked == [], f"the program on the port was asked for {impostor.asked}"


# --------------------------------------------------------------------------
# Where the step stands.

def test_the_step_runs_after_both_stops_on_every_system_and_returns_only_at_its_end():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    [check] = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Check"]
    [run] = [node for node in check.body if isinstance(node, ast.FunctionDef) and node.name == "run"]
    [attempt] = [node for node in run.body if isinstance(node, ast.Try)]
    assert [ast.unparse(statement) for statement in attempt.body] == [
        "self.ordinary_stop()", "self.current = None", "self.launcher_alone_ended()", "self.current = None",
        "self.typed_place()", "self.current = None"]
    [step] = [node for node in check.body if isinstance(node, ast.FunctionDef) and node.name == "typed_place"]
    assert not [node for node in ast.walk(step) if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom))], \
        "the step has no way out but its end or a failure"
    body = [ast.unparse(statement) for statement in step.body]
    assert body.index("self._reach_the_server(launch, port, output)") < body.index("session = Session(port)")
