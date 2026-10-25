# Public demo login setup

The five built-in BhuDrishti demo accounts are disabled on Vercel by default. To enable them for a public showcase:

1. Deploy this source to the BhuDrishti backend project on Vercel.
2. In Vercel → Project → Settings → Environment Variables, add `BHUDRISHTI_ENABLE_PUBLIC_DEMO_USERS` with value `true` for Production.
3. Confirm `DATABASE_URL` points to the dedicated BhuDrishti demo database and that `BHUDRISHTI_AUTH_SECRET` is a strong secret of at least 32 characters.
4. Run `python backend/migrate_postgres_schema.py` against that database before enabling demo logins.
5. Redeploy the backend. The application seeds/restores the five demo accounts on startup when the flag is enabled.
6. Test the login endpoint and each role in the deployed frontend.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Administrator | `admin@bhudrishti.gov.in` | `Bhu@Admin2026` |
| Project Officer | `project@bhudrishti.gov.in` | `Bhu@Project2026` |
| GIS / AI Operator | `gis@bhudrishti.gov.in` | `Bhu@GIS2026` |
| Field Surveyor | `surveyor@bhudrishti.gov.in` | `Bhu@Survey2026` |
| Revenue Officer | `revenue@bhudrishti.gov.in` | `Bhu@Revenue2026` |

## Security warning

These credentials are public and the Administrator account has the `ADMIN` role. Anyone who knows the credentials can act as that role, and all visitors share the same identities. Enable this only for a dedicated demo database containing synthetic/demo data. Do not enable these accounts against sensitive or authoritative cadastral records. Public shared accounts also cannot provide reliable attribution of individual actions.
