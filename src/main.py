import argparse

from .db import init_db
from .discovery import discover
from .research import research_pending
from .analyze import analyze
from .contacts import discover_contacts, show_contacts
from .sender import send_approved
from .outreach import (
    generate_outreach,
    reset_outreach,
    review_outreach,
    show_outreach,
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="PFE Outreach Agent",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("discover", help="find candidate companies")
    sub.add_parser("research", help="fetch company websites")
    sub.add_parser("analyze", help="classify and score companies")
    sub.add_parser("contacts", help="find contact emails")
    sub.add_parser("show-contacts", help="list contacts")
    sub.add_parser("all", help="discover → research → analyze → contacts")

    p = sub.add_parser("outreach", help="generate email drafts")
    p.add_argument("--regenerate", action="store_true",
                   help="delete unsent drafts and generate again")
    p.add_argument("--limit", type=int, help="only generate N drafts")

    p = sub.add_parser("show-outreach", help="print drafts")
    p.add_argument("--status",
                   help="filter, e.g. draft,needs_review or approved")

    sub.add_parser("review", help="approve / edit / reject drafts one by one")
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
        discover()
    elif args.command == "research":
        research_pending()
    elif args.command == "analyze":
        analyze()
    elif args.command == "contacts":
        discover_contacts()
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
        review_outreach()
    elif args.command == "reset-outreach":
        reset_outreach()
    elif args.command == "send":
        send_approved(dry_run=args.dry_run, limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()