"""MTU's public, complete HTML job inventory and JobPosting details."""

import time

from bs4 import BeautifulSoup

from .career import CareerPlatform, candidate, career_session, german, recent
from ..config import REQUEST_DELAY


class MTUPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen = [], set()
        with career_session() as session:
            response = session.get(site_config['search_url'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            if not soup.select_one('#jobs-list'):
                raise ValueError('MTU job inventory missing')
            for tile in soup.select('.jobs-list__item'):
                link = tile.select_one('a.jobs-list__item_anchor')
                title = tile.get('data-title', '')
                job_id = tile.get('data-job-id', '').split('-')[0]
                if not link or job_id in seen or not candidate(title, site_config):
                    continue
                seen.add(job_id)
                # The inventory includes international roles; _ger is the source location code.
                if not tile.get('data-location', '').endswith('_ger'):
                    continue
                detail = self.fetch_job_detail(link['href'], site_config, session)
                time.sleep(REQUEST_DELAY)
                if not any(german(c) for c in detail.get('_countries', [])) or not recent(detail.get('date_posted'), site_config):
                    continue
                detail.update(id=job_id, job_url=link['href'], title=title,
                              job_function=tile.get('data-category'), job_level=tile.get('data-target-group'))
                results.append(self.normalize_job(detail, site_config))
                if max_results is not None and len(results) >= max_results:
                    break
        return results

