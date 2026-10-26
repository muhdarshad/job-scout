import pandas as pd

from job_ranker_v2 import _freshness_series
from src.webscraper.platforms.bosch import BoschPlatform
from src.webscraper.platforms.career import CareerPlatform, parse_timestamp
from src.webscraper.platforms.honeywell import HoneywellPlatform


def test_parse_timestamp_requires_explicit_clock_time():
    assert parse_timestamp("2026-10-09") is None
    assert parse_timestamp("2026-10-09T13:08:59+00:00") == "2026-10-09T13:08:59Z"
    assert parse_timestamp("Fri Sep 25 02:01:00 UTC 2026") == "2026-09-25T02:01:00Z"


def test_generic_career_date_only_keeps_posted_at_blank():
    job = CareerPlatform().normalize_job(
        {"id": "1", "date_posted": "2026-10-09", "posted_at": None},
        {"company": "Example"},
    )
    assert job["date_posted"] == "2026-10-09"
    assert job["posted_at"] is None


def test_honeywell_preserves_external_posted_start_date():
    raw = {
        "Id": "158617",
        "Title": "Analyst",
        "PostedDate": "2026-10-09",
        "ExternalPostedStartDate": "2026-10-09T13:08:59+00:00",
        "PrimaryLocationCountry": "DE",
        "PrimaryLocation": "Wuppertal, Germany",
        "secondaryLocations": [],
    }
    job = HoneywellPlatform().normalize_job(HoneywellPlatform._job(raw, {}), {"company": "Honeywell"})
    assert job["date_posted"] == "2026-10-09"
    assert job["posted_at"] == "2026-10-09T13:08:59Z"


def test_bosch_preserves_release_timestamp():
    raw = {
        "refNumber": "REF1",
        "jobUrl": "REF1-data-analyst",
        "name": "Data Analyst",
        "releasedDate": "2026-09-07T10:00:00Z",
        "location": {"country": "de", "city": "Stuttgart"},
    }
    job = BoschPlatform().normalize_job(raw, {"company": "Bosch", "detail_base_url": "https://jobs.bosch.com/en/job"})
    assert job["date_posted"] == "2026-09-07"
    assert job["posted_at"] == "2026-09-07T10:00:00Z"


def test_ranker_freshness_prefers_exact_time_and_falls_back_to_date():
    df = pd.DataFrame([
        {"date_posted": "2026-10-09", "posted_at": ""},
        {"date_posted": "2026-10-09", "posted_at": "2026-10-09T13:08:59Z"},
    ])
    freshness = _freshness_series(df)
    assert freshness.iloc[0] == pd.Timestamp("2026-10-09", tz="UTC")
    assert freshness.iloc[1] > freshness.iloc[0]

