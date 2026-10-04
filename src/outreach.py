"""
Outreach stage.

Design:
- The fixed parts of the email (intro, experience, closing, signature) come
  from profile.json, written by you, so they stay consistent and accurate.
- The LLM writes ONE short company-specific paragraph and must return the exact
  website sentence it relied on. Python checks that sentence really exists on
  the site, plus a set of hard rules. Failed drafts are kept as 'needs_review'.
- One email per company (best contact only). Re-running skips companies that
  already have outreach unless --regenerate is used.
"""

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import requests

from .config import settings
from .db import (
    companies_with_outreach,
    connect,
    delete_unsent_outreach,
    get_contacts,
    get_outreach,
    save_outreach,
    update_outreach,
)
from .llm import DOMAIN_PATTERNS, build_relevant_evidence

# ---------------------------------------------------------
# YOUR EMAIL — edit the wording here. Same for every company.
# Placeholders: {company} {start} {school} {company_paragraph}
# ---------------------------------------------------------

EMAIL_TEMPLATE = [
    "I am applying for a graduation internship (PFE) at {company}, starting in "
    "{start}. I am a final-year software engineering student at {school}, with "
    "a strong interest in cloud, DevOps and applied AI.",

    "I have completed four internships at Satoripop, Tunisie Telecom, VISIOAD "
    "and Dot-IT, where I developed experience across DevOps and cloud, "
    "full-stack development, software engineering and applied AI. I have also "
    "worked on freelance software development projects, gaining experience "
    "building solutions around real client requirements.",

    "Alongside my studies, I built ClipForge, an AI-powered clipping agent "
    "designed to automate parts of the content production workflow and operate "
    "with minimal supervision.",

    "I also hold the AWS Certified Solutions Architect – Associate and AWS "
    "Certified Cloud Practitioner certifications.",

    "{company_paragraph}",

    "I would welcome the opportunity to contribute to {company} as a PFE intern "
    "and discuss how my background could fit your engineering team. "
    "My CV is attached.",
]

# Second sentence of the company paragraph, chosen by the company's focus.
INTEREST_BY_ANGLE = {
    "cloud": "cloud infrastructure and DevOps",
    "ai": "applied AI and intelligent software systems",
    "software": "building reliable software for real users",
}


# ---------------------------------------------------------
# PROFILE
# ---------------------------------------------------------

def load_profile():
    path = Path(settings.profile_path)

    if not path.exists():
        raise SystemExit(
            f"\n❌ {path} not found.\n"
            f"   Copy profile.example.json to {path} and fill in your details.\n"
        )

    profile = json.loads(path.read_text(encoding="utf-8"))

    if "XX" in profile.get("phone", ""):
        print("⚠ profile.json still has the placeholder phone number.")

    return profile


# ---------------------------------------------------------
# CONTACT SELECTION — one best contact per company
# ---------------------------------------------------------

RECRUITING_TYPES = {"careers", "jobs", "recruiting", "hr"}
CAREER_PAGE_HINTS = ["career", "internship", "stage", "jobs", "recruit", "join"]


def contact_rank(contact):
    """Lower is better. None means: do not email this address."""
    contact_type = contact["contact_type"]
    source = (contact["source_url"] or "").lower()

    if contact_type in RECRUITING_TYPES:
        return 0

    if contact_type == "other" and any(h in source for h in CAREER_PAGE_HINTS):
        return 1

    if contact_type == "contact":
        return 2

    if contact_type == "info":
        return 3

    # Personal emails found on random pages (sales, press, blog authors...)
    return None


def choose_contacts(limit=500):
    best = {}

    for contact in get_contacts(limit):
        rank = contact_rank(contact)

        if rank is None:
            continue

        key = contact["company_id"]
        candidate = (rank, -(contact["confidence"] or 0), contact["email"])

        if key not in best or candidate < best[key][0]:
            best[key] = (candidate, contact)

    return [contact for _, contact in best.values()]


# ---------------------------------------------------------
# COMPANY CONTEXT
# ---------------------------------------------------------

def get_company_context(company_id):
    with connect() as c:
        return c.execute("""
            SELECT
                c.id, c.name, c.website, c.location,
                c.description, c.fetched_text, a.domains
            FROM companies c
            LEFT JOIN analyses a ON a.company_id = c.id
            WHERE c.id = ?
        """, (company_id,)).fetchone()


def company_domains(company):
    try:
        return json.loads(company["domains"] or "[]")
    except (TypeError, json.JSONDecodeError):
        return []


def choose_angle(domains, text=""):
    """Pick the angle the website talks about most, not just the first match."""
    text = (text or "").lower()

    def hits(names):
        return sum(
            len(re.findall(p, text))
            for name in names
            for p in DOMAIN_PATTERNS.get(name, [])
        )

    scores = {
        "ai": hits(["AI", "Machine Learning"]),
        "cloud": hits(["Cloud", "DevOps"]),
        "software": hits(["Software Engineering", "Backend"]),
    }

    if not any(scores.values()):
        domains = set(domains)
        if domains & {"AI", "Machine Learning"}:
            return "ai"
        if domains & {"Cloud", "DevOps"}:
            return "cloud"
        return "software"

    return max(scores, key=scores.get)


def display_company_name(company):
    """'dbbsoftware.com' -> 'DBB Software' is not guessable; at least drop TLDs."""
    name = (company["name"] or "").strip()

    if re.fullmatch(r"[a-z0-9-]+\s?\.[a-z.]{2,}", name.lower()):
        name = name.split(".")[0]
        name = name.replace("-", " ").title()

    return name


def resolve_company_name(company, name_on_site):
    """
    Accept the LLM's 'company name as written on the website' only if it
    really appears on the site AND matches the domain (e.g. 'DBB Software'
    for dbbsoftware.com). Otherwise keep the stored name.
    """
    fallback = display_company_name(company)
    name_on_site = re.sub(r"\s+([.,])", r"\1", (name_on_site or "").strip())

    if not name_on_site or len(name_on_site) > 40:
        return fallback

    # "Ween.tn" -> "Ween": don't put domain endings in the greeting
    name_on_site = re.sub(r"\.(tn|com|io|fr|net|org|site|cloud|ai)$", "", name_on_site, flags=re.I)

    if normalize(name_on_site) not in normalize(company["fetched_text"]):
        return fallback

    squashed = normalize(name_on_site).replace(" ", "")
    stem = re.sub(r"^https?://(www\.)?", "", company["website"] or "").split(".")[0]
    stem = stem.lower().replace("-", "")

    if stem and (squashed == stem or squashed.startswith(stem) or stem.startswith(squashed)):
        return name_on_site

    return fallback


# ---------------------------------------------------------
# GREETING / SUBJECT / BODY — deterministic
# ---------------------------------------------------------

GENERIC_LOCALS = {
    "contact", "contacts", "info", "hello", "hi", "office", "jobs", "job",
    "careers", "career", "hr", "recruit", "recruiting", "recruitment",
    "talent", "talents", "people", "team", "admin", "support", "sales",
}


def build_greeting(contact, company_name):
    local = contact["email"].split("@")[0].lower()

    # first.last@ or first_last@ -> "Dear First Last,"
    parts = re.split(r"[._]", local)
    if (
        len(parts) == 2
        and all(p.isalpha() and len(p) >= 2 for p in parts)
        and local not in GENERIC_LOCALS
    ):
        return f"Dear {parts[0].title()} {parts[1].title()},"

    # Anything else (incl. dmitry@, mduda@): we can't safely tell a first name
    # from initial+surname, so use the team greeting. Edit it in `review`.
    return f"Dear {company_name} Team,"


def build_subject(profile, angle):
    area = profile["angles"][angle]["subject_area"]
    return (
        f"PFE Application – {area} – "
        f"{profile['pfe_start']} ({profile['pfe_duration']}) – {profile['name']}"
    )


CLAUSE_ANGLE_PATTERNS = {
    "ai": r"\bai\b|[a-z]ai\b|artificial intelligence|machine learning|\bllms?\b|"
          r"\bagents?\b|agentic|generative|\bml\b|computer vision|\bnlp\b",
    "cloud": r"\bcloud\b|devops|deploy|infrastructure|hosting|\bpaas\b|\biaas\b|"
             r"kubernetes|docker|ci/cd|data center|datacent|scalab|servers?\b|storage",
}


def angle_from_clause(clause, fallback):
    """The closing sentence must match what the clause talks about."""
    lower = clause.lower()
    ai = len(re.findall(CLAUSE_ANGLE_PATTERNS["ai"], lower))
    cloud = len(re.findall(CLAUSE_ANGLE_PATTERNS["cloud"], lower))

    if ai == 0 and cloud == 0:
        return fallback if fallback != "software" else "software"
    return "ai" if ai >= cloud else "cloud"


def build_company_paragraph(company_name, clause, angle):
    if not clause:
        return ""
    interest = INTEREST_BY_ANGLE[angle]
    return (
        f"What interests me about {company_name} is {clause}. "
        f"This strongly aligns with my interest in {interest}."
    )


def build_body(profile, angle, greeting, company_name, company_paragraph):
    values = {
        "company": company_name,
        "start": profile["pfe_start"],
        "school": profile["school"],
        "company_paragraph": company_paragraph,
    }
    paragraphs = [greeting] + [p.format(**values) for p in EMAIL_TEMPLATE]

    signature = "\n".join(
        ["Best regards,", profile["name"], profile["phone"], *profile.get("links", [])]
    )

    return "\n\n".join(p.strip() for p in paragraphs + [signature] if p and p.strip())


# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

BANNED_PHRASES = [
    "dream company", "perfect fit", "extremely passionate", "passionate",
    "available immediately", "hope this", "as an ai", "[", "]", "{", "}",
    "esteemed", "cutting-edge", "world-class", "seamless",
]


MONTHS = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
]


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def clean_clause(clause, company_name):
    """Turn whatever the model returned into the part after '... is'."""
    clause = re.sub(r"\s+", " ", clause or "").strip().strip('"').strip()
    clause = re.sub(
        rf"^what interests me about {re.escape(company_name)} is\s+",
        "", clause, flags=re.IGNORECASE,
    )
    clause = clause.rstrip(" .")

    # "how DBB Software builds..." -> "how it builds..." (name is already in the sentence)
    clause = re.sub(
        rf"^(how|the way)\s+{re.escape(company_name)}(\s?\.[a-z]{{2,}})?\b",
        r"\1 it", clause, flags=re.IGNORECASE,
    )
    # Website copy is written as "we/our" -> address the company as "you/your"
    for old, new in [(r"\bwe're\b", "you're"), (r"\bwe\b", "you"),
                     (r"\bour\b", "your"), (r"\bours\b", "yours")]:
        clause = re.sub(old, new, clause, flags=re.IGNORECASE)

    # lowercase the first letter unless it starts an acronym/name ("AI", "EODATA")
    if len(clause) > 1 and clause[0].isupper() and not clause[1].isupper():
        clause = clause[0].lower() + clause[1:]

    # "What interests me about X is custom software..." -> "...is your focus on custom software..."
    first = clause.split(" ", 1)[0].lower() if clause else ""
    if first and first not in GOOD_CLAUSE_STARTS:
        clause = "your focus on " + clause
    # "the largest..." -> "your ..." reads better when it's about the company
    elif first == "the" and not re.match(r"the (way|fact|scale|focus|range|idea)\b", clause.lower()):
        clause = "your work on " + clause

    return clause


GOOD_CLAUSE_STARTS = {
    "how", "the", "your", "its", "their", "that", "what", "why", "a", "an",
    "seeing", "building", "being",
}

STOPWORDS = set("""
a an the and or of to for in on with by from at as is are be your you
their its it that this how what which who way into through about our we
them they make makes making more most very all any can will also using use
uses used based without no not like across over under between within
""".split())

# The examples shown to the model. If it copies them, reject.
PROMPT_EXAMPLE_WORDS = {"hiring", "recruit", "recruitment", "candidates"}


def validate_clause(clause, evidence_quote, source_text):
    """Return a list of problems. Empty list means OK."""
    problems = []
    lower = f" {clause.lower()} "
    words = clause.split()

    if not 6 <= len(words) <= 30:
        problems.append(f"clause is {len(words)} words; it must be 8-25 words")

    if "." in clause.rstrip(".") and not re.search(r"\d\.\d|\.[a-z]{2,}", clause):
        problems.append("must be one clause, not several sentences")

    if re.search(r"\b(my|i|i'm|i've|me)\b", lower):
        problems.append("talks about the student; describe only the company")

    for phrase in BANNED_PHRASES:
        if phrase in lower:
            problems.append(f'contains forbidden text "{phrase}"')

    for month in MONTHS:
        if re.search(rf"\b{month}\b", lower):
            problems.append("mentions a date")
            break

    norm_quote = normalize(evidence_quote)
    if len(norm_quote.split()) < 4:
        problems.append("evidence_quote is missing or too short")
    elif norm_quote not in normalize(source_text):
        problems.append("evidence_quote was not found word-for-word on the website")

    for number in re.findall(r"\d+(?:[.,]\d+)?", clause):
        if number not in source_text:
            problems.append(f'number "{number}" does not appear on the website')

    # Grounding: most content words of the clause must appear on the website.
    norm_source = f" {normalize(source_text)} "
    content = [
        w for w in normalize(clause).split()
        if len(w) > 3 and w not in STOPWORDS
    ]
    missing = [w for w in content if w[:5] not in norm_source]
    if content and len(missing) / len(content) > 0.4:
        problems.append(
            "clause uses words that are not on the website "
            f"({', '.join(missing[:5])}); describe what the website says"
        )

    copied = [w for w in content if w in PROMPT_EXAMPLE_WORDS and w not in norm_source]
    if copied:
        problems.append("copied the example from the instructions; use this company's facts")

    return problems


# ---------------------------------------------------------
# LLM — company paragraph only
# ---------------------------------------------------------

def ask_ollama(prompt, temperature):
    response = requests.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": settings.outreach_num_ctx,
            },
        },
        timeout=180,
    )
    response.raise_for_status()

    raw = response.json().get("response", "")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group(0)) if match else {}


def clause_prompt(company_name, website, evidence, feedback=None):
    retry = ""
    if feedback:
        retry = (
            "\nYOUR PREVIOUS ATTEMPT WAS REJECTED BECAUSE:\n- "
            + "\n- ".join(feedback) + "\nFix these problems.\n"
        )

    return f"""A student is writing an internship application to {company_name}.
Complete this sentence using ONE concrete fact from the website evidence:

"What interests me about {company_name} is ___."

WEBSITE EVIDENCE ({website}):
\"\"\"
{evidence}
\"\"\"

RULES for the missing part ("interest_clause"):
- 8 to 25 words, describing what {company_name} does or builds.
- Start with "how", "the way", or "your focus on".
- Use the company's OWN words and facts from the evidence above.
  Shape (do not copy): "how you <what the company does> for <who/what>".
- Only facts from the evidence. No invented products, clients or numbers.
- Do not mention the student. No praise words. No dates.
- Copy the sentence you used, word for word, into "evidence_quote".
- If the evidence shows {company_name} does NOT build software, cloud or AI
  products/services (e.g. legal, accounting, directories, retail), set
  "relevant" to false.
{retry}
Return ONLY JSON:
{{"relevant": true,
  "company_name": "the company name exactly as written on the website",
  "evidence_quote": "...",
  "interest_clause": "..."}}
"""


def generate_company_paragraph(company, angle, profile):
    source_text = company["fetched_text"] or ""
    evidence = build_relevant_evidence(source_text, 4000)
    company_name = display_company_name(company)

    feedback = None
    last = {
        "angle": angle, "paragraph": "", "evidence_quote": "",
        "company_name": company_name, "problems": ["no attempt"],
    }

    for attempt in range(settings.outreach_max_attempts):
        try:
            result = ask_ollama(
                clause_prompt(company_name, company["website"], evidence, feedback),
                temperature=0.2 + 0.2 * attempt,
            )
        except Exception as e:
            last["problems"] = [f"LLM call failed: {e}"]
            continue

        if result.get("relevant") is False:
            last["problems"] = ["website suggests this is not a tech company — reject"]
            return last

        name = resolve_company_name(company, result.get("company_name"))
        clause = clean_clause(str(result.get("interest_clause", "")), name)
        quote = str(result.get("evidence_quote", "")).strip()
        problems = validate_clause(clause, quote, source_text)
        clause_angle = angle_from_clause(clause, angle)

        last = {
            "angle": clause_angle,
            "paragraph": build_company_paragraph(name, clause, clause_angle),
            "evidence_quote": quote,
            "company_name": name,
            "problems": problems,
        }

        if not problems:
            return last

        feedback = problems

    return last


# ---------------------------------------------------------
# COMMANDS
# ---------------------------------------------------------

def generate_outreach(regenerate=False, limit=None):
    profile = load_profile()
    contacts = choose_contacts()

    if not contacts:
        print("No suitable contacts found.")
        return

    already = companies_with_outreach()

    if regenerate:
        removed = delete_unsent_outreach()
        print(f"Removed {removed} unsent drafts.")
        already = companies_with_outreach()  # approved/sent are kept

    todo = [c for c in contacts if c["company_id"] not in already]

    if limit:
        todo = todo[:limit]

    print(
        f"{len(contacts)} companies with a usable contact, "
        f"{len(contacts) - len(todo)} skipped (already have outreach), "
        f"{len(todo)} to generate."
    )

    counts = {"draft": 0, "needs_review": 0}

    for contact in todo:
        company = get_company_context(contact["company_id"])

        if not company or not company["fetched_text"]:
            print(f"\n⚠ {contact['email']}: no website text, skipping")
            continue

        company_name = display_company_name(company)
        angle = choose_angle(company_domains(company), company["fetched_text"])

        print(f"\n✉️  {company_name}  [{angle}]")
        print(f"   → {contact['email']}")

        result = generate_company_paragraph(company, angle, profile)
        company_name = result["company_name"]
        angle = result["angle"]

        greeting = build_greeting(contact, company_name)
        body = build_body(
            profile, angle, greeting, company_name, result["paragraph"]
        )
        status = "needs_review" if result["problems"] else "draft"

        save_outreach(
            company_id=company["id"],
            contact_id=contact["id"],
            subject=build_subject(profile, angle),
            body=body,
            status=status,
            greeting=greeting,
            company_paragraph=result["paragraph"],
            evidence_quote=result["evidence_quote"],
            angle=angle,
            notes="; ".join(result["problems"]) or None,
        )

        counts[status] += 1

        if status == "draft":
            print("   ✓ draft generated (checks passed)")
        else:
            print("   ⚠ needs review: " + "; ".join(result["problems"]))

    print("\n" + "=" * 60)
    print(
        f"Generated {counts['draft']} clean drafts, "
        f"{counts['needs_review']} needing review."
    )
    print("Next: python -m src.main review")
    print("=" * 60)


def print_draft(row, index=None):
    print("\n" + "=" * 80)
    prefix = f"{index}. " if index is not None else ""
    print(f"{prefix}{row['name']}   [#{row['id']} · {row['angle'] or '-'} · {row['status']}]")
    print(f"To: {row['email']}")
    print(f"Subject: {row['subject']}")
    print("-" * 80)
    print(row["body"])
    print("-" * 80)

    if row["evidence_quote"]:
        print(f"Evidence used: \"{row['evidence_quote']}\"")
    if row["notes"]:
        print(f"⚠ Problems: {row['notes']}")


def show_outreach(status=None):
    rows = get_outreach(status)

    if not rows:
        print("No outreach drafts found.")
        return

    for i, row in enumerate(rows, 1):
        print_draft(row, i)


def edit_in_editor(text):
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
        path = f.name

    try:
        subprocess.call([settings.editor, path])
        return Path(path).read_text(encoding="utf-8").strip()
    finally:
        os.unlink(path)


def regenerate_one(row, profile):
    company = get_company_context(row["company_id"])
    company_name = display_company_name(company)
    angle = row["angle"] or choose_angle(company_domains(company), company["fetched_text"])
    result = generate_company_paragraph(company, angle, profile)
    company_name = result["company_name"]
    angle = result["angle"]
    greeting = row["greeting"] or f"Dear {company_name} Team,"

    update_outreach(
        row["id"],
        angle=angle,
        subject=build_subject(profile, angle),
        body=build_body(profile, angle, greeting, company_name, result["paragraph"]),
        company_paragraph=result["paragraph"],
        evidence_quote=result["evidence_quote"],
        notes="; ".join(result["problems"]) or None,
        status="needs_review" if result["problems"] else "draft",
    )


def review_outreach():
    profile = load_profile()
    skipped = set()

    menu = (
        "[a]pprove  [r]eject  [e]dit body  [s]ubject  [g]reeting  "
        "[n]ew paragraph  [k] skip  [q]uit"
    )

    while True:
        rows = [
            r for r in get_outreach("draft,needs_review")
            if r["id"] not in skipped
        ]

        if not rows:
            left = len(skipped)
            print(
                f"\nDone. {left} skipped draft(s) left for later."
                if left else "\nNothing left to review. 🎉"
            )
            return

        row = rows[0]
        print_draft(row)
        print(f"\n{len(rows)} left to review.  {menu}")
        choice = input("> ").strip().lower()

        if choice == "q":
            return

        elif choice == "k":
            skipped.add(row["id"])

        elif choice == "a":
            update_outreach(row["id"], status="approved", notes=None)
            print("✓ approved")

        elif choice == "r":
            update_outreach(row["id"], status="rejected")
            print("✗ rejected")

        elif choice == "e":
            body = edit_in_editor(row["body"])
            if body:
                update_outreach(row["id"], body=body)
                print("✎ body updated")

        elif choice == "s":
            subject = input("New subject: ").strip()
            if subject:
                update_outreach(row["id"], subject=subject)

        elif choice == "g":
            greeting = input('New greeting (e.g. "Dear Dmitry,"): ').strip()
            if greeting:
                body = row["body"].replace(row["greeting"] or "", greeting, 1)
                update_outreach(row["id"], greeting=greeting, body=body)

        elif choice == "n":
            print("Regenerating company paragraph...")
            regenerate_one(row, profile)

        else:
            print("Unknown option.")


def reset_outreach():
    removed = delete_unsent_outreach()
    print(f"Deleted {removed} unsent drafts (approved/sent kept).")