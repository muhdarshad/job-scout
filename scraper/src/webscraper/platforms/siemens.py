"""Siemens Energy platform scraper."""

import logging
import re
import time
import requests
from datetime import date, timedelta
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import REQUEST_DELAY
from ..utils import strip_html, first_item


SIEMENS_BASE_URL = "https://jobs.siemens-energy.com"
SIEMENS_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "referer": "https://jobs.siemens-energy.com/",
}


class SiemensEnergyPlatform:
    """Scraper for Siemens Energy career site."""

    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        """Paginate through Siemens Energy job listings."""
        company = site_config["company"]
        search_url = site_config["search_url"]
        search_term = site_config.get("search_term", "")
        country_filter = site_config.get("country_filter")
        posted_within_days = site_config.get("posted_within_days")

        cutoff_date = None
        if posted_within_days:
            cutoff_date = date.today() - timedelta(days=posted_within_days)

        results = []
        offset = 0
        page_size = 20
        seen_ids = set()

        # Use a session for cookie persistence and sort state
        session = requests.Session()
        session.headers.update(SIEMENS_HEADERS)

        while True:
            page_url = f"{search_url}/?folderRecordsPerPage={page_size}&folderOffset={offset}"
            if country_filter:
                page_url += f"&29454={country_filter}&29454_format=11381&listFilterMode=1"
            if search_term:
                page_url += f"&keyword={requests.utils.quote(search_term)}"

            # Add sort by Posted Date descending
            page_url += "&folderSort=schemaField_3_146_3&folderSortDirection=DESC"

            try:
                resp = session.get(page_url, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"  [{company}] Failed to fetch page at offset {offset}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article")

            page_jobs = 0
            for article in articles:
                job_data = self._extract_listing_job(article)
                if job_data:
                    job_id = job_data.get("id")
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)

                        # Fetch detail page for this job
                        detail = self.fetch_job_detail(job_data["job_url"], session)
                        
                        # Merge listing data with detail data
                        merged_job = self._merge_job_data(job_data, detail, site_config)

                        # Date filtering
                        if cutoff_date and merged_job.get("date_posted"):
                            try:
                                job_date = date.fromisoformat(merged_job["date_posted"])
                                if job_date < cutoff_date:
                                    continue
                            except (ValueError, TypeError):
                                # Exclude jobs with missing/invalid dates when filter is active
                                continue
                        elif cutoff_date and not merged_job.get("date_posted"):
                            # Exclude jobs with no date when filter is active
                            continue

                        results.append(merged_job)
                        page_jobs += 1

            logging.getLogger(__name__).info(f"  [{company}] fetched {len(results)} jobs (page offset {offset})")

            if max_results and len(results) >= max_results:
                results = results[:max_results]
                break

            if page_jobs == 0:
                break

            offset += page_size
            time.sleep(REQUEST_DELAY)

        return results

    def _extract_listing_job(self, article) -> dict[str, Any] | None:
        """Extract basic job info from a listing page article element."""
        link = article.select_one("a.article__header__focusable")
        if not link:
            return None

        title = link.get_text(strip=True)
        job_url = link.get("href", "")
        if job_url:
            job_url = urljoin(SIEMENS_BASE_URL, job_url)

        content_div = article.select_one(".article__content[data-job-id]")
        job_id = content_div.get("data-job-id") if content_div else None

        if not job_id:
            match = re.search(r"/(\d+)$", job_url)
            if match:
                job_id = match.group(1)

        if not job_id:
            return None

        return {
            "id": job_id,
            "job_url": job_url,
            "title": title,
        }

    def _merge_job_data(self, listing_data: dict, detail_data: dict, site_config: dict[str, Any]) -> dict[str, Any]:
        """Merge listing data with detail data, preferring detail data where available."""
        search_term = site_config.get("search_term", "")
        
        return {
            "id": detail_data.get("id") or listing_data.get("id"),
            "job_url": listing_data.get("job_url"),
            "title": detail_data.get("title") or listing_data.get("title"),
            "company": detail_data.get("company") or "Siemens Energy",
            "location": detail_data.get("location"),
            "date_posted": detail_data.get("date_posted"),
            "job_type": detail_data.get("job_type"),
            "job_level": detail_data.get("job_level"),
            "job_function": detail_data.get("job_function"),
            "description": detail_data.get("description"),
            "company_industry": detail_data.get("company_industry"),
            "skills": None,
            "search_term": search_term,
        }

    def normalize_job(self, raw_job: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        """Map a raw Siemens job to the canonical schema (used when no detail fetch)."""
        company = site_config["company"]
        search_term = site_config.get("search_term", "")

        return {
            "id": raw_job.get("id"),
            "job_url": raw_job.get("job_url"),
            "title": raw_job.get("title"),
            "company": "Siemens Energy",
            "location": None,
            "date_posted": None,
            "job_type": None,
            "job_level": None,
            "job_function": None,
            "description": None,
            "company_industry": None,
            "skills": None,
            "search_term": search_term,
        }

    def fetch_job_detail(self, job_url: str, session: requests.Session | None = None) -> dict[str, Any]:
        """Fetch and parse full job detail page."""
        # Use provided session or create a new one for backward compatibility
        use_session = session or requests.Session()
        if not session:
            use_session.headers.update(SIEMENS_HEADERS)

        try:
            resp = use_session.get(job_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"    ! Siemens detail fetch failed for {job_url}: {e}")
            return {
                "id": None,
                "title": None,
                "company": None,
                "location": None,
                "date_posted": None,
                "job_type": None,
                "job_level": None,
                "job_function": None,
                "description": None,
                "company_industry": None,
            }

        soup = BeautifulSoup(resp.text, "html.parser")

        fields = self._extract_metadata_fields(soup)

        job_id = fields.get("Job ID")
        if not job_id:
            match = re.search(r"/(\d+)$", job_url)
            job_id = match.group(1) if match else None

        title = self._extract_title(soup, fields)
        company = fields.get("Company") or "Siemens Energy"
        location = self._normalize_location(fields)
        date_posted = self._extract_date_posted(soup, fields)
        job_type = fields.get("Full / Part time")
        job_level = fields.get("Experience Level")
        description = self._extract_description(soup)
        company_industry = fields.get("Organization")

        return {
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "date_posted": date_posted,
            "job_type": job_type,
            "job_level": job_level,
            "job_function": None,
            "description": description,
            "company_industry": company_industry,
        }

    def _extract_metadata_fields(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract label/value pairs from job detail metadata section."""
        fields = {}

        field_containers = soup.select(".article__content__view__field")
        for container in field_containers:
            label_el = container.select_one(".article__content__view__field__label")
            value_el = container.select_one(".article__content__view__field__value")
            if label_el and value_el:
                label = label_el.get_text(strip=True).rstrip(":")
                value = value_el.get_text(strip=True)
                if label and value:
                    fields[label] = value

        generic_fields = soup.find_all(string=re.compile(r"^\s*\w+\s*:"))
        for text_node in generic_fields:
            parent = text_node.parent
            if parent:
                full_text = parent.get_text(strip=True)
                if ":" in full_text:
                    label, value = full_text.split(":", 1)
                    label = label.strip()
                    value = value.strip()
                    if label and value and label not in fields:
                        fields[label] = value

        location_parts = []
        location_fields = soup.select(".article__content__view__field.posting-location .article__content__view__field__value")
        for loc_field in location_fields:
            val = loc_field.get_text(strip=True)
            if val:
                location_parts.append(val)

        if location_parts:
            fields["_location_parts"] = location_parts

        return fields

    def _extract_title(self, soup: BeautifulSoup, fields: dict[str, str]) -> str | None:
        """Extract job title from detail page."""
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        h3 = soup.select_one("article h3")
        if h3:
            return h3.get_text(strip=True)

        return None

    def _normalize_location(self, fields: dict[str, str]) -> str | None:
        """Normalize location components to city, region, country format."""
        location_parts = fields.get("_location_parts", [])

        if not location_parts:
            for key in ["City", "State", "Region", "Country", "Location"]:
                for field_key, value in fields.items():
                    if field_key.lower() == key.lower():
                        location_parts.append(value)
                        break

        if not location_parts:
            return None

        seen = set()
        unique_parts = []
        for part in location_parts:
            if part and part not in seen:
                seen.add(part)
                unique_parts.append(part)

        unique_parts.reverse()

        return ", ".join(unique_parts) if unique_parts else None

    def _extract_date_posted(self, soup: BeautifulSoup, fields: dict[str, str]) -> str | None:
        """Extract and normalize date_posted from meta Description tag."""
        meta_desc = soup.select_one('meta[name="Description"]')
        if meta_desc:
            content = meta_desc.get("content", "")
            match = re.search(r"created\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", content)
            if match:
                date_str = match.group(1)
                try:
                    from datetime import datetime
                    parsed = datetime.strptime(date_str, "%d-%b-%Y")
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    return date_str

        return None

    def _extract_description(self, soup: BeautifulSoup) -> str | None:
        """Extract job description from detail page."""
        article = soup.select_one("article:has(h3:-soup-contains('About the Role'))")
        if not article:
            articles = soup.select("article")
            for a in articles:
                h3 = a.select_one("h3")
                if h3 and "About the Role" in h3.get_text():
                    article = a
                    break

        if not article:
            main = soup.select_one("main")
            if main:
                return strip_html(str(main))
            return None

        return strip_html(str(article))

