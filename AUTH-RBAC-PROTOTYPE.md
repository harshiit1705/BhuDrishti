# BhuDrishti Authentication & RBAC — Prototype

## What is implemented

- Backend-issued signed, expiring session token.
- PBKDF2 password hashing; plaintext passwords are not stored.
- Role-based authorization on sensitive API actions.
- Login and access-request UI at `frontend/auth.html`.
- Pending registration workflow; an administrator activates accounts.
- Administrator user-management page at `frontend/user-management.html`.
- Browser stores only the active session token and public user profile.
- Verification identity is taken from the authenticated backend user instead of trusting a browser-supplied surveyor name.

## Roles

| Role | Main prototype permissions |
|---|---|
| ADMIN | All workflow and user-management actions |
| PROJECT_OFFICER | Project/data ingestion, AI processing, export |
| GIS_OPERATOR | Dataset upload and AI inference |
| FIELD_SURVEYOR | Submit/correct/reject and certify verification; export workflow output |
| REVENUE_OFFICER | Review/certify/reject and export |

## Demo accounts

- `admin@bhudrishti.gov.in` / `Bhu@Admin2026`
- `project@bhudrishti.gov.in` / `Bhu@Project2026`
- `gis@bhudrishti.gov.in` / `Bhu@GIS2026`
- `surveyor@bhudrishti.gov.in` / `Bhu@Survey2026`
- `revenue@bhudrishti.gov.in` / `Bhu@Revenue2026`

These credentials are prototype-only and must be replaced before any real deployment.

## Important production limitation

The current prototype user store is SQLite and therefore inherits the same Vercel `/tmp` limitation as the rest of the prototype. It is suitable for a controlled SIH demonstration but is **not** a production identity system. A production deployment should use a managed persistent database or government/enterprise identity provider, a strong environment-managed signing secret, HTTPS-only cookies or another secure token strategy, audit logging, account recovery, MFA where required, and server-side session revocation.
