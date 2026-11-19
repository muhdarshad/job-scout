#!/usr/bin/env python
"""Filter, score, and export scraped jobs as a ranked Excel workbook."""

import argparse
import glob
import os
import re
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from job_requirements import extract_requirements


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "job_results"
MIN_SKILL_DENOMINATOR = 3


def word_pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-zA-Z0-9])" + re.escape(term) + r"(?![a-zA-Z0-9])", re.IGNORECASE)


SKILL_PATTERNS = {
    "Aerospace Engineering": [word_pattern("aerospace"), word_pattern("aeronautical")],
    "Numerical Modelling": [word_pattern("numerical modelling"), word_pattern("numerical modeling"), word_pattern("numerical simulation")],
    "English": [word_pattern("english")],
    "Power BI": [word_pattern("power bi"), word_pattern("powerbi")],
    "DAX": [word_pattern("dax")],
    "Power Query": [word_pattern("power query")],
    "Azure Databricks": [word_pattern("azure databricks"), word_pattern("databricks")],
    "SQL": [word_pattern("sql")],
    "Python": [word_pattern("python")],
    "Grafana": [word_pattern("grafana")],
    "ETL": [word_pattern("etl")],
    "Excel": [word_pattern("excel")],
    "VBA": [word_pattern("vba")],
    "GitHub": [word_pattern("github")],
    "GitLab": [word_pattern("gitlab")],
    "Machine Learning": [word_pattern("machine learning")],
    "OPC UA": [word_pattern("opc ua"), word_pattern("opc-ua")],
    "Industry 4.0": [word_pattern("industry 4.0"), word_pattern("industrie 4.0")],
    "Quality Inspection": [word_pattern("quality inspection"), word_pattern("quality control"), word_pattern("quality assurance")],
    "Measurement Techniques": [word_pattern("measurement"), word_pattern("messtechnik")],
    "Siemens NX": [word_pattern("siemens nx"), word_pattern("nx cad")],
    "Star CCM+": [word_pattern("star ccm"), word_pattern("starccm"), word_pattern("star-ccm")],
    "GD&T": [word_pattern("gd&t"), word_pattern("geometric dimensioning"), word_pattern("gdt")],
    "Engineering Drawings": [word_pattern("engineering drawings"), word_pattern("technical drawings"), word_pattern("zeichnungen")],
    "Microsoft Office": [word_pattern("microsoft office"), word_pattern("ms office"), word_pattern("office 365")],
    "SharePoint": [word_pattern("sharepoint")],
    "MATLAB": [word_pattern("matlab")],
    "Quality" : [word_pattern("fmea"), word_pattern("six sigma"), word_pattern("8d")],
    "German" : [word_pattern("german"), word_pattern("deutsch")]
}


# ---------- APPROVED TITLE KEYWORDS ----------
from job_rules import NOT_INTERESTED_PATTERNS, INTERESTED_PATTERNS, NOT_INTERESTED_REGEX, INTERESTED_REGEX, alternation, default_rules, title_regex

def _series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].fillna("").astype(str) if column in df else pd.Series("", index=df.index, dtype=str)


def _freshness_series(df: pd.DataFrame) -> pd.Series:
    exact = pd.to_datetime(_series(df, "posted_at").replace("", pd.NA), errors="coerce", utc=True)
    dates = pd.to_datetime(_series(df, "date_posted").replace("", pd.NA), errors="coerce", utc=True)
    return exact.fillna(dates)


def load_and_filter(input_csv: str | os.PathLike, rules=None) -> pd.DataFrame:
    rules = rules or default_rules()
    df = pd.read_csv(input_csv)
    missing = {"title", "company"} - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {', '.join(sorted(missing))}")

    # Approved title exclusions take precedence over interest matches.
    not_interested = title_regex(rules, "not_interested_titles")
    if not_interested:
        df = df[~_series(df, "title").str.contains(not_interested)].copy()

    if rules["full_time_only"]:
        job_type = _series(df, "job_type").str.lower().str.replace(r"[^a-z]", "", regex=True)
        df = df[(job_type == "") | job_type.str.contains("fulltime")]

    def drop_matching(frame, text, patterns):
        regex = alternation(tuple(patterns), False)
        return frame if regex is None else frame[~text(frame).str.contains(regex)]

    df = drop_matching(df, lambda frame: _series(frame, "title"), rules["excluded_titles"])
    df = drop_matching(df, lambda frame: _series(frame, "title") + " " + _series(frame, "job_level"), rules["excluded_seniority"])
    df = drop_matching(df, lambda frame: _series(frame, "description"), rules["excluded_requirements"])
    keys = _series(df, "title").str.strip().str.casefold() + "|" + _series(df, "company").str.strip().str.casefold()
    return df.loc[~keys.duplicated()].reset_index(drop=True)


def combined_text(row: pd.Series) -> str:
    columns = ["title", "description", "company_industry", "search_term", "skills"]
    return " ".join("" if pd.isna(row.get(column)) else str(row.get(column, "")) for column in columns)


def find_skills(text: str) -> set[str]:
    return {skill for skill, patterns in SKILL_PATTERNS.items() if any(pattern.search(text) for pattern in patterns)}


def seniority_multiplier(row: pd.Series) -> float:
    text = f"{row.get('job_level', '')} {row.get('title', '')}".lower()
    if any(term in text for term in ["senior", "lead", "principal", "head of", "director", "5+", "expert"]):
        return 0.2
    if "mid-senior" in text or re.search(r"\b3\s*[-–]\s*5\b", text):
        return 0.6
    if "associate" in text or re.search(r"\b2\s*[-–]\s*4\b", text):
        return 0.9
    return 1.0


def language_score(text: str) -> int:
    text = text.lower()
    if re.search(r"fluent german|native german|fließend deutsch|deutsch.{0,3}muttersprache|verhandlungssicher.{0,25}deutsch", text):
        return 0
    if re.search(r"basic german|grundkenntnisse.{0,10}deutsch|deutsch.{0,10}(a1|a2|b1|b2)|conversational german|german.{0,15}(nice to have|of advantage|a plus)", text):
        return 10
    if re.search(r"fluent english|business.?fluent english|english.{0,15}(fluent|proficient|required)", text) and "german" not in text:
        return 10
    return 10 if "german" not in text and "deutsch" not in text else 7


def industry_score(row: pd.Series) -> int:
    text = f"{row.get('company_industry', '')} {row['full_text'][:2000]}".lower()
    scores = {
        "aerospace": 10, "aviation": 10, "defense and space": 10, "aerospace & defense": 10,
        "automotive": 9, "motor vehicle": 9, "research": 8, "biotechnology research": 8,
        "mechanical": 7, "machinery manufacturing": 7, "industrial machinery": 7,
        "engineering services": 7, "energy": 6, "renewable energy": 6, "utilities": 6, "oil and gas": 6,
    }
    return max((score for term, score in scores.items() if term in text), default=4)


def location_score(location) -> int:
    text = "" if pd.isna(location) else str(location).lower()
    if not text:
        return 4
    bavaria = ["bavaria", "bayern", "münchen", "munich", "erlangen", "nürnberg", "nuremberg", "augsburg", "ingolstadt", "ottobrunn", "manching", "regensburg", "würzburg"]
    west_south = ["nrw", "north rhine", "hesse", "hessen", "baden-württemberg", "baden-wurttemberg", "köln", "cologne", "düsseldorf", "dusseldorf", "frankfurt", "stuttgart", "wiesbaden", "darmstadt", "mannheim", "karlsruhe", "essen", "dortmund", "bonn"]
    major = ["berlin", "hamburg", "bremen", "dresden", "leipzig", "hannover"]
    if any(term in text for term in bavaria):
        return 10
    if any(term in text for term in west_south):
        return 8
    if any(term in text for term in major):
        return 6
    return 4 if "germany" in text or re.search(r",\s*de$", text) else 0


def contract_score(row: pd.Series) -> int:
    text = row["full_text"].lower()
    job_type = str(row.get("job_type", "")).lower()
    if ("befristet" in text and "unbefristet" not in text) or re.search(r"\blimited contract\b|\bfixed[- ]term\b|\btemporary contract\b", text):
        return 5
    return 0 if "part time" in job_type and "full time" not in job_type else 10


def previous_job_keys(output_dir: Path) -> set[tuple[str, str]]:
    files = glob.glob(str(output_dir / "[0-9][0-9]_*_rankedjobs_germany.xlsx"))
    if not files:
        return set()
    try:
        previous = pd.read_excel(max(files, key=os.path.getmtime), usecols=["Title", "Company"])
    except (OSError, ValueError) as error:
        print(f"Warning: could not read previous ranked output: {error}")
        return set()
    return {(str(row.Title).strip().lower(), str(row.Company).strip().lower()) for row in previous.itertuples()}


def rank_dataframe(input_csv: str | os.PathLike, output_dir: str | os.PathLike = DEFAULT_OUTPUT_DIR, skill_keywords=None, rules=None) -> pd.DataFrame:
    df = load_and_filter(input_csv, rules)
    previous = previous_job_keys(Path(output_dir))
    if previous:
        before = len(df)
        keys = df.apply(lambda row: (str(row["title"]).strip().lower(), str(row["company"]).strip().lower()), axis=1)
        df = df[~keys.isin(previous)].copy()
        print(f"Removed {before - len(df)} jobs found in the previous ranked output.")
    if df.empty:
        return df

    requirements = pd.DataFrame(_series(df, "description").map(extract_requirements).tolist(), index=df.index)
    for column in requirements:
        df[column] = requirements[column]
    df["full_text"] = df.apply(combined_text, axis=1)
    patterns = SKILL_PATTERNS if skill_keywords is None else {skill:SKILL_PATTERNS.get(skill, [word_pattern(skill)]) for skill in skill_keywords}
    df["matched_skills"] = df["full_text"].apply(lambda text: {skill for skill, rules in patterns.items() if any(rule.search(text) for rule in rules)})
    df["skill_score"] = df.apply(lambda row: min(len(row["matched_skills"]) / MIN_SKILL_DENOMINATOR, 1) * 40 * seniority_multiplier(row), axis=1)
    df["language_score"] = df["full_text"].apply(language_score)
    df["industry_score"] = df.apply(industry_score, axis=1)
    df["location_score"] = _series(df, "location").apply(location_score)
    df["contract_score"] = df.apply(contract_score, axis=1)
    df["total_score"] = df[["skill_score", "language_score", "industry_score", "location_score", "contract_score"]].sum(axis=1)
    df["_freshness"] = _freshness_series(df)
    df = df.sort_values(["total_score", "_freshness"], ascending=[False, False], kind="stable", na_position="last").reset_index(drop=True)
    df.drop(columns="_freshness", inplace=True)
    df["source"] = _series(df, "source").replace("", "CS")
    df["serial"] = df["source"] + "_" + (df.groupby("source").cumcount() + 1).astype(str).str.zfill(2)
    return df


def next_output_path(output_dir: str | os.PathLike) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%y%m%d")
    numbers = [int(path.name.split("_", 1)[0]) for path in output_dir.glob(f"[0-9][0-9]_{today}_rankedjobs_germany.xlsx")]
    return output_dir / f"{max(numbers, default=0) + 1:02d}_{today}_rankedjobs_germany.xlsx"


def export_excel(df: pd.DataFrame, output_path: str | os.PathLike) -> None:
    output = pd.DataFrame({
        "Rank": range(1, len(df) + 1), "Title": _series(df, "title"), "Company": _series(df, "company"),
        "Location": _series(df, "location"), "Date Posted": _series(df, "date_posted"), "Posted At": _series(df, "posted_at"),
        "Job Type": _series(df, "job_type"), "Job Level": _series(df, "job_level"),
        "Industry": _series(df, "company_industry"), "Matched Skills": df["matched_skills"].apply(lambda skills: ", ".join(sorted(skills))),
        "Skill Fit (0-40)": df["skill_score"].round(1), "Language (0-10)": df["language_score"],
        "Industry Match (0-10)": df["industry_score"], "Location (0-10)": df["location_score"],
        "Contract (0-10)": df["contract_score"], "Total Score (0-80)": df["total_score"].round(1),
        "Job URL": _series(df, "job_url"),
        "Link": [f'=HYPERLINK(Q{row},"Link")' if url.strip() else ""
                 for row, url in enumerate(_series(df, "job_url"), start=2)],
        "status": _series(df, "title").apply(lambda title: "likely interested" if INTERESTED_REGEX.search(title) else ""),
        "Job Description": _series(df, "description"),
        "Serial": _series(df, "serial"), "Source": _series(df, "source"), "Website": _series(df, "source_site"),
        "Experience Required": _series(df, "experience_required"),
        "Experience Min Years": df.get("experience_min_years", pd.Series(index=df.index, dtype=float)).astype(object).where(lambda s: s.notna(), None),
        "Experience Requirement": _series(df, "experience_requirement"),
        "Experience Evidence": _series(df, "experience_evidence"),
        "German Required Level": _series(df, "german_required"),
        "German Requirement": _series(df, "german_requirement"),
        "German Evidence": _series(df, "german_evidence"),
    })
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Ranked Jobs"
    header_font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    top_fill = PatternFill("solid", fgColor="FFF2CC")
    border = Border(bottom=Side(style="thin", color="D9D9D9"))

    for column, name in enumerate(output.columns, 1):
        cell = sheet.cell(1, column, name)
        cell.font, cell.fill = header_font, header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_index, row in enumerate(output.itertuples(index=False), 2):
        for column, value in enumerate(row, 1):
            cell = sheet.cell(row_index, column, value)
            cell.font = Font(name="Arial", size=10, color="0563C1", underline="single") if column == 18 and value else Font(name="Arial", size=10)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=column in {2, 10, 17} or column >= 24)
            if row_index <= 11:
                cell.fill = top_fill

    for column in ["K", "L", "M", "N", "O", "P"]:
        sheet.conditional_formatting.add(f"{column}2:{column}{len(output) + 1}", ColorScaleRule(start_type="min", start_color="FF0000", end_type="max", end_color="00FF00"))
    widths = [6, 40, 22, 28, 12, 24, 12, 16, 24, 38, 12, 12, 14, 12, 12, 12, 48, 10, 22, 60, 12, 10, 32, 28, 14, 24, 65, 24, 24, 65]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["T"].hidden = True
    sheet.auto_filter.ref = sheet.dimensions

    methodology = workbook.create_sheet("Methodology")
    lines = [
        "Scoring Methodology", "", "Filters: full-time or blank job type; excluded unrelated, student, internship, senior/lead, and restrictive-language roles; title/company duplicates removed.",
        "Approved not-interested keywords exclude matching titles before the existing filters; exclusions take precedence.",
        "Approved interested keywords mark retained matching titles as likely interested in status; other statuses are blank.",
        "Keywords ignore case and use word boundaries; phrases allow spaces/hyphens. Qualitäts matches word suffixes.",
        "The Link column uses HYPERLINK to reference each row's Job URL in column Q.",
        "Skills & Role Fit (0-40): up to 40 points for three or more matching profile skills, adjusted by seniority.",
        "Language (0-10): English/no German requirement = 10; ambiguous German requirement = 7; fluent German required = 0.",
        "Industry (0-10): aerospace = 10; automotive = 9; research = 8; mechanical = 7; energy = 6; other = 4.",
        "Location (0-10): Bavaria = 10; NRW/Hesse/Baden-Württemberg = 8; selected major cities = 6; other Germany = 4; outside Germany = 0.",
        "Contract (0-10): full-time/unlimited = 10; fixed-term = 5; part-time = 0.",
        "Jobs with equal Total Score are ordered by freshness: exact Posted At when available, otherwise Date Posted. Blank timestamps are not treated as older than their date.",
        "Serial counts each source separately (LS_01 / CS_01); Rank orders all retained jobs together. Website records the collecting source.",
        "The ten highest-ranked jobs are highlighted. Score columns use red-to-green colour scales.",
        "Requirement extraction uses only the description and adds columns without changing existing filtering or scores.",
        "Requirement status: required = explicit obligation; preferred = optional wording; stated = mentioned without explicit obligation; mixed / review = conflicting cues.",
        "Not stated means no matching evidence, not no requirement. Evidence retains original clauses; multiple matches use |.",
        "Experience Min Years is the largest stated/required numeric lower bound; preferred, negated and mixed clauses are excluded. Qualitative experience is never converted to years. Review evidence for alternative qualifications.",
        "German wording remains descriptive; only explicitly written A1-C2 levels are reported as CEFR. Fluent/very good are not converted to CEFR.",
        "This rule-based extraction can miss or mis-scope complex wording. Existing filters can remove jobs before extraction; these columns describe retained jobs only.",
    ]
    for row, line in enumerate(lines, 1):
        methodology.cell(row, 1, line).font = Font(name="Arial", bold=row == 1, size=14 if row == 1 else 10)
    methodology.column_dimensions["A"].width = 120
    workbook.save(output_path)


def rank_jobs(input_csv: str | os.PathLike, output_dir: str | os.PathLike = DEFAULT_OUTPUT_DIR) -> Path | None:
    ranked = rank_dataframe(input_csv, output_dir)
    if ranked.empty:
        print("No new jobs remained after ranking filters and history deduplication.")
        return None
    output_path = next_output_path(output_dir)
    export_excel(ranked, output_path)
    print(f"Ranked {len(ranked)} jobs. Output saved to: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank a scraper CSV and export it to Excel")
    parser.add_argument("input_csv", help="Path to a scraper output CSV")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for ranked Excel files")
    args = parser.parse_args()
    rank_jobs(args.input_csv, args.output_dir)


if __name__ == "__main__":
    main()

