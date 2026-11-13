# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The Sky page's view: what its component is made of, and what it is handed.

The view is four pinned files in vendor/ (three.js, the world, the star view and
the figures) with sky_host.js after them, all one script, as the wheel's is, and
none of it reaches the window. vendor/tower-physical.js is pinned beside them and
never sent: this module reads each star's colour index and each object's kind
from it, and its numbers name each row (data/sky_source_ids.tsv).

Every place the view draws is the engine's, of date: right ascension and
declination from fixed_star_places, the observer from fixed_star_frame. A figure's
name stands at a point the figure's file gives at J2000, carried to the date by
the rotation that best takes the table's stars onto the engine's places.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

import house_style

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
PINS = {
    "three.r128.js": "3d43dd920529d6afb363357a559ee32c7916562081bb90349dc850295338da36",
    "sphere-world.js": "0f4f551a571883111c0cf07af1cb3d5aa1ab62f664f86dd00e4cd30b12faefa6",
    "tower-view.js": "5ee767191b355f06ca4754d1a0b10205c4010d9a36111f03ddbccc5fae77ec1b",
    "figures.js": "0505e3a4046a68cddffa76f1339cac04398cc1b0edfead1f33139e3f66a76645",
    "tower-physical.js": "760b8c0e2edfbc26df573fd7eec2085a792b3e8b3dcf298900b705836da23d5c",
    # Moves only with the file: tools/star_lists.py, which writes it, prints the new one.
    "sky_source_ids.tsv": "bf30bf63d7faac4b50024908025f0fc0f2cf3f86002bb4965a10f93e61a09b45",
}
SOURCE_IDS_FILE = HERE / "data" / "sky_source_ids.tsv"
EVENTS = {"Ascendant": ("asc", "rise"), "Descendant": ("dsc", "set"), "MC": ("mc", "culm"), "IC": ("ic", "anti")}
VIEWS = {"Outside": "orbit", "Within": "tower"}
# The control keeps that order; the page opens on this one.
FIRST_VIEW = "Within"
# Turn's speeds, as minutes of the chart's clock a real second, and its fastest in
# degrees of the sky a second.
TURN_MINUTES = (1, 2, 10, 60)
TURN_FASTEST = 26.0


def _pinned(path):
    """The file's text, from the one read its SHA-256 was checked on."""
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINS[path.name]:
        raise ValueError(f"{path.name} is not the pinned file")
    return raw.decode("utf-8")


def _vendored(name):
    return _pinned(VENDOR / name)


def _script():
    # Module code is strict and its top-level `this` is undefined: the files that
    # take their root from `this`, or from globalThis, are called on a holder.
    return "".join(("const __held = {};\n(function(globalThis, self){\n", _vendored("three.r128.js"),
                    "\n}).call(__held, __held, __held);\nconst THREE = __held.THREE;\n",
                    _vendored("sphere-world.js"), "\n", _vendored("tower-view.js"), "\n(function(){\n", _vendored("figures.js"),
                    "\n}).call(__held);\nconst FIGURES = __held.FIGURES, FIGURE_EXTRAS = __held.FIGURE_EXTRAS;\n",
                    "const SKY_WORDS = ", (HERE / "sky_words.json").read_text(encoding="utf-8"), ";\n",
                    (HERE / "sky_host.js").read_text(encoding="utf-8")))


def _json_after(text, mark):
    return json.JSONDecoder().raw_decode(text[text.index(mark) + len(mark):])[0]


def _load():
    physical = _json_after(_vendored("tower-physical.js"), "var data=")
    figures_text = _vendored("figures.js")
    figures = _json_after(figures_text, "var FIGURES=") + _json_after(figures_text, "var FIGURE_EXTRAS=")
    ids = {}
    for line in _pinned(SOURCE_IDS_FILE).splitlines():
        if line and not line.startswith(("#", "id\t")):
            number, row = line.split("\t")
            ids[number] = row
    return _script(), (HERE / "sky_host.css").read_text(encoding="utf-8"), physical, figures, ids


try:
    JS, CSS, PHYSICAL, FIGURES, SOURCE_IDS = _load()
    AVAILABLE = True
except (OSError, ValueError, KeyError):
    # A file changed or gone costs this one page, which says so; never the app.
    JS, CSS, PHYSICAL, FIGURES, SOURCE_IDS = "", "", {"stars": [], "objects": []}, [], {}
    AVAILABLE = False
_ID_OF_ROW = {row: number for number, row in SOURCE_IDS.items()}
_TABLE = ({f"hip:{row[0]}": {"ra": row[1], "dec": row[2], "bv": row[6]} for row in PHYSICAL["stars"]}
          | {row[0]: {"ra": row[1], "dec": row[2], "bv": row[6], "kind": row[7]} for row in PHYSICAL["objects"]})


def _mix(colour, ground, share):
    """`colour` taken `share` of the way to `ground`."""
    one, two = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (colour, ground))
    return "#" + "".join(f"{round(a + (b - a) * share):02X}" for a, b in zip(one, two))


def palette(theme):
    """The sky's colours by the page's: the sky is dark under both, so its marks
    keep the dark palette's, and the page's choice reaches its ground."""
    dark = house_style.WHEEL_PALETTES["dark"]
    ground = dark["panel"] if theme == "light" else dark["bg"]
    brass, steel, madder = dark["badge"], dark["horizon"], dark["cusp"]
    return {"background": ground, "colours": {
        "brass": brass, "brassDim": _mix(brass, dark["bg"], .4), "steel": steel, "steelDim": _mix(steel, dark["bg"], .4),
        "madder": madder, "madderDim": _mix(madder, dark["bg"], .4), "verdigris": dark["meridian"], "star": dark["ink"],
        "ground": dark["tints"][1], "labelBrass": brass, "labelPrime": _mix(brass, dark["bg"], .2),
        "labelDim": _mix(brass, dark["bg"], .25), "labelQuadrant": _mix(brass, dark["bg"], .15), "labelSteel": steel,
        "labelSteelDim": _mix(steel, dark["bg"], .25), "labelMadder": madder, "labelShadow": dark["bg"]}}


def _unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def _rotation(pairs):
    """The rotation that best takes the J2000 points onto the points of date."""
    table, placed = (_unit(np.array([p[i] for p in pairs]), np.array([p[i + 1] for p in pairs])) for i in (0, 2))
    left, _, right = np.linalg.svd(table.T @ placed)
    return right.T @ np.diag([1.0, 1.0, np.linalg.det(right.T @ left.T)]) @ left.T


def sources(stars, identity, label, at_minute, co_rising):
    """What one moment's places give the view: (star rows, object rows, names,
    each star's row id by identity, each identity by row id, figure anchors). Each
    row's `lon` and `co` are printed by the view, so they stand at the app's minute
    (`at_minute`); `co` is `co_rising(star)`, None where there is no such degree."""
    rows, objects, names, ids, back, pairs = [], [], {}, {}, {}, []
    for star in stars:
        key = identity(star)
        number = _ID_OF_ROW.get(key, f"zij:{key}")
        table = _TABLE.get(number, {})
        co = co_rising(star)
        row = {"id": number, "ra": star.right_ascension, "dec": star.declination, "vmag": star.magnitude, "bv": table.get("bv"),
               "lon": at_minute(star.longitude), "lat": star.latitude, "co": None if co is None else at_minute(co)}
        if star.magnitude is not None and star.magnitude != star.magnitude:
            row["vmag"] = None
        if table:
            pairs.append((table["ra"], table["dec"], star.right_ascension, star.declination))
        if "kind" in table:
            objects.append(row | {"kind": table["kind"]})
        else:
            rows.append(row)
        names[number], ids[key], back[number] = label(star), number, key
    # The view lists them in the order it is given.
    rows.sort(key=lambda row: names[row["id"]].casefold())
    objects.sort(key=lambda row: names[row["id"]].casefold())
    anchors = {}
    if pairs:
        turned = _rotation(pairs)
        for figure in FIGURES:
            if figure.get("label"):
                x, y, z = turned @ _unit(figure["label"]["ra"], figure["label"]["dec"])
                anchors[figure["key"]] = {"ra": float(np.degrees(np.arctan2(y, x)) % 360.0),
                                          "dec": float(np.degrees(np.arcsin(max(-1.0, min(1.0, z)))))}
    return {"stars": rows, "objects": objects, "names": names, "ids": ids, "back": back, "anchors": anchors}


def angles(lists, ids, identity, crossing_text, offset_text):
    """The axes' rows as the Axes tab holds them, in its own words for its own numbers."""
    return {"status": "ok"} | {
        word: {"byLongitude": [{"id": ids[identity(row["star"])], "dlon": offset_text(row["offset"])} for row in lists[axis]["longitude"]],
               "crossing": [{"id": ids[identity(row["star"])], "eventType": event, "dtMinutes": crossing_text(row["seconds"], axis)}
                            for row in lists[axis]["crossing"]],
               "crossingStatus": "ok"}
        for axis, (word, event) in EVENTS.items()}


def speeds(sidereal_rate):
    """Turn's five speeds: degrees of the sky a real second, from the rate the engine
    turns the sky, with the chart's minutes a second each is worth."""
    return ([{"rate": minutes * 60.0 * sidereal_rate, "minutes": minutes} for minutes in TURN_MINUTES]
            + [{"rate": TURN_FASTEST, "minutes": round(TURN_FASTEST / (60.0 * sidereal_rate))}])


def envelope(places, frame, shown, angle_rows, population, mode, theme, turn, at_minute, sidereal_rate):
    """One run's data for the component."""
    jd = frame["julian_day"]
    context = f"{jd:.8f}|{frame['latitude']:.8f}|{frame['armc']:.8f}"
    return {"context": context, "descriptor": {"mode": "apparentOfDate", "epoch": jd, "contextId": f"zij:{context}"},
            "observer": {"lat": frame["latitude"], "lst": frame["armc"] % 360.0, "obl": frame["obliquity"]},
            "axes": {"asc": at_minute(frame["axes"]["Ascendant"])}, "speeds": speeds(sidereal_rate),
            "stars": places["stars"], "objects": places["objects"], "names": places["names"], "anchors": places["anchors"],
            "shown": shown, "population": population, "angles": angle_rows, "angles_key": f"{context}|{population}",
            "mode": mode, "theme": theme or "dark", "palette": palette(theme), "turn": turn}
