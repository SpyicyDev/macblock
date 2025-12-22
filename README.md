# macblock

Local DNS sinkhole for macOS using `dnsmasq` on `127.0.0.1:53` with automatic system DNS configuration.

## Features

- Blocks ads, trackers, and malware at the DNS level
- Automatic DNS configuration for all network interfaces
- Split-DNS support (preserves VPN/corporate DNS routing)
- Pause/resume with automatic timers
- Whitelist and blacklist management
- Multiple blocklist sources (StevenBlack, HaGeZi, OISD)

## Install

### Via Homebrew (recommended)

```bash
brew tap SpyicyDev/macblock
brew install macblock
sudo macblock install
sudo macblock update
sudo macblock enable
```

### From source

```bash
git clone https://github.com/SpyicyDev/macblock.git
cd macblock
uv sync --dev
uv run macblock --version
```

### Development

Recommended tooling:

```bash
brew install just direnv
```

Then:

```bash
# auto-sync deps when uv.lock/pyproject.toml change

direnv allow

# install pre-commit hooks
just setup

# run the full local CI suite
just ci
```

## Commands

| Command | Description |
|---------|-------------|
| `macblock status` | Show current status |
| `macblock doctor` | Run diagnostics |
| `macblock logs [--follow]` | View daemon logs |
| `sudo macblock install [--force]` | Install system integration |
| `sudo macblock uninstall` | Remove system integration |
| `sudo macblock enable` | Enable blocking |
| `sudo macblock disable` | Disable blocking |
| `sudo macblock pause 10m\|2h\|1d` | Temporarily disable |
| `sudo macblock resume` | Resume blocking |
| `sudo macblock update [--source X]` | Update blocklist |
| `sudo macblock sources list` | List available blocklist sources |
| `sudo macblock sources set <source>` | Set blocklist source |
| `sudo macblock allow add\|remove\|list <domain>` | Manage whitelist |
| `sudo macblock deny add\|remove\|list <domain>` | Manage blacklist |
| `macblock test <domain>` | Test if domain is blocked |

## How it works

1. **dnsmasq** runs on `127.0.0.1:53` and handles all DNS queries
2. **macblock daemon** monitors network changes and manages DNS settings
3. When enabled, system DNS is set to `127.0.0.1` for all managed interfaces
4. Blocked domains return `NXDOMAIN`; allowed queries forward to upstream DNS

## Blocklist sources

| Source | Description |
|--------|-------------|
| `stevenblack` | StevenBlack Unified (default) |
| `stevenblack-fakenews` | StevenBlack + Fakenews |
| `stevenblack-gambling` | StevenBlack + Gambling |
| `hagezi-pro` | HaGeZi Pro |
| `hagezi-ultimate` | HaGeZi Ultimate |
| `oisd-small` | OISD Small |
| `oisd-big` | OISD Big |

Or use a custom URL: `sudo macblock update --source https://example.com/hosts.txt`

## Uninstall

```bash
sudo macblock uninstall
brew uninstall macblock dnsmasq
```

## Troubleshooting

Run `macblock doctor` to diagnose issues:

```bash
macblock doctor
```

Common issues:
- **dnsmasq not running**: Check `macblock logs --component dnsmasq`
- **DNS not redirected**: Verify with `scutil --dns`
- **Blocklist empty**: Run `sudo macblock update`

## Security

See [SECURITY.md](SECURITY.md) for the threat model and design constraints.

## License

MIT
