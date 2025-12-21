# Uninstall

## 1) Remove system integration (do this first)

This removes LaunchDaemons, system DNS changes, and state/config under `/Library` and `/var/db`.

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

- `launchd` jobs created by `macblock`.
- State/config directories under `/Library/Application Support/macblock`.
- Logs under `/Library/Logs/macblock`.
- Dynamic state under `/var/db/macblock`.
- If you upgraded from older versions: `sudo macblock uninstall` also removes any `/etc/resolver/*` files that were previously created by `macblock`.
