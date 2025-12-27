# Changelog

## [0.2.4](https://github.com/SpyicyDev/macblock/releases/tag/v0.2.4) - 2025-12-27

### Miscellaneous

- Undid justfile change

- chore(logging): unify dnsmasq logs under /Library/Logs

## [0.2.3](https://github.com/SpyicyDev/macblock/releases/tag/v0.2.3) - 2025-12-26

### Bug Fixes

- fix(daemon): wait for default route before applying DNS


### Miscellaneous

- Elaborated in README

## [0.2.2](https://github.com/SpyicyDev/macblock/releases/tag/v0.2.2) - 2025-12-25

### Bug Fixes

- fix: stage release artifacts before commit

- fix: make GitHub issue forms and PR template discoverable


### Documentation

- docs: update Homebrew tap references

- docs: add vibe-coding disclaimer


### Miscellaneous

- chore: improve repo readiness

- ci: publish releases to PyPI

- chore: prep PyPI metadata and docs

- chore: remove pre-commit tooling

- chore: remove legacy issue template markdown files

- Potential fix for code scanning alert no. 1: Workflow does not contain permissions

## [0.2.1](https://github.com/SpyicyDev/macblock/releases/tag/v0.2.1) - 2025-12-24

### Bug Fixes

- fix: make macblock test blocklist-aware


### Documentation

- docs: polish README and add GitHub templates


### Miscellaneous

- Revert Rich status/doctor output

- Overhaul status/doctor output with Rich tables

## [0.2.0](https://github.com/SpyicyDev/macblock/releases/tag/v0.2.0) - 2025-12-23

### Bug Fixes

- Fix release tooling and changelog generation

- Fix ruff E402 lint and just run workflows

- Fix daemon signal handling with interruptible wait loop

- Fix install and enable flows with proper verification and error handling

- Fix PF DNS redirect bypass and avoid dnsmasq TCP loops

- Fix PF anchor rules on macOS

- Fix pf.conf rdr-anchor insertion ordering


### Features

- Add comprehensive per-command help system and fix logs command

- Add automated Homebrew formula updates on release

- Add macblockd.py binary existence check to doctor

- Add schema version validation to state handling

- Add logs subcommand for daemon visibility

- Add subprocess timeouts to prevent CLI hangs

- Add macblockd daemon templates


### Miscellaneous

- chore: run pre-commit during release

- Modernize DX and automate Homebrew release updates

- Overhaul CLI UX with spinners, emoji headers, and custom help

- Use SIGUSR1 signal to trigger daemon instead of launchctl kickstart

- Improve macblock test output with result interpretation

- Remove PF references and deprecate resolver_domains field

- Harden macblockd upstream parsing and clean legacy services

- Align docs and templates with non-PF macblockd design

- Replace polling jobs with macblockd daemon

- Route enable/disable through macblockd reconcile

- Install macblockd LaunchDaemon alongside existing jobs

- Separate dnsmasq runtime files from root-owned state

- Ensure upstream.conf always has fallback servers

- Persist DHCP DNS servers for upstream fallback

- Auto-elevate root commands via sudo

- Use saved DNS backup for upstream fallback

- Replace PF interception with localhost DNS

- Make update verbose and compile NXDOMAIN blocklist

- Restart dnsmasq after blocklist updates

- Load upstreams via servers-file and start pf job

- Load PF rdr ruleset and surface pfctl errors

- Remove dnsmasq query-port to avoid startup refusals

- Improve dnsmasq health checks and status

- Avoid mDNS port conflict and prevent PF DNS loops

- Initial macblock PF-based DNS sinkhole


### Refactoring

- Refactor architecture: daemon runs from installed package

