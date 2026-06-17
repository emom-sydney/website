import os

from flask import Flask, jsonify, request

from forms_bridge.contact_us_workflow import register_contact_us_workflow_routes
from forms_bridge.newsletter_workflow import register_newsletter_workflow_routes
from forms_bridge.performer_workflow import register_performer_workflow_routes


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

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    register_newsletter_workflow_routes(app)

    register_performer_workflow_routes(app)

    register_contact_us_workflow_routes(app)

    return app


def error_response(message, status_code):
    return jsonify({"ok": False, "error": message}), status_code


app = create_app()
