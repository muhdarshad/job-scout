"""Concurrent company portals plus a separately paced LS worker."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone
from job_rules import excluded_keyword

import pandas as pd
import yaml

from .config import COLUMNS, load_sites_config
from .platforms import get_platform
from .utils.filtering import EXCLUDED_TITLES, EXCLUDED_SENIORITY, EXCLUDED_TITLE_PATTERN
from .enrichment import enrich_descriptions, add_skills_column
from .jobspy_source import fetch_jobspy
from .terminal import ScrapeDisplay


def filter_titles_before_enrichment(df, excluded_keywords=()):
    if 'title' not in df:
        return df
    keep = ~df['title'].fillna('').astype(str).str.contains(EXCLUDED_TITLE_PATTERN, na=False)
    keep &= ~df['title'].fillna('').map(lambda title: bool(excluded_keyword(title, excluded_keywords)))
    return df.loc[keep].reset_index(drop=True)


def run_pipeline(max_results_per_site=None, enrich=True, extract_skills=True, output_path=None,
                 config_path=None, workers=4, include_ls=False, ls_config_path=None, progress=True, excluded_keywords=(), report=None, skill_keywords=None):
    if workers < 1 or max_results_per_site is not None and max_results_per_site < 1:
        raise ValueError('Workers and result limits must be positive')
    config = load_sites_config(config_path)
    workday, other = config.get('workday_sites', []), config.get('other_sites', [])
    sites = [(s, 'workday') for s in workday] + [(s, s.get('platform')) for s in other]
    ls_path = ls_config_path or Path(__file__).resolve().parents[2] / 'config/jobspy.yaml'
    ls_config = yaml.safe_load(Path(ls_path).read_text()) if include_ls else {}
    stats, frames = [], []

    with ScrapeDisplay(progress, report) as display:
        def fetch_site(site, platform_name, task):
            name = f"CS / {site['company']}"
            stat = dict(source_site=name, found=0, after_titles=0, status='Complete', errors=[])
            try:
                display.update(task, 'Fetching listings')
                registered = get_platform(platform_name)
                if registered is None:
                    raise ValueError(f'Unknown platform: {platform_name}')
                # Independent adapter state for every portal worker.
                platform = type(registered)()
                limit = max_results_per_site if max_results_per_site is not None else site.get('max_results')
                rows = platform.fetch_jobs(site, max_results=limit)
                df = pd.DataFrame(rows, columns=COLUMNS)
                stat['found'] = len(df)
                df['scraped_at'] = datetime.now(timezone.utc).isoformat()
                df = filter_titles_before_enrichment(df, excluded_keywords)
                stat['after_titles'] = len(df)
                df['source'], df['source_site'] = 'CS', name
                if enrich and not df.empty:
                    display.update(task, 'Enriching descriptions')
                    df = enrich_descriptions(df, workday_sites=workday, other_sites=other,
                        progress_callback=lambda done, total: display.update(task, 'Enriching descriptions', done, total))
                if extract_skills and not df.empty:
                    df = add_skills_column(df, skill_keywords)
                display.update(task, f'Complete: {len(df)} jobs', 1, 1)
                return df, [stat]
            except Exception as exc:
                stat['status'] = 'Failed'
                stat['errors'].append(f'{type(exc).__name__}: {exc}')
                display.update(task, 'Failed', 1, 1)
                return pd.DataFrame(columns=COLUMNS + ['source', 'source_site']), [stat]

        def fetch_ls(task):
            names = [f'LS / {s}' for s in ls_config['sites']]
            try:
                raw, errors = fetch_jobspy(ls_config, enrich, lambda done, total, stage: display.update(task, stage, done, total))
                raw['source_site'] = 'LS / ' + raw['source_site']
                raw['scraped_at'] = datetime.now(timezone.utc).isoformat()
                df = filter_titles_before_enrichment(raw, excluded_keywords)
                if extract_skills and not df.empty:
                    df = add_skills_column(df, skill_keywords)
                rows = [dict(source_site=name, found=int((raw.source_site == name).sum()),
                             after_titles=int((df.source_site == name).sum()),
                             status='Partial / check logs' if errors else 'Complete', errors=errors if i == 0 else [])
                        for i, name in enumerate(names)]
                return df, rows
            except Exception as exc:
                display.update(task, 'Failed', 1, 1)
                return pd.DataFrame(columns=COLUMNS + ['source', 'source_site']), [
                    dict(source_site=name, found=0, after_titles=0, status='Failed',
                         errors=[f'{type(exc).__name__}: {exc}'] if i == 0 else []) for i, name in enumerate(names)]

        # LS starts immediately and has its own worker so portal queues do not delay it.
        with ThreadPoolExecutor(max_workers=workers) as portals, ThreadPoolExecutor(max_workers=1) as ls:
            futures = [portals.submit(fetch_site, site, platform, display.add(site['company'])) for site, platform in sites]
            if include_ls and ls_config.get('enabled', True):
                futures.append(ls.submit(fetch_ls, display.add('LS / job boards')))
            # Collect in submission order to make cross-source duplicate precedence stable.
            for future in futures:
                frame, counts = future.result()
                frames.append(frame)
                stats.extend(counts)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS + ['source', 'source_site'])
    df.attrs['site_stats'] = stats
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
    return df

