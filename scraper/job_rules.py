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

# Hard exclusions applied to scraped titles (kept as regular expressions, matched case-insensitively).
EXCLUDED_TITLES = [
    r"electrical engineer", r"elektrotechniker", r"elektroingenieur", r"mechatroniker",
    r"mechatronic", r"electronics engineer", r"elektronik", r"software developer",
    r"software engineer", r"softwareentwickler", r"it technician", r"it support specialist",
    r"desktop support engineer", r"infrastructure technician", r"bauingenieur", r"electrician",
]
# Seniority / student-level exclusions, matched against the title (and job level in the ranker).
EXCLUDED_SENIORITY = [
    r"werkstudent", r"working student", r"v\.i\.e", r"\bvie program\b", r"\bvie\b",
    r"intern(?!ational)", r"internship", r"masterarbeit", r"master thesis", r"masterand",
    r"bachelor'?s thesis", r"praktikant", r"praktikum", r"\bsenior\b", r"\bsr\.\b",
    r"\blead\b", r"\bprincipal\b", r"head of", r"\bdirector\b", r"post.?doctoral",
    r"premaster", r"abschlussarbeit",
]
# Jobs whose description matches any of these are dropped by the ranker.
EXCLUDED_REQUIREMENTS = [
    r"eu nationality", r"eu citizenship", r"european union nationality", r"eu-staatsbürgerschaft",
    r"eu passport required", r"five or more years of professional experience", r"sehr gute deutsch",
    r"5\+ years of experience", r"german language\s*[-:]\s*fluent", r"minimum 5 years of experience",
    r"more than five years", r"five years of professional experience", r"deutsch mindestens c1", r"nato or eu security clearance",
    r"Deutsch auf Muttersprachlerniveau",
]

RULE_LISTS = {
    'excluded_titles': EXCLUDED_TITLES,
    'excluded_seniority': EXCLUDED_SENIORITY,
    'not_interested_titles': NOT_INTERESTED_PATTERNS,
    'interested_titles': INTERESTED_PATTERNS,
    'excluded_requirements': EXCLUDED_REQUIREMENTS,
}

def default_rules():
    """Fresh copy of every built-in rule; `full_time_only` keeps the ranker's job-type filter."""
    return {**{name: list(values) for name, values in RULE_LISTS.items()}, 'full_time_only': True}

def resolve_rules(stored=None):
    """Defaults overlaid with any customised lists; unknown keys and wrong types are ignored."""
    rules = default_rules()
    for name, value in (stored or {}).items():
        if name == 'full_time_only' and isinstance(value, bool):
            rules[name] = value
        elif name in RULE_LISTS and isinstance(value, list) and all(isinstance(item, str) for item in value):
            rules[name] = list(value)
    return rules

@lru_cache(maxsize=64)
def alternation(patterns, whole_word):
    if not patterns:
        return None
    body = "|".join(f"(?:{pattern})" for pattern in patterns)
    return re.compile((r"\b(?:" + body + r")\b") if whole_word else body, re.IGNORECASE)

def title_regex(rules, name):
    """Compiled regex for one list, or None when the list is empty (an empty list excludes nothing)."""
    rules = rules or default_rules()
    return alternation(tuple(rules[name]), name in ('not_interested_titles', 'interested_titles'))

def title_exclusion_regex(rules=None):
    rules = rules or default_rules()
    return alternation(tuple(rules['excluded_titles']) + tuple(rules['excluded_seniority']), False)

NOT_INTERESTED_REGEX = title_regex(None, 'not_interested_titles')
INTERESTED_REGEX = title_regex(None, 'interested_titles')

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

def likely_interested(title, keywords=(), rules=None):
    interested, not_interested = title_regex(rules, 'interested_titles'), title_regex(rules, 'not_interested_titles')
    return bool(interested and interested.search(title or "")) and not (
        (not_interested and not_interested.search(title or "")) or excluded_keyword(title, keywords))
