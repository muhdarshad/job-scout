"""Liebherr job-list API with live country and aerospace facility facets."""

import json
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .career import CareerPlatform, candidate, career_session, german, recent
from ..config import REQUEST_DELAY


class LiebherrPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, page = [], set(), 0
        with career_session() as session:
            response = session.get(site_config['search_url'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            node = soup.select_one('#__NEXT_DATA__')
            if not node:
                raise ValueError('Liebherr job bootstrap missing')
            bootstrap = json.loads(node.string)['props']['pageProps']['hydrationData']['jlpData']
            facets = {f['facetId']: f['values'] for g in bootstrap['facetGroups'] for f in g['facets']}
            countries = [str(v['id']) for v in facets['country'] if german(v['text'])]
            facilities = [str(v['id']) for v in facets['facility'] if 'liebherr-aerospace' in v['text'].casefold()
                          or 'liebherr aerospace' in v['text'].casefold()]
            if not countries or not facilities:
                raise ValueError('Liebherr Germany/aerospace facets missing')
            while True:
                response = session.get(site_config['api_url'].rstrip('/') + f'/{page}/100', params={
                    'detailPageId': bootstrap['detailPageId'], 'filter': ';'.join(countries + facilities),
                    'term': site_config.get('search_term', ''), 'jobcountry': '',
                }, timeout=30)
                response.raise_for_status()
                data = response.json()
                fresh = 0
                for raw in data['jobs']:
                    job_id = str(raw['jobId'])
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    fresh += 1
                    company = raw.get('company', {}).get('name', '').casefold()
                    if 'aerospace' not in company or not candidate(raw.get('title'), site_config):
                        continue
                    url = urljoin(site_config['search_url'], raw['jobDetailPageUrl'])
                    detail = self.fetch_job_detail(url, site_config, session)
                    time.sleep(REQUEST_DELAY)
                    if not any(german(c) for c in detail.get('_countries', [])) or not recent(detail.get('date_posted'), site_config):
                        continue
                    # JSON-LD's identifier differs from the portal's public job ID.
                    detail.update(id=job_id, job_url=url, job_function=raw.get('workArea', {}).get('label'))
                    results.append(self.normalize_job(detail, site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                page += 1
                if not fresh or page * 100 >= data['total']:
                    break
                time.sleep(REQUEST_DELAY)
        return results

