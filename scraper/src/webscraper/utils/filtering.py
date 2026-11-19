"""Shared title exclusions applied before detail requests.

The rule lists live in ``job_rules`` so the app's Settings page can edit them; this module only
holds the pattern that is active for the current scrape.
"""

from job_rules import EXCLUDED_SENIORITY, EXCLUDED_TITLES, title_exclusion_regex

DEFAULT_TITLE_PATTERN = title_exclusion_regex()
EXCLUDED_TITLE_PATTERN = DEFAULT_TITLE_PATTERN
_active = DEFAULT_TITLE_PATTERN


def configure(rules=None):
    """Select the title exclusions used by adapters and the pipeline; ``None`` restores defaults."""
    global _active
    _active = title_exclusion_regex(rules) if rules is not None else DEFAULT_TITLE_PATTERN
    return _active


def active_pattern():
    return _active


def title_allowed(title):
    return _active is None or not _active.search(title or "")
