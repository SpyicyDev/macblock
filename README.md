# macblock

Local DNS sinkhole for macOS using `dnsmasq` (on `127.0.0.1:5353`) plus PF redirection of outbound DNS (`:53`) to the local resolver.

This project intentionally does **not** set system DNS servers to `127.0.0.1`. It follows system resolver selection (including split DNS from VPNs) by periodically translating macOS resolver state into `dnsmasq` `server=` rules.

## Status

This repo is scaffolded and implements:
- `sudo macblock install` installs PF + launchd + root-owned state/config locations.
- `sudo macblock enable|disable|pause|resume` toggles PF interception and pause scheduling.
- `sudo macblock update` downloads and compiles a hosts-format blocklist.
- `sudo macblock allow|deny` manages whitelist/blacklist and recompiles.

## Install (dev)

```bash
uv sync --dev
uv run macblock status
```

## Install (planned Homebrew)

This repo includes a tap scaffold under `../homebrew-macblock` in this workspace.

Typical flow will be:

```bash
brew tap <org>/macblock
brew install macblock
sudo macblock install
sudo macblock update
sudo macblock enable
```

## Commands

- `macblock status`
- `macblock doctor`
- `sudo macblock install [--force]`
- `sudo macblock uninstall [--force]`
- `sudo macblock enable|disable`
- `sudo macblock pause 10m|2h|1d`
- `sudo macblock resume`
- `sudo macblock update [--source stevenblack|https://…]`
- `sudo macblock allow add|remove|list <domain>`
- `sudo macblock deny add|remove|list <domain>`

## Uninstall

```bash
sudo macblock uninstall
```

If you installed via Homebrew:

```bash
brew uninstall macblock dnsmasq
```

## Notes

- PF conflicts: other DNS tools that install PF redirection rules may conflict. `macblock` should refuse or require manual resolution.
- Encrypted DNS (DoH/DoT): PF interception does not affect encrypted DNS.

See `SECURITY.md` for threat model and design constraints.
