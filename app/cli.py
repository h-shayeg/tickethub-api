"""Admin tasks that should not be exposed over HTTP.

Usage:
    python -m app.cli make-admin user@example.com
    python -m app.cli remove-admin user@example.com

The user must register through the API first. With Docker Compose:
    docker compose exec api python -m app.cli make-admin user@example.com
"""

import argparse
import sys

from app.core.database import SessionLocal
from app.services.user import UserNotFound, set_role

COMMANDS = {
    "make-admin": "admin",
    "remove-admin": "user",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, role in COMMANDS.items():
        sub = subcommands.add_parser(name, help=f"set the role of a user to '{role}'")
        sub.add_argument("email")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        try:
            user = set_role(db, args.email, COMMANDS[args.command])
        except UserNotFound:
            print(f"No user with email {args.email}. Register first.", file=sys.stderr)
            return 1

    print(f"{user.email} is now '{user.role}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
