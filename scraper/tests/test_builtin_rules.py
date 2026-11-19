import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from job_rules import default_rules, likely_interested, resolve_rules, title_exclusion_regex
from job_ranker_v2 import load_and_filter
from src.webscraper.pipeline import filter_titles_before_enrichment
from src.webscraper.utils import filtering


@pytest.fixture(autouse=True)
def restore_default_title_rules():
    yield
    filtering.configure(None)


def csv(tmp_path, rows):
    path = tmp_path / 'jobs.csv'
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


ROWS = [
    {'title': 'Quality Engineer', 'company': 'A', 'job_type': 'Full-time', 'job_level': '', 'description': 'Great role'},
    {'title': 'Senior Quality Engineer', 'company': 'B', 'job_type': 'Full-time', 'job_level': '', 'description': ''},
    {'title': 'Quality Analyst', 'company': 'C', 'job_type': 'Part-time', 'job_level': '', 'description': ''},
    {'title': 'Quality Planner', 'company': 'D', 'job_type': '', 'job_level': '', 'description': 'EU nationality required'},
    {'title': 'Embedded Software Engineer', 'company': 'E', 'job_type': '', 'job_level': '', 'description': ''},
]


def test_default_rules_keep_the_original_ranker_behaviour(tmp_path):
    assert load_and_filter(csv(tmp_path, ROWS)).company.tolist() == ['A']
    assert load_and_filter(csv(tmp_path, ROWS), default_rules()).company.tolist() == ['A']


def test_each_rule_list_can_be_changed_or_turned_off(tmp_path):
    path = csv(tmp_path, ROWS)
    assert load_and_filter(path, {**default_rules(), 'excluded_seniority': []}).company.tolist() == ['A', 'B']
    assert load_and_filter(path, {**default_rules(), 'full_time_only': False}).company.tolist() == ['A', 'C']
    assert load_and_filter(path, {**default_rules(), 'excluded_requirements': []}).company.tolist() == ['A', 'D']
    assert load_and_filter(path, {**default_rules(), 'excluded_titles': []}).company.tolist() == ['A', 'E']
    custom = load_and_filter(path, {**default_rules(), 'excluded_titles': [r'analyst'], 'excluded_seniority': [], 'excluded_requirements': [], 'full_time_only': False})
    assert custom.company.tolist() == ['A', 'B', 'D', 'E']


def test_empty_lists_never_match_everything():
    rules = {**default_rules(), 'excluded_titles': [], 'excluded_seniority': []}
    assert title_exclusion_regex(rules) is None
    frame = pd.DataFrame({'title': ['Senior Engineer', 'Software Engineer']})
    filtering.configure(rules)
    assert filter_titles_before_enrichment(frame).title.tolist() == ['Senior Engineer', 'Software Engineer']


def test_pipeline_and_adapters_share_the_configured_title_rules():
    assert not filtering.title_allowed('Senior Engineer')
    filtering.configure({**default_rules(), 'excluded_seniority': []})
    assert filtering.title_allowed('Senior Engineer')
    assert not filtering.title_allowed('Software Engineer')
    filtering.configure(None)
    assert not filtering.title_allowed('Senior Engineer')


def test_resolve_rules_overlays_only_valid_customisations():
    rules = resolve_rules({'interested_titles': ['cfd'], 'full_time_only': False, 'bogus': ['x'], 'excluded_titles': 'not a list'})
    assert rules['interested_titles'] == ['cfd'] and rules['full_time_only'] is False
    assert rules['excluded_titles'] == default_rules()['excluded_titles'] and 'bogus' not in rules
    assert likely_interested('CFD Engineer', rules=rules) and not likely_interested('Data Analyst', rules=rules)
