"""N3 Engine Overhaul Services' rexx career portal."""

import re
import time
from xml.etree import ElementTree

from ..config import REQUEST_DELAY
from .career import CareerPlatform, candidate, career_session, german, recent


class N3Platform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen = [], set()
        with career_session() as session:
            response = session.get(site_config["feed_url"], timeout=25)
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = entry.findtext("a:title", "", ns)
                link = entry.find("a:link", ns)
                url = link.get("href") if link is not None else None
                if not url or url in seen or not candidate(title, site_config):
                    continue
                seen.add(url)
                try:
                    detail = self.fetch_job_detail(url, site_config, session)
                except Exception as exc:
                    print(f"    ! N3 detail failed for {url}: {exc}")
                    continue
                # Atom 'updated' is not the original posting date.
                if not any(german(c) for c in detail.get("_countries", [])) or not recent(detail.get("date_posted"), site_config):
                    continue
                category = entry.find("a:category", ns)
                detail.update(id=re.search(r"-j(\d+)\.html", url).group(1), job_url=url,
                              job_function=category.get("term") if category is not None else None)
                results.append(self.normalize_job(detail, site_config))
                if max_results is not None and len(results) >= max_results:
                    break
                time.sleep(REQUEST_DELAY)
        return results

