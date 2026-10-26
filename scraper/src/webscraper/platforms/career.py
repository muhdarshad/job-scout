"""Shared parsing and filtering for public career portals."""

import json
import re
from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import COLUMNS, HEADERS
from ..utils import strip_html
from ..utils.filtering import title_allowed


def career_session():
    session = requests.Session()
    session.headers.update({"User-Agent": HEADERS["User-Agent"], "Accept": "*/*"})
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def parse_date(value):
    value = str(value or "").strip()
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d-%b-%Y", "%d.%m.%Y", "%m/%d/%Y", "%a %b %d %H:%M:%S UTC %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_timestamp(value):
    """Return an ISO timestamp only when the source contains explicit clock time."""
    value = str(value or "").strip()
    if not value or not re.search(r"(?:T|\s)\d{1,2}:\d{2}", value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return parsed.isoformat().replace("+00:00", "Z")


def recent(value, config):
    days = config.get("posted_within_days")
    posted = parse_date(value)
    return days is None or (posted is not None and posted >= date.today() - timedelta(days=days))


def german(value):
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id")
    return str(value or "").strip().casefold() in {"de", "deu", "germany", "deutschland"}


def candidate(title, config):
    term = config.get("search_term", "")
    return title_allowed(title) and (not term or term.casefold() in (title or "").casefold())


def text(soup, selector):
    node = soup.select_one(selector)
    return (node.get("content") or node.get_text(" ", strip=True)) if node else None


def job_posting(soup):
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if "JobPosting" in (types if isinstance(types, list) else [types]):
                yield value
            yield from walk(value.get("@graph", []))

    for node in soup.select('script[type="application/ld+json"]'):
        try:
            posting = next(walk(json.loads(node.string or node.get_text())), None)
            if posting:
                return posting
        except (ValueError, TypeError):
            continue
    return {}


def posting_detail(soup):
    data = job_posting(soup)
    locations, countries = [], []
    places = data.get("jobLocation") or []
    for place in places if isinstance(places, list) else [places]:
        address = place.get("address", {}) if isinstance(place, dict) else {}
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        countries.append(country)
        locations.append(", ".join(str(x) for x in (address.get("addressLocality"), address.get("addressRegion"), country) if x))
    identifier = data.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    employment = data.get("employmentType")
    raw_posted = data.get("datePosted") or text(soup, '[itemprop="datePosted"]')
    return {
        "id": str(identifier) if identifier else None,
        "title": data.get("title") or text(soup, '[itemprop="title"]') or text(soup, "h1"),
        "date_posted": raw_posted,
        "posted_at": parse_timestamp(raw_posted),
        "location": "; ".join(filter(None, locations)) or text(soup, '[itemprop="streetAddress"]'),
        "description": strip_html(data.get("description")) or text(soup, '[itemprop="description"]'),
        "job_type": ", ".join(employment) if isinstance(employment, list) else employment,
        "job_level": data.get("experienceRequirements") if isinstance(data.get("experienceRequirements"), str) else None,
        "job_function": data.get("occupationalCategory"),
        "_countries": countries,
    }


class CareerPlatform:
    def normalize_job(self, raw_job, site_config):
        job = {field: raw_job.get(field) for field in COLUMNS}
        job["id"] = str(raw_job["id"]) if raw_job.get("id") is not None else None
        posted = parse_date(raw_job.get("date_posted"))
        job.update(company=site_config["company"], company_industry=site_config.get("company_industry"),
                   date_posted=posted.isoformat() if posted else None,
                   posted_at=parse_timestamp(raw_job.get("posted_at")),
                   search_term=site_config.get("search_term", ""))
        return job

    def fetch_job_detail(self, job_url, site_config=None, session=None):
        with career_session() if session is None else nullcontext(session) as client:
            response = client.get(job_url, timeout=25)
            response.raise_for_status()
            detail = posting_detail(BeautifulSoup(response.text, "html.parser"))
            posted = parse_date(detail.get("date_posted"))
            detail["date_posted"] = posted.isoformat() if posted else None
            detail["posted_at"] = parse_timestamp(detail.get("posted_at"))
            return detail

