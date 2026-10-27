import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['DEMO_MODE'] = '0'
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend import db
# Shared in-memory connection across API request threads.
db.engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
db.Session.configure(bind=db.engine)
from backend.api import app
from backend.worker import due, run_once
from datetime import datetime, timezone, timedelta
import pytest

@pytest.fixture
def client():
    db.Base.metadata.drop_all(db.engine)
    with TestClient(app) as client:
        yield client

def sample(**extra):
    return {'id':'123','source_site':'CS / test','title':'Engineer','company':'Test','location':'Munich','total_score':70, **extra}

def test_refresh_preserves_tracking_and_identity(client):
    with db.Session.begin() as s:
        db.ingest(s,[sample()])
    job=client.get('/api/state').json()['jobs'][0]
    result=client.patch('/api/jobs/'+job['key'],json={'status':'Applied','notes':'Interview Monday','version':1})
    assert result.status_code==200
    with db.Session.begin() as s:
        assert db.ingest(s,[sample(title='Updated title',total_score=75)])==0
    updated=client.get('/api/state').json()['jobs'][0]
    assert (updated['status'],updated['notes'],updated['total_score'])==('Applied','Interview Monday',75)
    assert client.patch('/api/jobs/'+job['key'],json={'status':'New','notes':'stale','version':1}).status_code==409

def test_custom_status_rename_moves_jobs(client):
    assert client.post('/api/statuses',json={'name':'Offer'}).status_code==200
    with db.Session.begin() as s:
        db.ingest(s,[sample()])
    job=client.get('/api/state').json()['jobs'][0]
    client.patch('/api/jobs/'+job['key'],json={'status':'Offer','notes':'','version':1})
    assert client.post('/api/statuses',json={'old':'Offer','name':'Offer received'}).status_code==200
    assert client.get('/api/state').json()['jobs'][0]['status']=='Offer received'
    assert client.post('/api/statuses',json={'old':'New','name':'Inbox'}).status_code==400

def test_export_text_not_formula(client):
    import io, openpyxl
    with db.Session.begin() as s:
        db.ingest(s,[sample(title='=1+1')])
    workbook=openpyxl.load_workbook(io.BytesIO(client.post('/api/export', json={'keys':[j['key'] for j in client.get('/api/state').json()['jobs']]}).content))
    assert workbook.active['A2'].data_type=='s'
    assert workbook.active['A2'].value=='=1+1'

def test_schedule_and_failure(client):
    assert client.put('/api/schedule',json={'enabled':True,'interval_minutes':1,'include_ls':False}).status_code==422
    stamp=datetime.now(timezone.utc)
    run=db.Run(started=(stamp-timedelta(minutes=31)).isoformat(),finished=stamp.isoformat(),status='Complete')
    settings={'enabled':True,'interval_minutes':30}
    assert not due(settings,run,False,stamp)
    assert due(settings,run,True,stamp)
    assert not due({'enabled':False},None,False)
    run_once(lambda include: (_ for _ in ()).throw(RuntimeError('Test failure')))
    assert client.get('/api/state').json()['runs'][0]['status']=='Failed'

def test_partial_run_and_distinct_source_ids(client):
    run_once(lambda include: ([sample(),sample(id='456')],[{'source_site':'a','status':'Complete'},{'source_site':'b','status':'Failed'}]))
    data=client.get('/api/state').json()
    assert len(data['jobs'])==2
    assert data['runs'][0]['status']=='Partial'

def test_cross_origin_write_blocked(client):
    assert client.post('/api/scrape',headers={'Origin':'https://elsewhere.example'}).status_code==403


def test_bulk_status_is_atomic_and_preserves_notes(client):
    with db.Session.begin() as s:
        db.ingest(s, [sample(id='a'), sample(id='b')])
        for job in s.scalars(select(db.Job)):
            job.notes = 'Keep these notes'
    jobs = client.get('/api/state').json()['jobs']
    payload = {'status':'Not fit', 'jobs':[{'key':j['key'], 'version':j['version']} for j in jobs]}
    payload['jobs'][1]['version'] = 99
    assert client.post('/api/jobs/bulk-status', json=payload).status_code == 409
    assert all(j['status'] == 'New' and j['version'] == 1 for j in client.get('/api/state').json()['jobs'])
    payload['jobs'][1]['version'] = 1
    assert client.post('/api/jobs/bulk-status', json=payload).json() == {'updated':2}
    updated = client.get('/api/state').json()['jobs']
    assert all(j['status'] == 'Not fit' and j['notes'] == 'Keep these notes' for j in updated)
    assert client.post('/api/jobs/bulk-status', json={'status':'Missing', 'jobs':payload['jobs']}).status_code == 400
    assert client.post('/api/jobs/bulk-status', json={'status':'New', 'jobs':[]}).status_code == 422
    duplicate = {'key':jobs[0]['key'], 'version':2}
    assert client.post('/api/jobs/bulk-status', json={'status':'New', 'jobs':[duplicate,duplicate]}).status_code == 400

def test_upgrade_adds_not_fit_without_resetting_preferences(client):
    with db.Session.begin() as s:
        s.get(db.Setting, 'statuses').data = ['New', 'My custom stage', 'Not interested']
        s.get(db.Setting, 'schedule').data = {'enabled':False, 'interval_minutes':120, 'include_ls':True}
    db.init()
    db.init()
    state = client.get('/api/state').json()
    assert state['statuses'] == ['New', 'My custom stage', 'Not interested', 'Not fit']
    assert state['schedule']['interval_minutes'] == 120
    assert client.post('/api/statuses',json={'old':'Not fit','name':'Other'}).status_code == 400

def test_exclusion_settings_are_reversible_and_title_only(client):
    with db.Session.begin() as s:
        db.ingest(s, [sample(title='Postbote (m/w/d)'), sample(id='other', title='Mechanical Engineer', description='Develop tools for Postboten')])
    jobs = client.get('/api/state').json()['jobs']
    assert next(j for j in jobs if j['id']=='123')['excluded_keyword'] == 'postbote'
    engineer = next(j for j in jobs if j['id']=='other')
    assert not engineer['excluded_keyword'] and engineer['likely_interested']
    assert client.put('/api/title-exclusions', json={'keywords':[' mechanical ', 'MECHANICAL']}).status_code == 200
    state = client.get('/api/state').json()
    assert state['title_exclusions'] == ['mechanical']
    assert not next(j for j in state['jobs'] if j['id']=='other')['likely_interested']
    assert client.put('/api/title-exclusions', json={'keywords':[]}).status_code == 200
    assert all(not j['excluded_keyword'] for j in client.get('/api/state').json()['jobs'])
    assert client.put('/api/title-exclusions', json={'keywords':['x']}).status_code == 422

def test_scrape_times_remain_distinct_from_database_times(client):
    first = '2026-10-20T10:00:00+00:00'
    second = '2026-10-20T11:00:00+00:00'
    with db.Session.begin() as s:
        db.ingest(s, [sample(scraped_at=first)])
    job = client.get('/api/state').json()['jobs'][0]
    with db.Session.begin() as s:
        db.ingest(s, [sample(scraped_at=second)])
    updated = client.get('/api/state').json()['jobs'][0]
    assert updated['first_seen'] == job['first_seen']
    assert updated['first_scraped_at'] == first and updated['scraped_at'] == second
    assert updated['first_seen'] != first

def test_legacy_jobs_do_not_get_invented_scrape_times(client):
    with db.Session.begin() as s:
        db.ingest(s, [sample()])
        db.ingest(s, [sample(scraped_at='2026-10-26T11:00:00+00:00')])
    job = client.get('/api/state').json()['jobs'][0]
    assert job['first_scraped_at'] is None
    assert job['scraped_at'] == '2026-10-26T11:00:00+00:00'

def test_export_includes_multiline_description_as_safe_text(client):
    import io, openpyxl
    description = '=SUM(A1:A2)\nPython and SQL\nGerman: B2\x00'
    with db.Session.begin() as s:
        db.ingest(s, [sample(description=description)])
    response = client.post('/api/export', json={'keys':[j['key'] for j in client.get('/api/state').json()['jobs']]})
    assert response.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    headers = [cell.value for cell in sheet[1]]
    cell = sheet.cell(2, headers.index('description') + 1)
    assert cell.value == description.replace('\x00', '')
    assert cell.data_type == 's'

def test_export_preserves_descriptions_over_excel_cell_limit(client):
    import io, openpyxl
    description = 'Python SQL\n' * 4000
    with db.Session.begin() as s:
        db.ingest(s, [sample(description=description)])
    sheet = openpyxl.load_workbook(io.BytesIO(client.post('/api/export', json={'keys':[j['key'] for j in client.get('/api/state').json()['jobs']]}).content)).active
    headers = [cell.value for cell in sheet[1]]
    chunks = [sheet.cell(2, i + 1).value or '' for i, name in enumerate(headers) if name.startswith('description')]
    assert ''.join(chunks) == description
    assert all(len(chunk) <= 32767 for chunk in chunks)

def test_export_only_selected_and_filename(client):
    import io, openpyxl
    with db.Session.begin() as s:
        db.ingest(s, [sample(id='one', title='First job'), sample(id='two', title='Second job')])
    jobs = client.get('/api/state').json()['jobs']
    payload = {'keys':[jobs[1]['key']], 'filename':'jobscope_1345_271026.xlsx'}
    response = client.post('/api/export', json=payload)
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet.max_row == 2
    assert sheet['A2'].value == jobs[1]['title']
    assert 'jobscope_1345_271026.xlsx' in response.headers['content-disposition']
    assert client.get('/api/export').status_code == 405
    assert client.post('/api/export', json={'keys':[]}).status_code == 422
    assert client.post('/api/export', json={'keys':['f' * 64]}).status_code == 409
    assert client.post('/api/export', json={**payload, 'filename':'../bad.xlsx'}).status_code == 422
    assert client.post('/api/export', json={'keys':[jobs[1]['key']] * 2}).status_code == 422

def test_description_blocks_preserve_structure_and_remove_active_markup(client):
    from backend.presentation import description_blocks
    blocks = description_blocks('<h2>Requirements</h2><p>Python &amp; SQL</p><ul><li>First skill</li><li>Second skill</li></ul><script>alert(1)</script><p>Apply now</p>')
    assert blocks == [{'kind':'heading','text':'Requirements'}, {'kind':'paragraph','text':'Python & SQL'}, {'kind':'list','items':['First skill','Second skill']}, {'kind':'paragraph','text':'Apply now'}]
    assert description_blocks('Your tasks:\n\n- Analysis\n- Reporting\n\nContact us') == [{'kind':'heading','text':'Your tasks:'},{'kind':'list','items':['Analysis','Reporting']},{'kind':'paragraph','text':'Contact us'}]
    assert description_blocks(None) == []
    with db.Session.begin() as s:
        db.ingest(s, [sample(description='<p>First paragraph</p><p>Second paragraph</p>')])
    job = client.get('/api/state').json()['jobs'][0]
    assert len(job['description_blocks']) == 2
    assert job['first_seen']
