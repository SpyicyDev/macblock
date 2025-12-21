from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode = True

from macblock import __version__
from macblock.errors import MacblockError, PrivilegeError, UnsupportedPlatformError
from macblock.install import do_install, do_uninstall
from macblock.blocklists import list_blocklist_sources, set_blocklist_source, update_blocklist
from macblock.control import do_disable, do_enable, do_pause, do_resume
from macblock.doctor import run_diagnostics
from macblock.dns_test import test_domain
from macblock.lists import (
    add_blacklist,
    add_whitelist,
    list_blacklist,
    list_whitelist,
    remove_blacklist,
    remove_whitelist,
)
from macblock.platform import is_root, require_macos
from macblock.status import show_status


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="macblock")
    p.add_argument("--version", action="version", version=f"macblock {__version__}")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show status")
    sub.add_parser("doctor", help="Run diagnostics")

    p_install = sub.add_parser("install", help="Install system integration (root)")
    p_install.add_argument("--force", action="store_true")

    p_uninstall = sub.add_parser("uninstall", help="Uninstall system integration (root)")
    p_uninstall.add_argument("--force", action="store_true")

    sub.add_parser("enable", help="Enable interception (root)")
    sub.add_parser("disable", help="Disable interception (root)")

    p_pause = sub.add_parser("pause", help="Disable interception and auto-resume (root)")
    p_pause.add_argument("duration", help="Duration like 10m, 2h")

    sub.add_parser("resume", help="Resume interception now (root)")

    p_test = sub.add_parser("test", help="Test a domain")
    p_test.add_argument("domain")

    p_update = sub.add_parser("update", help="Update blocklist (root)")
    p_update.add_argument("--source", default=None)
    p_update.add_argument("--sha256", default=None)

    p_sources = sub.add_parser("sources", help="Manage blocklist sources")
    sources_sub = p_sources.add_subparsers(dest="sources_cmd", required=True)
    sources_sub.add_parser("list")
    sources_set = sources_sub.add_parser("set")
    sources_set.add_argument("source")

    p_allow = sub.add_parser("allow", help="Manage whitelist (root)")
    allow_sub = p_allow.add_subparsers(dest="allow_cmd", required=True)
    allow_add = allow_sub.add_parser("add")
    allow_add.add_argument("domain")
    allow_rm = allow_sub.add_parser("remove")
    allow_rm.add_argument("domain")
    allow_sub.add_parser("list")

    p_deny = sub.add_parser("deny", help="Manage blacklist (root)")
    deny_sub = p_deny.add_subparsers(dest="deny_cmd", required=True)
    deny_add = deny_sub.add_parser("add")
    deny_add.add_argument("domain")
    deny_rm = deny_sub.add_parser("remove")
    deny_rm.add_argument("domain")
    deny_sub.add_parser("list")

    return p


def _require_root(cmd: str, args: argparse.Namespace) -> None:
    if cmd in {"install", "uninstall", "enable", "disable", "pause", "resume", "update", "allow", "deny"}:
        if not is_root():
            raise PrivilegeError(f"Command '{cmd}' requires root (try: sudo macblock {cmd} ...)")

    if cmd == "sources" and getattr(args, "sources_cmd", None) == "set":
        if not is_root():
            raise PrivilegeError("Command 'sources set' requires root (try: sudo macblock sources set ...)")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        require_macos()
        parser = build_parser()
        args = parser.parse_args(argv)
        _require_root(args.cmd, args)

        if args.cmd == "status":
            return show_status()
        if args.cmd == "doctor":
            return run_diagnostics()
        if args.cmd == "install":
            return do_install(force=bool(args.force))
        if args.cmd == "uninstall":
            return do_uninstall(force=bool(args.force))
        if args.cmd == "enable":
            return do_enable()
        if args.cmd == "disable":
            return do_disable()
        if args.cmd == "pause":
            return do_pause(args.duration)
        if args.cmd == "resume":
            return do_resume()
        if args.cmd == "test":
            return test_domain(args.domain)
        if args.cmd == "update":
            return update_blocklist(source=args.source, sha256=args.sha256)
        if args.cmd == "sources":
            if args.sources_cmd == "list":
                return list_blocklist_sources()
            return set_blocklist_source(args.source)
        if args.cmd == "allow":
            if args.allow_cmd == "add":
                return add_whitelist(args.domain)
            if args.allow_cmd == "remove":
                return remove_whitelist(args.domain)
            return list_whitelist()
        if args.cmd == "deny":
            if args.deny_cmd == "add":
                return add_blacklist(args.domain)
            if args.deny_cmd == "remove":
                return remove_blacklist(args.domain)
            return list_blacklist()

        parser.error("unknown command")
        return 2
    except UnsupportedPlatformError as e:
        print(str(e), file=sys.stderr)
        return 2
    except PrivilegeError as e:
        print(str(e), file=sys.stderr)
        return 2
    except MacblockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
