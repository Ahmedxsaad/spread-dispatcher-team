"""Reads a dealer's note, in Finnish, Swedish or English: what it says about when the car can be
collected, when the sites are open, when the car must arrive, and what the driver needs.

The reader works in four steps. It repairs typos against the words that dealers use often
(words.txt). It cuts the note into sentences and takes out denied times ("not 3pm") and
corrections ("eikun pe"), which change the time before them. It finds each time: a day, a
clock time, or opening hours as a range. Then the words of the sentence say what the time means.
A time that the reader cannot place makes the note `unsure`, and the desk then gives no price.
analysis/notes_score.py measures the reader against what each note really meant."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .clock import DAY, HOUR

# words.txt: each word that dealers' notes use, with the number of distinct notes that use it.
COUNTS = {word: int(count) for word, count in (line.split() for line in (Path(__file__).parent / "words.txt").read_text(encoding="utf-8").splitlines())} \
    if (Path(__file__).parent / "words.txt").exists() else {}
COMMON = {word for word, count in COUNTS.items() if count >= 25}  # a typo is repaired to one of these


@dataclass
class Facts:
    """What a note changes. Clock times are minutes of the day; `ready_at` and `deliver_by` are world minutes."""
    manual: bool = False  # only a driver with a manual licence can collect the car
    plates: bool = False  # the driver must fetch transfer plates
    summer_tyres: bool = False  # the car cannot be driven in snow
    ready_at: Optional[int] = None  # the car cannot be collected before
    pickup_opens: Optional[int] = None
    pickup_closes: Optional[int] = None
    delivery_opens: Optional[int] = None
    delivery_closes: Optional[int] = None
    deliver_by: Optional[int] = None  # a deadline of the note's own
    unsure: bool = False  # the note has a time that the reader could not place


# --- words ---

FI_HOURS = {form: hour for hour, forms in {
    1: "yhden yhdelta yhdesta yhteen yhta", 2: "kahden kahdelta kahdesta kahteen kahta", 3: "kolmen kolmelta kolmesta kolmeen kolmea",
    4: "neljan neljalta neljasta neljaan neljaa", 5: "viiden viidelta viidesta viiteen viitta", 6: "kuuden kuudelta kuudesta kuuteen kuutta",
    7: "seitseman seitsemalta seitsemasta seitsemaan seitsemaa", 8: "kahdeksan kahdeksalta kahdeksasta kahdeksaan kahdeksaa",
    9: "yhdeksan yhdeksalta yhdeksasta yhdeksaan yhdeksaa", 10: "kymmenen kymmenelta kymmenesta kymmeneen kymmenta",
    11: "yksitoista yhdentoista yhdeltatoista yhdestatoista yhteentoista yhtatoista",
    12: "kaksitoista kahdentoista kahdeltatoista kahdestatoista kahteentoista kahtatoista"}.items() for form in forms.split()}
FI_BARE = {"yksi": 1, "kaksi": 2, "kolme": 3, "nelja": 4, "viisi": 5, "kuusi": 6}  # read only after "klo" or "puoli"
SV_HOURS = {"ett": 1, "tva": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "sju": 7, "atta": 8, "nio": 9, "tio": 10, "elva": 11, "tolv": 12}
EN_HOURS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
WORD_HOURS = {**FI_HOURS, **FI_BARE, **SV_HOURS, **EN_HOURS}

TODAY = {"tanaan": 0, "today": 0, "idag": 0, "huomenna": 1, "tomorrow": 1, "tmrw": 1, "tmr": 1, "imorgon": 1, "imorron": 1,
         "ylihuomenna": 2, "overmorgon": 2}
WEEKDAYS = {name: day for day, names in enumerate([
    "ma maanantai maanantaina maanantaihin maanantaiksi mon monday man mandag pa_mandag",
    "ti tiistai tiistaina tiistaihin tiistaiksi tue tues tuesday tis tisdag",
    "ke keskiviikko keskiviikkona keskiviikkoon keskiviikoksi wed wednesday ons onsdag",
    "to torstai torstaina torstaihin torstaiksi thu thur thurs thursday tor tors torsdag",
    "pe perjantai perjantaina perjantaihin perjantaiksi fri friday fre fredag",
    "la lauantai lauantaina lauantaihin sat saturday lor lordag",
    "su sunnuntai sunnuntaina sunnuntaihin sun sunday son sondag"]) for name in names.split()}
SHORT_DAYS = {"fi": {"ma", "ti", "ke", "to", "pe", "la", "su"}, "sv": {"man", "tis", "ons", "tor", "tors", "fre", "lor", "son"}, "en": {"mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun"}}
ALL_SHORT = set().union(*SHORT_DAYS.values())

MANUAL = re.compile(r"\bma+n+[au]{1,3}[ai]?l|\bmanuaa|manuell|k[a-z]{2,4}vaa?iht|stick shift|vaihdekeppi")
NOT_MANUAL = re.compile(r"ei manuaal|not a? ?manual|inte manuell|ingen manuell")
PLATES = re.compile(r"kilv|kilpi|kilpe|ilman ki|rekkar|poistettu rekisterista|plates|pltaes|paltes|unregistered|skylt|oregistrerad|avregistrerad")
ON_SUMMER_TYRES = re.compile(r"kesar+en+k[a-z]*lla\b|kesar[a-z]+ alla|viela kesa|kesakumit alla|kesakumeilla|talvirenkaita ei|ei talvirenkaita|talvet puuttuu|still on [a-z]+ tyres"
                             r"|on summer tyres|summer tyres on|summers? still on|still on summers?|no winters|no winter tyres|winter tyres not|winters not"
                             r"|sommardack pa|pa sommardack|inga vinterdack|utan vinterdack|vinterdacken inte")
REFERENCE = re.compile(r"\b(?:viite|viitenro|viitenumero|meidan viite|ref|reference|our ref|booking ref|order no|ordernr|order|varaus|varausnro|tilausnro|tilausnumero|tilaus|referens|bokning"
                       r"|koodi|code|kod|ruudussa|ruutu|paikka|bay|spot|plats|ruta|puh|tel|phone)\b[\s.:#]*\d[\d ]*")
COUNT = re.compile(r"\b\d+\s*(?:min\b|minuuttia|minutes|minuter|[a-z]*rengasta|[a-z]*renkaat|sarjaa|[a-z]* ?wheels|[a-z]* ?tyres|sets?\b|[a-z]*dack|hjul|kpl|t?km\b|h\b|tuntia|timm)")
ABBREVIATION = re.compile(r"\b(viim|klo|kl|n|oik|vas|t|esim|huom|obs|nro|ca|approx|" + "|".join(sorted(ALL_SHORT)) + r")\.(?=\s|$)")
WEEK_RANGE = re.compile(r"\b(?:ma|mon|man)\s*-\s*(?:pe|fri|fre)\b|\b(?:arkisin|arkipaivisin|weekdays|vardagar|mon to fri|monday to friday)\b")
CORRECTION = re.compile(r"[,;:(]?\s*\b(?:eikun|ei kun|ei vaan|korjaus|correction|sorry,? i mean|i mean|sorry|nej forlat|nej|rattelse|oikeastaan|siis)\b[:,]?\s*")
DENIAL = re.compile(r"[,;(]?\s*\b(?:ei|not|inte|ej)\s+((?:(?:klo|kello|kl|klockan|at|on|pa)\s*)?(?:\d{1,2}(?:[.:]\d{2})?\s?(?:am|pm)?(?![\d:])|puoli [a-z]+|[a-z]+))\)?")

LATER = re.compile(r"valmis|valmii|ready|klar|huolto|korjaamo|workshop|verkstad|odottaa osia|pesu kesken|waiting for parts|aikaisintaan|earliest|tidigast|alkaen|not before|ei ennen|inte fore"
                   r"|forran|framat|auton saa|saa hakea|haetta[a-z]*ssa|jalkeen|\bafter\b|\befter\b|\bvasta\b|maks|payment|pays|paid|betal|rahoitus|clears|luovutus|luovutetaan|released|lamnas ut|no pickup before|won't be|\bfrom\b|fran kl")
NO_MORE = re.compile(r"ei enaa|no more|inte langre|ei ketaan|nobody|ingen ")
DELIVERY = re.compile(r"perill|toimit|vastaanot|kohde|kohtee|destination|receiv|deliver|arriv|must be there|mottag|framme|pa plats|leverans|leverera|asiakas (?:noutaa|tulee)|customer picks|kunden hamtar")
DEADLINE = re.compile(r"viim|mennessa|oltava|pitaa olla|must|maste|\bby\b|latest|senast|kiire|silloin|by then|no later|dar da")
CLOSING = re.compile(r"kiinni|sulke|sulje|suljet|close|stang|asti|saakka|until|till kl|till klockan|\btill\b|ennen|before|fore\b|viimeistaan|no later|nobody|ei ketaan|ingen|jalkeen|after|efter")
SELLER = re.compile(r"myyja (?:paikalla|kotona)|seller (?:is )?(?:home|in|there)|saljaren (?:ar )?hemma|omistaja (?:paikalla|kotona)|owner (?:is )?home")


KNOWN = set(WORD_HOURS) | set(TODAY) | set(WEEKDAYS)


def plain(text: str) -> str:
    """Lower case, without accents: typos often drop them."""
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.replace("–", "-").replace("—", "-").replace("’", "'")).strip()


def one_edit(word: str) -> set[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    return ({a + b[1:] for a, b in splits if b} | {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}
            | {a + c + b[1:] for a, b in splits if b for c in letters} | {a + c + b for a, b in splits for c in letters})


def repair(text: str) -> str:
    """Replaces a word that dealers do not use by a word one typo away that they use often."""
    def fix(match: re.Match) -> str:
        word = match[0]
        if len(word) < 5 or word in KNOWN:
            return word
        # A typo is rare, and one edit away from a word that is at least 20 times as common.
        near = sorted(one_edit(word) & COMMON, key=lambda w: -COUNTS[w])
        if near and COUNTS[near[0]] >= max(25, 20 * COUNTS.get(word, 0)):
            return near[0]
        known = one_edit(word) & KNOWN if len(word) >= 7 and COUNTS.get(word, 0) < 3 else set()  # a day or an hour in words, misspelt
        return known.pop() if len(known) == 1 else word
    return re.sub(r"[a-z]+", fix, text) if COUNTS else text


# --- times ---

CLOCK = r"(\d{1,2})(?:[.:](\d{2}))?\s?(am|pm)?"
ITEM = re.compile(
    r"(?P<range>(?:(?:klo|kello|kl|klockan)\s*)?\b" + CLOCK + r"\s*(?:-|to|till)\s*" + CLOCK.replace("(", "(") + r"(?![\d.:]))"
    r"|(?P<half>\b(?:puoli|puolta|halv|half)(?: past)?\s+(?P<halfword>[a-z]+|\d{1,2}))"
    r"|(?P<clock>(?:\b(?:klo|kello|kl|klockan|at)\s*)\b(?P<h1>\d{1,2})(?:[.:](?P<m1>\d{2}))?\s?(?P<a1>am|pm)?(?![\d.:]))"
    r"|(?P<clock2>\b(?P<h2>\d{1,2})[.:](?P<m2>\d{2})\s?(?P<a2>am|pm)?(?![\d.:]))"
    r"|(?P<clock3>\b(?P<h3>\d{1,2})\s?(?P<a3>am|pm)\b)"
    r"|(?P<noon>\bnoon\b|\bkeskipaiva\w*|\bmidday\b)"
    r"|(?P<word>\b[a-z_]+\b)"
    r"|(?P<bare>\b\d{1,2}\b(?![\d.:]))")


def minute(hour: int, minutes: int = 0, half: str = "") -> Optional[int]:
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    return hour * HOUR + minutes if hour <= 24 and minutes < 60 else None


def worded(hour: int) -> int:
    """An hour in words is the working hour with that number, from 9 to 17: "two" is 14:00."""
    return (hour if hour >= 9 else hour + 12 if hour <= 5 else hour) * HOUR  # six to eight stay morning hours


@dataclass
class Time:
    day: Optional[int] = None  # days after the request arrived
    start: Optional[int] = None  # minute of the day
    end: Optional[int] = None  # for a range
    at: int = 0  # where the time stands in the sentence


def times(sentence: str, language: str, arrived_day: int) -> tuple[list[Time], bool]:
    """The times of a sentence, in order, and whether a number is left that could be a time."""
    found: list[Time] = []
    loose = False
    after_clock_word = False
    for match in ITEM.finditer(sentence):
        kind = match.lastgroup if match.lastgroup not in ("halfword", "h1", "m1", "a1", "h2", "m2", "a2", "h3", "a3") else None
        groups = match.groupdict()
        if groups["range"]:
            numbers = re.findall(CLOCK, groups["range"])
            (h1, m1, a1), (h2, m2, a2) = numbers[0], numbers[-1]
            start, end = minute(int(h1), int(m1 or 0), a1 or (a2 if a2 == "am" else "")), minute(int(h2), int(m2 or 0), a2)
            if start is not None and end is not None and end <= 8 * HOUR and not a2:  # "9-4": the afternoon
                end += 12 * HOUR
            if start is not None and end is not None and start < end:
                found.append(Time(None, start, end, match.start()))
            else:
                loose = True
        elif groups["half"]:
            word = groups["halfword"]
            hour = int(word) if word.isdigit() else WORD_HOURS.get(word)
            if hour is None:
                continue
            base = worded(hour) if not word.isdigit() else hour * HOUR
            english = match[0].startswith("half") and language == "en"
            found.append(Time(None, base - 30, None, match.start()))  # "half three" is half an hour before three, in every language of the rules
            del english
        elif groups["clock"] or groups["clock2"] or groups["clock3"]:
            hour = int(groups["h1"] or groups["h2"] or groups["h3"])
            value = minute(hour, int(groups["m1"] or groups["m2"] or 0), groups["a1"] or groups["a2"] or groups["a3"] or "")
            if value is None:
                loose = True
            else:
                found.append(Time(None, value, None, match.start()))
        elif groups["noon"]:
            found.append(Time(None, 12 * HOUR, None, match.start()))
        elif groups["word"]:
            word = groups["word"]
            if word in TODAY:
                found.append(Time(TODAY[word], None, None, match.start()))
            elif word in WEEKDAYS and (word not in ALL_SHORT or word in SHORT_DAYS.get(language, ())):
                ahead = (WEEKDAYS[word] - arrived_day) % 7  # a weekday name means that weekday 2 to 6 days after the request arrives
                found.append(Time(ahead if ahead >= 2 else ahead + 7, None, None, match.start()))
            elif word in FI_HOURS or (after_clock_word and word in WORD_HOURS) or (word in SV_HOURS and language == "sv" and after_clock_word) \
                    or (word in EN_HOURS and language == "en" and after_clock_word):
                found.append(Time(None, worded(WORD_HOURS[word]), None, match.start()))
            after_clock_word = word in ("klo", "kello", "kl", "klockan", "at", "by", "from", "before", "after", "until", "till", "vid", "fore", "efter", "senast", "tidigast",
                                        "ennen", "aikaisintaan", "viimeistaan", "viim", "jalkeen")
            continue
        elif groups["bare"]:
            hour = int(groups["bare"])
            rest = sentence[match.end():match.end() + 12]
            if found and found[-1].start is None and found[-1].day is not None and sentence[found[-1].at:match.start()].count(" ") <= 1 and hour <= 24:
                found.append(Time(None, hour * HOUR, None, match.start()))  # "huomenna 12 mennessä"
            elif re.match(r"\s*(?:mennessa|asti|saakka|alkaen|jalkeen|latest|senast)", rest) and hour <= 24:
                found.append(Time(None, hour * HOUR, None, match.start()))
            elif after_clock_word and hour <= 24:
                found.append(Time(None, hour * HOUR, None, match.start()))
            else:
                loose = True
        after_clock_word = False
    # A day and the clock time next to it are one time.
    merged: list[Time] = []
    for time in found:
        last = merged[-1] if merged else None
        if last and last.day is not None and last.start is None and time.day is None and len(sentence[last.at:time.at].split()) <= 3:
            last.start, last.end = time.start, time.end
        elif last and last.day is None and time.day is not None and time.start is None and last.end is None and len(sentence[last.at:time.at].split()) <= 3 \
                and not (len(merged) > 1 and merged[-2].day is not None and merged[-2].start is None):
            last.day = time.day  # "klo 14 huomenna"
        else:
            merged.append(time)
    return merged, loose


# --- reading ---

def read(note: Optional[dict], arrived_at: int = 0) -> Facts:
    facts = Facts()
    if not note:
        return facts
    language = note.get("language") or "fi"
    text = repair(plain(note["text"]))
    facts.manual = bool(MANUAL.search(text)) and not NOT_MANUAL.search(text)
    facts.plates = bool(PLATES.search(text)) and not re.search(r"kilvet (?:on |ovat )?(?:paikallaan|kiinni|mukana)|plates (?:are )?on\b|has plates|skyltar(?:na)? (?:sitter|finns)", text)
    facts.summer_tyres = bool(ON_SUMMER_TYRES.search(text))
    text = COUNT.sub(" ", REFERENCE.sub(" ", text))
    text = re.sub(r"\b(\d{1,2}):sta\s+(\d{1,2}):[a-z]+", r"\1-\2", text)  # "10:stä 16:een": from 10 to 16
    text = re.sub(r"\b(\d{1,2}):[a-z]+", r"klo \1", text)  # "19:ään saakka"
    text = re.sub(r"\b(klo|kello|kl|klockan)\s*([012]\d)([0-5]\d)\b", r"\1 \2.\3", text)  # "klo 1500"
    text = ABBREVIATION.sub(lambda m: m[1], text)
    text = text.replace("i morgon", "imorgon").replace("i dag", "idag").replace("i overmorgon", "overmorgon").replace("day after tomorrow", "ylihuomenna").replace("pa mandag", "mandag")
    text = WEEK_RANGE.sub(" ", text)
    arrived_day = arrived_at // DAY
    last: Optional[tuple[str, Time]] = None  # the last fact with a time: a correction changes it
    for sentence in re.split(r"[.!?]+(?:\s+|$)|\s+/\s+|;\s*", text):
        if not sentence.strip():
            continue
        parts = CORRECTION.split(sentence)
        for index, part in enumerate(parts):
            for denied in reversed(list(DENIAL.finditer(part))):  # a denied time does not count
                if times(denied[1], language, arrived_day % 7)[0]:
                    part = part[:denied.start()] + " " + part[denied.end():]
            found, loose = times(part, language, arrived_day % 7)
            if index > 0 or (last and found and not re.search(r"[a-z]{4,}", re.sub(r"\b(?:klo|kello|klockan)\b", "", ITEM.sub(lambda m: "" if m.lastgroup != "word" or m[0] in TODAY or m[0] in WEEKDAYS or m[0] in WORD_HOURS else m[0], part)))):
                # A correction, or a sentence of a time alone: it changes the time before it.
                if last and found:
                    role, time = last
                    fix = found[0]
                    if fix.day is not None:
                        time.day = fix.day
                    if fix.start is not None:
                        time.start, time.end = fix.start, fix.end if fix.end is not None else time.end
                    apply(facts, role, time, arrived_day)
                elif found or loose:
                    facts.unsure = True
                continue
            if loose:
                facts.unsure = True
            if not found:
                continue
            # The words of the clause that holds the time say what it means; when they say nothing, the whole sentence does.
            is_range = found[0].end is not None or (len(found) > 1 and found[1].end is not None)
            clause = next((c for c in re.split(r",\s*", part) if times(c, language, arrived_day % 7)[0]), part)
            role = role_of(clause, is_range) or role_of(part, is_range)
            if role is None:
                facts.unsure = True
                continue
            if role == "skip":
                continue
            time = found[0] if role != "deliver_by" or len(found) == 1 else max(found, key=lambda t: (t.day is not None, t.start is not None))
            if len(found) > 1 and role in ("pickup_hours", "delivery_hours") and found[0].end is None and found[1].end is not None:
                time = found[1]
            apply(facts, role, time, arrived_day)
            last = (role, time)
    return facts


def role_of(sentence: str, is_range: bool) -> Optional[str]:
    """What the time of a sentence means, from the words around it. A range is opening hours."""
    if SELLER.search(sentence):
        return "skip"  # the seller's hours at a private address: the request's booked slot says the same
    delivery, deadline, later = DELIVERY.search(sentence), DEADLINE.search(sentence), LATER.search(sentence)
    closing = CLOSING.search(sentence) or NO_MORE.search(sentence)
    if is_range:
        return "delivery_hours" if delivery else "pickup_hours"
    if NO_MORE.search(sentence):  # "20 jälkeen ei enää luovutuksia", "nobody here after 20:00"
        return "delivery_hours" if delivery else "pickup_hours"
    if delivery:
        hours = re.search(r"auki|open|oppet|kiinni|sulke|close|stang|asti|saakka|until|only|vain|\btill\b|paikalla", sentence)
        return "delivery_hours" if hours and not deadline else "deliver_by"
    if later and not re.search(r"(?<!ei )ennen klo|haettava|collect before|(?<!no )pick ?up before|hamtas fore|sulke|kiinni|close", sentence):
        return "ready_at"
    if closing or re.search(r"auki|open|oppet|aukiolo|opening|nouto|noud|haettav|haku|hakea|pick|collect|hamt|liike|shop|butik|taalla|here|\bwe\b|\bvi\b|ollaan", sentence):
        return "pickup_hours"
    return "ready_at" if later else None


def apply(facts: Facts, role: str, time: Time, arrived_day: int) -> None:
    day = arrived_day + (time.day or 0)  # a time without a day is on the day the request arrives
    if role == "ready_at":
        if time.start is None and time.day is None:
            return
        facts.ready_at = day * DAY + (time.start if time.start is not None else 0)
    elif role == "deliver_by":
        if time.start is None and time.day is None:
            return
        facts.deliver_by = day * DAY + (time.start if time.start is not None else 20 * HOUR)
    elif role == "pickup_hours":
        if time.end is not None:
            facts.pickup_opens, facts.pickup_closes = time.start, time.end
        elif time.start is not None:
            facts.pickup_closes = time.start
    elif role == "delivery_hours":
        if time.end is not None:
            facts.delivery_opens, facts.delivery_closes = time.start, time.end
        elif time.start is not None:
            facts.delivery_closes = time.start
