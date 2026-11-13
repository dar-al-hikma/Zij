# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""One name on each star: the names' table, by designation, and the old Virgo Cluster row left out.

The values below are written out on purpose, apart from the engine's table, so that a
spelling one letter off in either fails here."""
import collections
import hashlib
import math

import pytest

import engine as E

READS_BY = {
    '22Tau': 'Sterope', 'al-1Cap': 'α¹ Cap', 'al-2Lib': 'Zuben Algenubi', 'alAqr': 'Sadalmelik',
    'alCas': 'Shedar', 'alCyg': 'Deneb Adige', 'alGru': 'α Gru', 'alHer': 'Rasalgethi', 'alPsc': 'Alrescha',
    'alTri': 'Mothallah', 'alUMa': 'Aldubhe', 'beCep': 'Alfirk', 'beOph': 'Cebalrai', 'deDra': 'Altais',
    'deSgr': 'Kaus media', 'epCMa': 'Adhara', 'epDel': 'Deneb Eldelphin', 'epLeo': 'Ras Elased',
    'epSgr': 'Kaus australis', 'etBoo': 'Muphrid', 'ga-1And': 'Almach', 'ga-2Vel': 'Regor',
    'gaAqr': 'Sadachbia', 'gaCep': 'Errai', 'gaCyg': 'Sadr', 'gaLyr': 'Sulafat', 'HIP 101120': 'HIP 101120',
    'ioCar': 'Aspidiske', 'ioCet': 'ι Cet', 'kaHer': 'Marsic', 'laCet': 'λ Cet', 'laDra': 'Giausar',
    'laHer': 'Maasym', 'laPeg': 'λ Peg', 'laSgr': 'Kaus borealis', 'laVel': 'Suhail', 'M44': 'Praesepe',
    'muCep': 'The garnet star', 'muDra': 'Alrakis', 'muLeo': 'Rasalas', 'muPeg': 'Sadalbari',
    'omeSgr': 'Terebellum', 'pi-4Ori': 'π⁴ Ori', 'rhPup': 'Tureis', 'xiCep': 'Kurhah', 'zeAql': 'Deneb Alokab',
    'zeCen': 'Alnair', 'zeCep': 'ζ Cep', 'zeCnc': 'Tegmine', 'zeHer': 'ζ Her', 'zeTau': 'Al-Hecka',
}
# What each read by before, where that was a name and not its designation.
OLD_NAME = {
    '22Tau': 'Sterope II', 'al-1Cap': 'Algedi', 'al-2Lib': 'Zubenelgenubi', 'alAqr': 'Sadalmelek',
    'alCas': 'Schedar', 'alCyg': 'Deneb', 'alGru': 'Alnair', 'alHer': 'Ras Algethi', 'alPsc': 'Alrischa',
    'alTri': 'Ras Mutallah', 'alUMa': 'Dubhe', 'beCep': 'Alphirk', 'beOph': 'Celbalrai', 'deDra': 'Nodus II',
    'deSgr': 'Kaus Media', 'epCMa': 'Adara', 'epDel': 'Deneb Dulphim', 'epLeo': 'Ras Elased Australis',
    'epSgr': 'Kaus Australis', 'etBoo': 'Mufrid', 'ga-1And': 'Almaak', 'ga-2Vel': 'Suhail al Muhlif',
    'gaAqr': 'Sadalachbia', 'gaCep': 'Alrai', 'gaCyg': 'Sador', 'gaLyr': 'Sulaphat', 'HIP 101120': 'ο Cap',
    'ioCar': 'Scutulum', 'ioCet': 'Deneb Kaitos', 'kaHer': 'Marsik', 'laCet': 'Menkar', 'laDra': 'Giansar',
    'laHer': 'Masym', 'laPeg': 'Sadalbari', 'laSgr': 'Kaus Borealis', 'laVel': 'Alsuhail',
    'M44': 'Praesepe Cluster', 'muCep': 'Erakis', 'muDra': 'Arrakis', 'muLeo': 'Ras Elased Borealis',
    'omeSgr': 'Terebellium', 'pi-4Ori': 'Tabit', 'rhPup': 'Turais', 'xiCep': 'Kurdah',
    'zeAql': 'Deneb el Okab Australis', 'zeCep': 'Kurhah', 'zeCnc': 'Tegmen', 'zeHer': 'Rutilicus',
    'zeTau': 'Al Hecka',
}
SAHL_LABELS = [
    'Aldebaran · α Tau',
    'Algol · β Per',
    'Antares · α Sco',
    'Regulus · α Leo',
    'Sirius · α CMa',
    'Spica · α Vir',
    'Rigel · β Ori',
    'Alpheratz · α And',
    'Altair · α Aql',
    'Capella · α Aur',
    'Menkalinan · β Aur',
    'Toliman · α Cen',
    'Procyon · α CMi',
    'Alphecca · α CrB',
    'Acamar · θ¹ Eri',
    'Castor · α Gem',
    'Pollux · β Gem',
    'Alphard · α Hya',
    'Denebola · β Leo',
    'Zosma · δ Leo',
    'Zuben Eschemali · β Lib',
    'Vega · α Lyr',
    'Betelgeuse · α Ori',
    'Bellatrix · γ Ori',
    'Alnilam · ε Ori',
    'Scheat · β Peg',
    'Fomalhaut · α PsA',
    'Rukbat · α Sgr',
]
# Over every star outside the table but α² Cap, whose one new other name is below: identity,
# label and other names, joined and hashed, as they stood before the table.
UNMOVED_HASH = "03755731206372277e0df3a89d0d395a7912073564f195f246c385f3c1778723"


@pytest.fixture(scope="module")
def stars():
    placed, missing = E.fixed_star_places(2460000.5)
    assert placed and not missing
    return placed


# Each star's other name the unmoved hash stands without: the pin below holds them.
SECOND_NAMES = {("beCet", "Deneb Kaitos"), ("beHer", "Rutilicus")}


@pytest.fixture(scope="module")
def by_designation(stars):
    return {star.designation: star for star in stars}


def test_the_table_holds_each_star_s_form(by_designation):
    assert set(E.FIXED_STAR_SHOWN_NAME) == set(READS_BY) and len(READS_BY) == 51
    for designation, shown in READS_BY.items():
        assert E.fixed_star_shown_name(by_designation[designation]) == shown, designation


def test_a_form_is_printed_once(by_designation):
    for designation, shown in READS_BY.items():
        star = by_designation[designation]
        if shown == E.fixed_star_designation_form(star):
            assert E.fixed_star_second_form(star) is None and E.fixed_star_label(star) == shown
        else:
            assert E.fixed_star_label(star) == f"{shown} · {E.fixed_star_designation_form(star)}"
        assert shown not in star.other_names and shown not in E.fixed_star_other_names_shown(star)


def test_the_old_name_stands_among_its_other_names_once_and_finds_it(by_designation):
    assert len(OLD_NAME) == 49 and set(OLD_NAME) == set(READS_BY) - {"muPeg", "zeCen"}
    for designation, old in OLD_NAME.items():
        star = by_designation[designation]
        assert star.other_names.count(old) == 1 and star.other_names[0] == old, designation
        assert old in E.fixed_star_other_names_shown(star), designation
        assert E.fixed_star_identity(star) in E.fixed_star_find(old), designation


def test_each_new_name_answers_its_star(by_designation):
    for designation, shown in READS_BY.items():
        assert E.fixed_star_identity(by_designation[designation]) in E.fixed_star_find(shown), designation


@pytest.mark.parametrize("written, designations", [
    # Each of these answered nothing, or another star alone, before the table.
    ("Shedar", {"alCas"}), ("Aldubhe", {"alUMa"}), ("Deneb Eldelphin", {"epDel"}), ("Zuben Algenubi", {"al-2Lib"}),
    ("Deneb Alokab", {"zeAql"}),
    # A name one star held and another now reads by offers both.
    ("Kurhah", {"xiCep", "zeCep"}), ("Sadalbari", {"muPeg", "laPeg"}), ("Alnair", {"zeCen", "alGru"}),
    # And the pairs.
    ("Algedi", {"al-1Cap", "al-2Cap"}), ("Algiedi", {"al-1Cap", "al-2Cap"}), ("Menkar", {"alCet", "laCet"}),
    ("Tabit", {"pi-3Ori", "pi-4Ori"}), ("ο Cap", {"HIP 101120", "HIP 101123"}),
    ("Baten Algiedi", {"omeCap"}),
    # A second name of one star that another star keeps among its own.
    ("Deneb Kaitos", {"beCet", "ioCet"}), ("Rutilicus", {"beHer", "zeHer"}),
])
def test_what_the_finder_answers(by_designation, written, designations):
    identities = {star.designation: E.fixed_star_identity(star) for star in by_designation.values()}
    wanted = {identities[d] for d in designations}
    assert set(E.fixed_star_find(written)) == wanted, written


@pytest.mark.parametrize("kind, alike", [("curated", {}), ("significant", {}),
                                         ("full", {"Kuma": 2, "Ukdah": 2, "Jabhat al Akrab": 2})])
def test_no_two_entries_read_alike(stars, kind, alike):
    listed = E.fixed_star_listed(stars, kind)
    assert len(listed) == {"curated": 177, "significant": 486, "full": 1852}[kind]
    names = collections.Counter(E.fixed_star_shown_name(star) for star in listed)
    assert {name: count for name, count in names.items() if count > 1} == alike
    labels = collections.Counter(E.fixed_star_label(star) for star in listed)
    assert max(labels.values()) == 1


def test_no_other_star_moves(stars):
    # The Virgo Cluster's identity is its name and designation since it is read by its number.
    held = sorted(f"{E.fixed_star_identity(star).replace('Virgo Cluster,VC', 'Virgo Cluster')}|{E.fixed_star_label(star)}|"
                  f"{','.join(name for name in star.other_names if (star.designation, name) not in SECOND_NAMES)}"
                  for star in stars if star.designation not in READS_BY and star.designation != "al-2Cap")
    assert hashlib.sha256("\n".join(held).encode("utf-8")).hexdigest() == UNMOVED_HASH


def test_a_second_name_stands_among_the_other_names_and_moves_no_shown_name(by_designation):
    for designation, others, label in [("beCet", ("Difda", "Deneb Kaitos"), "Diphda · β Cet"),
                                       ("beHer", ("Rutilicus",), "Kornephoros · β Her")]:
        star = by_designation[designation]
        assert star.other_names == others and E.fixed_star_label(star) == label
    for designation, name, label in [("ioCet", "Deneb Kaitos", "ι Cet"), ("zeHer", "Rutilicus", "ζ Her")]:
        star = by_designation[designation]
        assert name in star.other_names and E.fixed_star_label(star) == label


def test_the_star_that_keeps_the_name_keeps_all_but_the_other_spelling(by_designation):
    star = by_designation["al-2Cap"]
    assert E.fixed_star_label(star) == "Algedi · α² Cap"
    assert star.other_names == ("Giedi Secunda", "Giedi a2", "Giedi a2", "Algiedi")
    assert by_designation["al-1Cap"].other_names.count("Algiedi") == 1


def test_sahl_s_own_rows_read_as_they_did(stars):
    assert [E.fixed_star_label(star) for star in stars if star.nature is not None] == SAHL_LABELS
    assert not {star.designation for star in stars if star.nature is not None} & set(READS_BY)
    assert E.FIXED_STAR_PAGE_NAME["Zuben Eschamali"] == "Zuben Eschemali"


def test_the_lists_and_the_exports_read_the_new_name(stars):
    rows = {row["Catalogue designation"]: row for row in E.fixed_star_list_rows(stars, full_catalogue=True)}
    for designation, shown in READS_BY.items():
        assert rows[designation]["Name"] == shown, designation
    assert "Menkar" in rows["laCet"]["Other names"]


# --- The old Virgo Cluster row -------------------------------------------------------------------

def _rows():
    return E._on_fixed_star_reader(E._fixed_star_rows_read)


def test_the_file_still_holds_both_rows_and_each_key_its_own(stars):
    both = [row for row in _rows() if row[1] == "Virgo Cluster"]
    assert len(both) == 2
    assert [E._fixed_star_is_old_row(row) for row in both] == [False, True]


def test_the_kept_entry_reads_the_later_place(stars):
    kept = [star for star in stars if star.catalogue_name == "Virgo Cluster"]
    assert len(kept) == 1 and E.fixed_star_identity(kept[0]) == "Virgo Cluster,VC"
    place = E._on_fixed_star_reader(E._fixed_star_place_read, kept[0], 2451545.0)[1]
    assert math.isclose(place[0], 15.0 * (12 + 30 / 60 + 47.3 / 3600), abs_tol=0.01)    # 12h 30m 47.3s
    assert math.isclose(place[1], 12 + 20 / 60 + 13 / 3600, abs_tol=0.01)                # +12° 20' 13"


def test_the_other_identity_is_gone_and_its_designation_finds_the_kept(stars):
    finder = E.fixed_star_finder()
    assert ",VC" not in finder["stars"] and ",VC" not in {E.fixed_star_identity(star) for star in stars}
    assert E.fixed_star_find("VC") == E.fixed_star_find("Virgo Cluster") == ("Virgo Cluster,VC",)
