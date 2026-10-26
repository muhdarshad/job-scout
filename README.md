# Job Scout — Application Studio

A local-first job discovery and application tracker. React frontend, FastAPI API, PostgreSQL database, and one scheduled Python scraping worker, packaged with Docker Compose.

## Start on your computer

1. Install and start Docker Desktop with Docker Compose support.
2. Extract this project into a new folder, separate from `custom_webscraper`.
3. Copy `.env.example` to `.env` and replace the example password with a long random alphanumeric password.
4. From this folder run:

```bash
docker compose up --build -d
```

Open `http://localhost:8000`. The database starts empty. The worker immediately runs the company scrapers, then waits 30 minutes after each run finishes. Jobs appear automatically; the interface refreshes every 15 seconds. First collection may take several minutes.

```bash
docker compose logs -f worker
docker compose stop
docker compose start
```

Your computer must remain awake and Docker must remain running. The app binds only to your computer's loopback interface. There is no cloud deployment or authentication layer. Do not expose this service publicly without adding authentication, HTTPS and appropriate deployment controls.

## Features

- Application board with Shortlisted, Applied and Interview stages.
- Add custom stages and rename stages without losing their jobs.
- Drag jobs between stages or edit their status in the details dialog.
- Persistent notes and optimistic edit conflict detection.
- Discover new jobs; filter by company, German wording and maximum explicit required years.
- Search titles, companies, locations and personal notes.
- Original descriptions and extracted requirement evidence.
- Existing personalized 0–80 ranking; scores are not probabilities.
- Excel export, including notes and statuses; scraped strings are written as text.
- Sources screen with run summaries, per-source errors, pause/resume and interval settings.
- Optional LS job boards; disabled by default for the frequent schedule. Enable in schedule settings to include the existing LinkedIn/Indeed/Google searches with their existing pacing.
- PostgreSQL volume persists jobs across container restarts.

## Existing scraper integration

`scraper/` is a source snapshot from `muhdarshad/custom_webscraper` at commit `45e7f5ee607f8a4d55297de341e0f4717a2e2205` (26 October 2026). It includes the platform adapters, JobSpy fork/license, requirement extractor, ranker and offline regression tests. Two inherited Excel integration tests now resolve columns by header instead of obsolete fixed positions. It excludes old spreadsheets, browser logs, node_modules and GitHub scheduled workflows. The previous repository has not been changed.

The worker calls `run_pipeline()` and `rank_dataframe()`. It gives the ranker a fresh temporary output directory, disabling workbook-history filtering. PostgreSQL deduplicates across runs by source plus source job ID (URL or a title/company/location fallback if absent). Scraped fields update independently of notes and application status. Source records remain distinct across portals. The existing ranker's within-run title/company deduplication and hard exclusions are preserved, including its experience/language exclusions; filters in the UI cannot recover jobs excluded by that ranker.

Edit `scraper/config/sites.yaml` and `scraper/config/jobspy.yaml` to configure sources. The config folder is mounted read-only into the worker and changes are read on subsequent runs. Existing one-day posting windows and result caps remain unchanged. Unknown dates may therefore be excluded. A long offline period can miss jobs outside these windows: widen the source windows for a catch-up run. The app does not declare jobs closed simply because they were absent from a filtered or failed scrape.

## Scheduling and storage

Compose starts the database, waits for health, starts the app and then the worker. The app creates the initial schema on first start. PostgreSQL advisory locking allows only one scheduled worker. Runs are sequential; scheduled cadence is measured from completion to avoid overlap. Manual requests coalesce into one pending run. On restart, an unfinished run is marked Interrupted. Failures are recorded and retried at the configured interval.

Tables: `jobs` (source data, status, notes, version, first/last seen), `settings` (schedule and statuses), `runs` (history and per-source statistics). This is the initial schema; a versioned migration system is required before changing deployed schemas. The worker currently repeats description enrichment on each collection; incremental per-job detail caching is a follow-up optimization. No push feed is available through these adapters.

## Backup

The named PostgreSQL volume survives normal stop/start and `docker compose down`. **Do not use `docker compose down -v` unless you intend to delete the database.**

Create a backup inside the container and copy it out (works without shell redirection encoding issues on Windows):

```bash
docker compose exec db pg_dump -U scout -d jobscout -Fc -f /tmp/jobscout.dump
docker compose cp db:/tmp/jobscout.dump ./jobscout.dump
```

## Development and tests

Python 3.12 and Node 22 are used by the Docker build.

```bash
python -m venv .venv
# Activate .venv (Windows: .venv\Scripts\activate; macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
pip install pytest httpx
npm ci
python -m pytest tests/test_app.py -q
# Run scraper tests from their own root:
cd scraper
python -m pytest tests -q
```

For a local UI preview without Docker, use SQLite and explicit sample data:

```bash
# macOS/Linux:
DEMO_MODE=1 uvicorn backend.api:app --port 8000
# Windows PowerShell:
# $env:DEMO_MODE='1'; uvicorn backend.api:app --port 8000
```

In another terminal run `npm run dev`. Demo data only seeds an empty database; it never silently appears in the normal Docker database. Demo scraping is disabled. User edits persist in `preview.db`. The scheduled worker requires PostgreSQL and refuses SQLite.

## Validation and current limits

- Frontend production build and API tests were run in the development workspace.
- Browser visual verification was blocked by the workspace browser security policy. See `design-qa.md`; the UI is not claimed to be visually verified.
- Docker is unavailable in that workspace; the complete Compose startup and PostgreSQL advisory-lock behavior must be verified on your computer.
- Live portals were not scraped during development. Adapter behavior can change externally.
- The API currently returns all retained jobs for client-side filtering. Add server-side pagination/indexed query columns when your database grows substantially.
- Logos are small website favicons used for identification; they differ from the larger wordmarks in the concept image. See `public/logos/SOURCES.md`.

## Create the new GitHub repository

No new GitHub repository was created automatically: the available connector supports file/branch/PR operations but does not expose repository creation, and no authenticated GitHub CLI is available here.

Create an empty **private** repository named `job-scout` under your account, without a README or .gitignore, then run these commands from this project folder:

```bash
git init
git add .
git commit -m "Build local job discovery and application tracker"
git branch -M main
git remote add origin https://github.com/muhdarshad/job-scout.git
git push -u origin main
```

The `.gitignore` excludes `.env`, local databases, virtual environments, node_modules and build output. Keep PostgreSQL backups outside the repository.
