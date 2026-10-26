"""Shared title exclusions applied before detail requests."""

import re

EXCLUDED_TITLES = [
    r"electrical engineer", r"elektrotechniker", r"elektroingenieur", r"mechatroniker",
    r"mechatronic", r"electronics engineer", r"elektronik", r"software developer",
    r"software engineer", r"softwareentwickler", r"it technician", r"it support specialist",
    r"desktop support engineer", r"infrastructure technician", r"bauingenieur", r"electrician",
]

EXCLUDED_SENIORITY = [
    r"werkstudent", r"working student", r"v\.i\.e", r"\bvie program\b", r"\bvie\b",
    r"intern(?!ational)", r"internship", r"masterarbeit", r"master thesis", r"masterand",
    r"bachelor'?s thesis", r"praktikant", r"praktikum", r"\bsenior\b", r"\bsr\.\b",
    r"\blead\b", r"\bprincipal\b", r"head of", r"\bdirector\b", r"post.?doctoral",
    r"premaster", r"abschlussarbeit",
]

EXCLUDED_TITLE_PATTERN = re.compile("|".join(EXCLUDED_TITLES + EXCLUDED_SENIORITY), re.IGNORECASE)



def title_allowed(title):
    return not EXCLUDED_TITLE_PATTERN.search(title or "")

