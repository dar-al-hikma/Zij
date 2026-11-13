# build.spec
#
# Build with:  pyinstaller build.spec
#
# Run this SEPARATELY on Windows (produces Zij.exe in dist/) and
# on macOS (produces Zij.app in dist/) -- PyInstaller bundles the
# native interpreter and platform libraries, so it cannot cross-compile.
#
# Before running, install the lock for the system you build on, as the
# release build does:
#   pip install --require-hashes -r requirements-build-windows.lock   (or -macos)
# It holds PyInstaller and pyinstaller-hooks-contrib with the app's own pins
# (pyinstaller-hooks-contrib includes maintained hooks for Streamlit and
# several of its dependencies; without it you will likely need to add more
# --hidden-import / --collect-all entries by trial and error.)

import os
import re
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules


def _source_modules(root):
    """The program's source modules, as source_modules.txt names them: one
    file name per line, "#" starts a comment, blank lines skipped; no list
    means engine.py and app.py. A list naming nothing, a name with a folder
    in it or one name twice stops the build. Each is bundled below. (The
    suite reads the list with tests/source_list.py, by the same rules, and
    checks that this bundles what that reads.)"""
    path = os.path.join(root, "source_modules.txt")
    if not os.path.isfile(path):
        return ["engine.py", "app.py"]
    with open(path, encoding="utf-8") as f:
        names = [line.split("#", 1)[0].strip() for line in f]
    names = [name for name in names if name]
    bad = [name for name in names if "/" in name or "\\" in name or name in (".", "..") or names.count(name) > 1]
    if not names or bad:
        sys.exit(f"build.spec: source_modules.txt names {bad or 'no file'}")
    return names


SOURCE_MODULES = _source_modules(SPECPATH)

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# These packages ship data files, C extensions, or dynamic imports that
# static analysis alone won't find -- pull in everything for each.
# NOTE: "webview" (pywebview's actual import name -- not the "pywebview"
# distribution name) was MISSING from this list entirely in earlier
# versions of this spec. pywebview's platform backends (edgechromium.py,
# winforms.py, mshtml.py, cocoa.py, etc.) are imported dynamically inside
# functions in guilib.py, which PyInstaller's static analysis can't see --
# so without explicitly collecting them, some backends silently never
# make it into the bundle at all. That's what caused pywebview to keep
# falling through to the broken legacy WinForms/IE renderer even after
# explicitly forcing gui="edgechromium" in desktop_launcher.py: the
# edgechromium backend module itself wasn't present to import.
# NOTE: pyswisseph's PyPI distribution name and its actual import name
# ("swisseph") differ -- listing "pyswisseph" here silently collects
# nothing, since collect_all() operates on the importable module name, not
# the PyPI package name. This went unnoticed for a while because every
# earlier build crashed (on pywebview issues) before app.py ever got far
# enough to actually execute `import swisseph`.
# NOTE: the same holds of the zone boundaries. Since timezonefinder 8 its
# polygons are a distribution of their own, timezonefinder-data, imported as
# "timezonefinder_data" -- a second top-level package, which
# collect_all("timezonefinder") does not reach. Listed here so that the
# build carries them whether or not a PyInstaller hook for it is installed.
# "tzdata" is the time-zone database the app reads every zone from, on
# every platform (zoneinfo opens each folder of it as a package resource).
collect_pkgs = ["streamlit", "altair", "pandas", "swisseph", "timezonefinder", "timezonefinder_data", "tzdata",
                "webview"]
if sys.platform == "win32":
    # pywebview's Qt backend on Windows needs PySide6 (which bundles its own
    # complete Chromium build via QtWebEngine -- no external runtime to
    # install or bundle separately) and qtpy, the Qt-binding-agnostic shim
    # pywebview's own qt.py imports through. PyInstaller has mature,
    # well-tested hooks for PySide6/QtWebEngine via pyinstaller-hooks-contrib
    # (this is an extremely common combination to bundle), unlike the
    # WebView2/pythonnet/.NET interop path this replaced.
    collect_pkgs += ["PySide6", "qtpy"]

for pkg in collect_pkgs:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Parts of those packages the program never runs, left out: pandas' own test
# suite, Streamlit's demo pages (those of the "streamlit hello" command;
# streamlit.hello itself and its streamlit_app stay, since Streamlit's server
# imports that module at every start to ask whether it is running the demo),
# timezonefinder's command line and the builder of its C extension, and Qt's
# SQL module, whose hook would collect its database drivers again (below). Each
# is dropped as a module (from hiddenimports, and in Analysis's excludes, so
# no import the analysis finds brings it back) and as a file (from datas, which
# collect_all fills with the packages' source files too).
UNUSED_MODULES = ["pandas.tests", "streamlit.hello.hello", "streamlit.hello.animation_demo",
                  "streamlit.hello.dataframe_demo", "streamlit.hello.mapping_demo", "streamlit.hello.plotting_demo",
                  "streamlit.hello.utils", "timezonefinder.command_line", "timezonefinder.__main__",
                  "timezonefinder.build", "PySide6.QtSql"]


def _unused(module):
    """True for a module of UNUSED_MODULES, or one inside it."""
    return any(module == name or module.startswith(name + ".") for name in UNUSED_MODULES)


def _module_of(entry):
    """A collected (src, dest[, typecode]) data file as a dotted name: its
    destination folder and its file name less the extension."""
    folder = str(entry[1]).replace("\\", "/").strip("/")
    stem = os.path.splitext(os.path.basename(str(entry[0])))[0]
    return ".".join([part for part in folder.split("/") if part not in ("", ".")] + [stem])


hiddenimports = [name for name in hiddenimports if not _unused(name)]
datas = [entry for entry in datas if not _unused(_module_of(entry))]

# collect_all("PySide6") is a blunt instrument: it also sweeps in the QML
# tree, the C++ headers, CMake files, import libraries and the
# objects-Release/*.cpp.obj static-link leftovers under PySide6/qml -- none
# of which the app touches (pywebview's Qt backend uses QtWebEngineWidgets,
# not QML). Those object files sit ten folders deep, and the first
# Windows build from this repository failed to EXTRACT on a Windows
# machine with "Error 0x80010135: Path too long" on every one of them.
# Drop them here; what stays is Qt's bin/, plugins/, resources/ and
# translations/, which QtWebEngine does need (QtWebEngineProcess.exe, the
# .pak resources, the locales). Qt's SQL drivers and module go as well: the
# program uses no Qt SQL, and the PostgreSQL driver brought its client library
# off the build machine's own PATH, in no package and under no notice. (Qt6Sql.dll
# stays: Qt6Help.dll, which the same collection brings, links it.)
_PYSIDE_DROP = ("/qml/", "/objects-release/", "/include/", "/lib/cmake/", "/typesystems/",
                "/glue/", "/examples/", ".cpp.obj", ".obj", ".lib", ".prl", ".cmake", ".pdb",
                "/sqldrivers/", "/qtsql.")

def _keep(entry):
    """False for a collected (src, dest[, typecode]) tuple the bundle does not need."""
    path = ("/" + "/".join(str(p).replace("\\", "/") for p in entry[:2])).lower()
    if "pyside6" not in path and "shiboken6" not in path:
        return True
    return not any(marker in path for marker in _PYSIDE_DROP)

if sys.platform == "win32":
    datas = [e for e in datas if _keep(e)]
    binaries = [e for e in binaries if _keep(e)]

# Belt-and-suspenders on top of collect_all("webview") above: explicitly
# force in every submodule of webview by name, matching the exact fix
# used by other pywebview+PyInstaller projects that hit this same issue.
hiddenimports += collect_submodules("webview")

# Belt-and-suspenders for swisseph too: it's a single compiled C-extension
# file with no submodule structure, so this just directly confirms
# PyInstaller's binary-dependency resolution picks it up. ephemeris.py, the
# one module that imports it, is bundled as data below, so no code the
# build analyzes imports it.
hiddenimports += ["swisseph"]

# Every file added from here to the analysis is the program's own (the notices
# below credit no package with it).
_OWN_FROM = len(datas)

# app.py is loaded at runtime via _resource_path("app.py") in the launcher,
# not imported as a module -- bundle it as a plain data file alongside the
# executable rather than analyzing it as code. engine.py goes beside it, as
# data for the same reason, and so does every other module source_modules.txt
# names. The launcher's own imports reach them at build time too, so a build's
# analysis holds a second copy of each, and a frozen run imports that one:
# PyInstaller's frozen importer looks in the archive before the folder, and the
# script's own folder is the frozen importer's. The data copies still serve what
# reads Path(__file__), and sky.py, which the archive does not hold. And
# Streamlit puts the script's own directory on sys.path before running it,
# which is how app.py's "from engine import *" finds it in the frozen build
# exactly as it does from a source checkout. ephemeris.py, time_zones.py and
# user_data.py (the data layer: the saved charts and the preferences), which
# engine.py imports first, and markup.py, wheel.py and export_html.py (the
# pictures and the HTML report), which it imports last, are found beside it the
# same way, so they need no hiddenimports entry; what they import (swisseph,
# streamlit, zoneinfo,
# tzdata and the standard library, the lock modules fcntl and msvcrt among
# it) is collected above or reached from the launcher, as it was while
# engine.py imported it itself. wheel.py's name is also a well-known package's,
# which no requirement here installs; setuptools does hold a copy of it, at
# setuptools/_vendor/wheel/, which neither build collects, and the step after the
# build in build.yml reads the archive's listing to say so. glyph_font.py goes
# beside engine.py for the same reason again: engine.py's own "from
# glyph_font import font_face_css" needs it on sys.path at run time, and
# it is pure data (two base64
# WOFF2 strings), not a package Analysis would find through imports; so is
# saved_faces.py, the faces a saved file carries, for wheel.py and
# export_html.py. atlas.db
# is the offline GeoNames lookup database queried in place of a network
# geocoding API; it is not kept in the repository, and tools/fetch_atlas.py
# puts it at the checkout's root, checked against the SHA-256 time_zones.py
# records, before the build. app_icon.ico is loaded at runtime via
# _resource_path("app_icon.ico") for the pywebview window icon, and doubles
# as the .exe icon below. ephe/sefstars.txt is the Swiss Ephemeris fixed-star
# catalogue the app ships (AGPL-3.0, see ephe/README.md); the engine finds it
# beside itself, exactly as it reads atlas.db, checks it against the SHA-256
# it records and reads a copy from the private folder ephemeris.py makes,
# the only folder Swiss Ephemeris is given. No .se1 planetary file is bundled: the
# planets stay on the built-in Moshier ephemeris (docs/BUILD_NOTES.md).
# data/mean_time_outlines.json holds the outlines of the areas the zone code
# reads by coordinates (an OpenStreetMap derivative under the ODbL, apart from
# the code's licence); time_zones.py reads it from the data folder beside
# itself at import, so it goes there, with its notice, data/NOTICE-ODBL.md.
# data/place_zones.tsv is the sourced list of the places whose zone is not
# the one the zone boundaries give their coordinates; time_zones.py reads it
# from the same folder at import, as it reads data/place_clocks.tsv, the table
# of the clocks particular places kept before 1970, and
# data/place_clock_sources.tsv, the documents that table's years name.
datas += [(name, ".") for name in SOURCE_MODULES]
datas += [("glyph_font.py", "."), ("saved_faces.py", "."), ("atlas.db", "."), ("app_icon.ico", "."), ("app_icon_opening.png", "."), ("ephe/sefstars.txt", "ephe"), ("ephe/sefstars_added.txt", "ephe")]
datas += [("data/mean_time_outlines.json", "data"), ("data/NOTICE-ODBL.md", "data"), ("data/place_zones.tsv", "data"),
          ("data/place_clocks.tsv", "data"), ("data/place_clock_sources.tsv", "data"), ("data/fixed_star_lists.tsv", "data"),
          ("data/sky_source_ids.tsv", "data")]
# The Sky page: the pinned files sky.py reads and hashes, and its host; one of them
# (tower-physical.js) never leaves the server. Their notices: licenses/SKY_NOTICES.txt.
datas += [("sky_host.js", "."), ("sky_host.css", "."), ("sky_words.json", ".")]
datas += [(f"vendor/{name}", "vendor") for name in (
    "three.r128.js", "sphere-world.js", "tower-view.js", "figures.js", "tower-physical.js")]
# LICENSE is the program's own licence, and fonts/OFL.txt the embedded
# symbol font's, which the font's licence requires to travel with it; both
# go into the download as they stand here. THIRD_PARTY_NOTICES.txt, the
# notices of everything else the download bundles, is written below, once
# the analysis has said what that is (licenses/Apache-2.0.txt, the Apache
# License's text verbatim, is read into it for a package that states that
# licence but carries no copy, and licenses/MIT.txt, the MIT License's terms,
# likewise).
datas += [("LICENSE", "."), ("fonts/OFL.txt", "fonts")]
# The page's fonts, which the server answers by name from the fonts folder
# beside the app (server_limits.FONT_FILES names the same list); their licences,
# carried as fonts/OFL.txt is, since no installed package brings them; and the
# checkout's config.toml, which is where the theme is. The launcher's flags
# outrank every other option in it (desktop_launcher._server_options).
datas += [(f"fonts/{name}", "fonts") for name in (
    "dejavu-sans-400.ttf", "eb-garamond-400-italic.ttf", "eb-garamond-400.ttf", "eb-garamond-600.ttf",
    "tae-symbols-400.ttf", "tae-symbols2-400.ttf",
    "zij-interface-400.ttf", "zij-interface-600.ttf", "zij-numeric-400.ttf")]
datas += [(f"licenses/{name}", "licenses") for name in (
    "SKY_NOTICES.txt", "three-MIT.txt", "FONT_NOTICES.txt", "dejavu-Bitstream-Arev-DejaVu.txt", "eb-garamond-OFL.txt", "ibm-plex-mono-OFL.txt",
    "ibm-plex-sans-condensed-OFL.txt")]
datas += [(".streamlit/config.toml", ".streamlit")]

a = Analysis(
    ["desktop_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # collect_submodules("webview") above force-imports every webview.platforms.*
    # submodule so pywebview's Qt backend -- itself only ever loaded dynamically
    # by guilib.py -- gets discovered. That net also catches winforms.py,
    # mshtml.py, and edgechromium.py: pywebview's legacy Windows backends,
    # superseded by the Qt/PySide6 backend desktop_launcher.py forces on
    # win32 (the WinForms fallback is explicitly disabled there too). All
    # three `import clr` at module scope, so pulling them in also drags in
    # pythonnet -- and its bundled .NET interop DLLs -- purely because that
    # import statement exists, never because anything here actually runs it.
    excludes=["webview.platforms.winforms", "webview.platforms.mshtml", "webview.platforms.edgechromium", "pythonnet", "clr", "clr_loader",
              *UNUSED_MODULES],
    cipher=block_cipher,
)

# A licence, notice, copying or authors file, by its name; any file under a
# metadata folder's licenses/ (where newer packages keep theirs) is one too.
_NOTICE_FILE = re.compile(r"(?i)^(?:licen[cs]e|copying|notice|authors|copyright)")
_RULE = "#" * 78   # a line no bundled licence text was found to hold
# OpenSSL 3's libraries, by each name they go under: the -x64 pair is what Qt's network
# module looks for, which PyInstaller's Qt hook takes off the build machine's PATH, in no
# package, when Qt finds them there; the other Windows pair and the macOS pair are Python's
# own copies, which Python's licence does not name. A 1.x library's names are none of
# these: it would need its own section, and .github/scripts/notices_check.py stops the
# build until it has one.
_OPENSSL = re.compile(r"(?i)^(?:libcrypto|libssl)(?:-3(?:-x64)?\.dll|\.3\.dylib)$")
# The other libraries the Python runtime brings: its files by their names, and the
# extension modules of its own that hold a library inside them, as each was read in the
# Windows and macOS builds, the runtime's own files among them. licenses/PYTHON_LIBRARIES.txt
# holds Zstandard's, expat's, libffi's, zlib-ng's and HACL*'s own licences under those names, then the
# Python documentation's list of what Python incorporates, under that list's own headings.
# It holds no text of SQLite or liblzma, which are named and no more; bzip2's stands in
# Windows's Python section, from the licence file of the Python that built it.
_PYTHON_LIBRARIES = ((r"^libffi[-.]", "libffi"), (r"^pyexpat\.", "expat"), (r"^_decimal\.", "libmpdec"),
                     (r"^sqlite3\.dll$", "SQLite"), (r"^_sqlite3\.cpython", "SQLite"),
                     (r"^libzstd\.", "Zstandard"), (r"^_zstd\.pyd$", "Zstandard"),
                     (r"^_lzma\.", "liblzma, part of XZ Utils"), (r"^_bz2\.pyd$", "bzip2"),
                     (r"(?i)^python3\d+\.dll$", "zlib-ng"), (r"(?i)^python3\d+\.dll$", "mimalloc"),
                     (r"(?i)^python3\d+\.dll$", "HACL*"), (r"^Python$", "mimalloc"))
# Microsoft's runtime libraries, which PyInstaller and some packages bring.
_MICROSOFT = re.compile(r"(?i)^(?:api-ms-win-.*|ucrtbase|vcruntime\d.*|msvcp\d.*|concrt\d.*|vccorlib\d.*|vcamp\d.*|vcomp\d.*)\.dll$")
# The runtime in macOS's framework, which no suffix shows, by the names a build gives it.
_PYTHON_FRAMEWORK = re.compile(r"^(?:Python\.framework/(?:Versions/[^/]+/)?)?Python$")


def _bundled_tops(analysis, own):
    """The top-level import names of what `analysis` bundles: each module's,
    each binary's (an extension module beside the program is named by its
    file), and the folder of each data file in one -- not a data file beside
    the program, nor a folder of `own`, the program's own."""
    tops = {name.split(".", 1)[0] for name, *_ in analysis.pure}
    tops |= {re.split(r"[\\/]", dest, maxsplit=1)[0].split(".", 1)[0] for dest, *_ in analysis.binaries}
    tops |= {parts[0] for parts in (re.split(r"[\\/]", dest) for dest, *_ in analysis.datas) if len(parts) > 1}
    return tops - set(own)


def _bundled_files(analysis):
    """The file names, without their folders, of the native libraries `analysis` bundles."""
    names = {re.split(r"[\\/]", dest)[-1] for dest, *_ in [*analysis.binaries, *analysis.datas]}
    framework = {"Python" for dest, *_ in analysis.binaries if _PYTHON_FRAMEWORK.match(dest)}
    return {name for name in names if re.search(r"(?i)\.(?:dll|pyd|so|dylib)$", name)} | framework


def _third_party_notices(tops, libraries):
    """THIRD_PARTY_NOTICES.txt's text: the Python runtime's licence, then a
    section for each installed distribution one of the top-level import
    names `tops` belongs to -- its name and version, its licence as its
    metadata states it, and every notice file its metadata folder holds --
    then a section for each kind of library the bundled file names `libraries`
    show that no distribution brought.
    Read from the build's own environment; nothing is fetched."""
    from email.utils import getaddresses
    from importlib import metadata
    import sysconfig
    owners = metadata.packages_distributions()
    names = sorted({dist for top in tops for dist in owners.get(top, ())}, key=str.lower)
    python = ".".join(str(part) for part in sys.version_info[:3])
    out = ["Third-party notices for Zīj", "",
           "Zīj itself is under the GNU Affero General Public License, version 3 (LICENSE, beside this",
           "file). This download also carries the work of others: the Python runtime, the libraries it",
           "brings, and the packages below, each section giving the name and version built with, its",
           "licence as its own metadata states it, and the text of every licence and notice file it",
           "carries; the symbol font's subset (fonts/OFL.txt); the page fonts (licenses/FONT_NOTICES.txt,",
           "with each font's licence beside it); the outlines in data/ (data/NOTICE-ODBL.md); and the",
           "place atlas, from GeoNames under Creative Commons Attribution 4.0 International.", ""]
    # In `datas` too, so a real build stops without it.
    sky_notices = os.path.join(SPECPATH, "licenses", "SKY_NOTICES.txt")
    if os.path.isfile(sky_notices):
        with open(sky_notices, encoding="utf-8") as f:
            out += [f.read().rstrip(), ""]
    licence = [os.path.join(sysconfig.get_path("stdlib"), "LICENSE.txt"), os.path.join(sys.base_prefix, "LICENSE.txt")]
    found = next((path for path in licence if os.path.isfile(path)), None)
    out += [_RULE, f"Python {python}", "License: the PSF License Agreement, https://docs.python.org/3/license.html", ""]
    if found:
        with open(found, encoding="utf-8", errors="replace") as f:
            out += [f.read().rstrip(), ""]
    else:
        out += ["(No LICENSE.txt was found in the Python this download was built with.)", ""]
    for name in names:
        dist = metadata.distribution(name)
        meta = dist.metadata
        out += [_RULE, f"{meta['Name']} {dist.version}"]
        long_text = []
        for field in ("License-Expression", "License"):
            value = (meta.get(field) or "").strip()
            if value and "\n" not in value and len(value) <= 200:
                out.append(f"{field}: {value}")
            elif value:
                long_text.append(value)
        classifiers = [c.split(" :: ", 1)[1] for c in meta.get_all("Classifier") or () if c.startswith("License ::")]
        if classifiers:
            out.append("Classifiers: " + "; ".join(classifiers))
        files = sorted((f for f in dist.files or () if f.parts[0].endswith(".dist-info")
                        and (_NOTICE_FILE.match(f.name) or "licenses" in f.parts[1:-1])), key=str)
        out.append("")
        for text in long_text:
            out += [text, ""]
        for f in files:
            out += [f"--- {'/'.join(f.parts[1:])}", f.locate().read_bytes().decode("utf-8", "replace").rstrip(), ""]
        stated = " ".join([meta.get("License-Expression") or "", meta.get("License") or ""] + classifiers)
        if not files and not long_text and re.search(r"(?i)\bapache\b", stated):
            # Streamlit's own package, for one, carries no licence file; the
            # Apache License requires its text to go with the work, so the
            # copy kept in the repository is given in its place.
            with open(os.path.join(SPECPATH, "licenses", "Apache-2.0.txt"), encoding="utf-8") as f:
                out += ["(Its metadata holds no licence file; the Apache License 2.0 it states follows.)", "",
                        f.read().rstrip(), ""]
        elif not files and not long_text and re.search(r"(?i)\bmit\b", stated):
            # The MIT License asks that its terms go with the copies. The holder is
            # whoever the package's own metadata names as its author, and no one else.
            holder = (meta.get("Author") or "").strip() or ", ".join(
                name for name, _address in getaddresses([meta.get("Author-email") or ""]) if name)
            with open(os.path.join(SPECPATH, "licenses", "MIT.txt"), encoding="utf-8") as f:
                terms = f.read().rstrip()
            if holder:
                out += ["(Its metadata holds no licence file; the MIT License it states follows, "
                        "with the author its metadata names.)", "", f"Copyright (c) {holder}", "", terms, ""]
            else:
                out += ["(Its metadata holds no licence file and names no author; the MIT License "
                        "it states follows.)", "", terms, ""]
        elif not files and not long_text:
            out += ["(Its metadata holds no licence file.)", ""]
    in_order = sorted(libraries, key=str.lower)
    brought = [f"{name}: {library}" for name in in_order for pattern, library in _PYTHON_LIBRARIES if re.search(pattern, name)]
    if brought:
        # Read here and in no `datas`, as the Apache text is; a real build stops without it.
        with open(os.path.join(SPECPATH, "licenses", "PYTHON_LIBRARIES.txt"), encoding="utf-8") as f:
            out += [_RULE, "Libraries the Python runtime brings", "", "Each file here is, or holds, the library named:",
                    "", *brought, "", f.read().rstrip(), ""]
    microsoft = [name for name in in_order if _MICROSOFT.match(name)]
    if microsoft:
        out += [_RULE, "Microsoft runtime libraries", "", f"Microsoft's runtime libraries, which this download holds: {', '.join(microsoft)}.", ""]
    openssl = [name for name in in_order if _OPENSSL.match(name)]
    if openssl:
        # OpenSSL 3's licence is the Apache License 2.0, and the libraries' file names say the 3.
        with open(os.path.join(SPECPATH, "licenses", "Apache-2.0.txt"), encoding="utf-8") as f:
            out += [_RULE, "OpenSSL 3", "License: Apache-2.0", "",
                    f"This download holds {', '.join(openssl)}. "
                    "The OpenSSL Project Authors hold the copyright.", "", f.read().rstrip(), ""]
    return "\n".join(out) + "\n"


# The program's own names: the folders its own files go to, and the module of
# each Python file beside this one (server_limits, which the launcher
# imports, reaches the analysis as a module).
_OWN = {re.split(r"[\\/]", dest)[0] for _src, dest in datas[_OWN_FROM:]}
_OWN |= {name[:-3] for name in os.listdir(SPECPATH) if name.endswith(".py")}
_NOTICES = os.path.join(workpath, "THIRD_PARTY_NOTICES.txt")
os.makedirs(workpath, exist_ok=True)
with open(_NOTICES, "w", encoding="utf-8", newline="\n") as f:
    f.write(_third_party_notices(_bundled_tops(a, _OWN), _bundled_files(a)))
a.datas += [("THIRD_PARTY_NOTICES.txt", _NOTICES, "DATA")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Declares Per-Monitor-V2 DPI awareness in the .exe's embedded manifest,
# which Windows reads at process-creation time -- before a single line of
# Python runs. That sidesteps the reliability problem with the runtime
# alternative (ctypes.windll.shcore.SetProcessDpiAwareness() in
# desktop_launcher.py, kept as a defensive fallback): that call only takes
# effect if it runs before the *first* GDI/window-related Win32 call
# anywhere in the process, and nothing guarantees Python/PyInstaller's own
# startup hasn't already made one. Without either, Windows DPI-virtualizes
# an unaware process -- bitmap-scaling its window to compensate for display
# scaling while it still thinks it drew at the requested size/position --
# which is what made the window open oversized and shifted off-screen.
# Includes the common-controls dependency PyInstaller's own default
# manifest normally carries, so native controls keep the modern Windows
# theme instead of falling back to unthemed Windows Classic controls.
WINDOWS_MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
    </dependentAssembly>
  </dependency>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/PM</dpiAware>
    </windowsSettings>
  </application>
</assembly>
""" if sys.platform == "win32" else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Zij",
    debug=False,
    strip=False,
    upx=False,      # UPX compression trips some antivirus heuristics; leave off
    console=False,  # set True temporarily if you need to see startup errors
    icon="app_icon.ico",  # Windows .exe icon (Explorer, taskbar, alt-tab)
    manifest=WINDOWS_MANIFEST,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Zij",
)

# On macOS, wrap the onedir output into a proper double-clickable .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Zij.app",
        icon="app_icon.icns",
        bundle_identifier="io.github.dar-al-hikma.zij",
    )
