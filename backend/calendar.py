import os
from datetime import datetime, timedelta, timezone

from flask import Response

from backend.db import connect


def _escape_text(value):
    return (str(value or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n"))


def _fold(line, limit=74):
    """Fold an iCalendar content line without splitting UTF-8 characters."""
    chunks = []
    while len(line) > limit:
        split_at = limit
        while split_at > 1 and len(line[:split_at].encode("utf-8")) > 75:
            split_at -= 1
        chunks.append(line[:split_at])
        line = line[split_at:]
        limit = 73
    chunks.append(line)
    return "\r\n ".join(chunks)


def _ical_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event_url(event):
    base_url = (os.getenv("PUBLIC_SITE_BASE_URL") or "https://sydney.emom.me").rstrip("/")
    gallery = (event[8] or "").strip()
    if gallery:
        safe_gallery = gallery.strip("/").replace("/", "-")
        return f"{base_url}/gallery/{safe_gallery}/index.html"
    return f"{base_url}/gallery/event-coming-soon/"


def build_calendar():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.id, e.event_date,
                       CASE WHEN e.type_id = 1
                            THEN 'EMOM: ' || e.event_name
                            ELSE 'EMOM Presents: ' || e.event_name
                       END AS event_name,
                       e.event_description,
                       e.starts_at, e.ends_at, e.timezone, et.description,
                       e.gallery_url, l.name, l.address
                FROM events e
                JOIN event_types et ON et.id = e.type_id
                LEFT JOIN locations l ON l.id = e.location_id
                ORDER BY COALESCE(e.starts_at, e.event_date::timestamptz), e.id
                """
            )
            events = cursor.fetchall()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EMOM Sydney//Event Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:EMOM Sydney",
        "X-WR-TIMEZONE:Australia/Sydney",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        event_id, event_date, name, description, starts_at, ends_at, timezone_name, event_type, gallery_url, location_name, address = event
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:event-{event_id}@sydney.emom.me",
            f"DTSTAMP:{stamp}",
            f"SUMMARY:{_escape_text(name)}",
            f"DESCRIPTION:{_escape_text(event_type + (': ' if description else '') + (description or ''))}",
            f"URL:{_event_url(event)}",
        ])
        if starts_at:
            lines.append(f"DTSTART:{_ical_datetime(starts_at)}")
            if ends_at:
                lines.append(f"DTEND:{_ical_datetime(ends_at)}")
        else:
            lines.append(f"DTSTART;VALUE=DATE:{event_date.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(event_date + timedelta(days=1)).strftime('%Y%m%d')}")
        location = ", ".join(value for value in (location_name, address) if value)
        if location:
            lines.append(f"LOCATION:{_escape_text(location)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def register_calendar_routes(app):
    @app.get("/calendar.ics")
    def calendar_feed():
        response = Response(build_calendar(), mimetype="text/calendar")
        response.headers["Content-Type"] = "text/calendar; charset=utf-8"
        response.headers["Content-Disposition"] = "inline; filename=emom-sydney.ics"
        response.headers["Cache-Control"] = "public, max-age=300"
        return response
