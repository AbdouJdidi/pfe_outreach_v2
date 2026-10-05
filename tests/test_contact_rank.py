import pytest

from src.outreach import choose_contacts, contact_rank
from tests.conftest import add_company


@pytest.mark.parametrize("email,ctype,source,expected", [
    ("jobs@acme.com", "jobs", "https://acme.com/careers", 0),
    ("hr@acme.com", "hr", "https://acme.com", 0),
    ("talent@acme.com", "other", "https://acme.com/careers", 1),
    ("contact@acme.com", "contact", "https://acme.com", 2),
    ("info@acme.com", "info", "https://acme.com", 3),
    ("erik.simins@acme.com", "other", "https://acme.com/about", 4),
    ("mduda@acme.com", "other", "https://acme.com/team", 4),
    ("sales@acme.com", "other", "https://acme.com", None),
    ("press@acme.com", "other", "https://acme.com", None),
    ("noreply@acme.com", "other", "https://acme.com", None),
    ("billing@acme.com", "other", "https://acme.com", None),
])
def test_contact_rank(email, ctype, source, expected):
    contact = {"email": email, "contact_type": ctype, "source_url": source}
    assert contact_rank(contact) == expected


def test_company_with_only_a_personal_email_is_still_chosen(temp_db):

    """Regression: this used to silently drop every such company."""
    cid = add_company("WorkWolf", "workwolf.com", "We build hiring software.")
    temp_db.save_contact(cid, "erik.simins@workwolf.com", "other", "https://workwolf.com/about", 40)

    chosen = choose_contacts(min_score=0)
    assert [c["email"] for c in chosen] == ["erik.simins@workwolf.com"]


def test_company_with_only_functional_emails_is_skipped(temp_db):
    cid = add_company("Acme", "acme.com", "We sell stuff.")
    temp_db.save_contact(cid, "sales@acme.com", "other", "https://acme.com", 40)
    temp_db.save_contact(cid, "press@acme.com", "other", "https://acme.com/news", 40)

    assert choose_contacts(min_score=0) == []


def test_jobs_address_still_beats_a_personal_one(temp_db):
    cid = add_company("Acme", "acme.com", "We build software.")
    temp_db.save_contact(cid, "erik@acme.com", "other", "https://acme.com/about", 40)
    temp_db.save_contact(cid, "jobs@acme.com", "jobs", "https://acme.com/careers", 40)

    chosen = choose_contacts(min_score=0)
    assert [c["email"] for c in chosen] == ["jobs@acme.com"]
