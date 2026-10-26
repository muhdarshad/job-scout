"""ALTEN Consulting Services platform scraper."""

import logging
import json
import re
import time
from datetime import date, timedelta
from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from ..config import HEADERS, REQUEST_DELAY
from ..utils import strip_html


HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.alten-consulting.de/karriere/stellenangebote",
    "X-Requested-With": "XMLHttpRequest",
}


class AltenPlatform:
    """Scraper for ALTEN Consulting Services' TYPO3 jobs endpoint."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        results, offset = [], 0
        cutoff = date.today() - timedelta(days=site_config["posted_within_days"]) if site_config.get("posted_within_days") else None

        while True:
            params = {
                "eID": "txVbJoblistAjaxDispatcher", "targetAction": "jobs-list",
                "fulltext": site_config.get("search_term", ""), "fulltext_save": "Was?",
                "offset": offset, "numScoutJobs": 0, "sortParameter": "publication_of",
                "sortDirection": "asc", "location": "", "doRecall": "true",
                "workLocation": "", "distance": 10, "umkreisdata": "", "umkreis_save": "",
            }
            response = requests.get(site_config["api_url"], params=params, headers=HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            postings = data.get("xmldata") or data.get("jobs") or data.get("items") or []
            if not postings:
                break

            for item in postings:
                job = self.normalize_job(item, site_config)
                if cutoff and job.get("date_posted"):
                    try:
                        if date.fromisoformat(job["date_posted"][:10]) < cutoff:
                            continue
                    except ValueError:
                        pass
                results.append(job)
                if max_results and len(results) >= max_results:
                    return results[:max_results]

            offset += len(postings)
            total = int(data.get("cnt") or data.get("total") or 0)
            logging.getLogger(__name__).info(f"  [{site_config['company']}] fetched {min(offset, total)} / {total}")
            if not total or offset >= total:
                break
            time.sleep(REQUEST_DELAY)

        return results

    def normalize_job(self, item: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        job_id = str(item.get("id"))
        slug = quote(item.get("slug") or "job", safe="()")
        locations = item.get("standorte") or []
        location = item.get("arbeitsort") or item.get("region") or (locations[0] if locations else None)

        return {
            "id": job_id,
            "job_url": f"{site_config['detail_base_url'].rstrip('/')}/{job_id}/{slug}",
            "title": unescape(item.get("titel") or item.get("title") or "") or None,
            "company": site_config["company"],
            "location": location,
            "date_posted": item.get("publication_of"),
            "job_type": None,
            "job_level": None,
            "job_function": item.get("stellenart") or item.get("area"),
            "description": None,
            "company_industry": item.get("branche") or site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    def fetch_job_detail(self, job_url: str) -> dict[str, Any]:
        try:
            response = requests.get(job_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except Exception as exc:
            print(f"    ! ALTEN detail fetch failed for {job_url}: {exc}")
            return {"description": None}

        soup = BeautifulSoup(response.text, "html.parser")
        posting = self._json_ld_posting(soup)
        address = posting.get("jobLocation", {}).get("address", {}) if posting else {}
        match = re.search(r"/stelle/(\d+)/", job_url)

        return {
            "id": match.group(1) if match else None,
            "title": strip_html(posting.get("title")) if posting else None,
            "location": ", ".join(str(address.get(key)) for key in ("postalCode", "addressLocality", "addressCountry") if address.get(key)) or None,
            "date_posted": posting.get("datePosted") if posting else None,
            "job_type": posting.get("employmentType") if posting else None,
            "description": strip_html(posting.get("description")) if posting else self._html_description(soup),
            "company_industry": posting.get("industry") if posting else None,
        }

    @staticmethod
    def _json_ld_posting(soup: BeautifulSoup) -> dict[str, Any]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = data.get("@graph", []) if isinstance(data, dict) and "@graph" in data else [data]
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                    return candidate
        return {}

    @staticmethod
    def _html_description(soup: BeautifulSoup) -> str | None:
        container = soup.select_one(".job-profile")
        return strip_html(str(container)) if container else None


