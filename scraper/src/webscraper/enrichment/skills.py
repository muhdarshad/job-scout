"""Skills extraction from job descriptions."""

import pandas as pd

from ..config import SKILL_KEYWORDS


def extract_skills(description: str | None, keywords: list[str] = None) -> str | None:
    """Extract known skill keywords from job description."""
    if pd.isna(description) or not description:
        return None
    if keywords is None:
        keywords = SKILL_KEYWORDS
    found = [kw for kw in keywords if kw.lower() in description.lower()]
    return ", ".join(found) if found else None


def add_skills_column(df: pd.DataFrame, keywords: list[str] = None) -> pd.DataFrame:
    """Add skills column to DataFrame by extracting from descriptions."""
    df["skills"] = df["description"].apply(lambda x: extract_skills(x, keywords))
    return df

