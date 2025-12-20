#!/usr/bin/python3

import json
import subprocess
import time
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    pfctl = "/sbin/pfctl"

    state_path = Path("{{SYSTEM_STATE_FILE}}")
    anchor_name = "{{APP_LABEL}}"
    anchor_file = "{{PF_ANCHOR_FILE}}"

    enabled = False
    resume_at = None
    blocklist_source = None

    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        enabled = bool(data.get("enabled") or False)
        resume_at = data.get("resume_at_epoch")
        blocklist_source = data.get("blocklist_source")
    else:
        data = {"schema_version": 1}

    now = int(time.time())

    should_enable = enabled
    should_load_anchor = enabled

    if resume_at is not None:
        try:
            resume_at_int = int(resume_at)
        except Exception:
            resume_at_int = now

        if resume_at_int > now:
            should_load_anchor = False
        else:
            data["resume_at_epoch"] = None

    r1 = run([pfctl, "-E"])
    if r1.returncode not in (0, 1):
        return 0

    r2 = run([pfctl, "-f", "/etc/pf.conf"])
    if r2.returncode != 0:
        return 0

    if should_enable and should_load_anchor:
        run([pfctl, "-a", anchor_name, "-f", anchor_file])
    else:
        run([pfctl, "-a", anchor_name, "-F", "all"])

    data["enabled"] = bool(should_enable)
    data["blocklist_source"] = blocklist_source

    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(state_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
