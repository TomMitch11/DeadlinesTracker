from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import get_email_config


def _send(subject: str, body_html: str) -> None:
    cfg = get_email_config()
    if not cfg["smtp_user"] or not cfg["to_addr"]:
        return  # email not configured — skip silently

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = cfg["to_addr"]
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.sendmail(cfg["from_addr"], cfg["to_addr"], msg.as_string())


def _row(label: str, value: str) -> str:
    return f"<tr><td style='padding:4px 12px 4px 0;color:#888;'>{label}</td><td style='padding:4px 0;'>{value}</td></tr>"


def _fixture_block(f: dict, badge: str = "", badge_colour: str = "#3498db") -> str:
    badge_html = (
        f"<span style='background:{badge_colour};color:white;padding:2px 8px;"
        f"border-radius:4px;font-size:12px;margin-left:8px;'>{badge}</span>"
        if badge else ""
    )
    rows = [
        _row("Match", f"{f['home_team']} vs {f['away_team']}{badge_html}"),
        _row("Date", f["match_date"]),
        _row("Competition", f.get("competition") or "—"),
        _row("Venue", f.get("venue") or "—"),
        _row("Approval deadline", f["approval_deadline"]),
    ]
    if f.get("old_date"):
        rows.insert(2, _row("Previous date", f"<s>{f['old_date']}</s>"))
    if f.get("cup_warning"):
        rows.append(_row("⚠️ Note", f["cup_warning"]))
    return (
        "<div style='border-left:3px solid #ddd;padding:8px 16px;margin:12px 0;'>"
        f"<table style='font-family:sans-serif;font-size:14px;'>{''.join(rows)}</table>"
        "</div>"
    )


def send_sync_summary(
    new_fixtures: list[dict],
    rescheduled_fixtures: list[dict],
) -> None:
    if not new_fixtures and not rescheduled_fixtures:
        return

    parts = []

    if new_fixtures:
        parts.append("<h3 style='margin-bottom:4px;'>New fixtures added</h3>")
        for f in new_fixtures:
            colour = "#e67e22" if f.get("cup_warning") else "#27ae60"
            badge = "Cup?" if f.get("cup_warning") else "New"
            parts.append(_fixture_block(f, badge=badge, badge_colour=colour))

    if rescheduled_fixtures:
        parts.append("<h3 style='margin-bottom:4px;'>Fixtures rescheduled</h3>")
        for f in rescheduled_fixtures:
            parts.append(_fixture_block(f, badge="Rescheduled", badge_colour="#e74c3c"))

    total = len(new_fixtures) + len(rescheduled_fixtures)
    subject = f"Deadlines Tracker — {total} fixture update{'s' if total != 1 else ''}"

    body = (
        "<div style='font-family:sans-serif;max-width:600px;'>"
        f"<h2>Fixture sync update</h2>"
        + "".join(parts)
        + "<p style='color:#aaa;font-size:12px;margin-top:24px;'>Deadlines Tracker</p>"
        "</div>"
    )

    _send(subject, body)
