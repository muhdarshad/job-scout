"""DHL's Phenom public job-search API."""

import re
import time
from urllib.parse import quote

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, german, parse_date, recent


class DHLPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        size = site_config.get("page_size", 50)
        with career_session() as session:
            while True:
                body = {
                    "lang": "en_global", "deviceType": "desktop", "country": "global", "pageName": "search-results",
                    "ddoKey": "eagerLoadRefineSearch", "sortBy": "Most recent", "sort": {"order": "desc", "field": "postedDate"},
                    "from": offset, "size": size, "jobs": True, "counts": True, "global": True, "siteType": "external",
                    "pageId": "page17-ds", "all_fields": ["country"], "selected_fields": {"country": ["Germany"]},
                    "keywords": site_config.get("search_term", ""), "subsearch": "", "s": "1",
                }
                response = session.post(site_config["api_url"], json=body, timeout=25)
                response.raise_for_status()
                payload = response.json()["eagerLoadRefineSearch"]
                if payload.get("status") != 200:
                    raise ValueError(f"DHL search failed: {payload.get('status')}")
                listings = payload.get("data", {}).get("jobs", [])
                if not listings:
                    break
                fresh = 0
                for raw in listings:
                    job_id = raw["jobSeqNo"]
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    fresh += 1
                    if not german(raw.get("country")) or not candidate(raw.get("title"), site_config) or not recent(raw.get("postedDate"), site_config):
                        continue
                    slug = quote(re.sub(r"\W+", "-", raw["title"]).strip("-"))
                    job = {"id": raw.get("jobId") or job_id, "title": raw["title"],
                           "job_url": f"{site_config['detail_base_url']}/{job_id}/{slug}",
                           "location": raw.get("cityStateCountry") or raw.get("location"), "date_posted": raw.get("postedDate"),
                           "job_type": raw.get("workHours"), "job_level": raw.get("careerLevel"),
                           "job_function": ", ".join(raw.get("multi_category") or [])}
                    results.append(self.normalize_job(job, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                offset += len(listings)
                if not fresh or offset >= payload["totalHits"] or (site_config.get("posted_within_days") is not None and all(parse_date(x.get("postedDate")) for x in listings) and not any(recent(x.get("postedDate"), site_config) for x in listings)):
                    break
                time.sleep(REQUEST_DELAY)
        return results

