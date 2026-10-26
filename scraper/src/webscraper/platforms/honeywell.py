"""Honeywell's Oracle Recruiting public API."""

import time
from urllib.parse import urlparse

from ..config import REQUEST_DELAY
from ..utils import strip_html
from .career import CareerPlatform, candidate, career_session, german, parse_date, parse_timestamp, recent


HONEYWELL_API = "https://ibqbjb.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest"


class HoneywellPlatform(CareerPlatform):
    def fetch_jobs(self, site_config, max_results=None):
        results, seen, offset = [], set(), 0
        size = site_config.get("page_size", 100)
        with career_session() as session:
            while True:
                finder = f"findReqs;siteNumber=CX_1,location=Germany,limit={size},offset={offset},sortBy=POSTING_DATES_DESC"
                response = session.get(f"{HONEYWELL_API}/recruitingCEJobRequisitions", params={
                    "onlyData": "true", "finder": finder,
                    "expand": "requisitionList.workLocation,requisitionList.otherWorkLocations,requisitionList.secondaryLocations",
                }, headers={"ora-irc-language": "en", "Accept-Language": "en"}, timeout=25)
                response.raise_for_status()
                search = response.json()["items"][0]
                listings = search.get("requisitionList", [])
                if not listings:
                    break
                fresh = 0
                for raw in listings:
                    job_id = str(raw["Id"])
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    fresh += 1
                    countries = [raw.get("PrimaryLocationCountry")] + [x.get("CountryCode") for x in raw.get("secondaryLocations", [])]
                    if not any(german(c) for c in countries) or not candidate(raw.get("Title"), site_config) or not recent(raw.get("PostedDate"), site_config):
                        continue
                    results.append(self.normalize_job(self._job(raw, site_config), site_config))
                    if max_results is not None and len(results) >= max_results:
                        return results
                offset += len(listings)
                dates = [parse_date(x.get("PostedDate")) for x in listings]
                if not fresh or offset >= search["TotalJobsCount"] or (site_config.get("posted_within_days") is not None and all(dates) and not any(recent(x.get("PostedDate"), site_config) for x in listings)):
                    break
                time.sleep(REQUEST_DELAY)
        return results

    @staticmethod
    def _job(raw, config):
        locations = [x.get("Name") for x in raw.get("secondaryLocations", []) if german(x.get("CountryCode"))]
        if german(raw.get("PrimaryLocationCountry")):
            locations.insert(0, raw.get("PrimaryLocation"))
        return {
            "id": raw["Id"], "title": raw.get("Title"),
            "job_url": f"{config.get('detail_base_url', 'https://careers.honeywell.com/en/sites/Honeywell/job')}/{raw['Id']}",
            "location": "; ".join(filter(None, locations)), "date_posted": raw.get("PostedDate") or raw.get("ExternalPostedStartDate"),
            "posted_at": raw.get("ExternalPostedStartDate"),
            "job_type": raw.get("JobSchedule"), "job_level": raw.get("JobLevel") or raw.get("RequisitionType"),
            "job_function": raw.get("Category") or raw.get("JobFunction"),
        }

    def fetch_job_detail(self, job_url, site_config=None, session=None):
        job_id = urlparse(job_url).path.rstrip("/").split("/")[-1]
        client = session or career_session()
        try:
            response = client.get(f"{HONEYWELL_API}/recruitingCEJobRequisitionDetails", params={
                "onlyData": "true", "expand": "all", "finder": f'ById;Id="{job_id}",siteNumber=CX_1',
            }, headers={"ora-irc-language": "en", "Accept-Language": "en"}, timeout=25)
            response.raise_for_status()
            raw = response.json()["items"][0]
            job = self._job(raw, site_config or {})
            job["description"] = strip_html(" ".join(raw.get(k) or "" for k in (
                "ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr",
            )))
            posted = parse_date(job["date_posted"])
            job["date_posted"] = posted.isoformat() if posted else None
            job["posted_at"] = parse_timestamp(job.get("posted_at"))
            return job
        finally:
            if session is None:
                client.close()

