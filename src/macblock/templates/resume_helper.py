#!/usr/bin/python3

import json
import subprocess
import time
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    state_path = Path("{{SYSTEM_STATE_FILE}}")

    if not state_path.exists():
        return 0

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    resume_at = data.get("resume_at_epoch")
    if resume_at is None:
        return 0

    try:
        resume_at_int = int(resume_at)
    except Exception:
        return 0

    now = int(time.time())
    if resume_at_int > now:
        return 0

    pfctl = "/sbin/pfctl"
    anchor_name = "{{APP_LABEL}}"
    anchor_file = "{{PF_ANCHOR_FILE}}"

    r1 = run([pfctl, "-E"])
    if r1.returncode not in (0, 1):
        return 0

    run([pfctl, "-f", "/etc/pf.conf"])
    run([pfctl, "-a", anchor_name, "-f", anchor_file])

    data["resume_at_epoch"] = None

    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(state_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
