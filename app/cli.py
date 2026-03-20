# cli.py
import argparse, os, sys
from pathlib import Path

# Run the normal main()
from main import main as run_main

# Minimal validators
from app.config import load_settings, load_feeds
from app.validate import validate_settings, validate_feeds

def cmd_run(args):
    # Allow quick overrides without editing settings.json
    if args.days is not None:
        os.environ["BIONEWS_WINDOW_DAYS"] = str(args.days)
    if args.only_new is not None:
        os.environ["BIONEWS_ONLY_NEW"] = "1" if args.only_new else "0"
    if args.outputs:
        os.environ["BIONEWS_OUTPUTS"] = ",".join(args.outputs)

    # Validate settings & feeds before running
    s = load_settings("settings.json")
    ferrs = validate_settings(s)
    if ferrs:
        print("Config errors:")
        for e in ferrs: print(" -", e)
        sys.exit(2)
    feeds = load_feeds("feeds.json")
    errs = validate_feeds(feeds)
    if errs:
        print("Feed errors:")
        for e in errs: print(" -", e)
        sys.exit(2)

    # Merge watchlist feeds if present and validate quickly
    try:
        extra = load_feeds("feeds_watchlist.json")
        _ = validate_feeds(extra)
    except FileNotFoundError:
        pass

    run_main()
    return 0

def cmd_mail(args):
    from app.mailer import send_digest
    from app.config import load_settings
    s = load_settings("settings.json")
    e = s.get("email") or {}
    if not e or not e.get("enabled", False):
        print("Email disabled in settings.json (email.enabled=false)."); return 1

    out_dir = Path(s.get("out_dir","out"))
    html = out_dir / "news.html"
    csv  = out_dir / "news.csv"
    json = out_dir / "news.json"

    res = send_digest(
        smtp_host=e["smtp_host"],
        smtp_port=int(e["smtp_port"]),
        smtp_user=e["smtp_user"],
        smtp_pass_env=e["smtp_pass_env"],
        from_addr=e["from"],
        to_addrs=e["to"],
        subject=e.get("subject", "BioNews"),
        body_text=e.get("body", "BioNews report attached."),
        attachments=[p for p in [html, csv, json] if p.exists()]
    )
    print("Email:", res)
    return 0

def main():
    ap = argparse.ArgumentParser(prog="bionews", description="BioNews CLI")
    sub = ap.add_subparsers(dest="cmd")

    runp = sub.add_parser("run", help="Run aggregator")
    runp.add_argument("--days", type=int, help="window days override")
    runp.add_argument("--only-new", action=argparse.BooleanOptionalAction, help="only unseen items")
    runp.add_argument("--outputs", nargs="*", choices=["csv","json","html"], help="outputs to write")
    runp.set_defaults(func=cmd_run)

    mailp = sub.add_parser("mail", help="Email the latest report")
    mailp.set_defaults(func=cmd_mail)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help(); return 1
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
