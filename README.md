# Job Scout

A local-first job discovery and application tracker. Job Scout regularly scrapes company career portals (Airbus, Lufthansa, BMW, Siemens, Bosch and more) and, optionally, LinkedIn and Indeed. It ranks the results and lets you review, filter and track applications in your browser.

It runs as a React frontend, a FastAPI backend, a PostgreSQL database and a scheduled Python scraping worker, all started together with Docker Compose.

## Tech stack

| Layer | Tools |
| --- | --- |
| Frontend | React 19, Vite, plain CSS, Phosphor Icons, browser Notification and Web Locks APIs |
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2 |
| Database | PostgreSQL 17 (SQLite for demo mode) |
| Scraping and data | Requests, BeautifulSoup, pandas, PyYAML, a vendored JobSpy fork (LinkedIn/Indeed) |
| Export | openpyxl (Excel) |
| DevOps | Docker, Docker Compose (multi-stage build, health checks), GitHub Actions CI |
| Testing | pytest, httpx, Node test runner |

## Engineering highlights

- **20+ scraper adapters** for company career portals (Workday, SuccessFactors, custom APIs and HTML pages) that all produce one common job schema. They run in parallel with a thread pool and are paced to avoid overloading the sites.
- **NLP-style requirement extraction**: German level, years of experience and skills are pulled out of free-text descriptions in German and English, then fed into a personalized ranking.
- **One scheduled worker at a time**: a PostgreSQL advisory lock stops two workers from scraping at once. Runs are spaced from when the last one finished, and an unfinished run is marked *Interrupted* after a restart.
- **Edits don't overwrite each other**: each job has a version number, so a stale edit is rejected instead of silently replacing a newer one. Bulk status changes and undo succeed or fail as a whole.
- **Duplicate-free storage**: jobs are keyed by source and source ID, so scraped fields refresh while your notes and statuses stay. Deleted jobs leave only a hash marker, which stops them from coming back.
- **Rules you can edit at runtime**: the scraper filters used to be hard-coded. They are now validated regular-expression lists that you change from the UI.
- **Safe Excel export**: scraped text is written in a way that can't turn into spreadsheet formulas, and long descriptions are split across cells.
- **Runs only on your machine**: Docker Compose binds the app to localhost, runs it as a non-root container user and keeps the database in a persistent volume. CI runs the backend, scraper and frontend tests on every push.

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS or Linux), installed and running
- [Git](https://git-scm.com/downloads) to download the project (or download the ZIP from GitHub)

## Quick start

1. **Download the project**

   ```bash
   git clone https://github.com/muhdarshad/job-scout.git
   cd job-scout
   ```

2. **Create your environment file**

   ```bash
   # macOS/Linux
   cp .env.example .env
   # Windows PowerShell
   Copy-Item .env.example .env
   ```

   Open `.env` and replace the example `POSTGRES_PASSWORD` with a long random alphanumeric password.

3. **Build and start everything**

   ```bash
   docker compose up --build -d
   ```

   The first build takes a few minutes.

4. **Open the app** at <http://localhost:8000>.

The database starts empty. The worker runs its first scrape right away, which can take several minutes, and then runs again 30 minutes after each scrape finishes. New jobs appear on their own because the page refreshes automatically.

Scraping only happens while your computer is awake and Docker is running.

## Everyday commands

| Task | Command |
| --- | --- |
| Follow scraper logs | `docker compose logs -f worker` |
| Stop the app | `docker compose stop` |
| Start it again | `docker compose start` |
| Update to the latest version | `git pull` then `docker compose up --build -d` |

Your data is stored in a Docker volume and survives stops, restarts, updates and `docker compose down`.

> **Warning:** `docker compose down -v` deletes the database volume and all your jobs and notes.

### Backup

```bash
docker compose exec db pg_dump -U scout -d jobscout -Fc -f /tmp/jobscout.dump
docker compose cp db:/tmp/jobscout.dump ./jobscout.dump
```

Keep backups outside the repository (`*.dump` is already git-ignored).

## Features

- **Discover**: review new jobs. Filter by company, source (`CS` = company site, `LS` = LinkedIn/Indeed job board), German requirement and required experience. Search titles, companies, locations and notes.
- **Applications board**: move jobs between Shortlisted, Applied and Interview by dragging them or from the details dialog. You can add and rename stages, and **Undo last assignment** reverses the last status change.
- **Job details**: shows the original description, the requirements extracted from it, matched skills and a personalized 0–80 ranking. The ranking is a relevance score, not a probability.
- **Bulk actions**: select jobs to assign a status, open their links, or **Export selected** to Excel. The export includes notes, statuses and full descriptions.
- **Archive**: *Not interested* and *Not fit* jobs are collapsed into an archive. They are deleted automatically after 24 hours, and you can turn that off in Settings.
- **Result alerts**: you can opt into a sound or desktop notification when a scrape finds new jobs. Alerts only work while the tab is open.
- **Sources**: shows run history, live progress, per-source errors and pause/resume controls.

## Configuration

Most options are in the app's **Settings** screen:

- turn individual company sources and LinkedIn/Indeed on or off, and edit search terms
- set the skills used for extraction and ranking
- set the scrape schedule and interval
- customize the application statuses
- set **Title exclusions**: plain keywords that hide unwanted jobs, which you can reveal again with *Show keyword-excluded jobs*
- edit the **Built-in scraper filters**: the regular expressions for excluded titles, seniority levels, requirements and "likely interested" keywords. Each list can be reset to its defaults, which live in `scraper/job_rules.py`

Settings take effect on the next scrape. Jobs that are already stored are not removed retroactively.

The scrape country, posting window and result caps are in `scraper/config/sites.yaml` and `scraper/config/jobspy.yaml`, and the worker reads them on every run. The default posting window is one day. If the app has been offline for a long time, widen these windows for one catch-up run.

## Development

You need Python 3.12 and Node.js 22.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt pytest httpx
npm ci
```

**Run without Docker (demo mode).** This uses a local SQLite database (`preview.db`) filled with sample data. Scraping is disabled.

```bash
# macOS/Linux
DEMO_MODE=1 uvicorn backend.api:app --port 8000
# Windows PowerShell
$env:DEMO_MODE='1'; uvicorn backend.api:app --port 8000
```

In a second terminal, run `npm run dev` and open the URL it prints (usually <http://localhost:5173>). The scheduled worker needs PostgreSQL, so use Docker for real scraping.

**Tests** (GitHub Actions also runs these on every push):

```bash
python -m pytest tests/test_app.py -q
cd scraper && python -m pytest tests -q && cd ..
npm run test:unit
npm run build
npm run test:sites
```

## Project layout

```
backend/     FastAPI API, database models and scheduled worker
src/         React frontend
scraper/     Scraper platforms, JobSpy fork, requirement extractor and ranker
scraper/config/  Source configuration (sites.yaml, jobspy.yaml)
tests/       Backend and frontend tests
```

## Notes and limitations

- The app is reachable only from your own computer (`127.0.0.1`) and has no login. Do not expose it to a network or the internet without adding authentication and HTTPS.
- Career portals change without notice, so individual scrapers can break. Check the **Sources** screen for per-source errors.
- All jobs are loaded into the browser for filtering. A very large database may need server-side pagination.
- Company logos are small website favicons. See `public/logos/SOURCES.md` for where they came from.

## License

[MIT](LICENSE). The bundled JobSpy fork is under its own license in `scraper/vendor/JobSpy/LICENSE`.
