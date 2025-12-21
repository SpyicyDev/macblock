# Security

## Threat model

This project intercepts DNS on the local machine and makes privileged changes (PF and launchd). The primary risks are:
- Root persistence (launchd jobs).
- Privilege escalation if a root job executes user-writable code.
- DNS hijack persistence if uninstall/rollback is incomplete.
- Privacy leakage if query logging is enabled.

## Design constraints

- Root-owned jobs must not execute user-writable scripts or binaries.
- `dnsmasq` is run on a non-privileged loopback port (`5300`) and can run as an unprivileged dedicated user.
- PF is the interception mechanism; system DNS servers are not rewritten.

## Privileged footprint

`sudo macblock install` writes to:
- `/etc/pf.conf` and `/etc/pf.anchors/…`
- `/Library/LaunchDaemons/…`
- `/Library/Application Support/macblock/…`
- `/var/db/macblock/…`

`sudo macblock uninstall` removes the above.

## Reporting

If you find a security issue, open an issue with a minimal reproduction and the affected OS version.
