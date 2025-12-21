# Security

## Threat model

This project intercepts DNS on the local machine and makes privileged changes (launchd + system DNS configuration). The primary risks are:
- Root persistence (LaunchDaemons).
- Privilege escalation if a privileged job executes user-writable code or writes into user-writable directories.
- DNS hijack persistence if uninstall/rollback is incomplete.
- Privacy leakage if query logging is enabled.

## Design constraints

- Root-owned jobs must not execute user-writable scripts or binaries.
- `dnsmasq` listens on loopback `127.0.0.1:53` and drops privileges to a dedicated user.
- Interception is performed by setting per-network-service DNS servers to `127.0.0.1` via `networksetup`.

## Privileged footprint

`sudo macblock install` writes to:
- `/Library/LaunchDaemons/…`
- `/Library/Application Support/macblock/…`
- `/Library/Logs/macblock/…`
- `/var/db/macblock/…`

`sudo macblock uninstall` removes the above.

## Reporting

If you find a security issue, open an issue with a minimal reproduction and the affected OS version.
