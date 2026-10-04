"""The deterministic text logic: what makes every email correct and readable."""

import pytest

from src.outreach import (
    angle_from_clause,
    build_body,
    build_company_paragraph,
    build_greeting,
    build_subject,
    clean_clause,
    display_company_name,
    resolve_company_name,
    validate_clause,
)

SOURCE = (
    "DBB Software builds production-ready AI features, agentic systems, "
    "and private AI platforms, backed by senior engineers."
)
QUOTE = "DBB Software builds production-ready AI features, agentic systems"


# --- clean_clause: grammar fixes -------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # repeated company name -> "it"
    ("how DBB Software builds AI platforms", "how it builds AI platforms"),
    # website "we" -> "you"
    ("how we provide over 90 PB of data", "how you provide over 90 PB of data"),
    # noun phrase -> needs "your focus on"
    ("custom software and cloud development", "your focus on custom software and cloud development"),
    # model repeated the sentence start
    ("What interests me about DBB Software is how it ships agents.", "how it ships agents"),
    # acronym at the start stays uppercase
    ("AI platforms for banks", "your focus on AI platforms for banks"),
])
def test_clean_clause(raw, expected):
    assert clean_clause(raw, "DBB Software") == expected


# --- validate_clause: anti-hallucination guardrails -------------------------

def test_grounded_clause_passes():
    clause = "how it builds production-ready AI features and agentic systems"
    assert validate_clause(clause, QUOTE, SOURCE) == []


def test_quote_must_exist_on_website():
    clause = "how it builds production-ready AI features and agentic systems"
    problems = validate_clause(clause, "DBB Software is the market leader in banking", SOURCE)
    assert any("not found" in p for p in problems)


def test_clause_with_words_not_on_website_is_rejected():
    # The real failure we saw: the model copied the prompt's example.
    clause = "how you use AI and data to make hiring more efficient and reliable"
    problems = validate_clause(clause, QUOTE, SOURCE)
    assert any("not on the website" in p or "copied the example" in p for p in problems)


def test_invented_number_is_rejected():
    clause = "how it builds AI features for 500 enterprise clients worldwide"
    problems = validate_clause(clause, QUOTE, SOURCE)
    assert any('"500"' in p for p in problems)


def test_clause_about_the_student_is_rejected():
    clause = "how my experience fits production-ready AI features"
    problems = validate_clause(clause, QUOTE, SOURCE)
    assert any("student" in p for p in problems)


def test_too_short_clause_is_rejected():
    problems = validate_clause("AI stuff", QUOTE, SOURCE)
    assert any("words" in p for p in problems)


# --- angle: the closing sentence must match the clause ----------------------

@pytest.mark.parametrize("clause,expected", [
    ("how it builds production-ready AI features and agentic systems", "ai"),
    ("the way it deploys applications from Git with no manual configuration", "cloud"),
    ("how it helps local businesses find customers", "software"),
])
def test_angle_from_clause(clause, expected):
    assert angle_from_clause(clause, "software") == expected


def test_company_paragraph_uses_matching_interest():
    text = build_company_paragraph("Clever Cloud", "how it automates deployment", "cloud")
    assert text.startswith("What interests me about Clever Cloud is how it automates deployment.")
    assert "cloud infrastructure and DevOps" in text


# --- names and greetings ----------------------------------------------------

def test_display_name_from_domain():
    assert display_company_name({"name": "dbbsoftware.com"}) == "Dbbsoftware"


def test_resolve_name_accepts_name_matching_domain():
    company = {"name": "dbbsoftware.com", "website": "https://dbbsoftware.com", "fetched_text": SOURCE}
    assert resolve_company_name(company, "DBB Software") == "DBB Software"


def test_resolve_name_rejects_invented_name():
    company = {"name": "dbbsoftware.com", "website": "https://dbbsoftware.com", "fetched_text": SOURCE}
    assert resolve_company_name(company, "Totally Different Inc") == "Dbbsoftware"


def test_resolve_name_strips_domain_ending():
    company = {"name": "Ween.tn", "website": "https://ween.tn", "fetched_text": "Ween .tn Annuaire"}
    assert resolve_company_name(company, "Ween .tn") == "Ween"


@pytest.mark.parametrize("email,expected", [
    ("erik.simins@workwolf.com", "Dear Erik Simins,"),
    ("jobs@workwolf.com", "Dear Workwolf Team,"),
    ("dmitry@workwolf.com", "Dear Workwolf Team,"),  # can't tell first name from surname
])
def test_build_greeting(email, expected):
    assert build_greeting({"email": email}, "Workwolf") == expected


# --- full email -------------------------------------------------------------

def test_body_contains_template_and_signature(profile):
    paragraph = build_company_paragraph("Workwolf", "how it uses AI to improve hiring", "ai")
    body = build_body(profile, "ai", "Dear Workwolf Team,", "Workwolf", paragraph)

    assert body.startswith("Dear Workwolf Team,")
    assert "graduation internship (PFE) at Workwolf" in body
    assert "AWS Certified Solutions Architect" in body
    assert paragraph in body
    assert body.rstrip().endswith(profile["links"][-1])
    assert "{" not in body  # no unfilled placeholders


def test_subject(profile):
    subject = build_subject(profile, "cloud")
    assert "Cloud & DevOps" in subject
    assert profile["pfe_start"] in subject
