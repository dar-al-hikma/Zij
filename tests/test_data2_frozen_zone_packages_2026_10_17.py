"""The zone packages' digest in a frozen build's layout (time_zones.py's
zone_package_digest).

A PyInstaller build puts a package's Python modules in its archive and its
data files on disk, in the folder sys._MEIPASS names: beside the program on
Windows (_internal/), and on macOS in the application bundle's Resources
folder, linked into Frameworks, where sys._MEIPASS points. The digest reads
the folder of the package's own file, the folder importlib.resources gives
for it (and zoneinfo reads each zone through), and leaves the modules out, so
it is the recorded one in either layout, and a byte changed on disk there is
refused.

Emulated, not built: in a fresh interpreter a finder placed first on
sys.meta_path serves tzdata and timezonefinder_data (and their subpackages)
from their source text, as the archive serves modules, with each package's
folder on disk in the layout under test; the data files are copied there, no
module file. Each module's attributes are set as PyInstaller 6.22.3's frozen
importer (PyInstaller/loader/pyimod02_importers.py) sets them: the loader's
path is sys._MEIPASS joined with the module's dotted name, "__init__.py" for a
package (".py" for a module), whether or not that file exists; the spec's
origin is that path, with a location, so __file__ is it; a package's search
locations, and so its __path__, are that file's folder; and its resource
reader's folder is the same, the loader path's parent. macOS links the
package folders whole (a folder of data alone is linked at its level); the
layout linking each entry one by one is kept as the harder case.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TIMEOUT = 300

ARCHIVE = textwrap.dedent('''
    import importlib.abc, importlib.machinery, importlib.resources, json, os, sys
    from pathlib import Path
    meipass, sources = {meipass!r}, {sources!r}

    class Reader:
        """PyiFrozenResourceReader: the folder of the loader's path."""
        def __init__(self, loader):
            self.path = Path(loader.path).parent

        def files(self):
            return self.path

    class Loader(importlib.abc.Loader):
        """PyiFrozenLoader: one per module, its path where the module's file
        would lie under sys._MEIPASS."""
        def __init__(self, name, package):
            self.name = name
            parts = name.split('.')
            self.path = (os.path.join(meipass, *parts, '__init__.py') if package
                         else os.path.join(meipass, *parts) + '.py')

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            spec = module.__spec__
            assert hasattr(module, '__file__')          # set by the import machinery from the origin
            if spec.submodule_search_locations is not None:
                module.__path__ = spec.submodule_search_locations
            source = os.path.join(sources, *spec.name.split('.'))
            source = os.path.join(source, '__init__.py') if os.path.isdir(source) else source + '.py'
            exec(compile(open(source, encoding='utf-8').read(), module.__file__, 'exec'), module.__dict__)

        def get_resource_reader(self, name):
            return Reader(self)

    class Archive(importlib.abc.MetaPathFinder):
        """PyiFrozenFinder.find_spec for a module found in the archive."""
        def find_spec(self, name, path=None, target=None):
            if name.split('.')[0] not in ('tzdata', 'timezonefinder_data'):
                return None
            source = os.path.join(sources, *name.split('.'))
            package = os.path.isdir(source)
            if not package and not os.path.isfile(source + '.py'):
                return None
            loader = Loader(name, package)
            spec = importlib.machinery.ModuleSpec(name, loader, is_package=package, origin=loader.path)
            spec.has_location = True
            if package:
                spec.submodule_search_locations = [os.path.dirname(spec.origin)]
            return spec

    sys.meta_path.insert(0, Archive())
    sys.path.insert(0, {root!r})
    import time_zones as tz
    from timezonefinder import TimezoneFinder
    import tzdata
    out = {{'tzdata_file': tzdata.__file__, 'digests': {{}}, 'folders': {{}}}}
    for name in ('tzdata', 'timezonefinder_data', 'tzdata.zoneinfo.Europe'):
        module = importlib.import_module(name)
        out['folders'][name] = [str(importlib.resources.files(name)), os.path.dirname(module.__file__),
                                *module.__path__]
    for name, (import_name, _version, count, recorded) in tz.ZONE_PACKAGES.items():
        out['digests'][name] = list(tz.zone_package_digest(import_name)) == [count, recorded]
    try:
        out['rome'] = tz.named_zone_state('Europe/Rome', 1990, 6, 15, 12, 0, 0)['offset_seconds']
        out['florence'] = tz.place_zone(43.77925, 11.24626, TimezoneFinder(), (1990, 6, 15, 12, 0, 0))
    except tz.ShippedDataChanged as refusal:
        out['refused'] = str(refusal)
    print(json.dumps(out))
''')


def _site():
    import tzdata
    return Path(tzdata.__file__).resolve().parents[1]


def _data_only(package, dest):
    """The package's files on disk as a build leaves them: its data, no module."""
    source = _site() / package
    for folder, subs, names in os.walk(source):
        subs[:] = [s for s in subs if s != "__pycache__"]
        rel = Path(folder).relative_to(source)
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for name in names:
            if not name.endswith((".py", ".pyc")):
                shutil.copy2(Path(folder) / name, dest / rel / name)


def _layout(tmp_path, kind):
    """The bundle's folder sys._MEIPASS names, laid out as `kind` lays it."""
    if kind == "windows":
        meipass = tmp_path / "Zij" / "_internal"
        for package in ("tzdata", "timezonefinder_data"):
            _data_only(package, meipass / package)
        return meipass
    contents = tmp_path / "Zij.app" / "Contents"
    meipass, resources = contents / "Frameworks", contents / "Resources"
    meipass.mkdir(parents=True)
    for package in ("tzdata", "timezonefinder_data"):
        _data_only(package, resources / package)
        if kind == "macos":                           # the package's folder linked whole
            (meipass / package).symlink_to(Path("..") / "Resources" / package)
        else:                                         # each of its folders and files linked one by one
            (meipass / package).mkdir()
            for entry in sorted((resources / package).iterdir()):
                (meipass / package / entry.name).symlink_to(Path("..") / ".." / "Resources" / package / entry.name)
    return meipass


def _run(tmp_path, meipass):
    from conftest import EXECUTABLE_DIR
    script = ARCHIVE.format(meipass=str(meipass), sources=str(_site()), root=str(EXECUTABLE_DIR))
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=TIMEOUT,
                          cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("kind", ["windows", "macos", "macos, each folder linked"])
def test_the_digest_is_the_recorded_one_in_a_frozen_layout_and_zones_are_read(tmp_path, kind):
    meipass = _layout(tmp_path, kind)
    got = _run(tmp_path, meipass)
    assert got["tzdata_file"] == str(meipass / "tzdata" / "__init__.py")
    assert not (meipass / "tzdata" / "__init__.py").exists()
    # importlib.resources' folder, __file__'s and __path__, each the module's own under sys._MEIPASS
    assert got["folders"] == {name: [str(meipass.joinpath(*name.split(".")))] * 3
                              for name in ("tzdata", "timezonefinder_data", "tzdata.zoneinfo.Europe")}
    assert got["digests"] == {"tzdata": True, "timezonefinder-data": True}
    assert (got.get("rome"), got.get("florence"), got.get("refused")) == (7200, "Europe/Rome", None)


@pytest.mark.parametrize("kind", ["windows", "macos", "macos, each folder linked"])
@pytest.mark.parametrize("package, rel", [("tzdata", "zoneinfo/Europe/Rome"),
                                          ("timezonefinder_data", "data/timezone_names.txt")])
def test_a_byte_changed_in_a_frozen_layout_is_refused(tmp_path, kind, package, rel):
    meipass = _layout(tmp_path, kind)
    target = (meipass / package / rel).resolve()
    data = bytearray(target.read_bytes())
    data[-2] ^= 0x01
    target.write_bytes(bytes(data))
    got = _run(tmp_path, meipass)
    name = {"tzdata": "tzdata", "timezonefinder_data": "timezonefinder-data"}[package]
    assert got["digests"][name] is False
    assert got["refused"].startswith(f"the {name} package's data files are not those this program was built with")


# --- Each real folder once -----------------------------------------------------

def _digest_of(monkeypatch, root):
    """time_zones.zone_package_digest over a stand-in tzdata whose file lies
    in `root`."""
    import types

    import time_zones
    monkeypatch.setattr(time_zones, "_zone_package",
                        lambda name: types.SimpleNamespace(__file__=str(root / "__init__.py")))
    return time_zones.zone_package_digest("tzdata")


def _stand_in_package(root):
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "zones.txt").write_text("a zone\n")
    (root / "sub").mkdir()
    (root / "sub" / "rome").write_bytes(b"Rome's record")


def test_the_walk_reads_each_real_folder_once(monkeypatch, tmp_path):
    """A link back to the package's own folder and a second link to a folder
    already read (named to be read after it) add nothing: the digest is the
    one of the same package without them, of its two data files."""
    import hashlib
    plain, linked = tmp_path / "plain" / "tzdata", tmp_path / "linked" / "tzdata"
    _stand_in_package(plain)
    _stand_in_package(linked)
    (linked / "back").symlink_to(".")
    (linked / "sub_again").symlink_to("sub")
    rows = "".join(f"{path}\t{hashlib.sha256(data).hexdigest()}\n" for path, data in
                   [("tzdata/sub/rome", b"Rome's record"), ("tzdata/zones.txt", b"a zone\n")])
    expected = (2, hashlib.sha256(rows.encode("utf-8")).hexdigest())
    assert _digest_of(monkeypatch, plain) == expected
    assert _digest_of(monkeypatch, linked) == expected
