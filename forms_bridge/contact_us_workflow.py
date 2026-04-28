import re

from flask import jsonify, request

from forms_bridge.mailer import get_from_address
from forms_bridge.mailer import send_mail


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def register_contact_us_workflow_routes(app):
    @app.route("/api/forms/contact-us", methods=["OPTIONS"])
    def contact_us_options():
        return ("", 204)

    @app.route("/api/forms/contact-us", methods=["POST"])
    def submit_contact_us():
        try:
            payload = get_json_payload()
            name = normalize_text(payload.get("name"))
            email = normalize_email(payload.get("email"))
            message = normalize_text(payload.get("message"))

            if not name:
                return error_response("Your name is required.", 400)
            if not email:
                return error_response("A valid email address is required.", 400)
            if not message:
                return error_response("A message is required.", 400)

            send_contact_email(name=name, email=email, message=message)

            return jsonify({"ok": True, "message": "Thanks. Your message has been sent."}), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Contact form submission failed")
            return error_response("Unable to send your message right now.", 500)


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
    email = normalize_text(value)
    if not email:
        return None
    email = email.lower()
    if not EMAIL_PATTERN.match(email):
        return None
    return email


def get_contact_to_address():
    return "websitecontact@sydney.emom.me"


def send_contact_email(*, name, email, message):
    body = (
        "New contact form submission from sydney.emom.me.\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n\n"
        "Message:\n"
        f"{message}\n"
    )

    send_mail(
        get_contact_to_address(),
        f"sydney.emom | contact form message from {name}",
        body,
        reply_to=email,
    )


def error_response(message, status_code):
    return jsonify({"ok": False, "error": message}), status_code
