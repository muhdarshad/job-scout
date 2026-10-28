"""Editable run preferences; adapter endpoints remain in the checked-in configuration."""
import ast
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[1] / 'scraper'

def catalog():
    config = yaml.safe_load((ROOT / 'config/sites.yaml').read_text())
    return [{'id':f"{group}:{site['company']}", 'name':site['company']} for group in ('workday_sites','other_sites') for i, site in enumerate(config.get(group, []))]

def builtin_filters():
    tree = ast.parse((ROOT / 'src/webscraper/utils/filtering.py').read_text())
    return {node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('EXCLUDED_TITLES','EXCLUDED_SENIORITY')}

def defaults():
    ls = yaml.safe_load((ROOT / 'config/jobspy.yaml').read_text())
    tree = ast.parse((ROOT / 'job_ranker_v2.py').read_text())
    skills = next([key.value for key in node.value.keys] for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SKILL_PATTERNS' for target in node.targets))
    return {'enabled_sites':[site['id'] for site in catalog()], 'job_boards':ls['sites'], 'search_terms':ls['search_terms'], 'skills':skills, 'exclude_linkedin_reposts':True, 'cleanup_archived':True}

class Preferences(BaseModel):
    enabled_sites: list[str] = Field(max_length=100)
    job_boards: list[str] = Field(max_length=2)
    search_terms: list[str] = Field(max_length=100)
    skills: list[str] = Field(max_length=200)
    exclude_linkedin_reposts: bool = True
    cleanup_archived: bool = True

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
