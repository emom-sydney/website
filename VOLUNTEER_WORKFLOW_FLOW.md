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
    I --> J[load role availability by event and role]
    J --> K[return session JSON]

    L[/POST volunteer-registration/submit/] --> M[validate registration token and payload]
    M --> N[match profile by email then display name]
    N --> O[validate event ids and role keys]
    O --> P[insert draft and social links]
    P --> Q[insert draft volunteer role claims]
    Q --> R{approved volunteer profile already exists?}
    R -- yes --> S[apply volunteer draft to profile]
    S --> T[materialize role claims into live claims table]
    T --> U[mark draft approved]
    U --> V[send volunteer approved email]
    R -- no --> W[create volunteer moderation tokens]
    W --> X[send moderation emails]

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

- Effective role capacity uses:
  - `event_volunteer_role_overrides.capacity_override` when present
  - otherwise `volunteer_roles.default_capacity`
- New claims become:
  - `selected` while selected count is below capacity
  - `standby` once capacity is full
- Cancellation sets claim status to `cancelled`.
- Selected cancellation auto-promotes the oldest standby claim for the same event and role.
