"""
ExecSearch AI - Multi-Source Job Scout
Searches Google, niche job boards, direct company career pages, and public APIs
for QA/QC roles in Aerospace, Defence, and Precision Manufacturing.

Targets: US, UK, Europe, Australia, New Zealand, India
Focus: Places where people DON'T usually apply (low competition, high response rate)
"""

import os
import re
import logging
import requests
from typing import List, Dict, Any, Optional
from time import sleep
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# SEARCH CONFIGURATION
# ============================================================

# QA/QC focused keywords (what your dad is best at)
SEARCH_QUERIES = [
    "QA QC Manager aerospace",
    "Quality Assurance Manager aerospace defence",
    "Quality Control Manager manufacturing",
    "AS9100 Quality Manager",
    "Head Quality Assurance aerospace",
    "Senior Quality Engineer aerospace",
    "Quality Manager precision engineering",
    "QA QC Lead CNC machining",
    "Supplier Quality Manager aerospace",
    "Quality Assurance Manager defence",
    "Plant Quality Manager manufacturing",
    "Quality Systems Manager AS9100D",
    "Quality Manager MRO aerospace",
]

# Target countries
TARGET_LOCATIONS = [
    "India", "Bangalore",
    "United States", "USA",
    "United Kingdom", "UK",
    "Germany", "Netherlands", "France",  # Europe
    "Australia", "New Zealand",
    "UAE", "Dubai", "Saudi Arabia", "Qatar",  # Middle East bonus
    "Singapore",
    "Remote",
]

# Junior titles to filter OUT
JUNIOR_KEYWORDS = [
    'intern', 'internship', 'junior', 'entry level', 'entry-level',
    'fresher', 'trainee', 'graduate', 'associate', 'jr.', 'jr ',
    'student', 'apprentice', 'co-op',
]


def _fetch_with_retry(url: str, params: Optional[Dict] = None,
                      headers: Optional[Dict] = None, timeout: int = 15) -> Optional[requests.Response]:
    """Fetches a URL with one retry on failure."""
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt == 0:
                sleep(2)
    return None


# ============================================================
# SOURCE 1: GOOGLE JOBS SEARCH (via SerpAPI or fallback scraping)
# ============================================================
def fetch_google_jobs(queries: List[str], locations: List[str]) -> List[Dict[str, Any]]:
    """
    Search Google for jobs using SerpAPI (if SERPAPI_KEY is set) or
    Google Custom Search API (if GOOGLE_CSE_KEY and GOOGLE_CSE_ID are set).
    Falls back to constructing direct Google search URLs for manual use.
    """
    jobs = []

    serpapi_key = os.environ.get("SERPAPI_KEY")
    google_cse_key = os.environ.get("GOOGLE_CSE_KEY")
    google_cse_id = os.environ.get("GOOGLE_CSE_ID")

    if serpapi_key:
        # SerpAPI Google Jobs endpoint — fail fast on first timeout
        serpapi_ok = True
        for query in queries[:3]:  # Only 3 queries to conserve free quota
            if not serpapi_ok:
                break
            for loc in ["India", "United States", "United Kingdom"]:
                if not serpapi_ok:
                    break
                url = "https://serpapi.com/search.json"
                params = {
                    "engine": "google_jobs",
                    "q": query,
                    "location": loc,
                    "api_key": serpapi_key,
                }
                try:
                    resp = requests.get(url, params=params, timeout=8)
                    resp.raise_for_status()
                    data = resp.json()
                    for item in data.get("jobs_results", []):
                        jobs.append({
                            "id": f"google_{hash(item.get('title','') + item.get('company_name',''))}",
                            "title": item.get("title", ""),
                            "company": item.get("company_name", ""),
                            "url": item.get("share_link", item.get("related_links", [{}])[0].get("link", "") if item.get("related_links") else ""),
                            "description": item.get("description", ""),
                            "source": "Google Jobs",
                            "location": item.get("location", loc),
                            "salary_info": item.get("detected_extensions", {}).get("salary", ""),
                        })
                except requests.Timeout:
                    logger.warning("SerpAPI timed out. Skipping Google Jobs entirely for this run.")
                    serpapi_ok = False
                    break
                except Exception as e:
                    logger.warning(f"SerpAPI error: {e}. Skipping.")
                    serpapi_ok = False
                    break
        logger.info(f"Google Jobs (SerpAPI) returned {len(jobs)} jobs.")

    elif google_cse_key and google_cse_id:
        # Google Custom Search API (searching job sites)
        for query in queries[:5]:
            search_q = f"{query} site:indeed.com OR site:glassdoor.com OR site:linkedin.com/jobs OR site:seek.com.au"
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": google_cse_key,
                "cx": google_cse_id,
                "q": search_q,
                "num": 10,
            }
            resp = _fetch_with_retry(url, params=params)
            if resp:
                try:
                    data = resp.json()
                    for item in data.get("items", []):
                        title = item.get("title", "")
                        jobs.append({
                            "id": f"gcse_{hash(title + item.get('link',''))}",
                            "title": title,
                            "company": item.get("displayLink", ""),
                            "url": item.get("link", ""),
                            "description": item.get("snippet", ""),
                            "source": "Google Search",
                            "location": "",
                            "salary_info": "",
                        })
                except Exception as e:
                    logger.error(f"Error parsing Google CSE response: {e}")
        logger.info(f"Google CSE returned {len(jobs)} jobs.")

    else:
        # No API keys - generate Google search URLs for manual use
        logger.info("No Google API keys set. Generating manual search URLs instead.")
        print("\n   📎 Tip: Open these Google search URLs in your browser to find hidden jobs:")
        for query in queries[:3]:
            encoded = quote_plus(f"{query} hiring now")
            url = f"https://www.google.com/search?q={encoded}&ibp=htl;jobs"
            print(f"      🔗 {url}")
        print()

    return jobs


# ============================================================
# SOURCE 2: REMOTIVE (Remote tech & operations jobs)
# ============================================================
def fetch_remotive(queries: List[str]) -> List[Dict[str, Any]]:
    """Fetches remote jobs from Remotive API."""
    jobs = []
    url = "https://remotive.com/api/remote-jobs"
    for kw in queries[:4]:
        resp = _fetch_with_retry(url, params={"search": kw})
        if resp:
            try:
                for job in resp.json().get("jobs", []):
                    jobs.append({
                        "id": f"remotive_{job.get('id')}",
                        "title": job.get("title", ""),
                        "company": job.get("company_name", ""),
                        "url": job.get("url", ""),
                        "description": job.get("description", ""),
                        "source": "Remotive",
                        "location": job.get("candidate_required_location", "Remote"),
                        "salary_info": job.get("salary", ""),
                    })
            except Exception as e:
                logger.error(f"Remotive parse error: {e}")
    logger.info(f"Remotive returned {len(jobs)} jobs.")
    return jobs


# ============================================================
# SOURCE 3: ARBEITNOW (Europe-focused jobs)
# ============================================================
def fetch_arbeitnow(queries: List[str]) -> List[Dict[str, Any]]:
    """Fetches jobs from Arbeitnow (strong in Germany/Europe)."""
    jobs = []
    resp = _fetch_with_retry("https://www.arbeitnow.com/api/job-board-api")
    if resp:
        try:
            for job in resp.json().get("data", []):
                title = job.get("title", "")
                desc = job.get("description", "")
                if any(kw.lower() in (title + " " + desc).lower() for kw in queries):
                    jobs.append({
                        "id": f"arbeitnow_{job.get('slug', '')}",
                        "title": title,
                        "company": job.get("company_name", ""),
                        "url": job.get("url", ""),
                        "description": desc,
                        "source": "Arbeitnow (Europe)",
                        "location": job.get("location", ""),
                        "salary_info": "",
                    })
        except Exception as e:
            logger.error(f"Arbeitnow parse error: {e}")
    logger.info(f"Arbeitnow returned {len(jobs)} jobs.")
    return jobs


# ============================================================
# SOURCE 4: ADZUNA (India, UK, US, AU, NZ, DE)
# ============================================================
def fetch_adzuna(queries: List[str]) -> List[Dict[str, Any]]:
    """Fetches jobs from Adzuna across multiple countries."""
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        logger.info("Adzuna credentials not set (ADZUNA_APP_ID / ADZUNA_APP_KEY). Skipping.")
        return []

    jobs = []
    # Country codes: in=India, gb=UK, us=US, au=Australia, nz=New Zealand, de=Germany
    countries = ["in", "gb", "us", "au", "nz", "de"]
    for country in countries:
        for kw in queries[:3]:
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            params = {"app_id": app_id, "app_key": app_key, "what": kw, "results_per_page": 25}
            resp = _fetch_with_retry(url, params=params)
            if resp:
                try:
                    for job in resp.json().get("results", []):
                        sal = ""
                        if job.get("salary_min"):
                            sal = f"Min: {job['salary_min']} Max: {job.get('salary_max', 'N/A')}"
                        jobs.append({
                            "id": f"adzuna_{job.get('id')}",
                            "title": job.get("title", ""),
                            "company": job.get("company", {}).get("display_name", ""),
                            "url": job.get("redirect_url", ""),
                            "description": job.get("description", ""),
                            "source": f"Adzuna ({country.upper()})",
                            "location": job.get("location", {}).get("display_name", ""),
                            "salary_info": sal,
                        })
                except Exception as e:
                    logger.error(f"Adzuna parse error ({country}): {e}")
    logger.info(f"Adzuna returned {len(jobs)} jobs.")
    return jobs


# ============================================================
# SOURCE 5: JSEARCH / RAPIDAPI (Aggregator: Indeed, Glassdoor, LinkedIn, ZipRecruiter)
# ============================================================
def fetch_jsearch(queries: List[str], locations: List[str]) -> List[Dict[str, Any]]:
    """Fetches jobs from JSearch (RapidAPI) - aggregates Indeed, Glassdoor, LinkedIn etc."""
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        logger.info("JSearch (RapidAPI) key not set (RAPIDAPI_KEY). Skipping.")
        return []

    jobs = []
    headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    for kw in queries[:4]:
        for loc in ["India", "United States", "United Kingdom", "Australia"]:
            params = {"query": f"{kw} in {loc}", "page": "1", "num_pages": "1"}
            resp = _fetch_with_retry("https://jsearch.p.rapidapi.com/search", params=params, headers=headers)
            if resp:
                try:
                    for job in resp.json().get("data", []):
                        sal = ""
                        if job.get("job_min_salary"):
                            sal = f"Min: {job['job_min_salary']} Max: {job.get('job_max_salary', 'N/A')}"
                        jobs.append({
                            "id": f"jsearch_{job.get('job_id')}",
                            "title": job.get("job_title", ""),
                            "company": job.get("employer_name", ""),
                            "url": job.get("job_apply_link", ""),
                            "description": job.get("job_description", ""),
                            "source": "JSearch",
                            "location": f"{job.get('job_city', '')}, {job.get('job_country', '')}",
                            "salary_info": sal,
                        })
                except Exception as e:
                    logger.error(f"JSearch parse error: {e}")
    logger.info(f"JSearch returned {len(jobs)} jobs.")
    return jobs


# ============================================================
# SOURCE 6: DIRECT NICHE / HIDDEN PORTALS (Static curated list)
# These are places where most people DON'T apply
# ============================================================
def get_hidden_portal_links() -> List[Dict[str, str]]:
    """
    Returns curated links to niche, low-competition portals and direct career pages
    that most candidates overlook. These should be opened in the browser manually.
    """
    return [
        # India niche
        {"name": "Instahyre (India - Curated)", "url": "https://www.instahyre.com/search-jobs/?q=quality+assurance+aerospace"},
        {"name": "Cutshort (India - Direct Founders)", "url": "https://cutshort.io/jobs?q=quality+assurance"},
        {"name": "Hirist (India - Senior Tech)", "url": "https://www.hirist.tech/search?q=quality+manager"},
        # Middle East
        {"name": "Naukri Gulf (UAE/Saudi)", "url": "https://www.naukrigulf.com/quality-assurance-jobs"},
        {"name": "Bayt (Middle East)", "url": "https://www.bayt.com/en/international/jobs/quality-assurance-jobs/"},
        {"name": "GulfTalent (Executive)", "url": "https://www.gulftalent.com/jobs/quality-assurance"},
        # Global Aerospace
        {"name": "FlightGlobal Jobs (Aerospace)", "url": "https://jobs.flightglobal.com/?q=quality"},
        {"name": "Aviation Job Search", "url": "https://www.aviationjobsearch.com/search?q=quality+assurance"},
        # UK
        {"name": "Reed UK (Quality)", "url": "https://www.reed.co.uk/jobs/quality-assurance-aerospace"},
        {"name": "TotalJobs UK", "url": "https://www.totaljobs.com/jobs/quality-assurance-aerospace"},
        # Australia / NZ
        {"name": "SEEK Australia", "url": "https://www.seek.com.au/quality-assurance-aerospace-jobs"},
        {"name": "Trade Me Jobs NZ", "url": "https://www.trademe.co.nz/a/jobs/search?search_string=quality+assurance+manufacturing"},
        # US
        {"name": "USAJobs (US Govt/Defence)", "url": "https://www.usajobs.gov/search?k=quality+assurance+aerospace"},
        {"name": "ClearanceJobs (US Defence)", "url": "https://www.clearancejobs.com/jobs?keywords=quality+assurance+aerospace"},
        # Europe
        {"name": "EuroJobs (Europe)", "url": "https://eurojobs.com/search?q=quality+assurance+manufacturing"},
        {"name": "StepStone Germany", "url": "https://www.stepstone.de/jobs/quality-assurance-aerospace"},
        # Direct company career pages (Tier-1 Aerospace)
        {"name": "Safran Careers", "url": "https://www.safran-group.com/jobs?query=quality"},
        {"name": "Collins Aerospace Careers", "url": "https://careers.rtx.com/global/en/search-results?keywords=quality%20assurance%20aerospace"},
        {"name": "Honeywell Careers", "url": "https://careers.honeywell.com/us/en/search-results?keywords=quality%20aerospace"},
        {"name": "EDGE Group UAE", "url": "https://www.edgegroup.ae/careers"},
        {"name": "ST Engineering Singapore", "url": "https://www.stengg.com/careers"},
    ]


# ============================================================
# FILTERS & DEDUP
# ============================================================
def filter_senior_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters out junior/intern/entry-level jobs."""
    filtered = []
    for job in jobs:
        title_lower = job.get("title", "").lower()
        if not any(kw in title_lower for kw in JUNIOR_KEYWORDS):
            filtered.append(job)
    removed = len(jobs) - len(filtered)
    if removed > 0:
        logger.info(f"Filtered out {removed} junior/intern positions.")
    return filtered


def deduplicate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicates jobs by title+company."""
    seen = set()
    deduped = []
    for job in jobs:
        key = f"{job.get('title','').strip().lower()}||{job.get('company','').strip().lower()}"
        if key not in seen:
            seen.add(key)
            deduped.append(job)
    return deduped


# ============================================================
# MAIN SCOUT FUNCTION
# ============================================================
def scout_jobs(queries: Optional[List[str]] = None,
               locations: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Scouts jobs across ALL sources:
    1. Google Jobs (via SerpAPI or Google CSE)
    2. Remotive (remote jobs)
    3. Arbeitnow (Europe)
    4. Adzuna (India, UK, US, AU, NZ, DE)
    5. JSearch/RapidAPI (Indeed, Glassdoor, LinkedIn aggregator)

    Also prints hidden portal links for manual browsing.
    """
    kw = queries or SEARCH_QUERIES
    loc = locations or TARGET_LOCATIONS

    all_jobs: List[Dict[str, Any]] = []

    print("\n   🔍 Searching across multiple job sources...\n")

    # Source 1: Google
    google_jobs = fetch_google_jobs(kw, loc)
    all_jobs.extend(google_jobs)

    # Source 2: Remotive
    remotive_jobs = fetch_remotive(kw)
    all_jobs.extend(remotive_jobs)

    # Source 3: Arbeitnow
    arbeitnow_jobs = fetch_arbeitnow(kw)
    all_jobs.extend(arbeitnow_jobs)

    # Source 4: Adzuna
    adzuna_jobs = fetch_adzuna(kw)
    all_jobs.extend(adzuna_jobs)

    # Source 5: JSearch
    jsearch_jobs = fetch_jsearch(kw, loc)
    all_jobs.extend(jsearch_jobs)

    # Filter and deduplicate
    senior_jobs = filter_senior_jobs(all_jobs)
    final_jobs = deduplicate_jobs(senior_jobs)

    logger.info(f"Total: {len(all_jobs)} raw -> {len(senior_jobs)} senior -> {len(final_jobs)} unique jobs.")

    # Print hidden portals for manual exploration
    portals = get_hidden_portal_links()
    print(f"\n   🌐 {len(portals)} hidden/niche portals available (low competition):")
    print("   Use these for manual browsing — most candidates never check these:\n")
    for p in portals[:8]:
        print(f"      • {p['name']}: {p['url']}")
    print(f"      ... and {len(portals) - 8} more. Run scout.py directly to see all.\n")

    return final_jobs


if __name__ == "__main__":
    print("=" * 60)
    print("ExecSearch AI - Job Scout (Standalone Test)")
    print("=" * 60)
    jobs = scout_jobs()
    print(f"\nFound {len(jobs)} jobs total.\n")
    for j in jobs[:10]:
        print(f"  [{j['source']}] {j['title']} at {j['company']} ({j['location']})")

    print(f"\n\nAll {len(get_hidden_portal_links())} hidden portal links:")
    for p in get_hidden_portal_links():
        print(f"  • {p['name']}: {p['url']}")
