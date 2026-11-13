"""The built program's theme file and the tied star.

A folder uploaded as a test download keeps its dot-named folders, where the theme
file stands; a step after the build reads that file where the server reads it; a
launch that cannot read the saved colours says so in one line; and the Virgo
Cluster, whose name and designation both open whichever of its two rows the
library's sort puts first, is read by its row's number, here and by a probe on
each build leg.
"""
import dataclasses
import importlib.util
import logging
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import engine as E
from test_build_pins import _step_index, _steps

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPTS = ROOT / ".github" / "scripts"
FROM_1962 = 2437671.5      # 7 January 1962, 0h UT


def _loaded(spec):
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The theme file, read where the server reads it ------------------------------------------

THEME = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def theme():
    return _loaded(importlib.util.spec_from_file_location("theme_check", SCRIPTS / "theme_check.py"))


def _windows_bundle(tmp_path, text=THEME):
    folder = tmp_path / "Zij" / "_internal"
    (folder / ".streamlit").mkdir(parents=True)
    (folder / ".streamlit" / "config.toml").write_text(text, encoding="utf-8")
    (folder / "app.py").write_text("", encoding="utf-8")
    return tmp_path / "Zij"


def _macos_bundle(tmp_path, linked=True):
    contents = tmp_path / "Zij.app" / "Contents"
    (contents / "Resources" / ".streamlit").mkdir(parents=True)
    (contents / "Resources" / ".streamlit" / "config.toml").write_text(THEME, encoding="utf-8")
    (contents / "Resources" / "app.py").write_text("", encoding="utf-8")
    (contents / "Frameworks").mkdir()
    (contents / "Frameworks" / "app.py").symlink_to("../Resources/app.py")
    if linked:
        (contents / "Frameworks" / ".streamlit").symlink_to("../Resources/.streamlit")
    return tmp_path / "Zij.app"


def test_the_theme_passes_in_each_system_s_form(theme, tmp_path):
    assert theme.faults(_windows_bundle(tmp_path)) == []
    assert theme.faults(_macos_bundle(tmp_path)) == []


def test_the_theme_check_runs_by_hand_on_a_bundle(theme, tmp_path, capsys):
    assert theme.main(["theme_check.py", str(_windows_bundle(tmp_path))]) == 0
    assert "with both primary colours" in capsys.readouterr().out
    assert theme.main(["theme_check.py", str(tmp_path / "nothing")]) == 1


@pytest.mark.parametrize("plant", ["no file", "no bundle", "the file not where the server reads it", "no app.py beside it",
                                   "a palette's colour changed", "a palette's colour gone", "not TOML"])
def test_a_planted_theme_fault_fails(theme, tmp_path, plant):
    if plant == "no bundle":
        bundle = tmp_path / "Zij"
    elif plant == "the file not where the server reads it":
        bundle = _macos_bundle(tmp_path, linked=False)
    else:
        text = {"a palette's colour changed": THEME.replace('primaryColor = "#E3AA3E"', 'primaryColor = "#FF4B4B"'),
                "a palette's colour gone": THEME.replace('primaryColor = "#895D16"\n', ""),
                "not TOML": THEME + "\n[theme\n"}.get(plant, THEME)
        assert text != THEME or plant in ("no file", "no app.py beside it")
        bundle = _windows_bundle(tmp_path, text)
        if plant == "no file":
            (bundle / "_internal" / ".streamlit" / "config.toml").unlink()
        if plant == "no app.py beside it":
            (bundle / "_internal" / "app.py").unlink()
    assert theme.faults(bundle) != []


def test_the_source_s_two_primaries_are_the_ones_read(theme):
    held = theme._primaries(ROOT / ".streamlit" / "config.toml")
    assert set(held) == {"light", "dark"} and all(held.values()) and held["light"] != held["dark"]


@pytest.mark.parametrize("script", ["theme_check.py", "star_row_check.py"])
def test_each_new_step_reads_the_bundle_after_the_build_and_before_any_zip_or_upload(script):
    at = _step_index(f'python .github/scripts/{script} "$bundle"')
    assert _step_index("run: pyinstaller build.spec") < at < _step_index("name: Package (Windows)")
    assert at < _step_index("name: Package (macOS)") < _step_index("run: python .github/scripts/stop_check.py")
    step = _steps()[at]
    assert "if:" not in step and "continue-on-error" not in step and "set -eu" in step
    assert "bundle=dist/Zij\n" in step and "bundle=dist/Zij.app\n" in step
    assert f'python .github/scripts/{script} "$bundle"' in step


# --- The Windows zip's theme file, read from the zip's own bytes ------------------------------

def _windows_zip(path, names=("_internal/.streamlit/config.toml", "_internal/app.py"), text=THEME, sep="/"):
    import zipfile
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Zij.exe", b"")
        for name in names:
            info = zipfile.ZipInfo(name.replace("/", sep))
            archive.writestr(info, text.encode("utf-8") if name.endswith("config.toml") else b"")
    return path


def test_the_windows_zip_passes_with_the_theme_file_where_it_unpacks(theme, tmp_path, capsys):
    assert theme.zip_faults(_windows_zip(tmp_path / "Zij-windows.zip")) == []
    assert theme.main(["theme_check.py", str(tmp_path / "Zij-windows.zip")]) == 0
    assert "with both primary colours" in capsys.readouterr().out


def test_a_zip_written_with_backslashes_passes(theme, tmp_path):
    archive = _windows_zip(tmp_path / "Zij-windows.zip", sep="\\")
    import zipfile
    assert any("\\" in name for name in zipfile.ZipFile(archive).namelist())
    assert theme.zip_faults(archive) == []


@pytest.mark.parametrize("plant", ["no theme file", "the file at another place", "a primary changed", "no app.py",
                                   "not a zip", "no zip"])
def test_a_planted_windows_zip_fault_fails(theme, tmp_path, plant):
    archive = tmp_path / "Zij-windows.zip"
    if plant == "no theme file":
        _windows_zip(archive, names=("_internal/app.py",))
    elif plant == "the file at another place":
        _windows_zip(archive, names=("Zij/_internal/.streamlit/config.toml", "_internal/app.py", ".streamlit/config.toml"))
    elif plant == "a primary changed":
        _windows_zip(archive, text=THEME.replace('primaryColor = "#E3AA3E"', 'primaryColor = "#FF4B4B"'))
    elif plant == "no app.py":
        _windows_zip(archive, names=("_internal/.streamlit/config.toml",))
    elif plant == "not a zip":
        archive.write_text(THEME, encoding="utf-8")
    assert theme.zip_faults(archive) != []
    assert theme.main(["theme_check.py", str(archive)]) == 1


def test_the_windows_zip_step_runs_last_after_the_test_download_and_fails_the_job():
    steps = _steps()
    at = _step_index("python .github/scripts/theme_check.py Zij-windows.zip")
    assert at == len(steps) - 1
    assert _step_index("run: Compress-Archive") < _step_index("path: dist/Zij/") < at
    step = steps[at]
    assert "if: runner.os == 'Windows'\n" in step and "continue-on-error" not in step
    release = (WORKFLOWS / "build.yml").read_text(encoding="utf-8").split("\n  release:\n", 1)[1]
    assert "needs: build" in release


# --- The saved colours' read: a witness, and still no stop -------------------------------------

def test_a_read_that_raises_writes_one_plain_line_and_stops_nothing(monkeypatch, caplog):
    import page_colours

    def raising():
        raise PermissionError(13, "denied", "saved-folder/preferences.json")
    monkeypatch.setattr(page_colours, "_saved_choice", raising)
    monkeypatch.setattr(page_colours, "_parsed", None)
    monkeypatch.setattr(page_colours, "_showing", None)
    shown = []
    monkeypatch.setattr(page_colours, "show", shown.append)
    with caplog.at_level(logging.WARNING, logger="page_colours"):
        assert page_colours.show_the_saved_choice() is None
    assert shown == ["Light"], "an unreadable file opens Light, as no file does"
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        ("page_colours", logging.WARNING, "The saved colours were not read (PermissionError).")]


def test_a_logger_that_raises_still_stops_nothing(monkeypatch):
    import page_colours

    class Broken(logging.Handler):
        def emit(self, record):
            raise RuntimeError("the log is broken")

    def raising():
        raise ValueError("Dark")
    monkeypatch.setattr(page_colours, "_saved_choice", raising)
    monkeypatch.setattr(page_colours, "_parsed", None)
    monkeypatch.setattr(page_colours, "_showing", None)
    logger = logging.getLogger("page_colours")
    handler = Broken()
    logger.addHandler(handler)
    try:
        assert page_colours.show_the_saved_choice() is None
    finally:
        logger.removeHandler(handler)


# --- The tied star: no reading by a key two places share ---------------------------------------

def _catalogue():
    assert E._fixed_star_catalogue_ready()

    def read():
        rows = E._fixed_star_rows_read()
        return rows, E._fixed_star_shared_keys(rows), E._fixed_star_catalogue_read()
    return E._on_fixed_star_reader(read)


def reads_by_a_shared_key(stars, shared):
    """Each star whose place a key _fixed_star_shared_keys holds would read."""
    names, designations = shared
    found = []
    for star in stars:
        if star.row is not None:
            continue
        key = star.lookup or ""
        held = designations if key.startswith(",") else names
        if E._fixed_star_key_form(key.lstrip(",")) in held or not key:
            found.append(star.catalogue_name)
    return found


def test_no_star_s_reading_depends_on_a_key_two_places_share():
    rows, shared, stars = _catalogue()
    assert "virgocluster" in shared[0] and "vc" in shared[1]
    assert reads_by_a_shared_key(stars, shared) == []
    by_number = [star for star in stars if star.row is not None]
    assert [(star.catalogue_name, star.designation, star.lookup) for star in by_number] == [("Virgo Cluster", "VC", None)]
    kept = next(row for row in rows if row[0] == by_number[0].row)
    assert kept[1:3] == ("Virgo Cluster", "VC") and not E._fixed_star_is_old_row(kept)
    assert E.fixed_star_identity(by_number[0]) == "Virgo Cluster,VC"


@pytest.mark.parametrize("key", ["Virgo Cluster", ",VC", None])
def test_a_planted_reading_by_a_shared_key_is_found(key):
    _rows, shared, stars = _catalogue()
    virgo = next(star for star in stars if star.row is not None)
    planted = [dataclasses.replace(virgo, lookup=key, row=None) if star is virgo else star for star in stars]
    assert reads_by_a_shared_key(planted, shared) == ["Virgo Cluster"]


def test_every_key_a_star_is_read_by_opens_rows_that_agree_at_every_date():
    """A key more rows hold, read by a star or by Sahl's list, opens rows of one place at
    every date, so no tie can move what it reads."""
    rows, _shared, stars = _catalogue()
    keys = {E._fixed_star_key_form(name) for name, _nature in E.SAHL_FIXED_STARS}
    keys |= {E._fixed_star_key_form(star.lookup) for star in stars if star.lookup and not star.lookup.startswith(",")}
    designations = {star.lookup[1:] for star in stars if star.lookup and star.lookup.startswith(",")}
    held = {}
    for row in rows:
        if E._fixed_star_key_form(row[1]) in keys:
            held.setdefault(("name", E._fixed_star_key_form(row[1])), []).append(row[0])
        if row[2] in designations:
            held.setdefault(("designation", row[2]), []).append(row[0])
    tied = {key: numbers for key, numbers in held.items() if len(numbers) > 1}
    assert len(tied) >= 30

    def places():
        return {key: {tuple(E.swe.fixstar_ut(str(n), jd, E.swe.FLG_MOSEPH)[0][:2]) for n in numbers}
                for key, numbers in tied.items() for jd in (E.swe.julday(-3000, 1, 1, 0.0), 2451545.0, 2816787.5)}
    read = E._on_fixed_star_reader(places)
    assert {key: seen for key, seen in read.items() if len(seen) > 1} == {}


def _virgo(stars):
    return next(star for star in stars if star.catalogue_name == "Virgo Cluster")


def test_the_kept_row_s_place_does_not_move():
    stars, missing = E.fixed_star_places(FROM_1962)
    virgo = _virgo(stars)
    assert missing == {} and E.fixed_star_missing_note(missing) == ""
    assert int(virgo.longitude // 30) == 6 and int(virgo.longitude % 30) == 1 and int(virgo.longitude % 1 * 60) == 32
    assert round(virgo.latitude, 2) == 14.36


def test_a_tie_that_opens_the_old_row_by_both_keys_moves_nothing(monkeypatch):
    """The symptom forced: both keys open the old row, as on a platform whose sort goes
    the other way. The kept row still reads, at its own place, and nothing is missing."""
    before, _ = E.fixed_star_places(FROM_1962)
    real, by_number, asked = E.swe.fixstar2_ut, E.swe.fixstar_ut, []

    def tied(key, *args):
        if E._fixed_star_key_form(key.lstrip(",")) in ("virgocluster", "vc"):
            asked.append(key)
            return by_number("1333", *args)      # the old row, by the file's number
        return real(key, *args)
    monkeypatch.setattr(E.swe, "fixstar2_ut", tied)
    E._fixed_star_catalogue_read.cache_clear()
    E._fixed_star_places_at.cache_clear()
    try:
        after, missing = E.fixed_star_places(FROM_1962)
    finally:
        monkeypatch.undo()
        E._fixed_star_catalogue_read.cache_clear()
        E._fixed_star_places_at.cache_clear()
    assert asked == [] and missing == {} and len(after) == len(before)
    assert [dataclasses.astuple(star) for star in after] == [dataclasses.astuple(star) for star in before]


# --- The probe each leg runs ----------------------------------------------------------------------

def _catalogue_bundle(tmp_path, windows=True, change=None):
    folder = tmp_path / ("Zij/_internal/ephe" if windows else "Zij.app/Contents/Resources/ephe")
    folder.mkdir(parents=True)
    for name in ("sefstars.txt", "sefstars_added.txt"):
        shutil.copyfile(ROOT / "ephe" / name, folder / name)
    if not windows:
        (tmp_path / "Zij.app/Contents/Frameworks").mkdir()
        (tmp_path / "Zij.app/Contents/Frameworks/ephe").symlink_to("../Resources/ephe")
    if change:
        path = folder / "sefstars.txt"
        path.write_bytes(change(path.read_bytes()))
    return tmp_path / ("Zij" if windows else "Zij.app")


def _probe(bundle, tmp_path, patch=""):
    runner = tmp_path / "runner.py"
    runner.write_text("import importlib.util, sys\n"
                      f"spec = importlib.util.spec_from_file_location('star_row_check', {str(SCRIPTS / 'star_row_check.py')!r})\n"
                      "c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)\n"
                      f"{patch}\nsys.exit(c.main(['star_row_check.py', {str(bundle)!r}]))\n", encoding="utf-8")
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    return subprocess.run([sys.executable, "-I", str(runner)], capture_output=True, text=True, timeout=300, env=env)


@pytest.mark.parametrize("windows", [True, False], ids=["Windows", "macOS"])
def test_the_probe_passes_on_the_shipped_files_and_prints_both_keys_and_both_numbers(tmp_path, windows):
    done = _probe(_catalogue_bundle(tmp_path, windows), tmp_path)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert "star_row_check: key 'Virgo Cluster' at J2000: 182.070866 +14.362270" in lines
    assert "star_row_check: key ',VC' at J2000: 180.930115 +14.292345" in lines
    assert "star_row_check: number 12 (kept row) at J2000: 182.070866 +14.362270 Virgo Cluster,VC" in lines
    assert "star_row_check: number 1333 (old row) at J2000: 180.930115 +14.292345 Virgo Cluster,VC" in lines


def test_the_probe_passes_under_a_forced_tie_either_way(tmp_path):
    patch = ("real = c.swe.fixstar2_ut\n"
             "c.swe.fixstar2_ut = lambda key, *a: c.swe.fixstar_ut('1333', *a) if key in ('Virgo Cluster', ',VC') else real(key, *a)\n")
    done = _probe(_catalogue_bundle(tmp_path), tmp_path, patch)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert "star_row_check: key 'Virgo Cluster' at J2000: 180.930115 +14.292345" in lines
    assert "star_row_check: key ',VC' at J2000: 180.930115 +14.292345" in lines


def test_the_probe_s_marks_are_the_engine_s():
    probe = _loaded(importlib.util.spec_from_file_location("star_row_check", SCRIPTS / "star_row_check.py"))
    assert (probe.NAME, probe.DESIGNATION, probe.OLD_LONGITUDE) == E.FIXED_STAR_OLD_ROW
    assert probe.OTHER_DATE == FROM_1962 == E.swe.julday(1962, 1, 7, 0.0)


KEPT = b"Virgo Cluster,VC,2000,12,30,47.3"
OLD = b"Virgo Cluster,VC,2000,12,26,32.1"


def _without_the_kept(data):
    lines = data.split(b"\n")
    return b"\n".join(line for line in lines if not line.startswith(KEPT))


def _rows_exchanged(data):
    lines = data.split(b"\n")
    a = next(i for i, line in enumerate(lines) if line.startswith(KEPT))
    b = next(i for i, line in enumerate(lines) if line.startswith(OLD))
    lines[a], lines[b] = lines[b], lines[a]
    return b"\n".join(lines)


def test_the_probe_follows_the_kept_row_when_the_rows_are_exchanged(tmp_path):
    done = _probe(_catalogue_bundle(tmp_path, change=_rows_exchanged), tmp_path)
    assert done.returncode == 0, done.stderr
    assert "star_row_check: number 1333 (kept row) at J2000: 182.070866 +14.362270 Virgo Cluster,VC" in done.stdout.splitlines()


@pytest.mark.parametrize("plant", ["no catalogue", "the kept row gone", "the number refused", "the number opens another row",
                                   "the number opens the old row's place"])
def test_a_planted_probe_fault_fails(tmp_path, plant):
    bundle = _catalogue_bundle(tmp_path, change=_without_the_kept if plant == "the kept row gone" else None)
    patch = ""
    if plant == "no catalogue":
        shutil.rmtree(bundle / "_internal" / "ephe")
    elif plant == "the number refused":
        patch = "real = c.swe.fixstar_ut\ndef f(s, *a):\n    if s == '12': raise c.swe.Error('refused')\n    return real(s, *a)\nc.swe.fixstar_ut = f\n"
    elif plant == "the number opens another row":
        patch = "real = c.swe.fixstar_ut\nc.swe.fixstar_ut = lambda s, *a: real('13' if s == '12' else s, *a)\n"
    elif plant == "the number opens the old row's place":
        patch = "real = c.swe.fixstar_ut\nc.swe.fixstar_ut = lambda s, *a: real('1333' if s == '12' else s, *a)\n"
    done = _probe(bundle, tmp_path, patch)
    assert done.returncode == 1 and "star_row_check: " in done.stderr, (done.stdout, done.stderr)
