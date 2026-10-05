"""Sending, with Gmail replaced by a fake SMTP server."""

import pytest

from src import sender

APPROVED = [
    ("Clever Cloud", "jobs@clever-cloud.com"),
    ("Lynkod", "contact@lynkod.com"),
]


class FakeSMTP:
    sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send_message(self, msg):
        FakeSMTP.sent.append({
            "to": msg["To"],
            "subject": msg["Subject"],
            "attachments": [p.get_filename() for p in msg.iter_attachments()],
        })


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(sender, "open_smtp", FakeSMTP)
    monkeypatch.setattr(sender.time, "sleep", lambda s: None)
    return FakeSMTP


@pytest.fixture
def ready(temp_db, tmp_path, override_settings):
    cv = tmp_path / "My_CV.pdf"
    cv.write_bytes(b"%PDF-1.4 test")
    # Fixed, test-safe values: never depend on the developer's real .env
    # (which might have e.g. SEND_DELAY_MAX smaller than SEND_DELAY_MIN).
    override_settings(
        sender,
        gmail_address="me@gmail.com",
        gmail_app_password="x" * 16,
        cv_path=str(cv),
        send_delay_min=0,
        send_delay_max=0,
        daily_send_limit=15,
    )

    for i, (name, email) in enumerate(APPROVED, start=1):
        temp_db.upsert_company({"name": name, "domain": f"c{i}.com", "verified": 1})
        temp_db.save_contact(i, email, "jobs", "x", 80)
        temp_db.save_outreach(i, i, f"PFE Application – {name}", "Dear Team,\n\nHello", status="approved")

    return temp_db


def statuses(db):
    return sorted(r["status"] for r in db.get_outreach())


def test_dry_run_sends_only_to_me_and_changes_nothing(ready, smtp):
    sender.send_approved(dry_run=True)

    assert [m["to"] for m in smtp.sent] == ["me@gmail.com", "me@gmail.com"]
    assert smtp.sent[0]["subject"].startswith("[TEST → jobs@clever-cloud.com]")
    assert statuses(ready) == ["approved", "approved"]


def test_live_send_attaches_cv_and_marks_sent(ready, smtp, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "SEND")
    sender.send_approved()

    assert {m["to"] for m in smtp.sent} == {"jobs@clever-cloud.com", "contact@lynkod.com"}
    assert all(m["attachments"] == ["My_CV.pdf"] for m in smtp.sent)
    assert statuses(ready) == ["sent", "sent"]


def test_live_send_needs_confirmation(ready, smtp, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "no")
    sender.send_approved()

    assert smtp.sent == []
    assert statuses(ready) == ["approved", "approved"]


def test_sent_emails_are_never_sent_twice(ready, smtp, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "SEND")
    sender.send_approved()
    sender.send_approved()

    assert len(smtp.sent) == 2


def test_daily_limit(ready, smtp, monkeypatch, override_settings):
    override_settings(sender, daily_send_limit=1)
    monkeypatch.setattr("builtins.input", lambda *_: "SEND")
    sender.send_approved()

    assert len(smtp.sent) == 1
    assert statuses(ready) == ["approved", "sent"]


def test_missing_cv_stops_before_sending(ready, smtp, override_settings):
    override_settings(sender, cv_path="does/not/exist.pdf")

    with pytest.raises(SystemExit, match="CV not found"):
        sender.send_approved(dry_run=True)
    assert smtp.sent == []
