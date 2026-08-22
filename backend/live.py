import json

from flask import Response, g, jsonify, render_template, request

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
            """SELECT COALESCE(p.display_name, perf.performer_display_name) FROM performances perf
               LEFT JOIN profiles p ON p.id = perf.profile_id
               WHERE perf.event_id = %s AND perf.profile_id = %s""",
            (event_id, profile_id or -1),
        )
        row = cursor.fetchone()
        name = row[0] if row else None
    return {"event_id": event_id, "profile_id": profile_id, "text": name or " "}


def _now_playing_context(cursor):
    now_playing = _now_playing(cursor)
    event = None
    performers = []
    if now_playing["event_id"]:
        cursor.execute(
            "SELECT event_name, event_date FROM events WHERE id = %s",
            (now_playing["event_id"],),
        )
        row = cursor.fetchone()
        if row:
            event = {"event_name": row[0], "event_date": row[1].isoformat()}
            cursor.execute(
                """SELECT p.id, COALESCE(p.display_name, perf.performer_display_name)
                   FROM performances perf
                   LEFT JOIN profiles p ON p.id = perf.profile_id
                   WHERE perf.event_id = %s
                   ORDER BY perf.sort_order, perf.id""",
                (now_playing["event_id"],),
            )
            performers = [
                {"profile_id": item[0], "display_name": item[1]}
                for item in cursor.fetchall()
            ]
    qr_url = None
    if now_playing["profile_id"]:
        cursor.execute(
            """SELECT 1 FROM profiles p
               JOIN profile_roles pr ON pr.profile_id = p.id AND pr.role = 'artist'
               WHERE p.id = %s
                 AND p.is_profile_approved = true
                 AND (p.profile_visible_from IS NULL OR p.profile_visible_from <= CURRENT_DATE)
                 AND p.profile_expires_on >= CURRENT_DATE""",
            (now_playing["profile_id"],),
        )
        if cursor.fetchone():
            profile_id = now_playing["profile_id"]
            qr_url = f"/api/v1/artists/{profile_id}/qr/display.svg?v={profile_id}"
    return {
        "now_playing": now_playing,
        "event": event,
        "performers": performers,
        "artist_qr_url": qr_url,
    }


def _roll_call(cursor, event_id):
    cursor.execute(
        """
        SELECT p.id, COALESCE(p.display_name, perf.performer_display_name), p.contact_phone, artist_role.bio,
          perf.sort_order, perf.checked_in_at,
          COALESCE(selection.status = 'selected', false), true
        FROM performances perf
        LEFT JOIN profiles p ON p.id = perf.profile_id
        LEFT JOIN profile_roles artist_role
          ON artist_role.profile_id = p.id AND artist_role.role = 'artist'
        LEFT JOIN event_performer_selections selection
          ON selection.event_id = perf.event_id AND selection.profile_id = perf.profile_id
        WHERE perf.event_id = %s
        UNION ALL
        SELECT p.id, p.display_name, p.contact_phone, artist_role.bio,
          NULL, NULL, true, false
        FROM event_performer_selections selection
        JOIN profiles p ON p.id = selection.profile_id
        LEFT JOIN profile_roles artist_role
          ON artist_role.profile_id = p.id AND artist_role.role = 'artist'
        WHERE selection.event_id = %s
          AND selection.status = 'selected'
          AND NOT EXISTS (
            SELECT 1 FROM performances perf
            WHERE perf.event_id = selection.event_id
              AND perf.profile_id = selection.profile_id
          )
        ORDER BY 3 NULLS LAST, 2
        """,
        (event_id, event_id),
    )
    return [
        {
            "profile_id": row[0],
            "display_name": row[1],
            "contact_phone": row[2],
            "bio": row[3],
            "sort_order": row[4],
            "checked_in": row[5] is not None,
            "selected": bool(row[6]),
            "in_performances": bool(row[7]),
        }
        for row in cursor.fetchall()
    ]


def _publish_arrived_artist(cursor, *, profile_id, staff_profile_id):
    """Make a checked-in performer's artist profile available to the next site build."""
    cursor.execute(
        """INSERT INTO profile_roles (profile_id, role)
           VALUES (%s, 'artist')
           ON CONFLICT (profile_id, role) DO NOTHING""",
        (profile_id,),
    )
    cursor.execute(
        """UPDATE profiles
           SET is_profile_approved = true,
               is_profile_index_visible = true,
               profile_visible_from = CASE
                 WHEN profile_visible_from IS NULL OR profile_visible_from > CURRENT_DATE
                   THEN CURRENT_DATE
                 ELSE profile_visible_from
               END,
               profile_expires_on = GREATEST(profile_expires_on, CURRENT_DATE),
               approved_at = COALESCE(approved_at, now()),
               approved_by_profile_id = COALESCE(approved_by_profile_id, %s)
           WHERE id = %s""",
        (staff_profile_id, profile_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("That performer profile no longer exists.")


def register_live_routes(app):
    @app.get("/live/stagemanager")
    @require_staff(moderator=True, api=False)
    def stagemanager_page():
        return render_template("live/stagemanager.html", staff=None)

    @app.get("/now-playing.txt")
    @app.get("/live/now-playing.txt")
    def now_playing_txt():
        with connect() as connection, connection.cursor() as cursor:
            value = _now_playing(cursor)["text"]
        return Response(value, mimetype="text/plain", headers={"Cache-Control": "no-store"})

    @app.get("/now-playing.html")
    @app.get("/live/now-playing.html")
    def now_playing_html():
        with connect() as connection, connection.cursor() as cursor:
            context = _now_playing_context(cursor)
        response = Response(render_template("live/now_playing.html", **context))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/live/now-playing")
    def now_playing_api():
        with connect() as connection, connection.cursor() as cursor:
            return api_data(_now_playing_context(cursor))

    @app.get("/api/v1/admin/live/now-playing")
    @require_staff(moderator=True)
    def admin_live_now_playing():
        try:
            with connect() as connection, connection.cursor() as cursor:
                value = _now_playing(cursor)
                events = workflow.get_upcoming_events(cursor)
                for event in events:
                    event["performers"] = _roll_call(cursor, event["event_id"])
            app.logger.info(
                "stage manager loaded %d upcoming events (live event=%s)",
                len(events),
                value["event_id"],
            )
            return api_data({"now_playing": value, "events": events})
        except Exception:
            app.logger.exception("stage manager API failed while loading upcoming events")
            raise

    @app.put("/api/v1/admin/live/events/<int:event_id>/performers/<int:profile_id>/roll-call")
    @require_staff(moderator=True)
    def update_roll_call(event_id, profile_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        checked_in = payload.get("checked_in")
        if not isinstance(checked_in, bool):
            return api_error("invalid_roll_call", "checked_in must be true or false.")
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM events WHERE id = %s", (event_id,))
            if not cursor.fetchone():
                return api_error("not_found", "Event not found.", 404)
            cursor.execute(
                """SELECT 1 FROM event_performer_selections
                   WHERE event_id = %s AND profile_id = %s AND status = 'selected'
                   UNION ALL
                   SELECT 1 FROM performances WHERE event_id = %s AND profile_id = %s""",
                (event_id, profile_id, event_id, profile_id),
            )
            if not cursor.fetchone():
                return api_error("invalid_performer", "That performer is not on this event's roll-call.")
            if checked_in:
                _publish_arrived_artist(
                    cursor,
                    profile_id=profile_id,
                    staff_profile_id=g.staff["profile_id"],
                )
                cursor.execute(
                    """INSERT INTO performances (event_id, profile_id, performer_display_name, sort_order, checked_in_at)
                       VALUES (
                         %s, %s,
                         (SELECT display_name FROM profiles WHERE id = %s),
                         (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM performances WHERE event_id = %s),
                         now()
                       )
                       ON CONFLICT (event_id, profile_id)
                       DO UPDATE SET checked_in_at = now()""",
                    (event_id, profile_id, profile_id, event_id),
                )
            else:
                cursor.execute(
                    """UPDATE performances SET checked_in_at = NULL
                       WHERE event_id = %s AND profile_id = %s""",
                    (event_id, profile_id),
                )
            return api_data({"performers": _roll_call(cursor, event_id)})

    @app.put("/api/v1/admin/live/events/<int:event_id>/performers/order")
    @require_staff(moderator=True)
    def save_performance_order(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        profile_ids = payload.get("profile_ids")
        moved_profile_id = payload.get("moved_profile_id")
        if not isinstance(profile_ids, list):
            return api_error("invalid_order", "A profile_ids list is required.")
        try:
            profile_ids = [int(profile_id) for profile_id in profile_ids]
            moved_profile_id = int(moved_profile_id)
        except (TypeError, ValueError):
            return api_error("invalid_order", "Profile IDs must be integers.")
        if len(profile_ids) != len(set(profile_ids)):
            return api_error("invalid_order", "A performer cannot appear twice.")
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT profile_id FROM performances WHERE event_id = %s AND profile_id IS NOT NULL
                   UNION
                   SELECT profile_id FROM event_performer_selections
                   WHERE event_id = %s AND status = 'selected'""",
                (event_id, event_id),
            )
            available_ids = {row[0] for row in cursor.fetchall()}
            if moved_profile_id not in available_ids or not set(profile_ids).issubset(available_ids):
                return api_error("invalid_order", "One or more performers are not available for this event.")
            cursor.execute(
                """INSERT INTO performances (event_id, profile_id, performer_display_name, sort_order)
                   SELECT %s, p.id, p.display_name, 0 FROM profiles p WHERE p.id = %s
                   ON CONFLICT (event_id, profile_id) DO NOTHING""",
                (event_id, moved_profile_id),
            )
            cursor.execute(
                "SELECT profile_id FROM performances WHERE event_id = %s",
                (event_id,),
            )
            existing_ids = {row[0] for row in cursor.fetchall()}
            ordered_ids = [profile_id for profile_id in profile_ids if profile_id in existing_ids]
            if set(ordered_ids) != existing_ids:
                return api_error("invalid_order", "The order must include every performance exactly once.")
            for sort_order, profile_id in enumerate(ordered_ids):
                cursor.execute(
                    "UPDATE performances SET sort_order = %s WHERE event_id = %s AND profile_id = %s",
                    (sort_order, event_id, profile_id),
                )
            return api_data({"performers": _roll_call(cursor, event_id)})

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
            if profile_id is None:
                event_id = None
            value = {"event_id": event_id, "profile_id": profile_id}
            cursor.execute(
                """INSERT INTO app_settings (key, value_json) VALUES (%s, %s::jsonb)
                   ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json""",
                (SETTING_KEY, json.dumps(value)),
            )
            return api_data(_now_playing(cursor))
