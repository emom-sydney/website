import hashlib
import html
import json
import logging
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate
from email.utils import make_msgid
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request
from urllib.request import urlopen

from flask import jsonify, request

from forms_bridge.db import connect


NEWSLETTER_CONFIRM_ACTION = "newsletter_subscribe_confirm"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)


def register_newsletter_workflow_routes(app):
    @app.route("/api/forms/newsletter-subscribe/start", methods=["OPTIONS"])
    def newsletter_subscribe_start_options():
        return ("", 204)

    @app.route("/api/forms/newsletter-subscribe/start", methods=["POST"])
    def newsletter_subscribe_start():
        try:
            payload = get_json_payload()
            email = normalize_email(payload.get("email"))
            first_name = normalize_text(payload.get("first_name"))
            last_name = normalize_text(payload.get("last_name"))

            if not email:
                return error_response("A valid email address is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    ttl_hours = get_newsletter_token_ttl_hours()
                    invalidated_count = invalidate_unused_newsletter_tokens(cursor, email)
                    raw_token, token_hash = generate_token_pair()
                    expires_at = now_utc() + timedelta(hours=ttl_hours)

                    cursor.execute(
                        """
                        INSERT INTO action_tokens (token_hash, action_type, email, expires_at)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (token_hash, NEWSLETTER_CONFIRM_ACTION, email, expires_at),
                    )
                    action_token_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO newsletter_subscribe_requests (action_token_id, first_name, last_name)
                        VALUES (%s, %s, %s)
                        """,
                        (action_token_id, first_name, last_name),
                    )
                    logger.info(
                        "newsletter_subscribe_start token_created email=%s token_id=%s ttl_hours=%s invalidated_previous=%s",
                        email,
                        action_token_id,
                        ttl_hours,
                        invalidated_count,
                    )

                send_newsletter_confirmation_email(app, email, raw_token, expires_at)
                logger.info("newsletter_subscribe_start confirmation_email_sent email=%s token_id=%s", email, action_token_id)

            return (
                jsonify(
                    {
                        "ok": True,
                        "message": "Thanks. Please check your email and confirm your subscription.",
                    }
                ),
                201,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Newsletter subscribe start failed")
            return error_response("Unable to start newsletter subscription right now.", 500)

    @app.route("/api/forms/newsletter-subscribe/confirm", methods=["GET"])
    def newsletter_subscribe_confirm():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return html_error_page("Missing confirmation token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token)
                    subscribe_request = get_newsletter_subscribe_request(cursor, token_row["id"])
                    logger.info(
                        "newsletter_subscribe_confirm token_valid token_id=%s email=%s",
                        token_row["id"],
                        token_row["email"],
                    )

            upsert_contact_in_keila(
                email=token_row["email"],
                first_name=subscribe_request["first_name"],
                last_name=subscribe_request["last_name"],
            )
            logger.info(
                "newsletter_subscribe_confirm keila_upsert_complete token_id=%s email=%s",
                token_row["id"],
                token_row["email"],
            )

            with connect() as connection:
                with connection.cursor() as cursor:
                    mark_action_token_used(cursor, token_row["id"])
                    logger.info(
                        "newsletter_subscribe_confirm token_marked_used token_id=%s email=%s",
                        token_row["id"],
                        token_row["email"],
                    )

            return html_success_page(
                "Subscription confirmed",
                f"Thanks, {token_row['email']} has been subscribed to the newsletter. <a href=\"/\">return to sydney.emom</a>",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except RuntimeError:
            app.logger.exception("Newsletter confirmation failed due to upstream API error")
            return html_error_page("Unable to confirm your subscription right now. Please try again soon.", 500)
        except Exception:
            app.logger.exception("Newsletter confirmation failed")
            return html_error_page("Unable to confirm your subscription right now. Please try again soon.", 500)


def get_json_payload():
    if not request.is_json:
        raise ValueError("Request body must be JSON.")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON payload.")

    return payload


def normalize_text(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def normalize_email(value):
    text = normalize_text(value)
    if not text:
        return None

    email = text.lower()
    if not EMAIL_PATTERN.match(email):
        return None

    return email


def now_utc():
    return datetime.now(timezone.utc)


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token_pair():
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


def get_newsletter_token_ttl_hours():
    value = normalize_text(os.getenv("NEWSLETTER_TOKEN_TTL_HOURS"))
    if not value:
        return 24
    if not value.isdigit():
        raise ValueError("NEWSLETTER_TOKEN_TTL_HOURS must be an integer.")
    ttl_hours = int(value)
    if ttl_hours <= 0:
        raise ValueError("NEWSLETTER_TOKEN_TTL_HOURS must be greater than zero.")
    return ttl_hours


def invalidate_unused_newsletter_tokens(cursor, email):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE action_type = %s
          AND lower(email) = lower(%s)
          AND used_at IS NULL
        """,
        (NEWSLETTER_CONFIRM_ACTION, email),
    )
    return cursor.rowcount


def get_action_token(cursor, raw_token):
    token_hash = hash_token(raw_token)
    cursor.execute(
        """
        SELECT id, email, expires_at, used_at
        FROM action_tokens
        WHERE token_hash = %s
          AND action_type = %s
        """,
        (token_hash, NEWSLETTER_CONFIRM_ACTION),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("This confirmation link is invalid.")

    token_row = {
        "id": row[0],
        "email": row[1],
        "expires_at": row[2],
        "used_at": row[3],
    }
    if token_row["used_at"] is not None:
        raise ValueError("This confirmation link has already been used.")
    if token_row["expires_at"] <= now_utc():
        raise ValueError("This confirmation link has expired.")
    if not token_row["email"]:
        raise ValueError("This confirmation link is invalid.")

    return token_row


def get_newsletter_subscribe_request(cursor, action_token_id):
    cursor.execute(
        """
        SELECT first_name, last_name
        FROM newsletter_subscribe_requests
        WHERE action_token_id = %s
        """,
        (action_token_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("This confirmation link is invalid.")

    return {"first_name": row[0], "last_name": row[1]}


def mark_action_token_used(cursor, action_token_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE id = %s
          AND used_at IS NULL
        """,
        (action_token_id,),
    )
    if cursor.rowcount != 1:
        raise ValueError("This confirmation link has already been used.")


def build_absolute_url(app, path):
    del app
    base_url = os.getenv("FORMS_SITE_BASE_URL") or os.getenv("PUBLIC_SITE_BASE_URL")
    if not base_url:
        raise ValueError("FORMS_SITE_BASE_URL must be configured.")
    return f"{base_url.rstrip('/')}{path}"


def format_link_expiry_local(expires_at):
    return expires_at.astimezone().strftime("%H:%M:%S on %d/%m/%y")


def get_from_address():
    return os.getenv("FORMS_EMAIL_FROM", "no-reply@sydney.emom.me")


def get_smtp_host():
    return os.getenv("FORMS_SMTP_HOST", "mail.f8.com.au")


def get_smtp_port():
    return int(os.getenv("FORMS_SMTP_PORT", "25"))


def send_mail(to_address, subject, body):
    message = EmailMessage()
    message["From"] = get_from_address()
    message["To"] = to_address
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    with smtplib.SMTP(get_smtp_host(), get_smtp_port(), timeout=30) as smtp:
        smtp.send_message(message)


def send_newsletter_confirmation_email(app, email, raw_token, expires_at):
    confirm_url = build_absolute_url(app, f"/api/forms/newsletter-subscribe/confirm?token={raw_token}")
    body = (
        "Please confirm your subscription to the EMOM Sydney newsletter by opening this link:\n\n"
        f"{confirm_url}\n\n"
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(email, "Confirm your EMOM newsletter subscription", body)


def get_keila_base_url():
    return (os.getenv("KEILA_API_BASE_URL") or "https://keila.emom.me").rstrip("/")


def get_keila_api_key():
    api_key = normalize_text(os.getenv("KEILA_API_KEY"))
    if not api_key:
        raise ValueError("KEILA_API_KEY must be configured.")
    return api_key


def get_keila_timeout_seconds():
    value = normalize_text(os.getenv("KEILA_TIMEOUT_SECONDS"))
    if not value:
        return 10
    if not value.isdigit():
        return 10
    timeout_seconds = int(value)
    return timeout_seconds if timeout_seconds > 0 else 10


def keila_request(method, path, payload=None, allow_not_found=False):
    url = f"{get_keila_base_url()}{path}"
    api_key = get_keila_api_key()
    request_body = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if payload is not None:
        request_body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=request_body, headers=headers, method=method)
    try:
        logger.info("keila_request start method=%s path=%s", method, path)
        with urlopen(req, timeout=get_keila_timeout_seconds()) as response:
            raw = response.read().decode("utf-8")
            logger.info("keila_request success method=%s path=%s status=%s", method, path, response.status)
            if not raw:
                return None
            return json.loads(raw)
    except HTTPError as exc:
        if allow_not_found and exc.code == 404:
            logger.info("keila_request not_found method=%s path=%s", method, path)
            return None
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("keila_request http_error method=%s path=%s status=%s body=%s", method, path, exc.code, body)
        raise RuntimeError(f"Keila API request failed ({exc.code}): {body}") from exc
    except URLError as exc:
        logger.error("keila_request network_error method=%s path=%s reason=%s", method, path, exc.reason)
        raise RuntimeError(f"Unable to reach Keila API: {exc.reason}") from exc


def build_keila_contact_payload(email, first_name=None, last_name=None):
    data = {"email": email, "status": "active"}
    if first_name:
        data["first_name"] = first_name
    if last_name:
        data["last_name"] = last_name
    return {"data": data}


def upsert_contact_in_keila(*, email, first_name=None, last_name=None):
    lookup_path = f"/api/v1/contacts/{quote(email, safe='')}?id_type=email"
    payload = build_keila_contact_payload(email, first_name=first_name, last_name=last_name)

    existing = keila_request("GET", lookup_path, allow_not_found=True)
    if existing is None:
        keila_request("POST", "/api/v1/contacts", payload=payload)
        logger.info("keila_upsert created email=%s", email)
        return

    keila_request("PUT", lookup_path, payload=payload)
    logger.info("keila_upsert updated email=%s", email)


def html_success_page(title, message):
    return (
        render_html_page(title=title, heading=title, message=message),
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


def html_error_page(message, status_code):
    return (
        render_html_page(title="Error", heading="Error", message=message),
        status_code,
        {"Content-Type": "text/html; charset=utf-8"},
    )


def render_html_page(*, title, heading, message):
    safe_title = html.escape(title)
    safe_heading = html.escape(heading)
    safe_message = html.escape(message)

    return (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        "body{margin:0;padding:24px;background:#1b1b1b;color:#ddd;font-family:'Lucida Console','Courier New',monospace;}"
        ".panel{width:min(100%,1000px);margin:24px auto;padding:24px;background:#fff;color:#333;border-radius:12px;}"
        "h1{margin:0 0 0.8rem;line-height:1.2;}"
        "p{margin:0;line-height:1.45;}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='panel'>"
        f"<h1>{safe_heading}</h1>"
        f"<p>{safe_message}</p>"
        "</div>"
        "</body>"
        "</html>"
    )


def error_response(message, status_code):
    return jsonify({"ok": False, "error": message}), status_code
