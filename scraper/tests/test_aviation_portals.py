"""Regression cases based on public portal schemas observed on 2026-10-15.

Fixtures retain response structure with short synthetic job text.
"""

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from src.webscraper.config import COLUMNS, OTHER_SITES, WORKDAY_SITES
from src.webscraper.enrichment.description import enrich_descriptions
from src.webscraper.platforms import get_platform
from src.webscraper.platforms.audi import AudiPlatform
from src.webscraper.platforms.man import MANPlatform


DATA = json.loads((Path(__file__).parent / 'fixtures/aviation_portals.json').read_text())
TODAY = date.today().isoformat()


def config(name, days=None):
    return {**next(s for s in OTHER_SITES if s['platform'] == name), 'posted_within_days': days}


def response(payload=None, html=''):
    r = Mock(text=html, url='https://jobs.volkswagen-group.com/search/')
    r.json.return_value = payload
    return r


def client(monkeypatch, module, pages, method='get'):
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    getattr(session, method).side_effect = pages
    monkeypatch.setattr('src.webscraper.platforms.' + module + '.career_session', lambda: session)
    monkeypatch.setattr('time.sleep', lambda _: None)
    return session


def test_all_nine_sources_and_country_scopes():
    names = ('mtu', 'audi', 'liebherr', 'man', 'volkswagen', 'diehl', 'smartrecruiters', 'emirates')
    assert all(get_platform(n) for n in names)
    assert len([s for s in WORKDAY_SITES if s['company'] == 'KION Group']) == 1
    for name in names:
        assert len([s for s in OTHER_SITES if s['platform'] == name]) == 1
    assert config('smartrecruiters')['country_codes'] == ['DE', 'AE']
    assert config('emirates')['countries'] == ['Germany', 'United Arab Emirates']


def test_audi_country_comes_from_hierarchy_not_language_or_city_substring(monkeypatch):
    raw = copy.deepcopy(DATA['audi_job'])
    foreign = {**raw, 'JobID': 'FOREIGN', 'Location': {'LocationID': 99}}
    raw['ZPublicationDate'] = '/Date(' + str(int(datetime.now(timezone.utc).timestamp() * 1000)) + ')/'
    client(monkeypatch, 'audi', [response({'d': {'results': DATA['audi_locations']}}),
                               response({'d': {'results': [foreign, raw]}})])
    jobs = get_platform('audi').fetch_jobs(config('audi', 1), 1)
    assert [j['id'] for j in jobs] == [raw['JobID']]
    assert jobs[0]['date_posted'] == TODAY and jobs[0]['posted_at'] is None
    assert not AudiPlatform._german_location(99, {99: {'ParentLocationID': 99}})


def test_audi_missing_publication_date_is_not_replaced_by_posting_age(monkeypatch):
    raw = {**DATA['audi_job'], 'ZPublicationDate': None, 'PostingAge': 0}
    client(monkeypatch, 'audi', [response({'d': {'results': DATA['audi_locations']}}),
                               response({'d': {'results': [raw]}})])
    assert get_platform('audi').fetch_jobs(config('audi', 1)) == []


def test_audi_detail_keeps_description_sections(monkeypatch):
    client(monkeypatch, 'audi', [response({'d': DATA['audi_detail']})])
    job = get_platform('audi').fetch_job_detail('https://careers.audi.com/desktop.html?jobId=ABC123', config('audi'))
    assert 'digital production' in job['description']
    assert job['date_posted'] is None and job['posted_at'] is None


def test_mtu_uses_listing_id_and_detail_publication_and_german_country(monkeypatch):
    client(monkeypatch, 'mtu', [response(html=DATA['html']['mtu'])])
    detail = Mock(return_value={'_countries': ['DE'], 'date_posted': TODAY, 'posted_at': None, 'description': 'Repair engines'})
    monkeypatch.setattr(get_platform('mtu'), 'fetch_job_detail', detail)
    jobs = get_platform('mtu').fetch_jobs(config('mtu', 1), 1)
    assert jobs[0]['id'] == '1809' and jobs[0]['date_posted'] == TODAY
    assert set(jobs[0]) == set(COLUMNS)


def test_mtu_rejects_foreign_locations_before_details(monkeypatch):
    html = DATA['html']['mtu'].replace('münchen_ger', 'delta_can')
    client(monkeypatch, 'mtu', [response(html=html)])
    detail = Mock()
    monkeypatch.setattr(get_platform('mtu'), 'fetch_job_detail', detail)
    assert get_platform('mtu').fetch_jobs(config('mtu')) == []
    detail.assert_not_called()


def test_liebherr_resolves_facets_and_keeps_public_job_id(monkeypatch):
    facets = [{'facets': [{'facetId': 'country', 'values': [{'id': 1, 'text': 'Germany'}]},
                         {'facetId': 'facility', 'values': [{'id': 2, 'text': 'Liebherr-Aerospace Lindenberg GmbH'}]}]}]
    bootstrap = {'props': {'pageProps': {'hydrationData': {'jlpData': {'facetGroups': facets, 'detailPageId': 3364214}}}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(bootstrap) + '</script>'
    raw = DATA['liebherr_job']
    session = client(monkeypatch, 'liebherr', [response(html=html), response({'jobs': [raw], 'total': 1})])
    monkeypatch.setattr(get_platform('liebherr'), 'fetch_job_detail', Mock(return_value={
        'id': 'DIFFERENT_INTERNAL_ID', '_countries': ['DE'], 'date_posted': TODAY, 'description': 'Repair aircraft'}))
    jobs = get_platform('liebherr').fetch_jobs(config('liebherr', 1), 1)
    assert jobs[0]['id'] == raw['jobId']
    assert session.get.call_args.kwargs['params']['filter'] == '1;2'


def test_diehl_filters_before_limit_and_requests_aviation_in_germany(monkeypatch):
    html = DATA['html']['diehl']
    foreign = html.replace('Diehl Aviation', 'Diehl Defence').replace('/vacancies/engineer', '/vacancies/defence')
    session = client(monkeypatch, 'diehl', [response(html=foreign + html)])
    jobs = get_platform('diehl').fetch_jobs(config('diehl'), 1)
    assert len(jobs) == 1 and jobs[0]['company'] == 'Diehl Aviation'
    assert session.get.call_args.kwargs['params']['co[]'] == 'DE'
    assert session.get.call_args.kwargs['params']['d'] == '4'


def test_diehl_detail_includes_tasks_and_qualifications(monkeypatch):
    client(monkeypatch, 'diehl', [response(html=DATA['html']['diehl_detail'])])
    detail = get_platform('diehl').fetch_job_detail('https://new.diehl.com/job', config('diehl'))
    assert 'Tasks' in detail['description'] and 'Qualifications' in detail['description']
    assert 'date_posted' not in detail


def test_volkswagen_paginates_past_foreign_and_excluded_titles(monkeypatch):
    html = DATA['html']['volkswagen']
    rejected = html.replace('Production Engineer', 'Senior Engineer')
    foreign = html.replace('DE, 38440', 'US, 38440')
    # Each page has a distinct URL so the repeated-page guard cannot hide the filtering behavior.
    session = client(monkeypatch, 'volkswagen', [response(html=rejected.replace('/123/', '/1/')),
        response(html=foreign.replace('/123/', '/2/')), response(html=html)])
    jobs = get_platform('volkswagen').fetch_jobs(config('volkswagen'), 1)
    assert [j['id'] for j in jobs] == ['123'] and jobs[0]['posted_at'] is None
    assert [c.kwargs['params']['startrow'] for c in session.get.call_args_list] == [0, 1, 2]


def test_etihad_country_filter_pagination_and_release_timestamp(monkeypatch):
    raw = {**DATA['etihad'], 'releasedDate': TODAY + 'T11:52:58.184Z'}
    foreign = {**raw, 'id': 'FOREIGN', 'location': {'country': 'us'}}
    session = client(monkeypatch, 'smartrecruiters', [response({'content': [foreign], 'totalFound': 2}),
        response({'content': [raw], 'totalFound': 2})])
    jobs = get_platform('smartrecruiters').fetch_jobs(config('smartrecruiters', 1), 1)
    assert jobs[0]['posted_at'].startswith(TODAY + 'T11:52:58.184')
    assert session.get.call_args.kwargs['params']['offset'] == 1


def test_etihad_detail_uses_posting_api(monkeypatch):
    session = client(monkeypatch, 'smartrecruiters', [response(DATA['etihad_detail'])])
    detail = get_platform('smartrecruiters').fetch_job_detail('https://jobs.smartrecruiters.com/EtihadAirways5/744000155738710', config('smartrecruiters'))
    assert 'knowledge base' in detail['description']
    assert session.get.call_args.args[0].endswith('/postings/744000155738710')


def test_emirates_uses_full_inventory_and_publication_not_closing_date(monkeypatch):
    raw = DATA['emirates']
    foreign = {**raw, 'reqid': 'FOREIGN', 'country': 'United Kingdom'}
    uae = {**raw, 'reqid': 'UAE', 'country': 'United Arab Emirates'}
    de = {**raw, 'reqid': 'DE', 'country': 'Germany'}
    session = client(monkeypatch, 'emirates', [response({'status': 'success', 'data': [foreign, uae, de]})])
    jobs = get_platform('emirates').fetch_jobs(config('emirates'))
    assert [j['id'] for j in jobs] == ['UAE', 'DE']
    assert all(j['date_posted'] == '2025-05-28' and j['posted_at'] is None for j in jobs)
    assert session.get.call_args.kwargs['params']['showAll'] == 'true'


def test_man_filters_overseas_employer_even_with_munich_label():
    assert MANPlatform._location(DATA['man_dubai'], {}) is None
    assert MANPlatform._location(DATA['man'], {}) == 'München, Germany'
    assert MANPlatform._location({**DATA['man'], 'filter7': ['Wien']}, {}) is None
    assert MANPlatform._location({**DATA['man'], 'filter7': ['Unknown']}, {}) is None


def test_man_pagination_does_not_apply_limit_before_location_filter(monkeypatch):
    raw = {**DATA['man'], 'unifiedStandardStart': date.today().strftime('%d.%m.%y')}
    session = client(monkeypatch, 'man', [response({'jobSearchResult': [{'response': DATA['man_dubai']}], 'totalJobs': 20}),
        response({'jobSearchResult': [{'response': raw}], 'totalJobs': 20})], 'post')
    jobs = get_platform('man').fetch_jobs(config('man'), 1)
    assert jobs[0]['id'] == str(raw['id']) and jobs[0]['posted_at'] is None
    assert [c.kwargs['json']['pageNumber'] for c in session.post.call_args_list] == [0, 1]
    assert session.post.call_args.kwargs['json']['sortBy'] == 'date'
    retry = session.mount.call_args.args[1].max_retries
    assert retry.total == 2 and 502 in retry.status_forcelist and retry.allowed_methods == {'POST'}


def test_man_scans_both_languages_and_deduplicates_ids(monkeypatch):
    de = {'jobSearchResult': [{'response': DATA['man']}], 'totalJobs': 1}
    en = {'jobSearchResult': [{'response': {**DATA['man'], 'unifiedStandardStart': '10/15/26'}}], 'totalJobs': 1}
    session = client(monkeypatch, 'man', [response(de), response(en)], 'post')
    assert len(get_platform('man').fetch_jobs(config('man'))) == 1
    assert [c.kwargs['json']['locale'] for c in session.post.call_args_list] == ['de_DE', 'en_US']


def test_man_detail_includes_main_duties_outside_itemprop(monkeypatch):
    client(monkeypatch, 'man', [response(html=DATA['html']['man_detail'])])
    detail = get_platform('man').fetch_job_detail('https://jobs.man.eu/job/engineer/3628-de_DE', config('man'))
    assert 'vehicle systems' in detail['description'] and 'qualification' in detail['description']


@pytest.mark.parametrize('name', ['audi', 'diehl', 'man', 'smartrecruiters', 'volkswagen'])
def test_new_adapters_dispatch_description_enrichment_and_preserve_listing_date(monkeypatch, name):
    cfg = config(name)
    platform = get_platform(name)
    monkeypatch.setattr(platform, 'fetch_job_detail', Mock(return_value={'description': 'Tasks and qualifications', 'date_posted': None}))
    frame = pd.DataFrame([{'company': cfg['company'], 'job_url': 'https://example.test/job', 'date_posted': TODAY}])
    result = enrich_descriptions(frame, delay=0, workday_sites=[], other_sites=[cfg])
    assert result.iloc[0]['description'] == 'Tasks and qualifications' and result.iloc[0]['date_posted'] == TODAY


@pytest.mark.parametrize('name', ['mtu', 'diehl', 'volkswagen'])
def test_missing_listing_markup_is_reported_as_failure(monkeypatch, name):
    client(monkeypatch, name, [response(html='<html>Service unavailable</html>')])
    with pytest.raises(ValueError):
        get_platform(name).fetch_jobs(config(name))

