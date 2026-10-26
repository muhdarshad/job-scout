"""Public SmartRecruiters postings API used by Etihad Airways."""

import time

from .career import CareerPlatform, candidate, career_session, parse_timestamp, recent
from ..config import REQUEST_DELAY
from ..utils import strip_html


class SmartRecruitersPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        with career_session() as session:
            while True:
                response = session.get(site_config['api_url'], params={'limit': 100, 'offset': offset}, timeout=30)
                response.raise_for_status()
                data = response.json()
                rows = data['content']
                fresh = 0
                for raw in rows:
                    job_id = str(raw['id'])
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    fresh += 1
                    if raw.get('location', {}).get('country', '').upper() not in site_config['country_codes']:
                        continue
                    if not candidate(raw.get('name'), site_config) or not recent(raw.get('releasedDate'), site_config):
                        continue
                    job = self._normalize(raw, site_config)
                    results.append(job)
                    if max_results is not None and len(results) >= max_results:
                        return results
                offset += len(rows)
                if not fresh or offset >= data['totalFound']:
                    break
                time.sleep(REQUEST_DELAY)
        return results

    def _normalize(self, raw, config):
        sections = raw.get('jobAd', {}).get('sections', {})
        return self.normalize_job({
            'id': raw['id'], 'title': raw.get('name'),
            'job_url': 'https://jobs.smartrecruiters.com/' + config['tenant'] + '/' + str(raw['id']),
            'location': raw.get('location', {}).get('fullLocation') or raw.get('location', {}).get('city'),
            'date_posted': raw.get('releasedDate'), 'posted_at': parse_timestamp(raw.get('releasedDate')),
            'description': strip_html('\n\n'.join(s.get('text') or '' for s in sections.values() if isinstance(s, dict))),
            'job_type': raw.get('typeOfEmployment', {}).get('label'),
            'job_level': raw.get('experienceLevel', {}).get('label'),
            'job_function': raw.get('function', {}).get('label'),
        }, config)

    def fetch_job_detail(self, job_url, site_config):
        job_id = job_url.rstrip('/').split('/')[-1].split('-')[0]
        with career_session() as session:
            response = session.get(site_config['api_url'].rstrip('/') + '/' + job_id, timeout=30)
            response.raise_for_status()
            return self._normalize(response.json(), site_config)

