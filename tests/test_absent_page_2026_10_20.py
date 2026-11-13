"""A page pin cannot pass on a page that never ran.

When app.py does not compile, AppTest logs a record, renders nothing and
leaves at.exception empty; when it raises at import, the page holds that
one exception and nothing else. A pin that asserts only that some text is
absent passed on either. The harness now fails every AppTest run that did
not reach the page, and says why: the app did not compile, it raised before
it rendered anything, or it rendered nothing. A raised exception on a page
that did render is still assert_no_exception's to report, as before.
"""
import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import conftest
from conftest import (APP_PATH, COMPILE_ERROR_LOGGER, assert_no_exception, make_app, page_not_reached)

ABSENT = "this is not python"
NOT_REACHED = "app.py: the run did not reach the page: "
BREAKS = {
    "compile": ("{app}\nthis is not python (\n", "the app did not compile: SyntaxError"),
    "import": ("import zij_no_such_module\n{app}", "the app raised before it rendered anything\n"),
}


def _texts(at):
    """Every string the run rendered, main and sidebar."""
    return "\n".join(str(getattr(node, "value", "")) for block in (at.main, at.sidebar) for node in block)


def absence_pin():
    """A pin that asserts only that some text is absent from the page."""
    at = make_app().run()
    assert ABSENT not in _texts(at)


def _broken_app(tmp_path, kind):
    path = tmp_path / kind / "app.py"
    path.parent.mkdir()
    path.write_text(BREAKS[kind][0].format(app=APP_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    return path


def _script(tmp_path, text):
    path = tmp_path / "app.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_normal_page_run_reaches_the_page_and_the_absence_pin_passes():
    at = make_app().run()
    assert page_not_reached(at) is None
    assert_no_exception(at, "the default page")
    absence_pin()


@pytest.mark.parametrize("kind", sorted(BREAKS))
def test_the_harness_run_fails_on_an_app_that_never_reached_the_page(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(conftest, "APP_PATH", _broken_app(tmp_path, kind))
    with pytest.raises(pytest.fail.Exception) as failed:
        make_app().run()
    assert str(failed.value).startswith(NOT_REACHED + BREAKS[kind][1]), str(failed.value)


@pytest.mark.parametrize("kind", sorted(BREAKS))
def test_an_absence_only_pin_fails_on_an_app_that_never_reached_the_page(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(conftest, "APP_PATH", _broken_app(tmp_path, kind))
    with pytest.raises(pytest.fail.Exception) as failed:
        absence_pin()
    assert str(failed.value).startswith(NOT_REACHED + BREAKS[kind][1]), str(failed.value)


@pytest.mark.parametrize("kind", sorted(BREAKS))
def test_a_run_made_without_the_harness_helper_is_checked_too(tmp_path, kind):
    """Most page tests build their AppTest themselves."""
    app = _broken_app(tmp_path, kind)
    with pytest.raises(pytest.fail.Exception) as failed:
        AppTest.from_file(str(app), default_timeout=60).run()
    assert str(failed.value).startswith(NOT_REACHED + BREAKS[kind][1]), str(failed.value)


def test_a_widgets_rerun_of_a_page_that_stopped_compiling_fails(tmp_path):
    """A click reruns the script through the element tree, not AppTest.run."""
    app = _script(tmp_path, "import streamlit as st\nst.button('Go')\n")
    at = AppTest.from_file(str(app), default_timeout=60).run()
    assert [b.label for b in at.button] == ["Go"]
    app.write_text("import streamlit as st\nst.button('Go'\n", encoding="utf-8")
    with pytest.raises(pytest.fail.Exception) as failed:
        at.button[0].click().run()
    assert str(failed.value).startswith(NOT_REACHED + "the app did not compile: SyntaxError"), str(failed.value)


def test_a_run_that_rendered_nothing_fails(tmp_path):
    app = _script(tmp_path, "import streamlit as st\nst.stop()\n")
    with pytest.raises(pytest.fail.Exception) as failed:
        AppTest.from_file(str(app), default_timeout=60).run()
    assert str(failed.value) == NOT_REACHED + "the app rendered nothing"


def test_a_compile_error_still_fails_if_streamlit_stops_logging_it(tmp_path, monkeypatch):
    """The empty page that follows fails as one."""
    monkeypatch.setattr(conftest, "COMPILE_ERROR_RECORD", "a record Streamlit no longer logs")
    app = _broken_app(tmp_path, "compile")
    with pytest.raises(pytest.fail.Exception) as failed:
        AppTest.from_file(str(app), default_timeout=60).run()
    assert str(failed.value) == NOT_REACHED + "the app rendered nothing"


def test_the_compile_error_record_is_where_the_harness_listens():
    """Streamlit 1.66: its script runner logs the record on its module's
    logger, which does not propagate. If an upgrade moves either, this fails,
    so a compile error is never reported as an empty page."""
    from streamlit.runtime.scriptrunner import script_runner

    assert script_runner._LOGGER.name == COMPILE_ERROR_LOGGER
    assert logging.getLogger(COMPILE_ERROR_LOGGER).propagate is False
    assert AppTest._run.checks_page_reached is True


def test_an_exception_raised_after_the_page_rendered_is_still_assert_no_exceptions(tmp_path):
    app = _script(tmp_path, "import streamlit as st\nst.write('rendered')\nraise RuntimeError('late')\n")
    at = AppTest.from_file(str(app), default_timeout=60).run()
    assert page_not_reached(at) is None
    with pytest.raises(pytest.fail.Exception) as failed:
        assert_no_exception(at, "app.py")
    assert str(failed.value).startswith("app.py: the app raised\n"), str(failed.value)
    assert "late" in str(failed.value)


CHILD_CHECK = "assert at.main.children, "
CHILD_REASONS = ('"the run did not reach the page: its main area is empty"', "not_reached(")


def _child_runs():
    """Each line, in a script a test hands to a fresh interpreter, that
    builds an AppTest itself; the wrap is not installed there. A child that
    imports conftest and runs make_app takes the wrap instead. Each comes
    with whether its script defines body(): such a script runs inside a
    shared head that defines not_reached, which names a compile error."""
    import ast

    needle = "AppTest" + ".from_file("
    found = []
    for path in sorted(Path(conftest.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in parts:
                text = node.value
            else:
                continue
            in_head = any(line.startswith("def body():") for line in text.splitlines())
            found += [(path.name, line.strip(), in_head) for line in text.splitlines() if needle in line]
    return found


def test_every_run_in_a_child_interpreter_fails_on_a_page_that_never_ran():
    runs = _child_runs()
    assert len(runs) >= 12, runs
    unchecked = [run for run in runs if CHILD_CHECK not in run[1]
                 or not run[1].split(CHILD_CHECK, 1)[1].startswith(CHILD_REASONS)]
    assert unchecked == []
    # A child run inside the shared head has not_reached at hand, and a bare
    # sentence there would say "its main area is empty" over a compile error.
    in_head = [run for run in runs if run[2]]
    assert len(in_head) >= 5, runs
    bare = [run for run in in_head if not run[1].split(CHILD_CHECK, 1)[1].startswith("not_reached(")]
    assert bare == []


def _child_scripts():
    """Every multi-line string in tests/*.py that parses as Python, with the
    file it is in."""
    import ast

    for path in sorted(Path(conftest.__file__).parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" in node.value:
                try:
                    yield path.name, ast.parse(node.value)
                except SyntaxError:
                    continue


def test_a_child_that_runs_the_page_in_a_thread_reports_why_the_run_failed():
    """A failure raised in a thread dies with it: the run is caught into what
    the child reports."""
    import ast

    needles = ("make_app", "from_file")
    threaded = []
    for name, tree in _child_scripts():
        targets = {k.value.id for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and getattr(n.func, "attr", getattr(n.func, "id", None)) == "Thread"
                   for k in n.keywords if k.arg == "target" and isinstance(k.value, ast.Name)}
        for fn in ast.walk(tree):
            if not (isinstance(fn, ast.FunctionDef) and fn.name in targets):
                continue
            runs = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                    and getattr(c.func, "attr", getattr(c.func, "id", None)) in needles]
            guarded = {id(c) for t in ast.walk(fn) if isinstance(t, ast.Try)
                       and any(isinstance(h.type, ast.Name) and h.type.id == "BaseException" for h in t.handlers)
                       for stmt in t.body for c in ast.walk(stmt)}
            threaded += [(name, fn.name, id(c) in guarded) for c in runs]
    assert threaded, "no child runs the page in a thread: the census found nothing"
    assert [t for t in threaded if not t[2]] == [], threaded


def test_the_import_audit_counts_what_a_run_rendered(tmp_path):
    """Its page record's "elements": 0 for a page that rendered nothing or
    only a sidebar, one for one element in the main area (the page's own
    block not counted)."""
    import json
    import subprocess
    import sys

    counts = {}
    for case, script in (("nothing", "import streamlit as st\nst.stop()\n"),
                         ("one", "import streamlit as st\nst.write('one')\n"),
                         ("only_a_sidebar", "import streamlit as st\nst.sidebar.write('side')\n")):
        root = tmp_path / case
        scratch = {name: root / "scratch" / name for name in ("home", "xdg", "appdata", "tmp")}
        for folder in scratch.values():
            folder.mkdir(parents=True)
        (root / "app.py").write_text(script, encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(scratch["home"]), "XDG_DATA_HOME": str(scratch["xdg"]),
               "APPDATA": str(scratch["appdata"]), "TMPDIR": str(scratch["tmp"]), "LANG": "C.UTF-8"}
        out = root / "audit.json"
        done = subprocess.run([sys.executable, str(Path(conftest.__file__).parent / "import_audit.py"), str(root),
                               str(out), "chart"], capture_output=True, text=True, env=env, timeout=300)
        assert done.returncode == 0, done.stderr[-3000:]
        counts[case] = json.loads(out.read_text(encoding="utf-8"))["outcome"]["pages"]["chart"]
    assert counts == {"nothing": {"exceptions": [], "elements": 0},
                      "one": {"exceptions": [], "elements": 1},
                      "only_a_sidebar": {"exceptions": [], "elements": 0}}, counts


def test_a_body_child_names_a_compile_error(tmp_path):
    """The fresh-interpreter children that run under a shared head say why
    their run rendered nothing."""
    import ast

    source = (Path(conftest.__file__).parent / "test_fm3_ephemeris_folder_umask_2026_10_07.py").read_text(encoding="utf-8")
    head = next(n.value.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assign)
                and [getattr(t, "id", None) for t in n.targets] == ["_HEAD"])
    helper = next(n for n in ast.parse(head).body if isinstance(n, ast.FunctionDef) and n.name == "not_reached")
    space = {}
    exec(compile(ast.Module([helper], []), "_HEAD", "exec"), space)
    broken, empty = tmp_path / "broken.py", tmp_path / "empty.py"
    broken.write_text("this is not python (\n", encoding="utf-8")
    empty.write_text("import streamlit as st\nst.stop()\n", encoding="utf-8")
    assert space["not_reached"](str(broken)).startswith(
        "the run did not reach the page: the app did not compile: SyntaxError(")
    assert space["not_reached"](str(empty)) == "the run did not reach the page: its main area is empty"
