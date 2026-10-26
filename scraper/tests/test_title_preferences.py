import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from job_rules import DEFAULT_EXCLUDED_KEYWORDS, excluded_keyword, likely_interested
from src.webscraper.pipeline import filter_titles_before_enrichment

def test_operational_roles_and_gender_variants():
    for title in ['Postbote (m/w/d)', 'POSTBOTEN', 'Paketzustellerin', 'Sortierer', 'Lagerhelfer',
                  'Kommissionierer', 'Staplerfahrer', 'Reinigungskräfte', 'Delivery-driver']:
        # Reinigungskräfte is an irregular plural; explicit keyword below.
        terms = [*DEFAULT_EXCLUDED_KEYWORDS, 'reinigungskräfte']
        assert excluded_keyword(title, terms), title
    for title in ['Mechanical Engineer', 'Entwicklungsingenieur für Sortieranlagen', 'Postbotentechnologie Engineer']:
        assert not excluded_keyword(title, DEFAULT_EXCLUDED_KEYWORDS), title

def test_literal_terms_and_normalization():
    assert excluded_keyword('KUECHENHILFE', ['küchenhilfe'])
    assert excluded_keyword('Engineer C++', ['c++'])
    assert not excluded_keyword('Engineer', ['.*'])
    assert not excluded_keyword('Cleaner technology engineer', [])
    assert not excluded_keyword('mail carriage designer', ['mail carrier'])

def test_shared_likely_interest_precedence():
    assert likely_interested('Mechanical Engineer')
    assert likely_interested('Data-Analyst')
    assert not likely_interested('Mechanical technician')
    assert not likely_interested('Quality Sortierer', ['sortierer'])
    assert not likely_interested('Engineer')

def test_before_enrichment_filter_preserves_timestamp_and_description_scope():
    frame = pd.DataFrame([
        {'title':'Sortierer', 'description':'Engineering', 'scraped_at':'2026-10-26T11:00:00Z'},
        {'title':'Mechanical Engineer', 'description':'Design machinery for Sortierer', 'scraped_at':'2026-10-26T11:00:00Z'}])
    kept = filter_titles_before_enrichment(frame, ['sortierer'])
    assert kept.title.tolist() == ['Mechanical Engineer']
    assert kept.scraped_at.tolist() == ['2026-10-26T11:00:00Z']
