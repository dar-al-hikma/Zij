# Zīj

A *zīj* (زِيج) is a set of astronomical tables with the rules for using them. This one is a study
companion for traditional natal astrology: cast a chart, then check, table by table, what the
texts say about it.

The rules it applies come from the course's two books in Benjamin Dykes's translations — Sahl
b. Bishr, *The Astrology of Sahl b. Bishr*, vol. I, and Abū Ma'shar, *On the Revolutions of the
Years of Nativities* (*Persian Nativities* IV) — with his *Great Introduction to the Science of
the Judgments of the Stars* as the supplement, and a handful of witness texts (Rhetorius,
Firmicus, al-Qabīsī, Abū 'Alī, Abū Bakr, the other *Persian Nativities* volumes, Valens, Morin)
where the course texts leave a question open. Every one of them, with what it supplies and how
it is cited, is in [docs/REFERENCES.md](docs/REFERENCES.md).

Every rule a page applies names the sentence it comes from. Where a text leaves something open,
the page says so and shows the reading it made; where the texts settle nothing at all — Mercury
exactly with the Sun, a tie between two contacts that open a distribution, a question the book
defers to another book — the result is reported *unresolved*, with its reason, its source and
the alternatives, and every total that depends on it shows what is known and what is not.

The judgment of the chart is the astrologer's.

## Download

Portable builds for Windows and macOS are on the
[Releases](https://github.com/dar-al-hikma/Zij/releases) page: unzip, run `Zij`. No install, no
internet — place lookup uses a bundled atlas and the planets run on the built-in Moshier
ephemeris. Saved charts and preferences live in your user data folder and survive updates.
The last ten versions of the saved charts, as they stood before each change, are kept beside
them, so a deleted chart stays in them until ten more changes are saved.

Every release after v1.0.0 also carries `SHA256SUMS`, the SHA-256 of each zip as the release
build made it. To check a download, compare its hash with its line there:
`shasum -a 256 Zij-macos.zip` on macOS, `Get-FileHash Zij-windows.zip` in PowerShell on Windows
(which prints it in capitals).

## What it computes

**The nativity**

- **Chart** — the wheel (square, or wide with a positions panel; light, dark or plain, whatever the page's mode; clickable, with an SVG
  download), positions, the Alchabitius divisions beside the whole-sign places, solar phase,
  Sahl's sign categories, the special degrees, the prenatal lunation, sect, the lords of the
  day and hour. **Here & Now** casts a chart for a stored home place at this moment.
- **Dignities and places** — the essential dignities at each planet's own degree, sect and
  domain, planets in the places and the lords of the places with their delineations from
  Masha'allah, *PN* IV and Rhetorius.
- **Delineations** — read off the cast chart: the fetus's stay, the Moon on the
  third day, Sahl's seven classes of fortune and livelihood, the places harming the eyesight,
  and, under the fuller reading depth, Mars by sect, the Moon's phases, Mercury's phase,
  Rhetorius's afflictions and Morin's aspect rules. Each cites its sentence; none is scored.
- **Configurations** — Sahl's connections and their states on his own sentences, receptions and
  their refusals, the handing-over, collection and reflection of light, prevented connections,
  strength and weakness, the corruption of the Moon; Abū Ma'shar's planetary conditions
  (Gr. Intr. VII) beside them, and the forward-looking conditions (revoking, resistance,
  escape) simulated against the ephemeris.
- **Lots** — the classical Lots and Sahl's topical Lots, each with its formula and its source;
  where Sahl gives a Lot twice with different formulas, both are shown.
- **Lunation and victors** — the prenatal syzygy, its lords and its governor (Sahl 1.7), the
  victor of the chart.

**Prediction** (Abū Ma'shar, *PN* IV, with the releaser and house-master from Sahl)

- **Revolutions** — the revolution of the year and of the month with their wheels; the
  indicators of the year in Abū Ma'shar's order; the distributions from the Ascendant and the
  meridian through the bounds, drawn as strips with the present marked; the lord of the year
  and the governor with their testimonies.
- **The releaser** — the releaser chosen from Sahl 1.15, the house-master and its years from
  1.20, its direction per 1.23, 2, and Abū 'Alī's additions and subtractions displayed beside
  Sahl's grant.
- **Days and months** — the profection of the month, the small days and the mighty days.
- **Fardar and ages** — the fardārs, the ages, the lord of the orb, the lords of the triplicity
  of the sect light over the life; and what the book does not settle, listed rather than filled
  in.

**Places and times** — an offline city search over the populated places in GeoNames, under their
other names and common short forms too; the birth time read as local mean time, on its named
zone's clock from a pinned copy of the time-zone database, or at a UTC offset you give. Before
1970, several hundred places in the United States are cast on the clocks they kept, not on their
zone's, each year with its sources. Where a record is disputed or settles nothing, the page says
so, and a UTC offset you give casts the chart instead.

**Reference** — the dignity tables, the bounds, the planetary years, the ages, the triplicity
lords by source; and **Sources and readings**, which lists every doctrinal switch in force, the
readings the app makes, and the scope of the export.

Every page's tables can be exported as one analysis (an HTML page, JSON with typed results, or
Markdown in the pages' own words), versioned with the readings the chart was analysed under.

## Running from source

```bash
pip install -r requirements.txt
python tools/fetch_atlas.py --repo dar-al-hikma/Zij
python run_source.py
```

The place atlas is not kept in the source: the second line downloads it from the project's
release and checks it against the SHA-256 the program records before putting it in place.

Open the address it prints, and open it again after reloading the page: the app opens only at
that address, which carries a key made for this run alone. Ctrl-C stops it.
A source run serves this computer only, and other accounts on this computer can reach it.

`streamlit run app.py` is a developer's command, with no key: any program on this computer, a
web page served from it included, can open the app there and read, change or delete its saved
charts. It also goes without the limits `run_source.py` keeps: when a page from another site
connects, it asks an outside service for this computer's public address; it answers its plain web
requests, among them its server's counters and the files it hands out, under any host name a page
gives; it reads Streamlit settings from `.streamlit` in the home folder and in the folder it is
started from; and it can still be made to keep an empty file sent to it. Nor does it answer the
page fonts, so its pages draw in the computer's own.

Python 3.14 is what the pins were resolved on and what the tests and the desktop build use.
The tests need the development pins as well: `pip install -r requirements-dev.txt`, then
`python -m pytest -q -n auto`. They pin every rule to a fixture drawn from the texts' own worked
figures, with a near-miss beside each, and render every page under the states the texts leave
open. The tests that read the texts themselves skip where the texts are absent, as they are here.

## Building the desktop app

See [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md) (PyInstaller, one folder per platform).
Releases are cut by tag; see [`docs/RELEASING.md`](docs/RELEASING.md).

## Repository

| Path | What |
|---|---|
| `engine.py` | the engine: the chart, the dignities, the evaluators, the lots and the timing |
| `wheel.py` | the pictures drawn from them: the chart wheel, the Timing page's wheels and the direction strips, in their two palettes |
| `export_html.py` | the HTML report: one file a reader opens in a browser and can print, nothing beside it |
| `markup.py` | the escaping the pictures and the report share, and the way a typed name is kept from turning the text around it |
| `ephemeris.py` | Swiss Ephemeris: the private folder it reads from, the handle every calculation goes through, the built-in Moshier ephemeris every body is read from, and the calendar dates are read in |
| `time_zones.py` | the time-zone database the app reads (its pinned copy, never the computer's), the zones and dates where that database is not trusted, the zone each place takes, and the offline atlas's search |
| `user_data.py` | where the app keeps what you save: its folder in your account, your saved charts with their last ten versions, and your preferences, each file written whole or not at all, by one window at a time; and the folder an older version kept them in, carried over only when it is your account's, and, on macOS and Linux, everything in it |
| `app.py` | the Streamlit pages, after the marker `# 4. STREAMLIT UI INTEGRATION`; it takes the engine whole and is the file to run |
| `glyph_font.py` | the symbol-font subset every picture embeds |
| `saved_faces.py` | the faces the HTML report and a saved picture carry, generated by `tools/house_style/build_fonts.py` |
| `fonts/` | the faces the pages draw in, which the server answers by name, and the symbol font's licence |
| `house_style.py` | the pages' own stylesheet, the pictures' colours and the HTML report's stylesheet, generated from `tools/house_style/tokens.json` with the theme in `.streamlit/config.toml` |
| `tests/` | the suite; `tests/fixtures/tables.json` pins which tables each page renders |
| `ephe/` | the Swiss Ephemeris fixed-star catalogue the app ships (AGPL-3.0; see its README) |
| `licenses/` | the page fonts' licences and notices, and the Apache License's text, which the build gives in a download's third-party notices for a bundled package that states that licence but carries no copy |
| `tools/fetch_atlas.py` | puts the offline place lookup, `atlas.db`, beside the app from the project's release, checked against the SHA-256 `time_zones.py` records; the lookup itself is not kept in the source |
| `build_atlas.py` | the maintainer's tool that builds `atlas.db` from GeoNames' `allCountries` dump and its alternate names, checking every row and recording its sources (the app never runs it) |
| `data/` | the outlines of the areas the app reads by coordinates for historical clocks, drawn from OpenStreetMap and published whole under the Open Database License, with their notice; the list of the places whose zone is settled by a named source rather than by the boundaries alone, each with its source; and the table of the clocks particular places kept before 1970 where research gives them clocks of their own, each year with its sources, with the list of those sources and how each was read |
| `desktop_launcher.py`, `build.spec` | the desktop wrapper and the PyInstaller build |
| `server_limits.py` | what the app's local server keeps to, from the desktop window or a source run: it never looks up this computer's public address, answers web requests only under its own address, reads no settings but the app's own, and takes in no file |
| `docs/` | four documents: the references, the build notes, the release procedure, the hostile-pass checklist |

This repository carries the app and those four documents, and nothing else. The build logs,
the audits and the working papers the rules were adjudicated from are the maintainer's private
notes. They are not public, and the source's comments do not cite them.

The texts themselves are not here either: they are copyrighted translations and are worked from
privately. The pages cite them by volume, chapter and sentence so that anyone with the books can
check every rule.

## History

Zīj was developed as the Traditional Astrology Engine and renamed at its first release. Its
rules were read twice against the texts, cell by cell, before that release; where a reading
could not be settled from the texts in hand, the app says so rather than choosing. The
development history is kept privately.

## Licence

Copyright (C) 2026 Dār al-Ḥikma.

Zīj is free software: you can share and change it under the terms of the GNU Affero General
Public License, version 3, as published by the Free Software Foundation (AGPL-3.0) — see
[`LICENSE`](LICENSE). It is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. Each download also carries `LICENSE` and `THIRD_PARTY_NOTICES.txt`: the licence texts
and notices of the Python runtime and of every package the download bundles.

The fixed-star catalogue in `ephe/` is Swiss Ephemeris
data redistributed under the same licence. `glyph_font.py` embeds a 26-glyph subset of Google's
Noto Sans Symbols and Noto Sans Symbols 2 (SIL Open Font License 1.1) as base64 WOFF2, so every
picture the app draws carries its own zodiac and planet glyphs regardless of what is installed
on the viewing machine — see [`fonts/OFL.txt`](fonts/OFL.txt) for the licence notice — and one glyph,
the Lot of Fortune's, cut from DejaVu Sans. The faces
the pages draw in are subsets of EB Garamond, IBM Plex Sans Condensed, IBM Plex Mono and DejaVu Sans,
with their licences and copyrights in [`licenses/`](licenses/FONT_NOTICES.txt). The
outlines in `data/` are drawn from OpenStreetMap (© OpenStreetMap contributors) and offered under the
Open Database License 1.0, apart from the code's licence — see [`data/NOTICE-ODBL.md`](data/NOTICE-ODBL.md).
The time-zone boundaries a birthplace's coordinates are read against are
[timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder)'s, drawn from
OpenStreetMap data (© OpenStreetMap contributors) and offered under the Open Database License 1.0;
the `timezonefinder-data` package carries them, with that licence.
The place atlas, `atlas.db`, which each download carries and a source run fetches, holds place
names, coordinates, and country and region names from [GeoNames](https://www.geonames.org/),
licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/);
Zīj selects and reformats the data for its offline atlas. GeoNames provides the data as is, with
no warranty of accuracy, timeliness or completeness.
