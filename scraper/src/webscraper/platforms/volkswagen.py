"""Volkswagen Group's public SuccessFactors table, sorted by publication date."""

import re
import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .career import CareerPlatform, candidate, career_session, recent, text
from ..config import REQUEST_DELAY


class VolkswagenPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        with career_session() as session:
            while True:
                response = session.get(site_config['search_url'], params={
                    'locale': 'en_US', 'q': site_config.get('search_term', ''), 'optionsFacetsDD_country': 'DE',
                    'startrow': offset, 'sortColumn': 'referencedate', 'sortDirection': 'desc', 'd': 0,
                }, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                if not soup.select_one('#searchresults'):
                    raise ValueError('Volkswagen search table missing')
                rows = soup.select('tr.data-row')
                fresh = 0
                for row in rows:
                    link = row.select_one('a.jobTitle-link')
                    if not link:
                        continue
                    url = urljoin(response.url, link['href'])
                    if url in seen:
                        continue
                    seen.add(url)
                    fresh += 1
                    title, location = link.get_text(' ', strip=True), text(row, '.colLocation .jobLocation')
                    posted = text(row, '.colDate .jobDate')
                    try:
                        posted = datetime.strptime(posted, '%b %d, %Y').date().isoformat()
                    except (ValueError, TypeError):
                        posted = None
                    if not re.search(r'(?:^|,)\s*DE(?:\s*,|$)', location or '') or not candidate(title, site_config) or not recent(posted, site_config):
                        continue
                    results.append(self.normalize_job({
                        'id': url.rstrip('/').split('/')[-1], 'job_url': url, 'title': title,
                        'location': location, 'date_posted': posted, 'job_function': text(row, '.jobDepartment'),
                    }, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                if not fresh:
                    break
                offset += len(rows)
                time.sleep(REQUEST_DELAY)
        return results

    def fetch_job_detail(self, job_url, site_config=None, session=None):
        detail = super().fetch_job_detail(job_url, site_config, session)
        # RMK emits synthetic midnight clock times for date-only publications.
        detail['posted_at'] = None
        return detail

