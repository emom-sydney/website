import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.admin import register_admin_routes
from backend.contact_us_workflow import register_contact_us_workflow_routes
from backend.keila_workflow import register_newsletter_workflow_routes
from backend.performer_workflow import register_performer_workflow_routes
from backend.profile_qr import register_profile_qr_routes
from backend.live import register_live_routes
from backend.calendar import register_calendar_routes


def create_app():
    app = Flask(__name__)
    allowed_origins = {
        origin.strip()
        for origin in os.getenv("API_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-CSRF-Token"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return jsonify({"data": {"status": "ok"}})

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        if not request.path.startswith("/api/"):
            return error

        return (
            jsonify(
                {
                    "error": {
                        "code": error.name.lower().replace(" ", "_"),
                        "message": error.description or error.name,
                    }
                }
            ),
            error.code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        if not request.path.startswith("/api/"):
            raise error
        app.logger.exception("Unhandled API error", exc_info=error)
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "The server could not complete this request.",
                    }
                }
            ),
            500,
        )

    register_newsletter_workflow_routes(app)

    register_performer_workflow_routes(app)

    register_profile_qr_routes(app)

    register_contact_us_workflow_routes(app)

    register_admin_routes(app)

    register_live_routes(app)

    register_calendar_routes(app)

    return app


app = create_app()
