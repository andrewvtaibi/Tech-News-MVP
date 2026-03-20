# bootstrap.py — creates .venv with pip, sets VS Code to use it, and writes a test script.
import sys, os, json, pathlib, venv

ROOT = pathlib.Path(__file__).parent.resolve()
VENV = ROOT / ".venv"
VS   = ROOT / ".vscode"
SET  = VS / "settings.json"

# 1) Require Python 3.11.x to ensure reproducibility/minimal maintenance
if sys.version_info[:2] != (3, 11):
    print(f"ERROR: Need Python 3.11.x; found {sys.version}. Install Python 3.11 and re-run.")
    raise SystemExit(2)

# 2) Create virtual environment if missing
if not VENV.exists():
    print(f"Creating venv at: {VENV}")
    venv.EnvBuilder(with_pip=True).create(str(VENV))
else:
    print(".venv already exists — skipping create")

# 3) Point VS Code at this interpreter (avoids relying on the status bar)
VS.mkdir(exist_ok=True)
settings_data = {
    "python.defaultInterpreterPath": str((VENV / "Scripts" / "python.exe")),
    "python.terminal.activateEnvironment": True
}
existing = {}
if SET.exists():
    try:
        existing = json.loads(SET.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
existing.update(settings_data)
SET.write_text(json.dumps(existing, indent=2), encoding="utf-8")

# 4) Create a verification script
SCRIPTS = ROOT / "scripts"
SCRIPTS.mkdir(parents=True, exist_ok=True)
(SCRIPTS / "test_env.py").write_text(
    "import sys, platform, ssl\n"
    "print('OK: Python:', sys.version)\n"
    "print('OK: Executable:', sys.executable)\n"
    "print('OK: Platform:', platform.platform())\n"
    "print('OK: SSL:', ssl.OPENSSL_VERSION)\n",
    encoding="utf-8"
)

print("\nBootstrap complete.")
print("Set interpreter to:", settings_data["python.defaultInterpreterPath"])
print("Next: Open scripts/test_env.py and run it (Ctrl+F5).")
