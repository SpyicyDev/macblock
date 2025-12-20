from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class State:
    schema_version: int
    enabled: bool
    resume_at_epoch: int | None
    blocklist_source: str | None


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
        return State(schema_version=1, enabled=False, resume_at_epoch=None, blocklist_source=None)

    data = json.loads(path.read_text(encoding="utf-8"))

    enabled_raw = data.get("enabled")
    enabled = bool(enabled_raw) if enabled_raw is not None else False

    raw_epoch = data.get("resume_at_epoch")
    if raw_epoch is None:
        raw_iso = data.get("resume_at")
        resume_at_epoch = _iso_to_epoch_seconds(raw_iso) if isinstance(raw_iso, str) else None
    else:
        try:
            resume_at_epoch = int(raw_epoch) if raw_epoch is not None else None
        except Exception:
            resume_at_epoch = None

    src = data.get("blocklist_source")

    return State(
        schema_version=int(data.get("schema_version", 1)),
        enabled=enabled,
        resume_at_epoch=resume_at_epoch,
        blocklist_source=str(src) if src is not None else None,
    )


def save_state_atomic(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "schema_version": state.schema_version,
        "enabled": state.enabled,
        "resume_at_epoch": state.resume_at_epoch,
        "blocklist_source": state.blocklist_source,
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
