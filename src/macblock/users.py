from __future__ import annotations

import re

from macblock.exec import run
from macblock.errors import MacblockError


def _dscl(args: list[str]) -> str:
    r = run(["/usr/bin/dscl", ".", *args])
    if r.returncode != 0:
        raise MacblockError(r.stderr.strip() or "dscl failed")
    return r.stdout


def user_exists(name: str) -> bool:
    r = run(["/usr/bin/dscl", ".", "-read", f"/Users/{name}"])
    return r.returncode == 0


def group_exists(name: str) -> bool:
    r = run(["/usr/bin/dscl", ".", "-read", f"/Groups/{name}"])
    return r.returncode == 0


def _list_ids(kind: str) -> set[int]:
    out = _dscl(
        ["-list", f"/{kind}", "UniqueID" if kind == "Users" else "PrimaryGroupID"]
    )
    ids: set[int] = set()
    for line in out.splitlines():
        parts = re.split(r"\s+", line.strip())
        if len(parts) != 2:
            continue
        try:
            ids.add(int(parts[1]))
        except Exception:
            continue
    return ids


def _allocate_id() -> int:
    used = _list_ids("Users") | _list_ids("Groups")
    for i in range(260, 500):
        if i not in used:
            return i
    raise MacblockError("No free UID/GID available")


def ensure_system_user(name: str) -> None:
    if user_exists(name):
        return

    gid = _allocate_id()

    if not group_exists(name):
        _dscl(["-create", f"/Groups/{name}"])
        _dscl(["-create", f"/Groups/{name}", "PrimaryGroupID", str(gid)])
        _dscl(["-create", f"/Groups/{name}", "RealName", "macblock group"])

    uid = gid

    _dscl(["-create", f"/Users/{name}"])
    _dscl(["-create", f"/Users/{name}", "UserShell", "/usr/bin/false"])
    _dscl(["-create", f"/Users/{name}", "RealName", "macblock user"])
    _dscl(["-create", f"/Users/{name}", "UniqueID", str(uid)])
    _dscl(["-create", f"/Users/{name}", "PrimaryGroupID", str(gid)])
    _dscl(["-create", f"/Users/{name}", "NFSHomeDirectory", "/var/empty"])


def delete_system_user(name: str) -> None:
    if user_exists(name):
        _dscl(["-delete", f"/Users/{name}"])
    if group_exists(name):
        _dscl(["-delete", f"/Groups/{name}"])
