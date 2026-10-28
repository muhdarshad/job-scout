"""Atomic status assignments, one-step undo and archive retention."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, String, JSON, select, delete
from fastapi import HTTPException
from .db import Base, Job, Setting, now

ARCHIVED = ('Not interested', 'Not fit')

class ArchiveClock(Base):
    __tablename__ = 'archive_clocks'
    key = Column(String(64), primary_key=True)
    entered = Column(String(40), nullable=False)

class PurgedJob(Base):
    __tablename__ = 'purged_jobs'
    key = Column(String(64), primary_key=True)


def archive_clock(s, key, status, entered=None):
    clock = s.get(ArchiveClock, key)
    if status in ARCHIVED:
        if clock:
            clock.entered = entered or now()
        else:
            s.add(ArchiveClock(key=key, entered=entered or now()))
    elif clock:
        s.delete(clock)


def assign(s, selections, status, notes=None):
    statuses = s.get(Setting, 'statuses', with_for_update=True).data
    if status not in statuses:
        raise HTTPException(400, 'Unknown status')
    changes = []
    for item in sorted(selections, key=lambda item:item.key):
        job = s.get(Job, item.key, with_for_update=True)
        if not job or job.version != item.version:
            raise HTTPException(409, 'Some selected jobs changed. Reload and retry; no jobs were updated.')
        if job.status != status:
            clock = s.get(ArchiveClock, job.key)
            changes.append({'key':job.key, 'before':job.status, 'after':status, 'version':job.version + 1, 'entered':clock.entered if clock else None})
            archive_clock(s, job.key, status)
        job.status, job.version = status, job.version + 1
        if notes is not None:
            job.notes = notes
    if changes:
        s.get(Setting, 'last_assignment').data = changes
    s.flush()
    return len(selections)


def undo(s):
    statuses = s.get(Setting, 'statuses', with_for_update=True).data
    history = s.get(Setting, 'last_assignment')
    if not history.data:
        raise HTTPException(409, 'No assignment to undo.')
    for change in history.data:
        job = s.get(Job, change['key'], with_for_update=True)
        if not job or job.version != change['version'] or job.status != change['after'] or change['before'] not in statuses:
            raise HTTPException(409, 'Jobs changed since the assignment; undo would overwrite newer changes.')
        job.status, job.version = change['before'], job.version + 1
        archive_clock(s, job.key, job.status, change.get('entered'))
    count = len(history.data)
    history.data = []
    return count


def cleanup(s, current=None):
    s.get(Setting, 'statuses', with_for_update=True)
    if not s.get(Setting, 'preferences').data.get('cleanup_archived', True):
        return 0
    cutoff = ((current or datetime.now(timezone.utc)) - timedelta(hours=24)).isoformat()
    expired = s.scalars(select(ArchiveClock).where(ArchiveClock.entered <= cutoff)).all()
    removed = set()
    for clock in expired:
        job = s.get(Job, clock.key, with_for_update=True)
        if job and job.status in ARCHIVED:
            if not s.get(PurgedJob, job.key):
                s.add(PurgedJob(key=job.key))
            removed.add(job.key)
            s.delete(job)
        s.delete(clock)
    history = s.get(Setting, 'last_assignment')
    if any(item['key'] in removed for item in history.data):
        history.data = []
    return len(removed)
