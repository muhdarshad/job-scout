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

## GitHub repository

The project is hosted in the private [`muhdarshad/job-scout`](https://github.com/muhdarshad/job-scout) repository. The default branch is `main`.

The `.gitignore` excludes `.env`, local databases, virtual environments, node_modules and build output. Keep PostgreSQL backups outside the repository.


## Review filters, bulk actions and alerts

- **Experience required** lists the actual extracted text as checkbox options, including numeric and qualitative requirements. No numeric bucketing is applied.
- Check individual jobs or **Select all shown**, choose a status and press **Assign status** (maximum 1,000 per batch). A stale edit or missing record rolls back the whole batch. Notes are untouched. Changing search, filters or page clears selection. Archived jobs can be selected individually.
- **Title exclusions** accepts one literal keyword/phrase per line, no regular expressions. Defaults cover postal delivery, parcel sorting, warehouse operatives, forklift/delivery drivers, cleaning, cashier and kitchen-helper roles in German and English. Matching ignores case, normalizes umlauts/hyphens and permits common plural/gender endings. These are starter rules; remove terms that are relevant to your search.
- Existing keyword matches are hidden by default, not deleted; **Show keyword-excluded jobs** reveals them. Remove a keyword to restore visibility. New matching listings are filtered before the later description-enrichment pass; adapters that fetch detail metadata during listing still make those requests. Existing hard-coded scraper/ranker filters remain in effect.
- **Likely interested** badges and **Likely interested only** use the same title-keyword rules as the existing Excel ranker. This is a keyword signal, not an assessment of qualification or a score threshold. Exclusion matches take precedence.
- **Not fit** is added automatically to existing databases without resetting statuses, notes or schedules. **Not interested** and **Not fit** share the collapsed archive and can be restored through the job dialog.
- Cards, overview rows, archive rows and details show one timestamp: **Posted** when an exact publication time exists, otherwise **Added** using the first database entry. A date-only posting falls back to database date and time. Scrape timestamps stay internal.
- Open **Result alerts** to opt into a beep and/or desktop notification. Permission is requested only from your click. Click **Enable / test sound** after reopening a tab to satisfy browser autoplay requirements. Keep Job Scout open: this is browser polling, not background OS push delivery. New completed/partial runs alert only when they add jobs; old runs, repeated polls and zero-new-job results do not alert. Web Locks serializes claims between tabs where supported; browsers without it use best-effort localStorage deduplication. Browser/OS notification settings, Do Not Disturb and sleeping/background tabs can delay or suppress delivery.

After merging, update your checkout and rebuild without deleting the PostgreSQL volume:

```bash
git pull origin main
docker compose up --build -d
```

No destructive database migration is required: this release uses existing JSON data and settings tables. A running scrape uses the exclusions captured at its start; new settings apply on the next scrape.

Additional checks: `npm run test:unit` covers minimum-year buckets, archive categories and notification deduplication. Backend regressions cover bulk rollback, notes, existing-database upgrades, reversible title filtering and timestamp semantics. GitHub Actions runs those checks plus the scraper suite and frontend build.

## Overview and checkbox filters

Company, German requirement and experience-text filters support multiple checked values on both Discover and Applications. Empty selection means all; selected values match any option within a filter, and filters combine together. Clear filter resets one filter; Escape or clicking outside closes its menu. Assignment dropdowns still choose one status.

Industry and extracted/matched skills appear as badges on overview rows, application cards and details. Missing source values are labeled as not stated; industries are not guessed from company names.

Excel exports include the stored job description with line breaks and formula-safe text. Descriptions longer than Excel's 32,767-character cell limit continue in numbered columns. Invalid XML control characters are removed.

## Selection exports and readable job details

- **Export selected (N)** exports only checked jobs from Discover, Applications or individually checked archive rows. With no selection it is disabled. Changing filters or page clears selection. The API now requires POST /api/export with a nonempty list of job keys; the old all-jobs GET export is removed.
- Filenames use the download time in your device timezone: jobscope_HHmm_ddMMyy.xlsx (for example jobscope_1345_271026.xlsx). API callers omitting the filename use Europe/Berlin time.
- Job cards, overview rows, archive rows and details show a prominent date and time. An exact posting timestamp takes priority; date-only publications fall back to the first database entry timestamp. Refreshes never replace the first database-entry time.
- **Experience required** is a dynamic checkbox filter using the extracted field text, including qualitative requirements. It no longer filters numeric minimum-year buckets.
- **Show keyword-excluded jobs** reports saved counts and overrides the likely-interested restriction for excluded records. Search, company, German, experience and page/status restrictions still apply. Jobs skipped by collection were never stored and cannot be recovered by this switch.
- Descriptions display paragraphs, headings and bullet lists. HTML is converted to text blocks; active markup is not rendered. Existing stored descriptions benefit immediately. Long flat text is split at sentence boundaries for readability.

## Settings, undo and archive retention

- **Undo last assignment** reverses the most recent status-changing action (single edit, drag/drop or bulk assignment) as one transaction. It survives reloads, keeps notes, and rejects undo if any affected job was edited afterward. There is one undo slot for this local workspace, not per browser tab. A new assignment replaces it; deletion invalidates it.
- Applications cards show only title and company, plus the selection checkbox. Open the title for details. Discover rows retain their information with tighter spacing and wrapping.
- **Open selected links** opens unique HTTP(S) posting links from checked jobs. Browsers may block multiple tabs; the result dialog provides individual links as a fallback. Jobs without valid URLs are skipped.
- **Settings** contains company-source switches, LinkedIn/Indeed switches and search terms, skills for extraction/ranking, schedule controls, **Customize statuses**, and **Title exclusions**. Saved run preferences are captured at the next scrape. Known skill names retain the original matching patterns; custom skills use literal word matching. Built-in adapter/ranker country, freshness, title, seniority and language rules remain managed in code; the title/seniority patterns are shown read-only.
- LinkedIn previously stored dates but no repost status. The bundled scraper now captures explicit “Reposted” / “Erneut veröffentlicht” labels in listing metadata or the posting-time element. **Skip explicitly labeled LinkedIn reposts** drops only confirmed LinkedIn matches, not Indeed jobs or unknown cases. It cannot reliably detect unlabeled reposts and does not infer reposts from dates or description text. Existing unknown records are not retroactively removed. This detection has fixture coverage, not a guarantee of current live-page coverage.
- Settings and Sources show real per-source progress, with stage counts for enrichment/search batches and indeterminate bars when the source provides no total. The UI polls every three seconds. Completion and failure history remains in Sources.
- With **Delete Not interested / Not fit jobs after 24 hours** enabled (default), the worker deletes archived job records and notes on the first maintenance pass after 24 hours from assignment. Cleanup runs even with scheduling paused, but requires the worker to be running and waits for an active scrape to finish. Restoring/undoing before expiry cancels deletion. Existing archives get a fresh timer on upgrade. Disabling cleanup preserves records; re-enabling applies their existing timers.
- Only a source-identity hash remains after deletion, preventing the same identity from reappearing on the next scrape. No job text or notes are retained in that marker. A genuinely different source ID is a new job. Undo cannot recover deleted records.

Upgrade creates archive-clock and suppression-marker tables and seeds preferences/undo settings automatically. It does not delete existing jobs during startup. Do not remove your PostgreSQL volume when updating.
