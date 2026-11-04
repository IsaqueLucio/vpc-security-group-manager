# VPC & Security Group Manager

**Status: initial backend foundation.** This repository currently provides
application, persistence, authentication, authorization, and test
infrastructure. No VPC-domain phase is marked complete, and no VPC or network
management behavior has been implemented.

## Project overview

The planned application is a backend for managing cloud networks and security
groups. Its future scope includes VPCs, subnets and IP addresses, route tables,
security group rules, configuration validation, approvals, audit records, and
simulated provisioning. Those capabilities are roadmap items only.

The current objective is to provide a maintainable FastAPI foundation from
which those features can be developed incrementally. The API currently exposes
generic user registration and login, the current-user profile, administrator
user management, and health endpoints.

## Technology stack

- Python 3.12+
- FastAPI and Uvicorn
- Pydantic Settings and Pydantic validation
- SQLAlchemy 2 and SQLite by default
- Alembic configuration for future schema migrations
- JWT access tokens and bcrypt password hashing
- Pytest and FastAPI `TestClient`
- Docker and Docker Compose

## Architecture

```text
app/
├── main.py
├── core/
│   ├── config.py
│   ├── dependencies.py
│   ├── exceptions.py
│   └── security.py
├── database/
│   ├── base.py
│   ├── session.py
│   └── migrations/
├── modules/
│   ├── auth/
│   └── users/
└── providers/
    └── README.md
```

HTTP routers delegate authentication and user-management behavior to services.
Services use repositories for user persistence. The SQLAlchemy declarative base
uses stable constraint naming to support future Alembic migrations. The
`providers` package is a documented architectural boundary only; it has no
provider or provisioning implementation.

Future domain modules should be introduced when their implementation begins.
Empty modules and placeholder CRUD endpoints are intentionally not included.

## Development setup

Requirements: Python 3.12 (the version used for validation) and `pip`.

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Replace the example `SECRET_KEY` with a randomly generated value of at least
32 characters before running the application. For example:

```bash
openssl rand -hex 32
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The default local database is SQLite at `./vpc_manager.db`. Tables for the
currently implemented user model are created when the application starts.
Interactive API documentation is available at
<http://127.0.0.1:8000/docs>; the health endpoint is
<http://127.0.0.1:8000/health>.

## Environment configuration

Copy `.env.example` to `.env` and set:

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | Signing key for access tokens; at least 32 characters | Required |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `DATABASE_URL` | SQLAlchemy connection URL | `sqlite:///./vpc_manager.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `30` |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Localhost ports 3000 and 5173 |

Do not commit `.env` or use development signing keys in deployed environments.
For a non-SQLite database, configure a matching SQLAlchemy DBAPI driver.

## Docker

Create `.env` from `.env.example`, set `SECRET_KEY`, then start the container:

```bash
docker compose up --build
```

The API is exposed on port `8000`. Compose stores the SQLite database in the
`app-data` named volume. Stop the service with `docker compose down`; the
database volume is retained.

## Authentication and authorization

- `POST /auth/register` creates a regular user. Passwords must contain at
  least eight characters, an uppercase letter, a digit, and a supported
  special character.
- `POST /auth/login` accepts OAuth2 form fields (`username` is the user's
  email) and returns a bearer token.
- `GET /users/me` returns the authenticated user's public profile.
- `GET /admin/users` and `DELETE /admin/users/{user_id}` require the `admin`
  role. An administrator cannot delete their own account.

Registration intentionally does not allow clients to select an administrator
role. Initial administrator provisioning is an operational task and is not
implemented as a public endpoint.

## Tests

Install project requirements and run:

```bash
pytest
```

Tests use an isolated in-memory SQLite database and cover authentication,
password validation, user profile access, administrator authorization, health,
and absence of the removed legacy routes.

## Migrations

Alembic is configured against the same `DATABASE_URL`. As domain models are
added, generate and apply migrations with:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

The foundation currently uses SQLAlchemy metadata initialization at startup;
there is no initial Alembic revision yet. Migration generation and rollout
should become the schema-management path before domain schema changes are
introduced.

## Roadmap

All domain phases below remain **not started**:

1. VPC and IP address management.
2. Subnets and network segmentation.
3. Route tables and routing.
4. Security groups and firewall rules.
5. Configuration validation and diagnostics.
6. Firewall requests and approvals.
7. Audit records.
8. Simulated provisioning and provider boundaries.

The repository is at the foundation stage and is being prepared to begin
**Phase 01: VPC and IP Address Management**. No work in that phase is claimed
as complete.
