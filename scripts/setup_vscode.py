# scripts/setup_vscode.py
from __future__ import annotations
import json
from pathlib import Path

LAUNCH = {
    "version": "0.2.0",
    "configurations": [
        {
            "name": "BioNews: Reset seen (Terminal, known-good)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal",
            "env": {
                "BIONEWS_OUTPUTS": "csv,json,html",
                "BIONEWS_WINDOW_DAYS": "7",
                "BIONEWS_ONLY_NEW": "0",
                "BIONEWS_RESET_SEEN": "1"
            }
        },
        {
            "name": "BioNews: 7 days (only-new) (Terminal)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal",
            "env": {
                "BIONEWS_OUTPUTS": "csv,json,html",
                "BIONEWS_WINDOW_DAYS": "7",
                "BIONEWS_ONLY_NEW": "1",
                "BIONEWS_RESET_SEEN": "0"
            }
        },
        {
            "name": "BioNews: Today (CSV+JSON) (Terminal)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal",
            "env": {
                "BIONEWS_OUTPUTS": "csv,json",
                "BIONEWS_WINDOW_DAYS": "1",
                "BIONEWS_ONLY_NEW": "0",
                "BIONEWS_RESET_SEEN": "0"
            }
        }
    ]
}

def main():
    root = Path(__file__).resolve().parents[1]
    vscode = root / ".vscode"
    vscode.mkdir(parents=True, exist_ok=True)
    launch = vscode / "launch.json"
    launch.write_text(json.dumps(LAUNCH, indent=2), encoding="utf-8")
    print("Wrote .vscode/launch.json with internal + terminal presets (debugpy).")

if __name__ == "__main__":
    main()
