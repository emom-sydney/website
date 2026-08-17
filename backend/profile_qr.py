import io
import os
import re
from pathlib import PurePosixPath

import qrcode
import qrcode.image.svg
from flask import abort, redirect, request, send_file

from backend.db import connect


DEFAULT_QR_TRACKING_RETENTION_DAYS = 90


def register_profile_qr_routes(app):
    @app.get("/api/v1/artists/<int:profile_id>/qr/scan")
    def scan_artist_profile_qr(profile_id):
        profile = get_public_artist(profile_id)
        if not profile:
            abort(404)

        log_qr_event(profile_id, "scan")
        response = redirect(get_artist_profile_path(profile["display_name"]), code=302)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/artists/<int:profile_id>/qr/download.svg")
    def download_artist_profile_qr_svg(profile_id):
        profile = get_public_artist(profile_id)
        if not profile:
            abort(404)

        log_qr_event(profile_id, "download")
        return qr_download_response(
            make_qr_svg(get_scan_url(profile_id)),
            profile["display_name"],
            profile_id,
            "svg",
            "image/svg+xml",
        )

    @app.get("/api/v1/artists/<int:profile_id>/qr/display.svg")
    def display_artist_profile_qr_svg(profile_id):
        profile = get_public_artist(profile_id)
        if not profile:
            abort(404)

        response = send_file(
            io.BytesIO(make_qr_svg(get_scan_url(profile_id))),
            mimetype="image/svg+xml",
            as_attachment=False,
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/api/v1/artists/<int:profile_id>/qr/download.png")
    def download_artist_profile_qr_png(profile_id):
        profile = get_public_artist(profile_id)
        if not profile:
            abort(404)

        log_qr_event(profile_id, "download")
        return qr_download_response(
            make_qr_png(get_scan_url(profile_id)),
            profile["display_name"],
            profile_id,
            "png",
            "image/png",
        )


def get_public_artist(profile_id):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.display_name
                FROM profiles p
                INNER JOIN profile_roles pr
                  ON pr.profile_id = p.id
                 AND pr.role = 'artist'
                WHERE p.id = %s
                  AND p.is_profile_approved = true
                  AND (p.profile_visible_from IS NULL OR p.profile_visible_from <= CURRENT_DATE)
                  AND p.profile_expires_on >= CURRENT_DATE
                """,
                (profile_id,),
            )
            row = cursor.fetchone()

    if not row:
        return None
    return {"id": row[0], "display_name": row[1]}


def log_qr_event(profile_id, action):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO profile_qr_events (
                  profile_id,
                  action,
                  ip_address,
                  user_agent,
                  referrer
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    profile_id,
                    action,
                    get_client_ip_address(),
                    request.headers.get("User-Agent"),
                    request.referrer,
                ),
            )


def get_client_ip_address():
    # nginx sets this from $remote_addr and overwrites any client supplied value.
    return request.headers.get("X-Real-IP") or request.remote_addr


def get_scan_url(profile_id):
    base_url = (os.getenv("PUBLIC_SITE_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("PUBLIC_SITE_BASE_URL must be configured.")
    return f"{base_url}/api/v1/artists/{profile_id}/qr/scan"


def get_artist_profile_path(display_name):
    return f"/artists/{slugify(display_name)}/index.html"


def slugify(value):
    slug = str(value).lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.ASCII)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def make_qr_svg(data):
    qr = build_qr(data)
    output = io.BytesIO()
    qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(output)
    return output.getvalue()


def make_qr_png(data):
    qr = build_qr(data)
    output = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    return output.getvalue()


def build_qr(data):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr


def qr_download_response(content, display_name, profile_id, extension, mimetype):
    filename = f"{get_safe_filename(display_name, profile_id)}-profile-qr.{extension}"
    response = send_file(
        io.BytesIO(content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def get_safe_filename(display_name, profile_id):
    slug = slugify(display_name)
    return PurePosixPath(slug or f"artist-{profile_id}").name


def get_qr_tracking_retention_days(cursor):
    cursor.execute(
        "SELECT value_json FROM app_settings WHERE key = %s",
        ("qr_tracking_retention_days",),
    )
    row = cursor.fetchone()
    if not row:
        return DEFAULT_QR_TRACKING_RETENTION_DAYS

    value = row[0]
    if isinstance(value, bool):
        return DEFAULT_QR_TRACKING_RETENTION_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_QR_TRACKING_RETENTION_DAYS
    return days if days > 0 else DEFAULT_QR_TRACKING_RETENTION_DAYS


def purge_expired_qr_events():
    with connect() as connection:
        with connection.cursor() as cursor:
            retention_days = get_qr_tracking_retention_days(cursor)
            cursor.execute(
                """
                DELETE FROM profile_qr_events
                WHERE occurred_at < now() - make_interval(days => %s)
                """,
                (retention_days,),
            )
            deleted_count = cursor.rowcount

    return {"retention_days": retention_days, "deleted_count": deleted_count}
