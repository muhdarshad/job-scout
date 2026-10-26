import json
from datetime import date, timedelta
from unittest.mock import Mock

from bs4 import BeautifulSoup

from src.webscraper.platforms import get_platform
from src.webscraper.platforms.bmw import BMWPlatform
from src.webscraper.platforms.bosch import BoschPlatform
from src.webscraper.platforms.lufthansa import LufthansaPlatform
from src.webscraper.platforms.workday import WorkdayPlatform


def test_platforms_are_registered():
    assert all(get_platform(name) for name in ("bmw", "workday", "bosch"))


def test_bmw_listing_and_detail_parsing():
    wrapper = BeautifulSoup('''
      <div class="grp-jobfinder__wrapper" data-job-id="196059">
        <a class="grp-jobfinder__link-jobdescription" href="/en/jobfinder/job-description-copy.196059.html"></a>
        <div class="grp-jobfinder-cell-refno" data-job-title="Analyst" data-job-location="Munich"
          data-job-field="Finance" data-posting-date="20260907" data-job-type="Full-time">196059</div>
      </div>''', "html.parser").div
    raw = BMWPlatform._parse_listing(wrapper)
    assert raw["id"] == "196059"
    assert raw["job_url"].endswith("196059.html")

    response = Mock(text='''
      <h1><span class="cmp-title__text-title1">Analyst</span></h1>
      <div itemprop="addressLocality">Munich</div><div itemprop="addressRegion">Germany</div>
      <div itemprop="datePosted">20260907</div><div itemprop="description"><p>Build reports.</p></div>
      <div class="grp-jobdescription__jobid">196059</div><div class="grp-jobdescription__jobField">Finance</div>
      <div class="grp-jobdescription__jobType">Full-time</div><div itemprop="industry">Automotive</div>''')
    response.raise_for_status = Mock()
    session = Mock()
    session.headers = {}
    session.get.return_value = response
    detail = BMWPlatform().fetch_job_detail(raw["job_url"], session)
    assert detail["_country"] == "Germany"
    assert detail["description"] == "Build reports."
    assert session.get.call_args.args[0].endswith("196059.content.html")


def test_rolls_royce_workday_discovers_and_applies_filters(monkeypatch):
    config = {
        "company": "Rolls-Royce", "tenant": "rollsroyce", "cluster": "wd3", "site": "professional",
        "company_industry": "Aerospace", "location_country_label": "Germany", "posted_within_days": 1,
    }
    bootstrap = Mock()
    bootstrap.raise_for_status = Mock()
    bootstrap.json.return_value = {
        "facets": [
            {"facetParameter": "locationCountry", "values": [{"descriptor": "Germany", "id": "country-de"}]},
            {"facetParameter": "startDate", "values": [{"descriptor": "Posted Today", "id": "today"}]},
        ]
    }
    listing = Mock()
    listing.raise_for_status = Mock()
    listing.json.return_value = {
        "total": 1,
        "jobPostings": [{
            "title": "Prüfingenieur (m/w/d)", "externalPath": "/job/Berlin/Pruefingenieur_JR1",
            "locationsText": "Berlin", "postedOn": "Posted Today", "timeType": "Full time",
        }],
    }
    post = Mock(side_effect=[bootstrap, listing])
    monkeypatch.setattr("src.webscraper.platforms.workday.requests.post", post)

    jobs = WorkdayPlatform().fetch_jobs(config, max_results=100)

    assert jobs[0]["id"] == "JR1"
    assert jobs[0]["job_url"].endswith("/professional/job/Berlin/Pruefingenieur_JR1")
    assert post.call_args_list[1].kwargs["json"]["appliedFacets"] == {
        "locationCountry": ["country-de"], "startDate": ["today"],
    }


def test_lufthansa_filters_date_upstream_and_country_locally(monkeypatch):
    config = {
        "company": "Lufthansa Group", "api_url": "https://example.test/jobs", "language": "EN",
        "country_filter": "Germany", "posted_within_days": 1,
    }
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "SearchResult": {
            "SearchResultCountAll": 2,
            "SearchResultItems": [
                {"MatchedObjectDescriptor": {
                    "ID": "de", "PositionTitle": "Analyst", "PositionURI": "https://example.test/de",
                    "PositionLocation": [{"CityName": "Frankfurt", "CountryName": "Germany"}],
                    "PublicationStartDate": date.today().isoformat(),
                }},
                {"MatchedObjectDescriptor": {
                    "ID": "at", "PositionTitle": "Analyst", "PositionURI": "https://example.test/at",
                    "PositionLocation": [{"CityName": "Vienna", "CountryName": "Austria"}],
                    "PublicationStartDate": date.today().isoformat(),
                }},
            ],
        }
    }
    get = Mock(return_value=response)
    monkeypatch.setattr("src.webscraper.platforms.lufthansa.requests.get", get)

    jobs = LufthansaPlatform().fetch_jobs(config, max_results=100)

    payload = json.loads(get.call_args.kwargs["params"]["data"])
    assert {
        "CriterionName": "PublicationStartDate",
        "CriterionValue": [(date.today() - timedelta(days=1)).isoformat()],
    } in payload["SearchCriteria"]
    assert [job["id"] for job in jobs] == ["de"]


def test_bosch_normalization_and_detail(monkeypatch):
    config = {
        "company": "Bosch", "detail_base_url": "https://jobs.bosch.com/en/job", "detail_api_url": "https://api.test/jobs",
        "api_token": "public-client-token", "company_industry": "Engineering", "language": "en",
    }
    raw = {
        "refNumber": "REF1", "jobUrl": "REF1-data-analyst", "name": "Data Analyst", "releasedDate": "2026-09-07T10:00:00Z",
        "location": {"country": "de", "city": "Stuttgart"}, "function": {"label": "Analytics"},
        "positionType": {"valueLabel": "Professional"}, "working_hours": {"valueLabel": "Full-time"},
    }
    job = BoschPlatform().normalize_job(raw, config)
    assert job["id"] == "REF1"
    assert job["location"] == "Stuttgart, Germany"

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = [{
        "defaultJobAd": True, "refNumber": "REF1", "name": "Data Analyst", "releasedDate": "2026-09-07T10:00:00Z",
        "location": {"fullLocation": "Stuttgart, Germany"}, "typeOfEmployment": {"label": "Full-time"},
        "experienceLevel": {"label": "Professional"}, "function": {"label": "Analytics"}, "industry": {"label": "Automotive"},
        "jobAd": {"sections": {"jobDescription": {"text": "<p>Build dashboards.</p>"}, "qualifications": {"text": "<p>Know SQL.</p>"}}},
    }]
    monkeypatch.setattr("src.webscraper.platforms.bosch.requests.get", Mock(return_value=response))
    detail = BoschPlatform().fetch_job_detail(job["job_url"], config)
    assert detail["description"] == "Build dashboards. Know SQL."
    assert detail["location"] == "Stuttgart, Germany"

