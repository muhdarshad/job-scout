import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/JobSpy'))
import pandas as pd
from bs4 import BeautifulSoup
from jobspy.linkedin import LinkedIn
from src.webscraper.jobspy_source import filter_reposts
from src.webscraper.terminal import ScrapeDisplay
from job_ranker_v2 import rank_dataframe

def test_explicit_repost_marker_only():
    marker = lambda text: LinkedIn._repost_marker(BeautifulSoup('<time>'+text+'</time>','html.parser').time)
    assert marker('Reposted 2 hours ago')
    assert marker('Erneut veröffentlicht vor 2 Stunden')
    assert marker('2 hours ago') is None
    assert marker('') is None

def test_repost_filter_keeps_unknown_and_non_linkedin():
    frame = pd.DataFrame({'site':['linkedin','linkedin','linkedin','indeed'],'is_reposted':[True,None,False,True]})
    assert list(filter_reposts(frame).index) == [1,2,3]
    assert len(filter_reposts(frame,False)) == 4

def test_progress_callback_reports_real_stage_and_counts():
    events = []
    with ScrapeDisplay(False,lambda *event:events.append(event)) as display:
        task = display.add('Portal')
        display.update(task,'Enriching descriptions',3,10)
    assert events == [('Portal','Queued',None,None),('Portal','Enriching descriptions',3,10)]

def test_custom_skills_change_ranking(tmp_path):
    file = tmp_path / 'jobs.csv'
    pd.DataFrame([{'title':'Data Analyst','company':'Example','description':'Python SQL English','location':'Munich'}]).to_csv(file,index=False)
    result = rank_dataframe(file,tmp_path,skill_keywords=['Python'])
    assert result.iloc[0].matched_skills == {'Python'}
    result = rank_dataframe(file,tmp_path,skill_keywords=[])
    assert result.iloc[0].skill_score == 0
