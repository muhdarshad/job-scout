"""Boeing's Radancy/TalentBrew Germany job listings."""

import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, recent, text


class BoeingPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, page = [], set(), 1
        with career_session() as session:
            response = session.get(site_config["search_url"], timeout=25)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            while True:
                root = soup.select_one('[data-selector-name="searchresults"]')
                if root is None:
                    raise ValueError("Boeing search-results contract was not found")
                listings = root.select("#search-results-list li")
                fresh = 0
                for listing in listings:
                    link = listing.select_one("a.search-results__job-link")
                    if not link:
                        continue
                    job_id = link.get("data-job-id")
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    fresh += 1
                    title = link.get_text(" ", strip=True)
                    posted = text(listing, ".date")
                    if not candidate(title, site_config) or not recent(posted, site_config):
                        continue
                    raw = {"id": job_id, "job_url": urljoin(site_config["search_url"], link["href"]),
                           "title": title, "location": text(listing, ".location") + ", Germany", "date_posted": posted}
                    results.append(self.normalize_job(raw, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                if not fresh or page >= int(root.get("data-total-pages", 1)):
                    break
                page += 1
                response = session.get(urljoin(site_config["search_url"], root["data-ajax-url"]), params={
                    "CurrentPage": page, "RecordsPerPage": int(root.get("data-records-per-page", 15)),
                    "FacetTerm": root.get("data-facet-term", "2921044"), "FacetType": 2,
                    "SearchType": 3, "ResultsType": 1, "OrganizationIds": "185", "IsPagination": "true",
                    "SortCriteria": root.get("data-sort-criteria", "0"), "SortDirection": root.get("data-sort-direction", "1"),
                }, timeout=25)
                response.raise_for_status()
                payload = response.json()
                soup = BeautifulSoup(payload["results"], "html.parser")
                time.sleep(REQUEST_DELAY)
        return results

