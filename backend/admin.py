import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote

from flask import Response, g, jsonify, make_response, redirect, render_template, request, stream_with_context

import backend.performer_workflow as workflow
from backend.db import connect
from backend.mailer import send_mail

STAFF_LOGIN_ACTION = "staff_login"
SESSION_COOKIE = "emom_staff_session"
CSRF_COOKIE = "emom_staff_csrf"

# TODO Split into multiple files. This one is way too big.
# TODO Move database queries into their own library files.

def now_utc():
    return datetime.now(timezone.utc)


def hash_secret(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def api_data(data, status=200):
    return jsonify({"data": data}), status


def api_error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


def normalize_next_path(value, default="/admin/"):
    value = (value or "").strip()
    if not (value.startswith("/admin/") or value == "/live/stagemanager") or value.startswith("//"):
        return default
    return value


def get_staff_login_ttl_minutes():
    return positive_int_env("STAFF_LOGIN_TOKEN_TTL_MINUTES", 15)


def get_staff_session_ttl_hours():
    return positive_int_env("STAFF_SESSION_TTL_HOURS", 12)


def positive_int_env(name, default):
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def find_staff_by_email(cursor, email):
    cursor.execute(
        """
        SELECT p.id, p.email, p.display_name, p.is_admin, p.is_moderator
        FROM profiles p
        WHERE lower(p.email) = lower(%s)
          AND p.profile_type = 'person'
          AND (p.is_admin = true OR p.is_moderator = true)
          AND EXISTS (
            SELECT 1 FROM profile_roles pr
            WHERE pr.profile_id = p.id AND pr.role = 'volunteer'
          )
        ORDER BY p.id
        """,
        (email,),
    )
    rows = cursor.fetchall()
    if len(rows) > 1:
        raise ValueError("Multiple staff profiles use that email address.")
    if not rows:
        return None
    row = rows[0]
    return {
        "profile_id": row[0],
        "email": row[1],
        "display_name": row[2],
        "is_admin": bool(row[3]),
        "is_moderator": bool(row[4]),
    }


def create_staff_login_token(
    cursor,
    staff,
    *,
    next_path="/admin/",
    draft_id=None,
    event_id=None,
):
    raw_token = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(minutes=get_staff_login_ttl_minutes())
    cursor.execute(
        """
        INSERT INTO action_tokens
          (token_hash, action_type, email, profile_id, draft_id, event_id, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            hash_secret(raw_token),
            STAFF_LOGIN_ACTION,
            staff["email"],
            staff["profile_id"],
            draft_id,
            event_id,
            expires_at,
        ),
    )
    return raw_token, expires_at, normalize_next_path(next_path)


def build_staff_login_url(raw_token, next_path="/admin/"):
    base_url = (os.getenv("PUBLIC_SITE_BASE_URL") or "").rstrip("/")
    if not base_url:
        raise ValueError("PUBLIC_SITE_BASE_URL must be configured.")
    return (
        f"{base_url}/admin/login/verify/?token={quote(raw_token, safe='')}"
        f"&next={quote(normalize_next_path(next_path), safe='/')}"
    )


def send_staff_login_email(staff, raw_token, expires_at, next_path="/admin/"):
    url = build_staff_login_url(raw_token, next_path)
    send_mail(
        staff["email"],
        "sydney.emom | staff access link",
        (
            "Use this one-time link to sign in to the sydney.emom admin area:\n\n"
            f"{url}\n\n"
            f"This link expires at {expires_at.astimezone().strftime('%H:%M:%S on %d/%m/%y')}.\n"
        ),
    )


def load_staff_session():
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not raw_session:
        return None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  s.id, s.profile_id, s.csrf_token_hash, s.expires_at,
                  p.email, p.display_name, p.is_admin, p.is_moderator
                FROM staff_sessions s
                JOIN profiles p ON p.id = s.profile_id
                WHERE s.session_token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > now()
                  AND p.profile_type = 'person'
                  AND (p.is_admin = true OR p.is_moderator = true)
                  AND EXISTS (
                    SELECT 1 FROM profile_roles pr
                    WHERE pr.profile_id = p.id AND pr.role = 'volunteer'
                  )
                """,
                (hash_secret(raw_session),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                "UPDATE staff_sessions SET last_seen_at = now() WHERE id = %s",
                (row[0],),
            )
    return {
        "session_id": row[0],
        "profile_id": row[1],
        "csrf_token_hash": row[2],
        "expires_at": row[3],
        "email": row[4],
        "display_name": row[5],
        "is_admin": bool(row[6]),
        "is_moderator": bool(row[7]),
    }


def require_staff(*, admin=False, moderator=False, api=True):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            staff = load_staff_session()
            if not staff:
                if api:
                    return api_error("authentication_required", "Staff authentication is required.", 401)
                next_path = quote(request.full_path.rstrip("?"), safe="/?=&")
                return redirect(f"/admin/login/?next={next_path}")
            if admin and not staff["is_admin"]:
                if api:
                    return api_error("admin_required", "Administrator access is required.", 403)
                return render_template("admin/error.html", staff=staff, message="Administrator access is required."), 403
            if moderator and not (staff["is_admin"] or staff["is_moderator"]):
                if api:
                    return api_error("moderator_required", "Moderator access is required.", 403)
                return render_template("admin/error.html", staff=staff, message="Moderator access is required."), 403
            g.staff = staff
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_csrf():
    raw_csrf = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    cookie_csrf = request.cookies.get(CSRF_COOKIE)
    if not raw_csrf or not cookie_csrf or not secrets.compare_digest(raw_csrf, cookie_csrf):
        return api_error("csrf_failed", "The security token is missing or invalid.", 403)
    if not secrets.compare_digest(hash_secret(raw_csrf), g.staff["csrf_token_hash"]):
        return api_error("csrf_failed", "The security token is missing or invalid.", 403)
    return None


def register_admin_routes(app):
    @app.get("/admin/login/")
    def admin_login_page():
        return render_template(
            "admin/login.html",
            next_path=normalize_next_path(request.args.get("next")),
        )

    @app.get("/admin/login/verify/")
    def admin_login_verify():
        raw_token = (request.args.get("token") or "").strip()
        next_path = normalize_next_path(request.args.get("next"))
        if not raw_token:
            return render_template("admin/error.html", message="The staff login link is missing."), 400
        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, profile_id, expires_at, used_at
                        FROM action_tokens
                        WHERE token_hash = %s AND action_type = %s
                        """,
                        (hash_secret(raw_token), STAFF_LOGIN_ACTION),
                    )
                    token_row = cursor.fetchone()
                    if not token_row or token_row[3] is not None or token_row[2] <= now_utc():
                        raise ValueError("This staff login link is invalid, expired, or already used.")
                    cursor.execute(
                        """
                        SELECT id, email, display_name, is_admin, is_moderator
                        FROM profiles
                        WHERE id = %s
                          AND profile_type = 'person'
                          AND (is_admin = true OR is_moderator = true)
                          AND EXISTS (
                            SELECT 1 FROM profile_roles pr
                            WHERE pr.profile_id = profiles.id AND pr.role = 'volunteer'
                          )
                        """,
                        (token_row[1],),
                    )
                    staff_row = cursor.fetchone()
                    if not staff_row:
                        raise ValueError("This profile no longer has staff access.")
                    raw_session = secrets.token_urlsafe(32)
                    raw_csrf = secrets.token_urlsafe(32)
                    expires_at = now_utc() + timedelta(hours=get_staff_session_ttl_hours())
                    cursor.execute("UPDATE action_tokens SET used_at = now() WHERE id = %s", (token_row[0],))
                    cursor.execute(
                        """
                        INSERT INTO staff_sessions
                          (session_token_hash, csrf_token_hash, profile_id, expires_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (hash_secret(raw_session), hash_secret(raw_csrf), staff_row[0], expires_at),
                    )
            response = make_response(redirect(next_path))
            max_age = get_staff_session_ttl_hours() * 60 * 60
            response.set_cookie(
                SESSION_COOKIE,
                raw_session,
                max_age=max_age,
                secure=True,
                httponly=True,
                samesite="Lax",
                path="/",
            )
            response.set_cookie(
                CSRF_COOKIE,
                raw_csrf,
                max_age=max_age,
                secure=True,
                httponly=False,
                samesite="Lax",
                path="/",
            )
            return response
        except ValueError as exc:
            return render_template("admin/error.html", message=str(exc)), 400

    @app.post("/api/v1/admin/login-links")
    def request_admin_login_link():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email") or "").strip().lower()
        next_path = normalize_next_path(payload.get("next"))
        if not email or "@" not in email:
            return api_error("invalid_email", "A valid email address is required.")
        with connect() as connection:
            with connection.cursor() as cursor:
                staff = find_staff_by_email(cursor, email)
                if staff:
                    raw_token, expires_at, next_path = create_staff_login_token(
                        cursor, staff, next_path=next_path
                    )
            if staff:
                send_staff_login_email(staff, raw_token, expires_at, next_path)
        return api_data(
            {"message": "If that email belongs to a staff profile, a login link has been sent."},
            202,
        )

    @app.get("/api/v1/admin/session")
    @require_staff()
    def get_admin_session():
        return api_data(
            {
                "profile_id": g.staff["profile_id"],
                "display_name": g.staff["display_name"],
                "email": g.staff["email"],
                "is_admin": g.staff["is_admin"],
                "is_moderator": g.staff["is_moderator"],
                "expires_at": g.staff["expires_at"].isoformat(),
            }
        )

    @app.delete("/api/v1/admin/session")
    @require_staff()
    def delete_admin_session():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE staff_sessions SET revoked_at = now() WHERE id = %s",
                    (g.staff["session_id"],),
                )
        response = make_response("", 204)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return response

    @app.get("/admin/")
    @require_staff(api=False)
    def admin_dashboard_page():
        return render_template("admin/dashboard.html", staff=g.staff, active_tab="dashboard")

    @app.get("/admin/events/")
    @require_staff(moderator=True, api=False)
    def admin_events_page():
        return render_template("admin/events.html", staff=g.staff, active_tab="events")

    @app.get("/admin/locations/")
    @require_staff(admin=True, api=False)
    def admin_locations_page():
        return render_template("admin/locations.html", staff=g.staff, active_tab="events")

    @app.get("/admin/events/<int:event_id>/lineup/")
    @require_staff(admin=True, api=False)
    def admin_lineup_page(event_id):
        return render_template(
            "admin/lineup.html",
            staff=g.staff,
            active_tab="events",
            event_id=event_id,
        )

    @app.get("/admin/events/<int:event_id>/edit/")
    @require_staff(admin=True, api=False)
    def admin_event_edit_page(event_id):
        return render_template(
            "admin/event_edit.html",
            staff=g.staff,
            active_tab="events",
            event_id=event_id,
        )

    @app.get("/admin/events/new/")
    @require_staff(admin=True, api=False)
    def admin_new_event_page():
        return render_template(
            "admin/event_edit.html",
            staff=g.staff,
            active_tab="events",
            event_id=None,
        )

    @app.get("/admin/events/<int:event_id>/standby/")
    @require_staff(moderator=True, api=False)
    def admin_standby_page(event_id):
        return render_template(
            "admin/standby.html",
            staff=g.staff,
            active_tab="events",
            event_id=event_id,
        )

    @app.get("/admin/profiles/")
    @require_staff(moderator=True, api=False)
    def admin_profiles_page():
        return render_template("admin/profiles.html", staff=g.staff, active_tab="profiles")

    @app.get("/admin/profiles/submissions/<int:draft_id>/")
    @require_staff(moderator=True, api=False)
    def admin_profile_submission_page(draft_id):
        return render_template(
            "admin/submission.html",
            staff=g.staff,
            active_tab="profiles",
            draft_id=draft_id,
        )

    register_admin_api_routes(app)


def register_admin_api_routes(app):
    @app.get("/api/v1/admin/dashboard")
    @require_staff(moderator=True)
    def admin_dashboard():
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM profile_submission_drafts WHERE status = 'pending'")
                pending_profiles = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT et.id, et.description, COUNT(e.id)
                    FROM event_types et
                    LEFT JOIN events e
                      ON e.type_id = et.id
                     AND e.event_date >= CURRENT_DATE
                    GROUP BY et.id, et.description
                    ORDER BY et.id
                    """
                )
                event_counts = [
                    {"type_id": row[0], "type_description": row[1], "count": row[2]}
                    for row in cursor.fetchall()
                ]
        return api_data({
            "pending_profile_submissions": pending_profiles,
            "event_counts": event_counts,
            "upcoming_events": sum(item["count"] for item in event_counts),
        })

    @app.get("/api/v1/admin/events")
    @require_staff(moderator=True)
    def admin_events():
        with connect() as connection:
            with connection.cursor() as cursor:
                events = workflow.get_upcoming_events(cursor)
        return api_data({"events": events})

    @app.get("/api/v1/admin/events/<int:event_id>")
    @require_staff(admin=True)
    def get_admin_event(event_id):
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT e.id, e.event_date, e.type_id, e.event_name, e.event_description, e.performance_slots,
                           e.starts_at, e.ends_at, e.timezone, e.location_id, l.name, l.address,
                           et.description
                    FROM events e
                    JOIN event_types et ON et.id = e.type_id
                    LEFT JOIN locations l ON l.id = e.location_id
                    WHERE e.id = %s
                    """,
                    (event_id,),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """
                        SELECT p.id, COALESCE(p.display_name, perf.performer_display_name), p.email, p.contact_phone
                        FROM performances perf
                        LEFT JOIN profiles p ON p.id = perf.profile_id
                        WHERE perf.event_id = %s
                        ORDER BY perf.sort_order, perf.id
                        """,
                        (event_id,),
                    )
                    performers = [
                        {"profile_id": item[0], "display_name": item[1], "email": item[2], "contact_phone": item[3]}
                        for item in cursor.fetchall()
                    ]
                else:
                    performers = []
        if not row:
            return api_error("not_found", "Event not found.", 404)
        return api_data({
            "event_id": row[0],
            "event_date": row[1].isoformat(),
            "type_id": row[2],
            "event_name": row[3],
            "event_description": row[4] or "",
            "performance_slots": row[5],
            "starts_at": row[6].isoformat() if row[6] else None,
            "ends_at": row[7].isoformat() if row[7] else None,
            "timezone": row[8],
            "location_id": row[9],
            "location_name": row[10] or "",
            "location_address": row[11] or "",
            "type_description": row[12],
            "performers": performers,
        })

    @app.get("/api/v1/admin/event-types")
    @require_staff(admin=True)
    def admin_event_types():
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, description FROM event_types ORDER BY id")
                types = [{"id": row[0], "description": row[1]} for row in cursor.fetchall()]
        return api_data({"event_types": types})

    @app.get("/api/v1/admin/locations")
    @require_staff(admin=True)
    def admin_locations():
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name, address FROM locations ORDER BY name, address, id")
                locations = [
                    {"id": row[0], "name": row[1], "address": row[2] or ""}
                    for row in cursor.fetchall()
                ]
        return api_data({"locations": locations})

    @app.post("/api/v1/admin/locations")
    @require_staff(admin=True)
    def create_admin_location():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        address = str(payload.get("address") or "").strip() or None
        if not name:
            return api_error("invalid_location", "Location name is required.")
        with connect() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        "INSERT INTO locations (name, address) VALUES (%s, %s) RETURNING id",
                        (name, address),
                    )
                    location_id = cursor.fetchone()[0]
                except Exception as exc:
                    if "locations_name_address_key" in str(exc):
                        return api_error("duplicate_location", "That location already exists.", 409)
                    raise
        return api_data({"location_id": location_id, "message": "Location saved."}, 201)

    @app.put("/api/v1/admin/locations/<int:location_id>")
    @require_staff(admin=True)
    def update_admin_location(location_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        address = str(payload.get("address") or "").strip() or None
        if not name:
            return api_error("invalid_location", "Location name is required.")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE locations SET name = %s, address = %s WHERE id = %s RETURNING id",
                    (name, address, location_id),
                )
                if not cursor.fetchone():
                    return api_error("not_found", "Location not found.", 404)
        return api_data({"message": "Location saved."})

    @app.delete("/api/v1/admin/locations/<int:location_id>")
    @require_staff(admin=True)
    def delete_admin_location(location_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM events WHERE location_id = %s", (location_id,))
                if cursor.fetchone()[0]:
                    return api_error("location_in_use", "This location is still assigned to one or more events.", 409)
                cursor.execute("DELETE FROM locations WHERE id = %s RETURNING id", (location_id,))
                if not cursor.fetchone():
                    return api_error("not_found", "Location not found.", 404)
        return make_response("", 204)

    @app.get("/api/v1/admin/profiles/search")
    @require_staff(admin=True)
    def search_admin_profiles():
        query = str(request.args.get("q") or "").strip()
        if len(query) < 2:
            return api_data({"profiles": []})
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, display_name, email, contact_phone
                    FROM profiles
                    WHERE display_name ILIKE %s OR email ILIKE %s
                    ORDER BY display_name, id
                    LIMIT 10
                    """,
                    (f"%{query}%", f"%{query}%"),
                )
                profiles = [
                    {"profile_id": item[0], "display_name": item[1], "email": item[2], "contact_phone": item[3]}
                    for item in cursor.fetchall()
                ]
        return api_data({"profiles": profiles})

    @app.put("/api/v1/admin/events/<int:event_id>/performers")
    @require_staff(admin=True)
    def update_admin_event_performers(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        profile_ids = payload.get("profile_ids")
        if not isinstance(profile_ids, list):
            return api_error("invalid_performers", "A profile_ids list is required.")
        try:
            profile_ids = [int(profile_id) for profile_id in profile_ids]
        except (TypeError, ValueError):
            return api_error("invalid_performers", "Profile IDs must be integers.")
        if len(profile_ids) != len(set(profile_ids)):
            return api_error("invalid_performers", "A performer cannot be listed twice.")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT type_id FROM events WHERE id = %s", (event_id,))
                event = cursor.fetchone()
                if not event:
                    return api_error("not_found", "Event not found.", 404)
                if event[0] != 2:
                    return api_error("invalid_event", "Performer lists are only available for type 2 events.")
                if profile_ids:
                    cursor.execute("SELECT id FROM profiles WHERE id = ANY(%s)", (profile_ids,))
                    found = {row[0] for row in cursor.fetchall()}
                    if found != set(profile_ids):
                        return api_error("invalid_performers", "One or more performers were not found.")
                cursor.execute("DELETE FROM performances WHERE event_id = %s AND profile_id IS NOT NULL", (event_id,))
                for sort_order, profile_id in enumerate(profile_ids):
                    cursor.execute(
                        """INSERT INTO performances (event_id, profile_id, performer_display_name, sort_order)
                           SELECT %s, id, display_name, %s FROM profiles WHERE id = %s""",
                        (event_id, sort_order, profile_id),
                    )
        return api_data({"message": "Performers saved."})

    @app.delete("/api/v1/admin/events/<int:event_id>")
    @require_staff(admin=True)
    def delete_admin_event(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT event_date FROM events WHERE id = %s", (event_id,))
                event = cursor.fetchone()
                if not event:
                    return api_error("not_found", "Event not found.", 404)
                if event[0] <= datetime.now(timezone.utc).date():
                    return api_error(
                        "past_event_delete_forbidden",
                        "Past events cannot be deleted from the admin interface.",
                        409,
                    )
                cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        return make_response("", 204)

    @app.put("/api/v1/admin/events/<int:event_id>")
    @require_staff(admin=True)
    def update_admin_event(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        event_date = str(payload.get("event_date") or "").strip()
        event_name = str(payload.get("event_name") or "").strip()
        event_description = str(payload.get("event_description") or "").strip()
        starts_at = str(payload.get("starts_at") or "").strip() or None
        ends_at = str(payload.get("ends_at") or "").strip() or None
        timezone_name = str(payload.get("timezone") or "Australia/Sydney").strip()
        location_id = payload.get("location_id") or None
        performance_slots = payload.get("performance_slots")
        try:
            from datetime import date
            date.fromisoformat(event_date)
            from datetime import datetime
            from zoneinfo import ZoneInfo
            event_timezone = ZoneInfo(timezone_name)
            if starts_at:
                starts_at = datetime.fromisoformat(starts_at)
                if starts_at.tzinfo is None:
                    starts_at = starts_at.replace(tzinfo=event_timezone)
            if ends_at:
                ends_at = datetime.fromisoformat(ends_at)
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=event_timezone)
            type_id = int(payload.get("type_id"))
            performance_slots = int(performance_slots)
            if type_id not in (1, 2) or performance_slots <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return api_error("invalid_event", "Date, event type, and a positive number of performance slots are required.")
        if not event_name:
            return api_error("invalid_event", "Event name is required.")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM event_performer_selections
                    WHERE event_id = %s AND status = %s
                    """,
                    (event_id, workflow.LINEUP_STATUS_SELECTED),
                )
                if cursor.fetchone()[0] > performance_slots:
                    return api_error(
                        "invalid_event",
                        "Performance slots cannot be lower than the current number of selected performers.",
                    )
                cursor.execute(
                    """
                    UPDATE events
                    SET event_date = %s, type_id = %s, event_name = %s,
                        event_description = %s, performance_slots = %s,
                        starts_at = %s, ends_at = %s, timezone = %s, location_id = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (event_date, type_id, event_name, event_description, performance_slots,
                     starts_at, ends_at, timezone_name, location_id, event_id),
                )
                if not cursor.fetchone():
                    return api_error("not_found", "Event not found.", 404)
        return api_data({"message": "Event saved."})

    @app.post("/api/v1/admin/events")
    @require_staff(admin=True)
    def create_admin_event():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        event_date = str(payload.get("event_date") or "").strip()
        event_name = str(payload.get("event_name") or "").strip()
        event_description = str(payload.get("event_description") or "").strip()
        starts_at = str(payload.get("starts_at") or "").strip() or None
        ends_at = str(payload.get("ends_at") or "").strip() or None
        timezone_name = str(payload.get("timezone") or "Australia/Sydney").strip()
        location_id = payload.get("location_id") or None
        performance_slots = payload.get("performance_slots")
        try:
            from datetime import date
            date.fromisoformat(event_date)
            from datetime import datetime
            from zoneinfo import ZoneInfo
            event_timezone = ZoneInfo(timezone_name)
            if starts_at:
                starts_at = datetime.fromisoformat(starts_at)
                if starts_at.tzinfo is None:
                    starts_at = starts_at.replace(tzinfo=event_timezone)
            if ends_at:
                ends_at = datetime.fromisoformat(ends_at)
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=event_timezone)
            type_id = int(payload.get("type_id"))
            performance_slots = int(performance_slots)
            if type_id not in (1, 2) or performance_slots <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return api_error("invalid_event", "Date, event type, and a positive number of performance slots are required.")
        if not event_name:
            return api_error("invalid_event", "Event name is required.")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO events (event_date, type_id, event_name, event_description, performance_slots,
                                        starts_at, ends_at, timezone, location_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (event_date, type_id, event_name, event_description, performance_slots,
                     starts_at, ends_at, timezone_name, location_id),
                )
                event_id = cursor.fetchone()[0]
        return api_data({"event_id": event_id, "message": "Event saved."}, 201)

    @app.get("/api/v1/admin/events/<int:event_id>/lineup")
    @require_staff(admin=True)
    def admin_event_lineup(event_id):
        with connect() as connection:
            with connection.cursor() as cursor:
                event = workflow.get_event_selection_context(cursor, event_id)
                candidates = workflow.get_lineup_selection_candidates(cursor, event_id)
        return api_data({"event": event, "candidates": candidates})

    @app.put("/api/v1/admin/events/<int:event_id>/lineup")
    @require_staff(admin=True)
    def save_admin_event_lineup(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        statuses = payload.get("statuses")
        if not isinstance(statuses, dict):
            return api_error("invalid_lineup", "A statuses object is required.")
        try:
            parsed_statuses = {int(key): str(value) for key, value in statuses.items()}
            allowed_statuses = {
                workflow.LINEUP_STATUS_REQUESTED,
                workflow.LINEUP_STATUS_AVAILABILITY_CONFIRMED,
                workflow.LINEUP_STATUS_SELECTED,
                workflow.LINEUP_STATUS_STANDBY,
                workflow.LINEUP_STATUS_RESERVE,
            }
            if any(value not in allowed_statuses for value in parsed_statuses.values()):
                raise ValueError("One or more lineup statuses are invalid.")
            with connect() as connection:
                with connection.cursor() as cursor:
                    lock = workflow.acquire_lineup_selection_lock(
                        cursor,
                        event_id=event_id,
                        profile_id=g.staff["profile_id"],
                        lock_minutes=workflow.get_lineup_selection_lock_minutes(),
                    )
                    if not lock["acquired"]:
                        return api_error(
                            "lineup_locked",
                            "Another administrator is editing this lineup.",
                            409,
                        )
                    event = workflow.get_event_selection_context(cursor, event_id)
                    candidates = workflow.get_lineup_selection_candidates(cursor, event_id)
                    newly_selected = [
                        item["requested_date_id"]
                        for item in candidates
                        if parsed_statuses.get(item["requested_date_id"]) == workflow.LINEUP_STATUS_SELECTED
                        and item.get("selection_status") != workflow.LINEUP_STATUS_SELECTED
                    ]
                    workflow.save_lineup_selection(
                        cursor,
                        event_id=event_id,
                        admin_profile_id=g.staff["profile_id"],
                        candidates=candidates,
                        candidate_statuses=parsed_statuses,
                        performance_slots=event["performance_slots"],
                    )
                    workflow.release_lineup_selection_lock(
                        cursor,
                        event_id=event_id,
                        profile_id=g.staff["profile_id"],
                    )
            if payload.get("notify", True) is False:
                return api_data({"message": "Lineup saved without notifying performers."})

            if payload.get("progress") is True:
                selected_request_ids = set(newly_selected)

                @stream_with_context
                def notification_progress():
                    for candidate in candidates:
                        if candidate["requested_date_id"] not in selected_request_ids:
                            continue
                        try:
                            workflow.send_selected_performer_email(event, candidate)
                        except Exception:
                            app.logger.exception("Selected performer notification failed")
                            yield json.dumps({"type": "error", "email": candidate["email"]}) + "\n"
                            return
                        yield json.dumps({"type": "sent", "email": candidate["email"]}) + "\n"
                    yield json.dumps({"type": "complete", "message": "Lineup saved."}) + "\n"

                return Response(
                    notification_progress(),
                    mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            workflow.send_selected_performer_emails(event, candidates, newly_selected)
            return api_data({"message": "Lineup saved."})
        except (TypeError, ValueError) as exc:
            return api_error("invalid_lineup", str(exc))

    @app.post("/api/v1/admin/events/<int:event_id>/lineup/preview")
    @require_staff(admin=True)
    def preview_admin_event_lineup(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        statuses = payload.get("statuses")
        if not isinstance(statuses, dict):
            return api_error("invalid_lineup", "A statuses object is required.")
        try:
            parsed_statuses = {int(key): str(value) for key, value in statuses.items()}
            if any(value not in {
                workflow.LINEUP_STATUS_REQUESTED,
                workflow.LINEUP_STATUS_AVAILABILITY_CONFIRMED,
                workflow.LINEUP_STATUS_SELECTED,
                workflow.LINEUP_STATUS_STANDBY,
                workflow.LINEUP_STATUS_RESERVE,
            } for value in parsed_statuses.values()):
                raise ValueError("One or more lineup statuses are invalid.")
        except (TypeError, ValueError) as exc:
            return api_error("invalid_lineup", str(exc))
        with connect() as connection:
            with connection.cursor() as cursor:
                candidates = workflow.get_lineup_selection_candidates(cursor, event_id)
        recipients = [
            {"display_name": item["display_name"], "email": item["email"]}
            for item in candidates
            if parsed_statuses.get(item["requested_date_id"]) == workflow.LINEUP_STATUS_SELECTED
            and workflow.is_lineup_selection_candidate_eligible(item)
            and item.get("selection_status") != workflow.LINEUP_STATUS_SELECTED
        ]
        unselected_emails = [
            item["email"]
            for item in candidates
            if item.get("email")
            and parsed_statuses.get(item["requested_date_id"]) != workflow.LINEUP_STATUS_SELECTED
        ]
        return api_data({"recipients": recipients, "unselected_emails": unselected_emails})

    @app.post("/api/v1/admin/events/<int:event_id>/lineup/lock")
    @require_staff(admin=True)
    def acquire_lineup_lock(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        with connect() as connection:
            with connection.cursor() as cursor:
                lock = workflow.acquire_lineup_selection_lock(
                    cursor,
                    event_id=event_id,
                    profile_id=g.staff["profile_id"],
                    lock_minutes=workflow.get_lineup_selection_lock_minutes(),
                )
        if not lock["acquired"]:
            return api_error("lineup_locked", "Another administrator is editing this lineup.", 409)
        return api_data({"locked_by": lock["locked_by_name"], "expires_at": lock["lock_expires_at"].isoformat()})

    @app.delete("/api/v1/admin/events/<int:event_id>/lineup/lock")
    @require_staff(admin=True)
    def release_lineup_lock(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        with connect() as connection:
            with connection.cursor() as cursor:
                workflow.release_lineup_selection_lock(
                    cursor, event_id=event_id, profile_id=g.staff["profile_id"]
                )
        return "", 204

    @app.post(
        "/api/v1/admin/events/<int:event_id>/performer-requests/"
        "<int:requested_date_id>/availability-reminders"
    )
    @require_staff(admin=True)
    def resend_availability(event_id, requested_date_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        try:
            payload = request.get_json(silent=True) or {}
            message = workflow.normalize_text(payload.get("message"))
            with connect() as connection:
                with connection.cursor() as cursor:
                    sent = workflow.send_availability_confirmation_for_requested_date(
                        app, cursor, requested_date_id=requested_date_id, event_id=event_id, message=message
                    )
            return api_data(
                {
                    "message": f"Availability reminder sent to {sent['display_name']}.",
                    "availability_email_sent_at_epoch": sent["availability_email_sent_at_epoch"],
                },
                201,
            )
        except ValueError as exc:
            return api_error("availability_reminder_failed", str(exc))

    @app.post(
        "/api/v1/admin/events/<int:event_id>/performer-requests/"
        "<int:requested_date_id>/lineup-status-notifications"
    )
    @require_staff(admin=True)
    def send_lineup_status_notification(event_id, requested_date_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        try:
            payload = request.get_json(silent=True) or {}
            status = payload.get("status")
            message = workflow.normalize_text(payload.get("message"))
            with connect() as connection:
                with connection.cursor() as cursor:
                    event = workflow.get_event_selection_context(cursor, event_id)
                    candidates = workflow.get_lineup_selection_candidates(cursor, event_id)
                    candidate = next(
                        (item for item in candidates if item["requested_date_id"] == requested_date_id),
                        None,
                    )
                    if not candidate:
                        raise ValueError("That performer request is not available for this event.")
                    sent = workflow.send_lineup_status_notification(
                        event,
                        candidate,
                        status=status,
                        message=message,
                    )
            return api_data({"message": f"Lineup status sent to {sent['display_name']}."}, 201)
        except ValueError as exc:
            return api_error("lineup_status_notification_failed", str(exc))

    @app.delete(
        "/api/v1/admin/events/<int:event_id>/performer-requests/<int:requested_date_id>"
    )
    @require_staff(admin=True)
    def remove_cancelled_performer_request(event_id, requested_date_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    workflow.remove_cancelled_lineup_candidate(
                        cursor, event_id=event_id, requested_date_id=requested_date_id
                    )
            return api_data({"message": "Cancelled performer removed from the lineup list."})
        except ValueError as exc:
            return api_error("performer_request_removal_failed", str(exc))

    @app.get("/api/v1/admin/events/<int:event_id>/standby")
    @require_staff(moderator=True)
    def admin_event_standby(event_id):
        with connect() as connection:
            with connection.cursor() as cursor:
                event = workflow.get_event_selection_context(cursor, event_id)
                current = workflow.get_current_selected_lineup(cursor, event_id)
                candidates = workflow.get_backup_candidates(cursor, event_id)
        return api_data({"event": event, "current_lineup": current, "candidates": candidates})

    @app.post("/api/v1/admin/events/<int:event_id>/lineup/promotions")
    @require_staff(moderator=True)
    def promote_standby(event_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        try:
            requested_date_id = int(payload.get("requested_date_id"))
            with connect() as connection:
                with connection.cursor() as cursor:
                    event = workflow.get_event_selection_context(cursor, event_id)
                    promoted = workflow.promote_backup_selection(
                        cursor,
                        event_id=event_id,
                        requested_date_id=requested_date_id,
                        admin_profile_id=g.staff["profile_id"],
                    )
                    links = workflow.create_availability_action_links(
                        app=app,
                        cursor=cursor,
                        requested_date_id=requested_date_id,
                        event_id=event_id,
                        ttl_hours=workflow.get_workflow_settings(cursor)["action_token_ttl_hours"],
                    )
                workflow.send_backup_promoted_email(event, promoted, links)
            return api_data({"promoted": promoted}, 201)
        except (TypeError, ValueError) as exc:
            return api_error("promotion_failed", str(exc))

    @app.get("/api/v1/admin/events/<int:event_id>/performer/<int:position>/name")
    # @require_staff(admin=True) # Should probably require this at some point
    def get_perfomer_subtitle_name(event_id, position):
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT e.id, e.event_date, e.type_id, e.event_name, e.event_description,
                        et.description
                    FROM events e
                    JOIN event_types et ON et.id = e.type_id
                    WHERE e.id = %s
                    """,
                    (event_id,),
                )
                row = cursor.fetchone()
                if row:
                    _ = cursor.execute(
                        """
                        SELECT COALESCE(profiles.display_name, performances.performer_display_name), profile_social_profiles.profile_name,
                            REPLACE(social_platforms.url_format, '{profileName}', profile_social_profiles.profile_name) AS social_link
                        FROM performances
                        LEFT JOIN profiles ON profiles.id = performances.profile_id
                        LEFT JOIN profile_social_profiles ON profiles.id = profile_social_profiles.profile_id
                        LEFT JOIN social_platforms ON profile_social_profiles.social_platform_id = social_platforms.id
                        WHERE performances.event_id = %s AND performances.id = %s
                        -- LIMIT 2 -- should limit it but this doesn't let us pick which two
                        """,
                        (event_id, position),
                    )
                    performer = cursor.fetchall();
                    if not performer:
                        return None
                    return render_template(
                        "admin/subtitle-performer.html",
                        name=performer[0][0],
                        social1=performer[0][2],
                        social2=performer[1][2]
                    )
                else:
                    return api_error("not_found", "Event not found.", 404)

    @app.get("/api/v1/admin/profiles/submissions")
    @require_staff(moderator=True)
    def admin_profile_submissions():
        status = request.args.get("status", "pending")
        if status not in {"pending", "approved", "denied", "superseded"}:
            return api_error("invalid_status", "Unknown submission status.")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, display_name, email, submitted_at, status
                    FROM profile_submission_drafts
                    WHERE status = %s
                    ORDER BY submitted_at DESC, id DESC
                    """,
                    (status,),
                )
                submissions = [
                    {
                        "id": row[0],
                        "display_name": row[1],
                        "email": row[2],
                        "submitted_at": row[3].isoformat(),
                        "status": row[4],
                    }
                    for row in cursor.fetchall()
                ]
        return api_data({"submissions": submissions})

    @app.get("/api/v1/admin/profiles/submissions/<int:draft_id>")
    @require_staff(moderator=True)
    def admin_profile_submission(draft_id):
        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    draft = workflow.get_profile_submission_draft(
                        cursor,
                        draft_id,
                        include_date_summary=True,
                    )
            return api_data({"submission": draft})
        except ValueError as exc:
            return api_error("submission_not_found", str(exc), 404)

    @app.post("/api/v1/admin/profiles/submissions/<int:draft_id>/decisions")
    @require_staff(moderator=True)
    def decide_profile_submission(draft_id):
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        payload = request.get_json(silent=True) or {}
        decision = payload.get("decision")
        reason = str(payload.get("message") or payload.get("reason") or "").strip() or None
        if decision not in {"approved", "denied"}:
            return api_error("invalid_decision", "Decision must be approved or denied.")
        if not reason:
            return api_error("message_required", "An include message is required.")
        try:
            edit_link = None
            with connect() as connection:
                with connection.cursor() as cursor:
                    draft = workflow.get_profile_submission_draft(cursor, draft_id)
                    if draft["status"] != workflow.WORKFLOW_STATUS_PENDING:
                        raise ValueError("This submission has already been reviewed.")
                    requested_date_ids = payload.get("requested_date_ids", draft.get("requested_date_ids", []))
                    if not isinstance(requested_date_ids, list) or any(not isinstance(value, int) for value in requested_date_ids):
                        raise ValueError("Requested dates are invalid.")
                    requested_date_ids = set(requested_date_ids)
                    all_requested_date_ids = {item["requested_date_id"] for item in draft["requested_events"]}
                    if not requested_date_ids.issubset(all_requested_date_ids):
                        raise ValueError("Requested dates are invalid.")
                    cursor.execute(
                        "UPDATE requested_dates SET status = 'withdrawn' WHERE draft_id = %s AND id <> ALL(%s)",
                        (draft_id, list(requested_date_ids)),
                    )
                    draft["requested_events"] = [item for item in draft["requested_events"] if item["requested_date_id"] in requested_date_ids]
                    draft["requested_event_ids"] = [item["event_id"] for item in draft["requested_events"]]
                    if decision == "approved":
                        profile_id = workflow.apply_approved_draft(cursor, draft, g.staff["profile_id"])
                        workflow.attach_profile_to_draft(cursor, draft_id=draft_id, profile_id=profile_id)
                    elif payload.get("include_edit_link", True):
                        edit_link = workflow.create_profile_submission_access_link(
                            cursor=cursor,
                            app=app,
                            email=draft["email"],
                            ttl_hours=workflow.get_workflow_settings(cursor)["action_token_ttl_hours"],
                        )
                    workflow.record_moderation_action(
                        cursor,
                        draft_id=draft_id,
                        moderator_profile_id=g.staff["profile_id"],
                        action=decision,
                        reason=reason,
                    )
                    workflow.finalize_draft_status(
                        cursor,
                        draft_id=draft_id,
                        status=decision,
                        reviewer_profile_id=g.staff["profile_id"],
                        denial_reason=reason,
                    )
                    settings = workflow.get_workflow_settings(cursor)
                if decision == "approved":
                    workflow.send_profile_approved_email(
                        app,
                        draft["email"],
                        requested_events=draft["requested_events"],
                        message=reason,
                        availability_confirmation_lead_days=settings["availability_confirmation_lead_days"],
                        lineup_selection_lead_days=settings["lineup_selection_lead_days"],
                    )
                else:
                    workflow.send_profile_denied_email(app, draft["email"], reason, edit_link=edit_link)
            return api_data({"decision": decision}, 201)
        except ValueError as exc:
            return api_error("decision_failed", str(exc))
