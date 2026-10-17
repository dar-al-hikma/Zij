"""Which time-zone database the app reads (the owner's ruling 71, lane TZ).

The app reads time zones only from its pinned ``tzdata`` package, on every
platform, never the computer's own database: ``zoneinfo`` searches the
directories on its path (the system's files, on Linux and macOS) before the
package, so the engine, the app and the desktop launcher empty that path
before any zone is made. The pin is the newest IANA release a package exists
for, and ``timezonefinder-data``, the boundary polygons the place lookup
answers from, is pinned beside it.

A computer's own database is stood in for by a planted directory on
``zoneinfo``'s search path: its Europe/Rome is Asia/Karachi's record (+05:00,
PKT, in 1980) and its version line names a release no package has.
"""
from __future__ import annotations

import ast
import importlib.metadata
import importlib.resources
import json
import os
import re
import subprocess
import sys
import textwrap
import zoneinfo
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import engine
from conftest import assert_no_exception, make_app

ROOT = Path(__file__).resolve().parent.parent
STD = "Standard time (named zone)"
JANUARY = datetime(2026, 1, 17, 12, 34, 56, tzinfo=timezone.utc)   # 13:34:56 CET at Florence
PLANTED_RELEASE = "1999z"


def _package_file(name):
    return importlib.resources.files("tzdata").joinpath("zoneinfo", *name.split("/"))


def _state(zone, *local):
    moment = datetime(*local, tzinfo=zone)
    return [int(moment.utcoffset().total_seconds()), moment.tzname()]


def _package_state(name, *local):
    """The offset and abbreviation the tzdata package's own file gives."""
    with _package_file(name).open("rb") as handle:
        return _state(ZoneInfo.from_file(handle, key=name), *local)


def _planted(tmp_path):
    """A directory standing in for the computer's own database."""
    root = tmp_path / "system_zoneinfo"
    (root / "Europe").mkdir(parents=True)
    (root / "Europe" / "Rome").write_bytes(_package_file("Asia/Karachi").read_bytes())
    (root / "tzdata.zi").write_text(f"# version {PLANTED_RELEASE}\n", encoding="utf-8")
    with (root / "Europe" / "Rome").open("rb") as handle:
        planted = _state(ZoneInfo.from_file(handle, key="Europe/Rome"), 1980, 1, 15, 12)
    # The doctored zone is one a reader would see: its answer is not the package's.
    assert planted == [18000, "PKT"] != _package_state("Europe/Rome", 1980, 1, 15, 12), planted
    return root


def _version_line(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("# version "):
            return line.split()[2]
    raise AssertionError(f"{path} has no version line")


def _release_read(tzpath):
    """The release of the database zoneinfo reads under `tzpath`, in its own
    order: a directory on the search path first, else the tzdata package."""
    for root in tzpath:
        if Path(root, "tzdata.zi").is_file():
            return _version_line(Path(root, "tzdata.zi"))
    return _version_line(str(_package_file("tzdata.zi")))


def _run_python(code, tmp_path, tzpath):
    """`code` in a fresh interpreter started with `tzpath` as its zone search
    path (what a computer's own database is to zoneinfo); its last line of
    output is JSON."""
    env = dict(os.environ, PYTHONTZPATH=str(tzpath), XDG_DATA_HOME=str(tmp_path / "xdg"))
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


class _PlantedSearchPath:
    """The running process's zone search path pointed at `root`, and back."""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        self.saved = zoneinfo.TZPATH
        zoneinfo.reset_tzpath(to=[str(self.root)])
        ZoneInfo.clear_cache()
        assert _state(ZoneInfo("Europe/Rome"), 1980, 1, 15, 12) == [18000, "PKT"]
        return self

    def __exit__(self, *exc):
        zoneinfo.reset_tzpath(to=list(self.saved))
        ZoneInfo.clear_cache()
        return False


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return tmp_path


def test_the_engine_reads_its_zones_from_the_package_whatever_the_system_has(tmp_path):
    planted = _planted(tmp_path)
    got = _run_python("""
        import json
        from datetime import datetime
        from zoneinfo import ZoneInfo
        def state(zone):
            moment = datetime(1980, 1, 15, 12, tzinfo=zone)
            return [int(moment.utcoffset().total_seconds()), moment.tzname()]
        # Uncached, then cached: a zone made before the engine is imported.
        system = state(ZoneInfo.no_cache("Europe/Rome"))
        made_before = ZoneInfo("Europe/Rome")
        import engine
        read = engine.named_zone_state("Europe/Rome", 1980, 1, 15, 12, 0, 0)
        print(json.dumps({"system": system, "engine": [read["offset_seconds"], read["abbreviation"]],
                          "process": state(ZoneInfo("Europe/Rome"))}))
    """, tmp_path, planted)
    package = _package_state("Europe/Rome", 1980, 1, 15, 12)
    assert package == [3600, "CET"], package
    assert got["system"] == [18000, "PKT"], got
    assert got["engine"] == package, got
    # Every zone made in the process after the engine is imported is the package's too.
    assert got["process"] == package, got


def test_the_apps_zone_reads_are_the_packages_whatever_the_system_has(tmp_path, prefs_on, monkeypatch):
    """The sidebar's named zone and Here & Now's own zone, with the process's
    search path pointed at the planted database before the app runs."""
    at = make_app(date="1980-01-15", page="chart")
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["time_standard_key"] = STD
    at.session_state["home_place"] = {"label": "Florence", "lat": 43.7792, "lon": 11.2463}
    monkeypatch.setattr(engine, "now_utc", lambda: JANUARY)
    package = _package_state("Europe/Rome", 1980, 1, 15, 12)
    assert package == [3600, "CET"], package
    with _PlantedSearchPath(_planted(tmp_path)):
        at.run()
        assert_no_exception(at, "1980-01-15 Florence, standard time")
        infos = "\n".join(n.value for n in at.sidebar.info)
        assert "**Europe/Rome** · UTC offset +01:00 (CET)" in infos, infos
        at.sidebar.button(key="_here_and_now").click().run()
        assert_no_exception(at, "here and now")
        assert at.session_state["time_input_key"] == time(13, 34, 56)
        assert at.session_state["time_standard_key"] == STD
        infos = "\n".join(n.value for n in at.sidebar.info)
        assert "**Europe/Rome** · UTC offset +01:00 (CET)" in infos, infos


def test_the_zone_database_read_is_the_pinned_packages_release_whatever_the_system_has(tmp_path):
    import tzdata

    planted = _planted(tmp_path)
    assert _release_read([planted]) == PLANTED_RELEASE
    # The engine, in a fresh interpreter whose search path is the planted database.
    tzpath = _run_python("""
        import json, zoneinfo
        import engine
        print(json.dumps(list(zoneinfo.TZPATH)))
    """, tmp_path, planted)
    assert _release_read(tzpath) == tzdata.IANA_VERSION, tzpath
    # The app, run in this process with its search path pointed there.
    at = make_app(page="chart")
    with _PlantedSearchPath(planted):
        at.run()
        assert_no_exception(at, "the app's own run")
        assert _release_read(zoneinfo.TZPATH) == tzdata.IANA_VERSION, zoneinfo.TZPATH

    # The package is the pin, and the comment over the pin names its IANA release.
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = re.findall(r"^tzdata==(\S+)\s*$", requirements, re.MULTILINE)
    assert pins == [importlib.metadata.version("tzdata")], pins
    lines = requirements.splitlines()
    at_pin = lines.index(f"tzdata=={pins[0]}")
    above = []
    for line in reversed(lines[:at_pin]):
        if not line.startswith("#"):
            break
        above.append(line)
    assert re.search(rf"\bIANA\b.*\b{tzdata.IANA_VERSION}\b", " ".join(reversed(above))), above
    assert _version_line(str(_package_file("tzdata.zi"))) == tzdata.IANA_VERSION


def test_the_boundary_data_is_pinned_at_the_version_installed_and_tested():
    from packaging.requirements import Requirement
    import timezonefinder.configs
    import timezonefinder_data

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = re.findall(r"^timezonefinder-data==(\S+)\s*$", requirements, re.MULTILINE)
    assert pins == [importlib.metadata.version("timezonefinder-data")], pins
    # Beside the finder it serves, and the data that finder reads.
    finder = re.findall(r"^timezonefinder==(\S+)\s*$", requirements, re.MULTILINE)
    assert finder == [importlib.metadata.version("timezonefinder")], finder
    assert Path(timezonefinder.configs.DEFAULT_DATA_DIR) == Path(timezonefinder_data.DATA_DIR)
    assert timezonefinder_data.__version__ == pins[0]
    wanted = [Requirement(r) for r in importlib.metadata.requires("timezonefinder")
              if Requirement(r).name == "timezonefinder-data"]
    assert len(wanted) == 1 and wanted[0].specifier.contains(pins[0]), wanted


def test_the_desktop_launcher_reads_the_package_and_the_build_carries_it(tmp_path):
    planted = _planted(tmp_path)
    got = _run_python("""
        import json, runpy, sys, types, zoneinfo
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # The window library is not needed to run the module's top level.
        sys.modules["webview"] = types.ModuleType("webview")
        runpy.run_path("desktop_launcher.py", run_name="desktop_launcher")
        moment = datetime(1980, 1, 15, 12, tzinfo=ZoneInfo("Europe/Rome"))
        print(json.dumps({"tzpath": list(zoneinfo.TZPATH),
                          "rome": [int(moment.utcoffset().total_seconds()), moment.tzname()]}))
    """, tmp_path, planted)
    assert got == {"tzpath": [], "rome": _package_state("Europe/Rome", 1980, 1, 15, 12)}, got
    # The desktop build collects the package whole: its zone files are the
    # package's data, each folder a subpackage zoneinfo opens as a resource.
    # So too the zone boundaries, whose distribution is a top-level package of
    # its own that collect_all("timezonefinder") does not reach: the build
    # names every top-level package of both pinned data distributions itself.
    tree = ast.parse((ROOT / "build.spec").read_text(encoding="utf-8"))
    collected = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and [getattr(t, "id", None) for t in node.targets] == ["collect_pkgs"]]
    assert len(collected) == 1 and "tzdata" in collected[0], collected
    tops = {top for top, dists in importlib.metadata.packages_distributions().items()
            if {"tzdata", "timezonefinder-data"} & set(dists)}
    assert tops == {"tzdata", "timezonefinder_data"}, tops
    assert tops <= set(collected[0]), (tops, collected)
    loops = [node for node in tree.body if isinstance(node, ast.For) and getattr(node.iter, "id", None) == "collect_pkgs"]
    assert len(loops) == 1 and "collect_all(pkg)" in ast.unparse(loops[0]), [ast.unparse(n) for n in loops]
