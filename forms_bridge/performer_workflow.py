import hashlib
import html
import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate
from email.utils import make_msgid

from flask import jsonify, request

from forms_bridge.db import connect


ACTION_TYPE_REGISTRATION_LINK = "registration_link"
ACTION_TYPE_MODERATION_APPROVE = "moderation_approve"
ACTION_TYPE_MODERATION_DENY = "moderation_deny"
ACTION_TYPE_AVAILABILITY_CONFIRM = "availability_confirm"
ACTION_TYPE_AVAILABILITY_CANCEL = "availability_cancel"

WORKFLOW_STATUS_PENDING = "pending"
WORKFLOW_STATUS_APPROVED = "approved"
WORKFLOW_STATUS_DENIED = "denied"
OPEN_MIC_EVENT_TYPE_ID = 1


def register_performer_workflow_routes(app):
    @app.route("/api/forms/performer-registration/start", methods=["OPTIONS"])
    def performer_registration_start_options():
        return ("", 204)

    @app.route("/api/forms/performer-registration/start", methods=["POST"])
    def start_performer_registration():
        try:
            payload = get_json_payload()
            email = normalize_email(payload.get("email"))
            if not email:
                return error_response("A valid email address is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    settings = get_workflow_settings(cursor)
                    invalidate_unused_tokens(cursor, email=email, action_type=ACTION_TYPE_REGISTRATION_LINK)
                    raw_token, token_hash = generate_token_pair()
                    expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])

                    cursor.execute(
                        """
                        INSERT INTO action_tokens (token_hash, action_type, email, expires_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (token_hash, ACTION_TYPE_REGISTRATION_LINK, email, expires_at),
                    )

                send_registration_email(app, email, raw_token, expires_at)

            return jsonify({"ok": True}), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Performer registration start failed")
            return error_response("Unable to start performer registration right now.", 500)

    @app.route("/api/forms/performer-registration/session", methods=["GET"])
    def get_performer_registration_session():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return error_response("A registration token is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_REGISTRATION_LINK)
                    email = token_row["email"]
                    settings = get_workflow_settings(cursor)
                    profile = get_existing_profile_by_email(cursor, email)
                    available_events = get_available_events(cursor, profile["id"] if profile else None, settings)
                    social_platforms = get_social_platforms(cursor)

            return jsonify(
                {
                    "ok": True,
                    "email": email,
                    "profile": serialize_profile(profile),
                    "social_platforms": social_platforms,
                    "available_events": available_events,
                    "cooldown_events": settings["performer_request_cooldown_events"],
                }
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Performer registration session lookup failed")
            return error_response("Unable to load performer registration right now.", 500)

    @app.route("/api/forms/performer-registration/submit", methods=["OPTIONS"])
    def performer_registration_submit_options():
        return ("", 204)

    @app.route("/api/forms/performer-registration/submit", methods=["POST"])
    def submit_performer_registration():
        try:
            payload = get_json_payload()
            raw_token = normalize_text(payload.get("token"))
            if not raw_token:
                return error_response("A registration token is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_REGISTRATION_LINK)
                    email = token_row["email"]
                    settings = get_workflow_settings(cursor)
                    draft_payload = normalize_profile_submission_payload(payload, email)
                    profile, matched_by = get_existing_profile_for_submission(
                        cursor,
                        email=email,
                        display_name=draft_payload["display_name"],
                    )
                    available_events = get_available_events(cursor, profile["id"] if profile else None, settings)
                    available_event_ids = {event["id"] for event in available_events}
                    ensure_requested_events_are_allowed(draft_payload["requested_event_ids"], available_event_ids)
                    ensure_social_platforms_exist(
                        cursor, [item["social_platform_id"] for item in draft_payload["social_links"]]
                    )

                    supersede_pending_drafts(cursor, profile["id"] if profile else None, email)
                    draft_id = insert_profile_submission_draft(
                        cursor=cursor,
                        profile=profile,
                        email=email,
                        draft_payload=draft_payload,
                    )

                    insert_profile_submission_social_links(cursor, draft_id, draft_payload["social_links"])
                    insert_requested_dates(cursor, draft_id, draft_payload["requested_event_ids"])

                    moderator_emails = get_moderator_emails(cursor)
                    if not moderator_emails:
                        raise ValueError("No moderator email addresses are configured yet.")

                    moderation_links = create_moderation_links(
                        cursor=cursor,
                        app=app,
                        draft_id=draft_id,
                        moderator_emails=moderator_emails,
                        ttl_hours=settings["action_token_ttl_hours"],
                    )
                    mark_action_token_used(cursor, token_row["id"])

                send_moderation_emails(
                    app=app,
                    draft_id=draft_id,
                    email=email,
                    draft_payload=draft_payload,
                    existing_profile=profile,
                    matched_by=matched_by,
                    moderation_links=moderation_links,
                )

            return jsonify({"ok": True, "draft_id": draft_id}), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Performer registration submission failed")
            return error_response("Unable to submit performer registration right now.", 500)

    @app.route("/api/forms/performer-registration/moderation/approve", methods=["GET"])
    def approve_profile_submission():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return html_error_page("Missing moderation token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_MODERATION_APPROVE)
                    draft = get_profile_submission_draft(cursor, token_row["draft_id"])
                    if draft["status"] != WORKFLOW_STATUS_PENDING:
                        raise ValueError("This submission has already been reviewed.")

                    profile_id = apply_approved_draft(cursor, draft, token_row["profile_id"])
                    record_moderation_action(
                        cursor,
                        draft_id=draft["id"],
                        moderator_profile_id=token_row["profile_id"],
                        action=WORKFLOW_STATUS_APPROVED,
                        reason=None,
                    )
                    finalize_draft_status(
                        cursor,
                        draft_id=draft["id"],
                        status=WORKFLOW_STATUS_APPROVED,
                        reviewer_profile_id=token_row["profile_id"],
                        denial_reason=None,
                    )
                    invalidate_moderation_tokens_for_draft(cursor, draft["id"])

                send_profile_approved_email(app, draft["email"])

            return html_success_page(
                "Profile approved",
                f"Draft #{draft['id']} has been approved and the artist has been notified.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Profile approval failed")
            return html_error_page("Unable to approve this submission right now.", 500)

    @app.route("/api/forms/performer-registration/moderation/deny", methods=["GET", "POST"])
    def deny_profile_submission():
        if request.method == "GET":
            raw_token = normalize_text(request.args.get("token"))
            if not raw_token:
                return html_error_page("Missing moderation token.", 400)
            try:
                with connect() as connection:
                    with connection.cursor() as cursor:
                        token_row = get_action_token(cursor, raw_token, ACTION_TYPE_MODERATION_DENY)
                        draft = get_profile_submission_draft(cursor, token_row["draft_id"])
                        if draft["status"] != WORKFLOW_STATUS_PENDING:
                            raise ValueError("This submission has already been reviewed.")

                return render_denial_form(raw_token)
            except ValueError as exc:
                return html_error_page(str(exc), 400)
            except Exception:
                app.logger.exception("Profile denial form lookup failed")
                return html_error_page("Unable to load this moderation action right now.", 500)

        raw_token = normalize_text(request.form.get("token"))
        denial_reason = normalize_text(request.form.get("reason"))
        if not raw_token:
            return html_error_page("Missing moderation token.", 400)
        if not denial_reason:
            return html_error_page("A denial reason is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_MODERATION_DENY)
                    draft = get_profile_submission_draft(cursor, token_row["draft_id"])
                    if draft["status"] != WORKFLOW_STATUS_PENDING:
                        raise ValueError("This submission has already been reviewed.")

                    record_moderation_action(
                        cursor,
                        draft_id=draft["id"],
                        moderator_profile_id=token_row["profile_id"],
                        action=WORKFLOW_STATUS_DENIED,
                        reason=denial_reason,
                    )
                    finalize_draft_status(
                        cursor,
                        draft_id=draft["id"],
                        status=WORKFLOW_STATUS_DENIED,
                        reviewer_profile_id=token_row["profile_id"],
                        denial_reason=denial_reason,
                    )
                    invalidate_moderation_tokens_for_draft(cursor, draft["id"])

                send_profile_denied_email(app, draft["email"], denial_reason)

            return html_success_page(
                "Profile denied",
                f"Draft #{draft['id']} has been denied and the artist has been notified.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Profile denial failed")
            return html_error_page("Unable to deny this submission right now.", 500)

    @app.route("/api/forms/performer-registration/availability/confirm", methods=["GET"])
    def confirm_requested_date():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return html_error_page("Missing availability token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_AVAILABILITY_CONFIRM)
                    requested_date = get_requested_date_with_context(cursor, token_row["requested_date_id"])
                    ensure_requested_date_is_actionable(requested_date)
                    update_requested_date_availability_status(
                        cursor,
                        requested_date_id=requested_date["id"],
                        status="availability_confirmed",
                    )
                    invalidate_availability_tokens_for_requested_date(cursor, requested_date["id"])

            return html_success_page(
                "Availability confirmed",
                f"Thanks. Your availability for {requested_date['event_name']} on {requested_date['event_date']} is confirmed.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Availability confirmation failed")
            return html_error_page("Unable to confirm availability right now.", 500)

    @app.route("/api/forms/performer-registration/availability/cancel", methods=["GET"])
    def cancel_requested_date():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return html_error_page("Missing availability token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_AVAILABILITY_CANCEL)
                    requested_date = get_requested_date_with_context(cursor, token_row["requested_date_id"])
                    ensure_requested_date_is_actionable(requested_date)
                    update_requested_date_availability_status(
                        cursor,
                        requested_date_id=requested_date["id"],
                        status="availability_cancelled",
                    )
                    invalidate_availability_tokens_for_requested_date(cursor, requested_date["id"])

            return html_success_page(
                "Availability cancelled",
                f"Your availability for {requested_date['event_name']} on {requested_date['event_date']} has been cancelled.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Availability cancellation failed")
            return html_error_page("Unable to cancel availability right now.", 500)


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
    if not email or "@" not in email or "." not in email:
        return None
    return email.lower()


def normalize_boolean(value, *, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("Boolean fields must be true or false.")


def normalize_profile_submission_payload(payload, email):
    profile_type = normalize_text(payload.get("profile_type"))
    display_name = normalize_text(payload.get("display_name"))
    first_name = normalize_text(payload.get("first_name"))
    last_name = normalize_text(payload.get("last_name"))
    contact_phone = normalize_text(payload.get("contact_phone"))
    artist_bio = normalize_text(payload.get("artist_bio"))
    social_links = payload.get("social_links") or []
    requested_event_ids = payload.get("requested_event_ids") or []

    if profile_type not in {"person", "group"}:
        raise ValueError("Profile type must be either 'person' or 'group'.")

    if not display_name:
        raise ValueError("A display name is required.")

    if not contact_phone:
        raise ValueError("A contact phone number is required.")

    if not isinstance(requested_event_ids, list) or not requested_event_ids:
        raise ValueError("At least one requested event date is required.")

    normalized_event_ids = []
    for event_id in requested_event_ids:
        if not isinstance(event_id, int):
            raise ValueError("Requested event ids must be integers.")
        if event_id not in normalized_event_ids:
            normalized_event_ids.append(event_id)

    if not isinstance(social_links, list):
        raise ValueError("Social links must be an array.")

    normalized_social_links = []
    for item in social_links:
        if not isinstance(item, dict):
            raise ValueError("Each social link must be an object.")

        social_platform_id = item.get("social_platform_id")
        profile_name = normalize_text(item.get("profile_name"))
        if social_platform_id is None and not profile_name:
            continue
        if not isinstance(social_platform_id, int):
            raise ValueError("Each social link must include an integer social_platform_id.")
        if not profile_name:
            raise ValueError("Each social link must include a profile name.")

        normalized_social_links.append(
            {
                "social_platform_id": social_platform_id,
                "profile_name": profile_name,
            }
        )

    return {
        "email": email,
        "profile_type": profile_type,
        "display_name": display_name,
        "first_name": first_name,
        "last_name": last_name,
        "contact_phone": contact_phone,
        "is_email_public": normalize_boolean(payload.get("is_email_public"), default=False),
        "is_name_public": normalize_boolean(payload.get("is_name_public"), default=False),
        "artist_bio": artist_bio,
        "is_artist_bio_public": normalize_boolean(payload.get("is_artist_bio_public"), default=False),
        "social_links": normalized_social_links,
        "requested_event_ids": normalized_event_ids,
    }


def now_utc():
    return datetime.now(timezone.utc)


def get_workflow_settings(cursor):
    cursor.execute(
        """
        SELECT key, value_json
        FROM app_settings
        WHERE key = ANY(%s)
        """,
        (
            [
                "performer_request_cooldown_events",
                "availability_confirmation_lead_days",
                "final_selection_lead_days",
                "action_token_ttl_hours",
                "max_performers_per_event",
            ],
        ),
    )
    settings = {
        "performer_request_cooldown_events": 3,
        "availability_confirmation_lead_days": 10,
        "final_selection_lead_days": 7,
        "action_token_ttl_hours": 24,
        "max_performers_per_event": 7,
    }
    for key, value_json in cursor.fetchall():
        value = value_json if not isinstance(value_json, str) else json.loads(value_json)
        settings[key] = int(value)
    return settings


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token_pair():
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


def get_action_token(cursor, raw_token, action_type):
    token_hash = hash_token(raw_token)
    cursor.execute(
        """
        SELECT id, action_type, email, profile_id, draft_id, event_id, expires_at, used_at
        FROM action_tokens
        WHERE token_hash = %s
          AND action_type = %s
        """,
        (token_hash, action_type),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That link is invalid.")

    token = {
        "id": row[0],
        "action_type": row[1],
        "email": row[2],
        "profile_id": row[3],
        "draft_id": row[4],
        "event_id": row[5],
        "expires_at": row[6],
        "used_at": row[7],
    }
    if token["used_at"] is not None:
        raise ValueError("That link has already been used.")
    if token["expires_at"] <= now_utc():
        raise ValueError("That link has expired.")
    return token


def mark_action_token_used(cursor, token_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE id = %s
        """,
        (token_id,),
    )


def invalidate_unused_tokens(cursor, *, email=None, draft_id=None, action_type=None):
    conditions = ["used_at IS NULL"]
    values = []
    if email is not None:
        conditions.append("email = %s")
        values.append(email)
    if draft_id is not None:
        conditions.append("draft_id = %s")
        values.append(draft_id)
    if action_type is not None:
        conditions.append("action_type = %s")
        values.append(action_type)

    cursor.execute(
        f"""
        UPDATE action_tokens
        SET used_at = now()
        WHERE {' AND '.join(conditions)}
        """,
        tuple(values),
    )


def invalidate_moderation_tokens_for_draft(cursor, draft_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE draft_id = %s
          AND action_type IN (%s, %s)
          AND used_at IS NULL
        """,
        (draft_id, ACTION_TYPE_MODERATION_APPROVE, ACTION_TYPE_MODERATION_DENY),
    )


def get_existing_profile_by_email(cursor, email):
    cursor.execute(
        """
        SELECT
          p.id,
          p.profile_type,
          p.display_name,
          p.first_name,
          p.last_name,
          p.email,
          p.contact_phone,
          p.is_email_public,
          p.is_name_public,
          p.is_profile_approved,
          p.profile_visible_from,
          p.profile_expires_on,
          artist_role.bio,
          artist_role.is_bio_public,
          EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'artist'
          ) AS has_artist_role
        FROM profiles p
        LEFT JOIN profile_roles artist_role
          ON artist_role.profile_id = p.id
         AND artist_role.role = 'artist'
        WHERE lower(p.email) = lower(%s)
        ORDER BY
          EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'artist'
          ) DESC,
          p.id
        """,
        (email,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError("Multiple profiles already use that email address. Please contact EMOM.")

    row = rows[0]
    profile = {
        "id": row[0],
        "profile_type": row[1],
        "display_name": row[2],
        "first_name": row[3],
        "last_name": row[4],
        "email": row[5],
        "contact_phone": row[6],
        "is_email_public": row[7],
        "is_name_public": row[8],
        "is_profile_approved": row[9],
        "profile_visible_from": row[10],
        "profile_expires_on": row[11],
        "artist_bio": row[12],
        "is_artist_bio_public": row[13],
        "has_artist_role": row[14],
        "social_links": [],
    }

    cursor.execute(
        """
        SELECT social_platform_id, profile_name
        FROM profile_social_profiles
        WHERE profile_id = %s
        ORDER BY id
        """,
        (profile["id"],),
    )
    profile["social_links"] = [
        {"social_platform_id": social_platform_id, "profile_name": profile_name}
        for social_platform_id, profile_name in cursor.fetchall()
    ]
    return profile


def get_existing_profile_by_display_name(cursor, display_name):
    cursor.execute(
        """
        SELECT p.id
        FROM profiles p
        WHERE lower(p.display_name) = lower(%s)
        ORDER BY
          EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'artist'
          ) DESC,
          p.id
        """,
        (display_name,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError("Multiple profiles already use that display name. Please contact EMOM.")

    return get_existing_profile_by_id(cursor, rows[0][0])


def get_existing_profile_by_id(cursor, profile_id):
    cursor.execute(
        """
        SELECT
          p.id,
          p.profile_type,
          p.display_name,
          p.first_name,
          p.last_name,
          p.email,
          p.contact_phone,
          p.is_email_public,
          p.is_name_public,
          p.is_profile_approved,
          p.profile_visible_from,
          p.profile_expires_on,
          artist_role.bio,
          artist_role.is_bio_public,
          EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'artist'
          ) AS has_artist_role
        FROM profiles p
        LEFT JOIN profile_roles artist_role
          ON artist_role.profile_id = p.id
         AND artist_role.role = 'artist'
        WHERE p.id = %s
        """,
        (profile_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    profile = {
        "id": row[0],
        "profile_type": row[1],
        "display_name": row[2],
        "first_name": row[3],
        "last_name": row[4],
        "email": row[5],
        "contact_phone": row[6],
        "is_email_public": row[7],
        "is_name_public": row[8],
        "is_profile_approved": row[9],
        "profile_visible_from": row[10],
        "profile_expires_on": row[11],
        "artist_bio": row[12],
        "is_artist_bio_public": row[13],
        "has_artist_role": row[14],
        "social_links": [],
    }

    cursor.execute(
        """
        SELECT social_platform_id, profile_name
        FROM profile_social_profiles
        WHERE profile_id = %s
        ORDER BY id
        """,
        (profile["id"],),
    )
    profile["social_links"] = [
        {"social_platform_id": social_platform_id, "profile_name": profile_name}
        for social_platform_id, profile_name in cursor.fetchall()
    ]
    return profile


def get_existing_profile_for_submission(cursor, *, email, display_name):
    profile = get_existing_profile_by_email(cursor, email)
    if profile:
        return profile, "email"

    profile = get_existing_profile_by_display_name(cursor, display_name)
    if profile:
        return profile, "display_name"

    return None, None


def serialize_profile(profile):
    if not profile:
        return None
    return {
        "id": profile["id"],
        "profile_type": profile["profile_type"],
        "display_name": profile["display_name"],
        "first_name": profile["first_name"],
        "last_name": profile["last_name"],
        "email": profile["email"],
        "contact_phone": profile["contact_phone"],
        "is_email_public": profile["is_email_public"],
        "is_name_public": profile["is_name_public"],
        "artist_bio": profile["artist_bio"],
        "is_artist_bio_public": profile["is_artist_bio_public"],
        "has_artist_role": profile["has_artist_role"],
        "social_links": profile["social_links"],
    }


def get_social_platforms(cursor):
    cursor.execute(
        """
        SELECT id, platform_name, url_format
        FROM social_platforms
        ORDER BY platform_name, id
        """
    )
    return [
        {"id": row[0], "platform_name": row[1], "url_format": row[2]}
        for row in cursor.fetchall()
    ]


def get_available_events(cursor, profile_id, settings):
    cooldown_events = settings["performer_request_cooldown_events"]
    last_performance = None

    if profile_id is not None:
        cursor.execute(
            """
            SELECT e.id, e.event_date
            FROM performances perf
            JOIN events e
              ON e.id = perf.event_id
            WHERE perf.profile_id = %s
              AND e.type_id = %s
              AND e.event_date <= CURRENT_DATE
            ORDER BY e.event_date DESC, e.id DESC
            LIMIT 1
            """,
            (profile_id, OPEN_MIC_EVENT_TYPE_ID),
        )
        row = cursor.fetchone()
        if row:
            last_performance = {"event_id": row[0], "event_date": row[1]}

    if last_performance is None:
        cursor.execute(
            """
            SELECT id, event_name, event_date
            FROM events
            WHERE event_date > CURRENT_DATE
              AND type_id = %s
            ORDER BY event_date, id
            """,
            (OPEN_MIC_EVENT_TYPE_ID,),
        )
    else:
        cursor.execute(
            """
            WITH ranked_future_events AS (
              SELECT
                e.id,
                e.event_name,
                e.event_date,
                ROW_NUMBER() OVER (ORDER BY e.event_date, e.id) AS future_position
              FROM events e
              WHERE e.event_date > CURRENT_DATE
                AND e.type_id = %s
                AND (e.event_date, e.id) > (%s, %s)
            )
            SELECT id, event_name, event_date
            FROM ranked_future_events
            WHERE future_position > %s
            ORDER BY event_date, id
            """,
            (
                OPEN_MIC_EVENT_TYPE_ID,
                last_performance["event_date"],
                last_performance["event_id"],
                cooldown_events,
            ),
        )

    return [
        {"id": row[0], "event_name": row[1], "event_date": row[2].isoformat()}
        for row in cursor.fetchall()
    ]


def ensure_requested_events_are_allowed(requested_event_ids, available_event_ids):
    disallowed = [event_id for event_id in requested_event_ids if event_id not in available_event_ids]
    if disallowed:
        raise ValueError("One or more requested event dates are not currently available.")


def ensure_social_platforms_exist(cursor, social_platform_ids):
    if not social_platform_ids:
        return
    cursor.execute(
        """
        SELECT id
        FROM social_platforms
        WHERE id = ANY(%s)
        """,
        (social_platform_ids,),
    )
    found_ids = {row[0] for row in cursor.fetchall()}
    missing_ids = sorted(set(social_platform_ids) - found_ids)
    if missing_ids:
        raise ValueError(f"Unknown social platform ids: {', '.join(str(item) for item in missing_ids)}")


def insert_profile_submission_draft(*, cursor, profile, email, draft_payload):
    cursor.execute(
        """
        INSERT INTO profile_submission_drafts (
          profile_id,
          email,
          profile_type,
          display_name,
          first_name,
          last_name,
          contact_phone,
          is_email_public,
          is_name_public,
          artist_bio,
          is_artist_bio_public,
          submitted_by_email
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            profile["id"] if profile else None,
            email,
            draft_payload["profile_type"],
            draft_payload["display_name"],
            draft_payload["first_name"],
            draft_payload["last_name"],
            draft_payload["contact_phone"],
            draft_payload["is_email_public"],
            draft_payload["is_name_public"],
            draft_payload["artist_bio"],
            draft_payload["is_artist_bio_public"],
            email,
        ),
    )
    return cursor.fetchone()[0]


def supersede_pending_drafts(cursor, profile_id, email):
    if profile_id is not None:
        cursor.execute(
            """
            UPDATE profile_submission_drafts
            SET status = 'superseded'
            WHERE profile_id = %s
              AND status = 'pending'
            """,
            (profile_id,),
        )
    else:
        cursor.execute(
            """
            UPDATE profile_submission_drafts
            SET status = 'superseded'
            WHERE lower(email) = lower(%s)
              AND profile_id IS NULL
              AND status = 'pending'
            """,
            (email,),
        )


def insert_profile_submission_social_links(cursor, draft_id, social_links):
    for sort_order, item in enumerate(social_links):
        cursor.execute(
            """
            INSERT INTO profile_submission_social_profiles (draft_id, social_platform_id, profile_name, sort_order)
            VALUES (%s, %s, %s, %s)
            """,
            (draft_id, item["social_platform_id"], item["profile_name"], sort_order),
        )


def insert_requested_dates(cursor, draft_id, requested_event_ids):
    for event_id in requested_event_ids:
        cursor.execute(
            """
            INSERT INTO requested_dates (draft_id, event_id)
            VALUES (%s, %s)
            """,
            (draft_id, event_id),
        )


def get_requested_date_with_context(cursor, requested_date_id):
    cursor.execute(
        """
        SELECT
          rd.id,
          rd.status,
          rd.event_id,
          e.event_name,
          e.event_date,
          d.id,
          d.email,
          d.display_name,
          d.profile_id,
          COALESCE(p.is_profile_approved, false) AS is_profile_approved
        FROM requested_dates rd
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        JOIN events e
          ON e.id = rd.event_id
        LEFT JOIN profiles p
          ON p.id = d.profile_id
        WHERE rd.id = %s
        """,
        (requested_date_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That availability request no longer exists.")

    return {
        "id": row[0],
        "status": row[1],
        "event_id": row[2],
        "event_name": row[3],
        "event_date": row[4].isoformat(),
        "draft_id": row[5],
        "email": row[6],
        "display_name": row[7],
        "profile_id": row[8],
        "is_profile_approved": row[9],
    }


def ensure_requested_date_is_actionable(requested_date):
    if requested_date["status"] not in {"requested", "availability_confirmed", "availability_cancelled"}:
        raise ValueError("This availability request can no longer be updated.")


def update_requested_date_availability_status(cursor, *, requested_date_id, status):
    cursor.execute(
        """
        UPDATE requested_dates
        SET
          status = %s,
          availability_responded_at = now()
        WHERE id = %s
        """,
        (status, requested_date_id),
    )


def invalidate_availability_tokens_for_requested_date(cursor, requested_date_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE requested_date_id = %s
          AND action_type IN (%s, %s)
          AND used_at IS NULL
        """,
        (requested_date_id, ACTION_TYPE_AVAILABILITY_CONFIRM, ACTION_TYPE_AVAILABILITY_CANCEL),
    )


def get_moderator_emails(cursor):
    cursor.execute(
        """
        SELECT p.id, p.email
        FROM profiles p
        WHERE p.is_moderator = true
          AND p.email IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'volunteer'
          )
        ORDER BY p.id
        """
    )
    return [{"profile_id": row[0], "email": row[1]} for row in cursor.fetchall()]


def create_moderation_links(*, cursor, app, draft_id, moderator_emails, ttl_hours):
    links = []
    expires_at = now_utc() + timedelta(hours=ttl_hours)
    for moderator in moderator_emails:
        approve_token, approve_hash = generate_token_pair()
        deny_token, deny_hash = generate_token_pair()

        cursor.execute(
            """
            INSERT INTO action_tokens (token_hash, action_type, email, profile_id, draft_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (approve_hash, ACTION_TYPE_MODERATION_APPROVE, moderator["email"], moderator["profile_id"], draft_id, expires_at),
        )
        cursor.execute(
            """
            INSERT INTO action_tokens (token_hash, action_type, email, profile_id, draft_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (deny_hash, ACTION_TYPE_MODERATION_DENY, moderator["email"], moderator["profile_id"], draft_id, expires_at),
        )

        links.append(
            {
                "email": moderator["email"],
                "approve_url": build_absolute_url(
                    app, f"/api/forms/performer-registration/moderation/approve?token={approve_token}"
                ),
                "deny_url": build_absolute_url(
                    app, f"/api/forms/performer-registration/moderation/deny?token={deny_token}"
                ),
            }
        )
    return links


def get_profile_submission_draft(cursor, draft_id):
    cursor.execute(
        """
        SELECT
          id,
          profile_id,
          email,
          profile_type,
          display_name,
          first_name,
          last_name,
          contact_phone,
          is_email_public,
          is_name_public,
          artist_bio,
          is_artist_bio_public,
          status
        FROM profile_submission_drafts
        WHERE id = %s
        """,
        (draft_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That submission no longer exists.")

    draft = {
        "id": row[0],
        "profile_id": row[1],
        "email": row[2],
        "profile_type": row[3],
        "display_name": row[4],
        "first_name": row[5],
        "last_name": row[6],
        "contact_phone": row[7],
        "is_email_public": row[8],
        "is_name_public": row[9],
        "artist_bio": row[10],
        "is_artist_bio_public": row[11],
        "status": row[12],
        "social_links": [],
        "requested_event_ids": [],
    }

    cursor.execute(
        """
        SELECT social_platform_id, profile_name
        FROM profile_submission_social_profiles
        WHERE draft_id = %s
        ORDER BY sort_order, id
        """,
        (draft_id,),
    )
    draft["social_links"] = [
        {"social_platform_id": social_platform_id, "profile_name": profile_name}
        for social_platform_id, profile_name in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT event_id
        FROM requested_dates
        WHERE draft_id = %s
        ORDER BY event_id
        """,
        (draft_id,),
    )
    draft["requested_event_ids"] = [row[0] for row in cursor.fetchall()]
    return draft


def apply_approved_draft(cursor, draft, approved_by_profile_id):
    if draft["profile_id"] is None:
        cursor.execute(
            """
            INSERT INTO profiles (
              profile_type,
              display_name,
              first_name,
              last_name,
              email,
              contact_phone,
              is_email_public,
              is_name_public,
              is_profile_approved,
              profile_visible_from,
              profile_expires_on,
              approved_at,
              approved_by_profile_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, NULL, CURRENT_DATE + INTERVAL '100 years', now(), %s)
            RETURNING id
            """,
            (
                draft["profile_type"],
                draft["display_name"],
                draft["first_name"],
                draft["last_name"],
                draft["email"],
                draft["contact_phone"],
                draft["is_email_public"],
                draft["is_name_public"],
                approved_by_profile_id,
            ),
        )
        profile_id = cursor.fetchone()[0]
    else:
        profile_id = draft["profile_id"]
        cursor.execute(
            """
            UPDATE profiles
            SET
              profile_type = %s,
              display_name = %s,
              first_name = %s,
              last_name = %s,
              email = %s,
              contact_phone = %s,
              is_email_public = %s,
              is_name_public = %s,
              is_profile_approved = true,
              approved_at = now(),
              approved_by_profile_id = %s
            WHERE id = %s
            """,
            (
                draft["profile_type"],
                draft["display_name"],
                draft["first_name"],
                draft["last_name"],
                draft["email"],
                draft["contact_phone"],
                draft["is_email_public"],
                draft["is_name_public"],
                approved_by_profile_id,
                profile_id,
            ),
        )

    upsert_artist_role(cursor, profile_id, draft["artist_bio"], draft["is_artist_bio_public"])
    replace_profile_social_links(cursor, profile_id, draft["social_links"])
    update_profile_visibility_from_requests(cursor, profile_id, draft["requested_event_ids"])
    return profile_id


def upsert_artist_role(cursor, profile_id, bio, is_bio_public):
    cursor.execute(
        """
        INSERT INTO profile_roles (profile_id, role, bio, is_bio_public)
        VALUES (%s, 'artist', %s, %s)
        ON CONFLICT (profile_id, role)
        DO UPDATE SET
          bio = EXCLUDED.bio,
          is_bio_public = EXCLUDED.is_bio_public
        """,
        (profile_id, bio, is_bio_public),
    )


def replace_profile_social_links(cursor, profile_id, social_links):
    cursor.execute("DELETE FROM profile_social_profiles WHERE profile_id = %s", (profile_id,))
    for item in social_links:
        cursor.execute(
            """
            INSERT INTO profile_social_profiles (profile_id, social_platform_id, profile_name)
            VALUES (%s, %s, %s)
            """,
            (profile_id, item["social_platform_id"], item["profile_name"]),
        )


def update_profile_visibility_from_requests(cursor, profile_id, requested_event_ids):
    if not requested_event_ids:
        return
    cursor.execute(
        """
        SELECT MIN(event_date)
        FROM events
        WHERE id = ANY(%s)
        """,
        (requested_event_ids,),
    )
    first_requested_event_date = cursor.fetchone()[0]
    cursor.execute(
        """
        UPDATE profiles
        SET
          profile_visible_from = CASE
            WHEN profile_visible_from IS NULL THEN %s
            ELSE LEAST(profile_visible_from, %s)
          END
        WHERE id = %s
        """,
        (first_requested_event_date, first_requested_event_date, profile_id),
    )

def record_moderation_action(cursor, *, draft_id, moderator_profile_id, action, reason):
    moderation_action = "approved" if action == WORKFLOW_STATUS_APPROVED else "denied"
    cursor.execute(
        """
        INSERT INTO moderation_actions (draft_id, moderator_profile_id, action, reason)
        VALUES (%s, %s, %s, %s)
        """,
        (draft_id, moderator_profile_id, moderation_action, reason),
    )


def finalize_draft_status(cursor, *, draft_id, status, reviewer_profile_id, denial_reason):
    cursor.execute(
        """
        UPDATE profile_submission_drafts
        SET
          status = %s,
          reviewed_at = now(),
          reviewed_by_profile_id = %s,
          denial_reason = %s
        WHERE id = %s
        """,
        (status, reviewer_profile_id, denial_reason, draft_id),
    )


def send_due_availability_confirmation_emails(app, run_date=None):
    sent_count = 0
    moderator_reminder_count = 0

    with connect() as connection:
        with connection.cursor() as cursor:
            settings = get_workflow_settings(cursor)
            target_date = resolve_target_event_date(
                run_date=run_date,
                lead_days=settings["availability_confirmation_lead_days"],
            )
            due_requests = get_due_availability_requests(cursor, target_date)
            moderator_emails = get_moderator_emails(cursor)

            for item in due_requests:
                invalidate_availability_tokens_for_requested_date(cursor, item["requested_date_id"])
                confirm_token, confirm_hash = generate_token_pair()
                cancel_token, cancel_hash = generate_token_pair()
                expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])

                cursor.execute(
                    """
                    INSERT INTO action_tokens (
                      token_hash,
                      action_type,
                      email,
                      profile_id,
                      draft_id,
                      requested_date_id,
                      event_id,
                      expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        confirm_hash,
                        ACTION_TYPE_AVAILABILITY_CONFIRM,
                        item["email"],
                        item["profile_id"],
                        item["draft_id"],
                        item["requested_date_id"],
                        item["event_id"],
                        expires_at,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO action_tokens (
                      token_hash,
                      action_type,
                      email,
                      profile_id,
                      draft_id,
                      requested_date_id,
                      event_id,
                      expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        cancel_hash,
                        ACTION_TYPE_AVAILABILITY_CANCEL,
                        item["email"],
                        item["profile_id"],
                        item["draft_id"],
                        item["requested_date_id"],
                        item["event_id"],
                        expires_at,
                    ),
                )

                confirm_url = build_absolute_url(
                    app, f"/api/forms/performer-registration/availability/confirm?token={confirm_token}"
                )
                cancel_url = build_absolute_url(
                    app, f"/api/forms/performer-registration/availability/cancel?token={cancel_token}"
                )

                send_availability_email(
                    email=item["email"],
                    display_name=item["display_name"],
                    event_name=item["event_name"],
                    event_date=item["event_date"],
                    confirm_url=confirm_url,
                    cancel_url=cancel_url,
                    expires_at=expires_at,
                )
                cursor.execute(
                    """
                    UPDATE requested_dates
                    SET availability_email_sent_at = now()
                    WHERE id = %s
                    """,
                    (item["requested_date_id"],),
                )
                sent_count += 1

            if moderator_emails:
                for reminder in get_unapproved_event_reminders(cursor, target_date):
                    if reminder["requested_date_ids"]:
                        send_unapproved_request_reminder_email(
                            moderator_emails=moderator_emails,
                            event_name=reminder["event_name"],
                            event_date=reminder["event_date"],
                            rows=reminder["rows"],
                        )
                        cursor.execute(
                            """
                            UPDATE requested_dates
                            SET moderator_reminder_sent_at = now()
                            WHERE id = ANY(%s)
                            """,
                            (reminder["requested_date_ids"],),
                        )
                        moderator_reminder_count += 1

        connection.commit()

    return {
        "target_event_date": target_date.isoformat(),
        "availability_emails_sent": sent_count,
        "moderator_reminders_sent": moderator_reminder_count,
    }


def resolve_target_event_date(*, run_date, lead_days):
    if run_date is not None:
        if isinstance(run_date, datetime):
            base_date = run_date.date()
        else:
            base_date = datetime.strptime(str(run_date), "%Y-%m-%d").date()
    else:
        base_date = now_utc().date()
    return base_date + timedelta(days=lead_days)


def get_due_availability_requests(cursor, target_date):
    cursor.execute(
        """
        SELECT
          rd.id,
          rd.draft_id,
          rd.event_id,
          e.event_name,
          e.event_date,
          d.email,
          d.display_name,
          d.profile_id
        FROM requested_dates rd
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        JOIN events e
          ON e.id = rd.event_id
        WHERE e.event_date = %s
          AND e.type_id = %s
          AND rd.status = 'requested'
          AND rd.availability_email_sent_at IS NULL
        ORDER BY e.id, rd.id
        """,
        (target_date, OPEN_MIC_EVENT_TYPE_ID),
    )
    return [
        {
            "requested_date_id": row[0],
            "draft_id": row[1],
            "event_id": row[2],
            "event_name": row[3],
            "event_date": row[4].isoformat(),
            "email": row[5],
            "display_name": row[6],
            "profile_id": row[7],
        }
        for row in cursor.fetchall()
    ]


def get_unapproved_event_reminders(cursor, target_date):
    cursor.execute(
        """
        SELECT
          e.id,
          e.event_name,
          e.event_date,
          rd.id,
          d.display_name,
          d.email
        FROM requested_dates rd
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        JOIN events e
          ON e.id = rd.event_id
        LEFT JOIN profiles p
          ON p.id = d.profile_id
        WHERE e.event_date = %s
          AND e.type_id = %s
          AND rd.status = 'requested'
          AND rd.moderator_reminder_sent_at IS NULL
          AND COALESCE(p.is_profile_approved, false) = false
        ORDER BY e.id, d.display_name, rd.id
        """,
        (target_date, OPEN_MIC_EVENT_TYPE_ID),
    )

    reminders_by_event = {}
    for event_id, event_name, event_date, requested_date_id, display_name, email in cursor.fetchall():
        reminder = reminders_by_event.setdefault(
            event_id,
            {
                "event_name": event_name,
                "event_date": event_date.isoformat(),
                "requested_date_ids": [],
                "rows": [],
            },
        )
        reminder["requested_date_ids"].append(requested_date_id)
        reminder["rows"].append({"display_name": display_name, "email": email})

    return list(reminders_by_event.values())


def build_absolute_url(app, path):
    base_url = os.getenv("FORMS_SITE_BASE_URL") or os.getenv("PUBLIC_SITE_BASE_URL")
    if not base_url:
        raise ValueError("FORMS_SITE_BASE_URL must be configured.")
    return f"{base_url.rstrip('/')}{path}"


def send_registration_email(app, email, raw_token, expires_at):
    register_url = build_absolute_url(app, f"/perform/?token={raw_token}")
    body = (
        "Click the link below to create or update your performer profile and request event dates.\n\n"
        f"{register_url}\n\n"
        f"This link expires at {expires_at.isoformat()}.\n"
    )
    send_mail(email, "EMOM performer registration link", body)


def send_moderation_emails(app, *, draft_id, email, draft_payload, existing_profile, matched_by, moderation_links):
    if not moderation_links:
        return

    requested_events = ", ".join(str(event_id) for event_id in draft_payload["requested_event_ids"])
    social_lines = "\n".join(
        f"- platform #{item['social_platform_id']}: {item['profile_name']}" for item in draft_payload["social_links"]
    ) or "- none provided"
    existing_profile_block = format_existing_profile_for_moderation(existing_profile, matched_by)

    for item in moderation_links:
        body = (
            f"A performer profile submission is awaiting moderation.\n\n"
            f"Draft ID: {draft_id}\n"
            f"{existing_profile_block}"
            f"Email: {email}\n"
            f"Profile type: {draft_payload['profile_type']}\n"
            f"Display name: {draft_payload['display_name']}\n"
            f"First name: {draft_payload['first_name'] or ''}\n"
            f"Last name: {draft_payload['last_name'] or ''}\n"
            f"Contact phone: {draft_payload['contact_phone']}\n"
            f"Email public: {'yes' if draft_payload['is_email_public'] else 'no'}\n"
            f"Name public: {'yes' if draft_payload['is_name_public'] else 'no'}\n"
            f"Bio public: {'yes' if draft_payload['is_artist_bio_public'] else 'no'}\n"
            f"Bio:\n{draft_payload['artist_bio'] or '(none)'}\n\n"
            f"Requested event ids: {requested_events}\n"
            f"Social links:\n{social_lines}\n\n"
            f"Approve: {item['approve_url']}\n"
            f"Deny: {item['deny_url']}\n"
        )
        send_mail(item["email"], f"EMOM performer profile moderation request #{draft_id}", body)


def format_existing_profile_for_moderation(existing_profile, matched_by):
    if not existing_profile:
        return "Existing profile match: none. This will create a new profile if approved.\n\n"

    social_lines = "\n".join(
        f"- platform #{item['social_platform_id']}: {item['profile_name']}" for item in existing_profile["social_links"]
    ) or "- none on current live profile"

    return (
        f"Existing profile match: yes ({matched_by})\n"
        f"Existing profile id: {existing_profile['id']}\n"
        f"Existing email: {existing_profile['email'] or ''}\n"
        f"Existing display name: {existing_profile['display_name'] or ''}\n"
        f"Existing first name: {existing_profile['first_name'] or ''}\n"
        f"Existing last name: {existing_profile['last_name'] or ''}\n"
        f"Existing contact phone: {existing_profile['contact_phone'] or ''}\n"
        f"Existing email public: {'yes' if existing_profile['is_email_public'] else 'no'}\n"
        f"Existing name public: {'yes' if existing_profile['is_name_public'] else 'no'}\n"
        f"Existing bio public: {'yes' if existing_profile['is_artist_bio_public'] else 'no'}\n"
        f"Existing bio:\n{existing_profile['artist_bio'] or '(none)'}\n"
        f"Existing social links:\n{social_lines}\n\n"
        "Submitted draft:\n"
    )


def send_profile_approved_email(app, email):
    body = (
        "Your performer profile has been approved, and your requested performance dates have been noted.\n"
    )
    send_mail(email, "EMOM performer profile approved", body)


def send_profile_denied_email(app, email, reason):
    body = (
        "Your performer profile submission was not approved at this stage.\n\n"
        f"Reason:\n{reason}\n"
    )
    send_mail(email, "EMOM performer profile update", body)


def send_availability_email(*, email, display_name, event_name, event_date, confirm_url, cancel_url, expires_at):
    body = (
        f"Hello {display_name or 'performer'},\n\n"
        f"You previously registered interest in playing at {event_name} on {event_date}.\n"
        "Please use one of the links below to confirm or cancel your availability.\n\n"
        f"Confirm availability: {confirm_url}\n"
        f"Cancel availability: {cancel_url}\n\n"
        f"These links expire at {expires_at.isoformat()}.\n"
    )
    send_mail(email, f"EMOM availability check for {event_name}", body)


def send_unapproved_request_reminder_email(*, moderator_emails, event_name, event_date, rows):
    row_lines = "\n".join(
        f"- {item['display_name']} <{item['email']}>" for item in rows
    ) or "- none"
    body = (
        f"Availability reminders have gone out for {event_name} on {event_date}.\n\n"
        "The following requesters for that event are still unapproved:\n"
        f"{row_lines}\n"
    )
    for moderator in moderator_emails:
        send_mail(
            moderator["email"],
            f"EMOM moderator reminder: unapproved requesters for {event_name}",
            body,
        )


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


def render_denial_form(raw_token):
    safe_token = html.escape(raw_token, quote=True)
    return (
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Deny performer profile</title>
    <style>
      body { font-family: sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }
      textarea { width: 100%; min-height: 12rem; }
      button { margin-top: 1rem; }
    </style>
  </head>
  <body>
    <h1>Deny performer profile</h1>
    <form method="post">
      <input type="hidden" name="token" value=\""""
        + safe_token
        + """\">
      <label for="reason">Reason</label>
      <textarea id="reason" name="reason" required></textarea>
      <button type="submit">Send denial</button>
    </form>
  </body>
</html>
"""
    )


def html_success_page(title, message):
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{html.escape(title)}</title></head>"
        f"<body><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></body></html>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


def html_error_page(message, status_code):
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Error</title></head>"
        f"<body><h1>Error</h1><p>{html.escape(message)}</p></body></html>",
        status_code,
        {"Content-Type": "text/html; charset=utf-8"},
    )


def error_response(message, status_code):
    return jsonify({"ok": False, "error": message}), status_code
