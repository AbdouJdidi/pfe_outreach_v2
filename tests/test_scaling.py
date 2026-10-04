"""Behaviour that matters once the pipeline handles hundreds of companies."""

from src import db
from src.outreach import choose_contacts
from tests.conftest import add_company


def set_score(company_id, score):
    with db.connect() as c:
        c.execute("UPDATE analyses SET score = ? WHERE company_id = ?", (score, company_id))


def test_low_score_companies_get_no_email(temp_db):
    good = add_company("Good", "good.com", "We build cloud software.")
    weak = add_company("Weak", "weak.com", "We sell furniture.")
    temp_db.save_contact(good, "jobs@good.com", "jobs", "https://good.com/jobs", 90)
    temp_db.save_contact(weak, "jobs@weak.com", "jobs", "https://weak.com/jobs", 90)
    set_score(weak, 20)

    chosen = {c["email"] for c in choose_contacts(min_score=50)}
    assert chosen == {"jobs@good.com"}


def test_contacts_scan_skips_companies_already_scanned(temp_db):
    scanned = add_company("Scanned", "scanned.com", "We build software.")
    add_company("New", "new.com", "We build software.")
    temp_db.save_contact(scanned, "jobs@scanned.com", "jobs", "x", 90)

    names = [r["name"] for r in temp_db.get_companies_for_contacts()]
    assert names == ["New"]
    assert len(temp_db.get_companies_for_contacts(include_scanned=True)) == 2


def test_stats_funnel(temp_db):
    a = add_company("A", "a.com", "We build software.")
    add_company("B", "b.com", "We build software.")
    temp_db.save_contact(a, "jobs@a.com", "jobs", "x", 90)
    temp_db.save_outreach(a, None, "s", "b", status="approved")

    data = temp_db.stats()
    assert data["funnel"]["companies"] == 2
    assert data["funnel"]["analyzed"] == 2
    assert data["funnel"]["with_contact"] == 1
    assert data["funnel"]["with_outreach"] == 1
    assert data["outreach"] == {"approved": 1}
