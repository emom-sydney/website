# I don't know a lot about test suites, and I keep hearing about how LLMs aren't very good at it 
# so when I look at this code I am inclined to agree. (see test_lineup_candidate_query_keeps_only_latest_applicable_draft())
# .. a test that will clearly fail if the db data ever changes... 

from contextlib import contextmanager
from datetime import timedelta

import pytest

import backend.admin as admin
import backend.performer_workflow as workflow
import backend.profile_qr as profile_qr
from backend.app import create_app


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_route_contract_has_v1_and_no_legacy_paths(app):
    paths = {str(rule) for rule in app.url_map.iter_rules()}
    expected = {
        "/api/v1/health",
        "/api/v1/profiles/submissions/access-links",
        "/api/v1/profiles/submissions/context",
        "/api/v1/profiles/submissions",
        "/api/v1/artists/<int:profile_id>/qr/scan",
        "/api/v1/artists/<int:profile_id>/qr/download.svg",
        "/api/v1/artists/<int:profile_id>/qr/download.png",
        "/api/v1/admin/events/<int:event_id>/lineup",
        "/api/v1/admin/profiles/submissions/<int:draft_id>/decisions",
        "/admin/",
        "/perform/availability/confirm/",
        "/newsletter/confirm/",
    }
    assert expected <= paths
    assert not any(path.startswith("/api/forms") for path in paths)
    assert "/perform/admin/" not in paths


def test_health_uses_api_envelope(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"data": {"status": "ok"}}


def test_artist_qr_scan_records_event_and_redirects(monkeypatch, client):
    events = []
    monkeypatch.setattr(profile_qr, "get_public_artist", lambda _profile_id: {"id": 12, "display_name": "Static In The Matrix"})
    monkeypatch.setattr(profile_qr, "log_qr_event", lambda profile_id, action: events.append((profile_id, action)))

    response = client.get(
        "/api/v1/artists/12/qr/scan",
        headers={"X-Real-IP": "203.0.113.9", "User-Agent": "QR test", "Referer": "https://example.test/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/artists/static-in-the-matrix/index.html"
    assert response.headers["Cache-Control"] == "no-store"
    assert events == [(12, "scan")]


def test_artist_qr_downloads_log_events_and_return_requested_formats(monkeypatch, client):
    events = []
    monkeypatch.setenv("PUBLIC_SITE_BASE_URL", "https://sydney.emom.me")
    monkeypatch.setattr(profile_qr, "get_public_artist", lambda _profile_id: {"id": 12, "display_name": "Static In The Matrix"})
    monkeypatch.setattr(profile_qr, "log_qr_event", lambda profile_id, action: events.append((profile_id, action)))

    svg_response = client.get("/api/v1/artists/12/qr/download.svg")
    png_response = client.get("/api/v1/artists/12/qr/download.png")

    assert svg_response.status_code == 200
    assert svg_response.mimetype == "image/svg+xml"
    assert "static-in-the-matrix-profile-qr.svg" in svg_response.headers["Content-Disposition"]
    assert b"id=\"qr-path\"" in svg_response.data
    assert profile_qr.get_scan_url(12) == "https://sydney.emom.me/api/v1/artists/12/qr/scan"
    assert png_response.status_code == 200
    assert png_response.mimetype == "image/png"
    assert png_response.data.startswith(b"\x89PNG")
    assert "static-in-the-matrix-profile-qr.png" in png_response.headers["Content-Disposition"]
    assert events == [(12, "download"), (12, "download")]


def test_artist_qr_rejects_non_public_profiles_without_logging(monkeypatch, client):
    monkeypatch.setattr(profile_qr, "get_public_artist", lambda _profile_id: None)
    monkeypatch.setattr(profile_qr, "log_qr_event", lambda *_args: pytest.fail("QR event should not be logged"))

    assert client.get("/api/v1/artists/99/qr/scan").status_code == 404
    assert client.get("/api/v1/artists/99/qr/download.svg").status_code == 404


def test_qr_event_request_context_uses_proxy_ip(app):
    with app.test_request_context(
        "/api/v1/artists/12/qr/scan",
        headers={"X-Real-IP": "203.0.113.9", "User-Agent": "QR test", "Referer": "https://example.test/"},
    ):
        assert profile_qr.get_client_ip_address() == "203.0.113.9"
        assert profile_qr.request.headers["User-Agent"] == "QR test"
        assert profile_qr.request.referrer == "https://example.test/"


def test_qr_tracking_retention_setting_falls_back_to_default():
    class SettingsCursor:
        def execute(self, query, params):
            assert "SELECT value_json FROM app_settings" in query
            assert params == ("qr_tracking_retention_days",)

        def fetchone(self):
            return ("invalid",)

    assert profile_qr.get_qr_tracking_retention_days(SettingsCursor()) == 90


def test_purge_qr_events_uses_retention_setting(monkeypatch):
    class PurgeCursor:
        def __init__(self):
            self.calls = []
            self.rowcount = 4

        def execute(self, query, params):
            self.calls.append((" ".join(query.split()), params))

        def fetchone(self):
            return (45,)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class PurgeConnection:
        def __init__(self):
            self.cursor_instance = PurgeCursor()

        def cursor(self):
            return self.cursor_instance

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    connection = PurgeConnection()
    monkeypatch.setattr(profile_qr, "connect", lambda: connection)

    assert profile_qr.purge_expired_qr_events() == {"retention_days": 45, "deleted_count": 4}
    assert connection.cursor_instance.calls[1][1] == (45,)
    assert "DELETE FROM profile_qr_events" in connection.cursor_instance.calls[1][0]


def test_admin_browser_page_redirects_to_login(client):
    response = client.get("/admin/events/")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/admin/login/?next=")


def test_admin_api_requires_authentication(client):
    response = client.get("/api/v1/admin/events")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"


def test_moderator_cannot_open_full_lineup(monkeypatch, client):
    monkeypatch.setattr(
        admin,
        "load_staff_session",
        lambda: {
            "session_id": 1,
            "profile_id": 2,
            "csrf_token_hash": "unused",
            "expires_at": admin.now_utc() + timedelta(hours=1),
            "email": "moderator@example.com",
            "display_name": "Moderator",
            "is_admin": False,
            "is_moderator": True,
        },
    )
    response = client.get("/admin/events/1/lineup/")
    assert response.status_code == 403
    assert b"Administrator access is required" in response.data


def test_admin_mutation_requires_csrf_before_database_use(monkeypatch, client):
    monkeypatch.setattr(
        admin,
        "load_staff_session",
        lambda: {
            "session_id": 1,
            "profile_id": 2,
            "csrf_token_hash": "unused",
            "expires_at": admin.now_utc() + timedelta(hours=1),
            "email": "admin@example.com",
            "display_name": "Admin",
            "is_admin": True,
            "is_moderator": False,
        },
    )
    response = client.put(
        "/api/v1/admin/events/1/lineup",
        json={"statuses": {}},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "csrf_failed"


def test_next_path_rejects_external_redirects():
    assert admin.normalize_next_path("https://example.com/") == "/admin/"
    assert admin.normalize_next_path("//example.com/admin/") == "/admin/"
    assert admin.normalize_next_path("/admin/events/1/lineup/") == "/admin/events/1/lineup/"


class FakeCursor:
    def __init__(self):
        self.fetches = [
            (10, 20, admin.now_utc() + timedelta(minutes=5), None),
            (20, "staff@example.com", "Staff", True, False),
        ]

    def execute(self, _query, _params=None):
        return None

    def fetchone(self):
        return self.fetches.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_login_verification_sets_secure_session_cookies(monkeypatch, client):
    monkeypatch.setattr(admin, "connect", lambda: FakeConnection())
    response = client.get(
        "/admin/login/verify/?token=valid-token&next=/admin/events/"
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/events/"
    cookies = response.headers.getlist("Set-Cookie")
    session_cookie = next(item for item in cookies if item.startswith("emom_staff_session="))
    csrf_cookie = next(item for item in cookies if item.startswith("emom_staff_csrf="))
    assert "Secure" in session_cookie
    assert "HttpOnly" in session_cookie
    assert "SameSite=Lax" in session_cookie
    assert "HttpOnly" not in csrf_cookie


def test_lineup_candidate_query_keeps_only_latest_applicable_draft():
    class CandidateCursor:
        def __init__(self):
            self.query = None
            self.params = None

        def execute(self, query, params=None):
            self.query = query
            self.params = params

        def fetchall(self):
            return [
                (
                    116,
                    70,
                    25,
                    "Static In The Matrix",
                    "static@yceran.org",
                    None,
                    "requested",
                    None,
                    True,
                    [
                        {
                            "social_platform_id": 3,
                            "profile_name": "staticinmatrix",
                            "platform_name": "Instagram",
                            "url_format": "https://instagram.com/{profileName}",
                        }
                    ],
                    3,
                    2,
                    "",
                    None,
                )
            ]

    cursor = CandidateCursor()

    candidates = workflow.get_lineup_selection_candidates(cursor, 18)

    normalized_query = " ".join(cursor.query.split())
    assert cursor.params == (18, 18, 18)
    assert "d.status IN ('pending', 'approved')" in normalized_query
    assert "PARTITION BY rd.event_id" in normalized_query
    assert "rd.event_id, d.profile_id" in normalized_query
    assert "CASE WHEN d.profile_id IS NULL THEN lower(d.email) END" in normalized_query
    assert "ORDER BY d.submitted_at DESC, d.id DESC, rd.id DESC" in normalized_query
    assert "FROM profile_submission_social_profiles pssp" in normalized_query
    assert "WHERE pssp.draft_id = d.id" in normalized_query
    assert "WHERE candidate_rank = 1" in normalized_query
    assert candidates == [
        {
            "requested_date_id": 116,
            "draft_id": 70,
            "profile_id": 25,
            "display_name": "Static In The Matrix",
            "email": "static@yceran.org",
            "contact_phone": None,
            "availability_status": "requested",
            "availability_email_sent_at_epoch": None,
            "is_profile_approved": True,
            "social_links": [
                {
                    "social_platform_id": 3,
                    "profile_name": "staticinmatrix",
                    "platform_name": "Instagram",
                    "url_format": "https://instagram.com/{profileName}",
                }
            ],
            "request_count": 3,
            "played_count": 2,
            "selection_status": None,
            "slot_number": None,
        }
    ]
