"""Lane KM (owner's ruling 23 of 2026-10-05; FQ-4, K-42): every word of every
Masha'allah lords cell, in order.

`engine.MASHAALLAH_LORDS` paraphrases, cell by cell, Sahl's twelve lords-of-places
passages in *On Nativities* (Sahl I pp. 368-369, 415-416, 450-451, 486-488,
520-521, 562-563, 605, 651, 666-667, 707-708, 729-730, 746). Until now a test held
three anchor words a cell (test_prose_tables), so a dropped "and honor" passed
(K-42). Before pinning, every cited sentence was read against its page
photograph and every cell against its sentence (the lane's report, KM_BUILD, has
the reading page by page). One cell said what its page does not -- [3][10], the
lord of the tenth in the third -- and four dropped a clause their pages state;
lane KN (the owner's ruling 45) corrected the five, and each is pinned whole.

Two layers:
- `CELLS` pins each cell's locator and its words in order (no corpus needed:
  this runs on CI). A word dropped, two swapped, or one changed fails, and
  `test_a_*` shows it for every cell.
- With the corpus present, each cell's words that its cited sentence(s) do not
  contain -- the paraphrase's own words -- are pinned as a set, so a pin cannot
  be moved to a word the page never had without this file saying which.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache

import pytest

from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

_corpus = needs_corpus()

# Where each of Sahl's twelve lords-of-places passages starts in on_nativities.md.
CHAPTER_STARTS = {
    "1.36": r"^### Chapter \[1\.36\]", "2.14": r"^### \[Chapter 2\.14:", "3.10": r"^### Chapter \[3\.10:\]",
    "4.11": r"^### \[Chapter 4\.11:", "5.1": r"^### \[Chapter 5\.1:", "6.3.4": r"^### Chapter \[6\.3\.4\]",
    "7.1": r"^### Chapter \[7\.\] 1:", "8.5": r"^\[Chapter 8\.5:", "9.4": r"^### \[Chapter 9\.4:",
    "10.2.4": r"^### \[Chapter 10\.2\.4:", "11.1": r"^### \[Chapter 11\.1:", "12.1": r"^### \[Chapter 12\.1:",
}
PAGE = re.compile(r"^\*\[Sahl I p\. \d+\]\*$")


def chapter_lines(lines, chapter):
    start = next(i for i, l in enumerate(lines) if re.match(CHAPTER_STARTS[chapter], l))
    out = []
    for l in lines[start + 1:]:
        if re.match(r"^#{1,4} .*Chapter", l):
            break
        out.append(l)
    return out


def sentences(lines, chapter):
    """{number: text} for a chapter's body, page markers and notes dropped, a
    word split over a page foot joined, numbering gaps (unprinted italic
    titles) stepped over."""
    body, notes = [], {}
    for l in chapter_lines(lines, chapter):
        m = re.match(r"^<sup>(\d+)</sup> (.*)", l)
        if m:
            notes[int(m.group(1))] = html.unescape(m.group(2))
            continue
        if PAGE.match(l) or l.strip() == "---":
            body.append("\x00")
            continue
        body.append(re.sub(r"^#+ ", "", l))
    text = " ".join(body)
    text = re.sub(r"-\s*(?:\x00\s*)+(?=[a-z])", "", text).replace("\x00", " ")
    text = html.unescape(re.sub(r"<sup>\d+</sup>", "", text))
    text = re.sub(r"\*\*(\d+)\*\*", r"\1", text)
    found, pos, n = [], 0, 1
    while True:
        for k in range(n, n + 4):
            m = re.compile(r"(?<![\d.,])%d (?=\S)" % k).search(text, pos)
            if m:
                break
        if not m:
            break
        found.append((k, m.start(), m.end()))
        pos, n = m.end(), k + 1
    out = {}
    for i, (k, _s, e) in enumerate(found):
        stop = found[i + 1][1] if i + 1 < len(found) else len(text)
        out[k] = re.sub(r"\s+", " ", text[e:stop]).strip()
    return out, notes


def words(text):
    """Lower-case words in order (Dykes's brackets and the cells' punctuation fall away)."""
    return re.findall(r"[a-z]+", text.lower())


def cited_source(lines, cite):
    m = re.match(r"([\d.]+), (\d+)(?:-(\d+))?(?: fn (\d+))?$", cite)
    chapter, a, b, fn = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4)
    sents, notes = sentences(lines, chapter)
    parts = [sents[k] for k in range(a, b + 1)]
    if fn:
        parts.append(notes[int(fn)])
    return " ".join(parts)



@lru_cache(maxsize=1)
def _nativities_lines():
    return corpus_file("on_nativities.md").read_text(encoding="utf-8").split("\n")


# (placed_in, ruled): (locator, the cell's words as read, the paraphrase's own words)
CELLS = {
    (1, 1): ('1.36, 79-81', "Respected in his family; if it connects with a planet in the Midheaven, rank from the Sultan by that planet's dignity, or rank through the loss of his religion and honor if the planet is in its fall",
             ('by', 'dignity', 'is', 'or', 's', 'that')),
    (1, 2): ('2.14, 9', 'Works with his own hands, blessed without searching or need; better if received',
             ('better', 'or', 'works')),
    (1, 3): ('3.10, 1', 'Good for his siblings: they get good from him and are sincere towards him',
             ('are', 'for', 'get')),
    (1, 4): ('4.11, 2-3', 'Master of his family, their livelihood from him, charitable to his parents and an authority to them; if an infortune looked at it, hardship for the parents over authority',
             ('over',)),
    (1, 5): ('5.1, 78', 'Blessed with children in his youth; his eye pleased, and he happy',
             ()),
    (1, 6): ('6.3.4, 12', 'An illness of the essence of that planet; the death of his animals, if he has them, and of his servants',
             ('has',)),
    (1, 7): ('7.1, 205', 'Good from women, and he successful',
             ()),
    (1, 8): ('8.5, 2', 'If free of the infortunes, a long lifespan, but frustrated and hard put to find his necessities',
             ('find', 'hard', 'put', 'to')),
    (1, 9): ('9.4, 23', 'Of fine religion and a good soul, endearing, knowing the Sunnah',
             ('and',)),
    (1, 10): ('10.2.4, 1', 'An associate of authority, proficient in his work; the Sultan comes to him without his seeking it',
             ('comes',)),
    (1, 11): ('11.1, 16', 'Successful, with a good livelihood and condition, and glad',
             ()),
    (1, 12): ('12.1, 35', 'Unhappy; his enemies multiply and are victorious over him; tribulations, and he belligerent',
             ('are',)),
    (2, 1): ('1.36, 83', 'A corruptor of assets; if the lord of its house looked at it and received it, he gains properly, from the essence of the sign the lord of the second is in',
             ('gains',)),
    (2, 2): ('2.14, 10-11', 'A livelihood from a known source; if the lord of the third looked at it, suffering siblings; if an infortune looked at it, his assets ruined and scattered',
             ('ruined', 'scattered')),
    (2, 3): ('3.10, 2', 'His siblings contend with him over his assets; sorrows come upon them, and they seek him out',
             ('come', 'out', 'over')),
    (2, 4): ('4.11, 4', 'Prosperous parents, good in what they leave behind; he inherits their assets and is the most distinguished of his brothers over the parents',
             ('inherits', 'is', 'their')),
    (2, 5): ('5.1, 79', 'Children blessed with a livelihood under their own authority, and with the Sultan',
             ()),
    (2, 6): ('6.3.4, 13', 'A livelihood from what slaves produce and the renting of animals; blessed from a lowly thing',
             ('what',)),
    (2, 7): ('7.1, 206', 'Corrupts his assets because of a contention; his women die, and have defects',
             ()),
    (2, 8): ('8.5, 3', 'Blessed by inheritance; sometimes in the steady employ of the Sultan',
             ()),
    (2, 9): ('9.4, 24', 'Assets from a country not his own; blessed in relation to journeys',
             ()),
    (2, 10): ('10.2.4, 2', 'A livelihood from the Sultan and because of him; he accumulates assets',
             ('a', 'accumulates')),
    (2, 11): ('11.1, 17', 'Blessed by his friends, getting assets because of them',
             ()),
    (2, 12): ('12.1, 36', 'A work he is embarrassed about; a bad character and a bad livelihood, with deception in it',
             ()),
    (3, 1): ('1.36, 84-85', 'Siblings suited to him who get good from him; he depends on them and travels much; if a fortune looked at it, good religion, if an infortune, wicked in his mind',
             ('depends', 'get', 'on', 'suited', 'to', 'travels', 'who')),
    (3, 2): ('2.14, 12', 'Gain from travels and because of siblings; if it is a fortune, religion, and gain by it',
             ('by', 'is')),
    (3, 3): ('3.10, 3', 'Well-known siblings who go to him and protect him, since he is loved',
             ()),
    (3, 4): ('4.11, 5-6', "Siblings from whom the parents meet hardship and hostility; he is better than his siblings in his parents' opinion, and seldom does them good; if an infortune looked at it, the parents confined in prisons, tribulation and hardship at their death, and the siblings most wretched",
             ('confined', 'does', 'hostility', 'is', 'meet', 'whom')),
    (3, 5): ('5.1, 80', 'Children named with the names of his siblings, successful in travels',
             ()),
    (3, 6): ('6.3.4, 14', "Siblings with defects or illness, or doing the work of slaves; it shows the siblings' livelihood",
             ('doing', 'shows')),
    (3, 7): ('7.1, 207', 'His brother marries a woman of his; he is hostile to his siblings, or marries his relatives, and his marriage is abroad',
             ('is', 'marries')),
    (3, 8): ('8.5, 4', 'Siblings with defects, chronic illness and disease, doing the work of slaves, and diminished',
             ('diminished', 'doing', 'with')),
    (3, 9): ('9.4, 25', 'His siblings marry foreign women; he moves from his own country to another',
             ('moves',)),
    (3, 10): ('10.2.4, 3', 'Few siblings, and any he has will be ruined; it multiplies travels',
             ('any', 'has')),
    (3, 11): ('11.1, 18', 'Well-known siblings, their condition good, blessed in their youth',
             ('condition',)),
    (3, 12): ('12.1, 37', 'His siblings hostile towards him; hardship from them, and the badness of their condition',
             ()),
    (4, 1): ('1.36, 86', 'Reverent towards his parents, hardship from the Sultan, a livelihood he is pleased with; if received where it stands, good or rank from his fathers',
             ('stands', 'where')),
    (4, 2): ('2.14, 13', "Gain in relation to fathers and ancestors: the fathers' assets good, the house he was born in thriving, their condition good, and he devoted to his parents",
             ('gain', 'good')),
    (4, 3): ('3.10, 4', "The siblings steal the parents' assets, and the family recognizes them as the thieves",
             ('recognizes',)),
    (4, 4): ('4.11, 7-8', "Parents well known among the people, with importance and a reputation; if an infortune looked at it, or the Sun made it unfortunate, the parents' lifespan is short",
             ('is', 'short', 'with')),
    (4, 5): ('5.1, 81', 'Children who are wretches; hardship and enmity because of them',
             ()),
    (4, 6): ('6.3.4, 15', 'Of the children of slaves, or of those who do the work of slaves',
             ()),
    (4, 7): ('7.1, 208', 'Marries a woman from the people of his own house, well known and virtuous',
             ('marries',)),
    (4, 8): ('8.5, 5', 'The fathers foreigners, or with defects or chronic illness, and their lifespans diminished',
             ()),
    (4, 9): ('9.4, 26', 'Parents with hidden illnesses, dying outside their homeland',
             ('dying', 'with')),
    (4, 10): ('10.2.4, 4', 'The parents of the people of the house well known at the doors of the Sultan, and hardship from the Sultan',
             ()),
    (4, 11): ('11.1, 19', "His father with a chronic illness, the parents' lives shortened, and his condition diminished",
             ('diminished', 'parents', 'with')),
    (4, 12): ('12.1, 38', 'The parents and family hostile towards him and quarrelling with him; he destroys the home he was born in and moves from it',
             ('destroys', 'moves', 'quarrelling')),
    (5, 1): ('1.36, 87', 'Happy with children and many friends; if an infortune looked, that is undermined',
             ('is', 'undermined')),
    (5, 2): ('2.14, 14', 'Gain in relation to women and his children, or those known at the door of the Sultan; they gain the good, or importance among their class',
             ('his',)),
    (5, 3): ('3.10, 5', 'Siblings away from the homeland who travel much and are blessed with suitable children',
             ('are', 'who')),
    (5, 4): ('4.11, 9', 'Prosperous parents who see children and grandchildren and reach a full lifespan, if no infortune looks while the fortunes do; they increase in the good',
             ('grandchildren', 'looks', 'no', 'reach', 'see', 'who')),
    (5, 5): ('5.1, 82', 'Well-known children, and happy',
             ('and',)),
    (5, 6): ('6.3.4, 16', 'The upbringing of his children hard, and a defect in them',
             ('them',)),
    (5, 7): ('7.1, 209', 'Marries a woman younger than himself, with compassion and goodness of character',
             ('marries', 'with')),
    (5, 8): ('8.5, 6', 'His children die in their youth, or have more power over the people because of the Sultan',
             ()),
    (5, 9): ('9.4, 27', 'Children in a country not his own, and he will marry; his eye delights in the children',
             ('delights',)),
    (5, 10): ('10.2.4, 5', 'His children with a chronic illness or disease, and they die; they meet hardship from the Sultan',
             ('meet', 'with')),
    (5, 11): ('11.1, 20', 'Delightful children, blessed with good and comfort from the first of them to the last',
             ()),
    (5, 12): ('12.1, 39', 'His children disobey him and are hostile towards him; defects in them, and their condition bad',
             ('are',)),
    (6, 1): ('1.36, 88-89', "Miserable, doing slaves' work; if received, illnesses occur; if the Moon is also corrupted and connects with a planet in a corrupt place, he becomes a slave",
             ('becomes', 'connects', 'is', 'occur')),
    (6, 2): ('2.14, 15-16', 'Gain in relation to slaves, riding animals and medications; if received, or the lord of the Ascendant looked at it, gain from medications and the illness of animals and slaves; if not received, or made unfortunate, his animals ruined, disaster in his assets, a bad condition, and a livelihood of toil and hardship',
             ('ruined',)),
    (6, 3): ('3.10, 6', 'His siblings are hostile to him, seek his calamity and crave his ruin',
             ('are',)),
    (6, 4): ('4.11, 10-12', "Parents unknown in the country they are in, their condition read from the planets connected with it: if an infortune looked, harm to them by illnesses of the sign's nature; if a fortune looked, good abroad, and at home too if that fortune received it",
             ('abroad', 'at', 'by', 'home', 'read', 's', 'them', 'too')),
    (6, 5): ('5.1, 83', 'Fortunate children, but defects appear in them',
             ()),
    (6, 6): ('6.3.4, 17', 'Healthy, if the lord of the Ascendant does not look at it',
             ()),
    (6, 7): ('7.1, 210', 'Associates with slave girls or women with defects',
             ('associates',)),
    (6, 8): ('8.5, 7', 'His calamities in slaves and riding animals; no blessing from them',
             ('blessing', 'from', 'no')),
    (6, 9): ('9.4, 28', 'Blessed with slaves and riding animals; ill on journeys, or if healthy, his slaves corrupted, one of the two without escape',
             ('corrupted', 'or', 'without')),
    (6, 10): ('10.2.4, 6', 'A short lifespan; he lives by walking about; he enslaves free people and has authority over them',
             ('about', 'enslaves', 'has', 'lives')),
    (6, 11): ('11.1, 21', 'A bad condition in his livelihood, little good, creating discord',
             ()),
    (6, 12): ('12.1, 40', 'Saddened by his slaves and riding animals, and no good in them',
             ()),
    (7, 1): ('1.36, 90', 'Many lawsuits; deceptive; subordinate to women in what they say',
             ('say', 'they', 'what')),
    (7, 2): ('2.14, 17-19', "Gain from women and lawsuits; if nothing looks at it, it is not received and the lord of the Ascendant does not look, he gathers assets mostly outside contention, his women die and he marries servant women; if the Ascendant lord aspects the second lord and 'it' is an infortune, assets are wasted through lawsuits and women, with hardship [antecedent of 'it' uncertain: either lord; 2.14, 19]",
             ('antecedent', 'are', 'aspects', 'does', 'either', 'gain', 'gathers', 'looks', 'marries', 'mostly', 'nothing', 'outside', 'second', 'through', 'uncertain', 'wasted', 'with')),
    (7, 3): ('3.10, 7', 'Either his brothers marry some of his women and have children by them, or they are hostile to him',
             ('are', 'by', 'have', 'them')),
    (7, 4): ('4.11, 13', 'He marries a woman somewhat above him, from his own family; the fathers held base, and the father hostile to him and contending with him',
             ('above', 'contending', 'held', 'marries')),
    (7, 5): ('5.1, 84', 'His children mostly from his maids and the women of his service; they are hostile to him, and he deceives himself about the women',
             ('about', 'are', 'deceives', 'mostly')),
    (7, 6): ('6.3.4, 18', 'Associates with women who have no social esteem, and bad words are said about him',
             ('are', 'associates', 'no')),
    (7, 7): ('7.1, 211', 'Marries a well-known woman, an equal match for him, whom he loves',
             ('loves', 'marries')),
    (7, 8): ('8.5, 8', 'Marries women with inheritances, inherits and gets their assets from them; dies in exile',
             ('dies', 'gets', 'inherits', 'marries', 'with')),
    (7, 9): ('9.4, 29', 'Marries a foreign woman of good, pleasing character; if it is a fortune, she is pious',
             ('is', 'marries')),
    (7, 10): ('10.2.4, 7', "Marries a woman more powerful and significant than himself, from the people of the Sultan's house, sensible and upright",
             ('marries', 's')),
    (7, 11): ('11.1, 22', 'A woman he loves, who is lucky; children by her, and benefit from them',
             ('by',)),
    (7, 12): ('12.1, 41', 'Mixes with low women with defects in them, and they are hostile towards him',
             ('are', 'mixes')),
    (8, 1): ('1.36, 91', 'A wicked soul, much distress, faint-hearted',
             ()),
    (8, 2): ('2.14, 20-21', 'Gain in relation to inheritance and the dead; generous with his gains, careless where they come from and go; if it connects with the lord of the eighth, his assets taken by force and he one who imposes taxes; if the lord of the eighth connects with it, gain from the dead and inheritances',
             ('careless', 'come', 'connects', 'go', 'imposes', 'one', 'they')),
    (8, 3): ('3.10, 8', "His brothers' women do not survive, and they get inheritances in relation to women",
             ('do',)),
    (8, 4): ('4.11, 14-15', "Diminishes the fathers' lifespan; fear for the native; the mother dies in childbirth, worse if the Moon is corrupted or connecting with a retrograde planet; if it is the Sun, fear for the father; a fortune looking changes some of this",
             ('changes', 'dies', 'fear', 'looking', 'this', 'worse')),
    (8, 5): ('5.1, 85 fn 47', "Partly illegible. Dykes's tentative interpretation: the children suffer or die, and those surviving are premature.",
             ('are', 'dykes', 'interpretation', 'partly', 's', 'surviving', 'tentative')),
    (8, 6): ('6.3.4, 19', 'Healthy, if the lord of the Ascendant does not look at it',
             ()),
    (8, 7): ('7.1, 212', 'Consumes the inheritance of the women; a foreign woman',
             ()),
    (8, 8): ('8.5, 9', 'Healthy, his illness insignificant, and his death light',
             ()),
    (8, 9): ('9.4, 30', 'Highway robbery on journeys; eager in the accumulation of assets',
             ()),
    (8, 10): ('10.2.4, 8', 'Authority in his younger years; a follower who seeks the leadership and is boastful',
             ('is', 'seeks', 'who')),
    (8, 11): ('11.1, 23', 'Not well known nor of distinguished descent; low work such as commerce',
             ()),
    (8, 12): ('12.1, 42', 'Few enemies; many of his slaves die',
             ()),
    (9, 1): ('1.36, 92', 'Stays in a land other than his birthplace, travels much, speaks of knowledge; if free of the infortunes, knowledgeable and sensible',
             ('birthplace', 'much', 'other', 'speaks', 'stays', 'than')),
    (9, 2): ('2.14, 22-24', 'Gain in relation to travels, piety and religion; if the lord of the Ascendant looked at it, a livelihood from travels and absence from home; if it does not look at it, gain by means of kindliness in the travels; if a fortune looked at it and received it, from religion and devoutness; if an infortune, or one inimical to it, a master of magic and remedies',
             ('absence', 'one')),
    (9, 3): ('3.10, 9', 'His siblings marry foreign women away from the homeland, and live and shelter with them',
             ('live', 'marry')),
    (9, 4): ('4.11, 16-17', 'The fathers unknown, moving from their homes, with a defect in them, dying a bad death with pains; if the sign is four-footed, one who employs riding animals, a deceiver without piety',
             ('dying', 'with', 'without')),
    (9, 5): ('5.1, 86', 'Children while absent from his homeland; they make him happy and please his eye',
             ('please',)),
    (9, 6): ('6.3.4, 20', 'Excellent intentions; ill while away from home, and hardship met',
             ('met',)),
    (9, 7): ('7.1, 213', 'Marries a foreign woman whom her brother gives in marriage, and he loves her',
             ('gives', 'loves', 'marries', 'whom')),
    (9, 8): ('8.5, 10', 'Bad thoughts and work; dies in exile',
             ('dies',)),
    (9, 9): ('9.4, 31', 'Few journeys; upright in the religion of his fathers, good in intention',
             ()),
    (9, 10): ('10.2.4, 9', 'Authority in traveling abroad, his leadership in it, and the good offered to him',
             ('him', 'to')),
    (9, 11): ('11.1, 24', 'Good fortune and the good when out of the country; happy until the end of his life',
             ()),
    (9, 12): ('12.1, 43', 'His siblings meet hardship from enemies, and he too if he travels; bad religion',
             ('meet', 'too')),
    (10, 1): ('1.36, 93', 'At the doors of the Sultan, known to him and making himself known, living by them',
             ('living', 'making')),
    (10, 2): ('2.14, 25', 'Gain at the doors of the Sultan and because of him',
             ('gain',)),
    (10, 3): ('3.10, 10', 'Death and ruin of the siblings; he is jealous of them, and they hate each other',
             ('is',)),
    (10, 4): ('4.11, 18-19', 'The fathers well known in the house of the Sultan, and he grows in knowledge with them, if received; if an infortune looked and it is not received, hardship, tribulation and conflict from the Sultan',
             ('grows', 'is')),
    (10, 5): ('5.1, 87', 'Illness and a defect appearing in his children',
             ()),
    (10, 6): ('6.3.4, 21', 'He will encounter hardship from the Sultan',
             ()),
    (10, 7): ('7.1, 214', 'Marries one of the family of the house of the Sultan, a fortunate woman, and gets good from her',
             ('and', 'gets', 'marries')),
    (10, 8): ('8.5, 11', 'His ruin because of the Sultan, and at his hands',
             ()),
    (10, 9): ('9.4, 32', "His siblings marry women better than themselves, or of the family of the Sultan's house; he is pious",
             ('is', 's')),
    (10, 10): ('10.2.4, 10', 'Proficient in work, with influence in it and informed in it; his livelihood from it',
             ('with',)),
    (10, 11): ('11.1, 25', 'Authority in his friendship; the Sultan of his people not hostile',
             ()),
    (10, 12): ('12.1, 44', 'The Sultan and those who wield power over him hostile; his sorrow and griefs last a long time',
             ()),
    (11, 1): ('1.36, 94', 'A good character and many friends, but harsh towards children, and few of them',
             ('and', 'them')),
    (11, 2): ('2.14, 26-27', 'Gain in relation to friends and commerce; if the lord of the Ascendant looked at it, a good condition and livelihood, his friends in need of him; if not, he in need of his friends',
             ('gain',)),
    (11, 3): ('3.10, 12', 'Pious siblings renowned for it, and they attribute it to him',
             ()),
    (11, 4): ('4.11, 20', "The father's lifespan short and the badness of the parents' condition, unless received by the lord of its house, which dissolves that and raises them up; better still if a fortune looked at it",
             ('parents', 'raises', 'short', 'still', 'them', 'which')),
    (11, 5): ('5.1, 88', 'His eye pleased with his children and the family of his house, and he praised',
             ()),
    (11, 6): ('6.3.4, 22', 'Befriends and associates with people who are not well known',
             ('associates', 'befriends')),
    (11, 7): ('7.1, 215', 'Marries a fertile woman, loves her, and lives in luxury because of her',
             ('lives', 'loves', 'marries')),
    (11, 8): ('8.5, 12', 'His friends diminished and what is between them corrupted; he dies when his condition is good',
             ('corrupted', 'dies')),
    (11, 9): ('9.4, 33', 'Pious friends who love him in the religion of God; his siblings marry foreign women',
             ('pious', 'who')),
    (11, 10): ('10.2.4, 11', 'His friends get good from him; his child inherits assets which he collects from the Sultan',
             ('collects', 'inherits')),
    (11, 11): ('11.1, 26', 'A comfortable life, imputed with goodness, with many friends and much culture',
             ()),
    (11, 12): ('12.1, 45', 'He leaves the goodness of friends, and they return to enmity; unhappy',
             ('leaves',)),
    (12, 1): ('1.36, 95-97', 'Miserable, a bad livelihood, many enemies who prevail over him; if it connects with no planet in a stake or an excellent place, the planet in its nature, miserable until ruined; if the planet it connects with is an infortune or harmed, enemies kill him',
             ('harmed', 'no', 'prevail')),
    (12, 2): ('2.14, 28', 'Gain in relation to prisons and enemies; poor in soul, much distressed',
             ('gain',)),
    (12, 3): ('3.10, 13', 'His siblings are hostile to him, take his authority and are superior to him',
             ('are', 'take')),
    (12, 4): ('4.11, 21-23', 'The fathers foreigners who left their own land for the badness of their condition, one of them devout; if a fortune looked at it, good in the exile, if an infortune, tribulation; best if the fortune received it, then good or elevated status in the exile',
             ('best', 'devout', 'then')),
    (12, 5): ('5.1, 89-90', 'Children with a defect or chronic illness, dying of that disease; if made unfortunate, no children',
             ('dying', 'no', 'with')),
    (12, 6): ('6.3.4, 23', 'Hostile to people who <do not> have social esteem, and they come to harm',
             ()),
    (12, 7): ('7.1, 216', 'Marries a woman with no social esteem; hardship from her, and she hostile to him',
             ('marries', 'no', 'with')),
    (12, 8): ('8.5, 13', 'Fear that enemies kill him, or that the foolish fight him',
             ('fear',)),
    (12, 9): ('9.4, 34', 'Wicked in his intention, a corruptor of religion, thinking himself in the right',
             ('thinking',)),
    (12, 10): ('10.2.4, 12', 'Dispossessed by the authorities; griefs and hardship from them',
             ()),
    (12, 11): ('11.1, 27', 'Little good, miserable in his way of living, few friends and many enemies',
             ()),
    (12, 12): ('12.1, 46', 'Few enemies, who do not appear to him; safe from their evil',
             ('do', 'who')),
}

# The cells' notes and details, word for word.
EXTRA = {
    (1, 7): {'note': "Alternative translation — 7.1, 205 fn 130: 'victorious'."},
    (1, 10): {'note': "Alternative translation — 10.2.4, 1 fn 160: 'master'."},
    (2, 2): {'note': "Alternative translation — 2.14, 10 fn 197: 'self-employed'."},
    (2, 5): {'note': "Referent uncertain; fn 45 suggests 'he,' one of the children."},
    (3, 4): {'note': "Variant — 4.11, 5 fn 160. E: 'he'; M: 'they,' referring to the parents' siblings. Referent — fn 161: 'them' seems to refer to the siblings."},
    (5, 4): {'note': "Conjecture — 4.11, 9 fn 163: 'prosperity' is a conjectured alternative whose required accusative ending is absent from both manuscripts."},
    (6, 1): {'note': "Interpretive note — fn 489: Dykes says Masha'allah seems to regard sickness as preferable to slavery; this does not cancel the following Moon clause."},
    (8, 3): {'note': 'Translation speculative; fn 115.'},
    (8, 5): {'detail': "Surviving printed wording: 'they will survive and will be miscarried'. Dykes's fn 47 says 'miscarried' can also mean very premature; his interpretation remains tentative."},
    (8, 11): {'note': "Variant — 11.1, 23 fn 16: the Latin WSM reads 'it signifies the loss of his neighbors and friends'; the printed translation retains commerce."},
    (9, 2): {'note': "Alternative translation — 2.14, 23 fn 201: 'pity in the travels'."},
    (9, 7): {'note': "Referent — 7.1, 213 fn 133: 'he' is taken to be the native."},
    (9, 10): {'note': "Variant — 10.2.4, 9 fn 163. M: 'the good will be strengthened.'"},
    (10, 4): {'note': "Variant — 4.11, 18 fn 165. M: 'the parents will be well known in the house of the Sultan'. Alternative translation — fn 166: 'he will be better at being a well-known acquaintance ... of the Sultan, as they are'."},
    (10, 11): {'note': "Variant — 11.1, 25 fn 17: E's 'youth'. Alternative translation — fn 18: '[his] authority over his family will not be hostile'."},
    (11, 5): {'note': "Pronoun disputed; fn 48 prefers 'they'."},
    (11, 11): {'note': "Alternative translation — 11.1, 26 fn 19: 'traced to a good lineage'."},
    (12, 6): {'note': "Variant — 6.3.4, 23 fn 161. M reverses the clause: 'they will not come' [to harm]."},
}


def _pin_holds(placed_in, ruled, text):
    """True when `text` carries exactly the pinned words in order."""
    return words(text) == words(CELLS[(placed_in, ruled)][1])


KEYS = sorted(CELLS)
IDS = [f"lord-of-{r}-in-{p}" for p, r in KEYS]


def test_every_cell_is_pinned_once(engine):
    table = engine["MASHAALLAH_LORDS"]
    assert sorted((p, r) for p, row in table.items() for r in row) == KEYS
    assert len(KEYS) == 144


@pytest.mark.parametrize("placed_in, ruled", KEYS, ids=IDS)
def test_lords_cell_keeps_its_words_in_order(engine, placed_in, ruled):
    cell = engine["MASHAALLAH_LORDS"][placed_in][ruled]
    assert cell["cite"] == CELLS[(placed_in, ruled)][0]
    assert _pin_holds(placed_in, ruled, cell["text"]), (words(cell["text"]), CELLS[(placed_in, ruled)][1])
    # and the text itself, which the words cannot see: a digit ("2.14, 19") and
    # Dykes's pointed brackets ("<do not>") (lane TL, TL-26)
    assert cell["text"] == CELLS[(placed_in, ruled)][1], (cell["text"], CELLS[(placed_in, ruled)][1])


@pytest.mark.parametrize("placed_in, ruled", KEYS, ids=IDS)
def test_lords_cell_notes_keep_their_words(engine, placed_in, ruled):
    cell = engine["MASHAALLAH_LORDS"][placed_in][ruled]
    assert {k: cell[k] for k in ("note", "detail") if k in cell} == EXTRA.get((placed_in, ruled), {})


def _mutations(text):
    """A dropped word, two neighbours swapped, one word changed."""
    w = text.split()
    mid = len(w) // 2
    dropped = w[:mid] + w[mid + 1:]
    i = next(k for k in range(len(w) - 1) if words(w[k]) != words(w[k + 1]))
    swapped = w[:i] + [w[i + 1], w[i]] + w[i + 2:]
    changed = w[:mid] + ["never" if words(w[mid]) != ["never"] else "always"] + w[mid + 1:]
    return {"dropped": " ".join(dropped), "swapped": " ".join(swapped), "changed": " ".join(changed)}


WHOLE = [k for k in KEYS if CELLS[k][1] is not None]
WHOLE_IDS = [i for k, i in zip(KEYS, IDS) if CELLS[k][1] is not None]


@pytest.mark.parametrize("how", ["dropped", "swapped", "changed"])
@pytest.mark.parametrize("placed_in, ruled", WHOLE, ids=WHOLE_IDS)
def test_a_word_dropped_swapped_or_changed_fails_the_pin(engine, placed_in, ruled, how):
    text = engine["MASHAALLAH_LORDS"][placed_in][ruled]["text"]
    assert _pin_holds(placed_in, ruled, text)
    mutated = _mutations(text)[how]
    assert not _pin_holds(placed_in, ruled, mutated), (how, mutated)


@pytest.mark.parametrize("how, old, new", [("dropped", "Few siblings,", "Few,"),
                                           ("swapped", "Few siblings,", "Siblings few,"),
                                           ("changed", "Few siblings,", "Many siblings,")])
def test_a_word_dropped_swapped_or_changed_in_the_pinned_head_of_3_10_fails(engine, how, old, new):
    text = engine["MASHAALLAH_LORDS"][3][10]["text"]
    assert _pin_holds(3, 10, text) and text.startswith(old)
    assert not _pin_holds(3, 10, text.replace(old, new, 1)), how


def test_k42_and_honor_is_pinned(engine):
    """K-42: dropping "and honor" from the lord of the Ascendant in the
    Ascendant (1.36, 81, Sahl I p. 368: "the loss of his religion and honor")
    passed every test before this file."""
    text = engine["MASHAALLAH_LORDS"][1][1]["text"]
    assert "religion and honor" in text
    assert not _pin_holds(1, 1, text.replace(" and honor", ""))


@_corpus
@pytest.mark.parametrize("placed_in, ruled", WHOLE, ids=WHOLE_IDS)
def test_lords_cell_adds_only_its_listed_words_to_the_page(engine, placed_in, ruled):
    cite, _text, own = CELLS[(placed_in, ruled)]
    cell = engine["MASHAALLAH_LORDS"][placed_in][ruled]
    source = words(cited_source(_nativities_lines(), cite))
    assert source, cite
    assert sorted(set(words(cell["text"])) - set(source)) == list(own), cite


@_corpus
def test_a_word_the_page_never_had_fails_the_page_layer(engine):
    cite, text, own = CELLS[(2, 3)]
    source = set(words(cited_source(_nativities_lines(), cite)))
    mutated = text.replace("sorrows", "joys")
    assert "joys" not in source
    assert sorted(set(words(mutated)) - source) != list(own)


def test_lord_of_the_tenth_in_the_third_has_the_siblings_ruined_as_the_page_says(engine):
    """10.2.4, 3 (Sahl I pp. 707-708): "he will have few siblings, and if he did
    have siblings they will be ruined, and it multiplies travels". The cell
    read "Few siblings, and those he has ruined", which reads as the native
    ruining them. Lane KN (ruling 45) reworded it to "any he has will be
    ruined"; its words are now pinned whole in CELLS."""
    text = engine["MASHAALLAH_LORDS"][3][10]["text"]
    assert "he has ruined" not in text
    assert re.search(r"\b(?:are|be|is) ruined\b", text), text

