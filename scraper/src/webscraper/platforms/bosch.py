"""Bosch careers API scraper."""

import logging
import json
import re
import time
from datetime import date, timedelta
from typing import Any

import requests

from ..config import HEADERS, REQUEST_DELAY
from ..utils import strip_html
from .career import parse_timestamp


class BoschPlatform:
    """Scraper for Bosch's CaaS careers API."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        headers = self._headers(site_config)
        cutoff = date.today() - timedelta(days=site_config["posted_within_days"]) if site_config.get("posted_within_days") else None
        country = site_config.get("country_code", "de")
        page_size = site_config.get("page_size", 50)
        results, page = [], 1

        while True:
            avars = {"country": [country], "sort": {"releasedDate": -1}, "page_language": site_config.get("language", "en")}
            response = requests.get(site_config["api_url"], params={"pagesize": page_size, "page": page, "avars": json.dumps(avars, separators=(",", ":"))}, headers=headers, timeout=20)
            response.raise_for_status()
            result = response.json().get("_embedded", {}).get("rh:result", [{}])[0]
            jobs = result.get("data", [])
            if not jobs:
                break

            page_dates = []
            for raw in jobs:
                posted = self._parse_date(raw.get("releasedDate"))
                if posted:
                    page_dates.append(posted)
                if (raw.get("location", {}).get("country") or "").casefold() != country.casefold():
                    continue
                if cutoff and (not posted or posted < cutoff):
                    continue
                results.append(self.normalize_job(raw, site_config))
                if max_results and len(results) >= max_results:
                    return results[:max_results]

            total = int((result.get("meta") or [{}])[0].get("count", 0))
            logging.getLogger(__name__).info(f"  [{site_config['company']}] fetched {min(page * page_size, total)} / {total}")
            if page * page_size >= total or (cutoff and page_dates and max(page_dates) < cutoff):
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        return results

    def normalize_job(self, raw_job: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        location = raw_job.get("location", {})
        slug = raw_job.get("jobUrl") or raw_job.get("refNumber")
        released = raw_job.get("releasedDate")
        return {
            "id": raw_job.get("refNumber") or raw_job.get("_id"),
            "job_url": f"{site_config['detail_base_url'].rstrip('/')}/{slug}",
            "title": raw_job.get("name"),
            "company": site_config["company"],
            "location": ", ".join(filter(None, (location.get("workLocation") or location.get("city"), "Germany"))),
            "date_posted": (released or "")[:10] or None,
            "posted_at": parse_timestamp(released),
            "job_type": self._label(raw_job.get("working_hours")) or self._label(raw_job.get("type_of_contract")),
            "job_level": self._label(raw_job.get("positionType")),
            "job_function": self._label(raw_job.get("function")),
            "description": None,
            "company_industry": site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    def fetch_job_detail(self, job_url: str, site_config: dict[str, Any]) -> dict[str, Any]:
        match = re.search(r"(REF[A-Z0-9]+)", job_url, re.IGNORECASE)
        if not match:
            return {"description": None}
        try:
            response = requests.get(site_config["detail_api_url"], params={"np": "", "rep": "pj", "filter": json.dumps({"refNumber": match.group(1).upper()}, separators=(",", ":"))}, headers=self._headers(site_config), timeout=20)
            response.raise_for_status()
            variants = response.json()
        except Exception as exc:
            print(f"    ! Bosch detail fetch failed for {job_url}: {exc}")
            return {"description": None}

        language = site_config.get("language", "en")
        detail = next((item for item in variants if item.get("defaultJobAd")), None) or next((item for item in variants if item.get("language", {}).get("code") == language), None) or (variants[0] if variants else {})
        sections = detail.get("jobAd", {}).get("sections", {})
        raw_description = " ".join((sections.get(key) or {}).get("text", "") for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
        location = detail.get("location", {})
        released = detail.get("releasedDate")
        return {
            "id": detail.get("refNumber"),
            "title": detail.get("name"),
            "location": location.get("fullLocation") or ", ".join(filter(None, (location.get("workLocation") or location.get("city"), "Germany"))),
            "date_posted": (released or "")[:10] or None,
            "posted_at": parse_timestamp(released),
            "job_type": self._label(detail.get("typeOfEmployment")),
            "job_level": self._label(detail.get("experienceLevel")),
            "job_function": self._label(detail.get("function")),
            "description": strip_html(raw_description),
            "company_industry": self._label(detail.get("industry")),
        }

    @staticmethod
    def _headers(site_config: dict[str, Any]) -> dict[str, str]:
        return {**HEADERS, "Accept": "application/json, text/plain, */*", "Authorization": f"Bearer {site_config['api_token']}", "Origin": "https://jobs.bosch.com"}

    @staticmethod
    def _label(value: Any) -> str | None:
        return value.get("valueLabel") or value.get("label") if isinstance(value, dict) else None

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        try:
            return date.fromisoformat((value or "")[:10])
        except ValueError:
            return None

