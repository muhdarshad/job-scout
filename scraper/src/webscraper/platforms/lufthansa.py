"""Lufthansa Group careers platform scraper."""

import logging
import json
import re
import time
from datetime import date, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

from ..config import HEADERS, REQUEST_DELAY
from ..utils import first_item, strip_html


FIELDS = [
    "ID", "PositionTitle", "PositionURI", "PositionShortURI",
    "PositionLocation.CountryName", "PositionLocation.CityName",
    "JobCategory.Name", "PublicationStartDate", "ParentOrganizationName",
    "OrganizationShortName", "CareerLevel.Name", "JobSector.Name",
    "PositionIndustry.Name", "PublicationCode", "PositionSchedule.Name",
    "PositionOfferingType.Name", "PositionStartDate",
]
HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://apply.lufthansagroup.careers",
    "Referer": "https://apply.lufthansagroup.careers/",
}


class LufthansaPlatform:
    """Scraper for Lufthansa Group's public careers API."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        results, first, page_size = [], 1, 25
        cutoff = date.today() - timedelta(days=site_config["posted_within_days"]) if site_config.get("posted_within_days") else None
        matched = scanned = 0

        while True:
            payload = {
                "LanguageCode": site_config.get("language", "EN"),
                "SearchParameters": {
                    "FirstItem": first,
                    "CountItem": page_size,
                    "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                    "MatchedObjectDescriptor": FIELDS,
                },
                "SearchCriteria": [
                    {"CriterionName": "PositionLocation.Distance", "CriterionValue": ["25"]},
                    {"CriterionName": "PositionLocation.Unit", "CriterionValue": ["km"]},
                    {"CriterionName": "PublicationChannel.Code", "CriterionValue": ["12"]},
                ],
            }
            if site_config.get("search_term"):
                payload["SearchCriteria"].append({"CriterionName": "PositionTitle", "CriterionValue": site_config["search_term"]})
            if cutoff:
                payload["SearchCriteria"].append({"CriterionName": "PublicationStartDate", "CriterionValue": [cutoff.isoformat()]})

            response = requests.get(
                site_config["api_url"], params={"data": json.dumps(payload, separators=(",", ":"))},
                headers=HEADERS, timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            search_result = data.get("SearchResult", data)
            postings = search_result.get("SearchResultItems", [])
            total = int(search_result.get("SearchResultCountAll") or 0)
            if not postings:
                break

            for item in postings:
                scanned += 1
                job = self.normalize_job(item, site_config)
                if site_config.get("country_filter") and site_config["country_filter"].lower() not in (job["location"] or "").lower():
                    continue
                if cutoff and job.get("date_posted"):
                    try:
                        if date.fromisoformat(job["date_posted"][:10]) < cutoff:
                            continue
                    except ValueError:
                        pass
                matched += 1
                if not max_results or len(results) < max_results:
                    results.append(job)

            first += len(postings)
            if not total or first > total:
                break
            time.sleep(REQUEST_DELAY)

        logging.getLogger(__name__).info(f"  [{site_config['company']}] matched {matched} Germany jobs posted since {cutoff}; scanned {scanned} date-filtered postings; returning {len(results)}")
        return results

    def normalize_job(self, item: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        desc = item.get("MatchedObjectDescriptor", item)
        location = first_item(desc.get("PositionLocation")) or {}
        city, country = location.get("CityName"), location.get("CountryName")

        return {
            "id": str(desc.get("ID") or item.get("MatchedObjectId")),
            "job_url": desc.get("PositionURI") or desc.get("PositionShortURI"),
            "title": desc.get("PositionTitle"),
            "company": site_config["company"],
            "location": ", ".join(part for part in (city, country) if part),
            "date_posted": desc.get("PublicationStartDate"),
            "job_type": first_item(desc.get("PositionSchedule"), "Name") or first_item(desc.get("PositionOfferingType"), "Name"),
            "job_level": first_item(desc.get("CareerLevel"), "Name"),
            "job_function": first_item(desc.get("JobCategory"), "Name") or first_item(desc.get("JobSector"), "Name"),
            "description": None,
            "company_industry": first_item(desc.get("PositionIndustry"), "Name") or site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    def fetch_job_detail(self, job_url: str) -> dict[str, Any]:
        try:
            response = requests.get(job_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except Exception as exc:
            print(f"    ! Lufthansa detail fetch failed for {job_url}: {exc}")
            return {"description": None}

        soup = BeautifulSoup(response.text, "html.parser")
        container = soup.select_one(".lh-jobad-content-details") or soup.select_one("#jobad-container")
        if container:
            for element in container.select("script, style, svg, iframe, video, button, .lh-jobad-collapsible-slider-container"):
                element.decompose()
        job_id = (soup.select_one("#jobad-container") or {}).get("data-jobad-id") if soup.select_one("#jobad-container") else None
        if not job_id:
            match = re.search(r"[?&]id=(\d+)", job_url)
            job_id = match.group(1) if match else None

        return {
            "id": job_id,
            "title": strip_html(str(soup.select_one("#jobad-container h1"))) if soup.select_one("#jobad-container h1") else None,
            "description": strip_html(str(container)) if container else None,
        }


