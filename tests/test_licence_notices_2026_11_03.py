"""The program's copyright and licence notices, and the licence texts a download carries.

The program's own files open with its notice and README states it; the Sources page shows
the notice the AGPL asks an interactive program to show; and the build puts LICENSE, the
symbol font's licence and THIRD_PARTY_NOTICES.txt -- the Python runtime's licence and every
bundled package's, read from the build's own environment -- into the download.
"""
import hashlib
import re
import sys
from importlib import metadata
from pathlib import Path

import pytest

import shipped_modules
import source_list
from conftest import APP_PATH, assert_no_exception, make_app, ui_source

ROOT = APP_PATH.parent
HEADER = ("# Zīj. Copyright (C) 2026 Dār al-Ḥikma.\n"
          "# Licensed under the GNU Affero General Public License, version 3: see LICENSE.\n")
PROGRAM_FILES = (*source_list.names(ROOT), "glyph_font.py", "desktop_launcher.py", "server_limits.py", "run_source.py")
NOTICE = ("Zīj © Dār al-Ḥikma. It is free software: anyone may share and change it under the "
          "[GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html), "
          "and it comes with no warranty. Its source: [github.com/dar-al-hikma/Zij](https://github.com/dar-al-hikma/Zij).")
# The Apache License 2.0 as the Apache Software Foundation publishes it, at
# https://www.apache.org/licenses/LICENSE-2.0.txt.
APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
# The MIT License's two paragraphs, as licenses/three-MIT.txt holds them below its copyright line.
MIT_FIRST = "Permission is hereby granted, free of charge, to any person"
RULE = "#" * 78


@pytest.mark.parametrize("name", PROGRAM_FILES)
def test_each_program_file_opens_with_the_notice(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert text.startswith(HEADER + '"""'), name


def test_the_readme_states_the_notice_and_the_licence():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Licence\n", 1)[1].split("\n## ", 1)[0]
    assert section.lstrip().startswith("Copyright (C) 2026 Dār al-Ḥikma.\n")
    for words in ("GNU Affero General\nPublic License, version 3", "WITHOUT ANY\nWARRANTY", "`THIRD_PARTY_NOTICES.txt`"):
        assert words in section, words


def _sentence(name):
    import ast
    tree = ast.parse(ui_source())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == [name])
    return ast.literal_eval(node.value)


def test_the_page_notice_names_the_holder_the_licence_the_warranty_and_the_source_and_no_year():
    text = _sentence("LICENCE_NOTICE")
    assert text == NOTICE
    assert not re.search(r"\d{4}", text)


def test_the_sources_page_ends_with_the_notice():
    at = make_app(page="sources").run()
    assert_no_exception(at, "the Sources page")
    assert [h.value for h in at.main.subheader][-1] == "Licence"
    assert [m.value for m in at.main.markdown][-1] == NOTICE


def test_the_download_carries_the_program_s_licence_and_the_font_s():
    datas = shipped_modules.spec_datas(ROOT)
    assert ("LICENSE", ".") in datas and ("fonts/OFL.txt", "fonts") in datas


def test_the_download_carries_each_page_font_s_licence_and_notice():
    datas = shipped_modules.spec_datas(ROOT)
    carried = {Path(source).name for source, dest in datas if dest == "licenses"}
    read_in = ("Apache-2.0.txt", "MIT.txt", "PYTHON_LIBRARIES.txt")
    held = {path.name for path in (ROOT / "licenses").iterdir() if path.name not in read_in}
    assert carried == held, "those three are read into the notices; every other licence goes as it stands"
    notice = (ROOT / "licenses" / "FONT_NOTICES.txt").read_text(encoding="utf-8")
    faces = sorted((ROOT / "fonts").glob("*.ttf"))
    assert faces
    for path in faces:
        if not path.name.startswith("tae-"):
            assert path.name in notice, path.name
    assert "fonts/OFL.txt" in notice


def test_each_face_s_own_copyright_line_stands_in_the_notice():
    """A licence file may hold no copyright line: the notice states what the face itself does."""
    from fontTools.ttLib import TTFont
    notices = (ROOT / "licenses" / "FONT_NOTICES.txt").read_text(encoding="utf-8")
    faces = sorted(path for path in (ROOT / "fonts").glob("*.ttf") if not path.name.startswith("tae-"))
    assert faces
    for path in faces:
        stated = TTFont(path)["name"].getDebugName(0)
        assert stated and stated in notices, path.name


def test_the_apache_text_is_the_published_one_verbatim():
    assert hashlib.sha256((ROOT / "licenses" / "Apache-2.0.txt").read_bytes()).hexdigest() == APACHE_SHA256


def _notices(tmp_path, toc):
    built = shipped_modules.run_spec(ROOT, toc=toc, workpath=tmp_path)
    entry = built["toc_datas"][-1]
    assert entry[0] == "THIRD_PARTY_NOTICES.txt" and entry[2] == "DATA"
    assert Path(entry[1]).parent == tmp_path, "written in the build's work folder, not the checkout"
    return Path(entry[1]).read_text(encoding="utf-8")


def _sections(text):
    """The notices' sections, by their first line (a name and a version)."""
    parts = text.split(RULE + "\n")[1:]
    return {part.split("\n", 1)[0]: part for part in parts}


# What a build bundles, as the analysis names it: modules by their dotted
# names, binaries and data files by where they go.
TOC = {"pure": [("streamlit.runtime.app_session", None, "PYMODULE"), ("pandas.core.frame", None, "PYMODULE"),
                ("json.decoder", None, "PYMODULE"), ("engine", None, "PYMODULE")],
       "binaries": [("swisseph.cpython-312-x86_64-linux-gnu.so", None, "BINARY"), ("libssl.so.3", None, "BINARY")],
       "datas": [("tzdata/zoneinfo/UTC", None, "DATA"), ("timezonefinder_data/timezone_names.json", None, "DATA"),
                 ("data/place_clocks.tsv", None, "DATA"), ("app.py", None, "DATA"),
                 ("streamlit-1.66.1.dist-info/METADATA", None, "DATA")]}


def test_the_notices_hold_python_and_each_package_the_bundle_draws_from(tmp_path):
    sections = _sections(_notices(tmp_path, TOC))
    names = [line.rsplit(" ", 1)[0] for line in sections]
    python = ".".join(str(part) for part in sys.version_info[:3])
    assert names[0] == "Python" and list(sections)[0] == f"Python {python}"
    assert names[1:] == ["pandas", "pyswisseph", "streamlit", "timezonefinder-data", "tzdata"], names
    for name in names[1:]:
        dist = metadata.distribution(name)
        assert f"{dist.metadata['Name']} {dist.version}" in sections


def test_each_package_s_section_carries_its_licence_text(tmp_path):
    sections = _sections(_notices(tmp_path, TOC))
    for head, body in sections.items():
        assert "(Its metadata holds no licence file.)" not in body, head
        assert len(body) > 500, head
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in sections[f"pyswisseph {metadata.version('pyswisseph')}"]
    assert "Open Database License" in sections[f"timezonefinder-data {metadata.version('timezonefinder-data')}"]


def test_a_package_that_states_apache_without_a_copy_gets_the_kept_text(tmp_path):
    """Streamlit's package carries no licence file. Should a later release add
    one, its section holds that one instead, and the Apache text is still there."""
    body = _sections(_notices(tmp_path, TOC))[f"streamlit {metadata.version('streamlit')}"]
    apache = (ROOT / "licenses" / "Apache-2.0.txt").read_text(encoding="utf-8").rstrip()
    assert ("--- " in body) or (apache in body)
    assert "Version 2.0, January 2004" in body


def test_the_python_section_carries_the_runtime_s_licence_where_the_build_has_one(tmp_path):
    import os
    import sysconfig
    found = [p for p in (os.path.join(sysconfig.get_path("stdlib"), "LICENSE.txt"),
                         os.path.join(sys.base_prefix, "LICENSE.txt")) if os.path.isfile(p)]
    body = next(iter(_sections(_notices(tmp_path, {})).values()))
    if found:
        assert Path(found[0]).read_text(encoding="utf-8", errors="replace").rstrip() in body
    else:
        assert "(No LICENSE.txt was found in the Python this download was built with.)" in body


def test_nothing_bundled_from_no_package_gives_python_alone(tmp_path):
    sections = _sections(_notices(tmp_path, {"datas": [("app.py", None, "DATA"), ("LICENSE", None, "DATA")]}))
    assert [head.split(" ")[0] for head in sections] == ["Python"]


def test_a_package_claiming_the_program_s_own_names_is_not_credited_with_them(tmp_path, monkeypatch):
    """A carelessly built package can install a top-level LICENSE, data/ or a
    module named like one of the program's; the program's own files, folders
    and modules are never read as that package's."""
    claims = {"LICENSE": ["streamlit"], "data": ["streamlit"], "fonts": ["streamlit"], "engine": ["streamlit"],
              "server_limits": ["streamlit"], "glyph_font": ["streamlit"]}
    monkeypatch.setattr(metadata, "packages_distributions", lambda: claims)
    toc = {"pure": [("server_limits", None, "PYMODULE"), ("engine", None, "PYMODULE")],
           "datas": [("LICENSE", None, "DATA"), ("data/place_clocks.tsv", None, "DATA"),
                     ("fonts/OFL.txt", None, "DATA"), ("glyph_font.py", None, "DATA")]}
    assert [head.split(" ")[0] for head in _sections(_notices(tmp_path, toc))] == ["Python"]
    claims["swisseph"] = ["streamlit"]
    toc["binaries"] = [("swisseph.cpython-312-x86_64-linux-gnu.so", None, "BINARY")]
    assert [head.split(" ")[0] for head in _sections(_notices(tmp_path, toc))] == ["Python", "streamlit"]


class _Stated:
    """A distribution the bundle draws from: its metadata as given, and no file in its metadata folder."""

    version = "1.2.3"
    files = None

    def __init__(self, **fields):
        self.metadata = _Fields(fields)


class _Fields(dict):
    def get_all(self, name):
        return None

    def __getitem__(self, name):
        return self.get(name)


def _stated_section(tmp_path, monkeypatch, **fields):
    """The section of an invented package, as the notices write it."""
    name = "invented-package"
    real = metadata.distribution
    monkeypatch.setattr(metadata, "packages_distributions", lambda: {"invented": [name]})
    monkeypatch.setattr(metadata, "distribution",
                        lambda asked: _Stated(Name=name, **fields) if asked == name else real(asked))
    toc = {"pure": [("invented.module", None, "PYMODULE")]}
    return _sections(_notices(tmp_path, toc))[f"{name} 1.2.3"]


@pytest.mark.parametrize("holder", ["Jonathan Tushman", "Ronald Oussoren"])
def test_a_package_that_states_mit_without_a_copy_gets_the_terms_and_its_own_author(tmp_path, monkeypatch, holder):
    body = _stated_section(tmp_path, monkeypatch, License="MIT", Author=holder)
    assert f"Copyright (c) {holder}\n" in body
    assert (ROOT / "licenses" / "MIT.txt").read_text(encoding="utf-8").rstrip() in body
    assert "(Its metadata holds no licence file.)" not in body


def test_an_author_named_only_beside_an_address_is_named_without_it(tmp_path, monkeypatch):
    name = "Someone Else"
    body = _stated_section(tmp_path, monkeypatch, License="MIT", **{"Author-email": f"{name} <someone@example.org>"})
    assert f"Copyright (c) {name}\n" in body and "example.org" not in body


def test_a_package_that_names_no_author_is_given_no_holder(tmp_path, monkeypatch):
    body = _stated_section(tmp_path, monkeypatch, License="MIT", Maintainer="Not The Holder",
                           **{"Author-email": "someone@example.org"})
    assert "Not The Holder" not in body and "example.org" not in body
    assert "Copyright" not in body.split(MIT_FIRST, 1)[0]
    assert MIT_FIRST in body and "names no author" in body


def test_a_package_stating_neither_licence_gets_neither_text(tmp_path, monkeypatch):
    body = _stated_section(tmp_path, monkeypatch, License="Some Other Licence", Author="Someone")
    assert "(Its metadata holds no licence file.)" in body
    assert MIT_FIRST not in body and "Copyright" not in body


def test_the_mit_terms_are_the_ones_that_travel_with_three(tmp_path):
    terms = (ROOT / "licenses" / "MIT.txt").read_text(encoding="utf-8")
    three = (ROOT / "licenses" / "three-MIT.txt").read_text(encoding="utf-8")
    assert terms.startswith(MIT_FIRST) and terms.rstrip().endswith("SOFTWARE.")
    assert " ".join(terms.split()) in " ".join(three.split())


OPENSSL_FORMS = [("libcrypto-3-x64.dll", "libssl-3-x64.dll"), ("libssl-3-x64.dll",), ("LIBCRYPTO-3-X64.dll",),
                 ("libcrypto-3.dll", "libssl-3.dll"), ("libssl-3.dll",), ("libcrypto.3.dylib", "libssl.3.dylib"),
                 ("libcrypto.3.dylib",), ("libcrypto-3-x64.dll", "libcrypto-3.dll", "libssl-3-x64.dll", "libssl-3.dll")]


def _binaries(*names):
    return {"binaries": [(name, None, "BINARY") for name in names]}


@pytest.mark.parametrize("names", OPENSSL_FORMS)
def test_openssl_has_a_section_by_each_name_form_when_it_is_bundled(tmp_path, names):
    sections = _sections(_notices(tmp_path, _binaries(*names)))
    assert list(sections)[-1] == "OpenSSL 3"
    body = sections["OpenSSL 3"]
    assert "License: Apache-2.0\n" in body and "The OpenSSL Project Authors hold the copyright." in body
    assert (ROOT / "licenses" / "Apache-2.0.txt").read_text(encoding="utf-8").rstrip() in body


@pytest.mark.parametrize("names", OPENSSL_FORMS)
def test_the_openssl_section_names_the_files_held_and_no_other(tmp_path, names):
    sentence = _sections(_notices(tmp_path, _binaries(*names)))["OpenSSL 3"].split("The OpenSSL Project", 1)[0]
    for name in ("libcrypto-3-x64.dll", "libssl-3-x64.dll", "libcrypto-3.dll", "libssl-3.dll", "libcrypto.3.dylib", "libssl.3.dylib"):
        assert (name.lower() in sentence.lower()) == (name.lower() in map(str.lower, names)), name


def test_a_library_in_a_package_s_folder_is_named_by_its_file(tmp_path):
    body = _sections(_notices(tmp_path, _binaries("PySide6\\libssl-3-x64.dll")))["OpenSSL 3"]
    assert "libssl-3-x64.dll" in body and "PySide6" not in body


@pytest.mark.parametrize("name", ["libcrypto-1_1.dll", "libssl-1_1.dll", "libcrypto-1_1-x64.dll", "libssl-1_1-x64.dll",
                                  "libcrypto.1.1.dylib", "libssl.1.1.dylib", "libssl.so.3", "swisseph.cp314-win_amd64.pyd"])
def test_a_name_of_no_openssl_3_form_gives_no_section(tmp_path, name):
    assert "OpenSSL 3" not in _sections(_notices(tmp_path, _binaries(name)))


def test_none_bundled_gives_no_section_of_any_library_kind(tmp_path):
    assert list(_sections(_notices(tmp_path, {"datas": [("app.py", None, "DATA")]}))) == [
        f"Python {'.'.join(str(part) for part in sys.version_info[:3])}"]


def test_a_library_s_name_in_a_folder_of_python_files_is_no_library(tmp_path):
    """A package's stub or header of the same name is not the library."""
    toc = {"datas": [("somewhere/_lzma.pyi", None, "DATA"), ("somewhere/libcrypto-3.dll.txt", None, "DATA")]}
    assert [head.split(" ")[0] for head in _sections(_notices(tmp_path, toc))] == ["Python"]


PYTHON_LIBRARIES_HEAD = "Libraries the Python runtime brings"
LIBRARY_TEXTS = {"Zstandard": "Meta Platforms, Inc. and affiliates", "expat": "2001-2025 Expat maintainers",
                 "libffi": "1996-2022  Anthony Green, Red Hat, Inc and others", "zlib-ng": "Jean-loup Gailly and Mark Adler",
                 "HACL*": "2022-2023 HACL* Contributors"}
DOCUMENTATION_HEAD = "Licenses and Acknowledgements for Incorporated Software"
DOCUMENTATION_HEADINGS = ["Mersenne Twister", "Sockets", "Asynchronous socket services", "Cookie management", "Execution tracing",
                          "UUencode and UUdecode functions", "XML Remote Procedure Calls", "test_epoll", "Select kqueue", "SipHash24",
                          "strtod and dtoa", "OpenSSL", "expat", "libffi", "zlib", "cfuhash", "libmpdec", "W3C C14N test suite", "mimalloc",
                          "asyncio", "Global Unbounded Sequences (GUS)", "Zstandard bindings", "Unicode Character Database"]


@pytest.mark.parametrize("name, library", [
    ("libffi-8.dll", "libffi"), ("pyexpat.pyd", "expat"), ("pyexpat.cpython-314-darwin.so", "expat"),
    ("_decimal.pyd", "libmpdec"), ("_decimal.cpython-314-darwin.so", "libmpdec"), ("sqlite3.dll", "SQLite"),
    ("_sqlite3.cpython-314-darwin.so", "SQLite"), ("libzstd.1.dylib", "Zstandard"), ("_zstd.pyd", "Zstandard"),
    ("_lzma.pyd", "liblzma, part of XZ Utils"), ("_lzma.cpython-314-darwin.so", "liblzma, part of XZ Utils"),
    ("_bz2.pyd", "bzip2"), ("python314.dll", "zlib-ng"), ("python314.dll", "mimalloc"), ("python314.dll", "HACL*"),
    ("Python", "mimalloc")])
def test_each_library_python_brings_is_named_with_its_file_and_the_texts_follow(tmp_path, name, library):
    body = _sections(_notices(tmp_path, _binaries(name)))[PYTHON_LIBRARIES_HEAD]
    assert f"\n{name}: {library}\n" in body
    assert (ROOT / "licenses" / "PYTHON_LIBRARIES.txt").read_text(encoding="utf-8").rstrip() in body


@pytest.mark.parametrize("name", ["_sqlite3.pyd", "_zstd.cpython-314-darwin.so", "_ctypes.pyd", "_ctypes.cpython-314-darwin.so",
                                  "_bz2.cpython-314-darwin.so", "python3.dll", "swisseph.cp314-win_amd64.pyd"])
def test_a_file_that_neither_is_nor_holds_a_named_library_names_none(tmp_path, name):
    """_sqlite3.pyd, _ctypes.pyd and macOS's _zstd reach their library in a file of its own; macOS's
    _bz2 and _ctypes the system's; python3.dll holds no library inside it. Windows's _bz2.pyd holds
    bzip2, and the runtime's DLL its libraries: those two have rows, and pass no file of this list."""
    assert PYTHON_LIBRARIES_HEAD not in _sections(_notices(tmp_path, _binaries(name)))


@pytest.mark.parametrize("dest", ["Python", "Python.framework/Python", "Python.framework/Versions/3.14/Python"])
def test_the_framework_s_runtime_is_mimalloc_alone_by_each_name_a_build_gives_it(tmp_path, dest):
    body = _sections(_notices(tmp_path, _binaries(dest)))[PYTHON_LIBRARIES_HEAD]
    assert [line for line in body.split("\n") if line.startswith("Python: ")] == ["Python: mimalloc"]


def test_a_file_called_python_that_is_not_the_framework_s_runtime_names_none(tmp_path):
    toc = {"binaries": [("somewhere/Python", None, "BINARY")], "datas": [("Python", None, "DATA"), ("Python.framework/Versions/3.14/Python", None, "DATA")]}
    assert PYTHON_LIBRARIES_HEAD not in _sections(_notices(tmp_path, toc))


def test_the_new_file_says_what_it_is_and_that_a_download_may_hold_less():
    text = (ROOT / "licenses" / "PYTHON_LIBRARIES.txt").read_text(encoding="utf-8")
    opening = " ".join(text.split("-" * 78, 1)[0].split())
    assert "Not every library in what follows is in every download: the list above names what this download holds." in opening
    assert "the Python documentation's list" in opening


@pytest.mark.parametrize("library, words", LIBRARY_TEXTS.items())
def test_the_new_file_holds_each_text_it_is_said_to(library, words):
    text = (ROOT / "licenses" / "PYTHON_LIBRARIES.txt").read_text(encoding="utf-8")
    part = text.split("-" * 78 + f"\n{library}\n", 1)[1].split("-" * 78, 1)[0]
    assert words in part and re.search(r"Redistribution and use|Permission is (?:hereby )?granted", part)


def test_the_new_file_holds_those_texts_and_no_other():
    """SQLite and liblzma stay named and no more."""
    text = (ROOT / "licenses" / "PYTHON_LIBRARIES.txt").read_text(encoding="utf-8")
    assert [part.split("\n", 2)[1] for part in text.split("-" * 78)[1:]] == [*LIBRARY_TEXTS, DOCUMENTATION_HEAD]


def test_the_new_file_holds_the_documentation_s_whole_list_plainly():
    text = (ROOT / "licenses" / "PYTHON_LIBRARIES.txt").read_text(encoding="utf-8")
    part = text.split("-" * 78 + f"\n{DOCUMENTATION_HEAD}\n", 1)[1]
    lines = part.split("\n")
    assert [above for above, line in zip(lines, lines[1:]) if re.fullmatch(r"-{3,}", line) and above] == DOCUMENTATION_HEADINGS
    assert "incomplete, but growing list" in part and "Microsoft Corporation, Daan Leijen" in part and "UNICODE LICENSE V3" in part
    assert not re.search(r":[a-z:]+:`|``|`_|::$", part, re.M)


@pytest.mark.parametrize("name", ["libzstd.1.dylib", "_zstd.pyd"])
def test_each_zstandard_file_reaches_its_bsd_text(tmp_path, name):
    body = _sections(_notices(tmp_path, _binaries(name)))[PYTHON_LIBRARIES_HEAD]
    part = body.split("-" * 78 + "\nZstandard\n\n", 1)[1].split("-" * 78, 1)[0]
    assert part.startswith("BSD License\n\nFor Zstandard software\n\n") and "Meta Platforms, Inc. and affiliates. All rights reserved.\n" in part
    assert "Redistributions in binary form must reproduce" in part and part.rstrip().endswith("SUCH DAMAGE.")


@pytest.mark.parametrize("name", ["VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "ucrtbase.dll", "api-ms-win-crt-math-l1-1-0.dll",
                                  "MSVCP140.dll", "msvcp140-d448dcabdad98c14abc6ff2741df95cd.dll", "vcamp140.dll", "vcomp140.dll"])
def test_a_microsoft_runtime_library_is_named_in_one_line_with_no_terms(tmp_path, name):
    body = _sections(_notices(tmp_path, _binaries(name, "ucrtbase.dll")))["Microsoft runtime libraries"]
    lines = [line for line in body.split("\n") if line][1:]
    assert len(lines) == 1 and name in lines[0] and "ucrtbase.dll" in lines[0]
    assert not re.search(r"(?i)licen[cs]e|terms|copyright|permission", body)


def test_the_opening_says_the_download_carries_what_the_runtime_brings(tmp_path):
    opening = _notices(tmp_path, {}).split(RULE, 1)[0]
    assert "the Python runtime, the libraries it\nbrings," in opening
