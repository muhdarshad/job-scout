"""Diehl Aviation's public HTML search endpoint and job descriptions."""

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .career import CareerPlatform, candidate, career_session, recent, text
from ..config import REQUEST_DELAY


class DiehlPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, page = [], set(), 1
        with career_session() as session:
            while True:
                response = session.get(site_config['api_url'], params={
                    'd': '4', 'co[]': 'DE', 'sort': 'date_desc', 'p': page, 'q': site_config.get('search_term', ''),
                }, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                if not soup.select_one('#search-results'):
                    raise ValueError('Diehl search results missing')
                fresh = 0
                for tile in soup.select('a[href*="/vacancies/"]'):
                    url = urljoin(site_config['api_url'], tile['href'])
                    if url in seen:
                        continue
                    seen.add(url)
                    fresh += 1
                    title, posted = text(tile, 'h3'), text(tile, '.date')
                    if text(tile, '.tag') != 'Diehl Aviation' or not candidate(title, site_config) or not recent(posted, site_config):
                        continue
                    results.append(self.normalize_job({
                        'id': url.rstrip('/').split('/')[-1], 'job_url': url, 'title': title,
                        'date_posted': posted, 'location': text(tile, '.city'), 'job_function': text(tile, '.function'),
                    }, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                pages = [int(m[1]) for a in soup.select('a[hx-get]') if (m := re.search(r'[?&]p=(\d+)', a['hx-get']))]
                if not fresh or page >= max(pages, default=page):
                    break
                page += 1
                time.sleep(REQUEST_DELAY)
        return results

    def fetch_job_detail(self, job_url, site_config):
        with career_session() as session:
            response = session.get(job_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            fields = {text(li, 'strong'): text(li, 'span') for li in soup.select('.details-container aside li')}
            return {'description': text(soup, '.details-container .main-75'),
                    'job_type': ', '.join(filter(None, (fields.get('Working time model'), fields.get('Employment type')))),
                    'job_level': fields.get('Experience level'), 'job_function': fields.get('Function area')}

