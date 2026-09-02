#!/usr/bin/env python3
"""Send the rendered newsletter over Gmail SMTP.

A GitHub Actions runner has no Gmail connector, so the send happens directly
over SMTP with an app password. Credentials come from the environment and are
never written to disk or echoed.

    GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx \\
    python3 scripts/send_email.py \\
        --html /tmp/edition.html \\
        --subject "The Morning · ..." \\
        --text-file /tmp/edition.txt \\
        --to ch22b007@smail.iitm.ac.in
"""
import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def build(args, html, text):
    msg = EmailMessage()
    msg["Subject"] = args.subject
    msg["From"] = formataddr((args.from_name, args.user))
    msg["To"] = ", ".join(args.to)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="the-morning.local")
    # A newsletter that lands in the inbox should still be easy to stop.
    msg["List-Id"] = "The Morning <the-morning.newsletter>"

    msg.set_content(text or "This edition is best viewed with HTML enabled.")
    msg.add_alternative(html, subtype="html")
    return msg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--html", required=True, help="rendered edition HTML")
    p.add_argument("--subject", required=True)
    p.add_argument("--to", nargs="+", required=True)
    p.add_argument("--text-file", default=None, help="plain-text alternative")
    p.add_argument("--from-name", default="The Morning")
    p.add_argument("--dry-run", action="store_true",
                   help="build and validate the message, but do not send")
    args = p.parse_args()

    args.user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not args.dry_run and not (args.user and password):
        print("GMAIL_USER and GMAIL_APP_PASSWORD must both be set.", file=sys.stderr)
        return 2
    args.user = args.user or "dry-run@example.com"

    with open(args.html, encoding="utf-8") as f:
        html = f.read()
    text = None
    if args.text_file and os.path.exists(args.text_file):
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read()

    if len(html) > 100_000:
        # Gmail clips anything past ~102KB and hides the tail behind a link.
        print(f"WARNING: message body is {len(html)} bytes; Gmail clips near "
              f"102400. Trim the edition.", file=sys.stderr)

    msg = build(args, html, text)

    if args.dry_run:
        print(f"OK (dry run) — {len(html)} bytes HTML, "
              f"{len(text or '')} bytes text, to {', '.join(args.to)}")
        return 0

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as s:
        s.login(args.user, password)
        s.send_message(msg)

    print(f"sent to {', '.join(args.to)} ({len(html)} bytes HTML)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
