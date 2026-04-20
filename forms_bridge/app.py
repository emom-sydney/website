import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request

from forms_bridge.db import connect
from forms_bridge.newsletter_workflow import register_newsletter_workflow_routes
from forms_bridge.performer_workflow import register_performer_workflow_routes


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_app():
    app = Flask(__name__)
    allowed_origins = {
        origin.strip()
        for origin in os.getenv("FORMS_API_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin and (not allowed_origins or origin in allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/forms/merch-interest", methods=["OPTIONS"])
    def merch_interest_options():
        return ("", 204)

    @app.route("/api/forms/merch-interest", methods=["POST"])
    def submit_merch_interest():
        if not request.is_json:
            return error_response("Request body must be JSON.", 400)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error_response("Invalid JSON payload.", 400)

        email = normalize_text(payload.get("email"))
        comments = normalize_text(payload.get("comments"))
        raw_lines = payload.get("lines")

        if not email or not EMAIL_PATTERN.match(email):
            return error_response("A valid email address is required.", 400)

        if not isinstance(raw_lines, list) or not raw_lines:
            return error_response("At least one merch selection is required.", 400)

        normalized_lines = normalize_lines(raw_lines)
        if not normalized_lines:
            return error_response("At least one merch selection is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    ensure_variants_exist(cursor, normalized_lines.keys())

                    cursor.execute(
                        """
                        INSERT INTO merch_interest_submissions (email, comments)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (email, comments),
                    )
                    submission_id = cursor.fetchone()[0]

                    for merch_variant_id, quantity in normalized_lines.items():
                        cursor.execute(
                            """
                            INSERT INTO merch_interest_lines (submission_id, merch_variant_id, quantity, submitted_price)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                submission_id,
                                merch_variant_id,
                                quantity["quantity"],
                                quantity["submitted_price"],
                            ),
                        )

            return jsonify(
                {
                    "ok": True,
                    "submission_id": submission_id,
                    "line_count": len(normalized_lines),
                }
            ), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Merch interest submission failed")
            return error_response("Unable to save submission right now.", 500)

    register_newsletter_workflow_routes(app)

    register_performer_workflow_routes(app)

    return app


def normalize_text(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def normalize_lines(lines):
    normalized = defaultdict(int)

    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Each merch selection must be an object.")

        merch_variant_id = line.get("merch_variant_id")
        quantity = line.get("quantity", 1)
        submitted_price = line.get("submitted_price")

        if not isinstance(merch_variant_id, int):
            raise ValueError("Each merch selection must include an integer merch_variant_id.")

        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Each merch selection must include a positive integer quantity.")

        normalized_price = normalize_price(submitted_price)
        if merch_variant_id in normalized:
            normalized[merch_variant_id]["quantity"] += quantity
        else:
            normalized[merch_variant_id] = {
                "quantity": quantity,
                "submitted_price": normalized_price,
            }

    return dict(normalized)


def normalize_price(value):
    if value is None:
        raise ValueError("Each merch selection must include a submitted price.")

    text = str(value).strip()
    if not text:
        raise ValueError("Each merch selection must include a submitted price.")

    try:
        price = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Each merch selection must include a valid price.") from exc

    if price < 0:
        raise ValueError("Each merch selection must include a non-negative price.")

    return price.quantize(Decimal("0.01"))


def ensure_variants_exist(cursor, variant_ids):
    cursor.execute(
        """
        SELECT id
        FROM merch_variants
        WHERE is_active = true
          AND id = ANY(%s)
        """,
        (list(variant_ids),),
    )
    found_ids = {row[0] for row in cursor.fetchall()}
    missing_ids = sorted(set(variant_ids) - found_ids)

    if missing_ids:
        raise ValueError(f"Unknown or inactive merch variant ids: {', '.join(str(item) for item in missing_ids)}")


def error_response(message, status_code):
    return jsonify({"ok": False, "error": message}), status_code


app = create_app()
