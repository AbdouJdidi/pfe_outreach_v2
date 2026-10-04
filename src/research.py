import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import settings
from .db import connect, save_fetched_text

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/154.0 Safari/537.36"
    )
}


PATHS = [
    ("homepage", ""),
    ("about", "/about"),
    ("about_us", "/about-us"),
    ("company", "/company"),

    ("careers", "/careers"),
    ("career", "/career"),
    ("jobs", "/jobs"),
    ("internships", "/internships"),
    ("internship", "/internship"),
    ("opportunities", "/opportunities"),

    ("contact", "/contact"),
    ("contact_us", "/contact-us"),
    ("team", "/team"),
]


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
    ]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    return re.sub(r"\s+", " ", text)


def research_company(company_id, website):
    chunks = []

    # Prevent storing the same page multiple times
    # when different paths redirect to the same URL.
    visited_urls = set()

    for page_type, path in PATHS:

        url = urljoin(
            website.rstrip("/") + "/",
            path.lstrip("/"),
        )

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=settings.request_timeout,
                allow_redirects=True,
            )

            if response.status_code >= 400:
                continue

            content_type = response.headers.get(
                "content-type",
                "",
            ).lower()

            if "text/html" not in content_type:
                continue

            final_url = response.url.rstrip("/")

            if final_url in visited_urls:
                continue

            visited_urls.add(final_url)

            text = extract_text(response.text)

            if not text:
                continue

            # Keep each page reasonably bounded.
            text = text[:7000]

            chunks.append(
                f"PAGE TYPE: {page_type}\n"
                f"URL: {response.url}\n"
                f"{text}"
            )

            print(
                f"      ✓ {page_type} "
                f"({len(text)} chars)"
            )

        except requests.RequestException:
            continue

        except Exception as e:
            print(
                f"      ⚠ {page_type}: {e}"
            )

    combined = "\n\n".join(chunks)

    save_fetched_text(
        company_id,
        combined,
    )

    return combined


def research_pending(limit=100):

    with connect() as c:
        rows = c.execute(
            """
            SELECT id, name, website
            FROM companies
            WHERE verified = 1
              AND (
                    fetched_text IS NULL
                    OR fetched_text = ''
                  )
            ORDER BY discovery_score DESC, id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    print(
        f"\n🌐 Researching {len(rows)} verified companies..."
    )

    for row in rows:

        print(
            f"\n🏢 {row['name']}"
        )

        text = research_company(
            row["id"],
            row["website"],
        )

        print(
            f"   collected {len(text)} chars"
        )