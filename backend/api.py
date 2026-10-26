import io, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
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
        return {'jobs': [serialize(j) for j in s.scalars(select(Job))],
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
            if body.old in ('New', 'Not interested') or body.old not in values:
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
    columns = ['title', 'company', 'location', 'total_score', 'experience_required', 'german_required', 'status', 'notes', 'job_url', 'first_seen', 'last_seen']
    sheet.append(columns)
    with Session() as s:
        for job in s.scalars(select(Job)):
            row = serialize(job)
            values = [row.get(k, '') for k in columns]
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
