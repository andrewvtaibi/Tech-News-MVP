# scripts/setup_deps.py
# Pins deps, installs them into .venv, verifies versions, and writes a lock file.
import sys, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PY   = VENV / "Scripts" / "python.exe"
REQ  = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock.txt"

# 1) Sanity checks
if not PY.exists():
    print("ERROR: .venv/python not found. Run bootstrap.py first to create the venv.")
    raise SystemExit(2)
if sys.version_info[:2] != (3, 11):
    print(f"WARNING: Running with Python {sys.version.split()[0]}. VS Code should target the .venv Python 3.11.")

# 2) Write pinned requirements (minimal maintenance = few deps, pinned)
REQ.write_text("feedparser==6.0.11\n", encoding="utf-8")
print(f"Wrote {REQ}")

# 3) Install (upgrade core tooling first for smoother installs)
def run(args):
    print(">", " ".join(map(str, args)))
    subprocess.run(args, check=True)

run([str(PY), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
run([str(PY), "-m", "pip", "install", "-r", str(REQ)])

# 4) Verify exact versions
out = subprocess.check_output([str(PY), "-c", "import feedparser; print(feedparser.__version__)"], text=True).strip()
print("feedparser version:", out)
if out != "6.0.11":
    print("ERROR: feedparser version mismatch; reinstalling pinned version…")
    run([str(PY), "-m", "pip", "install", "--force-reinstall", "feedparser==6.0.11"])
    out = subprocess.check_output([str(PY), "-c", "import feedparser; print(feedparser.__version__)"], text=True).strip()
    if out != "6.0.11":
        print("ERROR: Could not enforce feedparser==6.0.11.")
        raise SystemExit(3)

# 5) Write a lock file for reproducibility
frozen = subprocess.check_output([str(PY), "-m", "pip", "freeze", "--local"], text=True)
LOCK.write_text(frozen, encoding="utf-8")
print(f"Wrote {LOCK}\nDone.")