# app/mailer.py
import os, smtplib, mimetypes
from email.message import EmailMessage
from pathlib import Path

def send_digest(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass_env: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    body_text: str,
    attachments: list[Path]
) -> str:
    pwd = os.environ.get(smtp_pass_env, "")
    if not pwd:
        raise RuntimeError(f"SMTP password env var '{smtp_pass_env}' is empty")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.set_content(body_text)

    for p in attachments:
        if not p.exists():
            continue
        ctype, _ = mimetypes.guess_type(str(p))
        maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
        with p.open("rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=p.name)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
        s.starttls()
        s.login(smtp_user, pwd)
        s.send_message(msg)
    return "OK"
