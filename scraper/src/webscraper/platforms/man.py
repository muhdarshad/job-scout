"""MAN's public SuccessFactors job search in German and English."""

import logging
import time
from datetime import datetime
from html import unescape
from urllib.parse import quote

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .career import CareerPlatform, candidate, career_session, recent, text
from ..config import REQUEST_DELAY


# The portal exposes city labels, not country codes. Fail closed for new labels.
# These German facilities were verified against the live inventory in October 2026.
GERMAN_LOCATIONS = frozenset('''Aachen|Aalen|Altenkirchen|Amberg|Ampfing|Ansbach|Arnsberg|Aschaffenburg|Augsburg-Gersthofen
Bad Kreuznach|Bad Neustadt|Balingen|Bamberg|Bautzen|Bayreuth|Berlin-Freiheit|Berlin-Lichtenberg|Berlin-Spandau|Berlin-Tempelhof
Bielefeld|Bitburg|Bochum|Bonn-St.Augusti|Brandenburg|Braunschweig|Bühl-Vimbuch|Cham|Chemnitz|Dillenburg|Donauwörth|Dortmund
Dresden-Kaditz|Dresden-Nickern|Duisburg|Düsseldorf|Eisenach|Erfurt|Essen|Euskirchen|Flensburg|Frankfurt|Frechen|Freiburg|Fulda|Fürstenwalde
Garmisch|Gera|Gerolstein|Giessen|Großheubach|Gärtringen|Göppingen|Göttingen|Hagen|Halle|Hamburg-Moorfleet|Hamburg-Stellingen
Hanau|Hannover-Laatzen|Hannover-Langenhagen|Heilbronn|Hildesheim|Hirschberg|Ingolstadt|Itzehoe|Kaiserslautern|Karlsruhe|Kassel
Kempten|Kiel|Kirchheim(HE)|Kirn|Koblenz|Krauchenwies|Krefeld|Köln-Mülheim|Landau|Landshut|Lauchringen|Leipzig|Limburg
Ludwigshafen|Lübeck|Magdeburg|Mainz|Marburg|Memmingen|München|München-Karlsfeld|München-Lochham|München-Neufahrn|Münster
Mönchengladbach|Neckarelz|Neu-Ulm|Neuenstein|Neumarkt/Opf.|Nürnberg|Nürnberg-Großgründlach|Offenbach|Offenburg|Oldenburg|Osnabrück|Paderborn-Mönkeloh
Pforzheim|Pilsting|Quickborn|Regensburg|Remscheid|Reutlingen|Rheine|Rosenheim|Saarbrücken|Saarlouis|Salzgitter|Schwarzenbek
Rostock|Sangerhausen|Schweinfurt|Schwerin|Siegen|Singen|Stralsund|Stuttgart|Trier|Villingen|Weiden|Weil am Rhein|Weiterstadt|Wesel|Wiesbaden|Wildau|Winterbach|Wittlich|Würzburg'''.replace('\n', '|').split('|'))
GERMAN_COMPANIES = {'MAN Truck & Bus D GmbH', 'MAN Truck & Bus SE', 'TRATON R&D Germany GmbH'}


class MANPlatform(CareerPlatform):
    @staticmethod
    def _publication(value, locale):
        try:
            return datetime.strptime(value, '%d.%m.%y' if locale == 'de_DE' else '%m/%d/%y').date().isoformat()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _location(raw, config):
        locations = raw.get('filter7') or []
        if not locations:
            locations = [city for city in GERMAN_LOCATIONS if (raw.get('unifiedStandardTitle') or '').endswith('Standort ' + city)]
        companies = raw.get('division_obj') or []
        # A Dubai vacancy is labelled München by this portal; its overseas employer takes precedence.
        if companies and not all(c in GERMAN_COMPANIES for c in companies):
            return None
        allowed = GERMAN_LOCATIONS | set(config.get('germany_locations', []))
        if not locations or not all(city in allowed for city in locations):
            logging.getLogger(__name__).warning('MAN: skipping unverified location %s for job %s', locations, raw.get('id'))
            return None
        return '; '.join(locations) + ', Germany'

    def fetch_jobs(self, site_config, max_results=None):
        results, accepted = [], set()
        with career_session() as session:
            # This POST only searches public postings; transient failures can be retried safely.
            session.mount(site_config['api_url'], HTTPAdapter(max_retries=Retry(
                total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods={'POST'},
            )))
            for locale in ('de_DE', 'en_US'):
                page, seen = 0, set()
                while True:
                    response = session.post(site_config['api_url'], json={
                        'keywords': site_config.get('search_term', ''), 'locale': locale, 'location': '',
                        'pageNumber': page, 'sortBy': 'date', 'facetFilters': {}, 'brand': '', 'skills': [], 'categoryId': 0,
                    }, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    if 'error' in data:
                        raise ValueError('MAN job search error: ' + str(data['error']))
                    rows = [item['response'] for item in data['jobSearchResult']]
                    fresh = 0
                    for raw in rows:
                        job_id, title = str(raw['id']), unescape(raw.get('unifiedStandardTitle') or '')
                        if job_id in seen:
                            continue
                        seen.add(job_id)
                        fresh += 1
                        posted = self._publication(raw.get('unifiedStandardStart'), locale)
                        if job_id in accepted or not candidate(title, site_config) or not recent(posted, site_config):
                            continue
                        location = self._location(raw, site_config)
                        if not location:
                            continue
                        slug = raw.get('unifiedUrlTitle') or quote(title, safe='')
                        job = {'id': job_id, 'title': title, 'date_posted': posted, 'location': location,
                               'job_url': 'https://jobs.man.eu/job/' + slug + '/' + job_id + '-' + locale,
                               'job_level': ', '.join(raw.get('filter6') or []), 'job_function': ', '.join(raw.get('filter1') or [])}
                        accepted.add(job_id)
                        results.append(self.normalize_job(job, site_config))
                        if max_results is not None and len(results) >= max_results:
                            return results
                    page += 1
                    # Ten jobs per page; unlike the older widget's 25-job assumption.
                    if not fresh or page * 10 >= data['totalJobs']:
                        break
                    if site_config.get('posted_within_days') is not None and all(
                        self._publication(r.get('unifiedStandardStart'), locale) and
                        not recent(self._publication(r.get('unifiedStandardStart'), locale), site_config) for r in rows
                    ):
                        break
                    time.sleep(REQUEST_DELAY)
        return results

    def fetch_job_detail(self, job_url, site_config):
        with career_session() as session:
            response = session.get(job_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            shell = soup.select_one('.jobDisplayShell')
            if not shell:
                raise ValueError('MAN job description missing')
            blocks = [node.get_text(' ', strip=True) for node in shell.select('.joblayouttoken .rtltextaligneligible')]
            return {'description': '\n\n'.join(dict.fromkeys(blocks)) or text(shell, '[itemprop="description"]')}

