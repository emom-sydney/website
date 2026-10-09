import pytest

import backend.performer_workflow as workflow
from backend.app import create_app


def group_payload():
    return {
        "profile_type": "group",
        "display_name": "Antistatic",
        "contact_phone": "0400 000 000",
        "social_links": [],
        "associates": [
            {
                "client_key": "niknak",
                "profile_id": 10,
                "display_name": "NikNak",
                "social_links": [],
            },
            {
                "client_key": "mike",
                "profile_id": None,
                "display_name": "Mike",
                "social_links": [
                    {"social_platform_id": 3, "profile_name": "mike_visuals"}
                ],
            },
            {
                "client_key": "julie",
                "profile_id": None,
                "display_name": "Julie",
                "social_links": [],
            },
        ],
        "group_members": [
            {"associate_key": "niknak", "is_primary_contact": True},
            {"associate_key": "mike", "role_label": "visuals"},
        ],
        "requested_events": [
            {
                "event_id": 42,
                "performer_display_name": "Antistatic featuring Julie",
                "guest_credits": [
                    {"associate_key": "julie", "credit_label": "featuring"}
                ],
            }
        ],
    }


def test_group_submission_normalizes_members_billing_and_guests():
    normalized = workflow.normalize_profile_submission_payload(
        group_payload(), "niknak@example.com"
    )

    assert normalized["requested_event_ids"] == [42]
    assert normalized["requested_events"][0]["performer_display_name"] == "Antistatic featuring Julie"
    assert normalized["requested_events"][0]["guest_credits"] == [
        {"associate_key": "julie", "credit_label": "featuring", "sort_order": 0}
    ]
    assert normalized["group_members"][0]["is_primary_contact"] is True
    assert normalized["associates"][1]["social_links"][0]["profile_name"] == "mike_visuals"


def test_group_submission_requires_exactly_one_primary_contact():
    payload = group_payload()
    payload["group_members"][0]["is_primary_contact"] = False

    with pytest.raises(ValueError, match="exactly one primary contact"):
        workflow.normalize_profile_submission_payload(payload, "niknak@example.com")


def test_person_submission_cannot_add_group_members():
    payload = group_payload()
    payload["profile_type"] = "person"

    with pytest.raises(ValueError, match="Only group profiles"):
        workflow.normalize_profile_submission_payload(payload, "niknak@example.com")


def test_requested_event_cannot_be_duplicated():
    payload = group_payload()
    payload["requested_events"].append(dict(payload["requested_events"][0]))

    with pytest.raises(ValueError, match="only be included once"):
        workflow.normalize_profile_submission_payload(payload, "niknak@example.com")


def test_group_relationship_routes_are_registered():
    app = create_app()
    paths = {str(rule) for rule in app.url_map.iter_rules()}

    assert "/api/v1/profiles/member-candidates" in paths
    assert "/api/v1/admin/profiles/<int:profile_id>/relationships" in paths
    assert "/api/v1/admin/performances/<int:performance_id>/credits" in paths
