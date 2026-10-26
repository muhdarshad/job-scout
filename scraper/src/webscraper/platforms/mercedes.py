"""Mercedes-Benz (SuccessFactors) platform scraper."""

import logging
import json
import time
import uuid
import requests
from datetime import date, timedelta
from typing import Any

from ..config import MERCEDES_HEADERS, MERCEDES_REQUESTED_FIELDS, REQUEST_DELAY
from ..utils import strip_html, first_item


class MercedesPlatform:
    """Scraper for Mercedes-Benz's SuccessFactors-based career site."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        """Paginate through Mercedes-Benz's search API."""
        company = site_config["company"]
        api_url = site_config["api_url"]
        search_term = site_config.get("search_term", "")
        country_filter = site_config.get("country_filter")
        posted_within_days = site_config.get("posted_within_days")

        search_criteria = []
        if search_term:
            search_criteria = [{"CriterionName": "PositionTitle", "CriterionValue": search_term}]

        results = []
        seen_job_ids = set()
        first_item_idx = 1

        cutoff_date = None
        if posted_within_days:
            cutoff_date = date.today() - timedelta(days=posted_within_days)

        while True:
            payload = {
                "LanguageCode": "EN",
                "SearchParameters": {
                    "FirstItem": first_item_idx,
                    "CountItem": 20,
                    "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                    "MatchedObjectDescriptor": MERCEDES_REQUESTED_FIELDS,
                },
                "SearchCriteria": search_criteria,
            }

            params = {"data": json.dumps(payload, separators=(",", ":"))}

            resp = requests.get(api_url, params=params, headers=MERCEDES_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            postings = (
                data.get("SearchResult", {}).get("SearchResultItems")
                or data.get("SearchResultItems")
                or []
            )

            if not postings:
                break

            for item in postings:
                desc = item.get("MatchedObjectDescriptor", item)
                job_id = desc.get("ID") or desc.get("PositionID")
                if job_id and job_id in seen_job_ids:
                    continue
                if job_id:
                    seen_job_ids.add(job_id)

                job = self.normalize_job(item, site_config)
                
                # Client-side date filtering
                if cutoff_date and job.get("date_posted"):
                    try:
                        job_date = date.fromisoformat(job["date_posted"][:10])
                        if job_date < cutoff_date:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # Client-side country filtering if server-side doesn't work
                if country_filter and job.get("location"):
                    location = job["location"].lower()
                    germany_terms = ["germany", "deutschland", "stuttgart", "munich", "münchen", "berlin", "hamburg", "frankfurt", "cologne", "köln", "düsseldorf", "dortmund", "essen", "bremen", "leipzig", "dresden", "hannover", "nuremberg", "nürnberg", "duisburg", "bochum", "wuppertal", "bielefeld", "bonn", "münster", "karlsruhe", "mannheim", "augsburg", "wiesbaden", "gelsenkirchen", "mönchengladbach", "braunschweig", "chemnitz", "kiel", "aachen", "halle", "magdeburg", "freiburg", "krefeld", "lübeck", "oberhausen", "erfurt", "mainz", "rostock", "kassel", "hagen", "hamm", "saarbrücken", "potsdam", "ludwigshafen", "oldenburg", "leverkusen", "osnabrueck", "osnabrück", "solingen", "heidelberg", "herne", "neuss", "darmstadt", "paderborn", "regensburg", "ingolstadt", "wuerzburg", "wuerzburg", "fuerth", "wolfsburg", "offenbach", "ulm", "heidenheim", "pforzheim", "goettingen", "goettingen", "bottrop", "trier", "recklinghausen", "reutlingen", "koblenz", "bergisch gladbach", "jena", "rostock", "erlangen", "moers", "siegen", "hildesheim", "salzgitter", "sindelfingen"]
                    is_germany = any(term in location for term in germany_terms)
                    if not is_germany:
                        continue
                results.append(job)

            total = data.get("SearchResult", {}).get("SearchResultCountAll") or 0
            first_item_idx += 20
            logging.getLogger(__name__).info(f"  [{company}] fetched {min(first_item_idx - 1, total)} / {total}"
                  + (f" (capped at {max_results})" if max_results else ""))

            if max_results and len(results) >= max_results:
                results = results[:max_results]
                break

            if first_item_idx > total or not total:
                break
            time.sleep(REQUEST_DELAY)

        return results

    def normalize_job(self, item: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        """Map one Mercedes-Benz search result to the canonical COLUMNS schema."""
        company = site_config["company"]
        desc = item.get("MatchedObjectDescriptor", item)

        location = first_item(desc.get("PositionLocation"), "DisplayName") or first_item(
            desc.get("PositionLocation"), "CityName"
        )

        apply_uri = desc.get("ApplyURI")
        job_url = desc.get("PositionURI") or (apply_uri[0] if apply_uri else None)

        return {
            "id": str(uuid.uuid4()),
            "job_url": job_url,
            "title": desc.get("PositionTitle"),
            "company": company,
            "location": location,
            "date_posted": desc.get("PublicationStartDate") or desc.get("PositionStartDate"),
            "job_type": first_item(desc.get("PositionOfferingType"), "Name")
            or first_item(desc.get("PositionSchedule"), "Name"),
            "job_level": first_item(desc.get("CareerLevel"), "Name"),
            "job_function": first_item(desc.get("JobCategory"), "Name"),
            "description": strip_html(desc.get("PositionFormattedDescription.Content")),
            "company_industry": first_item(desc.get("PositionIndustry"), "Name")
            or site_config.get("company_industry"),
            "skills": None,
            "search_term": site_config.get("search_term", ""),
        }

    def fetch_job_detail(self, job_url: str) -> str | None:
        """Fetch full job description from Mercedes-Benz job detail page."""
        try:
            resp = requests.get(job_url, headers=MERCEDES_HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"    ! Mercedes detail fetch failed for {job_url}: {e}")
            return None

        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(resp.text, "html.parser")

        SELECTOR_CANDIDATES = [
            {"class_": re.compile(r"job.?description", re.I)},
            {"class_": re.compile(r"posting.?description", re.I)},
            {"id": re.compile(r"job.?description", re.I)},
        ]

        for selector in SELECTOR_CANDIDATES:
            el = soup.find(attrs=selector)
            if el and el.get_text(strip=True):
                return strip_html(str(el))

        main = soup.find("main")
        if main and main.get_text(strip=True):
            return strip_html(str(main))

        return None

