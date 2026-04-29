import os
import re
import smtplib
import html as html_lib
from email.message import EmailMessage
from email.utils import formatdate
from email.utils import make_msgid

URL_PATTERN = re.compile(r"(https?://[^\s<>()]+)")
EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def get_from_address():
    return os.getenv("FORMS_EMAIL_FROM", "no-reply@sydney.emom.me")


def get_smtp_host():
    return os.getenv("FORMS_SMTP_HOST", "mail.f8.com.au")


def get_smtp_port():
    return int(os.getenv("FORMS_SMTP_PORT", "25"))


def send_mail(to_address, subject, text_body, html_body=None, reply_to=None):
    message = EmailMessage()
    message["From"] = get_from_address()
    message["To"] = to_address
    if reply_to:
        message["Reply-To"] = reply_to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(text_body)
    message.add_alternative(
        html_body or render_basic_html_from_text(text_body),
        subtype="html",
    )

    with smtplib.SMTP(get_smtp_host(), get_smtp_port(), timeout=30) as smtp:
        smtp.send_message(message)


def render_basic_html_from_text(text_body):
    escaped = html_lib.escape(str(text_body or ""))
    linked = URL_PATTERN.sub(
        lambda match: f"<a href=\"{match.group(1)}\">{match.group(1)}</a>",
        escaped,
    )
    linked = EMAIL_PATTERN.sub(
        lambda match: f"<a href=\"mailto:{match.group(1)}\">{match.group(1)}</a>",
        linked,
    )
    with_breaks = linked.replace("\n", "<br>\n")
    return f"<html><body><p>{with_breaks}</p></body></html>"
