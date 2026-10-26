"""Workday platform scraper."""

import logging
import re
import time
import requests
from datetime import date, timedelta
from typing import Any

from ..config import HEADERS, PAGE_SIZE, REQUEST_DELAY


class WorkdayPlatform:
    """Scraper for Workday-based career sites."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        """Paginate through all job postings for one Workday site config."""
        tenant = site_config["tenant"]
        cluster = site_config["cluster"]
        site = site_config["site"]
        company = site_config["company"]
        search_term = site_config.get("search_term", "")
        location_country = site_config.get("location_country")
        location_country_label = site_config.get("location_country_label")
        posted_within_days = site_config.get("posted_within_days")

        base_url = f"https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        job_base = f"https://{tenant}.{cluster}.myworkdayjobs.com/{site}"

        results = []
        offset = 0
        applied_facets = {}
        country_facet_param = "locationCountry"
        date_facet_param = "startDate"

        if location_country:
            applied_facets[country_facet_param] = [location_country]

        if location_country_label or posted_within_days:
            bootstrap = requests.post(base_url, headers=HEADERS, json={
                "appliedFacets": applied_facets, "limit": 1, "offset": 0, "searchText": search_term,
            }, timeout=15)
            bootstrap.raise_for_status()
            facet_data = bootstrap.json()

            if location_country_label and not location_country:
                location_country, country_facet_param = self._find_country_facet(facet_data, location_country_label)
                if location_country:
                    applied_facets[country_facet_param] = [location_country]

            date_labels = self._date_facet_labels(posted_within_days)
            start_date, date_facet_param = self._find_date_facet(facet_data, date_labels)
            if start_date:
                applied_facets[date_facet_param] = [start_date]

        country_is_server_side = country_facet_param in applied_facets
        date_is_server_side = date_facet_param in applied_facets
        cutoff = date.today() - timedelta(days=posted_within_days) if posted_within_days else None
        scanned = matched = total = 0

        while True:
            payload = {
                "appliedFacets": applied_facets,
                "limit": PAGE_SIZE,
                "offset": offset,
                "searchText": search_term,
            }

            resp = requests.post(base_url, headers=HEADERS, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for job in postings:
                scanned += 1
                if not country_is_server_side and location_country_label and location_country_label.casefold() not in (job.get("locationsText") or "").casefold():
                    continue
                if not date_is_server_side and cutoff:
                    posted_date = self._posted_date(job.get("postedOn"))
                    if not posted_date or posted_date < cutoff:
                        continue
                matched += 1
                if not max_results or len(results) < max_results:
                    results.append(self.normalize_job(job, site_config))

            total = int(data.get("total", 0))
            offset += PAGE_SIZE

            if max_results and len(results) >= max_results and country_is_server_side and date_is_server_side:
                break

            if offset >= total:
                break
            time.sleep(REQUEST_DELAY)

        filtered_total = total if country_is_server_side and date_is_server_side else matched
        logging.getLogger(__name__).info(
            f"  [{company}] matched {filtered_total} jobs for the configured country/date filters; "
            f"scanned {scanned} postings; returning {len(results)}"
        )
        return results

    def _find_country_facet(self, facet_data: dict[str, Any], label: str) -> tuple[str | None, str]:
        """Find country facet ID and parameter name from bootstrap data."""
        for param in ("Country", "locationCountry"):
            facet_id = self._facet_id(facet_data, param, [label])
            if facet_id:
                return facet_id, param
        for facet in facet_data.get("facets", []):
            if (facet.get("descriptor") or "").casefold() == "country":
                facet_id = self._facet_id(facet_data, facet.get("facetParameter"), [label])
                if facet_id:
                    return facet_id, facet.get("facetParameter")
        return None, "locationCountry"

    def _find_date_facet(self, facet_data: dict[str, Any], labels: list[str]) -> tuple[str | None, str]:
        """Find date facet ID and parameter name from bootstrap data."""
        for param in ("startDate", "postedDate", "postingDate"):
            facet_id = self._facet_id(facet_data, param, labels)
            if facet_id:
                return facet_id, param
        for facet in facet_data.get("facets", []):
            if "date" in (facet.get("descriptor") or "").casefold() or "posting" in (facet.get("facetParameter") or "").casefold():
                facet_id = self._facet_id(facet_data, facet.get("facetParameter"), labels)
                if facet_id:
                    return facet_id, facet.get("facetParameter")
        return None, "startDate"

    def normalize_job(self, job: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        """Map a raw Workday job posting to the canonical COLUMNS schema."""
        company = site_config["company"]
        site = site_config["site"]
        external_path = job.get("externalPath", "")
        job_base = f"https://{site_config['tenant']}.{site_config['cluster']}.myworkdayjobs.com/{site}"

        return {
            "id": external_path.rsplit("_", 1)[-1] or external_path,
            "job_url": f"{job_base}{external_path}",
            "title": job.get("title"),
            "company": company,
            "location": job.get("locationsText"),
            "date_posted": self._posted_date(job.get("postedOn")).isoformat() if self._posted_date(job.get("postedOn")) else job.get("postedOn"),
            "job_type": job.get("timeType"),
            "job_level": None,
            "job_function": None,
            "description": None,
            "company_industry": site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    @staticmethod
    def _facet_id(data: dict[str, Any], parameter: str, labels: list[str]) -> str | None:
        wanted = [label.casefold() for label in labels]
        facet = next((item for item in data.get("facets", []) if item.get("facetParameter") == parameter), {})
        for value in facet.get("values", []):
            descriptor = (value.get("descriptor") or "").casefold()
            if any(label == descriptor or label in descriptor for label in wanted):
                return value.get("id")
        return None

    @staticmethod
    def _date_facet_labels(days: int | None) -> list[str]:
        if days == 1:
            return ["posted today", "today", "last 24 hours", "past 24 hours", "1 day"]
        if days == 7:
            return ["last 7 days", "past 7 days", "week"]
        return [f"last {days} days", f"past {days} days"] if days else []

    @staticmethod
    def _posted_date(value: str | None) -> date | None:
        text = (value or "").casefold()
        if "today" in text:
            return date.today()
        if "yesterday" in text:
            return date.today() - timedelta(days=1)
        match = re.search(r"(\d+)\s+days?\s+ago", text)
        return date.today() - timedelta(days=int(match.group(1))) if match else None

    def _extract_field_from_html(self, html: str, field_label: str) -> str | None:
        """Extract a field value from HTML following a specific label pattern."""
        if not html:
            return None
        pattern = rf"<b>\s*{re.escape(field_label)}\s*:</b></p>\s*([^<]+)"
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def fetch_job_detail(self, job_url: str, tenant: str, cluster: str, site: str) -> dict[str, Any]:
        """Fetch full job description and type from Workday detail API."""
        marker = f"/{site}/job/"
        idx = job_url.find(marker)
        if idx == -1:
            return {"description": None, "job_type": None, "job_level": None, "job_function": None}

        path_tail = job_url[idx + len(marker):]
        detail_url = f"https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{path_tail}"

        try:
            resp = requests.get(detail_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    ! Workday detail fetch failed for {job_url}: {e}")
            return {"description": None, "job_type": None, "job_level": None, "job_function": None}

        info = data.get("jobPostingInfo", {})
        raw_html = info.get("jobDescription")
        from ..utils import strip_html

        job_level = self._extract_field_from_html(raw_html, "Employment Type")
        job_function = self._extract_field_from_html(raw_html, "Job Family")

        return {
            "description": strip_html(raw_html),
            "job_type": info.get("timeType"),
            "job_level": job_level,
            "job_function": job_function,
        }


