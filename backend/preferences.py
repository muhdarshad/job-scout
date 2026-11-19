"""Editable run preferences; adapter endpoints remain in the checked-in configuration."""
import ast, re
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator
from scraper.job_rules import RULE_LISTS, default_rules

ROOT = Path(__file__).resolve().parents[1] / 'scraper'

def catalog():
    config = yaml.safe_load((ROOT / 'config/sites.yaml').read_text())
    return [{'id':f"{group}:{site['company']}", 'name':site['company']} for group in ('workday_sites','other_sites') for i, site in enumerate(config.get(group, []))]

def defaults():
    ls = yaml.safe_load((ROOT / 'config/jobspy.yaml').read_text())
    tree = ast.parse((ROOT / 'job_ranker_v2.py').read_text())
    skills = next([key.value for key in node.value.keys] for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SKILL_PATTERNS' for target in node.targets))
    return {'enabled_sites':[site['id'] for site in catalog()], 'job_boards':ls['sites'], 'search_terms':ls['search_terms'], 'skills':skills, 'exclude_linkedin_reposts':True, 'cleanup_archived':True}

LIST_LABELS = {'excluded_titles':'Excluded titles', 'excluded_seniority':'Excluded seniority / level', 'not_interested_titles':'Not-interested titles',
               'interested_titles':'Likely-interested titles', 'excluded_requirements':'Excluded description requirements'}

class BuiltinFilters(BaseModel):
    """Regular expressions (case-insensitive, one per entry) that replace the scraper's hard-coded lists."""
    excluded_titles: list[str] = Field(max_length=300)
    excluded_seniority: list[str] = Field(max_length=300)
    not_interested_titles: list[str] = Field(max_length=300)
    interested_titles: list[str] = Field(max_length=300)
    excluded_requirements: list[str] = Field(max_length=300)
    full_time_only: bool = True

    @field_validator(*RULE_LISTS)
    @classmethod
    def valid_patterns(cls, values, info):
        values = list(dict.fromkeys(value.strip() for value in values))
        for value in values:
            if not value or len(value) > 200:
                raise ValueError(f'{LIST_LABELS[info.field_name]}: each pattern must contain 1–200 characters.')
            try:
                re.compile(value, re.IGNORECASE)
                re.compile('(?:' + value + ')', re.IGNORECASE)
            except re.error as error:
                raise ValueError(f'{LIST_LABELS[info.field_name]}: invalid pattern “{value}” ({error}).') from None
        return values

    def overrides(self):
        """Only lists that differ from the built-in defaults are stored, so unchanged lists follow future updates."""
        defaults = default_rules()
        return {name: value for name, value in self.model_dump().items() if value != defaults[name]}

class Preferences(BaseModel):
    enabled_sites: list[str] = Field(max_length=100)
    job_boards: list[str] = Field(max_length=2)
    search_terms: list[str] = Field(max_length=100)
    skills: list[str] = Field(max_length=200)
    exclude_linkedin_reposts: bool = True
    cleanup_archived: bool = True
    builtin_filters: BuiltinFilters | None = None

    @field_validator('search_terms','skills')
    @classmethod
    def clean_text(cls, values):
        values = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 120 for value in values):
            raise ValueError('Each entry must contain 1–120 characters.')
        return values

    @field_validator('enabled_sites')
    @classmethod
    def sites(cls, values):
        if not set(values) <= {site['id'] for site in catalog()}:
            raise ValueError('Unknown source site.')
        return list(dict.fromkeys(values))

    @field_validator('job_boards')
    @classmethod
    def boards(cls, values):
        if not set(values) <= {'linkedin','indeed'}:
            raise ValueError('Unknown job board.')
        return list(dict.fromkeys(values))
