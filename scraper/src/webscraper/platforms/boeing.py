"""Boeing's Radancy/TalentBrew Germany job listings."""

import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, recent, text


def listing_date(value):
    """Boeing lists US month-first dates, e.g. '11.19.2026' and '10/05/2026'."""
    value = (value or "").strip()
    for fmt in ("%m.%d.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


class BoeingPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        # Pages are followed through the HTML "Next" link: the AJAX endpoint
        # (/search-jobs/results) now returns empty results for later pages.
        results, seen, url = [], set(), site_config["search_url"]
        with career_session() as session:
            while url:
                response = session.get(url, timeout=25)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                root = soup.select_one('[data-selector-name="searchresults"]')
                if root is None:
                    raise ValueError("Boeing search-results contract was not found")
                for listing in root.select("#search-results-list li"):
                    link = listing.select_one("a.search-results__job-link")
                    job_id = link.get("data-job-id") if link else None
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    title = link.get_text(" ", strip=True)
                    posted = listing_date(text(listing, ".date"))
                    if not candidate(title, site_config) or not recent(posted, site_config):
                        continue
                    location = text(listing, ".location") or ""
                    if "germany" not in location.casefold():
                        location = f"{location}, Germany" if location else "Germany"
                    raw = {"id": job_id, "job_url": urljoin(site_config["search_url"], link["href"]),
                           "title": title, "location": location, "date_posted": posted}
                    results.append(self.normalize_job(raw, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                next_link = soup.select_one("nav.pagination a.next:not(.disabled)")
                url = urljoin(site_config["search_url"], next_link["href"]) if next_link and next_link.get("href") else None
                if url:
                    time.sleep(REQUEST_DELAY)
        return results
