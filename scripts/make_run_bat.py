# scripts/make_run_bat.py
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
venv_py = ROOT / ".venv" / "Scripts" / "python.exe"

def mk_bat(name: str, env: dict):
    lines = ["@echo off"]
    lines.append(f'cd /d "{ROOT}"')
    # Set env inline for this process only
    for k, v in env.items():
        lines.append(f'set "{k}={v}"')
    lines.append(f'"{venv_py}" "{(ROOT / "main.py")}"')
    bat = ROOT / f"{name}.bat"
    bat.write_text("\n".join(lines), encoding="utf-8")
    return bat

reset_bat = mk_bat("run_reset_seen", {
    "PYTHONPATH": str(ROOT),
    "BIONEWS_OUTPUTS": "csv,json,html",
    "BIONEWS_WINDOW_DAYS": "7",
    "BIONEWS_ONLY_NEW": "0",
    "BIONEWS_RESET_SEEN": "1"
})

daily_bat = mk_bat("run_daily_onlynew", {
    "PYTHONPATH": str(ROOT),
    "BIONEWS_OUTPUTS": "csv,json,html",
    "BIONEWS_WINDOW_DAYS": "7",
    "BIONEWS_ONLY_NEW": "1"
})

print(f"Created:\n - {reset_bat}\n - {daily_bat}")
