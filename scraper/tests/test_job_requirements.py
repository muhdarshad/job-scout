import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl
import pandas as pd
import job_ranker_v2 as ranker
from job_requirements import extract_requirements

def _check_experience(text, level, years, status):
    result = extract_requirements(text)
    assert result['experience_required'] == level
    assert result['experience_min_years'] == years
    assert result['experience_requirement'] == status
    assert result['experience_evidence'] == text

def _check_german(text, level, status):
    result = extract_requirements(text)
    assert result['german_required'] == level
    assert result['german_requirement'] == status

def _check_unknown_does_not_mean_none_required(text):
    result = extract_requirements(text)
    assert result['german_required'] == 'not stated'
    assert result['experience_min_years'] is None

def _check_does_not_use_company_years_or_preferred_years_as_minimum():
    result = extract_requirements('For 50 years we have built engines with extensive experience. Ideally 5 years of experience.')
    assert result['experience_min_years'] is None
    assert '50 years' not in result['experience_required']

def _check_rank_and_export_requirements_preserve_existing_columns(tmp_path):
    csv, output = (tmp_path / 'jobs.csv', tmp_path / 'ranked.xlsx')
    pd.DataFrame([{'title': 'Data Analyst', 'company': 'A', 'source': 'LS', 'description': 'At least 3 years of experience required. German B2 preferred.', 'job_url': 'https://example.com/job'}, {'title': 'Quality Engineer', 'company': 'B', 'description': None}]).to_csv(csv, index=False)
    ranked = ranker.rank_dataframe(csv, tmp_path)
    assert len(ranked) == 2
    assert ranked.loc[ranked.company == 'A', 'experience_min_years'].item() == 3
    ranker.export_excel(ranked, output)
    sheet = openpyxl.load_workbook(output).active
    headers = [c.value for c in sheet[1]]
    assert headers[16:18] == ['Job URL', 'Link']
    assert headers[-7:] == ['Experience Required', 'Experience Min Years', 'Experience Requirement', 'Experience Evidence', 'German Required Level', 'German Requirement', 'German Evidence']
    assert sheet['R2'].value == '=HYPERLINK(Q2,"Link")'
    assert sheet.column_dimensions['T'].hidden
    assert sheet.auto_filter.ref.endswith('AD3')
    assert sheet.freeze_panes == 'A2'
    assert len(sheet.conditional_formatting) == 6
    unknown_row = next((row for row in sheet.iter_rows(min_row=2) if row[2].value == 'B'))
    assert unknown_row[24].value is None
    assert unknown_row[27].value == 'not stated'


class RequirementTests(unittest.TestCase):

    def test_additional_wording_and_no_cefr_guess(self):
        _check_experience('Berufseinsteiger willkommen.', 'entry / career change mentioned', None, 'stated')
        _check_experience('Mindestens 5 Jahre einschlägige Berufserfahrung.', '5 jahre', 5, 'required')
        _check_experience('5+ years of experience.', '5+ years', 5, 'stated')
        _check_german('Deutsch in Wort und Schrift.', 'unspecified', 'stated')
        _check_german('German B2 required and C1 preferred.', 'B2 | C1', 'mixed / review')
        assert extract_requirements('Fluent German required.')['german_required'] == 'fluent'

    def test_experience(self):
        for row in [('Mindestens 5 Jahre Berufserfahrung erforderlich.', '5 jahre', 5, 'required'), ('3+ years of experience required.', '3+ years', 3, 'required'), ("At least three years' relevant experience.", 'three years', 3, 'required'), ('Minimum 3–5 years of professional experience.', '3–5 years', 3, 'required'), ('Idealerweise mehrjährige Berufserfahrung.', 'several years', None, 'preferred'), ('Langjährige Erfahrung in der Fertigung.', 'long-standing', None, 'stated'), ('Erste praktische Erfahrung.', 'initial experience', None, 'stated'), ('No prior experience required.', 'experience mentioned', None, 'not required')]:
            with self.subTest(row=row):
                _check_experience(*row)

    def test_german(self):
        for row in [('Verhandlungssichere Deutschkenntnisse.', 'business fluent', 'stated'), ('Fließende Deutschkenntnisse erforderlich.', 'fluent', 'required'), ('Sehr gute Deutschkenntnisse.', 'very good', 'stated'), ('Deutsch auf Muttersprachlerniveau.', 'native', 'stated'), ('Gute und sichere Deutschkenntnisse.', 'good', 'stated'), ('German language skills are an advantage.', 'unspecified', 'preferred'), ('German language skills desirable.', 'unspecified', 'preferred'), ('Fluent English and basic German required.', 'basic', 'required'), ('Sehr gute Englischkenntnisse, gute Deutschkenntnisse.', 'good', 'stated'), ('German B2 required; German C1 preferred.', 'B2 | C1', 'required | preferred'), ('No German language skills required.', 'unspecified', 'not required'), ('German is not required.', 'unspecified', 'not required'), ('Keine Deutschkenntnisse erforderlich.', 'unspecified', 'not required'), ('<p>Fluent <b>German</b> required.</p>', 'fluent', 'required')]:
            with self.subTest(row=row):
                _check_german(*row)

    def test_unknown_does_not_mean_none_required(self):
        for row in [None, float('nan'), '', 'We have operated in Germany for 50 years.', 'A German engineering company.', 'Standorte in Deutschland.']:
            with self.subTest(row=row):
                _check_unknown_does_not_mean_none_required(row)

    def test_does_not_use_company_years_or_preferred_years_as_minimum(self):
        _check_does_not_use_company_years_or_preferred_years_as_minimum()

    def test_rank_and_export_requirements_preserve_existing_columns(self):
        with TemporaryDirectory() as directory:
            _check_rank_and_export_requirements_preserve_existing_columns(Path(directory))

