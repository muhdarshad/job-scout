import io, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from .db import Job, Run, Setting, Session, init, serialize

@asynccontextmanager
async def lifespan(app):
    init()
    if os.getenv('DEMO_MODE') == '1':
        from .seed import seed
        seed()
    yield

app = FastAPI(title='Job Scout', lifespan=lifespan)

@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        # Vite forwards the original Host; Docker serves the app on the API origin.
        from urllib.parse import urlsplit
        if urlsplit(origin).netloc != request.headers.get('host'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Cross-origin writes are not allowed'}, status_code=403)
    return await call_next(request)

@app.get('/api/health')
def health():
    with Session() as s:
        s.execute(select(Setting.key).limit(1))
    return {'ok': True}

@app.get('/api/state')
def state():
    with Session() as s:
        runs = s.scalars(select(Run).order_by(Run.id.desc()).limit(20)).all()
        keywords = s.get(Setting, 'title_exclusions').data
        return {'jobs': [serialize(j, keywords) for j in s.scalars(select(Job))],
                'title_exclusions': keywords,
                'statuses': s.get(Setting, 'statuses').data, 'schedule': s.get(Setting, 'schedule').data,
                'requested': s.get(Setting, 'run_requested').data, 'demo': os.getenv('DEMO_MODE') == '1',
                'runs': [{'id': r.id, 'started': r.started, 'finished': r.finished, 'status': r.status, 'details': r.details} for r in runs]}

class JobEdit(BaseModel):
    status: str = Field(min_length=1, max_length=80)
    notes: str = Field(max_length=20000)
    version: int

@app.patch('/api/jobs/{key}')
def edit(key: str, body: JobEdit):
    with Session.begin() as s:
        if body.status not in s.get(Setting, 'statuses').data:
            raise HTTPException(400, 'Unknown status')
        result = s.execute(update(Job).where(Job.key == key, Job.version == body.version).values(
            status=body.status, notes=body.notes, version=body.version + 1))
        if not result.rowcount:
            raise HTTPException(409, 'Job changed in another window. Reload and retry.')
        return serialize(s.get(Job, key))

class BulkJob(BaseModel):
    key: str = Field(min_length=64, max_length=64)
    version: int = Field(ge=1)

class BulkStatusEdit(BaseModel):
    jobs: list[BulkJob] = Field(min_length=1, max_length=1000)
    status: str = Field(min_length=1, max_length=80)

@app.post('/api/jobs/bulk-status')
def bulk_status(body: BulkStatusEdit):
    if len({job.key for job in body.jobs}) != len(body.jobs):
        raise HTTPException(400, 'Duplicate job selection')
    # One transaction: a stale/missing row rolls back the entire batch.
    with Session.begin() as s:
        if body.status not in s.get(Setting, 'statuses', with_for_update=True).data:
            raise HTTPException(400, 'Unknown status')
        for job in sorted(body.jobs, key=lambda item: item.key):
            changed = s.execute(update(Job).where(Job.key == job.key, Job.version == job.version)
                .values(status=body.status, version=Job.version + 1))
            if not changed.rowcount:
                raise HTTPException(409, 'Some selected jobs changed. Reload, reselect and retry; no jobs were updated.')
    return {'updated': len(body.jobs)}

class ExclusionsEdit(BaseModel):
    keywords: list[str] = Field(max_length=200)

    @field_validator('keywords')
    @classmethod
    def clean(cls, words):
        cleaned = []
        for word in words:
            word = word.strip()
            if not 2 <= len(word) <= 80:
                raise ValueError('Each keyword must contain 2–80 characters.')
            if word.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(word)
        return cleaned

@app.put('/api/title-exclusions')
def title_exclusions(body: ExclusionsEdit):
    with Session.begin() as s:
        s.get(Setting, 'title_exclusions').data = body.keywords
    return body

class StatusEdit(BaseModel):
    old: str | None = None
    name: str = Field(min_length=1, max_length=80)

@app.post('/api/statuses')
def statuses(body: StatusEdit):
    name = body.name.strip()
    with Session.begin() as s:
        setting = s.get(Setting, 'statuses', with_for_update=True)
        values = list(setting.data)
        if not name or name in values or len(values) >= 20 and not body.old:
            raise HTTPException(400, 'Use a unique status name (maximum 20 statuses).')
        if body.old:
            if body.old in ('New', 'Not interested', 'Not fit') or body.old not in values:
                raise HTTPException(400, 'This status cannot be renamed.')
            values[values.index(body.old)] = name
            s.execute(update(Job).where(Job.status == body.old).values(status=name, version=Job.version + 1))
        else:
            values.append(name)
        setting.data = values
        return values

class ScheduleEdit(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=30, le=1440)
    include_ls: bool

@app.put('/api/schedule')
def schedule(body: ScheduleEdit):
    with Session.begin() as s:
        s.get(Setting, 'schedule').data = body.model_dump()
    return body

@app.post('/api/scrape')
def scrape():
    if os.getenv('DEMO_MODE') == '1':
        raise HTTPException(400, 'Live scraping is disabled in the demo preview. Run Docker locally to scrape.')
    with Session.begin() as s:
        s.get(Setting, 'run_requested').data = True
    return {'queued': True}

@app.get('/api/export')
def export():
    import openpyxl
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Jobs'
    columns = ['title', 'company', 'location', 'total_score', 'experience_required', 'german_required', 'status', 'notes', 'job_url', 'first_seen', 'last_seen', 'scraped_at', 'first_scraped_at', 'likely_interested', 'excluded_keyword', 'description']
    with Session() as s:
        keywords = s.get(Setting, 'title_exclusions').data
        rows = [serialize(job, keywords) for job in s.scalars(select(Job))]
        # Excel cells hold at most 32,767 characters; retain long descriptions in continuations.
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        for row in rows:
            row['description'] = ILLEGAL_CHARACTERS_RE.sub('', row.get('description') or '')
        parts = max([1, *((len(row['description']) + 32766) // 32767 for row in rows)])
        columns += [f'description_continued_{part}' for part in range(2, parts + 1)]
        sheet.append(columns)
        for row in rows:
            description = row['description']
            for part in range(1, parts + 1):
                name = 'description' if part == 1 else f'description_continued_{part}'
                row[name] = description[(part - 1) * 32767:part * 32767]
            values = [row.get(k, '') for k in columns]
            values = [ILLEGAL_CHARACTERS_RE.sub('', value) if isinstance(value, str) else value for value in values]
            sheet.append(values)
            # Scraped text must never become an executable spreadsheet formula.
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    data = io.BytesIO()
    workbook.save(data)
    data.seek(0)
    return StreamingResponse(data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="job-scout.xlsx"'})

if Path('dist/client').exists():
    app.mount('/', StaticFiles(directory='dist/client', html=True), name='web')
