import json
from datetime import date, timedelta
from unittest.mock import Mock

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from src.webscraper.config import COLUMNS, OTHER_SITES
from src.webscraper.enrichment.description import enrich_descriptions
from src.webscraper.platforms import get_platform
from src.webscraper.platforms.career import parse_date, posting_detail, recent


NEW = ("n3", "honeywell", "boeing", "everllence", "siemens_ag", "dhl")
TODAY = date.today().isoformat()


def response(html="", payload=None):
    result = Mock(text=html, url="https://example.test/search/")
    result.json.return_value = payload
    return result


def client(monkeypatch, name, pages, method="get"):
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    getattr(session, method).side_effect = pages
    monkeypatch.setattr(f"src.webscraper.platforms.{name}.career_session", lambda: session)
    monkeypatch.setattr("time.sleep", lambda _: None)
    return session


def config(name):
    return next(s.copy() for s in OTHER_SITES if s.get("platform") == name)


def test_all_seven_sources_registered_once_and_german():
    for name in ("bmw", *NEW):
        sites = [s for s in OTHER_SITES if s.get("platform") == name]
        assert len(sites) == 1 and sites[0]["country_filter"] == "Germany"
        assert get_platform(name)
    assert get_platform("siemens_ag") is not get_platform("siemens_energy")


@pytest.mark.parametrize("value", ["2026-10-02", "2026-10-2", "20261002", "02-Oct-2026", "10/02/2026", "Fri Oct 02 02:01:00 UTC 2026"])
def test_dates_from_all_portal_formats(value):
    assert parse_date(value) == date(2026, 10, 2)


def test_rolling_window_rejects_missing_and_old_dates():
    assert recent(TODAY, {"posted_within_days": 0})
    assert not recent((date.today() - timedelta(days=2)).isoformat(), {"posted_within_days": 1})
    assert not recent(None, {"posted_within_days": 1})
    assert recent(None, {"posted_within_days": None})


def test_jsonld_graph_and_multiple_locations():
    posting = {"@type": "JobPosting", "identifier": {"value": "JR1"}, "title": "Engineer",
               "datePosted": TODAY, "description": "<p>Design engines &amp; systems.</p>",
               "jobLocation": [{"address": {"addressLocality": "Hamburg", "addressCountry": "DE"}},
                               {"address": {"addressLocality": "Paris", "addressCountry": "FR"}}]}
    soup = BeautifulSoup('<script type="application/ld+json">' + json.dumps({"@graph": [posting]}) + '</script>', "html.parser")
    detail = posting_detail(soup)
    assert detail["id"] == "JR1" and detail["_countries"] == ["DE", "FR"]
    assert detail["description"] == "Design engines & systems."


def test_n3_uses_original_date_and_filters_titles_before_details(monkeypatch):
    entries = [("Software Developer", "1"), ("Engineer", "2"), ("Mechanic", "3")]
    feed = '<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(
        f'<entry><title>{title}</title><link href="https://karriere.n3eos.com/role-de-j{id}.html"/><updated>{TODAY}</updated></entry>'
        for title, id in entries) + '</feed>'
    client(monkeypatch, "n3", [response(feed)])
    platform = get_platform("n3")
    detail = Mock(side_effect=[{"_countries": ["DE"], "date_posted": "2000-01-01", "title": "Engineer"},
                               {"_countries": ["DE"], "date_posted": TODAY, "title": "Mechanic", "description": "Repair engines"}])
    monkeypatch.setattr(platform, "fetch_job_detail", detail)
    jobs = platform.fetch_jobs(config("n3"), max_results=1)
    assert [j["id"] for j in jobs] == ["3"]
    assert detail.call_count == 2 and jobs[0]["date_posted"] == TODAY


def test_honeywell_paginates_past_rejected_jobs_and_defers_descriptions(monkeypatch):
    def page(rows):
        return response(payload={"items": [{"requisitionList": rows, "TotalJobsCount": 3}]})
    rows = [{"Id": "1", "Title": "Senior Engineer", "PrimaryLocationCountry": "DE", "PostedDate": TODAY},
            {"Id": "2", "Title": "Engineer", "PrimaryLocationCountry": "FR", "PostedDate": TODAY}]
    good = {"Id": "3", "Title": "Engineer", "PrimaryLocationCountry": "DE", "PrimaryLocation": "Berlin, Germany", "PostedDate": TODAY}
    session = client(monkeypatch, "honeywell", [page(rows), page([good])])
    jobs = get_platform("honeywell").fetch_jobs(config("honeywell"), max_results=1)
    assert [j["id"] for j in jobs] == ["3"] and jobs[0]["description"] is None
    assert "location=Germany" in session.get.call_args_list[0].kwargs["params"]["finder"]
    assert "offset=2" in session.get.call_args_list[1].kwargs["params"]["finder"]


def test_honeywell_detail_uses_external_id_and_oracle_language_header(monkeypatch):
    raw = {"Id": "158699", "Title": "Technical Support Specialist", "PrimaryLocationCountry": "DE",
           "PrimaryLocation": "Ratingen, Germany", "ExternalPostedStartDate": "2026-10-01T12:36:00Z",
           "ExternalDescriptionStr": "<p>Support customers.</p>", "ExternalQualificationsStr": "<p>Know English.</p>"}
    session = client(monkeypatch, "honeywell", [response(payload={"items": [raw]})])
    job = get_platform("honeywell").fetch_job_detail("https://careers.honeywell.com/en/sites/Honeywell/job/158699")
    assert job["description"] == "Support customers. Know English."
    assert job["date_posted"] == "2026-10-01"
    assert 'Id="158699"' in session.get.call_args.kwargs["params"]["finder"]
    assert session.get.call_args.kwargs["headers"]["ora-irc-language"] == "en"


def test_dhl_uses_verified_country_payload_and_caps_after_filtering(monkeypatch):
    def page(rows):
        return response(payload={"eagerLoadRefineSearch": {"status": 200, "totalHits": 2, "data": {"jobs": rows}}})
    bad = {"jobSeqNo": "bad", "title": "Senior Engineer", "country": "Germany", "postedDate": TODAY}
    good = {"jobSeqNo": "good", "jobId": "AV-1", "title": "Engineer", "country": "Germany", "location": "Bonn, Germany", "postedDate": TODAY}
    session = client(monkeypatch, "dhl", [page([bad]), page([good])], "post")
    jobs = get_platform("dhl").fetch_jobs(config("dhl"), max_results=1)
    assert [j["id"] for j in jobs] == ["AV-1"]
    assert session.post.call_args_list[0].kwargs["json"]["selected_fields"] == {"country": ["Germany"]}
    assert session.post.call_args_list[1].kwargs["json"]["from"] == 1


def test_everllence_skips_foreign_and_excluded_jobs_before_details(monkeypatch):
    def tile(id, title, country):
        return f'<li class="job-tile"><a class="jobTitle-link" href="/job/role/{id}/">{title}</a><div id="job-{id}-desktop-section-multilocation-value">City, {country}, 12345</div></li>'
    session = client(monkeypatch, "everllence", [response(tile("1", "Software Engineer", "DE") + tile("2", "Engineer", "AT")), response(tile("3", "Engineer", "DE"))])
    detail = Mock(return_value={"title": "Engineer", "date_posted": TODAY, "description": "Build engines"})
    monkeypatch.setattr(get_platform("everllence"), "fetch_job_detail", detail)
    jobs = get_platform("everllence").fetch_jobs(config("everllence"), max_results=1)
    assert [j["id"] for j in jobs] == ["3"] and detail.call_count == 1
    assert session.get.call_args_list[1].kwargs["params"]["startrow"] == 2


def test_siemens_ag_continues_after_excluded_page(monkeypatch):
    def article(id, title):
        return f'<article class="article--result"><a href="/en_US/externaljobs/JobDetail/{id}">{title}</a></article>'
    session = client(monkeypatch, "siemens_ag", [response(article("1", "Working Student")), response(article("2", "Engineer"))])
    detail = Mock(return_value={"id": "2", "title": "Engineer", "date_posted": TODAY, "_germany": True, "description": "Build systems"})
    monkeypatch.setattr(get_platform("siemens_ag"), "fetch_job_detail", detail)
    jobs = get_platform("siemens_ag").fetch_jobs(config("siemens_ag"), max_results=1)
    assert [j["id"] for j in jobs] == ["2"] and detail.call_count == 1
    assert session.get.call_args_list[1].kwargs["params"]["folderOffset"] == 1
    assert session.get.call_args_list[0].kwargs["params"]["42386"] == "[812132]"


def test_boeing_follows_next_links_and_reads_month_first_dates(monkeypatch):
    def page(jobs, next_href=None):
        items = "".join(f'''<li><a class="search-results__job-link" data-job-id="{id}" href="/job/role/{id}">{title}</a>
          <span class="location">{location}</span><span class="date">{posted}</span></li>''' for id, title, location, posted in jobs)
        nav = f'<nav class="pagination"><a class="next" href="{next_href}">Next</a></nav>' if next_href else               '<nav class="pagination"><a class="next disabled" href="#">Next</a></nav>'
        return f'<section data-selector-name="searchresults"><div id="search-results-list">{items}</div></section>{nav}'
    dotted, slashed = date.today().strftime("%m.%d.%Y"), date.today().strftime("%m/%d/%Y")
    old = (date.today() - timedelta(days=10)).strftime("%m.%d.%Y")
    session = client(monkeypatch, "boeing", [
        response(page([("1", "Senior Engineer", "Hamburg", dotted), ("2", "Engineer", "Hamburg, Germany", dotted),
                       ("3", "Engineer Old", "Munich", old)], "/location/germany-jobs/185/2921044/2/2")),
        response(page([("2", "Engineer", "Hamburg, Germany", dotted), ("4", "Engineer Two", "Munich", slashed)])),
    ])
    jobs = get_platform("boeing").fetch_jobs(config("boeing"))
    assert [j["id"] for j in jobs] == ["2", "4"]
    assert [j["date_posted"] for j in jobs] == [TODAY, TODAY]
    assert [j["location"] for j in jobs] == ["Hamburg, Germany", "Munich, Germany"]
    assert session.get.call_args.args[0] == "https://jobs.boeing.com/location/germany-jobs/185/2921044/2/2"
    assert session.get.call_count == 2


def test_boeing_listing_dates_are_month_first():
    from src.webscraper.platforms.boeing import listing_date
    assert listing_date("11.05.2026") == "2026-11-05"
    assert listing_date("10/30/2026") == "2026-10-30"
    assert listing_date("") is None and listing_date("19.11.2026") is None


def test_enrichment_dispatches_all_new_sources(monkeypatch):
    rows = [{"company": config(name)["company"], "job_url": f"https://example.test/{name}", "description": None} for name in NEW]
    platforms = {name: Mock() for name in NEW}
    for name, platform in platforms.items():
        platform.fetch_job_detail.return_value = {"description": name + " full description", "date_posted": TODAY}
    monkeypatch.setattr("src.webscraper.enrichment.description.get_platform", platforms.get)
    frame = enrich_descriptions(pd.DataFrame(rows, columns=COLUMNS), delay=0)
    assert frame["description"].tolist() == [name + " full description" for name in NEW]
    assert all(p.fetch_job_detail.call_count == 1 for p in platforms.values())

