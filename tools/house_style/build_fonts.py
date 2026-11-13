#!/usr/bin/env python3
# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""Rebuild the page faces from the pinned upstream font files.

Reads upstream-lock.json for what to build and from what, and the character
list the app needs (characters.json, or a fresh one with --collect). Writes:

    fonts/*.ttf          the faces the server answers by name (server_limits.py),
                         uncompressed, so that a search can read their tables
    a table beside this file: where each face came from, and its SHA-256
    font_faces.json      the faces as build_theme.py registers them
    saved_faces.py       the fixed set a saved file carries, compressed, as data URIs
    licenses/            the licences, and a notice of each face's copyright

Upstream's files are not kept in this repository: --upstream names a folder
holding them, and --download fills that folder, each file checked against its
pinned SHA-256. No installed font is consulted, and two runs with the same
input write the same bytes.

IBM Plex's licence reserves the name "Plex", so its subsets are renamed: Zij
Interface and Zij Numeric. Zij Interface Marks holds the letters IBM Plex Sans
Condensed lacks, each a composite of that font's own letter and combining mark
at the place the font's own mark table gives them, so that the letter matches
its word; build_theme.py embeds it in house_style.py as glyph_font.py embeds
the symbol font, and like the symbol font it stays compressed there.
"""
from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import tempfile
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent

# The modules whose string constants hold what a page prints.
APP_SOURCES = ("app.py", "engine.py", "markup.py", "wheel.py", "export_html.py", "user_data.py", "ephemeris.py")
# The atlas columns a page prints.
ATLAS_COLUMNS = (("places", "name"), ("places", "admin1_name"), ("admin1_names", "name"), ("country_names", "name"))
TRANSLITERATION = "ĀāĪīŪūḤḥṢṣṬṭḌḍẒẓḎḏṮṯḪḫĠġŠšČčʿʾʽʹĞİŞıśżēōḳḲ̣̱̄"
# The letters a label is held to draw whole, whether or not a string or a
# place holds one today.
NAMED_LETTERS = "Ḥḥṣṭḍẓ"
GREEK = set(range(0x391, 0x3AA)) | set(range(0x3B1, 0x3CA))
SUPERSCRIPTS = {0xB9, 0xB2, 0xB3} | set(range(0x2070, 0x207A))
MIDLINE_ELLIPSIS = {0x22EF}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unicode_ranges(points) -> str:
    points = sorted(set(points))
    if not points:
        return ""
    ranges, start, previous = [], points[0], points[0]
    for point in points[1:]:
        if point == previous + 1:
            previous = point
        else:
            ranges.append((start, previous))
            start = previous = point
    ranges.append((start, previous))
    return ", ".join(f"U+{a:04X}" if a == b else f"U+{a:04X}-{b:04X}" for a, b in ranges)


def range_points(text):
    points = set()
    for part in text.split(","):
        first, _, last = part.strip()[2:].partition("-")
        points |= set(range(int(first, 16), int(last or first, 16) + 1))
    return points


def nondrawing_reason(point: int) -> str | None:
    """Why a code point needs no glyph, if it needs none."""
    if 0xD800 <= point <= 0xDFFF:
        return "surrogate, in a pattern that rejects it; not text"
    if point & 0xFFFF in (0xFFFE, 0xFFFF) or 0xFDD0 <= point <= 0xFDEF:
        return "noncharacter, in a pattern that rejects it; not text"
    if point in range(0xFE00, 0xFE10) or point in range(0xE0100, 0xE01F0):
        return "variation selector; it selects the glyph before it and has no ink of its own"
    if unicodedata.category(chr(point)) in {"Cc", "Cf", "Cn", "Zl", "Zp"}:
        return "control, format or unassigned; no ink of its own"
    return None


def _forms(text):
    return (text, unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text))


def other_script(character: str) -> str | None:
    """The script of a place name's character that this list leaves to the
    computer's own fonts, or None for a Latin letter, or a mark or punctuation
    shared with Latin names, which the list keeps."""
    point = ord(character)
    if point < 0x370 or 0x2000 <= point <= 0x206F or "LATIN" in unicodedata.name(character, ""):
        return None
    return unicodedata.name(character, "UNKNOWN").split()[0]


def collect_characters(app_dir: Path) -> dict:
    groups = {}
    for name in APP_SOURCES:
        tree = ast.parse((app_dir / name).read_text(encoding="utf-8"), filename=name)
        texts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        groups[name + " strings"] = sorted({ord(c) for s in texts for form in _forms(s) for c in form})
    kept, others, rows_other, rows = set(), {}, 0, 0
    with sqlite3.connect((app_dir / "atlas.db").resolve().as_uri() + "?mode=ro", uri=True) as connection:
        for table, column in ATLAS_COLUMNS:
            for (value,) in connection.execute(f"SELECT {column} FROM {table}"):
                if not value:
                    continue
                rows += 1
                other = False
                for form in _forms(value):
                    for character in form:
                        script = other_script(character)
                        if script is None:
                            kept.add(ord(character))
                        else:
                            other = True
                            others.setdefault(script, set()).add(character)
                rows_other += other
    groups["place names"] = sorted(kept)
    groups["Latin and transliteration"] = sorted({ord(c) for c in TRANSLITERATION + NAMED_LETTERS}
                                                 | set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)))
    groups["Greek letters"] = sorted(GREEK)
    groups["superscript figures"] = sorted(SUPERSCRIPTS)
    groups["midline ellipsis"] = sorted(MIDLINE_ELLIPSIS)
    points = set().union(*(set(p) for p in groups.values()))
    return {"groups": groups,
            "required": sorted(p for p in points if not nondrawing_reason(p)),
            "non_rendering": {f"U+{p:04X}": why for p in sorted(points) if (why := nondrawing_reason(p))},
            "other_scripts": {"characters left to the computer's own fonts": {k: len(v) for k, v in sorted(others.items())},
                              "values in the columns read": rows, "values holding one": rows_other}}


def read_lock():
    return json.loads((ROOT / "upstream-lock.json").read_text(encoding="utf-8"))


def check_versions(lock):
    import brotli
    import fontTools
    if fontTools.__version__ != lock["fonttools"] or brotli.__version__ != lock["brotli"]:
        raise SystemExit(f"This build needs fonttools=={lock['fonttools']} and brotli=={lock['brotli']}; "
                         f"found {fontTools.__version__}, {brotli.__version__}")


def _cache_read(path: Path):
    """The bytes of one file in the upstream folder, or None where there is
    none.

    The folder may be one that others can write, so these bytes are the only
    copy of the file the build uses: its hash is checked on them, and the fonts
    are parsed and the licences copied from them, never from the file opened
    again by name.
    """
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _cache_write(path: Path, data: bytes):
    """Put `data` at `path` in the upstream folder: a new file beside it,
    written, synced, then renamed over the name.

    A link left at the name is itself replaced, never written through, and a
    write that fails leaves the name as it was and no new file behind. The new
    file is made as an ordinary write would make it, so the folder's other
    readers can read it. The folder itself is the one the maintainer named,
    followed wherever it leads.
    """
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.part")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _fetch(item, upstream):
    data = urllib.request.urlopen(item["url"], timeout=120).read()
    if digest(data) != item["sha256"]:
        raise SystemExit(f"Checksum mismatch: {item['url']}")
    _cache_write(upstream / item["file"], data)
    return data


def ensure_sources(lock, upstream: Path, download: bool, *, source_bytes=None):
    """Each upstream font and licence in `upstream`, as the lock pins it; the
    licences' bytes, by name. Given a dict as `source_bytes`, it puts each
    font's bytes there, by file name: the very bytes whose hash was checked,
    which the build then parses, never opening the upstream file again."""
    downloads = {d["file"]: d for d in lock["downloads"]}
    upstream.mkdir(parents=True, exist_ok=True)

    checked = {}

    def member(source_name, sha256, inner, target):
        # Faces that share a source file share its one checked read.
        if (target, sha256) not in checked:
            checked[target, sha256] = fresh(source_name, sha256, inner, target)
        return checked[target, sha256]

    def fresh(source_name, sha256, inner, target):
        data = _cache_read(target)
        if data is not None and digest(data) == sha256:
            return data
        if not download:
            raise SystemExit(f"Missing or changed: {target}. Name its folder with --upstream, or use --download.")
        source = downloads[source_name]
        archive = upstream / source["file"]
        raw = _cache_read(archive)
        if raw is None or digest(raw) != source["sha256"]:
            raw = _fetch(source, upstream)
        data = zipfile.ZipFile(io.BytesIO(raw)).read(inner) if inner else raw
        if digest(data) != sha256:
            raise SystemExit(f"Checksum mismatch inside {source['file']}: {target.name}")
        _cache_write(target, data)
        return data

    for face in lock["faces"]:
        data = member(face["download"], face["source_sha256"], face["member"], upstream / face["source_file"])
        if source_bytes is not None:
            source_bytes[face["source_file"]] = data
    return {item["file"]: member(item["download"], item["sha256"], item["member"], upstream / item["file"])
            for item in lock["licenses"]}


def _rename(font, family, weight, style):
    style_name = "Italic" if style == "italic" else {400: "Regular", 500: "Medium", 600: "SemiBold"}[weight]
    postscript = family.replace(" ", "") + "-" + style_name
    values = {1: family, 2: style_name, 3: "ZijHouseStyle-" + postscript, 4: family + " " + style_name,
              6: postscript, 16: family, 17: style_name}
    for record in font["name"].names:
        if record.nameID in values:
            record.string = values[record.nameID].encode(record.getEncoding())


def _subset(font, points, target, features="*", flavor=None):
    from fontTools import subset
    # A fixed valid timestamp, whatever the day of the build.
    font["head"].created = font["head"].modified = 2082844800
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "source.ttf"
        font.save(path, reorderTables=True)
        subset.main([str(path), "--output-file=" + str(target), *([f"--flavor={flavor}"] if flavor else []),
                     "--unicodes=" + ",".join(f"U+{p:04X}" for p in sorted(points)),
                     "--layout-features=" + features, "--name-IDs=*", "--name-languages=*", "--name-legacy",
                     "--glyph-names", "--notdef-glyph", "--notdef-outline", "--recommended-glyphs",
                     "--no-recalc-timestamp", "--canonical-order"])


def mark_offset(font, base, mark):
    """Where the font's own mark table sets `mark` on `base`, as (dx, dy), or
    None if it does not say."""
    if "GPOS" not in font:
        return None
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for table in lookup.SubTable:
            table = getattr(table, "ExtSubTable", table)
            if table.LookupType != 4:
                continue
            if base not in table.BaseCoverage.glyphs or mark not in table.MarkCoverage.glyphs:
                continue
            record = table.MarkArray.MarkRecord[table.MarkCoverage.glyphs.index(mark)]
            anchor = table.BaseArray.BaseRecord[table.BaseCoverage.glyphs.index(base)].BaseAnchor[record.Class]
            if anchor is not None:
                return anchor.XCoordinate - record.MarkAnchor.XCoordinate, anchor.YCoordinate - record.MarkAnchor.YCoordinate
    return None


def composable(font, point):
    """(base glyph, mark glyph, dx, dy) for a letter this font lacks and can
    build from one letter and one mark of its own, or None."""
    cmap = font.getBestCmap()
    parts = unicodedata.normalize("NFD", chr(point))
    if point in cmap or len(parts) != 2 or ord(parts[0]) not in cmap or ord(parts[1]) not in cmap:
        return None
    base, mark = cmap[ord(parts[0])], cmap[ord(parts[1])]
    offset = mark_offset(font, base, mark)
    return None if offset is None else (base, mark, *offset)


def build_marks(face, points, target, source_data):
    """The composite letters in `points`, each the source font's own letter and
    mark: composites, not new outlines, so that the letter keeps its hinting."""
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent
    font = TTFont(io.BytesIO(source_data), recalcTimestamp=False)
    glyf, hmtx = font["glyf"], font["hmtx"]
    built = {}
    for point in sorted(points):
        parts = composable(font, point)
        if parts is None:
            continue
        base, mark, dx, dy = parts
        name = f"u{point:04X}"
        glyph = Glyph()
        glyph.numberOfContours = -1
        glyph.components = []
        for component_name, x, y, flags in ((base, 0, 0, 0x204), (mark, dx, dy, 0x004)):
            component = GlyphComponent()
            component.glyphName, component.x, component.y, component.flags = component_name, x, y, flags
            glyph.components.append(component)
        glyf[name] = glyph
        glyph.recalcBounds(glyf)
        hmtx[name] = (hmtx[base][0], glyph.xMin)
        built[point] = name
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(built)
    _rename(font, face["family"], face["weight"], face["style"])
    _subset(font, built, target, features="", flavor="woff2")
    return sorted(built)


def _inherited(lock, font_dir, app_dir):
    """The symbol font's two payloads as glyph_font.py holds them, out of their
    compressed container and otherwise as they are."""
    from fontTools.ttLib import woff2
    constants = _glyph_font_constants(app_dir)
    for item in lock["inherited_symbols"]:
        woff2.decompress(io.BytesIO(base64.b64decode(constants[item["constant"]])), str(font_dir / item["file"]))
        yield item


def _glyph_font_constants(app_dir):
    tree = ast.parse((app_dir / "glyph_font.py").read_text(encoding="utf-8"))
    return {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}


def _notices(rows):
    """licenses/FONT_NOTICES.txt: each face's copyright as its own name table
    states it, which not every licence file repeats."""
    lines = ["The page fonts", "==============", "",
             "Each face below is a subset of the font it names, made by tools/house_style/build_fonts.py;",
             "IBM Plex's are renamed, since its licence reserves the name. A licence file named here is in",
             "this folder, verbatim, unless its path is given. The symbol font's notice and licence are",
             "fonts/OFL.txt; so are those of Zij Interface Marks, embedded in house_style.py.",
             "saved_faces.py holds some of these faces again, compressed, for what leaves the app.", ""]
    for row in rows:
        where = {"Zij Interface Marks": "embedded in house_style.py",
                 "TAE Symbols": "embedded in glyph_font.py and house_style.py"}.get(row["family"], row["file"])
        lines += [f"{where} ({row['family']}, weight {row['weight']}, {row['style']})",
                  f"    Design: {row['origin_family']}, {row['upstream_version']}",
                  f"    Copyright: {row['copyright']}",
                  f"    Licence: {row['licence']}", ""]
    return "\n".join(lines)


def cell_advances(path):
    """Every character of a face by its advance in thousandths of an em, as
    {advance: characters}: what the app sizes a grid's columns from, since a
    grid draws on a canvas no stylesheet reaches and fontTools is not there at
    run time."""
    from fontTools.ttLib import TTFont
    font = TTFont(path)
    scale, metrics = 1000 / font["head"].unitsPerEm, font["hmtx"]
    groups = {}
    for point, glyph in sorted(font.getBestCmap().items()):
        groups.setdefault(round(metrics[glyph][0] * scale), []).append(chr(point))
    return {str(advance): "".join(groups[advance]) for advance in sorted(groups)}


def saved_faces_module(lock, font_dir, faces):
    """saved_faces.py: the fixed set a file carries when it leaves the app, each
    subset already made, compressed and held as a data URI, so that nothing
    subsets at run time."""
    from fontTools.ttLib import TTFont
    by_file = {face["file"]: face for face in faces}
    rows = []
    for name in lock["saved_faces"]:
        face = by_file[name]
        payload = face.get("data_base64")
        if payload is None:
            font = TTFont(font_dir / name, recalcTimestamp=False)
            font.flavor = "woff2"
            buffer = io.BytesIO()
            font.save(buffer)
            payload = base64.b64encode(buffer.getvalue()).decode("ascii")
        width = 96
        lines = "\n".join("        " + json.dumps(payload[i:i + width]) for i in range(0, len(payload), width))
        points = json.dumps(face["unicode_range"]) if "unicode_range" in face else "None"
        rows.append(f"    ({json.dumps(face['family'])}, {face['weight']}, {points}, (\n{lines}\n    )),")
    held = "\n".join(rows)
    return ('# Zīj. Copyright (C) 2026 Dār al-Ḥikma.\n'
            '# Licensed under the GNU Affero General Public License, version 3: see LICENSE.\n'
            '"""Generated by tools/house_style/build_fonts.py from the faces in fonts/. Edit that, never this file.\n'
            '\n'
            'The faces a file carries when it leaves the app, the HTML report and a saved picture, which\n'
            'opened on their own have no page to take a face from. A fixed set of subsets already made,\n'
            'held as data URIs, as glyph_font.py holds the symbol font; nothing subsets at run time and\n'
            'this module imports nothing. Each face\'s notice and licence: licenses/FONT_NOTICES.txt.\n'
            '"""\n'
            '# Family, weight, the code points the face answers for (None: all it holds), WOFF2 in base64.\n'
            '_FACES = (\n' + held + '\n)\n\n'
            '# What a picture draws its words in. The report carries them all.\n'
            'PICTURE_FAMILIES = ("Zij Interface", "Zij Interface Marks", "DejaVu Sans")\n\n\n'
            'def font_face_css(*families):\n'
            '    """The @font-face rules of `families`, or of the whole set if none is named."""\n'
            '    return "".join(\n'
            '        f"@font-face{{font-family:\'{family}\';font-weight:{weight};font-style:normal;"\n'
            '        + (f"unicode-range:{points};" if points else "")\n'
            '        + f"src:url(data:font/woff2;base64,{payload}) format(\'woff2\');}}"\n'
            '        for family, weight, points, payload in _FACES if not families or family in families\n'
            '    )\n')


def build(lock, characters, upstream, out_dir, app_dir, *, source_bytes=None, licences=None):
    from fontTools.ttLib import TTFont
    font_dir = out_dir / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "licenses").mkdir(parents=True, exist_ok=True)
    if source_bytes is None or licences is None:
        source_bytes = {}
        licences = ensure_sources(lock, upstream, download=False, source_bytes=source_bytes)
    downloads = {d["file"]: d for d in lock["downloads"]}
    required = set(characters["required"])
    used = {p for g, points in characters["groups"].items() if g.endswith(" strings") or g == "place names" for p in points}
    used |= {ord(c) for c in NAMED_LETTERS}
    sources = {f["file"]: TTFont(io.BytesIO(source_bytes[f["source_file"]]), lazy=True).getBestCmap()
               for f in lock["faces"]}
    marks_built = {}
    with tempfile.TemporaryDirectory() as folder:
        for face in (f for f in lock["faces"] if f["role"] == "marks"):
            path = Path(folder) / face["file"]
            marks_built[face["file"]] = (
                set(build_marks(face, used & required, path, source_bytes[face["source_file"]])), path.read_bytes())
    composed = set.intersection(*(s for s, _ in marks_built.values()))
    if any(s != composed for s, _ in marks_built.values()):
        raise SystemExit("A letter composes in one weight of the marks face and not in another.")
    # What the faces a page reads and labels in leave to the fallbacks. The
    # symbol font comes first in every stack, so what it holds is no gap.
    symbols = {p for f in lock["inherited_symbols"] for p in range_points(f["unicode_range"])}
    gaps = set()
    for face in (f for f in lock["faces"] if f["role"] == "page"):
        extra = composed if face["family"] == "Zij Interface" else set()
        gaps |= required - set(sources[face["file"]]) - extra - symbols
    rows, faces, remaining = [], [], set(gaps)
    for face in lock["faces"]:
        target = font_dir / face["file"]
        cmap = set(sources[face["file"]])
        if face["role"] == "marks":
            data, points = marks_built[face["file"]][1], sorted(composed)
        else:
            if face["role"] == "fallback":
                wanted = cmap & remaining
                remaining -= wanted
            else:
                wanted = cmap & required
            font = TTFont(io.BytesIO(source_bytes[face["source_file"]]), recalcTimestamp=False)
            if face["family"] != face["origin_family"]:
                _rename(font, face["family"], face["weight"], face["style"])
            _subset(font, wanted, target)
            data = target.read_bytes()
            points = sorted(TTFont(io.BytesIO(data)).getBestCmap())
        loaded = TTFont(io.BytesIO(data))
        source = downloads[face["download"]]
        rows.append({"file": face["file"], "family": face["family"], "origin_family": face["origin_family"],
                     "weight": face["weight"], "style": face["style"], "upstream_release": face["upstream_release"],
                     "upstream_version": face["upstream_version"], "upstream_source": source["url"],
                     "download_sha256": source["sha256"], "upstream_font_sha256": face["source_sha256"],
                     "subset_sha256": digest(data), "glyph_count": len(loaded.getGlyphOrder()),
                     "unicode_ranges": unicode_ranges(points),
                     "copyright": loaded["name"].getDebugName(0), "licence": face["licence"]})
        entry = {"file": face["file"], "family": face["family"], "weight": face["weight"], "style": face["style"]}
        if face["role"] == "marks":
            entry["data_base64"] = base64.b64encode(data).decode("ascii")
        if face["role"] in ("marks", "fallback"):
            entry["unicode_range"] = unicode_ranges(points)
        faces.append(entry)
        print(f"{face['file']}: {len(points)} code points, {rows[-1]['glyph_count']} glyphs, {len(data)} bytes")
    noticed = list(rows)
    for item in _inherited(lock, font_dir, app_dir):
        data = (font_dir / item["file"]).read_bytes()
        rows.append({"file": item["file"], "family": item["family"], "origin_family": item["origin_family"],
                     "weight": 400, "style": "normal", "upstream_release": "glyph_font.py", "upstream_version": "",
                     "upstream_source": "", "download_sha256": "", "upstream_font_sha256": "",
                     "subset_sha256": digest(data), "glyph_count": len(TTFont(io.BytesIO(data)).getGlyphOrder()),
                     "unicode_ranges": item["unicode_range"]})
        faces.append({"file": item["file"], "family": item["family"], "weight": 400, "style": "normal",
                      "unicode_range": item["unicode_range"]})
    constants = _glyph_font_constants(app_dir)
    by_file = {row["file"]: row for row in rows}
    for item in lock["embedded_symbols"]:
        data = base64.b64decode(constants[item["constant"]])
        source = by_file[item["copyright_from"]]
        rows.append({"file": item["file"], "family": item["family"], "origin_family": item["origin_family"],
                     "weight": 400, "style": "normal", "upstream_release": "glyph_font.py", "upstream_version": "",
                     "upstream_source": "", "download_sha256": "", "upstream_font_sha256": "",
                     "subset_sha256": digest(data), "glyph_count": len(TTFont(io.BytesIO(data)).getGlyphOrder()),
                     "unicode_ranges": item["unicode_range"]})
        noticed.append(dict(rows[-1], upstream_version=source["upstream_version"], copyright=source["copyright"],
                            licence=source["licence"]))
        faces.append({"file": item["file"], "family": item["family"], "weight": 400, "style": "normal",
                      "unicode_range": item["unicode_range"], "data_base64": constants[item["constant"]]})
    for name, data in licences.items():
        (out_dir / "licenses" / name).write_bytes(data)
    (out_dir / "licenses" / "FONT_NOTICES.txt").write_text(_notices(noticed), encoding="utf-8", newline="\n")
    tools = out_dir / "tools" / "house_style"
    tools.mkdir(parents=True, exist_ok=True)
    fields = [f for f in rows[0] if f not in ("copyright", "licence")]
    with (tools / "FONTS.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (tools / "font_faces.json").write_text(json.dumps(faces, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "saved_faces.py").write_text(saved_faces_module(lock, font_dir, faces), encoding="utf-8", newline="\n")
    (tools / "cell_advances.json").write_text(
        json.dumps(cell_advances(font_dir / "zij-interface-400.ttf"), indent=0, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")
    print(f"Composed in the marks face: {''.join(chr(p) for p in sorted(composed))}")
    print(f"Left to no bundled face: {''.join(chr(p) for p in sorted(remaining)) or 'none'}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, default=ROOT / "upstream", help="the folder holding the upstream files")
    parser.add_argument("--download", action="store_true", help="fetch what is missing, each checked against its pin")
    parser.add_argument("--collect", action="store_true", help="read the character list afresh from the app and atlas.db")
    parser.add_argument("--app-dir", type=Path, default=REPO, help="the app's folder")
    parser.add_argument("--out-dir", type=Path, default=REPO, help="where to write fonts/, licenses/, tools/house_style/ and saved_faces.py")
    parser.add_argument("--saved-faces-only", action="store_true", help="write saved_faces.py from the faces already in fonts/, and nothing else")
    args = parser.parse_args()
    lock = read_lock()
    check_versions(lock)
    if args.saved_faces_only:
        faces = json.loads((ROOT / "font_faces.json").read_text(encoding="utf-8"))
        (args.out_dir / "saved_faces.py").write_text(saved_faces_module(lock, args.app_dir / "fonts", faces), encoding="utf-8", newline="\n")
        return
    source_bytes = {}
    licences = ensure_sources(lock, args.upstream, args.download, source_bytes=source_bytes)
    characters_path = ROOT / "characters.json"
    if args.collect:
        characters = collect_characters(args.app_dir)
        characters_path.write_text(json.dumps(characters, indent=0, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    else:
        characters = json.loads(characters_path.read_text(encoding="utf-8"))
    build(lock, characters, args.upstream, args.out_dir, args.app_dir,
          source_bytes=source_bytes, licences=licences)


if __name__ == "__main__":
    main()
