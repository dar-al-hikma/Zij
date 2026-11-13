"""The zone boundaries' credit: timezone-boundary-builder's data, an OpenStreetMap derivative
under the ODbL, which the app reads every birthplace's zone from. The Sources page credits it
between the place atlas and the historical-clock outlines, and README and the references name it.
"""
import ast
import re

from conftest import APP_PATH, assert_no_exception, make_app, ui_source

ROOT = APP_PATH.parent
ZONE_BOUNDARIES = (
    "The time-zone boundaries a birthplace's coordinates are read against: "
    "[timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder), drawn from OpenStreetMap "
    "data, © OpenStreetMap contributors ([copyright and attribution](https://www.openstreetmap.org/copyright)), "
    "under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).")


def _sentence(name):
    tree = ast.parse(ui_source())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == [name])
    return ast.literal_eval(node.value)


def test_the_credit_names_the_maker_openstreetmap_and_the_licence_and_no_date_or_file():
    text = _sentence("ZONE_BOUNDARIES_CREDIT")
    assert text == ZONE_BOUNDARIES
    assert not re.search(r"[0-9]", text.replace("1.0", "").replace("1-0", ""))
    for word in (".json", ".tsv", ".db", "data/", "timezonefinder"):
        assert word not in text, word


def test_the_place_data_credits_run_atlas_boundaries_outlines():
    at = make_app(page="sources").run()
    assert_no_exception(at, "the Sources page")
    texts = [m.value for m in at.main.markdown]
    first = texts.index(_sentence("GEONAMES_CREDIT"))
    assert texts[first:first + 3] == [_sentence(name) for name in
                                      ("GEONAMES_CREDIT", "ZONE_BOUNDARIES_CREDIT", "OPENSTREETMAP_CREDIT")]


def test_readme_and_the_references_name_the_boundaries_source_and_licence():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = " ".join(readme.split("## Licence\n", 1)[1].split("\n## ", 1)[0].split())
    assert ("The time-zone boundaries a birthplace's coordinates are read against are "
            "[timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder)'s, drawn from "
            "OpenStreetMap data (© OpenStreetMap contributors) and offered under the Open Database License 1.0") in section
    row = next(line for line in (ROOT / "docs" / "REFERENCES.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| **timezone-boundary-builder**"))
    assert "ODbL 1.0, drawn from OpenStreetMap (© OpenStreetMap contributors)" in row
