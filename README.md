# VPC & Security Group Manager

**Status: backend foundation with VPC, subnet, and IP allocation management.**
This repository provides application, persistence, JWT authentication,
ownership-aware authorization, and the initial network resource endpoints.

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
- SQLAlchemy 2 and PostgreSQL by default
- Alembic-managed database schema
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
│   ├── users/
│   ├── vpcs/
│   ├── subnets/
│   └── ip_allocations/
├── domain/
└── providers/
    └── README.md
```

Each resource module owns its SQLAlchemy model and the corresponding schemas,
router, repository, and service when that behavior is implemented. Shared
domain types and database helpers live outside the entity modules. HTTP
routers delegate behavior to services, which use repositories for persistence.
The SQLAlchemy declarative base uses stable constraint naming to support
Alembic migrations. VPC, subnet, and IP allocation APIs apply the same
ownership-aware authentication. The `providers` package is a documented
architectural boundary only; it has no provider implementation.

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

Install dependencies, start PostgreSQL, apply migrations, and start the API:

```bash
pip install -r requirements.txt
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload
```

PostgreSQL is the default database. Application startup does not create tables;
the schema is managed by Alembic migrations.
Interactive API documentation is available at
<http://127.0.0.1:8000/docs>. API routes, including health, require a valid
bearer token except for `POST /auth/login`.

## Environment configuration

Copy `.env.example` to `.env` and set:

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | Signing key for access tokens; at least 32 characters | Required |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `DATABASE_URL` | SQLAlchemy connection URL | `postgresql+psycopg://vpc_manager:local-development-only@localhost:5432/vpc_manager` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `30` |
| `VPC_LIMIT_PER_OWNER` | Maximum active VPCs per owner | `5` |
| `VPC_PROVISIONING_DELAY_SECONDS` | Delay before a pending VPC is activated | `30` |
| `DATABASE_LOCK_TIMEOUT_MS` | Maximum wait for a PostgreSQL row lock | `5000` |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Localhost ports 3000 and 5173 |

Do not commit `.env` or use development signing keys in deployed environments.
The values in `.env.example` are local-development placeholders; replace them
with secure values where appropriate.

## Docker

Create `.env` from `.env.example`, set `SECRET_KEY`, then start the API and
PostgreSQL containers:

```bash
docker compose up --build
```

The API is exposed on port `8000`. The API container runs `alembic upgrade head`
before starting FastAPI. PostgreSQL data is stored in the `postgres-data` named
volume. Stop the services with `docker compose down`; the database volume is
retained.

## VPC API

The VPC endpoints are `POST/GET /vpcs` and `GET/PATCH/DELETE /vpcs/{id}`.
Creation validates canonical IPv4 CIDRs, prefix length, reserved ranges,
per-owner name uniqueness, overlap, and the configurable per-owner quota.
Public CIDRs are accepted with a warning in the response. New VPCs start as
`PENDING` and the response includes that initial state.

VPC ownership is resolved from the JWT user. Admins can access resources for
any owner; regular users only see their own VPCs. PATCH accepts only `name`
and `description`; status changes are internal. DELETE soft-deletes the VPC;
active subnets and their active IP allocations are soft-deleted in the same
transaction.

The background activation task waits `VPC_PROVISIONING_DELAY_SECONDS`
(default `30`) and then changes a still-pending VPC to `ACTIVE`. This
simplified task runs only while the API process is alive; it is not durable
across restarts and is not a distributed job scheduler. The per-owner quota is
configured by `VPC_LIMIT_PER_OWNER` (default `5`).

## Subnet API and allocation concurrency

Subnets are created/listed under `/vpcs/{vpc_id}/subnets` and read, updated,
or soft-deleted through `/subnets/{id}`. Omitting `cidr_block` selects the
first free block in ascending order; `prefix_length` chooses its size and
defaults to `/24`. A manual `cidr_block` can be used instead. `type` is
required, and `availability_zone` is stored without region validation. The
response includes `total_ips`, `usable_ips`, and `available_ips`.

Before allocation, the API locks the parent VPC row with `SELECT ... FOR
UPDATE`, then checks active child CIDRs and inserts the subnet in that same
transaction. The lock wait is limited by `DATABASE_LOCK_TIMEOUT_MS` (default
`5000`); a timeout returns `503` and `Retry-After`. PostgreSQL exclusion
constraints independently reject overlapping active CIDRs, returning `409`
if that final safeguard fires. The row lock serializes cooperating API
requests; the exclusion constraint also protects against other code paths
that omit the lock or have a bug. VPC deletion uses the same parent lock and
soft-deletes active subnets in the same transaction.

To reproduce an allocation race, create a VPC first, then issue two requests
for automatic `/24` subnets concurrently. Replace `<vpc-id>` with the returned
UUID:

```bash
for n in 1 2; do
  curl -sS -X POST "http://127.0.0.1:8000/vpcs/<vpc-id>/subnets" \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
    -d "{\"name\":\"parallel-$n\",\"type\":\"PRIVATE\",\"prefix_length\":24}" &
done
wait
```

Successful requests should return different CIDRs. If allocation cannot
proceed, the API returns a clear `409` or `503` rather than persisting an
overlap.

IP addresses are allocated under `/subnets/{subnet-id}/ip-allocations`.
Omitting `ip_address` chooses the first available IPv4 address. The network
address, the following three addresses, and the broadcast address are reserved;
manual requests for any of these addresses or addresses outside the subnet are
rejected. `GET /subnets/{subnet-id}/ip-allocations` lists active allocations,
while `GET /ip-allocations/{id}` and `DELETE /ip-allocations/{id}` operate on a
single allocation. Deleting an allocation is a soft delete, so the address can
be reused. Creation locks the subnet row and uses the same configurable lock
timeout as subnet creation; a timeout returns `503` with `Retry-After`, and an
active duplicate address returns `409`. Deleting a subnet or VPC soft-deletes
its active allocations synchronously in the same transaction.

For a manual check, create a subnet and replace `<subnet-id>` with its UUID.
Omit `ip_address` for automatic first-fit, or provide an available address:

```bash
curl -X POST http://127.0.0.1:8000/subnets/<subnet-id>/ip-allocations \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}'
curl -X POST http://127.0.0.1:8000/subnets/<subnet-id>/ip-allocations \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"ip_address":"10.20.0.20","description":"application host"}'
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/subnets/<subnet-id>/ip-allocations
```

The Swagger UI at <http://127.0.0.1:8000/docs> exposes the same endpoints.

## Manual VPC checks

With the API running, open <http://127.0.0.1:8000/docs>. API routes require a
valid bearer token except `POST /auth/login`. To try the API, use an
operationally provisioned admin account, create regular users through the
authenticated registration endpoint, and log in as each account:

```bash
ADMIN_TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@example.com&password=<admin-password>' | jq -r .access_token)
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"StrongPassword@123"}'
ALICE_TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=alice@example.com&password=StrongPassword@123' | jq -r .access_token)
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob","email":"bob@example.com","password":"StrongPassword@123"}'
BOB_TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=bob@example.com&password=StrongPassword@123' | jq -r .access_token)
VPC_ID=$(curl -sS -X POST http://127.0.0.1:8000/vpcs \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"example-vpc","cidr_block":"10.20.0.0/16","region":"us-east-1"}' \
  | jq -r .id)
curl -i -H "Authorization: Bearer $BOB_TOKEN" \
  "http://127.0.0.1:8000/vpcs/$VPC_ID" # 404: Bob does not own Alice's VPC
curl -i -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://127.0.0.1:8000/vpcs/$VPC_ID" # 200: admin can read any owner's VPC
```

If Alice requests a VPC owned by another user, the API returns `404`. An admin
can inspect and manage it. Admin-created VPCs accept an optional `owner_id`;
when omitted, the VPC belongs to the admin. Regular-user creation schemas do
not include `owner_id`, and attempts to send it return `422`. The admin's
destination owner is used for the name uniqueness, quota, and CIDR-overlap
checks.

## Authentication and authorization

- `POST /auth/register` creates a regular user and requires an existing
  authenticated account. Passwords must contain at least eight characters,
  an uppercase letter, a digit, and a supported special character.
- `POST /auth/login` accepts OAuth2 form fields (`username` is the user's
  email) and returns a bearer token.
- `GET /users/me` returns the authenticated user's public profile.
- `GET /admin/users` and `DELETE /admin/users/{user_id}` require the `admin`
  role. An administrator cannot delete their own account.

Registration intentionally does not allow clients to select an administrator
role. Initial administrator provisioning is an operational task and is not
implemented as a public endpoint. User account activity is checked when
resolving the user from a JWT; inactive accounts receive `401`. The access
token contains the user's ID and role, while the current database user record
is authoritative for activity and permissions.

## Tests

Install project requirements and run:

```bash
pytest
```

Unit tests use an isolated in-memory SQLite database and cover authentication,
password validation, user profile access, administrator authorization, health,
and absence of the removed legacy routes.
VPC API integration tests require a migrated PostgreSQL database and can be
enabled with `RUN_POSTGRES_INTEGRATION_TESTS=1`.
Subnet integration tests also require PostgreSQL and include concurrent
first-fit requests and an overlap-constraint check performed without the
application lock.

## Migrations

Alembic is configured against `DATABASE_URL`. Generate and apply migrations
with:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

The initial migration enables `pgcrypto` and `btree_gist` and creates the user,
VPC, subnet, and IP allocation tables. PostgreSQL integration checks run the
migrations in CI before the unit tests.

## Roadmap

The VPC portion of Phase 01 is in progress; the remaining phases are not started:

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
