import json
from dataclasses import replace
from pathlib import Path

import pytest

from src import db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite database."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


@pytest.fixture
def profile():
    return json.loads((ROOT / "profile.example.json").read_text(encoding="utf-8"))


@pytest.fixture
def override_settings(monkeypatch):
    """Settings is a frozen dataclass: swap in a modified copy per module."""

    def _override(module, **changes):
        monkeypatch.setattr(module, "settings", replace(module.settings, **changes))

    return _override


def add_company(name, domain, text, domains=("Software Engineering",)):
    db.upsert_company({
        "name": name, "domain": domain, "website": f"https://{domain}", "verified": 1,
    })
    with db.connect() as c:
        company_id = c.execute(
            "SELECT id FROM companies WHERE domain = ?", (domain,)
        ).fetchone()[0]
    db.save_fetched_text(company_id, text)
    db.save_analysis(company_id, {
        "score": 70, "priority": "HIGH", "domains": list(domains),
        "remote_compatible": False, "pfe_potential": "unknown", "reasoning": "",
    })
    return company_id
