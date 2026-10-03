import sqlite3
from pathlib import Path
import json


DB_PATH = Path("data/pfe_agent.db")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")

    return c


def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT UNIQUE NOT NULL,
            website TEXT,
            location TEXT,
            company_type TEXT,
            description TEXT,
            source TEXT,
            source_url TEXT,
            raw_text TEXT,
            fetched_text TEXT,
            verified INTEGER DEFAULT 0,
            discovery_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS analyses (
            company_id INTEGER PRIMARY KEY,
            score INTEGER,
            priority TEXT,
            domains TEXT,
            remote_compatible INTEGER,
            pfe_potential TEXT,
            reasoning TEXT,
            raw_json TEXT,
            analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            company_id INTEGER NOT NULL,

            email TEXT NOT NULL,

            contact_type TEXT DEFAULT 'other',

            source_url TEXT,

            confidence INTEGER DEFAULT 0,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,

            UNIQUE(company_id, email)
        );

        CREATE INDEX IF NOT EXISTS idx_companies_domain
        ON companies(domain);

        CREATE INDEX IF NOT EXISTS idx_companies_verified
        ON companies(verified);

        CREATE INDEX IF NOT EXISTS idx_analyses_score
        ON analyses(score);

        CREATE INDEX IF NOT EXISTS idx_contacts_company
        ON contacts(company_id);

        CREATE INDEX IF NOT EXISTS idx_contacts_email
        ON contacts(email);


                CREATE TABLE IF NOT EXISTS outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            company_id INTEGER NOT NULL,
            contact_id INTEGER,

            subject TEXT NOT NULL,
            body TEXT NOT NULL,

            status TEXT DEFAULT 'draft',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,

            FOREIGN KEY(contact_id)
                REFERENCES contacts(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_outreach_company
        ON outreach(company_id);

        CREATE INDEX IF NOT EXISTS idx_outreach_status
        ON outreach(status);
        """)

    migrate_outreach()


OUTREACH_EXTRA_COLUMNS = {
    "greeting": "TEXT",
    "company_paragraph": "TEXT",
    "evidence_quote": "TEXT",
    "angle": "TEXT",
    "notes": "TEXT",
    "sent_at": "TEXT",
}


def migrate_outreach():
    """Add new outreach columns to existing databases without losing data."""
    with connect() as c:
        existing = {
            row["name"]
            for row in c.execute("PRAGMA table_info(outreach)")
        }
        for column, kind in OUTREACH_EXTRA_COLUMNS.items():
            if column not in existing:
                c.execute(f"ALTER TABLE outreach ADD COLUMN {column} {kind}")


def upsert_company(x):
    with connect() as c:
        c.execute("""
            INSERT INTO companies (
                name,
                domain,
                website,
                location,
                company_type,
                description,
                source,
                source_url,
                raw_text,
                verified,
                discovery_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(domain) DO UPDATE SET

                name = CASE
                    WHEN excluded.name IS NOT NULL
                    AND excluded.name != ''
                    THEN excluded.name
                    ELSE companies.name
                END,

                website = COALESCE(
                    excluded.website,
                    companies.website
                ),

                location = COALESCE(
                    excluded.location,
                    companies.location
                ),

                company_type = COALESCE(
                    excluded.company_type,
                    companies.company_type
                ),

                description = COALESCE(
                    excluded.description,
                    companies.description
                ),

                source = COALESCE(
                    excluded.source,
                    companies.source
                ),

                source_url = COALESCE(
                    excluded.source_url,
                    companies.source_url
                ),

                raw_text = COALESCE(
                    excluded.raw_text,
                    companies.raw_text
                ),

                verified = MAX(
                    companies.verified,
                    excluded.verified
                ),

                discovery_score = MAX(
                    companies.discovery_score,
                    excluded.discovery_score
                ),

                updated_at = CURRENT_TIMESTAMP
        """, (
            x.get("name"),
            x.get("domain"),
            x.get("website"),
            x.get("location"),
            x.get("company_type"),
            x.get("description"),
            x.get("source"),
            x.get("source_url"),
            x.get("raw_text"),
            int(x.get("verified", 0)),
            int(x.get("discovery_score", 0)),
        ))


def get_unanalyzed(limit=100):
    with connect() as c:
        return c.execute("""
            SELECT c.*
            FROM companies c
            LEFT JOIN analyses a
                ON a.company_id = c.id
            WHERE a.company_id IS NULL
              AND c.verified = 1
            ORDER BY c.discovery_score DESC, c.id
            LIMIT ?
        """, (limit,)).fetchall()


def save_fetched_text(cid, text):
    with connect() as c:
        c.execute("""
            UPDATE companies
            SET fetched_text = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (text[:30000], cid))


def save_analysis(cid, r):
    with connect() as c:
        c.execute("""
            INSERT INTO analyses (
                company_id,
                score,
                priority,
                domains,
                remote_compatible,
                pfe_potential,
                reasoning,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(company_id) DO UPDATE SET

                score = excluded.score,
                priority = excluded.priority,
                domains = excluded.domains,
                remote_compatible = excluded.remote_compatible,
                pfe_potential = excluded.pfe_potential,
                reasoning = excluded.reasoning,
                raw_json = excluded.raw_json,
                analyzed_at = CURRENT_TIMESTAMP
        """, (
            cid,
            r["score"],
            r["priority"],
            json.dumps(r["domains"], ensure_ascii=False),
            int(r["remote_compatible"]),
            r["pfe_potential"],
            r["reasoning"],
            json.dumps(r, ensure_ascii=False),
        ))


def ranked(limit=50):
    with connect() as c:
        return c.execute("""
            SELECT
                c.id,
                c.name,
                c.domain,
                c.website,
                c.location,
                c.company_type,
                c.source,
                c.verified,
                c.discovery_score,
                c.fetched_text,
                a.score,
                a.priority,
                a.domains,
                a.remote_compatible,
                a.pfe_potential,
                a.reasoning,
                a.raw_json
            FROM companies c
            JOIN analyses a
                ON a.company_id = c.id
            ORDER BY a.score DESC
            LIMIT ?
        """, (limit,)).fetchall()


def save_contact(
    company_id,
    email,
    contact_type="other",
    source_url="",
    confidence=0,
):
    with connect() as c:
        c.execute("""
            INSERT INTO contacts (
                company_id,
                email,
                contact_type,
                source_url,
                confidence
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(company_id, email) DO UPDATE SET

                contact_type = excluded.contact_type,

                source_url = excluded.source_url,

                confidence = MAX(
                    contacts.confidence,
                    excluded.confidence
                )
        """, (
            company_id,
            email.lower().strip(),
            contact_type,
            source_url,
            confidence,
        ))


def get_contacts(limit=100):
    with connect() as c:
        return c.execute("""
            SELECT
                contacts.id,
                contacts.company_id,
                companies.name,
                companies.domain,
                companies.website,
                contacts.email,
                contacts.contact_type,
                contacts.source_url,
                contacts.confidence
            FROM contacts
            JOIN companies
                ON companies.id = contacts.company_id
            ORDER BY
                contacts.confidence DESC,
                companies.name
            LIMIT ?
        """, (limit,)).fetchall()


def get_companies_for_contacts():
    with connect() as c:
        return c.execute("""
            SELECT
                c.id,
                c.name,
                c.domain,
                c.website,
                c.fetched_text,
                a.raw_json
            FROM companies c
            JOIN analyses a
                ON a.company_id = c.id
            WHERE c.verified = 1
            ORDER BY a.score DESC
        """).fetchall()


def stats():
    with connect() as c:
        companies = c.execute(
            "SELECT COUNT(*) FROM companies"
        ).fetchone()[0]

        verified = c.execute(
            "SELECT COUNT(*) FROM companies WHERE verified = 1"
        ).fetchone()[0]

        analyzed = c.execute(
            "SELECT COUNT(*) FROM analyses"
        ).fetchone()[0]

        contacts = c.execute(
            "SELECT COUNT(*) FROM contacts"
        ).fetchone()[0]

        return {
            "companies": companies,
            "verified": verified,
            "analyzed": analyzed,
            "contacts": contacts,
        }

OUTREACH_STATUSES = {"draft", "needs_review", "approved", "rejected", "sent"}


def save_outreach(
    company_id,
    contact_id,
    subject,
    body,
    status="draft",
    greeting=None,
    company_paragraph=None,
    evidence_quote=None,
    angle=None,
    notes=None,
):
    with connect() as c:
        c.execute("""
            INSERT INTO outreach (
                company_id, contact_id, subject, body, status,
                greeting, company_paragraph, evidence_quote, angle, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id, contact_id, subject, body, status,
            greeting, company_paragraph, evidence_quote, angle, notes,
        ))


def update_outreach(outreach_id, **fields):
    allowed = {
        "subject", "body", "status", "greeting", "company_paragraph",
        "evidence_quote", "angle", "notes", "sent_at",
    }
    fields = {k: v for k, v in fields.items() if k in allowed}

    if not fields:
        return

    if "status" in fields and fields["status"] not in OUTREACH_STATUSES:
        raise ValueError(f"Unknown status: {fields['status']}")

    assignments = ", ".join(f"{k} = ?" for k in fields)

    with connect() as c:
        c.execute(
            f"""
            UPDATE outreach
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*fields.values(), outreach_id),
        )


def companies_with_outreach():
    with connect() as c:
        return {
            row[0]
            for row in c.execute("SELECT DISTINCT company_id FROM outreach")
        }


def delete_unsent_outreach(company_id=None):
    """Delete drafts that were not approved or sent. Returns deleted count."""
    query = """
        DELETE FROM outreach
        WHERE status IN ('draft', 'needs_review', 'rejected')
    """
    params = ()

    if company_id is not None:
        query += " AND company_id = ?"
        params = (company_id,)

    with connect() as c:
        return c.execute(query, params).rowcount


def get_outreach(status=None):
    query = """
        SELECT
            o.id,
            o.company_id,
            o.contact_id,
            c.name,
            c.website,
            c.fetched_text,
            ct.email,
            ct.contact_type,
            o.subject,
            o.body,
            o.status,
            o.greeting,
            o.company_paragraph,
            o.evidence_quote,
            o.angle,
            o.notes,
            o.created_at
        FROM outreach o
        JOIN companies c
            ON c.id = o.company_id
        LEFT JOIN contacts ct
            ON ct.id = o.contact_id
    """
    params = ()

    if status:
        statuses = [s.strip() for s in status.split(",")]
        query += f" WHERE o.status IN ({','.join('?' * len(statuses))})"
        params = tuple(statuses)

    query += " ORDER BY o.created_at DESC, o.id DESC"

    with connect() as c:
        return c.execute(query, params).fetchall()
