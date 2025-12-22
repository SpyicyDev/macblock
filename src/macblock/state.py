from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Schema version for state.json - increment when making breaking changes.
# Both CLI (state.py) and daemon (macblockd.py.tmpl) must agree on this.
CURRENT_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class State:
    schema_version: int
    enabled: bool
    resume_at_epoch: int | None
    blocklist_source: str | None
    dns_backup: dict[str, dict[str, list[str] | None]]
    managed_services: list[str]
    resolver_domains: list[str]


def _iso_to_epoch_seconds(value: str) -> int | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def load_state(path: Path) -> State:
    if not path.exists():
        return State(
            schema_version=2,
            enabled=False,
            resume_at_epoch=None,
            blocklist_source=None,
            dns_backup={},
            managed_services=[],
            resolver_domains=[],
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    enabled_raw = data.get("enabled")
    enabled = bool(enabled_raw) if enabled_raw is not None else False

    raw_epoch = data.get("resume_at_epoch")
    if raw_epoch is None:
        raw_iso = data.get("resume_at")
        resume_at_epoch = (
            _iso_to_epoch_seconds(raw_iso) if isinstance(raw_iso, str) else None
        )
    else:
        try:
            resume_at_epoch = int(raw_epoch) if raw_epoch is not None else None
        except Exception:
            resume_at_epoch = None

    src = data.get("blocklist_source")

    dns_backup_raw = data.get("dns_backup")
    dns_backup: dict[str, dict[str, list[str] | None]] = {}
    if isinstance(dns_backup_raw, dict):
        for service, cfg in dns_backup_raw.items():
            if not isinstance(service, str) or not isinstance(cfg, dict):
                continue
            dns_val = cfg.get("dns")
            search_val = cfg.get("search")
            dhcp_val = cfg.get("dhcp")
            dns_backup[service] = {
                "dns": list(dns_val) if isinstance(dns_val, list) else None,
                "search": list(search_val) if isinstance(search_val, list) else None,
                "dhcp": list(dhcp_val) if isinstance(dhcp_val, list) else None,
            }

    managed_services_raw = data.get("managed_services")
    managed_services: list[str] = []
    if isinstance(managed_services_raw, list):
        for s in managed_services_raw:
            if isinstance(s, str) and s:
                managed_services.append(s)

    resolver_domains_raw = data.get("resolver_domains")
    resolver_domains: list[str] = []
    if isinstance(resolver_domains_raw, list):
        for d in resolver_domains_raw:
            if isinstance(d, str) and d:
                resolver_domains.append(d)

    schema_version = int(data.get("schema_version", CURRENT_SCHEMA_VERSION))
    if schema_version != CURRENT_SCHEMA_VERSION:
        print(
            f"warning: state.json schema_version={schema_version}, expected {CURRENT_SCHEMA_VERSION}",
            file=sys.stderr,
        )

    return State(
        schema_version=schema_version,
        enabled=enabled,
        resume_at_epoch=resume_at_epoch,
        blocklist_source=str(src) if src is not None else None,
        dns_backup=dns_backup,
        managed_services=managed_services,
        resolver_domains=resolver_domains,
    )


def replace_state(st: State, **updates: Any) -> State:
    payload: dict[str, Any] = {
        "schema_version": st.schema_version,
        "enabled": st.enabled,
        "resume_at_epoch": st.resume_at_epoch,
        "blocklist_source": st.blocklist_source,
        "dns_backup": st.dns_backup,
        "managed_services": st.managed_services,
        "resolver_domains": [],
    }
    payload.update(updates)
    return State(**payload)


def save_state_atomic(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "schema_version": state.schema_version,
        "enabled": state.enabled,
        "resume_at_epoch": state.resume_at_epoch,
        "blocklist_source": state.blocklist_source,
        "dns_backup": state.dns_backup,
        "managed_services": state.managed_services,
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
