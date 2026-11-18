"""Onboard a separate business without copying the application."""

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from workspace.config import validate_business
from workspace.security import hash_password

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--id", help="New business ID, e.g. acme")
parser.add_argument("--name", help="Business display name")
parser.add_argument("--website", help="HTTPS website origin")
parser.add_argument(
    "--password-hash",
    action="store_true",
    help="Generate an administrator password hash; input is hidden",
)
args = parser.parse_args()
if args.password_hash:
    password = getpass.getpass("Admin password (at least 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters")
    print(hash_password(password))
elif args.id and args.name and args.website:
    target = ROOT / "config" / "businesses" / (args.id + ".json")
    if not target.resolve().is_relative_to((ROOT / "config" / "businesses").resolve()):
        raise SystemExit("Invalid business ID")
    if target.exists():
        raise SystemExit("Business config already exists; no changes made")
    data = json.loads(
        (ROOT / "config" / "businesses" / "systematic.json").read_text(encoding="utf-8")
    )
    data.update(
        id=args.id,
        name=args.name,
        short_name=args.name[:25],
        website=args.website.rstrip("/"),
        allowed_origins=[args.website.rstrip("/")],
        navigation=[{"label": "Explore our website", "url": args.website.rstrip("/")}],
        welcome=f"Hello, I'm the {args.name} AI assistant. How can we help?",
        services=[],
        knowledge_directory="data/businesses/" + args.id,
        notification_email="",
    )
    validate_business(data)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    (ROOT / "data" / "businesses" / args.id).mkdir(parents=True, exist_ok=True)
    print(
        f"Created business {args.id}. Set its service catalog, add its own knowledge, and configure its administrator credentials before live use."
    )
else:
    parser.print_help()
