# Security

## Threat model

This project intercepts DNS on the local machine and makes privileged changes (launchd + system DNS configuration).

**Assumption:** macblock targets a **single-user admin machine** where the local admin user is trusted.

Primary risks:
- Root persistence (LaunchDaemons).
- DNS hijack persistence if uninstall/rollback is incomplete.
- Privacy leakage if query logging is enabled.
- On multi-user systems: privilege escalation risk if a privileged job executes code from locations writable by other users.

## Design constraints

- `dnsmasq` listens on loopback `127.0.0.1:53` and drops privileges to a dedicated user.
- Interception is performed by setting per-network-service DNS servers to `127.0.0.1` via `networksetup`.
- LaunchDaemons are configured to execute the `macblock` and `dnsmasq` binaries as installed on the machine (commonly via Homebrew). On a single-user admin machine this is acceptable; for multi-user hardening you would instead install/copy executables into a root-owned location and ensure they are not writable by non-admin users.

## Privileged footprint

`sudo macblock install` writes to:
- `/Library/LaunchDaemons/…`
- `/Library/Application Support/macblock/…`
- `/Library/Logs/macblock/…`
- `/var/db/macblock/…`

`sudo macblock uninstall` removes the above.

Note on directory permissions: `/Library/Application Support/macblock` and `/Library/Logs/macblock` are created with mode `0o755` so non-root diagnostics (e.g. `macblock status`, `macblock doctor`, log viewing) can work without `sudo`. On multi-user systems, consider tightening permissions to your desired privacy model.

## Reporting

For sensitive reports, please use GitHub Security Advisories.

For non-sensitive issues (or if you're unsure), open an issue with a minimal reproduction and the affected OS version.
