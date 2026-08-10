import email
import email.header
import pytest
from unittest.mock import MagicMock, patch
from notifications import _fixture_block, send_sync_summary

FAKE_EMAIL_CFG = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "bot@example.com",
    "smtp_password": "secret",
    "from_addr": "bot@example.com",
    "to_addr": "ops@example.com",
}

EMPTY_EMAIL_CFG = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "from_addr": "",
    "to_addr": "",
}

FIXTURE = {
    "home_team": "LA Galaxy",
    "away_team": "Portland",
    "match_date": "2026-06-10",
    "competition": "MLS",
    "venue": "Dignity Health Sports Park",
    "approval_deadline": "2026-06-05",
    "cup_warning": None,
}


def test_fixture_block_escapes_html_in_team_names():
    malicious = {**FIXTURE, "away_team": "<script>alert(1)</script>"}
    html_out = _fixture_block(malicious)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_fixture_block_escapes_cup_warning():
    warned = {**FIXTURE, "cup_warning": "Might be a cup game & needs <check>"}
    html_out = _fixture_block(warned)
    assert "<check>" not in html_out
    assert "&lt;check&gt;" in html_out


def test_send_sync_summary_noop_when_nothing_changed():
    with patch("notifications.get_email_config", return_value=FAKE_EMAIL_CFG), \
         patch("notifications.smtplib.SMTP") as mock_smtp:
        send_sync_summary([], [])
    mock_smtp.assert_not_called()


def test_send_sync_summary_noop_when_not_configured():
    with patch("notifications.get_email_config", return_value=EMPTY_EMAIL_CFG), \
         patch("notifications.smtplib.SMTP") as mock_smtp:
        send_sync_summary([FIXTURE], [])
    mock_smtp.assert_not_called()


def test_send_sync_summary_sends_when_configured():
    server = MagicMock()
    server.__enter__.return_value = server
    with patch("notifications.get_email_config", return_value=FAKE_EMAIL_CFG), \
         patch("notifications.smtplib.SMTP", return_value=server) as mock_smtp:
        send_sync_summary([FIXTURE], [])
    mock_smtp.assert_called_once_with("smtp.example.com", 587)
    server.login.assert_called_once_with("bot@example.com", "secret")
    server.sendmail.assert_called_once()


def test_send_sync_summary_subject_counts_new_and_rescheduled():
    server = MagicMock()
    server.__enter__.return_value = server
    with patch("notifications.get_email_config", return_value=FAKE_EMAIL_CFG), \
         patch("notifications.smtplib.SMTP", return_value=server):
        send_sync_summary([FIXTURE], [{**FIXTURE, "old_date": "2026-06-03"}])
    sent_body = server.sendmail.call_args[0][2]
    parsed = email.message_from_string(sent_body)
    subject = str(email.header.make_header(email.header.decode_header(parsed["Subject"])))
    assert "2 fixture updates" in subject
