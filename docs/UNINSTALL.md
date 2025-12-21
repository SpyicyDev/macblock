# Uninstall

## 1) Remove system integration (do this first)

This removes PF rules, LaunchDaemons, and state/config under `/Library` and `/var/db`.

```bash
sudo macblock uninstall
```

If `macblock` reports leftovers, try:

```bash
sudo macblock uninstall --force
```

## 2) Remove the Homebrew package

Once the system integration is clean, remove the Homebrew package:

```bash
brew uninstall macblock dnsmasq
```

## Homebrew permission errors

If Homebrew fails with a message like "Could not remove ... .reinstall", follow the printed path.

Typically it is root-owned due to a previous root run. Fix it by either removing it:

```bash
sudo rm -rf <path>
```

Or restoring ownership so Homebrew can remove it:

```bash
sudo chown -R $(whoami):admin <path>
```

## What is removed by `sudo macblock uninstall`

- PF anchor rules and the `pf.conf` include block.
- `launchd` jobs created by `macblock`.
- State/config directories under `/Library/Application Support/macblock`.
- Dynamic upstream state under `/var/db/macblock`.
