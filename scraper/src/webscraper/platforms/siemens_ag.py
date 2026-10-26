"""Siemens AG's Avature portal, separate from Siemens Energy."""

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, parse_date, recent, text


class SiemensAGPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        with career_session() as session:
            while True:
                params = {"42386": f"[{site_config.get('country_id', '812132')}]", "42386_format": "17546",
                          "listFilterMode": 1, "folderRecordsPerPage": 6, "folderOffset": offset,
                          "folderSort": "postedDate", "folderSortDirection": "DESC", "search": site_config.get("search_term", "")}
                response = session.get(site_config["search_url"].rstrip("/") + "/", params=params, timeout=25)
                response.raise_for_status()
                articles = BeautifulSoup(response.text, "html.parser").select("article.article--result")
                fresh = 0
                for article in articles:
                    link = article.select_one('a[href*="/JobDetail/"]')
                    if not link:
                        continue
                    url = urljoin(response.url, link["href"])
                    if url in seen:
                        continue
                    seen.add(url)
                    fresh += 1
                    if not candidate(link.get_text(" ", strip=True), site_config):
                        continue
                    try:
                        detail = self.fetch_job_detail(url, site_config, session)
                    except Exception as exc:
                        print(f"    ! Siemens AG detail failed for {url}: {exc}")
                        continue
                    if not detail.pop("_germany", False) or not recent(detail.get("date_posted"), site_config):
                        continue
                    detail.update(job_url=url)
                    results.append(self.normalize_job(detail, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                # An excluded or old page must not terminate pagination.
                if not fresh:
                    break
                offset += len(articles)
                time.sleep(REQUEST_DELAY)
        return results

    def fetch_job_detail(self, job_url, site_config=None, session=None):
        client = session or career_session()
        try:
            response = client.get(job_url, timeout=25)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            fields = {}
            for field in soup.select(".article__content__view__field"):
                label = text(field, ".article__content__view__field__label")
                value = text(field, ".article__content__view__field__value")
                if label and value:
                    fields[label.rstrip(":")] = value
            locations = fields.get("Location(s)", "")
            posted = parse_date(fields.get("Posted since"))
            return {
                "id": fields.get("Job ID") or job_url.rstrip("/").split("/")[-1],
                "title": text(soup, "h3") or text(soup, "h1"),
                "location": locations, "date_posted": posted.isoformat() if posted else None,
                "job_type": fields.get("Job type"), "job_level": fields.get("Experience level"),
                "job_function": fields.get("Field of work"),
                "description": text(soup, "#section1__content .article__content__view__field__value"),
                "_germany": bool(re.search(r"(?:^|[-,;])\s*(?:Germany|Deutschland|DE)\b", locations, re.I)),
            }
        finally:
            if session is None:
                client.close()

