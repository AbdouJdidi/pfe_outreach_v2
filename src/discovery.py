import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from .config import settings
from .db import connect, upsert_company

QUERIES = [
    # Europe / international
    "software companies Europe DevOps",
    "software companies Europe cloud",
    "AI companies Europe",
    "European software startups",
    "European technology startups",

    # Internships / PFE signals
    "software engineering internship Europe",
    "DevOps internship Europe",
    "cloud engineering internship Europe",
    "AI engineering internship Europe",

    # Tunisia
    "software companies Sousse Tunisia",
    "IT companies Sousse Tunisia",
    "startups Sousse Tunisia",
    "Sousse Technopole companies",

    "software companies Tunis Tunisia",
    "IT companies Tunis Tunisia",
    "startups Tunis Tunisia",
]

BLOCKED_DOMAINS = {
    # Job boards
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "wellfound.com",
    "remotive.com",
    "remoteok.com",
    "simplyhired.com",
    "jooble.org",
    "upwork.com",
    "fiverr.com",
    "workingnomads.com",
    "euremotejobs.com",
    "startup.jobs",
    "erasmusintern.org",
    "tech-internships.eu",
    "totaljobs.com",

    # Social
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",

    # Directories / startup databases
    "f6s.com",
    "crunchbase.com",
    "aeroleads.com",
    "rentechdigital.com",
    "cybo.com",
    "techbehemoths.com",
    "startupblink.com",
    "startuplist.africa",
    "startup.gov.tn",
    "tunisiayp.com",
    "businessdirectorylists.com",
    "findglocal.com",
    "goodfirms.co",
    "themanifest.com",
    "elioplus.com",
    "info-clipper.com",

    # Startup / tech media
    "sourceforge.net",
    "slashdot.org",
    "medium.com",
    "sifted.eu",
    "siliconcanals.com",
    "technicalbeep.com",
    "officechai.com",
    "ceo-review.com",
    "top10grid.com",
    "en.arageek.com",

    # Search / general information
    "google.com",
    "bing.com",
    "yahoo.com",
    "github.com",
    "wikipedia.org",

    # Startup / ecosystem platforms
    "ycombinator.com",
    "europe-startup-guide.com",
    "europeantechmap.eu",
    "european-alternatives.eu",
    "eu-startups.com",
    "dealroom.co",
    "seedtable.com",

    # Government / organizations / institutions
    "aiesec.org",
    "cdc.tn",
    "eit.edu.au",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/154.0 Safari/537.36"
)


def normalize_domain(url):
    """Extract a clean domain from a URL."""

    try:
        parsed = urlparse(url)

        host = parsed.netloc.lower().split(":")[0]

        if host.startswith("www."):
            host = host[4:]

        if not host or "." not in host:
            return None

        for blocked in BLOCKED_DOMAINS:
            if host == blocked or host.endswith("." + blocked):
                return None

        return host

    except Exception:
        return None


def clean_company_name(text, domain):
    if not text:
        return domain

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    # Common separators in page titles.
    parts = re.split(
        r"\s*\|\s*|\s*[-–—:]\s*",
        text,
    )

    if parts:
        candidates = [
            p.strip()
            for p in parts
            if p.strip()
        ]

        # Prefer the shorter branding-like part.
        if candidates:
            text = min(
                candidates,
                key=len,
            )

    # Remove obvious generic phrases.
    text = re.sub(
        r"\b(home|homepage|official website)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text[:150] or domain
def looks_like_company_page(title, text):
    """
    Lightweight filter.

    This should NOT try to prove that a website is a company.
    It only rejects obvious non-company pages.
    """

    title = (title or "").lower()
    text = (text or "").lower()

    combined = f"{title} {text}"

    obvious_non_company = [
        "job board",
        "job listings",
        "job search",
        "find jobs",
        "search jobs",

        "company directory",
        "business directory",
        "list of companies",

        "top companies",
        "top startups",
        "rankings",

        "news platform",
        "technology news",
        "startup news",

        "university",
        "college",
        "open day",

        "software alternatives",

        "market research report",
    ]

    if any(
        signal in combined
        for signal in obvious_non_company
    ):
        return False

    # Very short pages are usually not useful company pages.
    if len(text) < 300:
        return False

    return True 
def verify_company(url):
    """
    Visit the candidate URL and determine whether it is a real
    company website.

    Returns:
        dict or None
    """

    domain = normalize_domain(url)

    if not domain:
        return None

    homepage = f"https://{domain}"

    try:
        response = requests.get(
            homepage,
            headers={"User-Agent": USER_AGENT},
            timeout=settings.request_timeout,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        content_type = response.headers.get("content-type", "").lower()

        if "text/html" not in content_type:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        title = ""
        if soup.title:
            title = soup.title.get_text(" ", strip=True)

        h1 = ""
        h1_tag = soup.find("h1")
        if h1_tag:
            h1 = h1_tag.get_text(" ", strip=True)

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
        ]):
            tag.decompose()

        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        text_sample = text[:12000]

        if not looks_like_company_page(
            title,
            text_sample,
        ):
            return None

        og_site_name = ""

        og_tag = soup.find(
            "meta",
            attrs={"property": "og:site_name"}
        )

        if og_tag:
            og_site_name = og_tag.get("content", "").strip()


        name_source = (
            og_site_name
            or title
            or h1
        )

        company_name = clean_company_name(
            name_source,
            domain,
        )

        # Calculate a simple deterministic discovery score.
        combined = f"{title} {text_sample}".lower()

        score = 0

        keywords = {
            "cloud": 15,
            "devops": 15,
            "aws": 10,
            "azure": 10,
            "gcp": 10,
            "artificial intelligence": 15,
            "machine learning": 15,
            "software engineering": 10,
            "software development": 10,
            "engineering": 5,
            "remote": 5,
            "careers": 5,
            "internship": 10,
        }

        for keyword, points in keywords.items():
            if keyword in combined:
                score += points

        return {
            "name": company_name,
            "domain": domain,
            "website": response.url.rstrip("/"),
            "title": title,
            "description": text_sample[:3000],
            "score": min(score, 100),
        }

    except requests.RequestException:
        return None

    except Exception as e:
        print(f"   ⚠ verification error: {e}")
        return None


QUERIES_FILE = Path("queries.txt")

# First matching keyword wins, so cities come before countries.
LOCATION_KEYWORDS = [
    ("sousse", "Sousse, Tunisia"),
    ("sfax", "Sfax, Tunisia"),
    ("ghazala", "Tunis, Tunisia"),
    ("tunis ", "Tunis, Tunisia"),
    ("tunisi", "Tunisia"),
    ("tunisie", "Tunisia"),
    ("paris", "Paris, France"),
    ("lyon", "Lyon, France"),
    ("france", "France"),
    ("montréal", "Montreal, Canada"),
    ("montreal", "Montreal, Canada"),
    ("berlin", "Berlin, Germany"),
    ("germany", "Germany"),
    ("belgium", "Belgium"),
    ("switzerland", "Switzerland"),
    ("netherlands", "Netherlands"),
    ("europe", "Europe"),
    ("remote", "Remote"),
]


def load_queries(path=QUERIES_FILE):
    """Read searches from queries.txt; fall back to the built-in list."""
    path = Path(path)

    if not path.exists():
        return list(QUERIES)

    queries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in queries:
            queries.append(line)

    return queries or list(QUERIES)


def infer_location(query):
    query = f" {query.lower()} "
    for keyword, location in LOCATION_KEYWORDS:
        if keyword in query:
            return location
    return None


def known_domains():
    with connect() as c:
        return {row[0] for row in c.execute("SELECT domain FROM companies")}


def discover(queries=None):
    Path("data").mkdir(exist_ok=True)

    queries = queries or load_queries()
    raw_path = Path("data/raw_search.jsonl")

    # Skip companies already in the database: re-runs only verify new ones.
    already_known = known_domains()
    processed_domains = set(already_known)
    skipped_known = 0

    raw_count = 0
    verified_count = 0
    rejected_count = 0

    print(f"{len(queries)} searches, {len(already_known)} companies already known.")

    with raw_path.open("a", encoding="utf-8") as raw_file:

        for query_index, query in enumerate(queries, start=1):

            print(f"\n🔎 [{query_index}/{len(queries)}] {query}")

            try:
                # Create a fresh DDGS client for every search.
                # This helps avoid keeping a throttled session alive.
                with DDGS() as ddgs:

                    results = ddgs.text(
                        query,
                        max_results=settings.search_results_per_query,
                    )

                    results = list(results)

                if not results:
                    print("   ⚠ no results")
                    continue

                print(f"   📄 {len(results)} results")

                for result in results:

                    raw_count += 1

                    url = (
                        result.get("href")
                        or result.get("url")
                    )

                    if not url:
                        continue

                    domain = normalize_domain(url)

                    if not domain:
                        rejected_count += 1
                        continue

                    # Don't verify the same domain twice.
                    if domain in processed_domains:
                        if domain in already_known:
                            skipped_known += 1
                        continue

                    processed_domains.add(domain)

                    raw_file.write(
                        json.dumps(
                            {
                                "query": query,
                                "title": result.get("title", ""),
                                "href": url,
                                "body": result.get("body", ""),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                    print(f"   🌐 checking {domain}")

                    company = verify_company(url)

                    if not company:
                        rejected_count += 1
                        print("      ❌ rejected")
                        continue

                    query_lower = query.lower()
                    location = infer_location(query)

                    company_type = (
                        "startup"
                        if any(
                            x in query_lower
                            for x in [
                                "startup",
                                "yc",
                                "y combinator",
                            ]
                        )
                        else "company"
                    )

                    upsert_company(
                        {
                            "name": company["name"],
                            "domain": company["domain"],
                            "website": company["website"],
                            "location": location,
                            "company_type": company_type,
                            "description": company["description"],
                            "source": "ddgs",
                            "source_url": url,
                            "raw_text": json.dumps(
                                result,
                                ensure_ascii=False,
                            ),
                            "verified": 1,
                            "discovery_score": company["score"],
                        }
                    )

                    verified_count += 1

                    print(
                        f"      ✅ {company['name']} "
                        f"(score={company['score']})"
                    )

            except Exception as e:
                print(f"   ⚠ search error: {e}")

    print("\n" + "=" * 60)
    print("DISCOVERY COMPLETE")
    print("=" * 60)

    print(f"Raw results:      {raw_count}")
    print(f"Verified domains: {verified_count}")
    print(f"Rejected:         {rejected_count}")
    print(f"Already known:    {skipped_known} (skipped)")
    print(f"New domains seen: {len(processed_domains) - len(already_known)}")