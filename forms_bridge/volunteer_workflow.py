import html
from datetime import timedelta

from flask import jsonify, request

from forms_bridge.db import connect
from forms_bridge.performer_workflow import (
    WORKFLOW_STATUS_APPROVED,
    WORKFLOW_STATUS_DENIED,
    WORKFLOW_STATUS_PENDING,
    attach_profile_to_draft,
    build_absolute_url,
    error_response,
    finalize_draft_status,
    format_link_expiry_local,
    generate_token_pair,
    get_action_token,
    get_existing_profile_by_email,
    get_existing_profile_for_submission,
    get_latest_prefill_submission_by_email,
    get_moderator_emails,
    get_profile_submission_draft,
    get_social_platforms,
    get_workflow_settings,
    html_error_page,
    html_success_page,
    insert_profile_submission_draft,
    insert_profile_submission_social_links,
    invalidate_unused_tokens,
    mark_action_token_used,
    normalize_boolean,
    normalize_email,
    normalize_text,
    now_utc,
    record_moderation_action,
    render_token_page,
    replace_profile_social_links,
    send_mail,
    serialize_prefill_profile,
    serialize_profile,
    supersede_pending_drafts,
)


ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK = "volunteer_registration_link"
ACTION_TYPE_VOLUNTEER_MODERATION_APPROVE = "volunteer_moderation_approve"
ACTION_TYPE_VOLUNTEER_MODERATION_DENY = "volunteer_moderation_deny"
ACTION_TYPE_VOLUNTEER_CLAIMS_LINK = "volunteer_claims_link"

CLAIM_STATUS_SELECTED = "selected"
CLAIM_STATUS_STANDBY = "standby"
CLAIM_STATUS_CANCELLED = "cancelled"
GENERAL_CLAIM_STATUS_ACTIVE = "active"
GENERAL_CLAIM_STATUS_WITHDRAWN = "withdrawn"


def register_volunteer_workflow_routes(app):
    @app.route("/api/forms/volunteer-registration/start", methods=["OPTIONS"])
    def volunteer_registration_start_options():
        return ("", 204)

    @app.route("/api/forms/volunteer-registration/start", methods=["POST"])
    def volunteer_registration_start():
        try:
            payload = get_json_payload()
            email = normalize_email(payload.get("email"))
            if not email:
                return error_response("A valid email address is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    settings = get_workflow_settings(cursor)
                    invalidate_unused_tokens(
                        cursor,
                        email=email,
                        action_type=ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK,
                    )
                    raw_token, token_hash = generate_token_pair()
                    expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])

                    cursor.execute(
                        """
                        INSERT INTO action_tokens (token_hash, action_type, email, expires_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            token_hash,
                            ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK,
                            email,
                            expires_at,
                        ),
                    )

                send_volunteer_registration_email(app, email, raw_token, expires_at)

            return jsonify({"ok": True}), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer registration start failed")
            return error_response("Unable to start volunteer registration right now.", 500)

    @app.route("/api/forms/volunteer-registration/session", methods=["GET"])
    def volunteer_registration_session():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return error_response("A registration token is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(
                        cursor,
                        raw_token,
                        ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK,
                    )
                    email = token_row["email"]
                    live_profile = get_existing_profile_by_email(cursor, email)
                    live_profile = apply_volunteer_role_bio_to_profile(cursor, live_profile)
                    latest_draft = get_latest_volunteer_prefill_submission_by_email(cursor, email)
                    profile = serialize_prefill_profile(latest_draft) if latest_draft else live_profile
                    social_platforms = get_social_platforms(cursor)
                    available_events = get_future_events(cursor)
                    role_availability = get_role_availability_by_event(
                        cursor,
                        profile_id=profile["id"] if profile and profile.get("id") else None,
                    )
                    general_role_options = get_general_role_options(
                        cursor,
                        profile_id=profile["id"] if profile and profile.get("id") else None,
                    )
                    existing_claims = get_active_claim_pairs(
                        cursor,
                        profile_id=profile["id"] if profile and profile.get("id") else None,
                    )
                    existing_general_claims = get_active_general_claim_keys(
                        cursor,
                        profile_id=profile["id"] if profile and profile.get("id") else None,
                    )

            return jsonify(
                {
                    "ok": True,
                    "email": email,
                    "profile": serialize_profile(profile),
                    "social_platforms": social_platforms,
                    "available_events": available_events,
                    "role_availability": role_availability,
                    "general_role_options": general_role_options,
                    "existing_claims": existing_claims,
                    "existing_general_claims": existing_general_claims,
                }
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer registration session lookup failed")
            return error_response("Unable to load volunteer registration right now.", 500)

    @app.route("/api/forms/volunteer-registration/submit", methods=["OPTIONS"])
    def volunteer_registration_submit_options():
        return ("", 204)

    @app.route("/api/forms/volunteer-registration/submit", methods=["POST"])
    def volunteer_registration_submit():
        try:
            payload = get_json_payload()
            raw_token = normalize_text(payload.get("token"))
            if not raw_token:
                return error_response("A registration token is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(
                        cursor,
                        raw_token,
                        ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK,
                    )
                    email = token_row["email"]
                    settings = get_workflow_settings(cursor)
                    draft_payload = normalize_volunteer_submission_payload(payload, email)

                    profile, matched_by = get_existing_profile_for_submission(
                        cursor,
                        email=email,
                        display_name=draft_payload["display_name"],
                    )

                    future_event_ids = {event["id"] for event in get_future_events(cursor)}
                    ensure_claim_events_are_allowed(draft_payload["event_role_claims"], future_event_ids)
                    ensure_event_roles_exist(cursor, [item["role_key"] for item in draft_payload["event_role_claims"]])
                    ensure_general_roles_exist(cursor, draft_payload["general_role_keys"])
                    ensure_social_platforms_exist(
                        cursor,
                        [item["social_platform_id"] for item in draft_payload["social_links"]],
                    )

                    supersede_pending_drafts(cursor, profile["id"] if profile else None, email)
                    draft_id = insert_profile_submission_draft(
                        cursor=cursor,
                        profile=profile,
                        email=email,
                        draft_payload=draft_payload,
                    )
                    insert_profile_submission_social_links(cursor, draft_id, draft_payload["social_links"])
                    insert_profile_submission_volunteer_claims(cursor, draft_id, draft_payload["event_role_claims"])
                    insert_profile_submission_volunteer_general_claims(
                        cursor, draft_id, draft_payload["general_role_keys"]
                    )

                    auto_approve = bool(
                        profile
                        and profile.get("id")
                        and profile.get("is_profile_approved")
                        and has_volunteer_role(cursor, profile["id"])
                    )

                    moderation_links = []
                    if auto_approve:
                        profile_id = apply_volunteer_draft(cursor, draft_payload, profile_id=profile["id"])
                        attach_profile_to_draft(cursor, draft_id=draft_id, profile_id=profile_id)
                        finalize_draft_status(
                            cursor,
                            draft_id=draft_id,
                            status=WORKFLOW_STATUS_APPROVED,
                            reviewer_profile_id=profile_id,
                            denial_reason=None,
                        )
                        materialize_draft_claims(cursor, draft_id=draft_id, profile_id=profile_id)
                    else:
                        moderator_emails = get_moderator_emails(cursor)
                        if not moderator_emails:
                            raise ValueError("No moderator email addresses are configured yet.")
                        moderation_links = create_volunteer_moderation_links(
                            cursor=cursor,
                            app=app,
                            draft_id=draft_id,
                            moderator_emails=moderator_emails,
                            ttl_hours=settings["action_token_ttl_hours"],
                        )

                    mark_action_token_used(cursor, token_row["id"])
                    stored_draft = get_profile_submission_draft(cursor, draft_id)
                    stored_claims = get_profile_submission_volunteer_claims(cursor, draft_id)
                    stored_general_claims = get_profile_submission_volunteer_general_claims(cursor, draft_id)

                if auto_approve:
                    send_volunteer_profile_approved_email(
                        email=email,
                        display_name=draft_payload["display_name"],
                        role_claims=stored_claims,
                        general_role_claims=stored_general_claims,
                    )
                else:
                    send_volunteer_moderation_emails(
                        draft_id=draft_id,
                        email=email,
                        draft_payload=stored_draft,
                        draft_claims=stored_claims,
                        draft_general_claims=stored_general_claims,
                        existing_profile=profile,
                        matched_by=matched_by,
                        moderation_links=moderation_links,
                    )

            return jsonify({"ok": True, "draft_id": draft_id, "auto_approved": auto_approve}), 201
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer registration submission failed")
            return error_response("Unable to submit volunteer registration right now.", 500)

    @app.route("/api/forms/volunteer-registration/moderation/approve", methods=["GET"])
    def volunteer_moderation_approve():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return html_error_page("Missing moderation token.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(
                        cursor,
                        raw_token,
                        ACTION_TYPE_VOLUNTEER_MODERATION_APPROVE,
                    )
                    draft = get_profile_submission_draft(cursor, token_row["draft_id"])
                    if draft["status"] != WORKFLOW_STATUS_PENDING:
                        raise ValueError("This submission has already been reviewed.")

                    profile_id = apply_volunteer_draft(cursor, draft, profile_id=draft.get("profile_id"))
                    attach_profile_to_draft(cursor, draft_id=draft["id"], profile_id=profile_id)
                    materialize_draft_claims(cursor, draft_id=draft["id"], profile_id=profile_id)
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
                    invalidate_volunteer_moderation_tokens_for_draft(cursor, draft["id"])
                    role_claims = get_profile_submission_volunteer_claims(cursor, draft["id"])
                    general_role_claims = get_profile_submission_volunteer_general_claims(cursor, draft["id"])

                send_volunteer_profile_approved_email(
                    email=draft["email"],
                    display_name=draft["display_name"],
                    role_claims=role_claims,
                    general_role_claims=general_role_claims,
                )

            person_name = draft.get("display_name") or draft.get("email") or "the volunteer"
            return html_success_page(
                "Volunteer profile approved",
                f"Draft #{draft['id']} has been approved and {person_name} has been notified.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer profile approval failed")
            return html_error_page("Unable to approve this submission right now.", 500)

    @app.route("/api/forms/volunteer-registration/moderation/deny", methods=["GET", "POST"])
    def volunteer_moderation_deny():
        if request.method == "GET":
            raw_token = normalize_text(request.args.get("token"))
            if not raw_token:
                return html_error_page("Missing moderation token.", 400)

            try:
                with connect() as connection:
                    with connection.cursor() as cursor:
                        token_row = get_action_token(
                            cursor,
                            raw_token,
                            ACTION_TYPE_VOLUNTEER_MODERATION_DENY,
                        )
                        draft = get_profile_submission_draft(cursor, token_row["draft_id"])
                        if draft["status"] != WORKFLOW_STATUS_PENDING:
                            raise ValueError("This submission has already been reviewed.")
                return render_volunteer_denial_form(raw_token)
            except ValueError as exc:
                return html_error_page(str(exc), 400)
            except Exception:
                app.logger.exception("Volunteer denial form lookup failed")
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
                    token_row = get_action_token(
                        cursor,
                        raw_token,
                        ACTION_TYPE_VOLUNTEER_MODERATION_DENY,
                    )
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
                    invalidate_volunteer_moderation_tokens_for_draft(cursor, draft["id"])
                    if include_edit_link:
                        edit_link = create_volunteer_registration_link(
                            cursor=cursor,
                            app=app,
                            email=draft["email"],
                            ttl_hours=get_workflow_settings(cursor)["action_token_ttl_hours"],
                        )

                send_volunteer_profile_denied_email(
                    email=draft["email"],
                    reason=denial_reason,
                    edit_link=edit_link,
                )

            return html_success_page(
                "Volunteer profile denied",
                f"Draft #{draft['id']} has been denied and the volunteer has been notified.",
            )
        except ValueError as exc:
            return html_error_page(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer denial failed")
            return html_error_page("Unable to deny this submission right now.", 500)

    @app.route("/api/forms/volunteer-registration/claims/start", methods=["OPTIONS"])
    def volunteer_claims_start_options():
        return ("", 204)

    @app.route("/api/forms/volunteer-registration/claims/start", methods=["POST"])
    def volunteer_claims_start():
        try:
            payload = get_json_payload()
            email = normalize_email(payload.get("email"))
            if not email:
                return error_response("A valid email address is required.", 400)

            with connect() as connection:
                with connection.cursor() as cursor:
                    profile = get_existing_profile_by_email(cursor, email)
                    if profile and profile.get("id") and has_volunteer_role(cursor, profile["id"]):
                        settings = get_workflow_settings(cursor)
                        invalidate_unused_tokens(
                            cursor,
                            email=email,
                            action_type=ACTION_TYPE_VOLUNTEER_CLAIMS_LINK,
                        )
                        raw_token, token_hash = generate_token_pair()
                        expires_at = now_utc() + timedelta(hours=settings["action_token_ttl_hours"])
                        cursor.execute(
                            """
                            INSERT INTO action_tokens (token_hash, action_type, email, profile_id, expires_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                token_hash,
                                ACTION_TYPE_VOLUNTEER_CLAIMS_LINK,
                                email,
                                profile["id"],
                                expires_at,
                            ),
                        )
                    else:
                        raw_token = None
                        expires_at = None

                if raw_token:
                    send_volunteer_claims_link_email(app, email=email, raw_token=raw_token, expires_at=expires_at)

            return jsonify(
                {
                    "ok": True,
                    "message": "If that email belongs to a volunteer profile, a claims link has been sent.",
                }
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer claims start failed")
            return error_response("Unable to send a claims link right now.", 500)

    @app.route("/api/forms/volunteer-registration/claims/session", methods=["GET"])
    def volunteer_claims_session():
        raw_token = normalize_text(request.args.get("token"))
        if not raw_token:
            return error_response("A claims token is required.", 400)

        try:
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_VOLUNTEER_CLAIMS_LINK)
                    claims = get_claims_for_profile(cursor, token_row["profile_id"])
            return jsonify({"ok": True, **claims})
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer claims session lookup failed")
            return error_response("Unable to load volunteer claims right now.", 500)

    @app.route("/api/forms/volunteer-registration/claims/cancel", methods=["OPTIONS"])
    def volunteer_claims_cancel_options():
        return ("", 204)

    @app.route("/api/forms/volunteer-registration/claims/cancel", methods=["POST"])
    def volunteer_claims_cancel():
        try:
            payload = get_json_payload()
            raw_token = normalize_text(payload.get("token"))
            claim_type = normalize_text(payload.get("claim_type")) or "event"
            claim_id = payload.get("claim_id")
            general_role_key = normalize_text(payload.get("general_role_key"))
            if not raw_token:
                return error_response("A claims token is required.", 400)
            if claim_type not in {"event", "general"}:
                return error_response("A valid claim type is required.", 400)
            if claim_type == "event" and not isinstance(claim_id, int):
                return error_response("A valid claim id is required.", 400)
            if claim_type == "general" and not general_role_key:
                return error_response("A valid general role key is required.", 400)

            promoted = None
            with connect() as connection:
                with connection.cursor() as cursor:
                    token_row = get_action_token(cursor, raw_token, ACTION_TYPE_VOLUNTEER_CLAIMS_LINK)
                    if claim_type == "general":
                        claim = get_general_claim_for_profile(
                            cursor,
                            profile_id=token_row["profile_id"],
                            role_key=general_role_key.lower(),
                        )
                        if claim["status"] == GENERAL_CLAIM_STATUS_WITHDRAWN:
                            raise ValueError("This claim has already been cancelled.")
                        cursor.execute(
                            """
                            UPDATE volunteer_general_role_claims
                            SET
                              status = %s,
                              withdrawn_at = now()
                            WHERE profile_id = %s
                              AND role_key = %s
                            """,
                            (
                                GENERAL_CLAIM_STATUS_WITHDRAWN,
                                token_row["profile_id"],
                                general_role_key.lower(),
                            ),
                        )
                    else:
                        claim = get_claim_by_id_for_profile(cursor, claim_id=claim_id, profile_id=token_row["profile_id"])
                        if claim["status"] == CLAIM_STATUS_CANCELLED:
                            raise ValueError("This claim has already been cancelled.")

                        cursor.execute(
                            """
                            UPDATE event_volunteer_role_claims
                            SET
                              status = %s,
                              cancelled_at = now()
                            WHERE id = %s
                            """,
                            (CLAIM_STATUS_CANCELLED, claim_id),
                        )

                        if claim["status"] == CLAIM_STATUS_SELECTED:
                            promoted = promote_oldest_standby_claim(
                                cursor,
                                event_id=claim["event_id"],
                                role_key=claim["role_key"],
                            )

                if promoted:
                    send_volunteer_standby_promoted_email(promoted)

            return jsonify({"ok": True, "promoted": promoted})
        except ValueError as exc:
            return error_response(str(exc), 400)
        except Exception:
            app.logger.exception("Volunteer claim cancellation failed")
            return error_response("Unable to cancel this claim right now.", 500)


def get_json_payload():
    if not request.is_json:
        raise ValueError("Request body must be JSON.")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON payload.")

    return payload


def normalize_volunteer_submission_payload(payload, email):
    profile_type = "person"
    display_name = normalize_text(payload.get("display_name"))
    first_name = normalize_text(payload.get("first_name"))
    last_name = normalize_text(payload.get("last_name"))
    contact_phone = normalize_text(payload.get("contact_phone"))
    volunteer_bio = normalize_text(payload.get("volunteer_bio") or payload.get("artist_bio"))
    additional_info = normalize_text(payload.get("additional_info"))
    social_links = payload.get("social_links") or []
    role_claims = payload.get("event_role_claims")
    if role_claims is None:
        role_claims = payload.get("role_claims") or []
    general_role_claims = payload.get("general_role_claims") or []

    if not display_name:
        raise ValueError("A display name is required.")
    if not contact_phone:
        raise ValueError("A contact phone number is required.")
    if not isinstance(role_claims, list):
        raise ValueError("Event role claims must be an array.")
    if not isinstance(general_role_claims, list):
        raise ValueError("General role claims must be an array.")
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

    normalized_event_claims = []
    seen_event_claim_keys = set()
    for item in role_claims:
        if not isinstance(item, dict):
            raise ValueError("Each role claim must be an object.")
        event_id = item.get("event_id")
        role_key = normalize_text(item.get("role_key"))
        if not isinstance(event_id, int):
            raise ValueError("Each role claim must include an integer event_id.")
        if not role_key:
            raise ValueError("Each role claim must include a role_key.")
        role_key = role_key.lower()
        dedupe_key = (event_id, role_key)
        if dedupe_key in seen_event_claim_keys:
            continue
        seen_event_claim_keys.add(dedupe_key)
        normalized_event_claims.append(
            {
                "event_id": event_id,
                "role_key": role_key,
            }
        )

    normalized_general_role_keys = []
    seen_general_role_keys = set()
    for raw_role_key in general_role_claims:
        role_key = normalize_text(raw_role_key)
        if not role_key:
            continue
        role_key = role_key.lower()
        if role_key in seen_general_role_keys:
            continue
        seen_general_role_keys.add(role_key)
        normalized_general_role_keys.append(role_key)

    if not normalized_event_claims and not normalized_general_role_keys:
        raise ValueError("At least one volunteer role claim is required.")

    return {
        "email": email,
        "profile_type": profile_type,
        "display_name": display_name,
        "first_name": first_name,
        "last_name": last_name,
        "contact_phone": contact_phone,
        "is_email_public": normalize_boolean(payload.get("is_email_public"), default=False),
        "is_name_public": normalize_boolean(payload.get("is_name_public"), default=False),
        "artist_bio": volunteer_bio,
        "is_artist_bio_public": True,
        "additional_info": additional_info,
        "social_links": normalized_social_links,
        "event_role_claims": normalized_event_claims,
        "general_role_keys": normalized_general_role_keys,
    }


def get_future_events(cursor):
    cursor.execute(
        """
        SELECT id, event_name, event_date
        FROM events
        WHERE event_date > CURRENT_DATE
        ORDER BY event_date, id
        """
    )
    return [
        {
            "id": row[0],
            "event_name": row[1],
            "event_date": row[2].isoformat(),
        }
        for row in cursor.fetchall()
    ]


def get_latest_volunteer_prefill_submission_by_email(cursor, email):
    cursor.execute(
        """
        SELECT d.id
        FROM profile_submission_drafts d
        WHERE lower(d.email) = lower(%s)
          AND d.status IN (%s, %s, %s)
          AND EXISTS (
            SELECT 1 FROM profile_submission_volunteer_claims pvc WHERE pvc.draft_id = d.id
            UNION ALL
            SELECT 1 FROM profile_submission_volunteer_general_claims pvg WHERE pvg.draft_id = d.id
          )
        ORDER BY d.submitted_at DESC, d.id DESC
        LIMIT 1
        """,
        (
            email,
            WORKFLOW_STATUS_PENDING,
            WORKFLOW_STATUS_DENIED,
            WORKFLOW_STATUS_APPROVED,
        ),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return get_profile_submission_draft(cursor, row[0])


def apply_volunteer_role_bio_to_profile(cursor, profile):
    if not profile or not profile.get("id"):
        return profile

    cursor.execute(
        """
        SELECT bio, is_bio_public
        FROM profile_roles
        WHERE profile_id = %s
          AND role = 'volunteer'
        """,
        (profile["id"],),
    )
    row = cursor.fetchone()
    if not row:
        return profile

    profile["artist_bio"] = row[0]
    profile["is_artist_bio_public"] = row[1]
    return profile


def ensure_claim_events_are_allowed(role_claims, future_event_ids):
    disallowed = sorted({item["event_id"] for item in role_claims if item["event_id"] not in future_event_ids})
    if disallowed:
        raise ValueError("One or more selected event dates are not currently available.")


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


def ensure_event_roles_exist(cursor, role_keys):
    if not role_keys:
        return
    cursor.execute(
        """
        SELECT role_key
        FROM volunteer_roles
        WHERE is_active = true
          AND role_scope = 'event'
          AND role_key = ANY(%s)
        """,
        (role_keys,),
    )
    found_keys = {row[0] for row in cursor.fetchall()}
    missing_keys = sorted(set(role_keys) - found_keys)
    if missing_keys:
        raise ValueError(f"Unknown volunteer role keys: {', '.join(missing_keys)}")


def ensure_general_roles_exist(cursor, role_keys):
    if not role_keys:
        return
    cursor.execute(
        """
        SELECT role_key
        FROM volunteer_roles
        WHERE is_active = true
          AND role_scope = 'general'
          AND role_key = ANY(%s)
        """,
        (role_keys,),
    )
    found_keys = {row[0] for row in cursor.fetchall()}
    missing_keys = sorted(set(role_keys) - found_keys)
    if missing_keys:
        raise ValueError(f"Unknown volunteer role keys: {', '.join(missing_keys)}")


def insert_profile_submission_volunteer_claims(cursor, draft_id, role_claims):
    for item in role_claims:
        cursor.execute(
            """
            INSERT INTO profile_submission_volunteer_claims (draft_id, event_id, role_key)
            VALUES (%s, %s, %s)
            ON CONFLICT (draft_id, event_id, role_key) DO NOTHING
            """,
            (draft_id, item["event_id"], item["role_key"]),
        )


def insert_profile_submission_volunteer_general_claims(cursor, draft_id, role_keys):
    for role_key in role_keys:
        cursor.execute(
            """
            INSERT INTO profile_submission_volunteer_general_claims (draft_id, role_key)
            VALUES (%s, %s)
            ON CONFLICT (draft_id, role_key) DO NOTHING
            """,
            (draft_id, role_key),
        )


def get_profile_submission_volunteer_claims(cursor, draft_id):
    cursor.execute(
        """
        SELECT
          pvc.event_id,
          pvc.role_key,
          vr.display_name,
          e.event_name,
          e.event_date
        FROM profile_submission_volunteer_claims pvc
        JOIN volunteer_roles vr
          ON vr.role_key = pvc.role_key
        JOIN events e
          ON e.id = pvc.event_id
        WHERE pvc.draft_id = %s
          AND pvc.event_id IS NOT NULL
          AND vr.role_scope = 'event'
        ORDER BY e.event_date, e.id, vr.sort_order, vr.role_key
        """,
        (draft_id,),
    )
    return [
        {
            "event_id": row[0],
            "role_key": row[1],
            "role_display_name": row[2],
            "event_name": row[3],
            "event_date": row[4].isoformat(),
        }
        for row in cursor.fetchall()
    ]


def get_profile_submission_volunteer_general_claims(cursor, draft_id):
    cursor.execute(
        """
        SELECT
          pvg.role_key,
          vr.display_name
        FROM profile_submission_volunteer_general_claims pvg
        JOIN volunteer_roles vr
          ON vr.role_key = pvg.role_key
        WHERE pvg.draft_id = %s
          AND vr.role_scope = 'general'
        ORDER BY vr.sort_order, vr.role_key
        """,
        (draft_id,),
    )
    return [
        {
            "role_key": row[0],
            "role_display_name": row[1],
        }
        for row in cursor.fetchall()
    ]


def has_volunteer_role(cursor, profile_id):
    cursor.execute(
        """
        SELECT 1
        FROM profile_roles
        WHERE profile_id = %s
          AND role = 'volunteer'
        """,
        (profile_id,),
    )
    return cursor.fetchone() is not None


def apply_volunteer_draft(cursor, draft, *, profile_id=None):
    target_profile_id = profile_id or draft.get("profile_id")

    if target_profile_id is None:
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
              approved_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, now())
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
            ),
        )
        target_profile_id = cursor.fetchone()[0]
    else:
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
              approved_at = now()
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
                target_profile_id,
            ),
        )

    upsert_volunteer_role(cursor, target_profile_id, draft.get("artist_bio"), True)
    replace_profile_social_links(cursor, target_profile_id, draft.get("social_links", []))
    return target_profile_id


def upsert_volunteer_role(cursor, profile_id, bio, is_bio_public):
    cursor.execute(
        """
        INSERT INTO profile_roles (profile_id, role, bio, is_bio_public)
        VALUES (%s, 'volunteer', %s, %s)
        ON CONFLICT (profile_id, role)
        DO UPDATE SET
          bio = EXCLUDED.bio,
          is_bio_public = EXCLUDED.is_bio_public
        """,
        (profile_id, bio, is_bio_public),
    )


def materialize_draft_claims(cursor, *, draft_id, profile_id):
    claims = get_profile_submission_volunteer_claims(cursor, draft_id)
    general_claims = get_profile_submission_volunteer_general_claims(cursor, draft_id)
    materialized = []
    for claim in claims:
        upserted = materialize_single_claim(
            cursor,
            event_id=claim["event_id"],
            role_key=claim["role_key"],
            profile_id=profile_id,
            source_draft_id=draft_id,
        )
        if upserted:
            materialized.append(upserted)
    for claim in general_claims:
        upserted = materialize_single_general_claim(
            cursor,
            role_key=claim["role_key"],
            profile_id=profile_id,
            source_draft_id=draft_id,
        )
        if upserted:
            materialized.append(upserted)
    return materialized


def materialize_single_claim(cursor, *, event_id, role_key, profile_id, source_draft_id):
    cursor.execute(
        """
        SELECT id, status
        FROM event_volunteer_role_claims
        WHERE event_id = %s
          AND role_key = %s
          AND profile_id = %s
        FOR UPDATE
        """,
        (event_id, role_key, profile_id),
    )
    existing = cursor.fetchone()
    if existing and existing[1] in {CLAIM_STATUS_SELECTED, CLAIM_STATUS_STANDBY}:
        return None

    status = choose_claim_status(cursor, event_id=event_id, role_key=role_key)

    cursor.execute(
        """
        INSERT INTO event_volunteer_role_claims (
          event_id,
          role_key,
          profile_id,
          status,
          source_draft_id,
          claimed_at,
          promoted_at,
          cancelled_at
        )
        VALUES (
          %s,
          %s,
          %s,
          %s,
          %s,
          now(),
          CASE WHEN %s = 'selected' THEN now() ELSE NULL END,
          NULL
        )
        ON CONFLICT (event_id, role_key, profile_id)
        DO UPDATE SET
          status = EXCLUDED.status,
          source_draft_id = EXCLUDED.source_draft_id,
          claimed_at = CASE
            WHEN event_volunteer_role_claims.status = 'cancelled' THEN now()
            ELSE event_volunteer_role_claims.claimed_at
          END,
          promoted_at = CASE
            WHEN EXCLUDED.status = 'selected' AND event_volunteer_role_claims.status <> 'selected' THEN now()
            ELSE event_volunteer_role_claims.promoted_at
          END,
          cancelled_at = NULL
        RETURNING id, status
        """,
        (event_id, role_key, profile_id, status, source_draft_id, status),
    )
    row = cursor.fetchone()
    return {"id": row[0], "status": row[1], "event_id": event_id, "role_key": role_key}


def choose_claim_status(cursor, *, event_id, role_key):
    cursor.execute("SELECT id FROM events WHERE id = %s FOR UPDATE", (event_id,))
    if cursor.fetchone() is None:
        raise ValueError("That event no longer exists.")

    cursor.execute(
        """
        SELECT role_key
        FROM volunteer_roles
        WHERE role_key = %s
          AND is_active = true
          AND role_scope = 'event'
        FOR UPDATE
        """,
        (role_key,),
    )
    if cursor.fetchone() is None:
        raise ValueError("That volunteer role is not available.")

    cursor.execute(
        """
        SELECT role_key
        FROM event_volunteer_role_overrides
        WHERE event_id = %s
          AND role_key = %s
        FOR UPDATE
        """,
        (event_id, role_key),
    )
    cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(ov.capacity_override, vr.default_capacity)
        FROM volunteer_roles vr
        LEFT JOIN event_volunteer_role_overrides ov
          ON ov.role_key = vr.role_key
         AND ov.event_id = %s
        WHERE vr.role_key = %s
          AND vr.role_scope = 'event'
        """,
        (event_id, role_key),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That volunteer role is not available.")

    capacity = row[0]
    cursor.execute(
        """
        SELECT id
        FROM event_volunteer_role_claims
        WHERE event_id = %s
          AND role_key = %s
          AND status = 'selected'
        FOR UPDATE
        """,
        (event_id, role_key),
    )
    selected_count = len(cursor.fetchall())
    return CLAIM_STATUS_SELECTED if selected_count < capacity else CLAIM_STATUS_STANDBY


def materialize_single_general_claim(cursor, *, role_key, profile_id, source_draft_id):
    cursor.execute(
        """
        SELECT role_key
        FROM volunteer_roles
        WHERE role_key = %s
          AND is_active = true
          AND role_scope = 'general'
        """,
        (role_key,),
    )
    if cursor.fetchone() is None:
        raise ValueError("That volunteer role is not available.")

    cursor.execute(
        """
        INSERT INTO volunteer_general_role_claims (
          role_key,
          profile_id,
          source_draft_id,
          status,
          claimed_at,
          withdrawn_at
        )
        VALUES (%s, %s, %s, %s, now(), NULL)
        ON CONFLICT (role_key, profile_id)
        DO UPDATE SET
          source_draft_id = EXCLUDED.source_draft_id,
          status = %s,
          claimed_at = CASE
            WHEN volunteer_general_role_claims.status = %s THEN now()
            ELSE volunteer_general_role_claims.claimed_at
          END,
          withdrawn_at = NULL
        RETURNING role_key, status
        """,
        (
            role_key,
            profile_id,
            source_draft_id,
            GENERAL_CLAIM_STATUS_ACTIVE,
            GENERAL_CLAIM_STATUS_ACTIVE,
            GENERAL_CLAIM_STATUS_WITHDRAWN,
        ),
    )
    row = cursor.fetchone()
    return {"role_key": row[0], "status": row[1], "claim_type": "general"}


def get_role_availability_by_event(cursor, *, profile_id=None):
    cursor.execute(
        """
        SELECT
          e.id,
          e.event_name,
          e.event_date,
          vr.role_key,
          vr.display_name,
          COALESCE(ov.description_override, vr.description) AS role_description,
          COALESCE(ov.capacity_override, vr.default_capacity) AS capacity,
          COALESCE(sel.selected_count, 0) AS selected_count,
          COALESCE(sb.standby_count, 0) AS standby_count,
          uc.status AS user_claim_status
        FROM events e
        CROSS JOIN volunteer_roles vr
        LEFT JOIN event_volunteer_role_overrides ov
          ON ov.event_id = e.id
         AND ov.role_key = vr.role_key
        LEFT JOIN (
          SELECT event_id, role_key, COUNT(*) AS selected_count
          FROM event_volunteer_role_claims
          WHERE status = 'selected'
          GROUP BY event_id, role_key
        ) sel
          ON sel.event_id = e.id
         AND sel.role_key = vr.role_key
        LEFT JOIN (
          SELECT event_id, role_key, COUNT(*) AS standby_count
          FROM event_volunteer_role_claims
          WHERE status = 'standby'
          GROUP BY event_id, role_key
        ) sb
          ON sb.event_id = e.id
         AND sb.role_key = vr.role_key
        LEFT JOIN event_volunteer_role_claims uc
          ON uc.event_id = e.id
         AND uc.role_key = vr.role_key
         AND uc.profile_id = %s
         AND uc.status IN ('selected', 'standby')
        WHERE e.event_date > CURRENT_DATE
          AND vr.is_active = true
          AND vr.role_scope = 'event'
        ORDER BY e.event_date, e.id, vr.sort_order, vr.role_key
        """,
        (profile_id,),
    )

    events = {}
    for row in cursor.fetchall():
        event_id = row[0]
        event_bucket = events.setdefault(
            event_id,
            {
                "event_id": row[0],
                "event_name": row[1],
                "event_date": row[2].isoformat(),
                "roles": [],
            },
        )
        role = {
            "role_key": row[3],
            "display_name": row[4],
            "description": row[5],
            "capacity": row[6],
            "selected_count": row[7],
            "standby_count": row[8],
            "is_filled": row[7] >= row[6],
            "user_claim_status": row[9],
        }
        event_bucket["roles"].append(role)

    return list(events.values())


def get_general_role_options(cursor, *, profile_id=None):
    cursor.execute(
        """
        SELECT
          vr.role_key,
          vr.display_name,
          vr.description,
          COALESCE(active_claims.active_count, 0) AS active_count,
          uc.status AS user_claim_status
        FROM volunteer_roles vr
        LEFT JOIN (
          SELECT role_key, COUNT(*) AS active_count
          FROM volunteer_general_role_claims
          WHERE status = 'active'
          GROUP BY role_key
        ) active_claims
          ON active_claims.role_key = vr.role_key
        LEFT JOIN volunteer_general_role_claims uc
          ON uc.role_key = vr.role_key
         AND uc.profile_id = %s
         AND uc.status IN ('active')
        WHERE vr.is_active = true
          AND vr.role_scope = 'general'
        ORDER BY vr.sort_order, vr.role_key
        """,
        (profile_id,),
    )
    return [
        {
            "role_key": row[0],
            "display_name": row[1],
            "description": row[2],
            "active_count": row[3],
            "user_claim_status": row[4],
        }
        for row in cursor.fetchall()
    ]


def get_active_claim_pairs(cursor, *, profile_id):
    if profile_id is None:
        return []
    cursor.execute(
        """
        SELECT event_id, role_key, status
        FROM event_volunteer_role_claims
        WHERE profile_id = %s
          AND status IN ('selected', 'standby')
        """,
        (profile_id,),
    )
    return [
        {
            "event_id": row[0],
            "role_key": row[1],
            "status": row[2],
        }
        for row in cursor.fetchall()
    ]


def get_active_general_claim_keys(cursor, *, profile_id):
    if profile_id is None:
        return []
    cursor.execute(
        """
        SELECT role_key
        FROM volunteer_general_role_claims
        WHERE profile_id = %s
          AND status = %s
        """,
        (profile_id, GENERAL_CLAIM_STATUS_ACTIVE),
    )
    return [row[0] for row in cursor.fetchall()]


def create_volunteer_moderation_links(*, cursor, app, draft_id, moderator_emails, ttl_hours):
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
            (
                approve_hash,
                ACTION_TYPE_VOLUNTEER_MODERATION_APPROVE,
                moderator["email"],
                moderator["profile_id"],
                draft_id,
                expires_at,
            ),
        )
        cursor.execute(
            """
            INSERT INTO action_tokens (token_hash, action_type, email, profile_id, draft_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                deny_hash,
                ACTION_TYPE_VOLUNTEER_MODERATION_DENY,
                moderator["email"],
                moderator["profile_id"],
                draft_id,
                expires_at,
            ),
        )

        links.append(
            {
                "email": moderator["email"],
                "approve_url": build_absolute_url(
                    app,
                    f"/api/forms/volunteer-registration/moderation/approve?token={approve_token}",
                ),
                "deny_url": build_absolute_url(
                    app,
                    f"/api/forms/volunteer-registration/moderation/deny?token={deny_token}",
                ),
            }
        )

    return links


def invalidate_volunteer_moderation_tokens_for_draft(cursor, draft_id):
    cursor.execute(
        """
        UPDATE action_tokens
        SET used_at = now()
        WHERE draft_id = %s
          AND action_type IN (%s, %s)
          AND used_at IS NULL
        """,
        (
            draft_id,
            ACTION_TYPE_VOLUNTEER_MODERATION_APPROVE,
            ACTION_TYPE_VOLUNTEER_MODERATION_DENY,
        ),
    )


def create_volunteer_registration_link(*, cursor, app, email, ttl_hours):
    invalidate_unused_tokens(cursor, email=email, action_type=ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK)
    raw_token, token_hash = generate_token_pair()
    expires_at = now_utc() + timedelta(hours=ttl_hours)
    cursor.execute(
        """
        INSERT INTO action_tokens (token_hash, action_type, email, expires_at)
        VALUES (%s, %s, %s, %s)
        """,
        (token_hash, ACTION_TYPE_VOLUNTEER_REGISTRATION_LINK, email, expires_at),
    )
    return {
        "url": build_absolute_url(app, f"/volunteer/?token={raw_token}"),
        "expires_at": expires_at,
    }


def get_claims_for_profile(cursor, profile_id):
    cursor.execute(
        """
        SELECT
          c.id,
          c.event_id,
          c.role_key,
          vr.display_name,
          e.event_name,
          e.event_date,
          c.status,
          c.claimed_at,
          c.promoted_at,
          c.cancelled_at
        FROM event_volunteer_role_claims c
        JOIN volunteer_roles vr
          ON vr.role_key = c.role_key
        JOIN events e
          ON e.id = c.event_id
        WHERE c.profile_id = %s
          AND e.event_date >= CURRENT_DATE
          AND vr.role_scope = 'event'
        ORDER BY e.event_date, e.id, vr.sort_order, c.id
        """,
        (profile_id,),
    )
    event_claims = [
        {
            "claim_id": row[0],
            "claim_type": "event",
            "event_id": row[1],
            "role_key": row[2],
            "role_display_name": row[3],
            "event_name": row[4],
            "event_date": row[5].isoformat(),
            "status": row[6],
            "claimed_at": row[7].isoformat() if row[7] else None,
            "promoted_at": row[8].isoformat() if row[8] else None,
            "cancelled_at": row[9].isoformat() if row[9] else None,
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT
          c.role_key,
          vr.display_name,
          c.status,
          c.claimed_at,
          c.withdrawn_at
        FROM volunteer_general_role_claims c
        JOIN volunteer_roles vr
          ON vr.role_key = c.role_key
        WHERE c.profile_id = %s
          AND vr.role_scope = 'general'
        ORDER BY vr.sort_order, vr.role_key
        """,
        (profile_id,),
    )
    general_claims = [
        {
            "claim_type": "general",
            "role_key": row[0],
            "role_display_name": row[1],
            "status": row[2],
            "claimed_at": row[3].isoformat() if row[3] else None,
            "withdrawn_at": row[4].isoformat() if row[4] else None,
        }
        for row in cursor.fetchall()
    ]

    return {"event_claims": event_claims, "general_claims": general_claims}


def get_claim_by_id_for_profile(cursor, *, claim_id, profile_id):
    cursor.execute(
        """
        SELECT id, event_id, role_key, status
        FROM event_volunteer_role_claims
        WHERE id = %s
          AND profile_id = %s
        FOR UPDATE
        """,
        (claim_id, profile_id),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That claim no longer exists.")
    return {
        "id": row[0],
        "event_id": row[1],
        "role_key": row[2],
        "status": row[3],
    }


def get_general_claim_for_profile(cursor, *, profile_id, role_key):
    cursor.execute(
        """
        SELECT role_key, status
        FROM volunteer_general_role_claims
        WHERE profile_id = %s
          AND role_key = %s
        FOR UPDATE
        """,
        (profile_id, role_key),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("That claim no longer exists.")
    return {"role_key": row[0], "status": row[1]}


def promote_oldest_standby_claim(cursor, *, event_id, role_key):
    cursor.execute(
        """
        SELECT
          c.id,
          p.email,
          COALESCE(NULLIF(p.display_name, ''), p.email),
          e.event_name,
          e.event_date,
          vr.display_name
        FROM event_volunteer_role_claims c
        JOIN profiles p
          ON p.id = c.profile_id
        JOIN events e
          ON e.id = c.event_id
        JOIN volunteer_roles vr
          ON vr.role_key = c.role_key
        WHERE c.event_id = %s
          AND c.role_key = %s
          AND c.status = 'standby'
        ORDER BY c.claimed_at, c.id
        FOR UPDATE
        LIMIT 1
        """,
        (event_id, role_key),
    )
    row = cursor.fetchone()
    if not row:
        return None

    claim_id = row[0]
    cursor.execute(
        """
        UPDATE event_volunteer_role_claims
        SET
          status = 'selected',
          promoted_at = now(),
          cancelled_at = NULL
        WHERE id = %s
        """,
        (claim_id,),
    )

    return {
        "claim_id": claim_id,
        "email": row[1],
        "display_name": row[2],
        "event_name": row[3],
        "event_date": row[4].isoformat(),
        "role_display_name": row[5],
    }


def send_volunteer_registration_email(app, email, raw_token, expires_at):
    register_url = build_absolute_url(app, f"/volunteer/?token={raw_token}")
    body = (
        "Click the link below to create or update your volunteer profile and claim event roles.\n\n"
        f"{register_url}\n\n"
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(email, "sydney.emom | volunteer registration link", body)


def send_volunteer_moderation_emails(
    *,
    draft_id,
    email,
    draft_payload,
    draft_claims,
    draft_general_claims,
    existing_profile,
    matched_by,
    moderation_links,
):
    if not moderation_links:
        return

    existing_profile_block = format_existing_profile_for_moderation(existing_profile, matched_by)
    social_lines = format_social_lines(draft_payload.get("social_links", []))
    event_claim_lines = format_claim_lines(draft_claims)
    general_claim_lines = format_general_claim_lines(draft_general_claims)

    for link in moderation_links:
        body = (
            "A volunteer profile submission is awaiting moderation.\n\n"
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
            f"Bio:\n{draft_payload.get('artist_bio') or '(none)'}\n\n"
            f"Additional info (not shown on profile):\n{draft_payload.get('additional_info') or '(none)'}\n\n"
            f"Event role claims:\n{event_claim_lines}\n\n"
            f"General role claims:\n{general_claim_lines}\n\n"
            f"Social links:\n{social_lines}\n\n"
            f"Approve: {link['approve_url']}\n"
            f"Deny: {link['deny_url']}\n"
        )
        send_mail(link["email"], f"sydney.emom | volunteer moderation request #{draft_id}", body)


def format_existing_profile_for_moderation(existing_profile, matched_by):
    if not existing_profile:
        return "Existing profile match: none. This will create a new profile if approved.\n\n"

    return (
        f"Existing profile match: yes ({matched_by})\n"
        f"Existing profile id: {existing_profile['id']}\n"
        f"Existing email: {existing_profile.get('email') or ''}\n"
        f"Existing display name: {existing_profile.get('display_name') or ''}\n"
        f"Existing contact phone: {existing_profile.get('contact_phone') or ''}\n"
        "\nSubmitted draft:\n"
    )


def format_social_lines(social_links):
    lines = []
    for item in social_links:
        platform_name = item.get("platform_name") or f"platform #{item['social_platform_id']}"
        profile_name = item.get("profile_name") or ""
        lines.append(f"- {platform_name}: {profile_name}")
    return "\n".join(lines) or "- none provided"


def format_claim_lines(claims):
    lines = [
        f"- {item['event_date']}: {item['event_name']} -> {item['role_display_name']}"
        for item in claims
    ]
    return "\n".join(lines) or "- none selected"


def format_general_claim_lines(claims):
    lines = [f"- {item['role_display_name']}" for item in claims]
    return "\n".join(lines) or "- none selected"


def send_volunteer_profile_approved_email(*, email, display_name, role_claims, general_role_claims):
    claims_text = format_claim_lines(role_claims)
    general_claims_text = format_general_claim_lines(general_role_claims)
    body = (
        f"Hello {display_name or 'volunteer'},\n\n"
        "Your volunteer profile submission has been approved.\n\n"
        "Your current event role claims:\n"
        f"{claims_text}\n\n"
        "Your current general role claims:\n"
        f"{general_claims_text}\n\n"
        "If you need to cancel a role claim, request a claims-management link from the volunteer page.\n"
    )
    send_mail(email, "sydney.emom | volunteer profile approved", body)


def send_volunteer_profile_denied_email(*, email, reason, edit_link=None):
    body = (
        "Your volunteer profile submission was not approved at this stage.\n\n"
        f"Reason:\n{reason}\n"
    )
    if edit_link:
        body += (
            "\nYou can use the link below to review your details, make changes, and submit again.\n\n"
            f"{edit_link['url']}\n\n"
            f"This link expires at {format_link_expiry_local(edit_link['expires_at'])}.\n"
        )
    send_mail(email, "sydney.emom | volunteer profile update", body)


def send_volunteer_claims_link_email(app, *, email, raw_token, expires_at):
    claims_url = build_absolute_url(app, f"/volunteer/?claims_token={raw_token}")
    body = (
        "Use the link below to view and manage your volunteer role claims.\n\n"
        f"{claims_url}\n\n"
        f"This link expires at {format_link_expiry_local(expires_at)}.\n"
    )
    send_mail(email, "sydney.emom | volunteer claims link", body)


def send_volunteer_standby_promoted_email(promoted):
    body = (
        f"Hello {promoted['display_name'] or 'volunteer'},\n\n"
        f"A spot has opened and your standby claim has been promoted to selected for {promoted['event_name']} on {promoted['event_date']}.\n"
        f"Role: {promoted['role_display_name']}\n"
    )
    send_mail(
        promoted["email"],
        f"sydney.emom | role confirmed for {promoted['event_name']}",
        body,
    )


def render_volunteer_denial_form(raw_token):
    safe_token = html.escape(raw_token, quote=True)
    content_html = (
        "<div class='token-form-card'>"
        "<h1>Deny volunteer profile</h1>"
        "<form method='post'>"
        f"<input type='hidden' name='token' value='{safe_token}'>"
        "<label for='reason'>Reason</label>"
        "<textarea id='reason' name='reason' required></textarea>"
        "<label class='checkbox'>"
        "<input type='checkbox' name='include_edit_link' value='1' checked>"
        "<span>Include a fresh one-time edit link in the email to the volunteer</span>"
        "</label>"
        "<button type='submit'>Send denial</button>"
        "</form>"
        "</div>"
    )
    return render_token_page(
        title="Deny volunteer profile",
        content_html=content_html,
        layout_class="token-layout token-layout--narrow",
    )
