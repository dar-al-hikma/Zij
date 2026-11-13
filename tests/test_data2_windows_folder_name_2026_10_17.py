"""The ephemeris folder's name as Swiss Ephemeris reads it on Windows.

The library takes its path from $SE_EPHE_PATH, which wins over the path its
setter is handed, through the C library's getenv: on Windows the system's
ANSI code page's form of the name, in which a letter outside the code page
comes out as another, so the path is not the folder. The check compared the
UTF-8 form with os.fsencode's, which is UTF-8 on Windows too, so it could not
fail there. It now asks whether the code page can write the name, and the
refusal says so.

Emulated on this machine: the module's `os` is handed a stand-in whose name
is 'nt' (the real module, and every other module, untouched), and the code
page is monkeypatched; no environment variable is set.
"""
from __future__ import annotations

import json
import locale
import os
import subprocess
import sys

import pytest


@pytest.fixture
def ephemeris():
    import ephemeris
    return ephemeris


class _WindowsOs:
    """os, as ephemeris.py reads it, with the name Windows gives."""
    name = "nt"

    def __getattr__(self, attr):
        return getattr(os, attr)


@pytest.fixture
def on_windows(ephemeris, monkeypatch):
    def with_code_page(code_page):
        monkeypatch.setattr(ephemeris, "os", _WindowsOs())
        monkeypatch.setattr(locale, "getencoding", lambda: code_page)
    return with_code_page


@pytest.mark.parametrize("code_page, name", [
    ("cp1252", "/tmp/Пользователь/zij-ephemeris-x1"),
    ("cp1252", "/tmp/Zoë Ōta/zij-ephemeris-x1"),
    ("cp1251", "/tmp/José Ñúñez/zij-ephemeris-x1"),
    ("cp932", "/tmp/محمد/zij-ephemeris-x1"),
])
def test_a_name_outside_the_code_page_fails_the_check_and_says_why(ephemeris, on_windows, code_page, name):
    on_windows(code_page)
    assert ephemeris._ephemeris_folder_is_safe(name) is False
    assert ephemeris._ephemeris_folder_unsafe(name) == (
        f"it holds a letter the system's code page ({code_page}) cannot write")


@pytest.mark.parametrize("code_page, name", [
    ("cp1252", "/tmp/zij-ephemeris-plain"),
    ("cp1252", "/tmp/José Müller/zij-ephemeris-x1"),
    ("cp1251", "/tmp/Пользователь/zij-ephemeris-x1"),
    ("cp932", "/tmp/山田/zij-ephemeris-x1"),
    ("utf-8", "/tmp/Пётр 山田 José/zij-ephemeris-x1"),
])
def test_a_name_the_code_page_writes_passes_as_before(ephemeris, on_windows, code_page, name):
    on_windows(code_page)
    assert ephemeris._ephemeris_folder_unsafe(name) is None
    assert ephemeris._ephemeris_folder_is_safe(name) is True


def test_the_bound_counts_the_longer_of_the_two_forms(ephemeris, on_windows):
    """200 bytes in UTF-8 (100 two-byte letters, which cp1252 writes in one
    byte each) is the bound on Windows as elsewhere: the setter's form is
    still counted."""
    on_windows("cp1252")
    head = "/tmp/"
    taken = head + "é" * ((200 - len(head)) // 2)
    refused = taken + "é"
    assert len(taken.encode("utf-8")) <= 200 < len(refused.encode("utf-8"))
    assert ephemeris._ephemeris_folder_is_safe(taken) is True
    assert ephemeris._ephemeris_folder_unsafe(refused) == "it is longer than 200 bytes"


def test_a_folder_made_with_such_a_name_is_refused_removed_and_the_reason_named(ephemeris, on_windows, monkeypatch,
                                                                                  tmp_path):
    made = tmp_path / "Пользователь"
    monkeypatch.setattr(ephemeris.tempfile, "mkdtemp", lambda prefix: (made.mkdir(), str(made))[1])
    on_windows("cp1252")
    with pytest.raises(ephemeris.EphemerisFolderRefused) as refused:
        ephemeris._ephemeris_folder_make()
    assert str(refused.value) == (
        "the temporary folder's name cannot be given to Swiss Ephemeris whole (it holds a letter the system's code "
        "page (cp1252) cannot write); point TMPDIR, TEMP or TMP at a plain folder")
    assert not made.exists()


@pytest.mark.parametrize("name, why", [
    ("tmp/zij", "it is not an absolute path"),
    ("/tmp/zij;x", "it holds ';' or ':', where Swiss Ephemeris splits a path in two"),
    ("/tmp/zij:x", "it holds ';' or ':', where Swiss Ephemeris splits a path in two"),
    ("/tmp/zij\x00x", "it holds a NUL"),
    ("/tmp/zij-\udcff", "it holds a byte the system could not read as a letter"),
    ("/" + "x" * 200, "it is longer than 200 bytes"),
])
def test_each_reason_on_linux_and_macos(ephemeris, name, why):
    assert ephemeris._ephemeris_folder_unsafe(name) == why
    assert ephemeris._ephemeris_folder_is_safe(name) is False


def test_a_name_whose_two_forms_differ_says_so_on_linux_and_macos(ephemeris, monkeypatch):
    monkeypatch.setattr(os, "fsencode", lambda name: os.fspath(name).encode("latin-1"))
    assert ephemeris._ephemeris_folder_unsafe("/tmp/zij-éphéméris") == (
        "the system would hand Swiss Ephemeris another name than the folder's")


# --- What the page says of this refusal -------------------------------------------------

NAME_SENTENCE = ("Nothing is calculated: the computer's temporary folder has a name this app's ephemeris cannot "
                 "read; set TEMP to a folder such as C:\\Temp, whose whole path has only English letters and "
                 "digits, and open the app again.")
FOLDER_SENTENCE = ("Nothing is calculated: this app could not make a private folder for its ephemeris in the "
                   "computer's temporary folder.")

_PAGE = r"""
import json, locale, os, shutil, sys, tempfile
root, app, when, bad, platform = sys.argv[1:6]
sys.path[:0] = [root, os.path.join(root, "tests")]
from streamlit.testing.v1 import AppTest
if when == "run":
    import engine                                     # the engine loaded, its folder made as usual
import ephemeris

class WindowsOs:
    name = "nt"
    def __getattr__(self, attr):
        return getattr(os, attr)

if platform == "windows":
    ephemeris.os = WindowsOs()
    locale.getencoding = lambda: "cp1252"
os.makedirs(bad)
tempfile.tempdir = bad                                # the next folder is made in a folder so named
shutil.rmtree(ephemeris._EPHEMERIS_FOLDER)            # gone: the next check makes a new one
at = AppTest.from_file(app, default_timeout=240).run(timeout=240); assert at.main.children, "the run did not reach the page: its main area is empty"
print("PAGE " + json.dumps({"errors": [e.value for e in at.error],
                            "exceptions": [str(e.value)[:300] for e in at.exception],
                            "left": os.listdir(bad)}))
"""


def _page(tmp_path, when, bad_name, platform):
    from conftest import APP_PATH, EXECUTABLE_DIR
    temporary = tmp_path / "t"
    temporary.mkdir()
    env = {**os.environ, "TMPDIR": str(temporary), "XDG_DATA_HOME": str(tmp_path / "xdg")}
    env.pop("SE_EPHE_PATH", None)
    done = subprocess.run(
        [sys.executable, "-c", _PAGE, str(EXECUTABLE_DIR), str(APP_PATH), when, str(tmp_path / bad_name), platform],
        capture_output=True, text=True, env=env, timeout=600, cwd=tmp_path)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("PAGE ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    return json.loads(lines[-1][5:])


@pytest.mark.parametrize("when", ["import", "run"])
def test_a_name_outside_the_code_page_says_its_reason_and_remedy_on_the_page(tmp_path, when):
    """At the engine's import (app.py's guard, by the class's name) and at a
    run's own check: the sentence that names the remedy, nothing else, and
    the folder made for it removed."""
    got = _page(tmp_path, when, "Пользователь", "windows")
    assert got == {"errors": [NAME_SENTENCE], "exceptions": [], "left": []}, got


@pytest.mark.parametrize("when", ["import", "run"])
def test_another_folder_refusal_keeps_its_sentence(tmp_path, when):
    """A name holding ';' (refused on every system) says the folder's own sentence."""
    got = _page(tmp_path, when, "a;b", "windows")
    assert got == {"errors": [FOLDER_SENTENCE], "exceptions": [], "left": []}, got


def test_the_same_name_on_linux_and_macos_computes(tmp_path):
    got = _page(tmp_path, "run", "Пользователь", "posix")
    assert got["errors"] == [] and got["exceptions"] == [], got


def test_the_name_sentence_is_one_plain_sentence_with_no_file_or_build_word():
    # The one backslash allowed is the example folder's, C:\Temp (st.error
    # reads Markdown, where a backslash before a letter stays a backslash).
    # Taken out once, the rest is held to every word refused, the backslash
    # included.
    assert NAME_SENTENCE.count("C:\\Temp, ") == 1
    rest = NAME_SENTENCE.replace("C:\\Temp, ", "", 1)
    for word in ("Swiss", "cp1252", "code page", "TMPDIR", "TMP ", "%", "\\", "/", "ruling", "`"):
        assert word not in rest, word
    assert NAME_SENTENCE.count(".") == 1 and NAME_SENTENCE.endswith(".")
