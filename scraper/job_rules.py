"""Shared title matching for ranking, discovery and collection."""
import re
import unicodedata
from functools import lru_cache

NOT_INTERESTED_PATTERNS = [
    r"technician", r"techniker", r"prüfstandtechniker", r"inbetriebnahmetechniker",
    r"verkäufer", r"sales[\s-]+assistant", r"postdoc", r"post[\s-]+doc", r"postdoctoral", r"postdoktorand",
    r"ausbildung", r"duales[\s-]+studium", r"neuroscience", r"neurology", r"neuroimaging", r"neuropeptide",
    r"bioinformatics", r"immunity", r"clinical[\s-]+science", r"civil", r"bauingenieur", r"geotechnik", r"tragwerksplanung",
    r"uae[\s-]+nationals?", r"emiratis", r"professor", r"backend", r"full[\s-]+stack",
    r"react[\s-]+native", r"web[\s-]+development", r"marketing", r"business[\s-]+development",
]
INTERESTED_PATTERNS = [
    r"digitalisierung", r"reporting", r"aerospace", r"quality[\s-]+manager", r"data[\s-]+scientist",
    r"business[\s-]+intelligence", r"bi", r"data[\s-]+analyst", r"datenanalyst", r"analytics",
    r"quality", r"qualitäts\w*", r"mechanical", r"graduate",
]
NOT_INTERESTED_REGEX = re.compile(r"\b(?:" + "|".join(NOT_INTERESTED_PATTERNS) + r")\b", re.IGNORECASE)
INTERESTED_REGEX = re.compile(r"\b(?:" + "|".join(INTERESTED_PATTERNS) + r")\b", re.IGNORECASE)

DEFAULT_EXCLUDED_KEYWORDS = [
    "postbote", "postbotin", "briefzusteller", "paketzusteller", "sortierer", "briefsortierer", "paketsortierer",
    "lagerhelfer", "lagerarbeiter", "lagermitarbeiter", "kommissionierer",
    "staplerfahrer", "auslieferungsfahrer", "reinigungskraft", "kassierer",
    "reinigungskräfte", "küchenhilfe", "mail carrier", "delivery driver", "parcel sorter",
    "warehouse operative", "warehouse picker", "forklift driver", "cleaner", "cashier",
]

def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        value = value.replace(source, target)
    return re.sub(r"[\s‐‑–—-]+", " ", value).strip()

@lru_cache(maxsize=512)
def keyword_pattern(keyword):
    # Literal terms, whole words and ordinary gender/plural endings; no user regex.
    return re.compile(r"(?<!\w)" + re.escape(normalize(keyword)) + r"(?:in|innen|n|en|s)?(?!\w)")

def excluded_keyword(title, keywords):
    normalized = normalize(title)
    return next((word for word in keywords if word.strip() and keyword_pattern(word).search(normalized)), "")

def likely_interested(title, keywords=()):
    return bool(INTERESTED_REGEX.search(title or "")) and not (
        NOT_INTERESTED_REGEX.search(title or "") or excluded_keyword(title, keywords))
