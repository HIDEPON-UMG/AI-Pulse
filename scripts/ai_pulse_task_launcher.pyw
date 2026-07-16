from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPTS = {
    "auth": "refresh_notebooklm_auth.ps1",
    "daily": "run_daily.ps1",
    "weekly": "run_weekly.ps1",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(SCRIPTS))
    parser.add_argument("--probe", type=Path)
    args = parser.parse_args()
    if args.probe:
        args.probe.parent.mkdir(parents=True, exist_ok=True)
        args.probe.write_text("probe_ok", encoding="utf-8")
        return 0
    script = Path(__file__).resolve().parent / SCRIPTS[args.mode]
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if not script.is_file() or not powershell.is_file():
        return 66
    log = Path(__file__).resolve().parents[1] / "_logs" / "task-launcher.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with log.open("a", encoding="utf-8", errors="replace") as stream:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            check=False,
        )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
