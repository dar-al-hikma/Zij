"""The data the program ships, refused as it runs where its bytes are not the
ones it was built with (time_zones.py's SHIPPED_DATA_SHA256 and ZONE_PACKAGES,
the record tests/test_shipped_data_hashes_2026_10_13.py reads too).

Each refusal is where a missing or malformed file already refused: the four
tables read at time_zones.py's import stop the import, naming the file; the
atlas is refused at the lookup, and the page says so as it says a missing
atlas; each zone package is refused at its first use in the process, naming
the package and the version it gives (or saying it gives none). Every case
runs in a scratch copy: the program's files copied (or a zone package rebuilt
of links to the installed files, the one file changed copied) and imported in
a fresh interpreter, so nothing here touches the installed packages or the
tree.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import APP_PATH, small_atlas_copy, ui_source

ROOT = APP_PATH.parent
TIMEOUT = 300
CHANGED_SENTENCE = ("The offline place atlas is not the one this app supplies, so no city can be looked up. "
                    "Enter the place's latitude and longitude instead.")


def _tree(tmp_path, *extra):
    """A scratch copy of the zone code and the files it reads beside itself."""
    tree = tmp_path / "tree"
    tree.mkdir()
    shutil.copy2(ROOT / "time_zones.py", tree)
    shutil.copytree(ROOT / "data", tree / "data")
    for name in extra:
        shutil.copy2(ROOT / name, tree / name)
    return tree


def _change_one_byte(path, old: bytes, new: bytes):
    """One byte of a text file changed, the file still well formed."""
    data = path.read_bytes()
    assert len(old) == len(new) and sum(a != b for a, b in zip(old, new)) == 1 and data.count(old) >= 1
    path.write_bytes(data.replace(old, new, 1))


def _run(tree, code, *first_on_path):
    """`code` in a fresh interpreter (-I: no user site, no PYTHON* variables),
    with `first_on_path` and then the tree first on sys.path."""
    prelude = f"import sys; sys.path[:0] = {[str(p) for p in first_on_path] + [str(tree)]!r}\n"
    return subprocess.run([sys.executable, "-I", "-c", prelude + code], cwd=tree, capture_output=True,
                          text=True, timeout=TIMEOUT)


# --- The four tables read at the import --------------------------------------------

TABLES = {
    "data/place_zones.tsv": (b"# Hand-kept.", b"# Hand-kepT."),
    "data/place_clocks.tsv": (b"never edited by hand.", b"never edited by hanD."),
    "data/place_clock_sources.tsv": (b"never edited by hand.", b"never edited by hanD."),
    "data/mean_time_outlines.json": (b"modified application data", b"modified application datA"),
}


@pytest.mark.parametrize("name", sorted(TABLES))
def test_a_table_changed_by_one_byte_stops_the_import_naming_it(tmp_path, name):
    tree = _tree(tmp_path)
    _change_one_byte(tree / name, *TABLES[name])
    done = _run(tree, "import time_zones")
    assert done.returncode != 0, done.stdout
    assert f"ShippedDataChanged: {name} is not the file this program was built with" in done.stderr, done.stderr


def test_the_honest_tables_import_and_give_the_same_tables(tmp_path):
    tree = _tree(tmp_path)
    code = ("import time_zones as tz, json\n"
            "print(json.dumps([len(tz.PLACE_ZONES), sorted(tz.MEAN_TIME_EXCEPTIONS), sorted(tz.MEAN_TIME_CITY_DATES),"
            " sorted(tz.MEAN_TIME_OUTSIDE), len(tz.PLACE_CLOCKS), sorted(tz.PRE1970_SOURCES)]))")
    done = _run(tree, code)
    assert done.returncode == 0, done.stderr
    import time_zones as tz
    assert done.stdout.strip() == __import__("json").dumps(
        [len(tz.PLACE_ZONES), sorted(tz.MEAN_TIME_EXCEPTIONS), sorted(tz.MEAN_TIME_CITY_DATES),
         sorted(tz.MEAN_TIME_OUTSIDE), len(tz.PLACE_CLOCKS), sorted(tz.PRE1970_SOURCES)])


@pytest.mark.parametrize("name", sorted(TABLES))
@pytest.mark.parametrize("damage", ["empty", "truncated", "longer", "folder", "link to the honest file"])
def test_a_damaged_table_stops_the_import_and_a_link_to_the_honest_one_does_not(tmp_path, name, damage):
    tree = _tree(tmp_path)
    path, honest = tree / name, (ROOT / name).read_bytes()
    if damage == "empty":
        path.write_bytes(b"")
    elif damage == "truncated":
        path.write_bytes(honest[:-1])
    elif damage == "longer":
        path.write_bytes(honest + b"\n")
    elif damage == "folder":
        path.unlink()
        path.mkdir()
    else:
        path.unlink()
        path.symlink_to(ROOT / name)
    done = _run(tree, "import time_zones")
    if damage == "link to the honest file":
        assert done.returncode == 0, done.stderr
    elif damage == "folder":
        assert done.returncode != 0 and ("IsADirectoryError" in done.stderr or "PermissionError" in done.stderr)
    else:
        assert done.returncode != 0
        assert f"ShippedDataChanged: {name} is not the file this program was built with" in done.stderr


# --- The atlas, at the lookup ------------------------------------------------------

def _moved_florence(path):
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE places SET lat = 40.71427, lon = -74.00597 WHERE geonameid = 3176959")
    conn.close()


@pytest.mark.parametrize("damage", ["a row moved", "one byte", "empty", "truncated", "longer", "folder"])
def test_a_changed_atlas_is_refused_at_the_lookup_naming_it(tmp_path, damage, small_atlas_recorded):
    """Each damage done to a copy of the small atlas made from the shipped
    one, recorded for this test; an undamaged copy beside it is read."""
    import time_zones as tz
    undamaged = small_atlas_copy(small_atlas_recorded, tmp_path / "undamaged" / "atlas.db")
    assert ("Florence", "16", "IT", 43.77925, 11.24626) in tz.atlas_rows(undamaged, "Florence")
    copy = small_atlas_copy(small_atlas_recorded, tmp_path / "atlas.db")
    if damage == "a row moved":
        _moved_florence(copy)
    elif damage == "one byte":
        data = bytearray(copy.read_bytes())
        data[len(data) // 2] ^= 0x01
        copy.write_bytes(bytes(data))
    elif damage == "empty":
        copy.write_bytes(b"")
    elif damage == "truncated":
        copy.write_bytes(copy.read_bytes()[:-4096])
    elif damage == "longer":
        copy.write_bytes(copy.read_bytes() + b"\0" * 4096)
    else:
        copy.unlink()
        copy.mkdir()
    with pytest.raises(tz.ShippedDataChanged, match=r"^atlas\.db (is not the file this program was built with|"
                                                     r"cannot be read as a file)"):
        tz.atlas_rows(copy, "Florence")


def test_the_honest_atlas_and_a_link_to_it_answer_as_before(tmp_path):
    import time_zones as tz
    link = tmp_path / "atlas.db"
    link.symlink_to(ROOT / "atlas.db")
    for path in (ROOT / "atlas.db", link):
        rows = tz.atlas_rows(path, "Florence")
        assert ("Florence", "16", "IT", 43.77925, 11.24626) in rows


def _lifted_lookup(app_file):
    """app.py's _atlas_matches and its ATLAS_ sentences, by their source,
    beside `app_file` (as test_atlas1_atlas_open_and_page lifts them)."""
    import time_zones as tz
    source = ui_source()
    space = {"Path": Path, "__file__": str(app_file), "atlas_rows": tz.atlas_rows,
             "ShippedDataChanged": tz.ShippedDataChanged, "degrees_text": lambda v, p: f"{v:.{p}f}"}
    for node in ast.parse(source).body:
        if (isinstance(node, ast.FunctionDef) and node.name == "_atlas_matches") or (
                isinstance(node, ast.Assign) and any(getattr(t, "id", "").startswith("ATLAS_") for t in node.targets)):
            exec(ast.get_source_segment(source, node), space)
    return space


def test_the_page_says_the_atlas_is_not_the_one_supplied_and_offers_the_coordinates(tmp_path, small_atlas_recorded):
    """A copy of the small atlas made from the shipped one, recorded for this
    test, with Florence moved; an undamaged copy beside it is offered."""
    undamaged = small_atlas_copy(small_atlas_recorded, tmp_path / "undamaged" / "atlas.db")
    assert _lifted_lookup(undamaged.parent / "app.py")["_atlas_matches"]("Florence")[0]
    small_atlas_copy(small_atlas_recorded, tmp_path / "atlas.db")
    _moved_florence(tmp_path / "atlas.db")
    space = _lifted_lookup(tmp_path / "app.py")
    assert space["ATLAS_CHANGED_MESSAGE"] == CHANGED_SENTENCE
    assert space["_atlas_matches"]("Florence") == (None, CHANGED_SENTENCE)
    for word in ("atlas.db", ".db", "SHA", "hash", "folder", "built", "Please", "`"):
        assert word not in CHANGED_SENTENCE, word


def test_the_changed_atlas_sentence_is_shown_as_the_missing_one_is():
    """The sidebar's branch that shows a missing atlas as an error shows the
    changed one the same way."""
    tree = ast.parse(ui_source())
    tests = [ast.unparse(n.test) for n in ast.walk(tree) if isinstance(n, ast.If)
             and "ATLAS_MISSING_MESSAGE" in ast.unparse(n.test)]
    assert tests == ["location_error in (ATLAS_MISSING_MESSAGE, ATLAS_CHANGED_MESSAGE)"], tests


# --- The zone packages, at their first use ---------------------------------------------

def _site_packages():
    import tzdata
    return Path(tzdata.__file__).resolve().parents[1]


def _linked_package(site, import_name, dist_info):
    """The installed package and its metadata folder rebuilt under `site`,
    each file a link to the installed one."""
    real = _site_packages()
    for top in (import_name, dist_info):
        for folder, _subs, names in os.walk(real / top):
            rel = Path(folder).relative_to(real)
            (site / rel).mkdir(parents=True, exist_ok=True)
            for name in names:
                (site / rel / name).symlink_to(Path(folder) / name)


def _replace(site, rel, data: bytes):
    path = site / rel
    path.unlink()
    path.write_bytes(data)


def _set_version(site, package, version):
    """The package's own __version__ set to `version`, or its line taken out
    (None); its distribution's metadata left as installed, so a refusal that
    names the metadata's version is told from one that names the package's."""
    init = (site / package / "__init__.py").read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^__version__ = .*$", init)) == 1, init
    line = "" if version is None else f"__version__ = {version!r}"
    _replace(site, f"{package}/__init__.py", re.sub(r"(?m)^__version__ = .*$", line, init).encode("utf-8"))


ZONE_STATE = ("import time_zones as tz\n"
              "try:\n"
              "    state = tz.named_zone_state('Europe/Rome', 1990, 6, 15, 12, 0, 0)\n"
              "except tz.ShippedDataChanged as refusal:\n"
              "    print('REFUSED', refusal)\n"
              "else:\n"
              "    print('ACCEPTED', state['offset_seconds'])\n")
PLACE_ZONE = ("import time_zones as tz\n"
              "from timezonefinder import TimezoneFinder\n"
              "finder = TimezoneFinder()\n"
              "try:\n"
              "    zones = [tz.place_zone(lat, lon, finder, (1990, 6, 15, 12, 0, 0))\n"
              "             for lat, lon in ((43.77925, 11.24626), (48.85341, 2.3488))]\n"
              "except tz.ShippedDataChanged as refusal:\n"
              "    print('REFUSED', refusal)\n"
              "else:\n"
              "    print('ACCEPTED', *zones)\n")


def _tzdata(tmp_path):
    import tzdata
    site = tmp_path / "site"
    _linked_package(site, "tzdata", f"tzdata-{tzdata.__version__}.dist-info")
    return site, f"tzdata-{tzdata.__version__}.dist-info"


def _boundaries(tmp_path):
    import importlib.metadata
    site = tmp_path / "site"
    dist_info = f"timezonefinder_data-{importlib.metadata.version('timezonefinder-data')}.dist-info"
    _linked_package(site, "timezonefinder_data", dist_info)
    return site, dist_info


def test_the_honest_zone_packages_give_every_value_as_before(tmp_path):
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _boundaries(tmp_path)
    assert _run(tree, ZONE_STATE, site).stdout.split() == ["ACCEPTED", "7200"]
    assert _run(tree, PLACE_ZONE, site).stdout.split() == ["ACCEPTED", "Europe/Rome", "Europe/Paris"]


def test_a_time_zone_database_changed_under_its_version_is_refused_naming_it(tmp_path):
    """Rome's record replaced by Tokyo's, a well-formed file (which gave
    Rome +09:00 unseen)."""
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _replace(site, "tzdata/zoneinfo/Europe/Rome", (_site_packages() / "tzdata/zoneinfo/Asia/Tokyo").read_bytes())
    out = _run(tree, ZONE_STATE, site).stdout
    assert out.startswith("REFUSED the tzdata package's data files are not those this program was built with "
                          "(tzdata 2026.5 is installed; 2026.5's were recorded)"), out


def test_a_time_zone_database_of_another_version_is_refused_naming_that_version(tmp_path):
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _replace(site, "tzdata/zoneinfo/Europe/Rome", (_site_packages() / "tzdata/zoneinfo/Asia/Tokyo").read_bytes())
    _set_version(site, "tzdata", "2027.1")
    out = _run(tree, ZONE_STATE, site).stdout
    assert out.startswith("REFUSED the tzdata package's data files are not those this program was built with "
                          "(tzdata 2027.1 is installed; 2026.5's were recorded)"), out


def test_a_time_zone_database_that_names_no_version_is_refused_saying_so(tmp_path):
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _replace(site, "tzdata/zoneinfo/Europe/Rome", (_site_packages() / "tzdata/zoneinfo/Asia/Tokyo").read_bytes())
    _set_version(site, "tzdata", None)
    out = _run(tree, ZONE_STATE, site).stdout
    assert out.startswith("REFUSED the tzdata package's data files are not those this program was built with "
                          "(the tzdata installed does not name its version; 2026.5's were recorded), "
                          "so no zone is read from it"), out


def test_a_version_label_alone_moved_is_not_refused(tmp_path):
    """The data is what is checked: the same files under another version's
    label give the same zones."""
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _set_version(site, "tzdata", "2027.1")
    assert _run(tree, ZONE_STATE, site).stdout.split() == ["ACCEPTED", "7200"]


@pytest.mark.parametrize("damage", ["a file added", "a file removed", "a file emptied"])
def test_a_time_zone_database_with_a_file_added_removed_or_emptied_is_refused(tmp_path, damage):
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    if damage == "a file added":
        (site / "tzdata/zoneinfo/Europe/Atlantis").write_bytes((_site_packages() / "tzdata/zoneinfo/UTC").read_bytes())
    elif damage == "a file removed":
        (site / "tzdata/zoneinfo/Europe/Vaduz").unlink()
    else:
        _replace(site, "tzdata/zoneinfo/Europe/Vaduz", b"")
    assert _run(tree, ZONE_STATE, site).stdout.startswith("REFUSED the tzdata package's data files")


def test_zone_boundaries_changed_under_their_version_are_refused_naming_them(tmp_path):
    """Rome's and Paris's names swapped in the boundaries' list of names, a
    well-formed file (which gave Florence Paris's zone and Paris Rome's
    unseen)."""
    tree = _tree(tmp_path)
    site, _ = _boundaries(tmp_path)
    names = (_site_packages() / "timezonefinder_data/data/timezone_names.txt").read_text(encoding="utf-8")
    swapped = names.replace("Europe/Rome", "@").replace("Europe/Paris", "Europe/Rome").replace("@", "Europe/Paris")
    _replace(site, "timezonefinder_data/data/timezone_names.txt", swapped.encode("utf-8"))
    out = _run(tree, PLACE_ZONE, site).stdout
    assert out.startswith("REFUSED the timezonefinder-data package's data files are not those this program was "
                          "built with (timezonefinder-data 1.2026.3 is installed; 1.2026.3's were recorded)"), out


def test_zone_boundaries_whose_version_is_a_word_are_refused_saying_they_name_none(tmp_path):
    """timezonefinder-data gives "unknown" where it finds no metadata of its
    own: no version, said so."""
    tree = _tree(tmp_path)
    site, _ = _boundaries(tmp_path)
    names = (_site_packages() / "timezonefinder_data/data/timezone_names.txt").read_text(encoding="utf-8")
    swapped = names.replace("Europe/Rome", "@").replace("Europe/Paris", "Europe/Rome").replace("@", "Europe/Paris")
    _replace(site, "timezonefinder_data/data/timezone_names.txt", swapped.encode("utf-8"))
    init = (_site_packages() / "timezonefinder_data/__init__.py").read_text(encoding="utf-8")
    _replace(site, "timezonefinder_data/__init__.py", (init + '\n__version__ = "unknown"\n').encode("utf-8"))
    out = _run(tree, PLACE_ZONE, site).stdout
    assert out.startswith("REFUSED the timezonefinder-data package's data files are not those this program was "
                          "built with (the timezonefinder-data installed does not name its version; "
                          "1.2026.3's were recorded), so no zone is read from it"), out


def test_a_zone_package_is_checked_once_in_a_process_and_its_refusal_kept(tmp_path):
    tree = _tree(tmp_path)
    site, _ = _tzdata(tmp_path)
    _replace(site, "tzdata/zoneinfo/Europe/Rome", (_site_packages() / "tzdata/zoneinfo/Asia/Tokyo").read_bytes())
    code = ("import time_zones as tz\n"
            "calls = []\n"
            "real = tz.zone_package_digest\n"
            "tz.zone_package_digest = lambda name: (calls.append(name), real(name))[1]\n"
            "for _ in range(3):\n"
            "    try:\n"
            "        tz.named_zone_state('Asia/Tokyo', 1990, 6, 15, 12, 0, 0)\n"
            "    except tz.ShippedDataChanged:\n"
            "        print('REFUSED')\n"
            "print(calls)\n")
    assert _run(tree, code, site).stdout.split("\n")[:4] == ["REFUSED", "REFUSED", "REFUSED", "['tzdata']"]


# --- A changed zone package on the page ------------------------------------------------

ZONE_SENTENCE = ("The time-zone data is not the one this app supplies, so no standard-time zone can be read. "
                 "Choose LMT (Local Mean Time) or Manual UTC offset.")


@pytest.mark.parametrize("package", ["tzdata", "timezonefinder-data"])
def test_a_changed_zone_package_is_one_sentence_on_the_page_and_lmt_still_casts(monkeypatch, package):
    """The check's refusal held for the process (as _zone_package_checked
    keeps it): a named-zone cast says the sentence, in the sidebar's box, with
    no exception on the page; a cast in local mean time goes on."""
    import time_zones as tz
    from conftest import assert_no_exception, make_app
    monkeypatch.setitem(tz._ZONE_PACKAGES_SEEN, package, f"the {package} package's data files are not those ...")
    at = make_app()
    at.session_state["time_standard_key"] = "Standard time (named zone)"
    at.run(timeout=180)
    assert not at.exception, [e.value for e in at.exception]
    assert ZONE_SENTENCE in [e.value for e in at.sidebar.error], [e.value for e in at.sidebar.error]
    at = make_app().run(timeout=180)
    assert_no_exception(at, "an LMT cast beside a changed zone package")
    assert ZONE_SENTENCE not in [e.value for e in at.sidebar.error]


def test_the_zone_sentence_names_the_thing_not_its_file():
    space = _lifted_lookup(Path("/nonexistent/app.py"))
    tree = ast.parse(ui_source())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and [ast.unparse(t) for t in n.targets] == ["ZONE_DATA_CHANGED_MESSAGE"])
    assert "_LMT_OR_MANUAL" in ast.unparse(node.value)
    for word in ("tzdata", "timezonefinder", "package", "SHA", "hash", "folder", "built", "Please", "`"):
        assert word not in ZONE_SENTENCE, word
    assert space["ATLAS_CHANGED_MESSAGE"] == CHANGED_SENTENCE


# --- The atlas hashed once while its file is unchanged -----------------------------------

@pytest.fixture
def counted(monkeypatch, small_atlas_recorded):
    """time_zones with an empty record of the atlas's checks and its one
    reader of the atlas's bytes (_atlas_digest) counted; the atlas recorded
    is the small one made from the shipped atlas, which each test copies."""
    import time_zones as tz
    calls = []
    real = tz._atlas_digest
    monkeypatch.setattr(tz, "_ATLAS_SEEN", {})
    monkeypatch.setattr(tz, "_atlas_digest", lambda f: (calls.append(f.name), real(f))[1])
    return tz, calls


def test_a_second_lookup_of_an_unchanged_atlas_reads_none_of_its_bytes(tmp_path, counted, small_atlas):
    tz, calls = counted
    copy = small_atlas_copy(small_atlas, tmp_path / "atlas.db")
    for text in ("Florence", "London", "Hekou"):
        assert tz.atlas_rows(copy, text)
    assert calls == [str(copy)]


@pytest.mark.parametrize("times", ["moved", "set back"])
def test_an_atlas_changed_after_its_check_is_read_again_and_refused(tmp_path, counted, small_atlas, times):
    """Rewritten in place under the same name: its modification time moves,
    or is set back to the old one, and its change time moves either way."""
    tz, calls = counted
    copy = small_atlas_copy(small_atlas, tmp_path / "atlas.db")
    assert tz.atlas_rows(copy, "Florence")
    before = os.stat(copy)
    _moved_florence(copy)
    if times == "set back":
        os.utime(copy, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert os.stat(copy).st_size == before.st_size
    with pytest.raises(tz.ShippedDataChanged, match=r"^atlas\.db is not the file this program was built with"):
        tz.atlas_rows(copy, "Florence")
    assert calls == [str(copy), str(copy)]
    with pytest.raises(tz.ShippedDataChanged):
        tz.atlas_rows(copy, "London")
    assert len(calls) == 2


def test_an_atlas_swapped_for_another_file_at_its_name_is_read_again(tmp_path, counted, small_atlas):
    tz, calls = counted
    copy = small_atlas_copy(small_atlas, tmp_path / "atlas.db")
    assert tz.atlas_rows(copy, "Florence")
    other = small_atlas_copy(small_atlas, tmp_path / "other.db")
    _moved_florence(other)
    os.replace(other, copy)
    with pytest.raises(tz.ShippedDataChanged):
        tz.atlas_rows(copy, "Florence")
    assert len(calls) == 2
