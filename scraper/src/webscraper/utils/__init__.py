"""Utility functions for the web scraper."""

import re
from html import unescape
from typing import Any, Optional


def strip_html(raw_html: Optional[str]) -> Optional[str]:
    """Strip HTML tags from text."""
    if not raw_html:
        return raw_html
    text = re.sub(r"<[^>]+>", " ", raw_html)
    return unescape(re.sub(r"\s+", " ", text).strip())


def first_item(lst: Any, key: Optional[str] = None) -> Any:
    """Get first item from a list of dicts, optionally extracting a key."""
    if not lst:
        return None
    if not isinstance(lst, list):
        return lst
    first = lst[0]
    if key is None:
        return first
    return first.get(key) if isinstance(first, dict) else None

