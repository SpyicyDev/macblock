from __future__ import annotations

import sys
from .colors import Colors
from macblock import __version__


def format_help(text: str) -> str:
    """Helper to apply terminal colors to help text."""
    use_color = sys.stdout.isatty()

    replacements = {
        "bold": Colors.BOLD if use_color else "",
        "reset": Colors.RESET if use_color else "",
        "cyan": Colors.CYAN if use_color else "",
        "dim": Colors.DIM if use_color else "",
        "green": Colors.GREEN if use_color else "",
        "yellow": Colors.YELLOW if use_color else "",
        "red": Colors.RED if use_color else "",
        "version": __version__,
    }

    return text.format(**replacements)


MAIN_HELP = """{bold}DNS-level ad blocking for macOS using dnsmasq.{reset}

{bold}USAGE{reset}
  macblock <command> [flags]

{bold}STATUS & DIAGNOSTICS{reset}
  {green}status{reset}          Show current blocking status
  {green}doctor{reset}          Run diagnostics and health checks
  {green}logs{reset}            View daemon logs
  {green}test{reset}            Check if a domain is blocked

{bold}CONTROL{reset} {dim}(requires sudo){reset}
  {green}enable{reset}          Enable DNS blocking
  {green}disable{reset}         Disable DNS blocking
  {green}pause{reset}           Temporarily disable blocking
  {green}resume{reset}          Resume blocking after pause

{bold}INSTALLATION{reset} {dim}(requires sudo){reset}
  {green}install{reset}         Install system integration
  {green}uninstall{reset}       Remove system integration
  {green}update{reset}          Update blocklist from source

{bold}CONFIGURATION{reset}
  {green}sources{reset}         Manage blocklist sources
  {green}allow{reset}           Manage whitelisted domains {dim}(sudo for add/remove){reset}
  {green}deny{reset}            Manage blacklisted domains {dim}(sudo for add/remove){reset}
  {green}upstreams{reset}       Manage upstream DNS fallbacks {dim}(sudo for set/reset){reset}

{bold}FLAGS{reset}
  {yellow}-h, --help{reset}      Show help for command
  {yellow}-V, --version{reset}   Show version

{bold}EXAMPLES{reset}
  $ sudo macblock install
  $ sudo macblock enable
  $ macblock status
  $ macblock test example.com
  $ sudo macblock pause 30m

{bold}LEARN MORE{reset}
  Use 'macblock <command> --help' for more information about a command.

{dim}macblock v{version}{reset}
"""

COMMAND_HELP = {}

COMMAND_HELP["status"] = """{bold}USAGE{reset}
  macblock status

{bold}DESCRIPTION{reset}
  Show current blocking status, including whether the daemon is running,
  DNS configuration state, and the number of domains in the blocklist.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock status
"""

COMMAND_HELP["doctor"] = """{bold}USAGE{reset}
  macblock doctor

{bold}DESCRIPTION{reset}
  Run diagnostics and health checks to identify common issues with
  configuration, permissions, or conflicting services.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock doctor
"""

COMMAND_HELP["enable"] = """{bold}USAGE{reset}
  macblock enable

{bold}DESCRIPTION{reset}
  Enable DNS blocking. This sets the system DNS to 127.0.0.1 for all
  managed interfaces. Requires sudo privileges.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock enable
"""

COMMAND_HELP["disable"] = """{bold}USAGE{reset}
  macblock disable

{bold}DESCRIPTION{reset}
  Disable DNS blocking. This restores the system DNS to default settings.
  Requires sudo privileges.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock disable
"""

COMMAND_HELP["resume"] = """{bold}USAGE{reset}
  macblock resume

{bold}DESCRIPTION{reset}
  Resume blocking immediately after a pause. Requires sudo privileges.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock resume
"""

COMMAND_HELP["pause"] = """{bold}USAGE{reset}
  macblock pause <duration>

{bold}DESCRIPTION{reset}
  Temporarily disable blocking for a specified duration.
  Blocking will automatically resume after the timer expires.
  Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<duration>{reset}    Duration to pause (e.g., 10m, 2h, 1d)
                Units: m=minutes, h=hours, d=days

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock pause 30m
  $ sudo macblock pause 1h
"""

COMMAND_HELP["test"] = """{bold}USAGE{reset}
  macblock test <domain>

{bold}DESCRIPTION{reset}
  Check if a domain is blocked.
  Performs a DNS lookup against the local resolver.

{bold}ARGUMENTS{reset}
  {green}<domain>{reset}      Domain name to check (e.g., google-analytics.com)

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock test doubleclick.net
  $ macblock test example.com
"""

COMMAND_HELP["logs"] = """{bold}USAGE{reset}
  macblock logs [flags]

{bold}DESCRIPTION{reset}
  View daemon logs.
  Useful for debugging blocking issues or service failures.

{bold}FLAGS{reset}
  {yellow}--component <name>{reset}   Component: 'daemon' or 'dnsmasq' (default: daemon)
  {yellow}--lines <n>{reset}         Number of lines to show (default: 200)
  {yellow}--follow{reset}            Continuously follow log output (like tail -f)
  {yellow}--stream <name>{reset}     Stream: auto|stdout|stderr (default: auto)
  {yellow}--stderr{reset}            Alias for: --stream stderr

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock logs
  $ macblock logs --follow
  $ macblock logs --component dnsmasq --lines 50

{bold}NOTES{reset}
  Logs are stored in /Library/Logs/macblock/
"""

COMMAND_HELP["install"] = """{bold}USAGE{reset}
  macblock install [flags]

{bold}DESCRIPTION{reset}
  Install system integration. Sets up the launchd service, creates
  necessary directories, and downloads the initial blocklist.
  Requires sudo privileges.

{bold}FLAGS{reset}
  {yellow}--force{reset}         Force reinstall even if already installed
  {yellow}--skip-update{reset}   Skip downloading blocklist during install

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock install
  $ sudo macblock install --force
"""

COMMAND_HELP["uninstall"] = """{bold}USAGE{reset}
  macblock uninstall [flags]

{bold}DESCRIPTION{reset}
  Remove system integration. Stops services, removes launchd configuration,
  and cleans up data files. Requires sudo privileges.

{bold}FLAGS{reset}
  {yellow}--force{reset}         Force uninstall without confirmation

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock uninstall
"""

COMMAND_HELP["update"] = """{bold}USAGE{reset}
  macblock update [flags]

{bold}DESCRIPTION{reset}
  Update blocklist from source.
  Downloads the latest list, processes it, and restarts the resolver.
  Requires sudo privileges.

{bold}FLAGS{reset}
  {yellow}--source <name|url>{reset}   Specific source name or custom URL
  {yellow}--sha256 <hash>{reset}       Expected SHA256 hash for verification

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock update
  $ sudo macblock update --source oisd-small
  $ sudo macblock update --source https://example.com/hosts.txt
"""

COMMAND_HELP["sources"] = """{bold}USAGE{reset}
  macblock sources <subcommand> [args]

{bold}DESCRIPTION{reset}
  Manage blocklist sources. View available sources or switch to a different one.

{bold}SUBCOMMANDS{reset}
  {green}list{reset}          List available blocklist sources
  {green}set{reset}           Set blocklist source (requires sudo)

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock sources list
  $ sudo macblock sources set hagezi-pro

{bold}LEARN MORE{reset}
  Use 'macblock sources <subcommand> --help' for more info.
"""

COMMAND_HELP["sources list"] = """{bold}USAGE{reset}
  macblock sources list

{bold}DESCRIPTION{reset}
  List available blocklist sources.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock sources list
"""

COMMAND_HELP["sources set"] = """{bold}USAGE{reset}
  macblock sources set <name>

{bold}DESCRIPTION{reset}
  Set blocklist source.
  Available sources: stevenblack, stevenblack-fakenews, stevenblack-gambling,
  hagezi-pro, hagezi-ultimate, oisd-small, oisd-big.
  Can also be a custom URL.
  Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<name>{reset}        Source name or URL

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock sources set oisd-big
  $ sudo macblock sources set https://example.com/my-hosts.txt
"""

COMMAND_HELP["allow"] = """{bold}USAGE{reset}
  macblock allow <subcommand> [domain]

{bold}DESCRIPTION{reset}
  Manage whitelisted domains. Allowed domains bypass the blocklist.
  Requires sudo for add/remove.

{bold}SUBCOMMANDS{reset}
  {green}list{reset}          Show whitelisted domains
  {green}add{reset}           Add domain to whitelist
  {green}remove{reset}        Remove domain from whitelist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock allow list
  $ sudo macblock allow add example.com
"""

COMMAND_HELP["allow list"] = """{bold}USAGE{reset}
  macblock allow list

{bold}DESCRIPTION{reset}
  Show whitelisted domains.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command
"""

COMMAND_HELP["allow add"] = """{bold}USAGE{reset}
  macblock allow add <domain>

{bold}DESCRIPTION{reset}
  Add domain to whitelist. Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<domain>{reset}      Domain to whitelist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock allow add analytics.google.com
"""

COMMAND_HELP["allow remove"] = """{bold}USAGE{reset}
  macblock allow remove <domain>

{bold}DESCRIPTION{reset}
  Remove domain from whitelist. Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<domain>{reset}      Domain to remove from whitelist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command
"""

COMMAND_HELP["deny"] = """{bold}USAGE{reset}
  macblock deny <subcommand> [domain]

{bold}DESCRIPTION{reset}
  Manage blacklisted domains. Denied domains are always blocked.
  Requires sudo for add/remove.

{bold}SUBCOMMANDS{reset}
  {green}list{reset}          Show blacklisted domains
  {green}add{reset}           Add domain to blacklist
  {green}remove{reset}        Remove domain from blacklist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock deny list
  $ sudo macblock deny add tiktok.com
"""

COMMAND_HELP["deny list"] = """{bold}USAGE{reset}
  macblock deny list

{bold}DESCRIPTION{reset}
  Show blacklisted domains.

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command
"""

COMMAND_HELP["deny add"] = """{bold}USAGE{reset}
  macblock deny add <domain>

{bold}DESCRIPTION{reset}
  Add domain to blacklist. Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<domain>{reset}      Domain to blacklist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ sudo macblock deny add facebook.com
"""

COMMAND_HELP["deny remove"] = """{bold}USAGE{reset}
  macblock deny remove <domain>

{bold}DESCRIPTION{reset}
  Remove domain from blacklist. Requires sudo privileges.

{bold}ARGUMENTS{reset}
  {green}<domain>{reset}      Domain to remove from blacklist

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command
"""

COMMAND_HELP["upstreams"] = """{bold}USAGE{reset}
  macblock upstreams <subcommand> [args]

{bold}DESCRIPTION{reset}
  Manage upstream DNS configuration used by dnsmasq.

{bold}SUBCOMMANDS{reset}
  {green}fallbacks{reset}      Manage fallback upstream DNS servers

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command

{bold}EXAMPLES{reset}
  $ macblock upstreams fallbacks list
  $ sudo macblock upstreams fallbacks set
  $ sudo macblock upstreams fallbacks reset
"""

COMMAND_HELP["upstreams fallbacks"] = """{bold}USAGE{reset}
  macblock upstreams fallbacks <subcommand> [args]

{bold}DESCRIPTION{reset}
  Configure the last-resort upstream DNS servers used when no system/DHCP
  resolvers can be discovered.

{bold}SUBCOMMANDS{reset}
  {green}list{reset}           Show configured fallbacks (if any)
  {green}set{reset}            Set fallbacks (interactive if no IPs provided) {dim}(sudo){reset}
  {green}reset{reset}          Remove fallback config file {dim}(sudo){reset}

{bold}INHERITED FLAGS{reset}
  {yellow}-h, --help{reset}   Show help for command
"""

COMMAND_HELP["upstreams fallbacks list"] = """{bold}USAGE{reset}
  macblock upstreams fallbacks list

{bold}DESCRIPTION{reset}
  Show the configured fallback upstream DNS servers.
"""

COMMAND_HELP["upstreams fallbacks set"] = """{bold}USAGE{reset}
  macblock upstreams fallbacks set [ip...]

{bold}DESCRIPTION{reset}
  Set fallback upstream DNS servers.
  If no IPs are provided, prompts interactively.
  Requires sudo privileges.

{bold}EXAMPLES{reset}
  $ sudo macblock upstreams fallbacks set
  $ sudo macblock upstreams fallbacks set 9.9.9.9 149.112.112.112
"""

COMMAND_HELP["upstreams fallbacks reset"] = """{bold}USAGE{reset}
  macblock upstreams fallbacks reset

{bold}DESCRIPTION{reset}
  Remove the fallback config file so macblock uses built-in defaults.
  Requires sudo privileges.
"""


def show_main_help() -> None:
    """Show main help text."""
    print(format_help(MAIN_HELP))


def show_command_help(command: str) -> None:
    """Show help for a specific command."""
    if command in COMMAND_HELP:
        print(format_help(COMMAND_HELP[command]))
    else:
        # Fallback to main help if command not found
        show_main_help()
