import hashlib, os
from scraper.job_rules import DEFAULT_EXCLUDED_KEYWORDS, excluded_keyword, likely_interested
from datetime import datetime, timezone
from sqlalchemy import JSON, Column, Integer, String, Text, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

URL = os.getenv('DATABASE_URL', 'sqlite:///./preview.db')
engine = create_engine(URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if URL.startswith('sqlite') else {})
Session = sessionmaker(engine)
Base = declarative_base()

def now():
    return datetime.now(timezone.utc).isoformat()

class Job(Base):
    __tablename__ = 'jobs'
    key = Column(String(64), primary_key=True)
    data = Column(JSON, nullable=False)
    status = Column(String(80), nullable=False, default='New')
    notes = Column(Text, nullable=False, default='')
    version = Column(Integer, nullable=False, default=1)
    first_seen = Column(String(40), nullable=False)
    last_seen = Column(String(40), nullable=False)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(80), primary_key=True)
    data = Column(JSON, nullable=False)

class Run(Base):
    __tablename__ = 'runs'
    id = Column(Integer, primary_key=True)
    started = Column(String(40), nullable=False)
    finished = Column(String(40))
    status = Column(String(40), nullable=False)
    details = Column(JSON, nullable=False, default=dict)

DEFAULTS = {'statuses': ['New', 'Shortlisted', 'Applied', 'Interview', 'Not interested', 'Not fit'],
            'schedule': {'enabled': True, 'interval_minutes': 30, 'include_ls': False},
            'run_requested': False, 'title_exclusions': DEFAULT_EXCLUDED_KEYWORDS}

def init():
    Base.metadata.create_all(engine)
    with Session.begin() as s:
        for key, data in DEFAULTS.items():
            if s.get(Setting, key) is None:
                s.add(Setting(key=key, data=data))
        s.flush()
        statuses = s.get(Setting, 'statuses')
        if 'Not fit' not in statuses.data:
            statuses.data = [*statuses.data, 'Not fit']

def identity(row):
    source = row.get('source_site') or row.get('company') or ''
    identifier = row.get('id') or row.get('job_url')
    if not identifier:
        identifier = '|'.join(str(row.get(k, '')).strip().casefold() for k in ('company', 'title', 'location'))
    return hashlib.sha256(f'{source}|{identifier}'.encode()).hexdigest()

def ingest(s, rows):
    added = 0
    for row in rows:
        key, stamp = identity(row), now()
        row = dict(row)
        job = s.get(Job, key)
        row['first_scraped_at'] = job.data.get('first_scraped_at') if job else row.get('scraped_at')
        if job:
            job.data, job.last_seen = row, stamp
        else:
            s.add(Job(key=key, data=row, first_seen=stamp, last_seen=stamp))
            added += 1
        s.flush()
    return added

def serialize(job, keywords=()):
    excluded = excluded_keyword(job.data.get('title', ''), keywords)
    return {**job.data, 'key': job.key, 'status': job.status, 'notes': job.notes,
            'version': job.version, 'first_seen': job.first_seen, 'last_seen': job.last_seen,
            'likely_interested': likely_interested(job.data.get('title', ''), keywords),
            'excluded_keyword': excluded}
