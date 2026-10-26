"""Serial LS search batches using the user's bundled JobSpy fork."""
import logging
import random
import time

import pandas as pd

from .config import COLUMNS


def fetch_jobspy(config, enrich=True, report=None):
    from jobspy import scrape_jobs

    terms, sites = config['search_terms'], config['sites']
    pages, size = config.get('pages_per_term', 2), config.get('results_per_page', 20)
    low, high = config.get('pause_seconds', [5, 12])
    if not 0 <= low <= high or pages < 1 or size < 1:
        raise ValueError('Invalid LS pagination or pause configuration')
    frames, errors = [], []
    class ErrorCollector(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())
    handler = ErrorCollector()
    loggers = [logging.getLogger(f"JobSpy:{'LinkedIn' if site == 'linkedin' else site.capitalize()}") for site in sites]
    for logger in loggers:
        logger.addHandler(handler)
    total, completed = len(terms) * pages, 0
    try:
        for term in terms:
            for page in range(pages):
                if report:
                    report(completed, total, f'{term}: page {page + 1}')
                empty = False
                try:
                    jobs = scrape_jobs(
                        site_name=sites, search_term=term,
                        google_search_term=f"{term} jobs in {config.get('location', 'Germany')} since last {config.get('google_days', 3)} days",
                        location=config.get('location', 'Germany'), results_wanted=size, offset=page * size,
                        hours_old=config.get('hours_old', 8), country_indeed=config.get('country_indeed', 'Germany'),
                        linkedin_fetch_description=enrich, verbose=0,
                    )
                    empty = jobs.empty
                    if not empty:
                        jobs = jobs.copy()
                        jobs['search_term'], jobs['source'] = term, 'LS'
                        jobs['source_site'] = jobs['site'].astype(str).str.lower()
                        frames.append(jobs.reindex(columns=COLUMNS + ['source', 'source_site']))
                except Exception as exc:
                    errors.append(f'{term}, page {page + 1}: {type(exc).__name__}: {exc}')
                completed += 1
                # Retain the notebook's pause after calls, including failures.
                if not empty:
                    if report:
                        report(completed, total, 'Waiting between search batches')
                    time.sleep(random.uniform(low, high))
                else:
                    completed += pages - page - 1
                    break
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
    if report:
        report(total, total, 'Complete')
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS + ['source', 'source_site'])
    return df, errors

