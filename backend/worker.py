"""One persistent worker; PostgreSQL advisory lock prevents overlapping processes."""
import json, logging, os, sys, tempfile, time, threading
import yaml
from .tracking import cleanup
from .preferences import ROOT as SCRAPER_ROOT
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, text
from .db import Run, Setting, Session, engine, ingest, init, now

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scraper'))
logging.basicConfig(level=logging.INFO)


def collect(include_ls, report=None):
    from src.webscraper.pipeline import run_pipeline
    from job_ranker_v2 import rank_dataframe
    with Session() as s:
        keywords = s.get(Setting, 'title_exclusions').data
        preferences = s.get(Setting, 'preferences').data
    # Empty per-run history directory disables workbook-based duplicate removal.
    # Database source identity preserves records and user tracking across runs.
    with tempfile.TemporaryDirectory() as directory:
        csv = str(Path(directory) / 'jobs.csv')
        config = yaml.safe_load((SCRAPER_ROOT / 'config/sites.yaml').read_text())
        for group in ('workday_sites', 'other_sites'):
            config[group] = [site for i, site in enumerate(config.get(group, [])) if f"{group}:{site['company']}" in preferences['enabled_sites']]
        ls_config = yaml.safe_load((SCRAPER_ROOT / 'config/jobspy.yaml').read_text())
        ls_config.update(sites=preferences['job_boards'], search_terms=preferences['search_terms'], exclude_reposts=preferences['exclude_linkedin_reposts'])
        config_file, ls_file = Path(directory) / 'sites.yaml', Path(directory) / 'jobspy.yaml'
        config_file.write_text(yaml.safe_dump(config))
        ls_file.write_text(yaml.safe_dump(ls_config))
        frame = run_pipeline(workers=int(os.getenv('SCRAPE_WORKERS', '4')),
            include_ls=include_ls and bool(preferences['job_boards']) and bool(preferences['search_terms']), output_path=csv, progress=False, excluded_keywords=keywords,
            config_path=config_file, ls_config_path=ls_file, report=report, skill_keywords=preferences['skills'])
        if report:
            report('Ranking', 'Scoring jobs', None, None)
        ranked = rank_dataframe(csv, directory, skill_keywords=preferences['skills'])
        if not ranked.empty:
            ranked['matched_skills'] = ranked['matched_skills'].map(sorted)
        rows = json.loads(ranked.to_json(orient='records'))
        if report:
            report('Ranking', 'Complete', 1, 1)
        return rows, frame.attrs.get('site_stats', [])


def run_once(collector=collect):
    with Session.begin() as s:
        schedule = s.get(Setting, 'schedule').data
        s.get(Setting, 'run_requested').data = False
        run = Run(started=now(), status='Running', details={})
        s.add(run)
        s.flush()
        run_id = run.id
    progress, mutex, last_write = {}, threading.Lock(), [0.0]
    def report(name, stage, completed, total):
        with mutex:
            progress[name] = {'name':name, 'stage':stage, 'completed':completed, 'total':total}
            if time.monotonic() - last_write[0] < .5 and stage not in ('Failed', 'Complete') and not stage.startswith('Complete:'):
                return
            with Session.begin() as session:
                active = session.get(Run, run_id)
                active.details = {'progress':list(progress.values()), 'updated_at':now()}
            last_write[0] = time.monotonic()
    try:
        rows, sites = collector(schedule['include_ls'], report=report) if collector is collect else collector(schedule['include_ls'])
        failures = [site for site in sites if site.get('status') != 'Complete']
        with Session.begin() as s:
            added = ingest(s, rows)
            run = s.get(Run, run_id)
            run.status = 'Failed' if sites and len(failures) == len(sites) else 'Partial' if failures else 'Complete'
            run.details = {'added': added, 'total': len(rows), 'sites': sites, 'progress':list(progress.values())}
            run.finished = now()
    except Exception as exc:
        logging.exception('Scrape failed')
        with Session.begin() as s:
            run = s.get(Run, run_id)
            run.status, run.finished = 'Failed', now()
            run.details = {'error': f'{type(exc).__name__}: {exc}', 'progress':list(progress.values())}


def due(schedule, last, requested, current=None):
    if requested:
        return True
    if not schedule['enabled']:
        return False
    if last is None:
        return True
    stamp = datetime.fromisoformat(last.finished or last.started)
    return ((current or datetime.now(timezone.utc)) - stamp).total_seconds() >= schedule['interval_minutes'] * 60


def main():
    init()
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Scheduled worker requires PostgreSQL. SQLite is for preview/tests only.')
    with engine.connect() as lock:
        if not lock.execute(text('SELECT pg_try_advisory_lock(82716421)')).scalar():
            raise RuntimeError('Another Job Scout worker is already running.')
        lock.commit()
        with Session.begin() as s:
            for run in s.scalars(select(Run).where(Run.status == 'Running')):
                run.status, run.finished = 'Interrupted', now()
                run.details = {'error': 'Worker stopped before completing this run.'}
        while True:
            # Keep the lock connection alive and fail closed if it is lost.
            lock.execute(text('SELECT 1'))
            lock.commit()
            with Session.begin() as s:
                cleanup(s)
            with Session() as s:
                schedule = s.get(Setting, 'schedule').data
                requested = s.get(Setting, 'run_requested').data
                last = s.scalar(select(Run).order_by(Run.id.desc()).limit(1))
                should_run = due(schedule, last, requested)
            if should_run:
                run_once()
            time.sleep(5)

if __name__ == '__main__':
    main()
