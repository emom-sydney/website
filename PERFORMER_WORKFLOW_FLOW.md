# Performer Workflow Flowchart

This file documents the current structure of `forms_bridge/performer_workflow.py` using Mermaid diagrams.

## End-To-End Flow

```mermaid
flowchart TD
    A[/POST performer-registration/start/] --> B[get_json_payload]
    B --> C[normalize_email]
    C --> D[connect to Postgres]
    D --> E[get_workflow_settings]
    E --> F[invalidate_unused_tokens for existing registration links]
    F --> G[generate_token_pair]
    G --> H[insert action_tokens registration_link]
    H --> I[send_registration_email via SMTP relay]
    I --> J[201 ok]

    K[/GET performer-registration/session?token/] --> L[get_action_token registration_link]
    L --> M[get_existing_profile_by_email]
    M --> N[get_available_events]
    N --> O[get_social_platforms]
    O --> P[return token-backed session JSON]

    Q[/POST performer-registration/submit/] --> R[get_json_payload]
    R --> S[get_action_token registration_link]
    S --> T[get_workflow_settings]
    T --> U[normalize_profile_submission_payload]
    U --> V[get_existing_profile_for_submission]
    V --> W[get_available_events]
    W --> X[ensure_requested_events_are_allowed]
    X --> Y[ensure_social_platforms_exist]
    Y --> Z[supersede_pending_drafts]
    Z --> AA[insert_profile_submission_draft]
    AA --> AB[insert_profile_submission_social_links]
    AB --> AC[insert_requested_dates]
    AC --> AD[get_moderator_emails]
    AD --> AE[create_moderation_links]
    AE --> AF[mark_action_token_used registration token]
    AF --> AG[send_moderation_emails]
    AG --> AH[201 ok]

    AI[/GET moderation/approve?token/] --> AJ[get_action_token moderation_approve]
    AJ --> AK[get_profile_submission_draft]
    AK --> AL{draft pending?}
    AL -- no --> AM[error page]
    AL -- yes --> AN[apply_approved_draft]
    AN --> AO[record_moderation_action approved]
    AO --> AP[finalize_draft_status approved]
    AP --> AQ[invalidate_moderation_tokens_for_draft]
    AQ --> AR[send_profile_approved_email]
    AR --> AS[success page]

    AT[/GET moderation/deny?token/] --> AU[get_action_token moderation_deny]
    AU --> AV[get_profile_submission_draft]
    AV --> AW{draft pending?}
    AW -- no --> AX[error page]
    AW -- yes --> AY[render_denial_form]

    AZ[/POST moderation/deny/] --> BA[get_action_token moderation_deny]
    BA --> BB[get_profile_submission_draft]
    BB --> BC{draft pending?}
    BC -- no --> BD[error page]
    BC -- yes --> BE[record_moderation_action denied]
    BE --> BF[finalize_draft_status denied]
    BF --> BG[invalidate_moderation_tokens_for_draft]
    BG --> BH[send_profile_denied_email]
    BH --> BI[success page]
```

## Business Process Diagram

```mermaid
flowchart TD
    A[Performer enters email on /perform/] --> B[System emails one-time registration link]
    B --> C[Performer opens token link]
    C --> D[Performer creates or edits profile]
    D --> E[Performer selects eligible Open Mic dates]
    E --> F[Submission stored as pending draft]
    F --> G[System matches existing profile by email, then by stage name if needed]
    G --> H[Moderators receive approve / deny email links plus existing-vs-submitted profile details]
    H --> I{Moderator decision}
    I -- Approve --> J[Draft applied to live profile]
    J --> K[Existing profile may be updated with new email address]
    K --> L[Artist role and social links updated]
    L --> M[Artist emailed approval]
    I -- Deny --> N[Moderator enters denial reason]
    N --> O[Artist emailed denial reason]

    M --> P[Requested dates remain recorded for later scheduling]
    O --> Q[Artist can submit a revised profile later]

    P --> R[Future workflow: 10-day availability confirmation]
    R --> S[Future workflow: 7-day admin lineup selection]
    S --> T[Future workflow: actual played lineup copied into performances]
```

## Route / Helper / Data Interaction Map

```mermaid
flowchart LR
    subgraph Routes
        R1[start_performer_registration]
        R2[get_performer_registration_session]
        R3[submit_performer_registration]
        R4[approve_profile_submission]
        R5[deny_profile_submission]
    end

    subgraph ValidationAndTokenHelpers
        H1[get_json_payload]
        H2[normalize_email]
        H3[normalize_profile_submission_payload]
        H4[get_action_token]
        H5[generate_token_pair]
        H6[invalidate_unused_tokens]
        H7[invalidate_moderation_tokens_for_draft]
        H8[mark_action_token_used]
    end

    subgraph ReadHelpers
        Q1[get_workflow_settings]
        Q2[get_existing_profile_by_email]
        Q3[get_existing_profile_by_display_name]
        Q4[get_existing_profile_by_id]
        Q5[get_existing_profile_for_submission]
        Q6[get_social_platforms]
        Q7[get_available_events]
        Q8[get_moderator_emails]
        Q9[get_profile_submission_draft]
    end

    subgraph WriteHelpers
        W1[supersede_pending_drafts]
        W2[insert_profile_submission_draft]
        W3[insert_profile_submission_social_links]
        W4[insert_requested_dates]
        W5[create_moderation_links]
        W6[apply_approved_draft]
        W7[upsert_artist_role]
        W8[replace_profile_social_links]
        W9[update_profile_visibility_from_requests]
        W10[record_moderation_action]
        W11[finalize_draft_status]
        W12[format_existing_profile_for_moderation]
    end

    subgraph MailHelpers
        M1[send_registration_email]
        M2[send_moderation_emails]
        M3[send_profile_approved_email]
        M4[send_profile_denied_email]
        M5[send_mail]
    end

    subgraph Tables
        T1[(app_settings)]
        T2[(action_tokens)]
        T3[(profiles)]
        T4[(profile_roles)]
        T5[(profile_social_profiles)]
        T6[(profile_submission_drafts)]
        T7[(profile_submission_social_profiles)]
        T8[(requested_dates)]
        T9[(moderation_actions)]
        T10[(events)]
        T11[(performances)]
        T12[(social_platforms)]
    end

    R1 --> H1 --> H2 --> Q1
    R1 --> H6 --> H5 --> T2
    R1 --> M1 --> M5

    R2 --> H4 --> T2
    R2 --> Q2 --> T3
    Q2 --> T4
    Q2 --> T5
    R2 --> Q7 --> T10
    Q7 --> T11
    R2 --> Q6 --> T12

    R3 --> H1
    R3 --> H4 --> T2
    R3 --> Q1 --> T1
    R3 --> H3
    R3 --> Q5
    Q5 --> Q2
    Q5 --> Q3
    Q3 --> Q4
    R3 --> Q7
    R3 --> W1 --> T6
    R3 --> W2 --> T6
    R3 --> W3 --> T7
    R3 --> W4 --> T8
    R3 --> Q8 --> T3
    Q8 --> T4
    R3 --> W5 --> T2
    R3 --> W12
    R3 --> H8 --> T2
    R3 --> M2 --> M5

    R4 --> H4 --> T2
    R4 --> Q9 --> T6
    Q9 --> T7
    Q9 --> T8
    R4 --> W6 --> T3
    W6 --> W7 --> T4
    W6 --> W8 --> T5
    W6 --> W9 --> T3
    W9 --> T10
    R4 --> W10 --> T9
    R4 --> W11 --> T6
    R4 --> H7 --> T2
    R4 --> M3 --> M5

    R5 --> H4 --> T2
    R5 --> Q9 --> T6
    R5 --> W10 --> T9
    R5 --> W11 --> T6
    R5 --> H7 --> T2
    R5 --> M4 --> M5
```

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Performer as Performer Browser
    participant Site as /perform/ page JS
    participant Bridge as forms_bridge
    participant DB as Postgres
    participant SMTP as SMTP Relay
    participant Mod as Moderator

    Performer->>Site: Open /perform/
    Site-->>Performer: Show email-only start form

    Performer->>Site: Submit email
    Site->>Bridge: POST /api/forms/performer-registration/start
    Bridge->>DB: Read app_settings
    Bridge->>DB: Invalidate old registration tokens
    Bridge->>DB: Insert new registration token
    Bridge->>SMTP: Send one-time registration email
    SMTP-->>Performer: Registration link email
    Bridge-->>Site: ok
    Site-->>Performer: “Check your inbox”

    Performer->>Site: Open emailed token link
    Site->>Bridge: GET /api/forms/performer-registration/session?token=...
    Bridge->>DB: Validate token
    Bridge->>DB: Load existing profile by email
    Bridge->>DB: Load social platform options
    Bridge->>DB: Compute eligible Open Mic dates
    Bridge-->>Site: Session JSON
    Site-->>Performer: Prefilled profile + event selection form

    Performer->>Site: Submit profile, social links, requested dates
    Site->>Bridge: POST /api/forms/performer-registration/submit
    Bridge->>DB: Validate token
    Bridge->>DB: Match existing profile by email
    alt No email match
        Bridge->>DB: Match existing profile by stage name
    end
    Bridge->>DB: Validate allowed dates + platforms
    Bridge->>DB: Supersede older pending drafts
    Bridge->>DB: Insert draft
    Bridge->>DB: Insert draft social links
    Bridge->>DB: Insert requested dates
    Bridge->>DB: Find moderators
    Bridge->>DB: Insert approve/deny moderation tokens
    Bridge->>DB: Mark registration token used
    Bridge->>SMTP: Send moderation emails with existing/live profile snapshot and submitted draft
    SMTP-->>Mod: Approve / deny links
    Bridge-->>Site: ok
    Site-->>Performer: “Sent for moderation”

    alt Moderator approves
        Mod->>Bridge: GET /api/forms/performer-registration/moderation/approve?token=...
        Bridge->>DB: Validate approve token
        Bridge->>DB: Load draft
        Bridge->>DB: Apply draft to live profile or update matched existing profile
        Bridge->>DB: Upsert artist role
        Bridge->>DB: Replace live social links
        Bridge->>DB: Set profile visibility window
        Bridge->>DB: Record moderation action
        Bridge->>DB: Mark draft approved
        Bridge->>DB: Invalidate both moderation links
        Bridge->>SMTP: Send approval email
        SMTP-->>Performer: Approval email
        Bridge-->>Mod: Success page
    else Moderator denies
        Mod->>Bridge: GET /api/forms/performer-registration/moderation/deny?token=...
        Bridge->>DB: Validate deny token
        Bridge->>DB: Confirm draft still pending
        Bridge-->>Mod: Denial reason form
        Mod->>Bridge: POST deny reason
        Bridge->>DB: Validate deny token again
        Bridge->>DB: Record moderation action
        Bridge->>DB: Mark draft denied
        Bridge->>DB: Invalidate both moderation links
        Bridge->>SMTP: Send denial email with reason
        SMTP-->>Performer: Denial email
        Bridge-->>Mod: Success page
    end
```

## Notes

- `get_available_events` currently restricts dates to Open Mic events only with `type_id = 1`.
- Submission-time profile matching now works by:
  - email first
  - then exact case-insensitive `display_name` if email did not match
- That means a changed email address can currently update an existing profile when the stage name matches.
- Moderator emails now include both the existing live profile snapshot and the submitted draft details when a match is found.
- `apply_approved_draft` currently sets `profile_visible_from` using the earliest requested event date.
- That visibility rule is a temporary approximation until the later admin selection workflow is implemented.
- Email delivery now goes through SMTP relay using `FORMS_SMTP_HOST` and `FORMS_SMTP_PORT`.
