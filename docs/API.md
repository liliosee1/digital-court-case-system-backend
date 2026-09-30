# Digital Court Case Tracking API

Base URL: `http://localhost:8000/api/`

The API uses the existing MySQL tables. It does not create tables. All collection
endpoints are paginated and return `count`, `next`, `previous`, and `results`.
The default page size is 25; clients may request `?page=2&page_size=50` (maximum
100).

## Run locally

The project reads secrets and database settings from `.env` or environment
variables. `.env` is ignored by Git. For a new checkout, copy `.env.example` to
`.env`, generate a private Django secret key, and enter the existing MySQL
connection values. Do not run migrations for the unmanaged court tables.

```powershell
py -3.13 -m venv venv
Copy-Item .env.example .env
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py runserver
```

If the existing virtual environment or `.env` is already present, keep it and do
not overwrite it. Update `.env` with the local database connection and a newly
generated `DJANGO_SECRET_KEY` when setting up another machine.

For production deployment on Railway, follow [the Railway deployment guide](RAILWAY_DEPLOYMENT.md).

Check the project and run the database-free API unit tests with:

```powershell
py manage.py check
py manage.py shell -c "from cases.tests import run_isolated_tests; raise SystemExit(run_isolated_tests())"
```

The isolated unit-test command uses mocks and does not create a test database.

## Authentication

`POST /api/auth/login/` accepts:

```json
{
  "email": "user@example.org",
  "password": "your password"
}
```

On success it returns a signed Bearer token (valid for eight hours) and safe user
information. Send the token on protected requests:

```http
Authorization: Bearer <token>
```

Login is limited to 10 requests per minute per client IP. The API does not have
user registration; user accounts and role assignment are maintained by the
system administrator.

For browser frontends, the default CORS allow-list supports local development on
ports 3000 and 5173. Set `CORS_ALLOWED_ORIGINS` to the exact deployed frontend
origins; the API does not allow wildcard origins or credentialed cookies.

## Role access

| Resource/action | Administrator | Court Clerk | Judge |
| --- | --- | --- | --- |
| Read cases, hearings, parties, history, lookups, dashboard | Yes | Yes | Yes |
| Create or update cases, hearings, parties, case-party links | Yes | Yes | No |
| Delete cases, hearings, parties, case-party links | Yes | No | No |
| Manage users and roles | Yes | No | No |

Judge users see only hearings assigned to themselves. Case lists and case
history remain visible to all three roles under the current project policy.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/` | API links |
| POST | `/api/auth/login/` | Sign in |
| GET, POST | `/api/cases/` | List and create cases |
| GET, PUT, PATCH, DELETE | `/api/cases/<id>/` | Read and manage one case |
| GET, POST | `/api/hearings/` | List and schedule hearings |
| GET, PUT, PATCH, DELETE | `/api/hearings/<id>/` | Read and manage one hearing |
| GET, POST | `/api/parties/` | List and add parties |
| GET, PUT, PATCH, DELETE | `/api/parties/<id>/` | Read and manage one party |
| GET, POST | `/api/case-parties/` | List and link parties to cases |
| GET, PUT, PATCH, DELETE | `/api/case-parties/<id>/` | Read and manage a case-party link |
| GET | `/api/case-history/` | Read case history |
| GET | `/api/case-history/<id>/` | Read one history event |
| GET | `/api/courtrooms/` | List courtrooms |
| GET | `/api/judges/` | List users with the Judge role |
| GET | `/api/roles/` | List role IDs and names (Administrator only) |
| GET, POST | `/api/users/` | List and create user accounts (Administrator only) |
| GET, PUT, PATCH, DELETE | `/api/users/<id>/` | Read and manage one user (Administrator only) |
| GET | `/api/dashboard/summary/` | Case and hearing totals |
| GET | `/api/schema/` or `/api/docs/` | OpenAPI schema |

Administrators create users through `POST /api/users/` with `full_name`, `email`,
`password`, and an existing `role` ID. The password must pass Django's password
validators; the API stores only its PBKDF2 hash and never returns the password or
hash. Use `GET /api/roles/` to retrieve role IDs. The last Administrator cannot
remove their own role or delete their account.

## Cases

Search and filter cases with:

- `search`: matches case number, title, or description
- `status`: case status
- `case_type`: type of case
- `assigned_judge`: user ID
- `filed_after`, `filed_before`: filing date range (`YYYY-MM-DD`)

Example: `/api/cases/?search=CASE-2026&status=Registered&page=1`

Create a case (the creator is taken from the token):

```json
{
  "case_number": "CIV-2026-0042",
  "case_type": "Civil",
  "title": "Sample matter",
  "description": "Optional case details",
  "filing_date": "2026-10-01",
  "status": "Registered",
  "assigned_judge": 3
}
```

Case creation and updates add entries to `case_history`. A case with hearings
or linked parties cannot be deleted; change its status to retain those records.
The existing schema cascades case history when a case is physically deleted.

## Hearings

Filters: `case`, `judge`, `courtroom`, `status`, `date_from`, and `date_to`.
Scheduling requires an existing case, a user with the Judge role, and an
Available courtroom. Scheduled hearings must be today or later. The API rejects
a booking if that judge or room already has an active hearing at the same date
and time. Cancelled and Completed hearings do not block a slot. Hearing changes
are recorded in case history.

```json
{
  "case": 1,
  "judge": 3,
  "courtroom": 2,
  "hearing_date": "2026-11-02",
  "hearing_time": "10:30:00",
  "status": "Scheduled",
  "notes": "Initial hearing"
}
```

The current database already contains overlapping hearing records. They are
returned as stored; the API prevents new conflicts and does not rewrite old
records.

## Parties, links, and history

Create parties with `full_name` and `party_type`; phone, email, and address are
optional. Link a party to a case by POSTing `{"case": 1, "party": 2}` to
`/api/case-parties/`. Filter links with `?case=1` or `?party=2`.

History is read-only through the API. Case and hearing changes create events
with the authenticated user as the actor. Filter with `?case=1`, `?user=2`, or
`?action=updated`.

## Errors

- `400`: invalid fields, foreign keys, or date/filter input
- `401`: missing, invalid, or expired token; invalid credentials
- `403`: authenticated role is not allowed to perform the action
- `404`: requested record does not exist
- `409`: operation conflicts with related court records
- `429`: login rate limit reached

The OpenAPI schema is available from `/api/schema/` and can be used by frontend
tools to inspect request and response definitions.
