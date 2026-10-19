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

Built-in demo identities are for isolated local development only. The production backend refuses authentication for those known demo email addresses, does not reconstruct their sessions from JWT claims, and does not reseed or reset their passwords. The hosted login page does not publish the built-in demo passwords. Create a real production administrator using the controlled bootstrap command in `POSTGRES-MIGRATION-RUNBOOK.md`.

## Important production limitation

Authentication users are stored through the shared SQLite-local/PostgreSQL-production adapter. Production requires a managed PostgreSQL database and a strong `BHUDRISHTI_AUTH_SECRET`; the app fails closed when these configuration requirements are missing. This remains a prototype authentication system: a real deployment should additionally consider an enterprise identity provider, secure session strategy, account recovery, MFA where required, and server-side session revocation.
