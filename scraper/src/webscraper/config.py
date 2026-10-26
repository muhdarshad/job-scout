"""Configuration constants for the web scraper."""

import os
import yaml

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

REQUEST_DELAY = 0.5
PAGE_SIZE = 20
ENRICH_DELAY = 0.4

COLUMNS = [
    "id",
    "job_url",
    "title",
    "company",
    "location",
    "date_posted",
    "posted_at",
    "job_type",
    "job_level",
    "job_function",
    "description",
    "company_industry",
    "skills",
    "search_term",
]

MERCEDES_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://jobs.mercedes-benz.com",
    "referer": "https://jobs.mercedes-benz.com/",
    "user-agent": HEADERS["User-Agent"],
}

MERCEDES_REQUESTED_FIELDS = [
    "ID",
    "PositionID",
    "PositionTitle",
    "PositionURI",
    "OrganizationName",
    "PositionLocation.CityName",
    "PositionLocation.DisplayName",
    "PositionLocation.CountryCode",
    "PositionStartDate",
    "PublicationStartDate",
    "PositionFormattedDescription.Content",
    "PositionIndustry.Name",
    "JobCategory.Name",
    "CareerLevel.Name",
    "PositionOfferingType.Name",
    "PositionSchedule.Name",
    "ApplyURI",
]

SKILL_KEYWORDS = [
    "Power BI", "DAX", "SQL", "Python", "Excel", "Tableau", "Azure",
    "Databricks", "ETL", "SSIS", "SSRS", "Data Warehouse", "Snowflake",
    "Six Sigma", "DMAIC", "FMEA", "8D", "GD&T", "CMM", "ISO 9001",
    "SAP", "Lean Manufacturing",
    "CATIA", "Siemens NX", "CFD", "Star CCM+", "SolidWorks",
    "Java", "JavaScript", "React", "Git", "AWS", "Docker",
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")


def load_sites_config(config_path: str | None = None) -> dict:
    """Load site configurations from YAML file."""
    if config_path is None:
        config_path = os.path.join(CONFIG_DIR, "sites.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# Load sites from config
_sites_config = load_sites_config()
WORKDAY_SITES = _sites_config.get("workday_sites", [])
OTHER_SITES = _sites_config.get("other_sites", [])
