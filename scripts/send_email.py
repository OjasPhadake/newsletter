#!/usr/bin/env python3
"""Send the rendered newsletter.

A GitHub Actions runner has no Gmail connector, so the send happens directly.
Which way is [sender].provider in newsletter.toml, overridable with
--provider. Credentials always come from the environment and are never
written to disk or echoed.

    gmail   GMAIL_USER, GMAIL_APP_PASSWORD          (SMTP, the default)
    smtp    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    resend  RESEND_API_KEY, RESEND_FROM             (HTTPS, no app password)

    GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx \\
    python3 scripts/send_email.py \\
        --html build/edition.html \\
        --subject "The Morning · ..." \\
        --text-file build/edition.txt \\
        --to reader@example.com
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as _config

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465
RESEND_URL = "https://api.resend.com/emails"


def credentials(provider, dry_run):
    """(sender address, secret) for the chosen provider, or an error string."""
    if provider == "gmail":
        user = os.environ.get("GMAIL_USER", "").strip()
        secret = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
        missing = "GMAIL_USER and GMAIL_APP_PASSWORD must both be set."
    elif provider == "smtp":
        user = os.environ.get("SMTP_USER", "").strip()
        secret = os.environ.get("SMTP_PASSWORD", "").strip()
        missing = ("SMTP_USER and SMTP_PASSWORD must both be set "
                   "(with SMTP_HOST, and SMTP_PORT if not 465).")
    elif provider == "resend":
        user = os.environ.get("RESEND_FROM", "").strip()
        secret = os.environ.get("RESEND_API_KEY", "").strip()
        missing = ("RESEND_API_KEY and RESEND_FROM must both be set. "
                   "RESEND_FROM has to be on a domain verified with Resend.")
    else:
        return None, None, f"unknown provider {provider!r}"

    if not dry_run and not (user and secret):
        return None, None, missing
    return (user or "dry-run@example.com"), secret, None


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
    p.add_argument("--from-name", default=None,
                   help="default: [sender].from_name in newsletter.toml")
    p.add_argument("--provider", default=None, choices=["gmail", "smtp", "resend"],
                   help="default: [sender].provider in newsletter.toml")
    p.add_argument("--dry-run", action="store_true",
                   help="build and validate the message, but do not send")
    args = p.parse_args()

    cfg = _config.load()
    args.from_name = args.from_name or cfg["sender"]["from_name"]
    provider = args.provider or cfg["sender"]["provider"]

    args.user, password, problem = credentials(provider, args.dry_run)
    if problem:
        print(problem, file=sys.stderr)
        return 2

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
        print(f"OK (dry run, {provider}) — {len(html)} bytes HTML, "
              f"{len(text or '')} bytes text, to {', '.join(args.to)}")
        return 0

    if provider == "resend":
        req = urllib.request.Request(
            RESEND_URL,
            data=json.dumps({
                "from": formataddr((args.from_name, args.user)),
                "to": args.to, "subject": args.subject,
                "html": html, "text": text or "",
            }).encode(),
            headers={"Authorization": f"Bearer {password}",
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            json.loads(r.read().decode())
    else:
        host = (GMAIL_HOST if provider == "gmail"
                else os.environ.get("SMTP_HOST", "").strip())
        port = (GMAIL_PORT if provider == "gmail"
                else int(os.environ.get("SMTP_PORT", GMAIL_PORT)))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(args.user, password)
            s.send_message(msg)

    print(f"sent to {', '.join(args.to)} ({len(html)} bytes HTML, via {provider})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
