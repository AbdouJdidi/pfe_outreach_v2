"""
Send approved outreach emails through Gmail (SMTP + App Password).

- Only drafts with status 'approved' are sent.
- CV is attached to every email.
- Random delay between emails + a daily cap, so Gmail doesn't flag you.
- --dry-run sends every email to YOURSELF (subject shows the real recipient)
  and changes nothing in the database.
"""

import random
import smtplib
import ssl
import time
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from .config import settings
from .db import connect, get_outreach, update_outreach


def check_settings():
    problems = []

    if not settings.gmail_address or "@" not in settings.gmail_address:
        problems.append("GMAIL_ADDRESS is missing in .env")
    if not settings.gmail_app_password:
        problems.append("GMAIL_APP_PASSWORD is missing in .env")

    cv = Path(settings.cv_path).expanduser()
    if not cv.is_file():
        problems.append(f"CV not found at: {cv}")

    if problems:
        raise SystemExit("\n❌ Can't send yet:\n   - " + "\n   - ".join(problems) + "\n")

    return cv


def sent_today():
    today = date.today().isoformat()
    with connect() as c:
        return c.execute(
            "SELECT COUNT(*) FROM outreach WHERE status = 'sent' AND sent_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]


def open_smtp():
    """Try SSL on 465, then STARTTLS on 587 (some networks/antivirus block 465)."""
    context = ssl.create_default_context()
    errors = []

    for port in (465, 587):
        try:
            if port == 465:
                smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30)
            else:
                smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()

            smtp.login(settings.gmail_address, settings.gmail_app_password)
            print(f"Connected to Gmail (port {port}).")
            return smtp

        except smtplib.SMTPAuthenticationError as e:
            raise SystemExit(
                "\n❌ Gmail rejected the login.\n"
                "   - GMAIL_APP_PASSWORD must be the 16-char App Password, not your normal password\n"
                "   - 2-Step Verification must be ON for this account\n"
                f"   Gmail said: {e.smtp_error.decode(errors='ignore')}\n"
            ) from None
        except (smtplib.SMTPException, OSError) as e:
            errors.append(f"port {port}: {type(e).__name__}: {e}")

    raise SystemExit(
        "\n❌ Could not connect to Gmail:\n   - " + "\n   - ".join(errors) +
        "\n   Likely causes: antivirus 'mail shield' scanning SMTP, a VPN/proxy, "
        "or the network blocking SMTP.\n"
    )


def build_message(row, cv_path, to_address, subject):
    msg = EmailMessage()
    msg["From"] = formataddr((settings.sender_name, settings.gmail_address))
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=settings.gmail_address.split("@")[1])
    msg.set_content(row["body"])

    msg.add_attachment(
        cv_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=cv_path.name,
    )
    return msg


def send_approved(dry_run=False, limit=None):
    cv_path = check_settings()
    rows = list(reversed(get_outreach("approved")))  # oldest approved first

    if not rows:
        print("No approved drafts. Run: python -m src.main review")
        return

    if dry_run:
        remaining = len(rows)
    else:
        remaining = max(0, settings.daily_send_limit - sent_today())
        if remaining == 0:
            print(f"Daily limit of {settings.daily_send_limit} reached. Try tomorrow.")
            return

    if limit:
        remaining = min(remaining, limit)

    batch = rows[:remaining]
    mode = "DRY RUN → all emails go to YOU" if dry_run else "LIVE"

    print(f"\n{mode}: sending {len(batch)} of {len(rows)} approved emails")
    print(f"From: {settings.gmail_address}   CV: {cv_path.name}\n")

    if not dry_run:
        for row in batch:
            print(f"   • {row['name']:<25} → {row['email']}")
        if input("\nType SEND to confirm: ").strip() != "SEND":
            print("Cancelled.")
            return

    sent = 0

    with open_smtp() as smtp:
        for i, row in enumerate(batch):
            if dry_run:
                to_address = settings.gmail_address
                subject = f"[TEST → {row['email']}] {row['subject']}"
            else:
                to_address = row["email"]
                subject = row["subject"]

            try:
                smtp.send_message(build_message(row, cv_path, to_address, subject))
            except smtplib.SMTPException as e:
                print(f"✗ {row['name']}: {e}")
                update_outreach(row["id"], notes=f"send failed: {e}")
                continue

            sent += 1
            print(f"✓ {row['name']} → {to_address}")

            if not dry_run:
                update_outreach(
                    row["id"],
                    status="sent",
                    sent_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    notes=None,
                )

            if i < len(batch) - 1:
                if dry_run:
                    time.sleep(2)
                else:
                    wait = random.randint(settings.send_delay_min, settings.send_delay_max)
                    print(f"   waiting {wait}s...")
                    time.sleep(wait)

    print(f"\nDone: {sent} sent." + ("  (dry run — database unchanged)" if dry_run else ""))