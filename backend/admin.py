import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote

from flask import g, jsonify, make_response, redirect, render_template, request

from backend.db import connect
from backend.mailer import send_mail
import backend.performer_workflow as workflow


STAFF_LOGIN_ACTION = "staff_login"
SESSION_COOKIE = "emom_staff_session"
CSRF_COOKIE = "emom_staff_csrf"


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
    if not value.startswith("/admin/") or value.startswith("//"):
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

    @app.get("/admin/events/<int:event_id>/lineup/")
    @require_staff(admin=True, api=False)
    def admin_lineup_page(event_id):
        return render_template(
            "admin/lineup.html",
            staff=g.staff,
            active_tab="events",
            event_id=event_id,
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
                    "SELECT COUNT(*) FROM events WHERE event_date >= CURRENT_DATE AND type_id = %s",
                    (workflow.OPEN_MIC_EVENT_TYPE_ID,),
                )
                upcoming_events = cursor.fetchone()[0]
        return api_data({"pending_profile_submissions": pending_profiles, "upcoming_events": upcoming_events})

    @app.get("/api/v1/admin/events")
    @require_staff(moderator=True)
    def admin_events():
        with connect() as connection:
            with connection.cursor() as cursor:
                events = workflow.get_upcoming_open_mic_events(cursor)
        return api_data({"events": events})

    @app.get("/api/v1/admin/events/<int:event_id>/lineup")
    @require_staff(admin=True)
    def admin_event_lineup(event_id):
        with connect() as connection:
            with connection.cursor() as cursor:
                event = workflow.get_event_selection_context(cursor, event_id)
                candidates = workflow.get_lineup_selection_candidates(cursor, event_id)
                max_performers = workflow.get_workflow_settings(cursor)["max_performers_per_event"]
        return api_data({"event": event, "candidates": candidates, "max_performers": max_performers})

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
                        max_performers=workflow.get_workflow_settings(cursor)["max_performers_per_event"],
                    )
                    workflow.release_lineup_selection_lock(
                        cursor,
                        event_id=event_id,
                        profile_id=g.staff["profile_id"],
                    )
                workflow.send_selected_performer_emails(event, candidates, newly_selected)
            return api_data({"message": "Lineup saved."})
        except (TypeError, ValueError) as exc:
            return api_error("invalid_lineup", str(exc))

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
            with connect() as connection:
                with connection.cursor() as cursor:
                    sent = workflow.send_availability_confirmation_for_requested_date(
                        app, cursor, requested_date_id=requested_date_id, event_id=event_id
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
                    sent = workflow.send_lineup_status_notification(event, candidate, status=status)
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
                    draft = workflow.get_profile_submission_draft(cursor, draft_id)
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
        reason = str(payload.get("reason") or "").strip() or None
        if decision not in {"approved", "denied"}:
            return api_error("invalid_decision", "Decision must be approved or denied.")
        if decision == "denied" and not reason:
            return api_error("reason_required", "A denial reason is required.")
        try:
            edit_link = None
            with connect() as connection:
                with connection.cursor() as cursor:
                    draft = workflow.get_profile_submission_draft(cursor, draft_id)
                    if draft["status"] != workflow.WORKFLOW_STATUS_PENDING:
                        raise ValueError("This submission has already been reviewed.")
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
                        availability_confirmation_lead_days=settings["availability_confirmation_lead_days"],
                        lineup_selection_lead_days=settings["lineup_selection_lead_days"],
                    )
                else:
                    workflow.send_profile_denied_email(app, draft["email"], reason, edit_link=edit_link)
            return api_data({"decision": decision}, 201)
        except ValueError as exc:
            return api_error("decision_failed", str(exc))
