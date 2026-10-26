"""Emirates Group's own public listings and detail API."""

from datetime import datetime, timezone
from html import unescape

from .career import CareerPlatform, candidate, career_session, recent
from ..utils import strip_html


class EmiratesPlatform(CareerPlatform):
    def _normalize(self, raw, config):
        posted = raw.get('postingdate')
        # The API supplies a publication date encoded as epoch milliseconds.
        posted = datetime.fromtimestamp(posted / 1000, timezone.utc).date().isoformat() if isinstance(posted, (int, float)) else None
        return self.normalize_job({
            'id': raw['reqid'], 'title': unescape(raw.get('title') or ''),
            'job_url': 'https://www.emiratesgroupcareers.com/search-and-apply/' + str(raw['reqid']) + '/',
            'location': ', '.join(dict.fromkeys(x for x in (raw.get('city'), raw.get('state'), raw.get('country')) if x)),
            'date_posted': posted, 'description': strip_html(raw.get('jobdescription')),
            'job_function': ', '.join(raw.get('categoryList') or []) or raw.get('category'),
        }, config)

    def fetch_jobs(self, site_config, max_results=None):
        results, seen = [], set()
        with career_session() as session:
            response = session.get(site_config['api_url'], params={
                'title': site_config.get('search_term', ''), 'brand': '', 'category': '',
                'location': '', 'jobcategory': '', 'showAll': 'true',
            }, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('status') != 'success' or not isinstance(data.get('data'), list):
                raise ValueError('Emirates returned an invalid job inventory')
            for raw in data['data']:
                if raw.get('country') not in site_config['countries'] or not candidate(unescape(raw.get('title') or ''), site_config):
                    continue
                job = self._normalize(raw, site_config)
                if job['id'] in seen or not recent(job['date_posted'], site_config):
                    continue
                seen.add(job['id'])
                results.append(job)
                if max_results is not None and len(results) >= max_results:
                    break
        return results

    def fetch_job_detail(self, job_url, site_config):
        job_id = job_url.rstrip('/').split('/')[-1]
        with career_session() as session:
            response = session.get(site_config['api_url'].rstrip('/') + '/' + job_id, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('status') != 'success' or not isinstance(data.get('data'), dict):
                raise ValueError('Emirates returned an invalid job detail')
            return self._normalize(data['data'], site_config)

