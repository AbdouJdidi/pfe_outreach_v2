import json

from rich.console import Console
from rich.table import Table

from .db import ranked

COLUMNS = ["#", "Company", "Location", "Type", "Score", "Priority", "Domains", "PFE"]


def show_report(limit=30):
    rows = ranked(limit)
    table = Table(title=f"Top {limit} PFE Candidates")

    for column in COLUMNS:
        table.add_column(column)

    for i, r in enumerate(rows, 1):
        table.add_row(
            str(i),
            r["name"][:28],
            (r["location"] or "Unknown")[:18],
            r["company_type"] or "?",
            str(r["score"]),
            r["priority"],
            ", ".join(json.loads(r["domains"] or "[]"))[:30],
            r["pfe_potential"],
        )

    Console().print(table)

    for i, r in enumerate(rows[:10], 1):
        print(f"{i}. {r['name']}: {r['reasoning']}")
