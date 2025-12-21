from __future__ import annotations

import time

from macblock.colors import print_success
from macblock.constants import APP_LABEL, LAUNCHD_PF_PLIST, SYSTEM_STATE_FILE
from macblock.launchd import bootstrap_system, enable_service, kickstart
from macblock.pf import disable_anchor, enable_anchor
from macblock.state import State, load_state, save_state_atomic


def _parse_duration_seconds(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("m"):
        return int(value[:-1]) * 60
    if value.endswith("h"):
        return int(value[:-1]) * 60 * 60
    if value.endswith("d"):
        return int(value[:-1]) * 60 * 60 * 24
    raise ValueError("duration must end with m/h/d")


def _ensure_pf_daemon() -> None:
    try:
        bootstrap_system(LAUNCHD_PF_PLIST)
    except Exception:
        pass

    try:
        enable_service(f"{APP_LABEL}.pf")
    except Exception:
        pass

    try:
        kickstart(f"{APP_LABEL}.pf")
    except Exception:
        pass


def do_enable() -> int:
    _ensure_pf_daemon()
    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        State(schema_version=st.schema_version, enabled=True, resume_at_epoch=None, blocklist_source=st.blocklist_source),
    )
    enable_anchor()
    print_success("enabled")
    return 0


def do_disable() -> int:
    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        State(schema_version=st.schema_version, enabled=False, resume_at_epoch=None, blocklist_source=st.blocklist_source),
    )
    disable_anchor()
    print_success("disabled")
    return 0


def do_pause(duration: str) -> int:
    _ensure_pf_daemon()
    seconds = _parse_duration_seconds(duration)
    resume_at = int(time.time()) + seconds
    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        State(schema_version=st.schema_version, enabled=True, resume_at_epoch=resume_at, blocklist_source=st.blocklist_source),
    )
    disable_anchor()
    print_success("paused")
    return 0


def do_resume() -> int:
    _ensure_pf_daemon()
    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        State(schema_version=st.schema_version, enabled=True, resume_at_epoch=None, blocklist_source=st.blocklist_source),
    )
    enable_anchor()
    print_success("resumed")
    return 0
