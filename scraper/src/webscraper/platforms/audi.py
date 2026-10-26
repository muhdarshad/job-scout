"""Audi's public SAP OData service, including its location hierarchy."""

import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from .career import CareerPlatform, candidate, career_session, german, recent
from ..utils import strip_html


class AudiPlatform(CareerPlatform):
    def _read(self, session, config, resource):
        response = session.get(config['api_url'].rstrip('/') + '/' + resource, params={
            'sap-client': '200', 'sap-language': 'EN', '$format': 'json',
            **({'$expand': 'Location,HierarchyLevel,ContractType,FunctionalArea,Company'} if resource.startswith('JobSet') else {}),
        }, timeout=30)
        response.raise_for_status()
        return response.json()['d']

    @staticmethod
    def _publication(value):
        match = re.fullmatch(r'/Date\((\d+)(?:[+-]\d+)?\)/', str(value or ''))
        return datetime.fromtimestamp(int(match[1]) / 1000, timezone.utc).date().isoformat() if match else None

    @staticmethod
    def _german_location(location_id, locations):
        seen = set()
        while location_id in locations and location_id not in seen:
            seen.add(location_id)
            location = locations[location_id]
            if german(location.get('Text')):
                return True
            location_id = location.get('ParentLocationID')
        return False

    def fetch_jobs(self, site_config, max_results=None):
        results, seen, continuations = [], set(), set()
        with career_session() as session:
            locations = {r['LocationID']: r for r in self._read(session, site_config, 'LocationSet')['results']}
            data = self._read(session, site_config, 'JobSet')
            while True:
                for raw in data['results']:
                    job_id, title = raw['JobID'], raw.get('Title')
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    if not self._german_location(raw.get('Location', {}).get('LocationID'), locations) or not candidate(title, site_config):
                        continue
                    posted = self._publication(raw.get('ZPublicationDate'))
                    if not recent(posted, site_config):
                        continue
                    job = self._normalize(raw, site_config)
                    job.update(date_posted=posted)
                    results.append(job)
                    if max_results is not None and len(results) >= max_results:
                        return results
                next_url = data.get('__next')
                if not next_url:
                    break
                if next_url in continuations:
                    raise ValueError('Audi returned a repeated OData continuation')
                continuations.add(next_url)
                # SAP emits internal hostnames in metadata; keep pagination on the public service.
                query = parse_qs(urlparse(next_url).query)
                token = query.get('$skiptoken', query.get('$skip'))
                if not token:
                    raise ValueError('Unsupported Audi OData continuation')
                resource = 'JobSet?' + urlparse(next_url).query
                response = session.get(site_config['api_url'].rstrip('/') + '/' + resource, timeout=30)
                response.raise_for_status()
                data = response.json()['d']
        return results

    def _normalize(self, raw, config):
        return self.normalize_job({
            'id': raw['JobID'], 'title': raw.get('Title'),
            'job_url': 'https://careers.audi.com/desktop.html?jobId=' + raw['JobID'],
            'location': raw.get('Location', {}).get('Text'),
            'date_posted': self._publication(raw.get('ZPublicationDate')),
            'job_type': raw.get('ContractType', {}).get('Text'),
            'job_level': raw.get('HierarchyLevel', {}).get('Text'),
            'job_function': raw.get('FunctionalArea', {}).get('Text'),
            'description': strip_html('\n\n'.join(raw.get(k) or '' for k in (
                'CompanyDesc', 'DepartmentDesc', 'ProjectDesc', 'TaskDesc', 'AdditionalInfo', 'Contact', 'EEOText'))),
        }, config)

    def fetch_job_detail(self, job_url, site_config, session=None):
        job_id = parse_qs(urlparse(job_url).query)['jobId'][0]
        if not re.fullmatch('[A-Fa-f0-9]+', job_id):
            raise ValueError('Invalid Audi job ID')
        if session is not None:
            return self._normalize(self._read(session, site_config, "JobSet('" + job_id + "')"), site_config)
        with career_session() as client:
            return self._normalize(self._read(client, site_config, "JobSet('" + job_id + "')"), site_config)

