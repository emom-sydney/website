# Volunteer Workflow Flowchart

This file documents `forms_bridge/volunteer_workflow.py` and the volunteer role-claim lifecycle.

## End-To-End Flow

```mermaid
flowchart TD
    A[/POST volunteer-registration/start/] --> B[validate email]
    B --> C[invalidate old volunteer registration tokens]
    C --> D[create volunteer_registration_link token]
    D --> E[send volunteer registration email]

    F[/GET volunteer-registration/session?token/] --> G[validate registration token]
    G --> H[load prefill profile and social platforms]
    H --> I[load future events]
    I --> J[load event role availability by event and role]
    J --> K[load non-event general role options]
    K --> L[return session JSON]

    M[/POST volunteer-registration/submit/] --> N[validate registration token and payload]
    N --> O[match profile by email then display name]
    O --> P[validate event role claims and general role claims]
    P --> Q[insert draft and social links]
    Q --> R[insert draft event claims and draft general claims]
    R --> S{approved volunteer profile already exists?}
    S -- yes --> T[apply volunteer draft to profile]
    T --> U[materialize event and general claims into live claim tables]
    U --> V[mark draft approved]
    V --> W[send volunteer approved email]
    S -- no --> X[create volunteer moderation tokens]
    X --> Y[send moderation emails]

    Y[/GET volunteer-registration/moderation/approve?token/] --> Z[validate approve token]
    Z --> ZA[apply volunteer draft to profile]
    ZA --> ZB[materialize live role claims]
    ZB --> ZC[record moderation action approved]
    ZC --> ZD[finalize draft approved]

    ZE[/GET|POST volunteer-registration/moderation/deny?token/] --> ZF[validate deny token]
    ZF --> ZG[record moderation action denied]
    ZG --> ZH[finalize draft denied]
    ZH --> ZI[optional fresh volunteer edit link]

    ZJ[/POST volunteer-registration/claims/start/] --> ZK[validate email]
    ZK --> ZL{approved volunteer profile found?}
    ZL -- yes --> ZM[create volunteer_claims_link token]
    ZM --> ZN[send claims link email]
    ZL -- no --> ZO[return generic success]

    ZP[/GET volunteer-registration/claims/session?token/] --> ZQ[validate claims token]
    ZQ --> ZR[load profile claims]
    ZR --> ZS[return claims JSON]

    ZT[/POST volunteer-registration/claims/cancel/] --> ZU[validate claims token and claim id]
    ZU --> ZV[cancel selected or standby claim]
    ZV --> ZW{was selected?}
    ZW -- yes --> ZX[promote oldest standby for same event and role]
    ZX --> ZY[send promoted standby email]
    ZW -- no --> ZZ[done]
```

## Data Notes

- Effective event role capacity uses:
  - `event_volunteer_role_overrides.capacity_override` when present
  - otherwise `volunteer_roles.default_capacity`
- New event-role claims become:
  - `selected` while selected count is below capacity
  - `standby` once capacity is full
- Non-event general roles are stored as active/withdrawn claims independent of event dates.
- Cancellation sets event-role claim status to `cancelled`.
- Selected event-role cancellation auto-promotes the oldest standby claim for the same event and role.
