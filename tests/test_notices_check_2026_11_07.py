"""The step after the build that fails on a native library nobody has credited.

.github/scripts/notices_check.py reads a bundle; here it reads invented bundles in
each system's form, with the files named as the real downloads name theirs.
"""
import importlib.util
from pathlib import Path

import pytest

from test_build_pins import _step_index, _steps

ROOT = Path(__file__).resolve().parent.parent
RULE = "#" * 78
PE = b"MZ" + bytes(58) + (64).to_bytes(4, "little") + b"PE\0\0"
MACH_O = bytes.fromhex("cffaedfe") + bytes(60)
NOTICES = "Third-party notices\n\n{0}\nPython 3.14.8\n\nPSF text.\n{0}\npillow 13.0.0\n\nIts licence, naming mention.dll.\n{0}\nOpenSSL 3\n\nThis download holds libcrypto-3.dll, libcrypto.3.dylib.\n".format(RULE)
INSTALLED = {"pillow 13.0.0": ["PIL/_imaging.pyd", "PIL/.dylibs/libtiff.6.dylib", "PIL/_imaging.so", "PySide6/Qt6Core.dll"],
             "gone-from-the-notices 1.0": ["gone/gone.dll", "gone/gone.dylib", "PySide6/plugins/sqldrivers/qsqlpsql.dll"]}


@pytest.fixture(scope="module")
def check():
    spec = importlib.util.spec_from_file_location("notices_check", ROOT / ".github" / "scripts" / "notices_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _put(path, data=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def windows(tmp_path):
    bundle = tmp_path / "Zij"
    _put(bundle / "Zij.exe", PE)
    for name in ("python314.dll", "python3.dll", "_ssl.pyd", "_testcapi.pyd", "select.pyd", "libcrypto-3.dll", "PIL/_imaging.pyd"):
        _put(bundle / "_internal" / name, PE)
    _put(bundle / "_internal" / "app.py", b"not native")
    _put(bundle / "_internal" / "THIRD_PARTY_NOTICES.txt", NOTICES.replace("\n", "\r\n").encode("utf-8"))
    return bundle


@pytest.fixture
def macos(tmp_path):
    bundle = tmp_path / "Zij.app"
    contents = bundle / "Contents"
    _put(contents / "MacOS" / "Zij", MACH_O)
    _put(contents / "Frameworks" / "Python.framework" / "Versions" / "3.14" / "Python", MACH_O)
    _put(contents / "Frameworks" / "python3__dot__14" / "lib-dynload" / "_ssl.cpython-314-darwin.so", MACH_O)
    _put(contents / "Frameworks" / "libcrypto.3.dylib", MACH_O)
    _put(contents / "Frameworks" / "PIL" / "__dot__dylibs" / "libtiff.6.dylib", MACH_O)
    (contents / "Resources").mkdir()
    (contents / "Resources" / "libcrypto.3.dylib").symlink_to(contents / "Frameworks" / "libcrypto.3.dylib")
    _put(contents / "Resources" / "THIRD_PARTY_NOTICES.txt", NOTICES.encode("utf-8"))
    return bundle


def _internal(bundle):
    return bundle / "_internal"


def _frameworks(bundle):
    return bundle / "Contents" / "Frameworks"


def test_a_windows_bundle_with_everything_credited_passes(check, windows):
    assert check.faults(windows, INSTALLED) == []


def test_a_macos_bundle_with_everything_credited_passes(check, macos):
    assert check.faults(macos, INSTALLED) == []


@pytest.mark.parametrize("name", ["planted.dll", "planted.pyd", "sub/folder/planted.dll", "PLANTED.DLL"])
def test_a_library_planted_in_a_windows_bundle_fails_and_is_named(check, windows, name):
    _put(_internal(windows) / name, PE)
    found = check.faults(windows, INSTALLED)
    assert len(found) == 1 and name in found[0] and "no distribution's RECORD" in found[0]


@pytest.mark.parametrize("name", ["planted.dylib", "planted.so", "planted.so.3", "Some.framework/Versions/A/Some"])
def test_a_library_planted_in_a_macos_bundle_fails_and_is_named(check, macos, name):
    _put(_frameworks(macos) / name, MACH_O)
    found = check.faults(macos, INSTALLED)
    assert len(found) == 1 and name in found[0]


def test_a_library_with_no_telling_name_is_read_by_its_first_bytes_on_windows(check, windows):
    _put(_internal(windows) / "planted.bin", PE)
    assert check.faults(windows, INSTALLED)
    _put(_internal(windows) / "planted.bin", b"MZ is how this text happens to begin, and it runs on past sixty-four bytes.")
    assert check.faults(windows, INSTALLED) == []


def test_case_is_folded_on_windows(check, windows):
    _put(_internal(windows) / "PySide6" / "QT6CORE.DLL", PE)
    _put(_internal(windows) / "LIBCRYPTO-3.DLL", PE)
    assert check.faults(windows, INSTALLED) == []


def test_case_is_not_folded_on_macos(check, macos):
    _put(_frameworks(macos) / "LIBCRYPTO.3.DYLIB", MACH_O)
    _put(_frameworks(macos) / "PIL" / "__dot__dylibs" / "LIBTIFF.6.dylib", MACH_O)
    assert len(check.faults(macos, INSTALLED)) == 2


def test_a_named_library_stands_by_its_whole_name(check, windows):
    """ssl-3.dll is no credit for being inside another file's name, and .dll.bak is another file."""
    for name in ("crypto-3.dll", "libcrypto-3.dl", "ibcrypto-3.dll"):
        _put(_internal(windows) / name, PE)
    assert len(check.faults(windows, INSTALLED)) == 3


def test_a_package_s_licence_text_mentioning_a_file_credits_nothing(check, windows):
    _put(_internal(windows) / "mention.dll", PE)
    found = check.faults(windows, INSTALLED)
    assert len(found) == 1 and "mention.dll" in found[0]
    # The same words in a section that is no installed distribution's do credit it.
    assert not [fault for fault in check.faults(windows, {"unrelated 1.0": []}) if "mention.dll" in fault]


def test_a_listed_library_whose_distribution_has_no_section_fails(check, windows):
    _put(_internal(windows) / "gone" / "gone.dll", PE)
    found = check.faults(windows, INSTALLED)
    assert len(found) == 1 and "gone-from-the-notices 1.0" in found[0] and "no section" in found[0]


def test_a_library_is_credited_when_any_distribution_listing_it_has_a_section(check, windows):
    _put(_internal(windows) / "gone" / "gone.dll", PE)
    assert check.faults(windows, {**INSTALLED, "pillow 13.0.0": [*INSTALLED["pillow 13.0.0"], "gone/gone.dll"]}) == []


@pytest.mark.parametrize("rel", ["LIBPQ.dll", "libpq.dll", "libpq-5.dll", "PySide6/plugins/sqldrivers/qsqlpsql.dll"])
def test_postgresql_s_client_and_qt_s_drivers_fail_even_when_credited(check, windows, rel):
    _put(_internal(windows) / rel, PE)
    text = (_internal(windows) / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    (_internal(windows) / "THIRD_PARTY_NOTICES.txt").write_text(text + f"\nThis download holds {rel.rsplit('/')[-1]}.\n", encoding="utf-8")
    found = check.faults(windows, INSTALLED)
    assert len(found) == 1 and "do not ship" in found[0]


@pytest.mark.parametrize("name", ["_ssl.dll", "not_of_the_standard_library.pyd", "sub/_ssl.pyd", "python314_extra.dll"])
def test_the_runtime_s_list_is_no_wider_than_its_own_files(check, windows, name):
    _put(_internal(windows) / name, PE)
    assert check.faults(windows, INSTALLED), name


@pytest.mark.parametrize("name", ["planted.cpython-314-darwin.so", "libthing.so", "_ssl.so", "sub/_ssl.cpython-314-darwin.so"])
def test_the_runtime_s_list_on_macos_is_no_wider_than_its_own_files(check, macos, name):
    _put(_frameworks(macos) / "python3__dot__14" / "lib-dynload" / name, MACH_O)
    found = check.faults(macos, INSTALLED)
    assert len(found) == 1 and name in found[0] and "no distribution's RECORD" in found[0]


def test_a_standard_module_s_name_passes_only_in_the_runtime_s_folder_on_macos(check, macos):
    _put(_frameworks(macos) / "python3__dot__14" / "lib-dynload" / "_testcapi.cpython-314-darwin.so", MACH_O)
    assert check.faults(macos, INSTALLED) == []
    _put(_frameworks(macos) / "elsewhere" / "_ssl.cpython-314-darwin.so", MACH_O)
    found = check.faults(macos, INSTALLED)
    assert len(found) == 1 and "elsewhere/_ssl" in found[0]


def test_the_program_s_own_starter_passes_at_its_own_path_alone(check, windows):
    _put(_internal(windows) / "Zij.exe", PE)
    found = check.faults(windows, INSTALLED)
    assert len(found) == 1 and "Zij.exe" in found[0]


def test_a_link_is_read_where_its_target_stands(check, macos):
    """A link of any name passes, so long as what it points to is credited where that stands."""
    target = _frameworks(macos) / "libcrypto.3.dylib"
    (_frameworks(macos) / "a-link-of-another-name.dylib").symlink_to(target)
    assert "a-link-of-another-name.dylib" not in check.native_files(macos)
    assert check.faults(macos, INSTALLED) == []
    target.rename(_frameworks(macos) / "uncredited.dylib")
    (_frameworks(macos) / "a-link-of-another-name.dylib").unlink()
    (_frameworks(macos) / "a-link-of-another-name.dylib").symlink_to(_frameworks(macos) / "uncredited.dylib")
    found = check.faults(macos, INSTALLED)
    assert len(found) == 1 and "uncredited.dylib" in found[0]


def test_a_bundle_without_notices_fails(check, windows):
    (_internal(windows) / "THIRD_PARTY_NOTICES.txt").unlink()
    assert "holds no THIRD_PARTY_NOTICES.txt" in check.faults(windows, INSTALLED)[0]


def test_a_folder_holding_no_library_fails(check, tmp_path):
    bundle = tmp_path / "Zij"
    _put(bundle / "_internal" / "THIRD_PARTY_NOTICES.txt", NOTICES.encode("utf-8"))
    assert "holds no native library" in check.faults(bundle, INSTALLED)[0]


def test_the_program_s_data_are_read_by_name_and_never_opened(check, windows, monkeypatch):
    _put(_internal(windows) / "data" / "table.tsv", PE)
    _put(_internal(windows) / "atlas.db", PE)
    opened = []
    real = check._is_native_by_its_head
    monkeypatch.setattr(check, "_is_native_by_its_head", lambda path: opened.append(path.name) or real(path))
    assert check.faults(windows, INSTALLED) == []
    assert opened and not {"table.tsv", "atlas.db"} & set(opened)


def test_the_script_runs_by_hand_on_a_bundle(check, windows, capsys, monkeypatch):
    monkeypatch.setattr(check, "installed", lambda: INSTALLED)
    assert check.main(["notices_check.py", str(windows)]) == 0
    assert "are credited" in capsys.readouterr().out
    _put(_internal(windows) / "planted.dll", PE)
    assert check.main(["notices_check.py", str(windows)]) == 1
    assert "planted.dll" in capsys.readouterr().err
    assert check.main(["notices_check.py"]) == 2


def test_the_installed_distributions_are_read_from_the_environment(check):
    found = check.installed()
    assert any(head.startswith("pytest ") and any(path.startswith("_pytest/") for path in paths) for head, paths in found.items())


def test_the_step_stands_on_each_leg_after_the_build_and_before_the_zip():
    at = _step_index("notices_check.py")
    assert _step_index("run: pyinstaller build.spec") < at
    assert at < _step_index("Compress-Archive")
    assert at < _step_index("run: python .github/scripts/stop_check.py")
    step = _steps()[at]
    assert "if:" not in step and "continue-on-error" not in step
    assert "shell: bash" in step and "set -eu" in step
    assert "bundle=dist/Zij\n" in step and "bundle=dist/Zij.app\n" in step
    assert 'python .github/scripts/notices_check.py "$bundle"' in step


def test_the_script_starts_nothing():
    source = (ROOT / ".github" / "scripts" / "notices_check.py").read_text(encoding="utf-8")
    for word in ("subprocess", "os.system", "popen", "urllib", "socket", "ctypes"):
        assert word not in source, word
