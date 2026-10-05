import argparse

from .analyze import analyze
from .contacts import discover_contacts, show_contacts
from .db import init_db, stats
from .discovery import discover
from .outreach import (
    bulk_approve_clean,
    generate_outreach,
    quick_review,
    reset_outreach,
    review_outreach,
    show_outreach,
)
from .research import research_pending
from .sender import send_approved


def show_stats():
    data = stats()
    f = data["funnel"]
    steps = [
        ("Companies found", f["companies"]),
        ("Website researched", f["researched"]),
        ("Analyzed", f["analyzed"]),
        ("Have a contact email", f["with_contact"]),
        ("Have an email draft", f["with_outreach"]),
    ]

    print("\nPIPELINE")
    for label, value in steps:
        bar = "█" * min(40, value)
        print(f"  {label:<22} {value:>5}  {bar}")

    if data["priorities"]:
        print("\nPRIORITY  " + "   ".join(f"{k}: {v}" for k, v in data["priorities"].items()))

    if data["outreach"]:
        print("OUTREACH  " + "   ".join(f"{k}: {v}" for k, v in data["outreach"].items()))
    print()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="PFE Outreach Agent",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("discover", help="find candidate companies")
    p.add_argument("--query", action="append",
                   help='run only this search (repeatable), e.g. --query "DevOps startup Lyon"')
    sub.add_parser("research", help="fetch company websites")
    sub.add_parser("analyze", help="classify and score companies")
    p = sub.add_parser("contacts", help="find contact emails")
    p.add_argument("--all", action="store_true",
                   help="rescan companies that already have contacts")
    sub.add_parser("show-contacts", help="list contacts")
    sub.add_parser("all", help="discover → research → analyze → contacts")
    sub.add_parser("stats", help="show the pipeline funnel")

    p = sub.add_parser("outreach", help="generate email drafts")
    p.add_argument("--regenerate", action="store_true",
                   help="delete unsent drafts and generate again")
    p.add_argument("--limit", type=int, help="only generate N drafts")

    p = sub.add_parser("show-outreach", help="print drafts")
    p.add_argument("--status",
                   help="filter, e.g. draft,needs_review or approved")

    p = sub.add_parser("review", help="approve / edit / reject drafts one by one")
    p.add_argument("--quick", action="store_true",
                   help="one line per draft (company + AI sentence only)")
    p.add_argument("--auto-clean", action="store_true",
                   help="approve all drafts that passed every automated check, in one go")
    sub.add_parser("reset-outreach", help="delete all unsent drafts")

    p = sub.add_parser("send", help="send approved emails with your CV")
    p.add_argument("--dry-run", action="store_true",
                   help="send everything to yourself first")
    p.add_argument("--limit", type=int, help="send at most N emails")

    return parser


def main():
    init_db()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "discover":
        discover(queries=args.query)
    elif args.command == "research":
        research_pending()
    elif args.command == "analyze":
        analyze()
    elif args.command == "contacts":
        discover_contacts(include_scanned=args.all)
    elif args.command == "stats":
        show_stats()
    elif args.command == "show-contacts":
        show_contacts()
    elif args.command == "all":
        discover()
        research_pending()
        analyze()
        discover_contacts()
    elif args.command == "outreach":
        generate_outreach(regenerate=args.regenerate, limit=args.limit)
    elif args.command == "show-outreach":
        show_outreach(status=args.status)
    elif args.command == "review":
        if args.auto_clean:
            bulk_approve_clean()
        elif args.quick:
            quick_review()
        else:
            review_outreach()
    elif args.command == "reset-outreach":
        reset_outreach()
    elif args.command == "send":
        send_approved(dry_run=args.dry_run, limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()