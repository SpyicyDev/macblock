# Uninstall

## Standard

```bash
sudo macblock uninstall
```

## Force cleanup

```bash
sudo macblock uninstall --force
```

`--force` attempts best-effort removal even if a launchd job cannot be unloaded.

## Remove Homebrew package

```bash
brew uninstall macblock dnsmasq
```

## What is removed

- PF anchor rules and the `pf.conf` include block.
- `launchd` jobs created by `macblock`.
- State/config directories under `/Library/Application Support/macblock`.
- Dynamic upstream state under `/var/db/macblock`.
