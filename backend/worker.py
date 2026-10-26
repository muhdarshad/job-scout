"""One persistent worker; PostgreSQL advisory lock prevents overlapping processes."""
import json, logging, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, text
from .db import Run, Setting, Session, engine, ingest, init, now

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scraper'))
logging.basicConfig(level=logging.INFO)


def collect(include_ls):
    from src.webscraper.pipeline import run_pipeline
    from job_ranker_v2 import rank_dataframe
    with Session() as s:
        keywords = s.get(Setting, 'title_exclusions').data
    # Empty per-run history directory disables workbook-based duplicate removal.
    # Database source identity preserves records and user tracking across runs.
    with tempfile.TemporaryDirectory() as directory:
        csv = str(Path(directory) / 'jobs.csv')
        frame = run_pipeline(workers=int(os.getenv('SCRAPE_WORKERS', '4')),
            include_ls=include_ls, output_path=csv, progress=False, excluded_keywords=keywords)
        ranked = rank_dataframe(csv, directory)
        if not ranked.empty:
            ranked['matched_skills'] = ranked['matched_skills'].map(sorted)
        rows = json.loads(ranked.to_json(orient='records'))
        return rows, frame.attrs.get('site_stats', [])


def run_once(collector=collect):
    with Session.begin() as s:
        schedule = s.get(Setting, 'schedule').data
        s.get(Setting, 'run_requested').data = False
        run = Run(started=now(), status='Running', details={})
        s.add(run)
        s.flush()
        run_id = run.id
    try:
        rows, sites = collector(schedule['include_ls'])
        failures = [site for site in sites if site.get('status') != 'Complete']
        with Session.begin() as s:
            added = ingest(s, rows)
            run = s.get(Run, run_id)
            run.status = 'Failed' if sites and len(failures) == len(sites) else 'Partial' if failures else 'Complete'
            run.details = {'added': added, 'total': len(rows), 'sites': sites}
            run.finished = now()
    except Exception as exc:
        logging.exception('Scrape failed')
        with Session.begin() as s:
            run = s.get(Run, run_id)
            run.status, run.finished = 'Failed', now()
            run.details = {'error': f'{type(exc).__name__}: {exc}'}


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
