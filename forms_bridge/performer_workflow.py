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
from urllib.parse import quote

from flask import jsonify, request

from forms_bridge.db import connect


ACTION_TYPE_REGISTRATION_LINK = "registration_link"
ACTION_TYPE_MODERATION_APPROVE = "moderation_approve"
ACTION_TYPE_MODERATION_DENY = "moderation_deny"
ACTION_TYPE_AVAILABILITY_CONFIRM = "availability_confirm"
ACTION_TYPE_AVAILABILITY_CANCEL = "availability_cancel"
ACTION_TYPE_ADMIN_SELECTION = "admin_selection"
ACTION_TYPE_BACKUP_SELECTION = "backup_selection"

WORKFLOW_STATUS_PENDING = "pending"
WORKFLOW_STATUS_APPROVED = "approved"
WORKFLOW_STATUS_DENIED = "denied"
LINEUP_STATUS_SELECTED = "selected"
LINEUP_STATUS_STANDBY = "standby"
LINEUP_STATUS_RESERVE = "reserve"
ADMIN_SELECTION_ALLOWED_STATUSES = {
    LINEUP_STATUS_SELECTED,
    LINEUP_STATUS_STANDBY,
    LINEUP_STATUS_RESERVE,
}
OPEN_MIC_EVENT_TYPE_ID = 1
DEFAULT_ADMIN_SELECTION_LOCK_MINUTES = 30


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
                    live_profile = get_existing_profile_by_email(cursor, email)
                    latest_draft = get_latest_prefill_submission_by_email(cursor, email)
                    profile = serialize_prefill_profile(latest_draft) if latest_draft else live_profile
                    availability_profile = live_profile
                    if not availability_profile and latest_draft and latest_draft["profile_id"]:
                        availability_profile = get_existing_profile_by_id(cursor, latest_draft["profile_id"])
                    available_events = get_available_events(
                        cursor, availability_profile["id"] if availability_profile else None, settings
                    )
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
                    stored_draft = get_profile_submission_draft(cursor, draft_id)
                    current_status_summary = get_upcoming_event_status_summary(cursor)

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
                    draft_payload=stored_draft,
                    existing_profile=profile,
                    matched_by=matched_by,
                    moderation_links=moderation_links,
                    current_status_summary=current_status_summary,
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
                    attach_profile_to_draft(cursor, draft_id=draft["id"], profile_id=profile_id)
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
                    settings = get_workflow_settings(cursor)

                send_profile_approved_email(
                    app,
                    draft["email"],
                    requested_events=draft["requested_events"],
                    final_selection_lead_days=settings["final_selection_lead_days"],
                )

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
        include_edit_link = request.form.get("include_edit_link") != "0"
        if not raw_token:
            return html_error_page("Missing moderation token.", 400)
        if not denial_reason:
            return html_error_page("A denial reason is required.", 400)

        try:
            edit_link = None
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
                    if include_edit_link:
                        edit_link = create_registration_link(
                            cursor=cursor,
                            app=app,
                            email=draft["email"],
                            ttl_hours=get_workflow_settings(cursor)["action_token_ttl_hours"],
                        )

                send_profile_denied_email(app, draft["email"], denial_reason, edit_link=edit_link)

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
                    handle_selection_cancellation_if_needed(app, cursor, requested_date)

            return html_success_page(
                "Availability cancelled",
                f"Your availability for {requested_date['event_name']} on {requested_date['event_date']} has been cancelled.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Availability cancellation failed")
            return html_error_page("Unable to cancel availability right now.", 500)

    @app.route("/api/forms/performer-registration/admin-selection", methods=["GET", "POST"])
    def admin_selection():
        if request.method == "GET":
            raw_token = normalize_text(request.args.get("token"))
            if not raw_token:
                return html_error_page("Missing admin selection token.", 400)

            try:
                with connect() as connection:
                    with connection.cursor() as cursor:
                        token_row = get_action_token(cursor, raw_token, ACTION_TYPE_ADMIN_SELECTION)
                        lock_state = acquire_admin_selection_lock(
                            cursor,
                            event_id=token_row["event_id"],
                            profile_id=token_row["profile_id"],
                            lock_minutes=get_admin_selection_lock_minutes(),
                        )
                        if not lock_state["acquired"]:
                            holder_name = lock_state["locked_by_name"] or "Another admin"
                            locked_until = format_link_expiry_local(lock_state.get("lock_expires_at"))
                            raise ValueError(
                                f"{holder_name} is currently editing this lineup. "
                                f"Please try again after {locked_until}."
                            )
                        event = get_event_selection_context(cursor, token_row["event_id"])
                        candidates = get_admin_selection_candidates(cursor, token_row["event_id"])
                        max_performers = get_workflow_settings(cursor)["max_performers_per_event"]
                return render_admin_selection_form(
                    raw_token,
                    event,
                    candidates,
                    max_performers,
                    active_editor_name=lock_state.get("locked_by_name"),
                )
            except ValueError as exc:
                status_code = 409 if "currently editing this lineup" in str(exc) else 400
                return html_error_page(str(exc), status_code)
            except Exception:
                app.logger.exception("Admin selection form lookup failed")
                return html_error_page("Unable to load admin selection right now.", 500)

        raw_token = normalize_text(request.form.get("token"))
        if not raw_token:
            return html_error_page("Missing admin selection token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_ADMIN_SELECTION)
                    lock_state = acquire_admin_selection_lock(
                        cursor,
                        event_id=token_row["event_id"],
                        profile_id=token_row["profile_id"],
                        lock_minutes=get_admin_selection_lock_minutes(),
                    )
                    if not lock_state["acquired"]:
                        holder_name = lock_state["locked_by_name"] or "Another admin"
                        locked_until = format_link_expiry_local(lock_state.get("lock_expires_at"))
                        raise ValueError(
                            f"{holder_name} is currently editing this lineup. "
                            f"Please try again after {locked_until}."
                        )
                    settings = get_workflow_settings(cursor)
                    event = get_event_selection_context(cursor, token_row["event_id"])
                    candidates = get_admin_selection_candidates(cursor, token_row["event_id"])
                    candidate_statuses = parse_admin_selection_statuses(request.form, candidates)
                    save_admin_selection(
                        cursor,
                        event_id=token_row["event_id"],
                        admin_profile_id=token_row["profile_id"],
                        candidates=candidates,
                        candidate_statuses=candidate_statuses,
                        max_performers=settings["max_performers_per_event"],
                    )
                    mark_action_token_used(cursor, token_row["id"])
                    release_admin_selection_lock(
                        cursor,
                        event_id=token_row["event_id"],
                        profile_id=token_row["profile_id"],
                    )

                send_selected_performer_emails(
                    event,
                    candidates,
                    [
                        item["requested_date_id"]
                        for item in candidates
                        if candidate_statuses.get(item["requested_date_id"]) == LINEUP_STATUS_SELECTED
                    ],
                )

            return html_success_page(
                "Lineup saved",
                f"The selection for {event['event_name']} on {event['event_date']} has been saved.",
            )
        except ValueError as exc:
            status_code = 409 if "currently editing this lineup" in str(exc) else 400
            return html_error_page(str(exc), status_code)
        except Exception:
            app.logger.exception("Admin selection save failed")
            return html_error_page("Unable to save admin selection right now.", 500)

    @app.route("/api/forms/performer-registration/admin-selection/send-confirmation", methods=["GET"])
    def admin_selection_send_confirmation():
        raw_token = normalize_text(request.args.get("token"))
        requested_date_id_text = normalize_text(request.args.get("requested_date_id"))
        if not raw_token:
            return html_error_page("Missing admin selection token.", 400)
        if not requested_date_id_text or not requested_date_id_text.isdigit():
            return html_error_page("A valid performer request is required.", 400)

        try:
            requested_date_id = int(requested_date_id_text)
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_ADMIN_SELECTION)
                    lock_state = acquire_admin_selection_lock(
                        cursor,
                        event_id=token_row["event_id"],
                        profile_id=token_row["profile_id"],
                        lock_minutes=get_admin_selection_lock_minutes(),
                    )
                    if not lock_state["acquired"]:
                        holder_name = lock_state["locked_by_name"] or "Another admin"
                        locked_until = format_link_expiry_local(lock_state.get("lock_expires_at"))
                        raise ValueError(
                            f"{holder_name} is currently editing this lineup. "
                            f"Please try again after {locked_until}."
                        )
                    event = get_event_selection_context(cursor, token_row["event_id"])
                    sent = send_availability_confirmation_for_requested_date(
                        app,
                        cursor,
                        requested_date_id=requested_date_id,
                        event_id=token_row["event_id"],
                    )
                    candidates = get_admin_selection_candidates(cursor, token_row["event_id"])
                    max_performers = get_workflow_settings(cursor)["max_performers_per_event"]

                return render_admin_selection_form(
                    raw_token,
                    event,
                    candidates,
                    max_performers,
                    notice_message=f"Availability confirmation email sent to {sent['display_name']} ({sent['email']}).",
                    active_editor_name=lock_state.get("locked_by_name"),
                )
        except ValueError as exc:
            status_code = 409 if "currently editing this lineup" in str(exc) else 400
            return html_error_page(str(exc), status_code)
        except Exception:
            app.logger.exception("Admin selection confirmation resend failed")
            return html_error_page("Unable to send confirmation email right now.", 500)

    @app.route("/api/forms/performer-registration/admin-selection/lock", methods=["POST"])
    def admin_selection_lock_heartbeat():
        raw_token = normalize_text(request.args.get("token") or request.form.get("token"))
        if not raw_token:
            return error_response("A valid admin selection token is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_ADMIN_SELECTION)
                    lock_state = acquire_admin_selection_lock(
                        cursor,
                        event_id=token_row["event_id"],
                        profile_id=token_row["profile_id"],
                        lock_minutes=get_admin_selection_lock_minutes(),
                    )
            if not lock_state["acquired"]:
                holder_name = lock_state["locked_by_name"] or "Another admin"
                locked_until = format_link_expiry_local(lock_state.get("lock_expires_at"))
                return error_response(
                    f"{holder_name} is currently editing this lineup. Please try again after {locked_until}.",
                    409,
                )

            return jsonify(
                {
                    "ok": True,
                    "locked_by": lock_state.get("locked_by_name"),
                    "expires_at": lock_state["lock_expires_at"].isoformat(),
                }
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Admin selection lock heartbeat failed")
            return error_response("Unable to refresh admin selection lock right now.", 500)

    @app.route("/api/forms/performer-registration/admin-selection/lock/release", methods=["POST"])
    def admin_selection_lock_release():
        raw_token = normalize_text(request.args.get("token") or request.form.get("token"))
        if not raw_token:
            return ("", 204)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_ADMIN_SELECTION)
                    release_admin_selection_lock(
                        cursor,
                        event_id=token_row["event_id"],
                        profile_id=token_row["profile_id"],
                    )
            return ("", 204)
        except ValueError:
            return ("", 204)
        except Exception:
            app.logger.exception("Admin selection lock release failed")
            return ("", 204)

    @app.route("/api/forms/performer-registration/admin-selection/events", methods=["GET"])
    def admin_selection_events():
        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    events = get_upcoming_open_mic_events(cursor)
            return jsonify({"ok": True, "events": events})
        except Exception:
            app.logger.exception("Admin selection events lookup failed")
            return error_response("Unable to load upcoming event dates right now.", 500)

    @app.route("/api/forms/performer-registration/admin-selection/start", methods=["OPTIONS"])
    def admin_selection_start_options():
        return ("", 204)

    @app.route("/api/forms/performer-registration/admin-selection/start", methods=["POST"])
    def admin_selection_start():
        try:
            payload = get_json_payload()
            email = normalize_email(payload.get("email"))
            event_id = payload.get("event_id")
            if not email:
                return error_response("A valid email address is required.", 400)
            if not isinstance(event_id, int):
                raise ValueError("A valid event date must be selected.")

            with connect() as connection:
                with connection.cursor() as cursor:
                    settings = get_workflow_settings(cursor)
                    event = get_open_mic_event_for_admin_selection(cursor, event_id)
                    admin = get_admin_profile_by_email(cursor, email)
                    if admin:
                        # If this admin asks for a fresh link, clear any stale self-lock for this event.
                        release_admin_selection_lock(
                            cursor,
                            event_id=event["event_id"],
                            profile_id=admin["profile_id"],
                        )
                        invalidate_unused_tokens(
                            cursor,
                            email=email,
                            action_type=ACTION_TYPE_ADMIN_SELECTION,
                        )
                        raw_token, token_hash = generate_token_pair()
                        expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])
                        cursor.execute(
                            """
                            INSERT INTO action_tokens (token_hash, action_type, email, profile_id, event_id, expires_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                token_hash,
                                ACTION_TYPE_ADMIN_SELECTION,
                                admin["email"],
                                admin["profile_id"],
                                event["event_id"],
                                expires_at,
                            ),
                        )
                        selection_url = build_absolute_url(app, f"/perform/admin/?token={raw_token}")
                    else:
                        selection_url = None
                        expires_at = None

                if admin:
                    send_admin_selection_email(
                        admin_email=admin["email"],
                        event_name=event["event_name"],
                        event_date=event["event_date"],
                        selection_url=selection_url,
                        expires_at=expires_at,
                    )

            return jsonify(
                {
                    "ok": True,
                    "message": "If that email address belongs to an admin, a fresh selection link has been sent.",
                }
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Admin selection start failed")
            return error_response("Unable to send an admin selection link right now.", 500)

    @app.route("/api/forms/performer-registration/backup-selection", methods=["GET", "POST"])
    def backup_selection():
        if request.method == "GET":
            raw_token = normalize_text(request.args.get("token"))
            if not raw_token:
                return html_error_page("Missing standby selection token.", 400)

            try:
                with connect() as connection:
                    with connection.cursor() as cursor:
                        token_row = get_action_token(cursor, raw_token, ACTION_TYPE_BACKUP_SELECTION)
                        event = get_event_selection_context(cursor, token_row["event_id"])
                        current_selected = get_current_selected_lineup(cursor, token_row["event_id"])
                        backups = get_backup_candidates(cursor, token_row["event_id"])
                        if not backups:
                            raise ValueError("There are no standby performers available for this event.")
                return render_backup_selection_form(raw_token, event, current_selected, backups)
            except ValueError as exc:
                return html_error_page(str(exc), 400)
            except Exception:
                app.logger.exception("Standby selection form lookup failed")
                return html_error_page("Unable to load standby selection right now.", 500)

        raw_token = normalize_text(request.form.get("token"))
        requested_date_id_text = normalize_text(request.form.get("requested_date_id"))
        if not raw_token:
            return html_error_page("Missing standby selection token.", 400)
        if not requested_date_id_text or not requested_date_id_text.isdigit():
            return html_error_page("A standby performer must be selected.", 400)

        requested_date_id = int(requested_date_id_text)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_BACKUP_SELECTION)
                    event = get_event_selection_context(cursor, token_row["event_id"])
                    promoted = promote_backup_selection(
                        cursor,
                        event_id=token_row["event_id"],
                        requested_date_id=requested_date_id,
                        admin_profile_id=token_row["profile_id"],
                    )
                    invalidate_backup_selection_tokens_for_event(cursor, token_row["event_id"])

                send_backup_promoted_email(event, promoted)

            return html_success_page(
                "Standby performer promoted",
                f"{promoted['display_name']} has been promoted into the lineup for {event['event_name']}.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Standby promotion failed")
            return html_error_page("Unable to promote standby performer right now.", 500)


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


def parse_int_list(values):
    parsed = []
    for value in values:
        text = normalize_text(value)
        if not text:
            continue
        if not text.isdigit():
            raise ValueError("Expected integer values.")
        parsed.append(int(text))
    return parsed


def parse_admin_selection_statuses(form, candidates):
    parsed = {}
    for item in candidates:
        if not is_admin_selection_candidate_eligible(item):
            continue
        requested_date_id = item["requested_date_id"]
        raw_value = normalize_text(form.get(f"status_{requested_date_id}")) or LINEUP_STATUS_STANDBY
        if raw_value not in ADMIN_SELECTION_ALLOWED_STATUSES:
            raise ValueError("One or more performer statuses are invalid.")
        parsed[requested_date_id] = raw_value
    return parsed


def normalize_profile_submission_payload(payload, email):
    profile_type = normalize_text(payload.get("profile_type"))
    display_name = normalize_text(payload.get("display_name"))
    first_name = normalize_text(payload.get("first_name"))
    last_name = normalize_text(payload.get("last_name"))
    contact_phone = normalize_text(payload.get("contact_phone"))
    artist_bio = normalize_text(payload.get("artist_bio"))
    additional_info = normalize_text(payload.get("additional_info"))
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
        "is_artist_bio_public": True,
        "additional_info": additional_info,
        "social_links": normalized_social_links,
        "requested_event_ids": normalized_event_ids,
    }


def now_utc():
    return datetime.now(timezone.utc)


def format_link_expiry_local(expires_at):
    if not expires_at:
        return ""
    return expires_at.astimezone().strftime("%H:%M:%S on %d/%m/%y")


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
        "additional_info": None,
        "has_artist_role": row[14],
        "social_links": [],
    }

    cursor.execute(
        """
        SELECT psp.social_platform_id, psp.profile_name, sp.platform_name, sp.url_format
        FROM profile_social_profiles psp
        JOIN social_platforms sp ON sp.id = psp.social_platform_id
        WHERE psp.profile_id = %s
        ORDER BY psp.id
        """,
        (profile["id"],),
    )
    profile["social_links"] = [
        {
            "social_platform_id": social_platform_id,
            "profile_name": profile_name,
            "platform_name": platform_name,
            "url_format": url_format,
        }
        for social_platform_id, profile_name, platform_name, url_format in cursor.fetchall()
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
        "additional_info": None,
        "has_artist_role": row[14],
        "social_links": [],
    }

    cursor.execute(
        """
        SELECT psp.social_platform_id, psp.profile_name, sp.platform_name, sp.url_format
        FROM profile_social_profiles psp
        JOIN social_platforms sp ON sp.id = psp.social_platform_id
        WHERE psp.profile_id = %s
        ORDER BY psp.id
        """,
        (profile["id"],),
    )
    profile["social_links"] = [
        {
            "social_platform_id": social_platform_id,
            "profile_name": profile_name,
            "platform_name": platform_name,
            "url_format": url_format,
        }
        for social_platform_id, profile_name, platform_name, url_format in cursor.fetchall()
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
        "additional_info": profile.get("additional_info"),
        "has_artist_role": profile["has_artist_role"],
        "social_links": profile["social_links"],
        "requested_event_ids": profile.get("requested_event_ids", []),
    }


def serialize_prefill_profile(draft):
    if not draft:
        return None
    return {
        "id": draft["profile_id"],
        "profile_type": draft["profile_type"],
        "display_name": draft["display_name"],
        "first_name": draft["first_name"],
        "last_name": draft["last_name"],
        "email": draft["email"],
        "contact_phone": draft["contact_phone"],
        "is_email_public": draft["is_email_public"],
        "is_name_public": draft["is_name_public"],
        "artist_bio": draft["artist_bio"],
        "is_artist_bio_public": draft["is_artist_bio_public"],
        "additional_info": draft.get("additional_info"),
        "has_artist_role": True,
        "social_links": draft["social_links"],
        "requested_event_ids": draft["requested_event_ids"],
    }


def get_social_platforms(cursor):
    cursor.execute(
        """
        SELECT id, platform_name, url_format, input_label, input_placeholder, input_help
        FROM social_platforms
        ORDER BY platform_name, id
        """
    )
    return [
        {
            "id": row[0],
            "platform_name": row[1],
            "url_format": row[2],
            "input_label": row[3],
            "input_placeholder": row[4],
            "input_help": row[5],
        }
        for row in cursor.fetchall()
    ]


def get_latest_prefill_submission_by_email(cursor, email):
    cursor.execute(
        """
        SELECT id
        FROM profile_submission_drafts
        WHERE lower(email) = lower(%s)
          AND status IN (%s, %s, %s)
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (email, WORKFLOW_STATUS_PENDING, WORKFLOW_STATUS_DENIED, WORKFLOW_STATUS_APPROVED),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return get_profile_submission_draft(cursor, row[0])


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
          additional_info,
          submitted_by_email
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            draft_payload["additional_info"],
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


def create_registration_link(*, cursor, app, email, ttl_hours):
    invalidate_unused_tokens(cursor, email=email, action_type=ACTION_TYPE_REGISTRATION_LINK)
    raw_token, token_hash = generate_token_pair()
    expires_at = now_utc() + timedelta(hours=ttl_hours)
    cursor.execute(
        """
        INSERT INTO action_tokens (token_hash, action_type, email, expires_at)
        VALUES (%s, %s, %s, %s)
        """,
        (token_hash, ACTION_TYPE_REGISTRATION_LINK, email, expires_at),
    )
    return {
        "url": build_absolute_url(app, f"/perform/?token={raw_token}"),
        "expires_at": expires_at,
    }


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
          additional_info,
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
        "additional_info": row[12],
        "status": row[13],
        "social_links": [],
        "requested_event_ids": [],
        "requested_events": [],
    }

    cursor.execute(
        """
        SELECT pssp.social_platform_id, pssp.profile_name, sp.platform_name, sp.url_format
        FROM profile_submission_social_profiles pssp
        JOIN social_platforms sp ON sp.id = pssp.social_platform_id
        WHERE pssp.draft_id = %s
        ORDER BY pssp.sort_order, pssp.id
        """,
        (draft_id,),
    )
    draft["social_links"] = [
        {
            "social_platform_id": social_platform_id,
            "profile_name": profile_name,
            "platform_name": platform_name,
            "url_format": url_format,
        }
        for social_platform_id, profile_name, platform_name, url_format in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT rd.event_id, e.event_date, e.event_name
        FROM requested_dates rd
        JOIN events e ON e.id = rd.event_id
        WHERE rd.draft_id = %s
        ORDER BY e.event_date, rd.event_id
        """,
        (draft_id,),
    )
    requested_events = [
        {"event_id": row[0], "event_date": row[1].isoformat(), "event_name": row[2]}
        for row in cursor.fetchall()
    ]
    draft["requested_events"] = requested_events
    draft["requested_event_ids"] = [item["event_id"] for item in requested_events]
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

    upsert_artist_role(cursor, profile_id, draft["artist_bio"], True)
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


def attach_profile_to_draft(cursor, *, draft_id, profile_id):
    cursor.execute(
        """
        UPDATE profile_submission_drafts
        SET profile_id = %s
        WHERE id = %s
        """,
        (profile_id, draft_id),
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


def send_availability_confirmation_for_requested_date(app, cursor, *, requested_date_id, event_id):
    requested_date = get_requested_date_with_context(cursor, requested_date_id)
    if requested_date["event_id"] != event_id:
        raise ValueError("That performer request is not for this event.")
    if not requested_date["is_profile_approved"]:
        raise ValueError("Only approved performer requests can be emailed from this page.")
    if requested_date["status"] != "requested":
        raise ValueError("Only unconfirmed performer requests can be re-sent.")
    if not requested_date["email"]:
        raise ValueError("This performer request has no email address to send to.")

    settings = get_workflow_settings(cursor)
    invalidate_availability_tokens_for_requested_date(cursor, requested_date_id)
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
            requested_date["email"],
            requested_date["profile_id"],
            requested_date["draft_id"],
            requested_date["id"],
            requested_date["event_id"],
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
            requested_date["email"],
            requested_date["profile_id"],
            requested_date["draft_id"],
            requested_date["id"],
            requested_date["event_id"],
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
        email=requested_date["email"],
        display_name=requested_date["display_name"],
        event_name=requested_date["event_name"],
        event_date=requested_date["event_date"],
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
        (requested_date["id"],),
    )

    return {"display_name": requested_date["display_name"], "email": requested_date["email"]}


def send_due_admin_selection_emails(app, run_date=None):
    sent_count = 0

    with connect() as connection:
        with connection.cursor() as cursor:
            settings = get_workflow_settings(cursor)
            target_date = resolve_target_event_date(
                run_date=run_date,
                lead_days=settings["final_selection_lead_days"],
            )
            due_events = get_due_admin_selection_events(cursor, target_date)
            admins = get_admin_emails(cursor)

            for event in due_events:
                if not admins:
                    continue

                for admin in admins:
                    raw_token, token_hash = generate_token_pair()
                    expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])
                    cursor.execute(
                        """
                        INSERT INTO action_tokens (token_hash, action_type, email, profile_id, event_id, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            token_hash,
                            ACTION_TYPE_ADMIN_SELECTION,
                            admin["email"],
                            admin["profile_id"],
                            event["event_id"],
                            expires_at,
                        ),
                    )
                    selection_url = build_absolute_url(
                        app, f"/perform/admin/?token={raw_token}"
                    )
                    send_admin_selection_email(
                        admin_email=admin["email"],
                        event_name=event["event_name"],
                        event_date=event["event_date"],
                        selection_url=selection_url,
                        expires_at=expires_at,
                    )
                    sent_count += 1

                cursor.execute(
                    """
                    UPDATE events
                    SET admin_selection_email_sent_at = now()
                    WHERE id = %s
                    """,
                    (event["event_id"],),
                )

        connection.commit()

    return {
        "target_event_date": target_date.isoformat(),
        "admin_selection_emails_sent": sent_count,
    }


def get_due_admin_selection_events(cursor, target_date):
    cursor.execute(
        """
        SELECT id, event_name, event_date
        FROM events
        WHERE event_date = %s
          AND type_id = %s
          AND admin_selection_email_sent_at IS NULL
        ORDER BY id
        """,
        (target_date, OPEN_MIC_EVENT_TYPE_ID),
    )
    return [
        {"event_id": row[0], "event_name": row[1], "event_date": row[2].isoformat()}
        for row in cursor.fetchall()
    ]


def get_upcoming_open_mic_events(cursor):
    cursor.execute(
        """
        SELECT id, event_name, event_date
        FROM events
        WHERE type_id = %s
          AND event_date >= CURRENT_DATE
        ORDER BY event_date, id
        """,
        (OPEN_MIC_EVENT_TYPE_ID,),
    )
    return [
        {"event_id": row[0], "event_name": row[1], "event_date": row[2].isoformat()}
        for row in cursor.fetchall()
    ]


def get_open_mic_event_for_admin_selection(cursor, event_id):
    cursor.execute(
        """
        SELECT id, event_name, event_date
        FROM events
        WHERE id = %s
          AND type_id = %s
          AND event_date >= CURRENT_DATE
        """,
        (event_id, OPEN_MIC_EVENT_TYPE_ID),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That event date is not available for admin selection.")
    return {"event_id": row[0], "event_name": row[1], "event_date": row[2].isoformat()}


def get_admin_selection_lock_minutes():
    value = normalize_text(os.getenv("ADMIN_SELECTION_LOCK_MINUTES"))
    if not value:
        return DEFAULT_ADMIN_SELECTION_LOCK_MINUTES
    if not value.isdigit():
        return DEFAULT_ADMIN_SELECTION_LOCK_MINUTES
    minutes = int(value)
    if minutes <= 0:
        return DEFAULT_ADMIN_SELECTION_LOCK_MINUTES
    return minutes


def get_profile_lock_display_name(cursor, profile_id):
    cursor.execute(
        """
        SELECT first_name, last_name, display_name, email
        FROM profiles
        WHERE id = %s
        """,
        (profile_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    first_name, last_name, display_name, email = row
    full_name = " ".join(part for part in [first_name, last_name] if normalize_text(part))
    if full_name:
        return full_name
    if normalize_text(display_name):
        return display_name
    if normalize_text(email):
        return email
    return f"profile #{profile_id}"


def get_active_admin_selection_lock(cursor, event_id):
    cursor.execute(
        """
        SELECT event_id, locked_by_profile_id, lock_started_at, lock_expires_at
        FROM admin_selection_locks
        WHERE event_id = %s
          AND lock_expires_at > now()
        """,
        (event_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "event_id": row[0],
        "locked_by_profile_id": row[1],
        "lock_started_at": row[2],
        "lock_expires_at": row[3],
        "locked_by_name": get_profile_lock_display_name(cursor, row[1]),
    }


def acquire_admin_selection_lock(cursor, *, event_id, profile_id, lock_minutes):
    cursor.execute(
        """
        DELETE FROM admin_selection_locks
        WHERE lock_expires_at <= now()
        """
    )

    lock_expires_at = now_utc() + timedelta(minutes=lock_minutes)
    cursor.execute(
        """
        INSERT INTO admin_selection_locks (event_id, locked_by_profile_id, lock_started_at, lock_expires_at)
        VALUES (%s, %s, now(), %s)
        ON CONFLICT (event_id)
        DO UPDATE SET
          locked_by_profile_id = EXCLUDED.locked_by_profile_id,
          lock_started_at = CASE
            WHEN admin_selection_locks.locked_by_profile_id = EXCLUDED.locked_by_profile_id
              THEN admin_selection_locks.lock_started_at
            ELSE now()
          END,
          lock_expires_at = EXCLUDED.lock_expires_at
        WHERE admin_selection_locks.locked_by_profile_id = EXCLUDED.locked_by_profile_id
           OR admin_selection_locks.lock_expires_at <= now()
        RETURNING event_id, locked_by_profile_id, lock_started_at, lock_expires_at
        """,
        (event_id, profile_id, lock_expires_at),
    )
    row = cursor.fetchone()
    if row:
        return {
            "acquired": True,
            "event_id": row[0],
            "locked_by_profile_id": row[1],
            "lock_started_at": row[2],
            "lock_expires_at": row[3],
            "locked_by_name": get_profile_lock_display_name(cursor, row[1]),
        }

    lock = get_active_admin_selection_lock(cursor, event_id)
    if not lock:
        return {
            "acquired": False,
            "event_id": event_id,
            "locked_by_profile_id": None,
            "lock_expires_at": None,
            "locked_by_name": None,
        }

    return {
        "acquired": False,
        "event_id": lock["event_id"],
        "locked_by_profile_id": lock["locked_by_profile_id"],
        "lock_expires_at": lock["lock_expires_at"],
        "locked_by_name": lock["locked_by_name"],
    }


def release_admin_selection_lock(cursor, *, event_id, profile_id):
    cursor.execute(
        """
        DELETE FROM admin_selection_locks
        WHERE event_id = %s
          AND locked_by_profile_id = %s
        """,
        (event_id, profile_id),
    )


def get_admin_emails(cursor):
    cursor.execute(
        """
        SELECT p.id, p.email
        FROM profiles p
        WHERE p.is_admin = true
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


def get_admin_profile_by_email(cursor, email):
    cursor.execute(
        """
        SELECT p.id, p.email
        FROM profiles p
        WHERE lower(p.email) = lower(%s)
          AND p.is_admin = true
          AND EXISTS (
            SELECT 1
            FROM profile_roles pr
            WHERE pr.profile_id = p.id
              AND pr.role = 'volunteer'
          )
        ORDER BY p.id
        """,
        (email,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError("Multiple admin profiles already use that email address.")
    return {"profile_id": rows[0][0], "email": rows[0][1]}


def get_event_selection_context(cursor, event_id):
    cursor.execute(
        """
        SELECT id, event_name, event_date
        FROM events
        WHERE id = %s
        """,
        (event_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That event no longer exists.")
    return {"event_id": row[0], "event_name": row[1], "event_date": row[2].isoformat()}


def get_admin_selection_candidates(cursor, event_id):
    cursor.execute(
        """
        SELECT
          rd.id,
          d.id,
          p.id,
          d.display_name,
          d.email,
          d.contact_phone,
          rd.status,
          COALESCE(sel.status, ''),
          sel.slot_number
        FROM requested_dates rd
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        JOIN profiles p
          ON p.id = d.profile_id
        LEFT JOIN event_performer_selections sel
          ON sel.event_id = rd.event_id
         AND sel.profile_id = p.id
        WHERE rd.event_id = %s
          AND rd.status IN ('requested', 'availability_confirmed', 'availability_cancelled')
          AND p.is_profile_approved = true
        ORDER BY d.display_name, rd.id
        """,
        (event_id,),
    )
    return [
        {
            "requested_date_id": row[0],
            "draft_id": row[1],
            "profile_id": row[2],
            "display_name": row[3],
            "email": row[4],
            "contact_phone": row[5],
            "availability_status": row[6],
            "selection_status": row[7] or None,
            "slot_number": row[8],
        }
        for row in cursor.fetchall()
    ]


def is_admin_selection_candidate_eligible(candidate):
    return candidate.get("availability_status") == "availability_confirmed"


def save_admin_selection(cursor, *, event_id, admin_profile_id, candidates, candidate_statuses, max_performers):
    candidate_by_requested_date_id = {item["requested_date_id"]: item for item in candidates}
    invalid_ids = [item for item in candidate_statuses if item not in candidate_by_requested_date_id]
    if invalid_ids:
        raise ValueError("One or more selected performers are invalid for this event.")

    selected_requested_date_ids = [
        item["requested_date_id"]
        for item in candidates
        if is_admin_selection_candidate_eligible(item)
        if candidate_statuses.get(item["requested_date_id"]) == LINEUP_STATUS_SELECTED
    ]
    if len(selected_requested_date_ids) > max_performers:
        raise ValueError(f"You can select at most {max_performers} performers.")

    selected_profile_ids = []
    for item in candidates:
        if not is_admin_selection_candidate_eligible(item):
            continue
        status = candidate_statuses.get(item["requested_date_id"], LINEUP_STATUS_STANDBY)
        if status == LINEUP_STATUS_SELECTED:
            slot_number = selected_requested_date_ids.index(item["requested_date_id"]) + 1
            selected_profile_ids.append(item["profile_id"])
        else:
            slot_number = None

        cursor.execute(
            """
            INSERT INTO event_performer_selections (
              event_id,
              profile_id,
              requested_date_id,
              slot_number,
              status,
              selected_at,
              selected_by_profile_id
            )
            VALUES (%s, %s, %s, %s, %s, now(), %s)
            ON CONFLICT (event_id, profile_id)
            DO UPDATE SET
              requested_date_id = EXCLUDED.requested_date_id,
              slot_number = EXCLUDED.slot_number,
              status = EXCLUDED.status,
              selected_at = now(),
              selected_by_profile_id = EXCLUDED.selected_by_profile_id
            """,
            (
                event_id,
                item["profile_id"],
                item["requested_date_id"],
                slot_number,
                status,
                admin_profile_id,
            ),
        )
        if status == LINEUP_STATUS_SELECTED:
            cursor.execute(
                """
                UPDATE requested_dates
                SET
                  selected_at = now(),
                  selected_by_profile_id = %s
                WHERE id = %s
                """,
                (admin_profile_id, item["requested_date_id"]),
            )

    if selected_profile_ids:
        settings = get_workflow_settings(cursor)
        apply_cooldown_backups_for_selected(
            cursor,
            event_id=event_id,
            selected_profile_ids=selected_profile_ids,
            admin_profile_id=admin_profile_id,
            cooldown_events=settings["performer_request_cooldown_events"],
        )


def apply_cooldown_backups_for_selected(cursor, *, event_id, selected_profile_ids, admin_profile_id, cooldown_events):
    if not selected_profile_ids or cooldown_events <= 0:
        return

    cursor.execute(
        """
        WITH current_event AS (
          SELECT event_date, id
          FROM events
          WHERE id = %s
        )
        SELECT e.id
        FROM events e
        CROSS JOIN current_event ce
        WHERE e.type_id = %s
          AND (
            e.event_date > ce.event_date
            OR (e.event_date = ce.event_date AND e.id > ce.id)
          )
        ORDER BY e.event_date, e.id
        LIMIT %s
        """,
        (event_id, OPEN_MIC_EVENT_TYPE_ID, cooldown_events),
    )
    future_event_ids = [row[0] for row in cursor.fetchall()]
    if not future_event_ids:
        return

    cursor.execute(
        """
        SELECT
          rd.event_id,
          d.profile_id,
          rd.id
        FROM requested_dates rd
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        WHERE d.profile_id = ANY(%s)
          AND rd.event_id = ANY(%s)
          AND rd.status IN ('requested', 'availability_confirmed')
          AND d.status = 'approved'
        """,
        (selected_profile_ids, future_event_ids),
    )
    for future_event_id, profile_id, requested_date_id in cursor.fetchall():
        cursor.execute(
            """
            INSERT INTO event_performer_selections (
              event_id,
              profile_id,
              requested_date_id,
              slot_number,
              status,
              selected_at,
              selected_by_profile_id
            )
            VALUES (%s, %s, %s, NULL, 'reserve', now(), %s)
            ON CONFLICT (event_id, profile_id)
            DO UPDATE SET
              requested_date_id = EXCLUDED.requested_date_id,
              slot_number = NULL,
              status = CASE
                WHEN event_performer_selections.status = 'selected' THEN 'reserve'
                ELSE 'reserve'
              END,
              selected_at = now(),
              selected_by_profile_id = EXCLUDED.selected_by_profile_id
            """,
            (future_event_id, profile_id, requested_date_id, admin_profile_id),
        )


def get_current_selected_lineup(cursor, event_id):
    cursor.execute(
        """
        SELECT p.display_name, sel.slot_number
        FROM event_performer_selections sel
        JOIN profiles p
          ON p.id = sel.profile_id
        WHERE sel.event_id = %s
          AND sel.status = 'selected'
        ORDER BY sel.slot_number NULLS LAST, p.display_name
        """,
        (event_id,),
    )
    return [{"display_name": row[0], "slot_number": row[1]} for row in cursor.fetchall()]


def get_backup_candidates(cursor, event_id):
    cursor.execute(
        """
        SELECT
          rd.id,
          p.id,
          d.display_name,
          d.email,
          d.contact_phone,
          sel.status
        FROM event_performer_selections sel
        JOIN requested_dates rd
          ON rd.id = sel.requested_date_id
        JOIN profile_submission_drafts d
          ON d.id = rd.draft_id
        JOIN profiles p
          ON p.id = sel.profile_id
        WHERE sel.event_id = %s
          AND sel.status IN ('standby', 'reserve')
        ORDER BY CASE sel.status WHEN 'standby' THEN 0 ELSE 1 END, d.display_name, rd.id
        """,
        (event_id,),
    )
    return [
        {
            "requested_date_id": row[0],
            "profile_id": row[1],
            "display_name": row[2],
            "email": row[3],
            "contact_phone": row[4],
            "selection_status": row[5],
        }
        for row in cursor.fetchall()
    ]


def promote_backup_selection(cursor, *, event_id, requested_date_id, admin_profile_id):
    backups = get_backup_candidates(cursor, event_id)
    backup = next((item for item in backups if item["requested_date_id"] == requested_date_id), None)
    if not backup:
        raise ValueError("That standby performer is not available for promotion.")

    cursor.execute(
        """
        SELECT COALESCE(MAX(slot_number), 0) + 1
        FROM event_performer_selections
        WHERE event_id = %s
          AND status = 'selected'
        """,
        (event_id,),
    )
    next_slot = cursor.fetchone()[0]

    cursor.execute(
        """
        UPDATE event_performer_selections
        SET
          status = 'selected',
          slot_number = %s,
          selected_at = now(),
          selected_by_profile_id = %s
        WHERE event_id = %s
          AND requested_date_id = %s
        """,
        (next_slot, admin_profile_id, event_id, requested_date_id),
    )
    cursor.execute(
        """
        UPDATE requested_dates
        SET
          selected_at = now(),
          selected_by_profile_id = %s
        WHERE id = %s
        """,
        (admin_profile_id, requested_date_id),
    )

    return {
        "requested_date_id": requested_date_id,
        "display_name": backup["display_name"],
        "email": backup["email"],
        "contact_phone": backup["contact_phone"],
        "slot_number": next_slot,
    }


def invalidate_backup_selection_tokens_for_event(cursor, event_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE event_id = %s
          AND action_type = %s
          AND used_at IS NULL
        """,
        (event_id, ACTION_TYPE_BACKUP_SELECTION),
    )


def handle_selection_cancellation_if_needed(app, cursor, requested_date):
    if requested_date["profile_id"] is None:
        return

    cursor.execute(
        """
        SELECT status
        FROM event_performer_selections
        WHERE event_id = %s
          AND profile_id = %s
        """,
        (requested_date["event_id"], requested_date["profile_id"]),
    )
    row = cursor.fetchone()
    if not row:
        return

    selection_status = row[0]
    if selection_status == "standby":
        cursor.execute(
            """
            UPDATE event_performer_selections
            SET status = 'cancelled'
            WHERE event_id = %s
              AND profile_id = %s
            """,
            (requested_date["event_id"], requested_date["profile_id"]),
        )
        return

    if selection_status != "selected":
        return

    cursor.execute(
        """
        UPDATE event_performer_selections
        SET status = 'cancelled'
        WHERE event_id = %s
          AND profile_id = %s
        """,
        (requested_date["event_id"], requested_date["profile_id"]),
    )

    moderator_emails = get_moderator_emails(cursor)
    if not moderator_emails:
        return

    event = get_event_selection_context(cursor, requested_date["event_id"])
    backups = get_backup_candidates(cursor, requested_date["event_id"])
    if backups:
        settings = get_workflow_settings(cursor)
        invalidate_backup_selection_tokens_for_event(cursor, requested_date["event_id"])
        for moderator in moderator_emails:
            raw_token, token_hash = generate_token_pair()
            expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])
            cursor.execute(
                """
                INSERT INTO action_tokens (token_hash, action_type, email, profile_id, event_id, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    token_hash,
                    ACTION_TYPE_BACKUP_SELECTION,
                    moderator["email"],
                    moderator["profile_id"],
                    requested_date["event_id"],
                    expires_at,
                ),
            )
            backup_url = build_absolute_url(
                app, f"/api/forms/performer-registration/backup-selection?token={raw_token}"
            )
            send_backup_selection_email(
                moderator_email=moderator["email"],
                event_name=event["event_name"],
                event_date=event["event_date"],
                backup_url=backup_url,
                backups=backups,
                expires_at=expires_at,
            )
        return

    if get_selected_count(cursor, requested_date["event_id"]) < get_workflow_settings(cursor)["max_performers_per_event"]:
        send_open_slot_alert_email(
            moderator_emails=moderator_emails,
            event_name=event["event_name"],
            event_date=event["event_date"],
            selected_count=get_selected_count(cursor, requested_date["event_id"]),
            slot_count=get_workflow_settings(cursor)["max_performers_per_event"],
        )


def get_selected_count(cursor, event_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM event_performer_selections
        WHERE event_id = %s
          AND status = 'selected'
        """,
        (event_id,),
    )
    return cursor.fetchone()[0]


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
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(email, "EMOM performer registration link", body)


def send_moderation_emails(
    app, *, draft_id, email, draft_payload, existing_profile, matched_by, moderation_links, current_status_summary
):
    if not moderation_links:
        return

    requested_events = "\n".join(
        f"- {item['event_date']}: {item['event_name']}"
        for item in draft_payload.get("requested_events", [])
    ) or "- none selected"
    social_lines = format_social_links_for_moderation(draft_payload["social_links"], empty_text="- none provided")
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
            f"Bio:\n{draft_payload['artist_bio'] or '(none)'}\n\n"
            f"Additional info (not shown on profile):\n{draft_payload.get('additional_info') or '(none)'}\n\n"
            f"Requested event dates:\n{requested_events}\n"
            f"Social links:\n{social_lines}\n\n"
            f"Approve: {item['approve_url']}\n"
            f"Deny: {item['deny_url']}\n"
            f"\nCurrent status:\n{current_status_summary}\n"
        )
        send_mail(item["email"], f"EMOM performer profile moderation request #{draft_id}", body)


def format_existing_profile_for_moderation(existing_profile, matched_by):
    if not existing_profile:
        return "Existing profile match: none. This will create a new profile if approved.\n\n"

    social_lines = format_social_links_for_moderation(
        existing_profile["social_links"], empty_text="- none on current live profile"
    )

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
        f"Existing bio:\n{existing_profile['artist_bio'] or '(none)'}\n"
        f"Existing social links:\n{social_lines}\n\n"
        "Submitted draft:\n"
    )


def format_social_links_for_moderation(social_links, *, empty_text):
    lines = []
    for item in social_links:
        platform_name = item.get("platform_name") or f"platform #{item['social_platform_id']}"
        profile_name = item["profile_name"]
        url_format = item.get("url_format")
        if url_format:
            lines.append(f"- {platform_name}: {url_format.replace('{profileName}', profile_name)}")
        else:
            lines.append(f"- {platform_name}: {profile_name}")
    return "\n".join(lines) or empty_text


def format_requested_events_for_email(requested_events, *, empty_text):
    return "\n".join(
        f"- {item['event_date']}: {item['event_name']}"
        for item in requested_events
    ) or empty_text


def format_selection_status_label(status):
    if status == "standby":
        return "standby"
    if status == "reserve":
        return "reserve"
    if status:
        return status.replace("_", " ")
    return "-"


def format_availability_status_label(status):
    labels = {
        "requested": "unconfirmed",
        "availability_confirmed": "confirmed",
        "availability_cancelled": "cancelled",
    }
    return labels.get(status, status.replace("_", " ") if status else "-")


def render_admin_status_option(status, current_status):
    selected_status = current_status or LINEUP_STATUS_STANDBY
    selected_attr = " selected" if status == selected_status else ""
    return f"<option value=\"{html.escape(status)}\"{selected_attr}>{html.escape(format_selection_status_label(status))}</option>"


def render_admin_confirmation_link(raw_token, requested_date_id):
    token = quote(raw_token, safe="")
    return (
        f"/api/forms/performer-registration/admin-selection/send-confirmation"
        f"?token={token}&requested_date_id={requested_date_id}"
    )


def get_upcoming_event_status_summary(cursor):
    cursor.execute(
        """
        SELECT id, event_date, event_name
        FROM events
        WHERE type_id = %s
          AND event_date >= CURRENT_DATE
        ORDER BY event_date, id
        LIMIT 1
        """,
        (OPEN_MIC_EVENT_TYPE_ID,),
    )
    next_event = cursor.fetchone()
    if not next_event:
        return "- No upcoming Open Mic dates found."

    event_id, event_date, event_name = next_event
    cursor.execute(
        """
        WITH ranked_rows AS (
          SELECT
            e.event_date,
            e.event_name,
            COALESCE(p.display_name, d.display_name) AS artist_name,
            d.status AS profile_status,
            rd.status AS requested_date_status,
            COALESCE(sel.status, '') AS lineup_status,
            ROW_NUMBER() OVER (
              PARTITION BY e.id, COALESCE(d.profile_id::text, lower(d.email))
              ORDER BY d.submitted_at DESC, d.id DESC, rd.id DESC
            ) AS row_rank
          FROM events e
          LEFT JOIN requested_dates rd
            ON rd.event_id = e.id
          LEFT JOIN profile_submission_drafts d
            ON d.id = rd.draft_id
           AND d.status <> 'superseded'
          LEFT JOIN profiles p
            ON p.id = d.profile_id
          LEFT JOIN event_performer_selections sel
            ON sel.event_id = e.id
           AND sel.profile_id = d.profile_id
          WHERE e.id = %s
            AND (rd.id IS NULL OR d.id IS NOT NULL)
        )
        SELECT
          event_date,
          event_name,
          artist_name,
          profile_status,
          requested_date_status,
          lineup_status
        FROM ranked_rows
        WHERE row_rank = 1
        ORDER BY lower(COALESCE(artist_name, ''))
        """,
        (event_id,),
    )
    rows = cursor.fetchall()
    return format_upcoming_event_status_summary(rows, event_date=event_date, event_name=event_name)


def format_upcoming_event_status_summary(rows, *, event_date, event_name):
    if not rows:
        return f"{event_date.isoformat()} | {event_name}\n(no current registrations)"

    lines = []
    header = f"{'Artist':24}  {'Profile':10}  {'Request':22}  {'Lineup':10}"
    divider = f"{'-' * 24}  {'-' * 10}  {'-' * 22}  {'-' * 10}"
    lines.append(f"{event_date.isoformat()} | {event_name}")
    lines.append(header)
    lines.append(divider)

    for _, _, artist_name, profile_status, requested_date_status, lineup_status in rows:
        if artist_name:
            artist_cell = artist_name[:24].ljust(24)
            profile_cell = (profile_status or "-")[:10].ljust(10)
            request_cell = (requested_date_status or "-")[:22].ljust(22)
            lineup_cell = (lineup_status or "-")[:10].ljust(10)
            lines.append(f"{artist_cell}  {profile_cell}  {request_cell}  {lineup_cell}")
        else:
            lines.append(f"{'(no current registrations)':24}  {'-':10}  {'-':22}  {'-':10}")

    return "\n".join(lines)


def send_profile_approved_email(app, email, *, requested_events, final_selection_lead_days):
    requested_dates_text = format_requested_events_for_email(
        requested_events, empty_text="- no requested dates recorded"
    )
    body = (
        "Your performer profile has been approved, and your requested performance dates have been noted.\n\n"
        f"Requested dates:\n{requested_dates_text}\n\n"
        "We will be in touch once we have made our final selection, "
        f"{final_selection_lead_days} days before the next event date.\n"
    )
    send_mail(email, "EMOM performer profile approved", body)


def send_profile_denied_email(app, email, reason, *, edit_link=None):
    body = (
        "Your performer profile submission was not approved at this stage.\n\n"
        f"Reason:\n{reason}\n"
    )
    if edit_link:
        body += (
            "\nYou can use the link below to review your details, make changes, and submit again.\n\n"
            f"{edit_link['url']}\n\n"
            f"This link expires at {format_link_expiry_local(edit_link['expires_at'])}.\n"
        )
    send_mail(email, "EMOM performer profile update", body)


def send_availability_email(*, email, display_name, event_name, event_date, confirm_url, cancel_url, expires_at):
    body = (
        f"Hello {display_name or 'performer'},\n\n"
        f"You previously registered interest in playing at {event_name} on {event_date}.\n"
        "Please use one of the links below to confirm or cancel your availability.\n\n"
        f"Confirm availability: {confirm_url}\n"
        f"Cancel availability: {cancel_url}\n\n"
        f"These links expire at {format_link_expiry_local(expires_at)}.\n"
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


def send_admin_selection_email(*, admin_email, event_name, event_date, selection_url, expires_at):
    body = (
        f"The final lineup selection window is now open for {event_name} on {event_date}.\n\n"
        f"Open selection page: {selection_url}\n\n"
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(admin_email, f"EMOM lineup selection for {event_name}", body)


def send_selected_performer_emails(event, candidates, selected_requested_date_ids):
    selected_set = set(selected_requested_date_ids)
    for item in candidates:
        if item["requested_date_id"] not in selected_set:
            continue
        body = (
            f"Your performance slot for {event['event_name']} on {event['event_date']} has been confirmed.\n"
        )
        send_mail(item["email"], f"EMOM performance confirmed for {event['event_name']}", body)


def send_backup_selection_email(*, moderator_email, event_name, event_date, backup_url, backups, expires_at):
    backup_lines = "\n".join(
        f"- {item['display_name']} <{item['email']}> [{format_selection_status_label(item.get('selection_status'))}]"
        for item in backups
    ) or "- none"
    body = (
        f"A selected performer has cancelled for {event_name} on {event_date}.\n\n"
        "Current standby/reserve pool:\n"
        f"{backup_lines}\n\n"
        f"Choose a standby performer to promote: {backup_url}\n\n"
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(moderator_email, f"EMOM standby selection needed for {event_name}", body)


def send_backup_promoted_email(event, promoted):
    body = (
        f"You have been promoted from standby to the confirmed lineup for {event['event_name']} on {event['event_date']}.\n"
    )
    send_mail(
        promoted["email"],
        f"EMOM performance confirmed for {event['event_name']}",
        body,
    )


def send_open_slot_alert_email(*, moderator_emails, event_name, event_date, selected_count, slot_count):
    body = (
        f"There is now an open slot for {event_name} on {event_date}.\n\n"
        f"Confirmed performers remaining: {selected_count}\n"
        f"Target slot count: {slot_count}\n"
        "There are currently no standby or reserve performers available for this event.\n"
    )
    for moderator in moderator_emails:
        send_mail(
            moderator["email"],
            f"EMOM open slot alert for {event_name}",
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
      .checkbox { display: flex; gap: 0.5rem; align-items: flex-start; margin-top: 1rem; }
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
      <label class="checkbox">
        <input type="checkbox" name="include_edit_link" value="1" checked>
        <span>Include a fresh one-time edit link in the email to the performer</span>
      </label>
      <button type="submit">Send denial</button>
    </form>
  </body>
</html>
"""
    )


def render_admin_selection_form(
    raw_token,
    event,
    candidates,
    max_performers,
    notice_message=None,
    active_editor_name=None,
):
    candidate_rows = "\n".join(
        (
            "<tr>"
            f"<td><strong>{html.escape(item['display_name'])}</strong></td>"
            f"<td>{html.escape(item['email'] or '')}<br>{html.escape(item['contact_phone'] or '')}</td>"
            f"<td>{html.escape(format_availability_status_label(item.get('availability_status')))}</td>"
            f"<td>{html.escape(format_selection_status_label(item.get('selection_status')))}</td>"
            "<td>"
            + (
                (
                    f"<select name=\"status_{item['requested_date_id']}\" data-lineup-status>"
                    f"{render_admin_status_option(LINEUP_STATUS_SELECTED, item.get('selection_status'))}"
                    f"{render_admin_status_option(LINEUP_STATUS_STANDBY, item.get('selection_status'))}"
                    f"{render_admin_status_option(LINEUP_STATUS_RESERVE, item.get('selection_status'))}"
                    "</select>"
                )
                if is_admin_selection_candidate_eligible(item)
                else "<small>Selection available after confirmation.</small>"
            )
            + "</td>"
            "<td>"
            + (
                (
                    f"<a href=\"{html.escape(render_admin_confirmation_link(raw_token, item['requested_date_id']), quote=True)}\">Send confirmation email</a>"
                )
                if item.get("availability_status") == "requested"
                else "-"
            )
            + "</td>"
            "</tr>"
        )
        for item in candidates
    ) or "<tr><td colspan=\"6\">No performer requests are available for this event.</td></tr>"

    notice_block = (
        f"<div class=\"summary\" style=\"background:#edf7ed;border-color:#c4e3c4;\">{html.escape(notice_message)}</div>"
        if notice_message
        else ""
    )
    lock_notice = (
        f"<div class=\"summary lock-banner\"><strong>Editing lock active:</strong> {html.escape(active_editor_name)} is currently editing this lineup.</div>"
        if active_editor_name
        else ""
    )

    return (
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Admin lineup selection</title>
    <style>
      body { font-family: sans-serif; max-width: 72rem; margin: 2rem auto; padding: 0 1rem; }
      .summary { padding: 0.75rem 1rem; background: #f3f3f3; border: 1px solid #ddd; margin: 1rem 0; }
      .lock-banner {
        background: #fff4d8;
        border-color: #efc96a;
        color: #4d3600;
        font-size: 1rem;
        font-weight: 600;
      }
      table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
      th, td { text-align: left; vertical-align: top; padding: 0.6rem; border-bottom: 1px solid #ddd; }
      select { width: 100%; max-width: 16rem; }
      button { margin-top: 1rem; }
    </style>
  </head>
  <body>
    <h1>Admin lineup selection</h1>
    <p><strong>Event:</strong> """
        + html.escape(event["event_name"])
        + """</p>
    <p><strong>Date:</strong> """
        + html.escape(event["event_date"])
        + """</p>
    """
        + notice_block
        + lock_notice
        + """
    <p>All requests for this event are shown below. Only confirmed performers can be assigned lineup status.</p>
    <div class="summary">
      <strong>Total selected to perform:</strong>
      <span id="selected-count">0</span>
      <span> / """
        + html.escape(str(max_performers))
        + """</span>
    </div>
    <form method="post">
      <input type="hidden" name="token" value=\""""
        + html.escape(raw_token, quote=True)
        + """\">
      <table>
        <thead>
          <tr>
            <th>Artist</th>
            <th>Contact</th>
            <th>Availability</th>
            <th>Current lineup</th>
            <th>Set lineup status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>"""
        + candidate_rows
        + """</tbody>
      </table>
      <button type="submit">Save lineup</button>
    </form>
    <script>
      (function () {
        const selects = [...document.querySelectorAll('[data-lineup-status]')];
        const countNode = document.getElementById('selected-count');
        const token = """
        + json.dumps(raw_token)
        + """;
        const heartbeatUrl = `/api/forms/performer-registration/admin-selection/lock?token=${encodeURIComponent(token)}`;
        const releaseUrl = `/api/forms/performer-registration/admin-selection/lock/release?token=${encodeURIComponent(token)}`;
        function updateSelectedCount() {
          const count = selects.filter((node) => node.value === 'selected').length;
          countNode.textContent = String(count);
        }
        async function refreshLock() {
          try {
            const response = await fetch(heartbeatUrl, {
              method: 'POST',
              credentials: 'same-origin',
              keepalive: true
            });
            if (response.status === 409) {
              const payload = await response.json().catch(() => ({}));
              window.alert(payload.error || 'Another admin is now editing this lineup.');
              window.location.reload();
            }
          } catch (error) {
            // Ignore transient network issues and keep the page usable.
          }
        }
        selects.forEach((node) => node.addEventListener('change', updateSelectedCount));
        updateSelectedCount();
        window.setInterval(refreshLock, 60000);
        window.addEventListener('beforeunload', () => {
          if (navigator.sendBeacon) {
            navigator.sendBeacon(releaseUrl);
          }
        });
      }());
    </script>
  </body>
</html>
"""
    )


def render_backup_selection_form(raw_token, event, current_selected, backups):
    selected_rows = "\n".join(
        f"<li>{html.escape(item['display_name'])} (slot {item['slot_number']})</li>"
        for item in current_selected
    ) or "<li>No selected performers currently recorded.</li>"

    backup_rows = "\n".join(
        (
            "<label style=\"display:flex; gap:0.75rem; align-items:flex-start; margin-bottom:0.75rem;\">"
            f"<input type=\"radio\" name=\"requested_date_id\" value=\"{item['requested_date_id']}\" required>"
            f"<span><strong>{html.escape(item['display_name'])}</strong><br>"
            f"{html.escape(item['email'] or '')}<br>"
            f"{html.escape(item['contact_phone'] or '')}<br>"
            f"<small>Status: {html.escape(format_selection_status_label(item.get('selection_status')))}</small></span>"
            "</label>"
        )
        for item in backups
    ) or "<p>No standby performers are currently available.</p>"

    return (
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Standby selection</title>
    <style>
      body { font-family: sans-serif; max-width: 56rem; margin: 2rem auto; padding: 0 1rem; }
      button { margin-top: 1rem; }
    </style>
  </head>
  <body>
    <h1>Standby selection</h1>
    <p><strong>Event:</strong> """
        + html.escape(event["event_name"])
        + """</p>
    <p><strong>Date:</strong> """
        + html.escape(event["event_date"])
        + """</p>
    <h2>Current selected lineup</h2>
    <ul>"""
        + selected_rows
        + """</ul>
    <h2>Available standby/reserve performers</h2>
    <form method="post">
      <input type="hidden" name="token" value=\""""
        + html.escape(raw_token, quote=True)
        + """\">
      """
        + backup_rows
        + """
      <button type="submit">Promote standby performer</button>
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
