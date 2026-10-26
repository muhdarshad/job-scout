"""Description enrichment for job postings."""

import time
from tqdm.auto import tqdm
import pandas as pd

from ..config import ENRICH_DELAY, WORKDAY_SITES, OTHER_SITES
from ..platforms import get_platform


def enrich_descriptions(df: pd.DataFrame, delay: float = ENRICH_DELAY, workday_sites=None, other_sites=None, progress_callback=None) -> pd.DataFrame:
    """
    Fill in 'description' (and other fields) for any row
    where description is still empty. Dispatches to the right fetcher
    based on which platform the job_url belongs to. Mutates and returns
    the same DataFrame.
    """
    workday_sites = WORKDAY_SITES if workday_sites is None else workday_sites
    other_sites = OTHER_SITES if other_sites is None else other_sites
    rows_to_enrich = [idx for idx, row in df.iterrows()
                      if pd.isna(row.get("description")) or not row.get("description")]
    total = len(rows_to_enrich)

    if total == 0:
        return df

    for i, idx in enumerate(tqdm(rows_to_enrich, desc="Enriching job descriptions", unit="job", disable=progress_callback is not None)):
        row = df.loc[idx]
        url = row.get("job_url") or ""
        result = None

        try:
            if "myworkdayjobs.com" in url:
                site_cfg = next(
                    (s for s in workday_sites if s["company"] == row["company"]), None
                )
                if site_cfg:
                    platform = get_platform("workday")
                    if platform:
                        result = platform.fetch_job_detail(
                            url, site_cfg["tenant"], site_cfg["cluster"], site_cfg["site"]
                        )
            elif "mercedes-benz.com" in url:
                platform = get_platform("mercedes_successfactors")
                if platform:
                    desc = platform.fetch_job_detail(url)
                    result = {"description": desc} if desc else None
            elif "jobs.siemens-energy.com" in url:
                platform = get_platform("siemens_energy")
                if platform:
                    result = platform.fetch_job_detail(url)
            elif "apply.lufthansagroup.careers" in url:
                platform = get_platform("lufthansa")
                if platform:
                    result = platform.fetch_job_detail(url)
            elif "alten-consulting.de/karriere/stelle/" in url:
                platform = get_platform("alten")
                if platform:
                    result = platform.fetch_job_detail(url)
            elif "bmwgroup.jobs/" in url:
                platform = get_platform("bmw")
                if platform:
                    result = platform.fetch_job_detail(url)
            elif "jobs.bosch.com/" in url:
                platform = get_platform("bosch")
                site_cfg = next((s for s in other_sites if s.get("platform") == "bosch"), None)
                if platform and site_cfg:
                    result = platform.fetch_job_detail(url, site_cfg)
            else:
                site_cfg = next((s for s in other_sites if s.get("company") == row["company"]
                                 and s.get("platform") in {"n3", "honeywell", "boeing", "everllence", "siemens_ag", "dhl",
                                                           "mtu", "audi", "liebherr", "volkswagen", "diehl", "smartrecruiters", "emirates", "man"}), None)
                if site_cfg:
                    result = get_platform(site_cfg["platform"]).fetch_job_detail(url, site_cfg)
        except Exception as exc:
            print(f"    ! Description enrichment failed for {url}: {type(exc).__name__}: {exc}. Continuing.")

        if result:
            for field in [
                "id",
                "title",
                "company",
                "location",
                "date_posted",
                "posted_at",
                "job_type",
                "job_level",
                "job_function",
                "description",
                "company_industry",
            ]:
                if result.get(field) is not None:
                    if field in df and df[field].dtype.kind != "O":
                        df[field] = df[field].astype(object)
                    df.at[idx, field] = result[field]

        if progress_callback:
            progress_callback(i + 1, total)
        time.sleep(delay)

    return df


