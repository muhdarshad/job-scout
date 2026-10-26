"""BMW Group careers scraper."""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import HEADERS, REQUEST_DELAY
from ..utils import strip_html
from .career import candidate


BMW_BASE_URL = "https://www.bmwgroup.jobs"
BMW_HEADERS = {
    **HEADERS,
    "Accept": "*/*",
    "Referer": "https://www.bmwgroup.jobs/en.html",
    "X-Requested-With": "XMLHttpRequest",
}


class BMWPlatform:
    """Scraper for BMW Group's AEM job finder."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        results, row_index = [], 0
        page_size = site_config.get("page_size", 50)
        cutoff = date.today() - timedelta(days=site_config["posted_within_days"]) if site_config.get("posted_within_days") else None
        session = requests.Session()
        session.headers.update(BMW_HEADERS)

        while True:
            params = {"rowIndex": row_index, "blockCount": page_size}
            if site_config.get("country_filter") == "Germany":
                params["filterSearch"] = "location_DE"
            response = session.get(site_config["api_url"], params=params, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            wrappers = soup.select(".grp-jobfinder__wrapper")
            if not wrappers:
                break

            page_dates = []
            for wrapper in wrappers:
                raw = self._parse_listing(wrapper)
                posted = self._parse_date(raw.get("date_posted"))
                if posted:
                    page_dates.append(posted)
                if cutoff and (not posted or posted < cutoff):
                    continue
                if not raw.get("job_url") or not candidate(raw.get("title"), site_config):
                    continue
                if site_config.get("country_filter") == "Germany":
                    raw["location"] = ", ".join(filter(None, (raw.get("location"), "Germany")))
                results.append(self.normalize_job(raw, site_config))
                if max_results and len(results) >= max_results:
                    return results[:max_results]

            row_index += len(wrappers)
            total_node = soup.select_one(".grp-jobfinder__table[data-counter]")
            total = int(total_node.get("data-counter", 0)) if total_node else 0
            logging.getLogger(__name__).info(f"  [{site_config['company']}] fetched {min(row_index, total or row_index)} / {total or '?'}")
            if (total and row_index >= total) or (cutoff and page_dates and max(page_dates) < cutoff):
                break
            time.sleep(REQUEST_DELAY)

        return results

    @staticmethod
    def _parse_listing(wrapper) -> dict[str, Any]:
        link = wrapper.select_one("a.grp-jobfinder__link-jobdescription")
        ref = wrapper.select_one(".grp-jobfinder-cell-refno")
        attrs = ref.attrs if ref else {}
        return {
            "id": wrapper.get("data-job-id") or (ref.get_text(strip=True) if ref else None),
            "job_url": urljoin(BMW_BASE_URL, link.get("href", "")) if link else None,
            "title": attrs.get("data-job-title"),
            "location": attrs.get("data-job-location"),
            "date_posted": attrs.get("data-posting-date"),
            "job_level": attrs.get("data-job-type"),
            "job_function": attrs.get("data-job-field"),
        }

    def normalize_job(self, raw_job: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(raw_job.get("id")),
            "job_url": raw_job.get("job_url"),
            "title": raw_job.get("title"),
            "company": site_config["company"],
            "location": raw_job.get("location"),
            "date_posted": self._iso_date(raw_job.get("date_posted")),
            "job_type": raw_job.get("job_type"),
            "job_level": raw_job.get("job_level"),
            "job_function": raw_job.get("job_function"),
            "description": raw_job.get("description"),
            "company_industry": raw_job.get("company_industry") or site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    def fetch_job_detail(self, job_url: str, session: requests.Session | None = None) -> dict[str, Any]:
        use_session = session or requests.Session()
        use_session.headers.update(BMW_HEADERS)
        detail_url = job_url[:-5] + ".content.html" if job_url.endswith(".html") else job_url
        try:
            response = use_session.get(detail_url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            print(f"    ! BMW detail fetch failed for {job_url}: {exc}")
            return {"description": None, "_country": None}

        soup = BeautifulSoup(response.text, "html.parser")
        city = soup.select_one('[itemprop="addressLocality"]')
        country = soup.select_one('[itemprop="addressRegion"]')
        value = lambda node: node.get_text(" ", strip=True) if node else None
        return {
            "id": value(soup.select_one('.grp-jobdescription__jobid')),
            "title": value(soup.select_one('h1 .cmp-title__text-title1')),
            "location": ", ".join(filter(None, (value(city), value(country)))),
            "date_posted": self._iso_date(value(soup.select_one('[itemprop="datePosted"]'))),
            "job_type": value(soup.select_one('.grp-jobdescription__jobType')) or value(soup.select_one('[itemprop="employmentType"]')),
            "job_function": value(soup.select_one('.grp-jobdescription__jobField')),
            "description": strip_html(str(soup.select_one('[itemprop="description"]') or "")),
            "company_industry": value(soup.select_one('[itemprop="industry"]')),
            "_country": value(country),
        }

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        try:
            return datetime.strptime((value or "")[:8], "%Y%m%d").date()
        except ValueError:
            return None

    @classmethod
    def _iso_date(cls, value: str | None) -> str | None:
        parsed = cls._parse_date(value)
        return parsed.isoformat() if parsed else value




