"""Sahl, On Nativities 1.23, 12-14: the redirection when the house-master is
unsuitable, and the case where the lord of the Ascendant IS the house-master.

12 sets the governor aside when it is an infortune or the lord of the eighth
(Sahl I p. 310). 13 turns to "the lord of the Ascendant" in its stead; 14:
"Now if there was nothing of what I have mentioned, then take from the degree
of the Ascendant to the positions of the infortunes, and their squares and
oppositions." When the lord of the Ascendant is the house-master, 13 would
direct the governor 12 has just set aside in its own stead -- its table was
the house-master's own direction again. 13 names no other planet, so nothing
of 13 is found and 14 alone is directed.

Two harness-style charts (Florence, 14:30 local mean time):
  1240-09-18  Capricorn rising: Saturn is the lord of the Ascendant AND the
              house-master, flagged as an infortune -- 14 only.
  1240-05-10  Libra rising: Venus the lord of the Ascendant, Saturn the
              house-master, flagged as an infortune -- 13, then 14.
"""
from conftest import FLORENCE, LOCAL_TIME, assert_no_exception, make_app

SELF_CHART = "1240-09-18"
OTHER_CHART = "1240-05-10"
LABEL_13 = "*1.23, 13: the lord of the Ascendant, in the house-master's stead*"
LABEL_14 = "*1.23, 14: the degree of the Ascendant*"


def _bundle(engine, iso):
    y, m, d = map(int, iso.split("-"))
    lat, lon = FLORENCE
    hour = LOCAL_TIME.hour + LOCAL_TIME.minute / 60.0
    chart = engine["calculate_traditional_chart_jd"](engine["civil_local_to_jd_ut"](y, m, d, hour, lon / 15.0), lat, lon)
    civil = engine["CivilDate"]
    bundle = engine["pn4_timing_bundle"](chart, lat, lon, civil(y, m, d), civil(y + 30, m, d),
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0])
    return chart, bundle


def _direct(engine, chart, planet, **kw):
    return engine["sahl_house_master_direction"](chart["planetary_data"], planet, chart["obliquity"], FLORENCE[0],
                                                 origin_jd=chart["julian_day"], **kw)


def test_hm_redirect_directs_the_ascendant_alone_when_its_lord_is_the_house_master(engine):
    """Engine level, both cases. Where the lord of the Ascendant is the
    house-master, the bundle directs no lord of the Ascendant (13) and
    directs the Ascendant's degree (14); where it is another planet, that
    planet is directed as before and its table is not the house-master's."""
    chart, b = _bundle(engine, SELF_CHART)
    rd = b["hm_redirect"]
    assert any("1.23, 12" in f for f in b["hm_flags"]), b["hm_flags"]
    assert rd["lord"] == b["house_master"] == "Saturn"
    assert rd["lord_direction"] is None, "13 directs the house-master in its own stead"
    assert rd["lord_is_house_master"] is True
    assert rd["ascendant_direction"] and rd["ascendant_direction"] == _direct(engine, chart, None, start_lon=chart["ascendant"])

    chart, b = _bundle(engine, OTHER_CHART)
    rd = b["hm_redirect"]
    assert any("1.23, 12" in f for f in b["hm_flags"]), b["hm_flags"]
    assert (rd["lord"], b["house_master"]) == ("Venus", "Saturn")
    assert rd["lord_is_house_master"] is False
    assert rd["lord_direction"] and rd["lord_direction"] == _direct(engine, chart, "Venus")
    assert rd["lord_direction"] != b["hm_direction"]
    assert rd["ascendant_direction"] and rd["ascendant_direction"] == _direct(engine, chart, None, start_lon=chart["ascendant"])
    # 13's aggravation: Venus in a sign of Mars's, so Mars rules the house of the lord of the Ascendant.
    assert rd["aggravators"] == ["Mars"]


def _releaser_page(date, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page="releaser")
    at.session_state["_reading_depth"] = "Course text"
    at.run(timeout=300)
    assert_no_exception(at, f"releaser {date}")
    return at


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children:
        for child in (children.values() if isinstance(children, dict) else children):
            yield from _walk(child)


def _labelled_tables(at):
    """{label: DataFrame} for each table, keyed by the bold or italic line
    since the last subheader that introduces it."""
    out, label = {}, None
    for node in _walk(at.main):
        kind = getattr(node, "type", "")
        if kind == "markdown" and node.value.lstrip().startswith("*"):
            label = node.value.strip()
        elif kind in ("subheader", "header"):
            label = None
        elif kind == "dataframe" and label is not None:
            out.setdefault(label, node.value)
    return out


def _redirection_line(at):
    lines = [m.value for m in at.main.markdown if m.value.startswith("**1.23, 13-14, the redirection**")]
    assert len(lines) == 1, lines
    return lines[0]


def test_the_page_draws_no_table_for_13_when_the_lord_of_the_ascendant_is_the_house_master(tmp_path, monkeypatch):
    """1240-09-18: no 13 table, 14's table, and the line says why, quoting
    12, 13 and 14."""
    at = _releaser_page(SELF_CHART, tmp_path, monkeypatch)
    tables = _labelled_tables(at)
    assert LABEL_13 not in tables, "13 directs the house-master in its own stead"
    assert LABEL_14 in tables and len(tables[LABEL_14]) > 0
    line = _redirection_line(at)
    assert "**Saturn**, the house-master itself" in line
    assert "\"one will not be able to be guided by the governor\" (12)" in line
    assert "13 turns to \"the lord of the Ascendant\"" in line
    assert ("14 follows: \"Now if there was nothing of what I have mentioned, then take from the degree of the "
            "Ascendant to the positions of the infortunes, and their squares and oppositions.\"") in line
    assert "directed in the house-master's stead" not in line
    assert any(c.value.startswith("Read: no sentence names another planet for 13") for c in at.main.caption)


def test_the_page_draws_13_when_the_lord_of_the_ascendant_is_another_planet(tmp_path, monkeypatch):
    """1240-05-10: 13's table (Venus) and 14's, as before; 13's rows are not
    the house-master's own; the line names Venus as not the house-master."""
    at = _releaser_page(OTHER_CHART, tmp_path, monkeypatch)
    tables = _labelled_tables(at)
    assert LABEL_13 in tables and LABEL_14 in tables
    own = [df for label, df in tables.items() if label.startswith("**Saturn**, the house-master, directed")]
    assert len(own) == 1 and len(tables[LABEL_13]) > 0
    assert not tables[LABEL_13].equals(own[0])
    line = _redirection_line(at)
    assert "the lord of the Ascendant here is **Venus**, not the house-master, and is directed in the house-master's stead" in line
    assert "holds for: Mars." in line
    assert not any(c.value.startswith("Read: no sentence names another planet for 13") for c in at.main.caption)


def _redirection_section(at):
    """Every element from the redirection line to the next heading."""
    nodes, inside = [], False
    for node in _walk(at.main):
        kind = getattr(node, "type", "")
        if kind == "markdown" and node.value.startswith("**1.23, 13-14, the redirection**"):
            inside = True
        elif inside and kind in ("subheader", "header"):
            break
        elif inside:
            nodes.append(node)
    return nodes


def test_the_self_case_draws_no_13_label_and_no_refusal(tmp_path, monkeypatch):
    """1240-09-18, the lord of the Ascendant the house-master: the section
    draws 14's label and table, and neither 13's label nor a "Refused at
    this latitude" warning. 13's lord_direction is None in this case, so a
    page that drew 13's table again would print its label and that warning
    with no table beneath -- which the table test above cannot see."""
    at = _releaser_page(SELF_CHART, tmp_path, monkeypatch)
    section = _redirection_section(at)
    labels = [n.value.strip() for n in section if n.type == "markdown" and n.value.lstrip().startswith("*1.23, 1")]
    assert labels == [LABEL_14], labels
    assert not [n.value for n in section if n.type == "warning" and "Refused at this latitude" in n.value]
    assert any(n.type == "dataframe" for n in section)
