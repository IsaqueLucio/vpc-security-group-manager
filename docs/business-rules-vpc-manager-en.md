# Business Rules — vpc-security-group-manager (Phase 01)

Portfolio project: FastAPI service for managing VPCs, subnets, and IP allocation, built as preparation for a Junior Developer — VPC role (Magalu Cloud). Consolidated document with all Phase 01 decisions, organized into 5 groups.

---

## Group 1 — VPC

**Attributes:** `id` (UUID), `name` (required), `cidr_block` (IPv4 CIDR), `description` (optional), `region` (required), `status` (`PENDING | ACTIVE | ERROR | DELETED`), `created_at` / `updated_at` (UTC).

| RN | Name | Rule |
|---|---|---|
| 1.1 | Ownership | VPCs belong to an individual user. Name is unique per owner, not globally — two different users may have VPCs with the same name. |
| 1.2 | Exact CIDR uniqueness | An exact CIDR duplicate is rejected within the same owner. (In practice this is subsumed by RN 1.6's overlap check — decide at implementation time whether to keep it as a separate check for clearer error messages, or treat it as a special case of overlap.) |
| 1.3 | Prefix range | VPC prefix between `/16` and `/28` (AWS-like default). |
| 1.4 | Private/public CIDR | Both allowed (RFC 1918 and public ranges). A non-blocking warning is returned when the CIDR is public. |
| 1.5 | Reserved CIDR ranges | Reject creation if the CIDR is contained in `0.0.0.0/8`, `127.0.0.0/8`, `169.254.0.0/16`, `224.0.0.0/4`, or `240.0.0.0/4`. "Contained in", not just "equal to". |
| 1.6 | Overlap between VPCs of the same owner | No VPC of a given user may have a CIDR that overlaps (fully or partially) with another VPC of the same user. Overlap across different users is allowed. The check ignores VPCs with `status = DELETED`. |
| 1.7 | Strict canonicalization | A CIDR with host bits set outside the mask (e.g. `10.0.5.0/16`) is rejected with a clear error — never silently masked/corrected. |
| 1.8 | VPC limit per user | Fixed limit, configurable via environment variable (suggested default: 5, matching AWS's default per-account/region quota). |
| 1.9 | VPC deletion | Cascading deletion: soft-deletes (inactivates) child resources (subnets, IP allocations). `status` becomes `DELETED`. The cascade is synchronous, within the same transaction (RN 3.3). |
| 1.10 | State machine | `PENDING` on creation → a background job transitions it to `ACTIVE` after a configurable interval, simulating asynchronous provisioning. `ERROR` is reserved for failures of a real provider adapter (future phase). `DELETED` via soft delete (RN 1.9). |

---

## Group 2 — CIDR, Subnets, and IP Addresses

**Subnet attributes:** `id` (UUID), `vpc_id` (required), `name` (required), `cidr_block`, `type` (`PUBLIC | PRIVATE`, required), `availability_zone` (optional, no validation yet), `status` (same state machine as VPC), `created_at` / `updated_at`.

**IP Allocation attributes:** `id` (UUID), `subnet_id` (required), `ip_address`, `description`/`label` (optional), `status`, `created_at` / `updated_at`.

| RN | Name | Rule |
|---|---|---|
| 2.1 | Subnet creation | Two ways: manual CIDR, or automatic allocation from a requested size/prefix. **Automatic is the default** when the client does not send `cidr_block`. |
| 2.2 | Containment | The subnet's CIDR must be fully contained within the parent VPC's CIDR. |
| 2.3 | No overlap between sibling subnets | Two subnets of the same VPC may not overlap. Across different VPCs there is nothing to compare. |
| 2.4 | Subnet prefix range | `/16`–`/28`, and the prefix must be **equal to or larger** (equal or smaller network) than the parent VPC's. |
| 2.5 | Automatic allocation algorithm | First-fit: scans candidate blocks of the requested size in increasing order from the start of the VPC's CIDR, returns the first one without overlap, ignoring soft-deleted subnets. |
| 2.6 | Subnet type | `type` is user-declared metadata at creation time (`PUBLIC` or `PRIVATE`), with no default — it must be explicitly provided. No real routing semantics (Internet Gateway/NAT) in Phase 01; that is deferred to a future Route Tables phase. |
| 2.7 | Availability zone | The `availability_zone` field exists from now on, but is unvalidated in Phase 01. Future rule (deferred, pending a regions/zones catalog): the subnet's AZ must belong to the parent VPC's `region`. |
| 2.8 | Subnet status | Subnets reuse the same state machine as VPCs (`PENDING | ACTIVE | ERROR | DELETED`). |
| 2.9 | Reserved IPs per subnet | AWS convention: the first 4 addresses (network, reserved gateway, 2 reserved by the provider) and the last address (broadcast) of each subnet are blocked from allocation. In a `/24` (256 addresses), 251 remain usable. |
| 2.10 | IP allocation model | A generic `IP Allocation` resource, not tied to a real compute instance — reserves a single address within a subnet. Manual (specific address) or automatic (default), reusing the same first-fit logic from RN 2.5 at the single-address level. |
| 2.11 | IP uniqueness | Two active `IP Allocation` records in the same subnet cannot point to the same address. The check ignores soft-deleted allocations. |
| 2.12 | IP release | Soft-deleting an `IP Allocation` frees the address for future allocation. |

---

## Group 3 — CRUD and API Behavior

| RN | Name | Rule |
|---|---|---|
| 3.1 | Immutability | Structural fields (`cidr_block`, `vpc_id`, `subnet_id`) are immutable after creation. Only `name`, `description`, and (for subnets) `type` can be changed via `PATCH`. |
| 3.2 | Operational state guard *(fixed)* | Child-resource creation is blocked only when the parent is `DELETED` or `ERROR`. **Not blocked when the parent is `PENDING`** — this avoids a race with the asynchronous transition from RN 1.10/2.8. |
| 3.3 | Deletion cascade | Synchronous, within the same transaction: deleting a VPC marks all active descendants (subnets, IP allocations) as `DELETED` in the same operation. |
| 3.4 | Listing | List endpoints support pagination and relevant filters (e.g. by `status`, `type`, `vpc_id`). |
| 3.5 | Error code mapping | `422` for a structurally/mathematically invalid payload (malformed CIDR, prefix out of range). `409` for a valid payload that conflicts with current state (duplicate, overlap, quota exceeded, first-fit exhaustion, parent in a state that blocks child creation). `404` for a resource that does not exist **or** belongs to another user (RN 4.2) **or** a mutation attempt on a `DELETED` resource. |
| 3.6 | Non-blocking warnings | Warning messages (e.g. public CIDR, RN 1.4) are returned in the response without failing the request. |
| 3.7 | Computed metrics | Subnet responses include `total_ips`, `usable_ips` (`total_ips - 5`), `available_ips` (`usable_ips` minus active allocations). Never negative, since the smallest allowed prefix (`/28`) guarantees `usable_ips >= 11`. |
| 3.8 | Deletion semantics | `DELETE` returns `200` with the resource in `DELETED` state. A second deletion attempt on an already-`DELETED` resource returns `404` (not idempotent in the "always succeeds" sense). |
| 3.9 | Route design | Nested routes for creation/listing under the parent resource (e.g. `POST/GET /vpcs/{id}/subnets`). Direct routes for single-resource operations (`GET/PATCH/DELETE /subnets/{id}`). |

---

## Group 4 — Security and RBAC

| RN | Name | Rule |
|---|---|---|
| 4.1 | Ownership inherited through the hierarchy | `owner_id` is stored only on the VPC, not duplicated on subnet/IP allocation — ownership of children is always resolved by walking up to the VPC. |
| 4.2 | 404 instead of 403 across tenants | Attempting to access/modify another user's resource returns `404` (not `403`), to avoid confirming the resource's existence to someone without access (anti-enumeration). |
| 4.3 | Admin privileges | The `admin` user has read/write access to resources owned by anyone. |
| 4.4 | Authentication required | All endpoints require a valid JWT. |
| 4.5 | `owner_id` delegation | Only `admin` can set `owner_id` at creation time, on behalf of another user. Regular users don't have that field available at all — implemented via **separate Pydantic schemas** (one for regular users, without the field; one for admins, with the field as optional), rather than a runtime permission check. |
| 4.6 | Validations against the correct owner context | Quota (RN 1.8), uniqueness, and overlap checks, when an admin creates on behalf of another user, are validated against the target `owner_id`, never against the admin's own `owner_id`. |
| 4.7 | Active-user check | Every authenticated request confirms the user account is active, reusing the same lookup already performed to resolve the user from the JWT (no extra query). |
| 4.8 | `status` is read-only via the public API | `status` cannot be changed via `PATCH` by regular users — it only changes through the internal lifecycle (the background job from RN 1.10, the cascade from RN 1.9, or, optionally, an admin-only endpoint to force transitions). |

---

## Group 5 — Persistence

| RN | Name | Rule |
|---|---|---|
| 5.1 | Database engine | PostgreSQL as the application's default, with Docker Compose for local development and CI. |
| 5.2 | Concurrency in first-fit allocation | Pessimistic lock (`SELECT ... FOR UPDATE`) on the parent resource before computing the first-fit, **plus** a database exclusion constraint (GiST) as a safety net. Lock-acquisition timeout → `503` with `Retry-After`. Database constraint firing despite the lock → `409`. |
| 5.3 | Native network types | `cidr_block` and `ip_address` use PostgreSQL's native `CIDR`/`INET` types, not `VARCHAR`. |
| 5.4 | Database-generated UUIDs and timestamps | `id` via `gen_random_uuid()` (`pgcrypto` extension). `created_at`/`updated_at` via `server_default`/`server_onupdate`, never computed in the application. |
| 5.5 | Database-level exclusion constraint for overlap | `EXCLUDE USING gist` (`btree_gist` extension) on `vpcs` (`owner_id` equality + `cidr_block` overlap) and on `subnets` (`vpc_id` equality + `cidr_block` overlap), filtered by `status != 'DELETED'`. Final guarantee for RN 1.6/2.3, independent of any future application bug. |
| 5.6 | Partial unique indexes | `UNIQUE (owner_id, name) WHERE status != 'DELETED'` on `vpcs`; `UNIQUE (vpc_id, name) WHERE status != 'DELETED'` on `subnets`; `UNIQUE (subnet_id, ip_address) WHERE status != 'DELETED'` on `ip_allocations`. |
| 5.7 | Performance indexes | B-tree indexes on `vpcs(owner_id)`, `vpcs(status)`, `subnets(vpc_id)`, `subnets(status)`, `ip_allocations(subnet_id)`, `ip_allocations(status)`. |
| 5.8 | Referential integrity | Foreign keys with `ON DELETE RESTRICT` (never `CASCADE`) — the system never performs hard deletes, only soft deletes (RN 1.9/3.3); `RESTRICT` guards against an accidental physical `DELETE`. |
| 5.9 | Database checks (defense in depth) | `masklen(cidr_block) BETWEEN 16 AND 28` on `vpcs`/`subnets`; `status` as a native PostgreSQL `ENUM`, not a free `VARCHAR`. |
| 5.10 | Alembic migrations | Schema managed only through manually reviewed migrations (autogenerate doesn't reliably capture `EXCLUDE`/`CHECK` constraints). `Base.metadata.create_all()` never runs outside isolated unit tests that don't use Postgres. |
| 5.11 | Transaction isolation | `READ COMMITTED` (PostgreSQL's default) is sufficient, since concurrency is resolved via explicit locking (RN 5.2), not stricter isolation. |
| 5.12 | Tests against real PostgreSQL | Integration tests run against a real PostgreSQL instance (Testcontainers), never SQLite — native types, `EXCLUDE USING gist`, and partial indexes have no faithful equivalent in SQLite. |

---

## Out of scope (explicitly deferred)

- Archiving/purging old `DELETED` records.
- Table partitioning.
- Read replicas.
- Real Route Tables / Internet Gateway / NAT (the routing semantics behind a subnet's `type`).
- A regions/availability-zones catalog (validation for RN 2.7).
