"""generate_outreach end to end, with the LLM replaced by a fake."""

from src import outreach
from tests.conftest import add_company

CLEVER_TEXT = (
    "Clever Cloud is a European PaaS.\n\n"
    "The platform detects the language, configures the right environment and "
    "deploys applications from Git with no manual configuration."
)


def setup_companies(db):
    clever = add_company("Clever Cloud", "clever-cloud.com", CLEVER_TEXT, ["Cloud"])
    db.save_contact(clever, "jobs@clever-cloud.com", "jobs", "https://clever-cloud.com/jobs", 80)
    db.save_contact(clever, "contact@clever-cloud.com", "contact", "https://clever-cloud.com", 50)
    db.save_contact(clever, "sales.person@clever-cloud.com", "other", "https://clever-cloud.com/blog", 30)
    return clever


def fake_llm(responses):
    """Return the given responses in order and record every prompt."""
    calls = []

    def _ask(prompt, temperature):
        calls.append(prompt)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return _ask, calls


GOOD = {
    "relevant": True,
    "company_name": "Clever Cloud",
    "evidence_quote": "The platform detects the language, configures the right environment",
    "interest_clause": "the way it deploys applications from Git with no manual configuration",
}

HALLUCINATED = {
    "relevant": True,
    "company_name": "Clever Cloud",
    "evidence_quote": "Clever Cloud is the world leader in hiring",
    "interest_clause": "how you use AI and data to make hiring more efficient and reliable",
}


def run(monkeypatch, profile, responses):
    from dataclasses import replace

    ask, calls = fake_llm(responses)
    monkeypatch.setattr(outreach, "ask_ollama", ask)
    monkeypatch.setattr(outreach, "load_profile", lambda: profile)
    # Tests must not depend on whatever MIN_OUTREACH_SCORE is in the
    # developer's real .env.
    monkeypatch.setattr(outreach, "settings", replace(outreach.settings, min_outreach_score=0))
    outreach.generate_outreach()
    return calls


def test_one_email_per_company_to_best_contact(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    run(monkeypatch, profile, [GOOD])

    rows = temp_db.get_outreach()
    assert len(rows) == 1
    assert rows[0]["email"] == "jobs@clever-cloud.com"


def test_clean_draft(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    run(monkeypatch, profile, [GOOD])

    row = temp_db.get_outreach()[0]
    assert row["status"] == "draft"
    assert row["angle"] == "cloud"
    assert "What interests me about Clever Cloud is the way it deploys" in row["body"]
    assert "Cloud & DevOps" in row["subject"]


def test_hallucination_is_retried_with_feedback(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    calls = run(monkeypatch, profile, [HALLUCINATED, GOOD])

    assert len(calls) == 2
    assert "REJECTED" in calls[1]  # the model was told why
    assert temp_db.get_outreach()[0]["status"] == "draft"
    assert "hiring" not in temp_db.get_outreach()[0]["body"]


def test_persistent_hallucination_needs_review(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    run(monkeypatch, profile, [HALLUCINATED])

    row = temp_db.get_outreach()[0]
    assert row["status"] == "needs_review"
    assert row["notes"]


def test_irrelevant_company_is_flagged(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    run(monkeypatch, profile, [{"relevant": False}])

    row = temp_db.get_outreach()[0]
    assert row["status"] == "needs_review"
    assert "not a tech company" in row["notes"]


def test_rerun_does_not_duplicate(temp_db, monkeypatch, profile):
    setup_companies(temp_db)
    run(monkeypatch, profile, [GOOD])
    calls = run(monkeypatch, profile, [GOOD])

    assert calls == []
    assert len(temp_db.get_outreach()) == 1


def test_bulk_approve_clean_leaves_needs_review_alone(temp_db, monkeypatch):
    temp_db.upsert_company({"name": "Clean", "domain": "clean.com", "verified": 1})
    temp_db.save_outreach(1, None, "s", "b", status="draft")
    temp_db.upsert_company({"name": "Flagged", "domain": "flag.com", "verified": 1})
    temp_db.save_outreach(2, None, "s", "b", status="needs_review", notes="evidence_quote not found")

    monkeypatch.setattr("builtins.input", lambda *_: "YES")
    outreach.bulk_approve_clean()

    statuses = {r["name"]: r["status"] for r in temp_db.get_outreach()}
    assert statuses == {"Clean": "approved", "Flagged": "needs_review"}


def test_bulk_approve_clean_requires_confirmation(temp_db, monkeypatch):
    temp_db.upsert_company({"name": "Clean", "domain": "clean.com", "verified": 1})
    temp_db.save_outreach(1, None, "s", "b", status="draft")

    monkeypatch.setattr("builtins.input", lambda *_: "no")
    outreach.bulk_approve_clean()

    assert temp_db.get_outreach()[0]["status"] == "draft"
