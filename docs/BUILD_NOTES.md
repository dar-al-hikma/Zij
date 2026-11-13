# Packaging Zij as a portable desktop app

## Files
- `desktop_launcher.py` — spawns Streamlit headlessly, opens it in a pywebview window.
- `build.spec` — PyInstaller build configuration.
- `app.py` — the Streamlit script, bundled as a data file (not imported).
- `engine.py`, `ephemeris.py`, `time_zones.py`, `user_data.py`, `markup.py`,
  `wheel.py`, `export_html.py` — the modules `app.py` takes, bundled beside it
  as data files too (`build.spec` bundles every module `source_modules.txt`
  names). `wheel.py` draws the pictures and `export_html.py` builds the HTML
  report, with `markup.py`'s escaping. `user_data.py` is the data layer:
  the folder the saved charts and the preferences are kept in, in the
  account's own data folder (`%APPDATA%\Zij` on Windows,
  `~/Library/Application Support/Zij` on macOS, `$XDG_DATA_HOME/Zij` or
  `~/.local/share/Zij` elsewhere) and never in the build's own folder, which
  a new download replaces whole. It keeps the last ten versions of the
  saved charts beside them, each as it stood before a write over it.

## 1. Test in dev mode first
Before packaging anything:
```
pip install pywebview
python tools/fetch_atlas.py --repo dar-al-hikma/Zij
python desktop_launcher.py
```
The second line puts the place atlas, `atlas.db`, beside the app, checked
against the SHA-256 `time_zones.py` records; the build bundles it from there.
This should open a native window showing the app. Fix any issues here —
they'll be much harder to debug once frozen.

## 2. Why onedir instead of onefile
PyInstaller's `--onefile` mode self-extracts to a temp directory on *every
launch*, adding a real startup delay, and its unsigned self-extracting
`.exe`s are flagged by antivirus heuristics far more often than a plain
folder of files. `build.spec` uses `--onedir` (via `COLLECT`) instead:

- **Windows:** the build is a folder (`dist/Zij/`) containing
  `Zij.exe` plus its dependencies. Zip the folder — that *is* the
  portable, no-install form. Users unzip and double-click the `.exe`.
- **macOS:** the spec's `BUNDLE` step wraps that same folder into a proper
  `Zij.app`, which behaves as a single double-clickable icon even
  though it's technically a directory. Zip or `.dmg` it for distribution.

If a folder of files is unwanted, `--onefile` still
works for personal use — change `EXE(..., exclude_binaries=True)`
to a single onefile `EXE(...)` per PyInstaller's docs and drop `COLLECT`.

## 3. Platform-specific requirements

### Windows
pywebview uses the **Qt (PySide6/QtWebEngine)** backend, which bundles its
own Chromium build via the `PySide6` pip package — no external runtime
dependency like WebView2, no version detection, nothing to install on the
end user's machine beyond the app itself.

Unsigned `.exe`s trigger a Windows SmartScreen warning ("Windows protected
your PC"). Users can click **More info → Run anyway**. A proper fix requires
a code-signing certificate (~$100+/yr) — not necessary for personal/private
distribution.

### macOS
pywebview uses the built-in WebKit — no extra runtime needed, which is a
genuine advantage for portability here.

Unsigned `.app` bundles trigger Gatekeeper's "unidentified developer"
block. First run: try to open the app once, then go to System Settings →
Privacy & Security, scroll down to Security, find the line saying Zij was
blocked, click **Open Anyway** beside it, and enter your password (this
only needs doing once). Removing that friction needs an Apple Developer
ID ($99/yr) and a notarized build; the releases are not notarized.

## 4. Gotchas specific to this app's dependencies

- **Windows GUI backend: Qt (PySide6), not WebView2.** Earlier versions of
  this project used pywebview's EdgeChromium backend, which depends on the
  Microsoft Edge WebView2 Runtime being present on the end user's machine
  (usually true on stock Windows 10/11, but not guaranteed — debloated
  installs, locked-down corporate images, or older systems can be missing
  it entirely, and there's no way to know in advance whose machine it'll
  run on). We switched to pywebview's Qt backend instead: `PySide6`
  bundles its own complete Chromium build (QtWebEngine) directly in the
  pip wheel, so there's nothing external to detect, download, or bundle
  separately — `requirements-desktop.txt`, from which the Windows build's lock is made, is the
  whole story.
  `desktop_launcher.py` forces `gui="qt"` on Windows; macOS keeps using
  its native Cocoa/WebKit backend, since that already works well there
  with no equivalent runtime-availability problem.
- **pyswisseph / ephemeris precision:** the planets run on the built-in
  Moshier ephemeris (no external `.se1` files needed). This is
  arc-second-level precision, which is far finer than anything the app
  displays (minutes of arc) — no need to bundle Swiss Ephemeris planetary
  files unless there is a specific reason to want JPL-grade precision.
  The invariant that matters is that NO `.se1` FILE IS BUNDLED OR NEEDED
  and the planets stay on Moshier: every body is read with `FLG_MOSEPH`.
  Swiss Ephemeris still opens other files by name from the folders on its
  ephemeris path -- above all a Delta T table (`swe_deltat.txt`,
  `sedeltat.txt`), which moves every value -- and a thread's path starts
  at the working directory. So `ephemeris.py`, which the engine imports
  first, makes a private folder of its own before it imports `swisseph`
  (`tempfile.mkdtemp`, its mode then set to 0700 and its catalogue copy's
  to 0600 whatever the umask, removed at a normal exit by an `atexit` hook;
  a killed process leaves it behind, and so does a Windows server stopped
  by `terminate()`) and sets `$SE_EPHE_PATH` to it, and every call into the
  library goes through its `swe` handle, which the engine takes whole and
  which points the calling thread at that folder before the thread's first
  calculation. `app.py`
  takes `swe` from the engine and must not import `swisseph` itself. The
  folder holds nothing but a copy of the star catalogue the app ships,
  `ephe/sefstars.txt` (137 KB, the Swiss Ephemeris fixed-star file, copied
  unmodified from the `kerykeion` package, which redistributes it under
  AGPL-3.0 -- the app's own licence; see `ephe/README.md`), checked
  against the SHA-256 `engine.py` records (`FIXED_STAR_CATALOGUE_SHA256`).
  No other catalogue is looked for (`$SE_EPHE_PATH`, the user data
  directory and installed packages were searched once). The copy is a
  plain file written into the temporary folder, with no link (the first
  Windows build of the branch failed at a symlink-or-copy into
  `%APPDATA%`). `build.spec` lists the file in `datas` so the frozen app
  carries it at `_internal/ephe/sefstars.txt`. The fixed-star tables (PN
  IV I.6, 7 and III.8, 9) therefore render identically on every checkout
  and in the frozen app; when the page says "Not computed" it says only
  that the fixed-star file could not be read, and why stays off the page,
  in `_FIXED_STAR_STATE['why']`. The Linux build keeps Swiss Ephemeris's
  state per thread; whether the Windows and macOS builds do has not been
  checked (where a build shares one state, every thread is pointed at the
  same folder all the same).
- **pyswisseph is compiled from source on every platform.** The pinned
  `pyswisseph==2.10.3.2` publishes ready-made wheels only up to CPython
  3.11, and the build runs CPython 3.14, so on Windows and on macOS pip
  downloads its 2.10.3.2 sdist (`pyswisseph-2.10.3.2.tar.gz`) and builds
  the wheel on the runner itself, with that runner's compiler. The last
  release build's log shows it on both runners ("Downloading
  pyswisseph-2.10.3.2.tar.gz", then "Building wheel for pyswisseph",
  ending in a `cp314` wheel built there). The local and CI test venvs
  on Linux are built from the same sdist. CI's test venv compiles it
  with the interpreter's own C flags plus `-ffp-contract=off` (no fused
  multiply-adds), so the last digits the suite pins do not depend on how
  the interpreter was built; a local test venv is sure to hold those pins
  only when it is built the same way, which a plain `pip install` does not
  do. The Swiss Ephemeris code a release carries is therefore the
  unmodified upstream source, compiled per platform at build time: no
  downloaded binary of it is involved, and the suite, which runs on
  Linux, never runs the Windows or macOS build of it.
  The build's stop check holds one value each download computes with it,
  where the example chart's wheel puts Jupiter, to the value the app draws
  on Linux, within a hundred-thousandth of a degree.
- **timezonefinder:** answers from a sizeable boundary dataset (tens of
  MB) that, since timezonefinder 8, is a distribution of its own,
  `timezonefinder-data` (pinned in `requirements.txt`), imported as the
  separate top-level package `timezonefinder_data`.
  `collect_all("timezonefinder")` does not reach it, so `build.spec`
  lists `timezonefinder_data` in `collect_pkgs` beside it; without that
  the build would carry the polygons only if a PyInstaller hook for the
  package happened to be installed. This is the single biggest
  contributor to final build size. For a much smaller build at the cost
  of coarser timezone boundaries, `TimezoneFinderL` is a lighter drop-in
  alternative; it trades accuracy for size and is not used.
- **Geocoding is offline.** Place lookup reads the bundled `atlas.db`
  (SQLite, about 2.1 GB, put in the checkout by `tools/fetch_atlas.py` and
  listed in `build.spec`'s `datas`), opened read-only, so
  the packaged app needs no internet access and no geopy/Nominatim or
  certifi -- neither is a dependency any more, and neither is in
  `requirements*.txt` or the spec. Swapping the atlas for a live geocoder
  would bring both back: a network requirement at runtime, and certifi's CA
  bundle for frozen HTTPS calls.
- **Rebuilding the atlas.** `build_atlas.py` builds `atlas.db` from
  GeoNames' `allCountries` dump (every populated place), its alternate
  names, and its country and region name lists; it is a maintainer's tool,
  never run by the app. Run it with the app's interpreter:
  `python -I build_atlas.py --fetch FOLDER` downloads the four files over
  HTTPS with a manifest of each one's address, Last-Modified, SHA-256 and
  size, and `python -I build_atlas.py --build` (with `--places`,
  `--alternates`, `--countries`, `--admin1`, `--manifest` and `--output`)
  builds from them, stopping, writing nothing, where a file is not the one
  the manifest records. It checks every row (a failing row stops the build
  and is named), writes the database beside its output through a temporary
  file, and records its sources in the database's `metadata` table: the
  manifest, the row count, the dump's date, and the Python, Unicode, SQLite
  and tzdata versions it was built with. The atlas is not kept in the
  repository: it is published as a release file, and `tools/fetch_atlas.py`
  puts it in the checkout, checked against the SHA-256 `time_zones.py`
  records (which the program also checks before each lookup). The tests pin
  its row count, schema and dump, a digest of every place's coordinates and
  five places' coordinates exactly, so a rebuild is a reviewed change that
  updates those pins, the recorded SHA-256, and the atlas's length and its
  published zip's length and SHA-256 that `tools/fetch_atlas.py` records,
  in the same commit; the tool refuses any other zip before it reads it as
  a zip.
- **The outline data.** `time_zones.py` reads the outlines of the areas it
  judges by coordinates (areas that kept their own time, cities with dates
  of their own, areas outside the country a zone's notes describe) from
  `data/mean_time_outlines.json` beside it, once, at import: an
  OpenStreetMap derivative published under the ODbL, with its notice,
  `data/NOTICE-ODBL.md`. `build.spec` lists both in `datas` under `data`,
  so the frozen app carries them at `_internal/data/`. Without the file the
  module's import fails, loudly, rather than judging without the outlines.
  Beside them, `data/place_zones.tsv` is the hand-kept list of the atlas's
  places whose zone is settled by a named source rather than by the
  boundaries alone, each with its reason and source; `time_zones.py` reads it at
  import the same way, and `build.spec` ships it in the same folder. So is
  `data/place_clocks.tsv`, the table of the clocks particular places kept
  before 1970 where research gives them clocks of their own (generated from
  the research, never edited by hand), read and shipped the same way, and so
  is `data/place_clock_sources.tsv`, the documents its years name, with how
  each was read, generated with it.
- **The licence texts.** `build.spec` ships `LICENSE`, `fonts/OFL.txt` and
  the page fonts' licences in `licenses/` as they stand, at `_internal/`,
  `_internal/fonts/` and `_internal/licenses/` on Windows (inside
  the bundle on macOS), and writes `THIRD_PARTY_NOTICES.txt` beside
  `LICENSE` at every build, in the build's work folder, from the build's own
  environment: the Python runtime's `LICENSE.txt`, then a section for each
  installed distribution the analysis bundled a module, binary or data
  folder of, with its name and version, the licence its metadata states and
  every licence, notice, copying or authors file in its metadata folder.
  The program's own files, folders and modules are never credited to a
  package that claims their names. A package that states the Apache License
  but ships no copy of it (Streamlit's ships none) gets
  `licenses/Apache-2.0.txt`, that licence's text verbatim; one that states the
  MIT License and ships no copy gets `licenses/MIT.txt`, its terms, under the
  author its metadata names. Then, by the bundled file names: the other
  libraries the Python runtime brings, with `licenses/PYTHON_LIBRARIES.txt`,
  which holds Zstandard's, expat's, libffi's, zlib-ng's and HACL\*'s own licences
  and the Python documentation's list of what Python incorporates, and by name
  alone for SQLite and liblzma, with bzip2's text in Windows's Python section;
  Microsoft's runtime libraries, by name; and OpenSSL 3, under each name it
  goes by on either system, with the files the build holds. Nothing is
  fetched. After the build, `.github/scripts/notices_check.py` fails on any
  native library in the bundle that is uncredited.

## 5. Building for both platforms without owning both machines PyInstaller
does not cross-compile — a build run on Linux/Mac cannot produce a Windows
`.exe`, and vice versa. Without both machines the standard solution is a
CI matrix, which this repository has: `.github/workflows/build.yml` runs
on `windows-2025-vs2026` (x86-64) and on Apple silicon: `macos-26` in a
public repository, where a release tag builds, and the maintainer's own
Mac in the private development repository, where GitHub bills every macOS
minute. Each of GitHub's runners is named by its image, not by a `-latest`
label that moves on its own, and the release job runs on `ubuntu-24.04`.
Python is pinned to the patch release (3.14.8) in both workflows, which
move together; the maintainer's Mac and the test runner must hold that
release before the pin moves. On macOS it first makes an environment in
the job's temporary folder, so nothing installed on that Mac outlives the
run. It installs that system's lock and nothing else (`pip install
--require-hashes -r requirements-build-windows.lock`, or
`requirements-build-macos.lock`), fetches the place atlas from the
repository's own release (`tools/fetch_atlas.py`), runs
`tests/test_mac1_platform_names_2026_10_14.py` as a script and then under
pytest (the platform's errno names, and the names the program reads), runs
`pyinstaller build.spec`, zips `dist/` (the macOS zip with `zip -y`, so
the links inside `Zij.app` stay links), and starts, reaches and stops the
download it built (`.github/scripts/stop_check.py`). That build job can
only read the repository, and its checkout keeps no token on disk. For a
pushed `v*` tag, a second job, which runs no build tool and is the only
one allowed to write, waits for both platforms and creates one draft
release with both zips and `SHA256SUMS`, the SHA-256 of each, attached and
no notes; a manual run builds the zips and stops. How it is triggered and
where the zips go is in `docs/RELEASING.md`.

**The locks.** Each lock is made from `requirements-desktop.txt` (which
includes `requirements.txt`) and `requirements-build.txt` for its system,
so PyInstaller, its hooks and everything pip would resolve for any of them
are pinned there, each with the SHA-256 of every file of that version; the
command that makes it is in its header. After a pin moves in any of the
three files, rewrite both locks with those commands, and keep every
version they share with the set the tests run on the same (uv keeps the
pins a lock already holds; `--upgrade-package NAME` moves one). `pyswisseph`,
`timezonefinder` and `proxy-tools` publish no wheel for CPython 3.14 on
either system, so pip builds them on the runner from the source archives
the lock hashes; the build tools it fetches to do that (setuptools and
the like) come from the package index with no hash check.

## 6. Debugging a frozen build that fails silently
Set `console=True` in `build.spec` temporarily — this gives a terminal
window showing Streamlit's actual startup errors/tracebacks, which are
otherwise invisible with `console=False`. Switch back to `False` for the
release build once it's working.
