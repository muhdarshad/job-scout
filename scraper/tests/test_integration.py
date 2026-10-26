import sys
import threading
from types import SimpleNamespace

import openpyxl
import pandas as pd
import yaml

import job_ranker_v2 as ranker
from src.webscraper import pipeline
from src.webscraper import jobspy_source


def test_portals_overlap_and_results_are_deterministic(tmp_path, monkeypatch):
    barrier = threading.Barrier(2)
    class Platform:
        def fetch_jobs(self, site, max_results=None):
            barrier.wait(timeout=3)
            return [{'title': 'Quality Engineer', 'company': site['company'], 'description': 'Python English',
                     'job_type': 'fulltime', 'location': 'Munich'}]
    monkeypatch.setattr(pipeline, 'get_platform', lambda name: Platform())
    config = tmp_path / 'sites.yaml'
    config.write_text(yaml.safe_dump({'other_sites': [{'company': x, 'platform': 'fake'} for x in ['A', 'B']]}))
    df = pipeline.run_pipeline(config_path=config, workers=2, include_ls=False, enrich=False, progress=False)
    assert df.company.tolist() == ['A', 'B']
    assert df.source.tolist() == ['CS', 'CS']
    assert [r['found'] for r in df.attrs['site_stats']] == [1, 1]


def test_failure_does_not_drop_other_sites(tmp_path, monkeypatch):
    class Platform:
        def fetch_jobs(self, site, max_results=None):
            if site['company'] == 'Bad':
                raise RuntimeError('offline')
            return [{'title': 'Engineer', 'company': 'Good'}]
    monkeypatch.setattr(pipeline, 'get_platform', lambda name: Platform())
    config = tmp_path / 'sites.yaml'
    config.write_text(yaml.safe_dump({'other_sites': [{'company': x, 'platform': 'fake'} for x in ['Bad', 'Good']]}))
    df = pipeline.run_pipeline(config_path=config, include_ls=False, enrich=False, progress=False)
    assert df.company.tolist() == ['Good']
    assert df.attrs['site_stats'][0]['status'] == 'Failed'


def test_ls_keeps_offsets_pauses_and_sources(monkeypatch):
    calls, pauses = [], []
    def scrape(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([{'title': 'Data Analyst', 'company': 'A', 'site': 'linkedin', 'id': 'li-1'}])
    monkeypatch.setitem(sys.modules, 'jobspy', SimpleNamespace(scrape_jobs=scrape))
    monkeypatch.setattr(jobspy_source.time, 'sleep', pauses.append)
    monkeypatch.setattr(jobspy_source.random, 'uniform', lambda a, b: 7)
    config = {'sites': ['linkedin'], 'search_terms': ['Data Analyst'], 'pages_per_term': 2, 'results_per_page': 20}
    df, errors = jobspy_source.fetch_jobspy(config)
    assert [c['offset'] for c in calls] == [0, 20]
    assert all(c['hours_old'] == 8 and c['linkedin_fetch_description'] for c in calls)
    assert pauses == [7, 7] and not errors
    assert df.source.tolist() == ['LS', 'LS']
    assert df.source_site.tolist() == ['linkedin', 'linkedin']


def test_ls_empty_and_error_pause(monkeypatch):
    calls, pauses = [], []
    def scrape(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError('rate limited')
        return pd.DataFrame()
    monkeypatch.setitem(sys.modules, 'jobspy', SimpleNamespace(scrape_jobs=scrape))
    monkeypatch.setattr(jobspy_source.time, 'sleep', pauses.append)
    df, errors = jobspy_source.fetch_jobspy({'sites': ['linkedin'], 'search_terms': ['Data'], 'pages_per_term': 3})
    assert df.empty and len(errors) == 1 and len(pauses) == 1 and len(calls) == 2


def test_combined_rank_serials_dedup_history_and_excel(tmp_path):
    rows = [dict(title='Data Analyst', company='A', source='CS', source_site='CS / A', description='SQL Python English', job_url='https://a'),
            dict(title=' data analyst ', company=' a ', source='LS', source_site='LS / linkedin', description='SQL Python English'),
            dict(title='Quality Engineer', company='B', source='LS', source_site='LS / linkedin', description='English'),
            dict(title='Mechanical Engineer', company='C', source='CS', source_site='CS / C', description='English'),
            dict(title='Senior Engineer', company='D', source='LS', source_site='LS / indeed')]
    csv = tmp_path / 'jobs.csv'
    pd.DataFrame(rows).to_csv(csv, index=False)
    ranked = ranker.rank_dataframe(csv, tmp_path)
    assert len(ranked) == 3
    assert ranked.serial.tolist() == ['CS_01', 'CS_02', 'LS_01']
    output = tmp_path / '01_261009_rankedjobs_germany.xlsx'
    ranker.export_excel(ranked, output)
    ws = openpyxl.load_workbook(output).active
    columns = {cell.value: cell.column_letter for cell in ws[1]}
    assert ws[f"{columns['Link']}2"].value == f'=HYPERLINK({columns["Job URL"]}2,"Link")'
    assert ws[f"{columns['Serial']}2"].value == 'CS_01'
    assert ws[f"{columns['Website']}2"].value == 'CS / A'
    assert ws.column_dimensions[columns['Job Description']].hidden and len(ws.conditional_formatting) == 6
    assert ranker.rank_dataframe(csv, tmp_path).empty


def test_custom_config_passed_to_enrichment(tmp_path, monkeypatch):
    class Platform:
        def fetch_jobs(self, *args, **kwargs):
            return [{'title': 'Engineer', 'company': 'Custom'}]
    seen = []
    monkeypatch.setattr(pipeline, 'get_platform', lambda name: Platform())
    def enrich(df, **kwargs):
        seen.append(kwargs)
        df['description'] = 'English'
        return df
    monkeypatch.setattr(pipeline, 'enrich_descriptions', enrich)
    config = tmp_path / 'sites.yaml'
    config.write_text(yaml.safe_dump({'workday_sites': [{'company': 'Custom', 'tenant': 'custom'}]}))
    pipeline.run_pipeline(config_path=config, include_ls=False, progress=False)
    assert seen[0]['workday_sites'][0]['tenant'] == 'custom'
    assert seen[0]['other_sites'] == []


def test_main_combines_sources_and_reports_counts(tmp_path, monkeypatch, capsys):
    import main
    class Platform:
        def fetch_jobs(self, *args, **kwargs):
            return [{'title': 'Quality Engineer', 'company': 'Portal', 'description': 'English Python'}]
    monkeypatch.setattr(pipeline, 'get_platform', lambda name: Platform())
    monkeypatch.setattr(pipeline, 'fetch_jobspy', lambda *args: (
        pd.DataFrame([{'title': 'Data Analyst', 'company': 'Board', 'description': 'SQL English',
                       'source': 'LS', 'source_site': 'linkedin'}]), []))
    site_config, ls_config = tmp_path / 'sites.yaml', tmp_path / 'ls.yaml'
    site_config.write_text(yaml.safe_dump({'other_sites': [{'company': 'Portal', 'platform': 'fake'}]}))
    ls_config.write_text(yaml.safe_dump({'sites': ['linkedin']}))
    monkeypatch.setattr(sys, 'argv', ['main.py', '--config', str(site_config), '--ls-config', str(ls_config),
                       '--output', str(tmp_path / 'all.csv'), '--ranked-output-dir', str(tmp_path), '--no-progress'])
    main.main()
    wb = openpyxl.load_workbook(next(tmp_path.glob('*rankedjobs_germany.xlsx')))
    serial_column = next(cell.column for cell in wb.active[1] if cell.value == 'Serial')
    serials = {wb.active.cell(i, serial_column).value for i in [2, 3]}
    assert serials == {'LS_01', 'CS_01'}
    text = capsys.readouterr().out
    assert 'Likely' in text and 'TOTAL' in text and 'LS / linkedin' in text
    assert pd.read_csv(tmp_path / 'all.csv').source.tolist() == ['CS', 'LS']


def test_missing_descriptions_do_not_fail_skills():
    from src.webscraper.enrichment.skills import add_skills_column
    df = add_skills_column(pd.DataFrame({'description': [None, float('nan'), 'Python']}))
    assert df.skills.isna().tolist() == [True, True, False]


def test_ls_reports_jobspy_partial_failure(monkeypatch):
    import logging
    def scrape(**kwargs):
        logging.getLogger('JobSpy:LinkedIn').error('429 blocked')
        return pd.DataFrame()
    monkeypatch.setitem(sys.modules, 'jobspy', SimpleNamespace(scrape_jobs=scrape))
    logger = logging.getLogger('JobSpy:LinkedIn')
    before = list(logger.handlers)
    df, errors = jobspy_source.fetch_jobspy({'sites': ['linkedin'], 'search_terms': ['Data']})
    assert df.empty and errors == ['429 blocked']
    assert logger.handlers == before

