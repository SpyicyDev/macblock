from __future__ import annotations

import importlib
import os
import shutil
import sys

from macblock import __version__
from macblock.errors import MacblockError, PrivilegeError, UnsupportedPlatformError
from macblock.install import do_install, do_uninstall
from macblock.blocklists import (
    list_blocklist_sources,
    set_blocklist_source,
    update_blocklist,
)
from macblock.control import do_disable, do_enable, do_pause, do_resume
from macblock.doctor import run_diagnostics
from macblock.dns_test import test_domain
from macblock.help import show_main_help, show_command_help
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


def _has_help_flag(args: list[str]) -> bool:
    """Check if args contain help flags."""
    return "-h" in args or "--help" in args


def _remove_help_flags(args: list[str]) -> list[str]:
    """Remove help flags from args."""
    return [a for a in args if a not in ("-h", "--help")]


def _get_help_context(args: list[str]) -> str | None:
    """Extract command context for help display.

    Returns the command (and subcommand if applicable) that help was requested for.
    """
    clean = _remove_help_flags(args)
    if not clean:
        return None

    cmd = clean[0]
    # Handle subcommands for sources, allow, deny
    if cmd in ("sources", "allow", "deny") and len(clean) >= 2:
        subcmd = clean[1]
        if subcmd not in ("-h", "--help"):
            return f"{cmd} {subcmd}"

    return cmd


def _needs_root(cmd: str, args: dict) -> bool:
    if cmd in {
        "install",
        "uninstall",
        "enable",
        "disable",
        "pause",
        "resume",
        "update",
    }:
        return True

    if cmd == "sources":
        return args.get("sources_cmd") == "set"

    if cmd == "allow":
        return args.get("allow_cmd") in ("add", "remove")

    if cmd == "deny":
        return args.get("deny_cmd") in ("add", "remove")

    return False


def _exec_sudo(argv: list[str]) -> None:
    sudo = shutil.which("sudo")
    if sudo is None:
        raise PrivilegeError("sudo not found")

    if os.environ.get("MACBLOCK_ELEVATED") == "1":
        raise PrivilegeError("failed to elevate privileges")

    env = dict(os.environ)
    env["MACBLOCK_ELEVATED"] = "1"

    exe = shutil.which(sys.argv[0])
    if exe:
        os.execve(sudo, [sudo, "-E", exe, *argv], env)

    os.execve(sudo, [sudo, "-E", sys.executable, "-m", "macblock", *argv], env)


def _parse_args(argv: list[str]) -> tuple[str | None, dict]:
    """Simple argument parser.

    Returns (command, args_dict). If help was requested, args will contain
    {"_help": True, "_help_context": "command"} and command will be "_help".
    """
    args: dict = {}

    if not argv:
        return "status", args

    # Handle --version first (can appear anywhere)
    if "--version" in argv or "-V" in argv:
        print(f"macblock {__version__}")
        sys.exit(0)

    # Check for help flag anywhere in args
    if _has_help_flag(argv):
        help_context = _get_help_context(argv)
        args["_help"] = True
        args["_help_context"] = help_context
        return "_help", args

    # Handle explicit "help" command
    if argv[0] == "help":
        rest = argv[1:]
        if rest:
            # "help sources set" -> "sources set"
            if len(rest) >= 2 and rest[0] in ("sources", "allow", "deny"):
                args["_help_context"] = f"{rest[0]} {rest[1]}"
            else:
                args["_help_context"] = rest[0]
        else:
            args["_help_context"] = None
        args["_help"] = True
        return "_help", args

    cmd = argv[0]
    rest = argv[1:]

    # Handle subcommands
    if cmd == "logs":
        args["component"] = "daemon"
        args["lines"] = 200
        args["follow"] = False
        args["stderr"] = False
        args["stream"] = "auto"
        i = 0
        while i < len(rest):
            if rest[i] == "--component" and i + 1 < len(rest):
                args["component"] = rest[i + 1]
                i += 2
            elif rest[i] == "--lines" and i + 1 < len(rest):
                args["lines"] = int(rest[i + 1])
                i += 2
            elif rest[i] == "--follow":
                args["follow"] = True
                i += 1
            elif rest[i] == "--stderr":
                args["stderr"] = True
                args["stream"] = "stderr"
                i += 1
            elif rest[i] == "--stream" and i + 1 < len(rest):
                args["stream"] = rest[i + 1]
                i += 2
            else:
                i += 1

    elif cmd == "install":
        args["force"] = "--force" in rest
        args["skip_update"] = "--skip-update" in rest

    elif cmd == "uninstall":
        args["force"] = "--force" in rest

    elif cmd == "pause":
        if rest:
            args["duration"] = rest[0]
        else:
            raise MacblockError("pause requires a duration (e.g., 10m, 2h, 1d)")

    elif cmd == "test":
        if rest:
            args["domain"] = rest[0]
        else:
            raise MacblockError("test requires a domain")

    elif cmd == "update":
        args["source"] = None
        args["sha256"] = None
        i = 0
        while i < len(rest):
            if rest[i] == "--source" and i + 1 < len(rest):
                args["source"] = rest[i + 1]
                i += 2
            elif rest[i] == "--sha256" and i + 1 < len(rest):
                args["sha256"] = rest[i + 1]
                i += 2
            else:
                i += 1

    elif cmd == "sources":
        if not rest:
            raise MacblockError("sources requires a subcommand: list or set")
        args["sources_cmd"] = rest[0]
        if rest[0] == "set":
            if len(rest) < 2:
                raise MacblockError("sources set requires a source name")
            args["source"] = rest[1]

    elif cmd == "allow":
        if not rest:
            raise MacblockError("allow requires a subcommand: add, remove, or list")
        args["allow_cmd"] = rest[0]
        if rest[0] in ("add", "remove"):
            if len(rest) < 2:
                raise MacblockError(f"allow {rest[0]} requires a domain")
            args["domain"] = rest[1]

    elif cmd == "deny":
        if not rest:
            raise MacblockError("deny requires a subcommand: add, remove, or list")
        args["deny_cmd"] = rest[0]
        if rest[0] in ("add", "remove"):
            if len(rest) < 2:
                raise MacblockError(f"deny {rest[0]} requires a domain")
            args["domain"] = rest[1]

    return cmd, args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        require_macos()

        cmd, args = _parse_args(argv)

        # Show help if no command provided
        if cmd is None:
            show_main_help()
            return 0

        # Handle help requests
        if cmd == "_help":
            help_context = args.get("_help_context")
            if help_context:
                show_command_help(help_context)
            else:
                show_main_help()
            return 0

        # Check if we need root
        if _needs_root(cmd, args) and not is_root():
            _exec_sudo(argv)

        if cmd == "status":
            return show_status()
        if cmd == "doctor":
            return run_diagnostics()
        if cmd == "daemon":
            from macblock.daemon import run_daemon

            return run_daemon()
        if cmd == "logs":
            show_logs = importlib.import_module("macblock.logs").show_logs
            return show_logs(
                component=str(args.get("component", "daemon")),
                lines=int(args.get("lines", 200)),
                follow=bool(args.get("follow", False)),
                stderr=bool(args.get("stderr", False)),
                stream=str(args.get("stream", "auto")),
            )
        if cmd == "install":
            return do_install(
                force=bool(args.get("force")), skip_update=bool(args.get("skip_update"))
            )
        if cmd == "uninstall":
            return do_uninstall(force=bool(args.get("force")))
        if cmd == "enable":
            return do_enable()
        if cmd == "disable":
            return do_disable()
        if cmd == "pause":
            return do_pause(args["duration"])
        if cmd == "resume":
            return do_resume()
        if cmd == "test":
            return test_domain(args["domain"])
        if cmd == "update":
            return update_blocklist(
                source=args.get("source"), sha256=args.get("sha256")
            )
        if cmd == "sources":
            if args.get("sources_cmd") == "list":
                return list_blocklist_sources()
            return set_blocklist_source(args["source"])
        if cmd == "allow":
            if args.get("allow_cmd") == "add":
                return add_whitelist(args["domain"])
            if args.get("allow_cmd") == "remove":
                return remove_whitelist(args["domain"])
            return list_whitelist()
        if cmd == "deny":
            if args.get("deny_cmd") == "add":
                return add_blacklist(args["domain"])
            if args.get("deny_cmd") == "remove":
                return remove_blacklist(args["domain"])
            return list_blacklist()

        print(f"error: unknown command: {cmd}", file=sys.stderr)
        print("Run 'macblock --help' for usage.", file=sys.stderr)
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
