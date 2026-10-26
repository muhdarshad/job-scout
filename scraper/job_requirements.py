"""Conservative DE/EN requirement extraction; no network calls or inferred CEFR levels."""

import math
import re
import unicodedata
from html import unescape


def _norm(text):
    return unicodedata.normalize("NFKC", text).casefold().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def _parts(value):
    if value is None or isinstance(value, float) and math.isnan(value):
        return []
    text = unescape(str(value))
    text = re.sub(r"</?(?:p|div|li|br|h[1-6]|ul|ol)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]*>", " ", text)
    return [p.strip() for p in re.split(r"[\n;•]+|(?<=[.!?])\s+", text) if p.strip()]


OPTIONAL = r"\b(?:idealerweise|wuenschenswert\w*|vorteilhaft\w*|von vorteil|von vorteil waer\w*|optional|desirable|desired|preferred|preferably|ideally|an? advantage|an? asset|a plus|nice[- ]to[- ]have)\b"
REQUIRED = r"\b(?:required|mandatory|essential|must|minimum|at least|mindestens|erforderlich\w*|zwingend\w*|voraussetzung\w*|setzen.{0,15}voraus)\b"
EXP = r"(?:(?:einschlaegig\w*|relevant\w*|praktisch\w*|beruflich\w*)\s+)?(?:berufs\w*erfahrung|berufserfahrung\w*|praxiserfahrung\w*|erfahrung\w*|(?:professional |relevant |work |working |practical )?experience)"
NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "ein": 1, "eine": 1, "einem": 1, "einen": 1, "eines": 1, "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10}
NUMBER = r"(?:\d{1,2}|" + "|".join(NUMBERS) + r")"
YEARS = re.compile(r"\b(?P<low>" + NUMBER + r")(?:\s*(?:[-–—]|bis|to)\s*(?P<high>" + NUMBER + r"))?\s*(?:\+|or more|oder mehr)?\s*(?:years?|jahre\w*|jaehrig\w*)\b")
LANG = re.compile(r"\b(?:deutsch(?:kenntnis\w*|sprach\w*|en|er|es|e)?|german)\b")
OTHER_LANG = r"\b(?:englisch\w*|english|french|franzoesisch\w*|spanish|spanisch\w*)\b"
LEVELS = [
    ("native", r"\b(?:muttersprach\w*|native(?:[- ]level)?|mother tongue)\b"),
    ("business fluent", r"\b(?:verhandlungssicher\w*|business[- ]fluent)\b"),
    ("fluent", r"\b(?:fliessend\w*|fluent\w*)\b"),
    ("very good", r"\b(?:sehr gut\w*|very good|excellent\w*|ausgezeichnet\w*|hervorragend\w*)\b"),
    ("good", r"\b(?:gut\w*|good)\b"),
    ("proficient", r"\b(?:sicher\w*|proficien\w*|advanced|fortgeschritten\w*)\b"),
    ("conversational", r"\b(?:konversationssicher\w*|conversational)\b"),
    ("basic", r"\b(?:grundkenntnisse\w*|basiskenntnisse\w*|basic|elementar\w*)\b"),
]
CEFR = r"\b[abc][12]\b"
ENTRY = r"\b(?:berufseinsteiger\w*|quereinsteiger\w*|entry[- ]level|graduates? welcome)\b"


def _status(text, negative):
    if re.search(negative, text):
        return "not required"
    optional, required = bool(re.search(OPTIONAL, text)), bool(re.search(REQUIRED, text))
    return "mixed / review" if optional and required else "preferred" if optional else "required" if required else "stated"


def _join(values):
    return " | ".join(dict.fromkeys(str(v) for v in values)) or "not stated"


def extract_requirements(description):
    """Keep all matched clauses; missing evidence stays unknown rather than zero."""
    experience, german = [], []
    for evidence in _parts(description):
        text = _norm(evidence)
        if re.search(EXP + "|" + ENTRY, text):
            status = _status(text, r"\b(?:no (?:prior |previous |professional |work )?experience (?:is )?(?:required|necessary|needed)|keine.{0,30}erfahrung.{0,20}(?:erforderlich|notwendig|vorausgesetzt))\b")
            # A year count needs an adjacent experience expression, not a company anniversary.
            years = [m for m in YEARS.finditer(text) if re.search(r"^['’]?\s*(?:of\s+)?" + EXP, text[m.end():])
                     or re.search(EXP + r"\s*(?:von|of|:|mit)?\s*(?:mindestens|at least|minimum)?\s*$", text[:m.start()])]
            labels = [m.group() for m in years]
            if re.search(ENTRY, text):
                labels.append("entry / career change mentioned")
            if not labels:
                for label, pattern in [("long-standing", r"langjaehrig\w*"), ("several years", r"mehrjaehrig\w*|mehrere\w* jahre\w*|several years|multiple years"),
                                       ("initial experience", r"erste\w*|initial|first"), ("substantial / solid experience", r"umfangreich\w*|fundiert\w*|extensive|substantial|proven|solid")]:
                    if re.search(pattern + r".{0,40}" + EXP, text):
                        labels.append(label)
            minimum = [int(m['low']) if m['low'].isdigit() else NUMBERS[m['low']] for m in years]
            experience.append((_join(labels) if labels else "experience mentioned", status, evidence, minimum))
        for match in LANG.finditer(text):
            # Bound scope by other named languages so English fluency is not assigned to German.
            left, right = text[:match.start()], text[match.end():]
            left = re.split(OTHER_LANG + r"|[,;]", left)[-1][-70:]
            right = re.split(OTHER_LANG + r"|[,;]", right)[0][:90]
            local = left + match.group() + right
            status = _status(local, r"\b(?:no german.{0,30}(?:required|necessary|needed)|german.{0,30}not (?:required|necessary|needed)|deutsch\w*.{0,30}nicht (?:erforderlich|notwendig)|keine deutsch\w*.{0,25}(?:erforderlich|notwendig))\b")
            levels = [m.group().upper() for m in re.finditer(CEFR, local)]
            if not levels:
                levels = [label for label, pattern in LEVELS if re.search(pattern, local)][:1]
            if not levels and not re.search(r"kenntnis|sprach|language|skills?|speak|speaking|written|oral|command|communicat|wort|schrift|beherrsch|sprich|required|necessary|needed|erforderlich|notwendig|" + OPTIONAL, local):
                continue
            german.append((_join(levels) if levels else "unspecified", status, evidence))
    # Optional, negated and conflicting clauses do not contribute a lower bound.
    minima = [n for _, status, _, numbers in experience if status in {"required", "stated"} for n in numbers]
    return {
        "experience_required": _join(x[0] for x in experience),
        "experience_min_years": max(minima) if minima else None,
        "experience_requirement": _join(x[1] for x in experience),
        "experience_evidence": _join(x[2] for x in experience) if experience else "",
        "german_required": _join(x[0] for x in german),
        "german_requirement": _join(x[1] for x in german),
        "german_evidence": _join(x[2] for x in german) if german else "",
    }

