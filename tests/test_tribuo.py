import backend.performer_workflow as workflow


def test_tribuo_tag_candidates_use_requested_name_patterns():
    candidates = workflow.tribuo_tag_candidates("Static In The Matrix")
    assert next(candidates) == "STAINT"

    candidates = workflow.tribuo_tag_candidates("Sunset")
    assert next(candidates) == "SUNSET"

    candidates = workflow.tribuo_tag_candidates("AB")
    assert next(candidates) == "AB0000"


def test_tribuo_tag_collision_candidates_are_six_character_uppercase_values():
    candidates = workflow.tribuo_tag_candidates("Static In The Matrix")
    values = [next(candidates) for _ in range(3)]
    assert values == ["STAINT", "STAI01", "STAI02"]
    assert all(len(value) == 6 and value.isalnum() and value.isupper() for value in values)


def test_registration_payload_normalizes_tribuo_checkbox():
    payload = workflow.normalize_profile_submission_payload(
        {
            "profile_type": "person",
            "display_name": "Test Artist",
            "contact_phone": "0400000000",
            "show_tribuo_link": True,
            "requested_event_ids": [12],
        },
        "artist@example.com",
    )
    assert payload["show_tribuo_link"] is True


def test_registration_payload_defaults_tribuo_checkbox_to_false():
    payload = workflow.normalize_profile_submission_payload(
        {
            "profile_type": "person",
            "display_name": "Test Artist",
            "contact_phone": "0400000000",
            "requested_event_ids": [12],
        },
        "artist@example.com",
    )
    assert payload["show_tribuo_link"] is False
