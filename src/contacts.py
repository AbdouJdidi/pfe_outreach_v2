import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .db import get_companies_for_contacts, save_contact

EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)


CONTACT_PAGE_KEYWORDS = [
    "contact",
    "contacts",
    "career",
    "careers",
    "jobs",
    "job",
    "work-with-us",
    "work-with-us",
    "join-us",
    "join-our-team",
    "team",
    "about",
    "recruit",
    "hiring",
]


EMAIL_PRIORITY = {
    "careers": 100,
    "jobs": 100,
    "recruiting": 95,
    "hr": 90,
    "contact": 70,
    "info": 50,
    "hello": 50,
    "other": 30,
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    )
}


def normalize_url(url):
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


def same_domain(url, base_url):
    try:
        return (
            urlparse(url).netloc.lower().replace("www.", "")
            == urlparse(base_url).netloc.lower().replace("www.", "")
        )
    except Exception:
        return False


def classify_email(email):
    local = email.split("@")[0].lower()

    if local in {"career", "careers"}:
        return "careers"

    if local in {"job", "jobs"}:
        return "jobs"

    if local in {
        "recruit",
        "recruiting",
        "recruitment",
        "talent",
        "talents",
    }:
        return "recruiting"

    if local in {
        "hr",
        "humanresources",
        "human.resources",
        "people",
    }:
        return "hr"

    if local in {
        "contact",
        "contacts",
    }:
        return "contact"

    if local in {
        "info",
        "hello",
        "hi",
        "office",
    }:
        return "info"

    return "other"


def confidence_for_email(email, source_url):
    email_type = classify_email(email)

    score = EMAIL_PRIORITY.get(email_type, 30)

    page = source_url.lower()

    if "career" in page or "job" in page or "recruit" in page:
        score += 10

    if "contact" in page:
        score += 5

    return min(score, 100)


def extract_emails(text):
    if not text:
        return set()

    emails = set()

    for email in EMAIL_RE.findall(text):
        email = email.lower().strip()

        # Remove common punctuation accidentally captured from HTML text.
        email = email.rstrip(".,;:!?)]}")

        if "example.com" in email:
            continue

        if email.endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue

        emails.add(email)

    return emails


def fetch_page(url, timeout=15):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "text/html" not in content_type:
            return None

        return response.text

    except requests.RequestException:
        return None


def discover_pages(home_url, html):
    soup = BeautifulSoup(html, "html.parser")

    pages = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()

        if not href:
            continue

        if href.startswith(
            (
                "mailto:",
                "tel:",
                "javascript:",
                "#",
            )
        ):
            continue

        url = urljoin(home_url, href)

        if not same_domain(url, home_url):
            continue

        text = link.get_text(" ", strip=True).lower()

        combined = f"{text} {url.lower()}"

        if any(
            keyword in combined
            for keyword in CONTACT_PAGE_KEYWORDS
        ):
            pages.append(url.rstrip("/"))

    # Deduplicate while preserving order.
    result = []

    seen = set()

    for page in pages:
        if page not in seen:
            result.append(page)
            seen.add(page)

    return result[:15]


def discover_contacts_for_company(company):
    company_id = company["id"]
    name = company["name"]
    website = normalize_url(company["website"])

    if not website:
        print("   ⚠ no website")
        return 0

    # IMPORTANT:
    # Only process companies that the analysis classified as tech companies.
    raw_json = company["raw_json"] or ""

    if '"tech_company": true' not in raw_json.lower():
        print("   → skipped: not classified as tech company")
        return 0

    print(f"\n📧 {name}")

    home_html = fetch_page(website)

    if not home_html:
        print("   ⚠ could not fetch homepage")
        return 0

    pages = [website]

    discovered_pages = discover_pages(
        website,
        home_html,
    )

    pages.extend(discovered_pages)

    # Also try common paths directly.
    common_paths = [
        "/contact",
        "/contact-us",
        "/careers",
        "/career",
        "/jobs",
        "/join-us",
        "/about",
        "/team",
    ]

    for path in common_paths:
        pages.append(
            urljoin(website + "/", path.lstrip("/"))
        )

    # Deduplicate.
    unique_pages = []

    seen = set()

    for page in pages:
        page = page.rstrip("/")

        if page not in seen:
            unique_pages.append(page)
            seen.add(page)

    found = 0
    checked = 0

    for page_url in unique_pages[:20]:
        html = home_html if page_url == website else fetch_page(page_url)

        if not html:
            continue

        checked += 1

        soup = BeautifulSoup(html, "html.parser")

        # Check mailto links.
        for link in soup.find_all(
            "a",
            href=True,
        ):
            href = link["href"].strip()

            if href.lower().startswith("mailto:"):
                email = href[7:].split("?")[0].strip().lower()

                if EMAIL_RE.fullmatch(email):
                    contact_type = classify_email(email)

                    save_contact(
                        company_id=company_id,
                        email=email,
                        contact_type=contact_type,
                        source_url=page_url,
                        confidence=confidence_for_email(
                            email,
                            page_url,
                        ),
                    )

                    found += 1

        # Also scan visible page text / HTML.
        text = soup.get_text(
            " ",
            strip=True,
        )

        emails = extract_emails(text)

        for email in emails:
            contact_type = classify_email(email)

            save_contact(
                company_id=company_id,
                email=email,
                contact_type=contact_type,
                source_url=page_url,
                confidence=confidence_for_email(
                    email,
                    page_url,
                ),
            )

            found += 1

    print(
        f"   → checked {checked} pages | "
        f"found {found} email occurrence(s)"
    )

    return found


def discover_contacts():
    companies = get_companies_for_contacts()

    if not companies:
        print("No analyzed companies found.")
        return

    total = 0

    for company in companies:
        total += discover_contacts_for_company(company)

    print("\n" + "=" * 60)
    print("Contact discovery finished.")
    print(f"Email occurrences found: {total}")
    print("=" * 60)


def show_contacts(limit=100):
    from .db import get_contacts

    rows = get_contacts(limit)

    if not rows:
        print("No contacts found.")
        return

    print("\nCONTACTS")
    print("=" * 80)

    for row in rows:
        print(
            f"{row['name']:<28} "
            f"{row['email']:<40} "
            f"{row['contact_type']:<12} "
            f"{row['confidence']:>3}"
        )

        if row["source_url"]:
            print(
                f"  source: {row['source_url']}"
            )

    print("=" * 80)
    print(f"Total contacts: {len(rows)}")


if __name__ == "__main__":
    discover_contacts()