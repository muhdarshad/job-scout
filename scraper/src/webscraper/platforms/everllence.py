"""Everllence's SuccessFactors Recruiting Marketing career site."""

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, recent, text


class EverllencePlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        with career_session() as session:
            while True:
                response = session.get(site_config["search_url"], params={
                    "q": site_config.get("search_term", ""), "startrow": offset,
                    "sortColumn": "referencedate", "sortDirection": "desc",
                }, timeout=25)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                tiles = soup.select(".job-tile")
                fresh = 0
                for tile in tiles:
                    link = tile.select_one("a.jobTitle-link")
                    if not link:
                        continue
                    url = urljoin(response.url, link["href"])
                    if url in seen:
                        continue
                    seen.add(url)
                    fresh += 1
                    title = link.get_text(" ", strip=True)
                    location = text(tile, '[id$="-desktop-section-multilocation-value"]') or text(tile, '[id$="-tablet-section-location-value"]')
                    if not re.search(r"(?:^|,)\s*DE(?:\s*,|$)", location or "") or not candidate(title, site_config):
                        continue
                    try:
                        detail = self.fetch_job_detail(url, site_config, session)
                    except Exception as exc:
                        print(f"    ! Everllence detail failed for {url}: {exc}")
                        continue
                    if not recent(detail.get("date_posted"), site_config):
                        continue
                    detail.update(id=url.rstrip("/").split("/")[-1], job_url=url, location=location,
                                  job_level=text(tile, '[id$="-desktop-section-customfield1-value"]'),
                                  job_function=text(tile, '[id$="-desktop-section-customfield2-value"]'))
                    results.append(self.normalize_job(detail, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                if not fresh:
                    break
                offset += len(tiles)
                time.sleep(REQUEST_DELAY)
        return results

