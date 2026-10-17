"""The stop check's third launch, when a run does not end: how far it got.

A run that does not end within its bound fails the check with what the
server sent after the run's request: its messages counted by kind (the
session's start, elements, a run's end, any other), their bytes, how long
before the bound the last came, the last elements and messages, and whether
the server still answers its health check. A run that never started (no
message at all, or none the session's start) and one that started and
stalled read differently, in the failure's own line. Each is pinned here
by a stand-in server: in process on a socket pair, by messages Streamlit's
own classes build, and live, by a stand-in for the server entry
(`fixtures/stop_check/stand_in_server.py`) and by the app run from source
whose run never ends. Nothing said carries the check's key.
"""
import socket

import pytest

# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import _module, _outside
from test_stop_check_atlas_2026_10_15 import _finish, _frame, _stand_in_server, _step


def _forward(build):
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    msg = ForwardMsg()
    msg.metadata.delta_path.extend([1, 0, 3])
    build(msg)
    return msg.SerializeToString()


def _start(m):
    m.new_session.SetInParent()


def _box(m):
    m.delta.new_element.text_input.id = "$$ID-ab-location_input_key"
    m.delta.new_element.text_input.label = "City, or latitude, longitude"


def _markdown(m):
    m.delta.new_element.markdown.body = "**not read**"


def _status(m):
    m.session_status_changed.script_is_running = True


def _page(m):
    m.page_config_changed.title = "a title"


def _unended(module, sent, seconds=0.6, tail=b""):
    """A run asked of a stand-in server on a socket pair that sends `sent`
    (whole messages, each a frame) and `tail`, then nothing: the run's
    RunUnfinished."""
    session = module.Session(1)
    ours, theirs = socket.socketpair()
    with ours, theirs:
        session.sock = ours
        theirs.sendall(b"".join(_frame(2, data) for data in sent) + tail)
        with pytest.raises(module.RunUnfinished) as raised:
            session.run(module.rerun_message("launch=" + "K" * 43), seconds)
    elements, heard = raised.value.args
    return elements, heard


def test_the_kind_of_each_message_read_is_streamlits():
    module = _module()

    def selectbox(m):
        m.delta.new_element.selectbox.label = "Select specific location:"
        m.delta.new_element.selectbox.options.extend(["a", "b"])

    def alert(m):
        m.delta.new_element.alert.body = "x"
        m.delta.new_element.alert.format = 3

    def exception(m):
        m.delta.new_element.exception.type = "KeyError"

    def finished(m):
        m.script_finished = 2

    def block(m):
        m.delta.add_block.SetInParent()

    kinds = [module.message_kind(_forward(build)) for build in
             (_start, _box, selectbox, alert, exception, _markdown, finished, _status, _page, block)]
    assert kinds == [
        ("start", "the session's start"),
        ("element", "a text box 'City, or latitude, longitude'"),
        ("element", "a choice 'Select specific location:' of 2 option(s)"),
        ("element", "info alert"),
        ("element", "an exception KeyError"),
        ("element", "an element of another kind (field 29)"),
        ("end", "a run's end (status 2)"),
        ("other", "another message (field 9)"),
        ("other", "another message (field 13)"),
        ("other", "a delta with no new element (field 6)"),
    ]
    # What a message holds besides an element's label is never told: the
    # address the window shows, the key in it, among them.
    key = "Key-Made-For-This-Test_0123456789abcdefABCDEF"

    def page(m):
        m.page_info_changed.query_string = f"launch={key}"

    def body(m):
        m.delta.new_element.alert.body = key

    assert module.message_kind(_forward(page)) == ("other", "another message (field 12)")
    assert module.message_kind(_forward(body)) == ("element", "an alert")


def test_a_run_given_no_message_never_started():
    module = _module()
    elements, heard = _unended(module, [])
    assert elements == []
    assert heard.verdict() == "it never started: no message came after the request"
    notes = heard.notes()
    assert notes[0] == "the run: it never started: no message came after the request"
    assert notes[1] == ("the server's messages after the request: 0 (0 session's start, 0 element(s), 0 run's end, "
                        "0 other), 0 byte(s); none in the 0.6 s after the request; 0 byte(s) read from the session "
                        "in all")
    assert len(notes) == 2


def test_a_run_given_messages_but_no_start_never_started():
    module = _module()
    sent = [_forward(_status), _forward(_page)]
    elements, heard = _unended(module, sent)
    assert heard.verdict() == "it never started: 2 message(s) came after the request, none the session's start"
    notes = heard.notes()
    assert notes[1].startswith(f"the server's messages after the request: 2 (0 session's start, 0 element(s), "
                               f"0 run's end, 2 other), {sum(map(len, sent))} byte(s); the last ")
    assert notes[2:] == ["the last message(s), in order: another message (field 9); another message (field 13)"]


def test_a_run_that_started_and_stalled_says_after_what():
    module = _module()
    sent = [_forward(_status), _forward(_start), _forward(_box), _forward(_markdown)]
    elements, heard = _unended(module, sent, tail=bytes([0x82, 100]) + b"0123456789")
    assert elements == [("text_input", "$$ID-ab-location_input_key", "City, or latitude, longitude")]
    assert heard.verdict().startswith("it started (the session's start ")
    assert heard.verdict().endswith(" s after the request) and stalled after 2 element(s)")
    notes = heard.notes()
    whole = sum(len(data) + 2 for data in sent) + 12
    assert notes[1].startswith("the server's messages after the request: 4 (1 session's start, 2 element(s), "
                               "0 run's end, 1 other), ")
    assert notes[1].endswith(f"; {whole} byte(s) read from the session in all, 12 of them a message not yet whole")
    assert notes[2] == ("the last element(s): a text box 'City, or latitude, longitude'; an element of another kind "
                        "(field 29)")
    assert notes[3] == ("the last message(s), in order: another message (field 9); the session's start; a text box "
                        "'City, or latitude, longitude'; an element of another kind (field 29)")


def test_what_a_stalled_run_says_has_the_key_withheld_before_it_is_cut():
    """A label holding the key, standing across the line's width, is
    withheld whole, never printed in part."""
    module = _module()
    key = "Key-Made-For-This-Test_0123456789abcdefABCDEF"
    module._WITHHELD.insert(0, (key, "<withheld>"))
    try:
        def box(m):
            m.delta.new_element.text_input.label = "x" * 250 + key       # the line's cut falls in the key

        _, heard = _unended(module, [_forward(_start), _forward(box)])
        notes = heard.notes()
    finally:
        module._WITHHELD.remove((key, "<withheld>"))
    assert len(notes) == 4, notes
    assert [line for line in notes if key[:6] in line] == [], notes
    assert notes[2] == "the last element(s): a text box '" + "x" * 250 + "<withheld>'"
    assert [len(line) for line in notes if len(line) > module.LINE_CHARS] == []
    assert len(notes[3]) == module.LINE_CHARS, "the last messages' line is cut, the key past its end"


# --------------------------------------------------------------------------
# Live, the step alone, against a stand-in for the server entry.

def test_live_a_server_that_opens_the_session_and_sends_nothing_never_started(tmp_path, monkeypatch, capsys):
    module, check, short = _step(tmp_path, monkeypatch, _stand_in_server(tmp_path, "silent", monkeypatch))
    check.args.run_seconds = 3
    out, failure = _finish(module, check, short, capsys)
    assert failure == "launch 3: the first run did not end within 3 s: it never started: no message came after " \
                      "the request", out
    assert "  the run: it never started: no message came after the request" in out
    assert ("  the server's messages after the request: 0 (0 session's start, 0 element(s), 0 run's end, 0 other), "
            "0 byte(s); none in the 3 s after the request; 0 byte(s) read from the session in all") in out
    assert "  the server still answered its health check after the bound" in out
    assert "launch=" not in out


def test_live_a_server_whose_run_starts_and_stalls_says_so(tmp_path, monkeypatch, capsys):
    module, check, short = _step(tmp_path, monkeypatch, _stand_in_server(tmp_path, "stalls", monkeypatch))
    check.args.run_seconds = 3
    out, failure = _finish(module, check, short, capsys)
    assert failure.startswith("launch 3: the first run did not end within 3 s: it started (the session's start "), out
    assert failure.endswith(" s after the request) and stalled after 2 element(s)"), out
    assert ("  the last element(s): a text box 'City, or latitude, longitude'; an element of another kind (field 29)"
            in out)
    assert "  the server still answered its health check after the bound" in out

