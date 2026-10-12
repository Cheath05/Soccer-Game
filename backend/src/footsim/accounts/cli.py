"""`footsim users ...`: add, list, change and remove the accounts that may play on this server.

The server only asks for accounts when it runs with FOOTSIM_AUTH=1 (deploy/README.md); until
then everyone who can reach it plays as the owner, as before accounts existed.
"""

import argparse
import getpass
import secrets
import shutil
import sys
from pathlib import Path

from footsim.accounts.store import USERS_DIR, AccountError, AccountStore, saves_root
from footsim.core.paths import saves_dir
from footsim.defs.loader import load_server


def _password(args: argparse.Namespace, min_length: int) -> tuple[str, bool]:
    """The new password, and whether it was made up here (and so must be shown)."""
    if args.generate:
        return secrets.token_urlsafe(max(9, min_length)), True
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n"), False
    first = getpass.getpass(f"Password (at least {min_length} characters): ")
    if getpass.getpass("Again: ") != first:
        raise AccountError("the two passwords differ")
    return first, False


def _add(store: AccountStore, args: argparse.Namespace) -> int:
    min_length = load_server().min_password_length
    password, made_up = _password(args, min_length)
    account = store.add(args.name, password, owner=args.owner, min_password_length=min_length)
    kind = "owner" if account.is_owner else "player"
    print(f"Added {account.name} ({kind}); careers in {saves_root(account, args.saves)}")
    if made_up:
        print(f"Password: {password}")
    return 0


def _list(store: AccountStore, args: argparse.Namespace) -> int:
    accounts = store.accounts()
    if not accounts:
        print("No accounts yet. Add the owner first: footsim users add NAME --owner")
    for account in accounts:
        flags = [f for f, on in (("owner", account.is_owner), ("disabled", account.disabled))
                 if on]
        signed_in = store.session_count(account)
        print(f"{account.name:<20} {', '.join(flags) or 'player':<16} "
              f"signed in on {signed_in} device{'s' if signed_in != 1 else ''}")
    return 0


def _reset(store: AccountStore, args: argparse.Namespace) -> int:
    min_length = load_server().min_password_length
    password, made_up = _password(args, min_length)
    store.set_password(args.name, password, min_password_length=min_length)
    print(f"New password set for {store.get(args.name).name}; signed out everywhere")
    if made_up:
        print(f"Password: {password}")
    return 0


def _disable(store: AccountStore, args: argparse.Namespace) -> int:
    store.set_disabled(args.name, not args.enable)
    print(f"{store.get(args.name).name} {'enabled' if args.enable else 'disabled'}")
    return 0


def _rename(store: AccountStore, args: argparse.Namespace) -> int:
    old = store.get(args.name).name
    account = store.rename(args.name, args.new_name)
    print(f"{old} is now {account.name}: they sign in with the new name; careers unchanged")
    return 0


def _remove(store: AccountStore, args: argparse.Namespace) -> int:
    account = store.get(args.name)
    if account.is_owner:
        raise AccountError("the owner can't be removed (their careers are the saves folder "
                           "itself); disable the account instead")
    store.remove(args.name)
    folder = saves_root(account, args.saves)
    if args.delete_saves and folder.is_dir():
        if folder.resolve().parent != (args.saves / USERS_DIR).resolve():
            raise AccountError(f"refusing to delete {folder}: not a player's own folder")
        shutil.rmtree(folder)
        print(f"Removed {account.name} and deleted {folder}")
    else:
        print(f"Removed {account.name}; their careers stay in {folder}")
    return 0


def run(args: argparse.Namespace) -> int:
    try:
        store = AccountStore.in_saves(args.saves)
    except AccountError as exc:
        print(f"footsim users: {exc}", file=sys.stderr)
        return 1
    try:
        result: int = args.action(store, args)
        return result
    except AccountError as exc:
        print(f"footsim users: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


def add_parser(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    users = sub.add_parser("users", help="the accounts that may play on this server")
    users.add_argument("--saves", type=Path, default=saves_dir(),
                       help="the server's saves folder (default: FOOTSIM_SAVES_DIR)")
    users.set_defaults(func=run)
    actions = users.add_subparsers(dest="users_command", required=True)

    def password_options(parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--generate", action="store_true",
                           help="make up a password and print it")
        group.add_argument("--password-stdin", action="store_true",
                           help="read the password from the first line of stdin")

    add = actions.add_parser("add", help="add an account")
    add.add_argument("name")
    add.add_argument("--owner", action="store_true",
                     help="the server's owner: plays from the saves folder itself (one only)")
    password_options(add)
    add.set_defaults(action=_add)

    actions.add_parser("list", help="list the accounts").set_defaults(action=_list)

    reset = actions.add_parser("reset-password", help="set a new password (signs them out)")
    reset.add_argument("name")
    password_options(reset)
    reset.set_defaults(action=_reset)

    rename = actions.add_parser("rename", help="change the name an account signs in with")
    rename.add_argument("name")
    rename.add_argument("new_name")
    rename.set_defaults(action=_rename)

    disable = actions.add_parser("disable", help="stop an account signing in")
    disable.add_argument("name")
    disable.add_argument("--enable", action="store_true", help="let it sign in again")
    disable.set_defaults(action=_disable)

    remove = actions.add_parser("remove", help="delete an account (its careers are kept)")
    remove.add_argument("name")
    remove.add_argument("--delete-saves", action="store_true",
                        help="also delete the account's careers")
    remove.set_defaults(action=_remove)
