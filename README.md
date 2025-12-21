# macblock

Local DNS sinkhole for macOS using `dnsmasq` (on `127.0.0.1:53`) plus per-network-service DNS rewriting to `127.0.0.1` via `networksetup`.

`macblock` maintains a local `dnsmasq` instance and dynamically generates `dnsmasq` upstream `server=` rules (including split-DNS) from macOS resolver state.

## Status

This repo implements:
- `sudo macblock install` installs `launchd` jobs plus root-owned state/config locations.
- `sudo macblock enable|disable|pause|resume` toggles system DNS to localhost and schedules pause/resume.
- `sudo macblock update` downloads and compiles a hosts-format blocklist.
- `sudo macblock allow|deny` manages whitelist/blacklist and recompiles.
- `macblock logs` tails daemon logs for visibility.

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

## Important notes

- Do not run `sudo brew`. Homebrew expects to manage files as your user.
- `sudo macblock ...` installs and manages system integration under `/Library`, `/etc`, and `/var/db`. Homebrew uninstall does not remove those.
- If Homebrew fails with a message like "Could not remove ... .reinstall", that directory is usually root-owned due to a previous root run. Fix it by following Homebrew's printed path (either `sudo rm -rf <path>` or `sudo chown -R $(whoami):admin <path>`).

## Commands

- `macblock status`
- `macblock doctor`
- `macblock logs [--component daemon|dnsmasq] [--follow]`
- `sudo macblock install [--force]`
- `sudo macblock uninstall [--force]`
- `sudo macblock enable|disable`
- `sudo macblock pause 10m|2h|1d`
- `sudo macblock resume`
- `sudo macblock update [--source stevenblack|https://…]`
- `sudo macblock allow add|remove|list <domain>`
- `sudo macblock deny add|remove|list <domain>`

## Uninstall

Remove system integration first:

```bash
sudo macblock uninstall
```

Then remove the Homebrew package:

```bash
brew uninstall macblock dnsmasq
```

If you run `brew uninstall` first, `macblock` may no longer be available to remove the system integration components.

## Notes

- Encrypted DNS (DoH/DoT): can bypass system DNS settings entirely.
- VPNs: may install scoped resolvers; if you see odd behavior, check `macblock doctor` and `macblock logs`.

See `SECURITY.md` for threat model and design constraints.
