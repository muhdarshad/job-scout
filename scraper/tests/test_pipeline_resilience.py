from src.webscraper import pipeline


def test_pipeline_continues_after_one_portal_fails(monkeypatch):
    calls = []
    class Platform:
        def fetch_jobs(self, site, max_results=None):
            calls.append(site['company'])
            if site['company'] == 'Broken Portal':
                raise RuntimeError('temporary portal failure')
            return [{'id': 'ok', 'title': 'Analyst'}]
    monkeypatch.setattr(pipeline, 'load_sites_config', lambda path: {
        'workday_sites': [{'company': 'Broken Portal'}],
        'other_sites': [{'company': 'Working Portal', 'platform': 'working'}],
    })
    monkeypatch.setattr(pipeline, 'get_platform', lambda name: Platform())
    result = pipeline.run_pipeline(enrich=False, extract_skills=False, progress=False)
    assert result['id'].tolist() == ['ok']
    assert sorted(calls) == ['Broken Portal', 'Working Portal']
    assert result.attrs['site_stats'][0]['status'] == 'Failed'

