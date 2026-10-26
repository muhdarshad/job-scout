# Career Web Scraper

A modular Python scraper for collecting job postings from career sites. Supports Workday, Mercedes-Benz, Siemens Energy, Lufthansa, ALTEN, Bosch, BMW, N3, Honeywell, Boeing, Everllence, Siemens AG, and DHL.

## Features

- **Multi-platform support**: public career APIs, feeds, and HTML portals
- **Config-driven**: Add new Workday sites via YAML config — no code changes needed
- **Canonical schema**: All sites normalized to a common 13-column format
- **Two-pass enrichment**: Fetches full descriptions and job types via per-job detail calls
- **Skills extraction**: Keyword-based skill tagging from descriptions
- **Respectful scraping**: Configurable delays, proper headers, pagination

## Project Structure

```
custom_webscraper/
├── config/
│   └── sites.yaml          # Site configurations (add new sites here)
├── src/
│   └── webscraper/
│       ├── __init__.py
│       ├── config.py       # Constants, headers, column schema
│       ├── pipeline.py     # Main orchestration logic
│       ├── platforms/      # Platform-specific scrapers
│       │   ├── __init__.py
│       │   ├── base.py     # Abstract base class
│       │   ├── workday.py  # Workday scraper
│       │   └── mercedes.py # Mercedes-Benz (SuccessFactors) scraper
│       ├── enrichment/     # Post-processing
│       │   ├── __init__.py
│       │   ├── description.py  # Full description fetching
│       │   └── skills.py       # Keyword-based skill extraction
│       └── utils/          # Helper functions
│           └── __init__.py
├── main.py                 # CLI entry point
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# Run with defaults (scrapes configured sites, enriches descriptions, extracts skills)
python main.py

# Limit results per site for testing
python main.py --max-results 10

# Skip enrichment for faster runs
python main.py --no-enrich

# Custom output path
python main.py --output data/my_jobs.csv
```

## Configuration

Edit `config/sites.yaml` to add or modify sites:

### Workday Sites
```yaml
workday_sites:
  - company: "Airbus"
    tenant: "ag"           # From URL: https://ag.wd3.myworkdayjobs.com/Airbus
    cluster: "wd3"
    site: "Airbus"
    company_industry: "Aerospace & Defense"
    search_term: ""        # Optional keyword filter
    max_results: 20        # Cap results (null = no limit)
```

### Other Platforms
```yaml
other_sites:
  - company: "Mercedes-Benz"
    platform: "mercedes_successfactors"
    api_url: "https://jobs.api.mercedes-benz.com/search"
    company_industry: "Automotive"
    search_term: ""
    max_results: 50
```

## Output Schema

All jobs normalized to these columns:

| Column | Description |
|--------|-------------|
| `id` | Source job identifier |
| `job_url` | Direct link to job posting |
| `title` | Job title |
| `company` | Company name |
| `location` | Job location |
| `date_posted` | Publication date; new sources use YYYY-MM-DD |
| `job_type` | Full time, Contract, etc. |
| `job_level` | Entry, Senior, Director, etc. |
| `job_function` | Engineering, Sales, etc. |
| `description` | Full job description (HTML stripped) |
| `company_industry` | Industry category |
| `skills` | Comma-separated matched keywords |
| `search_term` | Filter used for this query |

## Germany career sources

The following sources run automatically through `main.py`, including description enrichment and ranking. BMW already existed and now uses its Germany job finder endpoint. Siemens AG is separate from Siemens Energy.

| Company | Platform key | Extraction |
|---|---|---|
| BMW Group | `bmw` | Germany AEM listing endpoint and HTML details |
| N3 Engine Overhaul Services | `n3` | rexx Atom feed and JobPosting JSON-LD details |
| Honeywell | `honeywell` | Oracle Recruiting listing and detail APIs |
| Boeing | `boeing` | Germany TalentBrew listings and JobPosting JSON-LD details |
| Everllence | `everllence` | SuccessFactors listings and HTML detail metadata |
| Siemens AG | `siemens_ag` | Germany Avature listings and HTML details |
| DHL | `dhl` | Phenom country-filtered search API and JobPosting JSON-LD details |

All seven are configured for Germany with `max_results: 100` and the existing rolling `posted_within_days: 1` window. Set that value to `7` for the last seven days, or `null` to include all publication dates. Missing or invalid dates are excluded when a date window is active. A result cap applies after filtering, so a source may legitimately return zero jobs.

The new adapters and BMW reuse the pipeline's title exclusions before detail requests. BMW, Honeywell, Boeing, and DHL defer descriptions to enrichment. N3, Everllence, and Siemens AG fetch eligible details during collection because publication dates or country metadata are unavailable in their listings. Consequently, `--no-enrich` skips the later enrichment pass but does not eliminate those metadata requests. N3's feed update timestamp is not treated as an original publication date.

The adapters use the existing Python dependencies; no browser installation or Firecrawl account is required. Career-site API and HTML contracts can change. Fetch failures are reported, and the pipeline continues with the remaining sources.

Run the offline regression checks with `python -m pytest -q` after installing pytest. Tests cover title and country filtering, publication dates, pagination, enrichment dispatch, and caps after filtering. Live discovery was checked against all seven portals; the tests do not make network requests.

## Adding New Platforms

1. Create `src/webscraper/platforms/newplatform.py` implementing `BasePlatform`
2. Register in `src/webscraper/platforms/__init__.py`
3. Add site config to `config/sites.yaml` with `platform: "newplatform"`

## CLI Options

| Option | Description |
|--------|-------------|
| `--max-results N` | Limit jobs per site |
| `--no-enrich` | Skip description fetching (faster) |
| `--no-skills` | Skip skill extraction |
| `--output PATH` | Custom output CSV path |
| `--config PATH` | Custom sites YAML path |

## Example Output

```csv
id,job_url,title,company,location,date_posted,job_type,job_level,job_function,description,company_industry,skills,search_term
abc123,https://.../job/123,Design Engineer,Airbus,Wichita KS,Posted Today,Full time,,,"Airbus is committed...",Aerospace & Defense,"SQL, Python",""
```

## Notes

- Workday detail fetching uses the public `/wday/cxs/{tenant}/{site}/job/{path}` endpoint (no auth required)
- Mercedes-Benz detail pages are HTML-scraped; CSS selectors may need adjustment if the site changes
- Skills extraction is simple keyword matching — not NLP
- Uses request delays; adjust `REQUEST_DELAY` in config if needed

## License

MIT



## Combined LS + CS run

`python main.py` now runs the company portals and LS job boards, writes one combined CSV,
and uses `job_ranker_v2.py` once to produce one ranked Excel workbook.
Install from the repository root with `python -m pip install -r requirements.txt`.
Python 3.10+ is required. The local JobSpy fork from the uploaded LS project is preserved
under `vendor/JobSpy`, including its license; virtual environments, notebooks, and old outputs are not copied.

```bash
python main.py --workers 4
python main.py --no-ls                  # company portals only
python main.py --workers 1 --no-ls      # sequential company portals
python main.py --ls-config config/jobspy.yaml --config config/sites.yaml
```

Company portals run in up to four independent threads by default. Each worker fetches,
filters, and enriches one portal, so different portals overlap while each portal's existing
request delays remain intact. LS has one separate worker: search terms/pages stay serial,
with the notebook's random 5–12 second pause after nonempty calls and failures.
JobSpy still searches its different boards concurrently within each batch, as in LS.
LinkedIn's internal page/detail delays remain in the bundled fork. Delays reduce request
frequency but cannot guarantee that a board will never block requests.

Edit `config/jobspy.yaml` for the original 14 search terms, Germany location, LinkedIn/Indeed/Google,
two pages of 20 results, 8-hour window, Google's original 3-day search text, and pause range.
`--max-results` controls company portals; LS pagination is controlled separately in its YAML.
`--no-enrich` also disables LinkedIn description requests; other boards can still return descriptions.
Programmatic `run_pipeline()` keeps company-only behavior unless `include_ls=True` is passed.

The workbook retains global numeric Rank and adds Serial (`LS_01`, `CS_01`, etc.), Source,
and Website columns. Serials count each source independently in final score order and restart
on each export. LS includes all three boards. Source job IDs are preserved in the combined CSV.
Duplicate titles/companies are normalized for case and surrounding whitespace, with the first
configured company portal preferred over LS. Existing ranking rules and latest-export history
filtering apply to the combined dataset. Jobs retained in this workbook become the next run's
history, as before; earlier standalone LS exports are not automatically imported.

The terminal shows a spinner during listings, bars for description enrichment/LS batches,
and a final per-website table with returned rows, rows after title exclusions, ranked/new rows,
and likely-interested rows. Likely interested uses the existing title keyword rule, not a score threshold.
Returned counts include repeat LS searches and reflect any filters already inside a portal adapter;
ranked/new counts also apply final filters, current-run deduplication, and latest-export history.
`--no-progress` disables animation. Errors are reported and other sources continue.

Run offline regressions with `python -m pytest -q` (install pytest separately).

## Additional company portals (October 2026)

These sources are enabled in `config/sites.yaml` and join the same CS scraping,
filtering, enrichment and ranking pipeline. Existing LS settings are unchanged.
All nine sources use the existing rolling one-day setting; change each entry's
`posted_within_days` to expand the window, or use YAML `null` for all open roles.
An unknown publication date is excluded when a date window is enabled.

| Source | Public data source | Geographic scope |
| --- | --- | --- |
| MTU Aero Engines | [Complete HTML inventory](https://www.mtu.de/careers/online-job-market/) and job-page JSON-LD | Germany |
| Audi | [SAP OData JobSet](https://careers.audi.com/EREC_OPEN_DESTINATION/sap/opu/odata/sap/zaudi_ui_open_srv/JobSet?sap-client=200&sap-language=EN&$format=json), LocationSet hierarchy and individual JobSet records | Germany |
| Liebherr Aerospace | [Job-list API](https://www.liebherr.com/_api/app/job/list_page/en-de/0/10?detailPageId=3364214), live country/facility facets and job-page JSON-LD | German aerospace facilities |
| MAN Truck & Bus | [Public search API](https://jobs.man.eu/services/recruiting/v1/jobs), German/English inventories and HTML details | Verified German facilities |
| Volkswagen Group | [Group portal](https://jobs.volkswagen-group.com/search/), country-filtered paginated tables and HTML details | Germany, across participating Group companies |
| Diehl Aviation | [HTML search endpoint](https://new.diehl.com/career/en/vacancy/search-result?d=4&co%5B%5D=DE) and job details | Aviation division, Germany |
| KION Group | [Workday KIONGroup](https://kiongroup.wd3.myworkdayjobs.com/en-US/KIONGroup), using the existing adapter | Germany |
| Etihad Airways | [SmartRecruiters posting API](https://api.smartrecruiters.com/v1/companies/EtihadAirways5/postings) and individual postings | Germany and UAE |
| Emirates Group | [Public jobs API](https://www.emiratesgroupcareers.com/api/v1/jobs?showAll=true), including descriptions | Germany and UAE |

No Firecrawl dependency, credentials or copied browser tokens are needed at runtime.
Title exclusions apply before extra detail requests wherever the listing provides a title.
MTU and Liebherr need detail requests to obtain publication dates; other new adapters
filter dates from listings first. Etihad release timestamps populate `posted_at`;
date-only fields in the other new adapters leave it empty. Closing dates, start dates,
webpage modification times and retrieval times are not substituted for posting dates.

MAN's source does not expose country codes. Its city labels are checked against a
German facility allowlist; foreign employing entities are excluded even when a city
is incorrectly labelled (the live feed included a Dubai role labelled München).
New unrecognized locations are logged and skipped. Add a verified label through the
MAN entry's optional `germany_locations` list, or update the adapter's mapping.
German and English inventories are both scanned, and posting IDs are deduplicated.
Liebherr uses the public listing ID rather than the different internal JSON-LD ID.

The offline portal regressions use captured response shapes with synthetic text:
`python -m pytest tests/test_aviation_portals.py -q`.
Live checks verified all nine sources and detail retrieval with a one-result cap.
Audi and Volkswagen had no eligible one-day results during that check; repeating
with the date window removed verified their listing and description paths.


