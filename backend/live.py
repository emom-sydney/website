import json

from flask import Response, jsonify, render_template, request

from backend.admin import api_data, api_error, require_csrf, require_staff
from backend.db import connect
import backend.performer_workflow as workflow


SETTING_KEY = "live_now_playing"


def _state(cursor):
    cursor.execute("SELECT value_json FROM app_settings WHERE key = %s", (SETTING_KEY,))
    row = cursor.fetchone()
    value = row[0] if row else {}
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _now_playing(cursor):
    state = _state(cursor)
    event_id = state.get("event_id")
    request_id = state.get("requested_date_id")
    profile_id = state.get("profile_id")
    name = None
    if event_id and (request_id or profile_id):
        cursor.execute(
            """SELECT p.display_name FROM performances perf
               JOIN profiles p ON p.id = perf.profile_id
               WHERE perf.event_id = %s AND perf.profile_id = %s""",
            (event_id, profile_id or -1),
        )
        row = cursor.fetchone()
        name = row[0] if row else None
    return {"event_id": event_id, "profile_id": profile_id, "text": name or " "}


def register_live_routes(app):
    @app.get("/live/stagemanager")
    @require_staff(moderator=True, api=False)
    def stagemanager_page():
        return render_template("live/stagemanager.html", staff=None)

    @app.get("/live/now-playing.txt")
    def now_playing_txt():
        with connect() as connection, connection.cursor() as cursor:
            value = _now_playing(cursor)["text"]
        return Response(value, mimetype="text/plain", headers={"Cache-Control": "no-store"})

    @app.get("/live/now-playing.html")
    def now_playing_html():
        with connect() as connection, connection.cursor() as cursor:
            value = _now_playing(cursor)
        return render_template("live/now_playing.html", now_playing=value)

    @app.get("/api/v1/live/now-playing")
    def now_playing_api():
        with connect() as connection, connection.cursor() as cursor:
            return api_data(_now_playing(cursor))

    @app.get("/api/v1/admin/live/now-playing")
    @require_staff(moderator=True)
    def admin_live_now_playing():
        with connect() as connection, connection.cursor() as cursor:
            value = _now_playing(cursor)
            events = workflow.get_upcoming_events(cursor)
            for event in events:
                cursor.execute(
                    """SELECT p.id, p.display_name, perf.sort_order
                       FROM performances perf JOIN profiles p ON p.id = perf.profile_id
                       WHERE perf.event_id = %s ORDER BY perf.sort_order, perf.id""",
                    (event["event_id"],),
                )
                event["performers"] = [
                    {"profile_id": row[0], "display_name": row[1], "sort_order": row[2]}
                    for row in cursor.fetchall()
                ]
        return api_data({"now_playing": value, "events": events})

    @app.put("/api/v1/admin/live/now-playing")
    @require_staff(moderator=True)
    def save_live_now_playing():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        event_id = payload.get("event_id")
        profile_id = payload.get("profile_id")
        if event_id is not None:
            try:
                event_id = int(event_id)
            except (TypeError, ValueError):
                return api_error("invalid_event", "event_id must be an integer.")
        if profile_id is not None:
            try:
                profile_id = int(profile_id)
            except (TypeError, ValueError):
                return api_error("invalid_performer", "profile_id must be an integer.")
        with connect() as connection, connection.cursor() as cursor:
            if event_id and profile_id:
                cursor.execute("SELECT 1 FROM performances WHERE profile_id = %s AND event_id = %s", (profile_id, event_id))
                if not cursor.fetchone():
                    return api_error("invalid_performer", "That performer is not part of this event.")
            value = {"event_id": event_id, "profile_id": profile_id}
            cursor.execute(
                """INSERT INTO app_settings (key, value_json) VALUES (%s, %s::jsonb)
                   ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json""",
                (SETTING_KEY, json.dumps(value)),
            )
            return api_data(_now_playing(cursor))
