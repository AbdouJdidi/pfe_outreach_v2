import sqlite3

import pytest

from src import db
from tests.conftest import add_company


def test_migration_adds_columns_to_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("""
        CREATE TABLE outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
            contact_id INTEGER, subject TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT DEFAULT 'draft', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)
    """)
    old.execute("INSERT INTO outreach (company_id, subject, body) VALUES (1, 's', 'b')")
    old.commit()
    old.close()

    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()

    with db.connect() as c:
        columns = {row["name"] for row in c.execute("PRAGMA table_info(outreach)")}
        rows = c.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]

    assert {"evidence_quote", "angle", "sent_at", "greeting"} <= columns
    assert rows == 1  # existing data kept


def test_delete_unsent_keeps_approved_and_sent(temp_db):
    add_company("Acme", "acme.com", "Acme builds software.")
    for status in ["draft", "needs_review", "rejected", "approved", "sent"]:
        temp_db.save_outreach(1, None, "s", "b", status=status)

    assert temp_db.delete_unsent_outreach() == 3
    assert sorted(r["status"] for r in temp_db.get_outreach()) == ["approved", "sent"]


def test_update_outreach_rejects_unknown_status(temp_db):
    add_company("Acme", "acme.com", "Acme builds software.")
    temp_db.save_outreach(1, None, "s", "b")
    outreach_id = temp_db.get_outreach()[0]["id"]

    with pytest.raises(ValueError):
        temp_db.update_outreach(outreach_id, status="maybe")
