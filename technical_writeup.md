# Technical Writeup — HeliosHR Onboarding Automation

## Design Decisions

### 1. n8n as the trigger layer, Python as the engine

n8n is already in the stack and excels at event wiring: it can poll Workday on a schedule, receive a webhook, transform the payload, and forward it. What n8n is not good at is stateful orchestration with retries, idempotency enforcement, and LLM calls that need fallback logic. That belongs in code.

The split: n8n handles the edge (Workday credential, trigger, payload normalization, alerting). The Python engine handles the core (idempotency, Claude assessment, parallel dispatch, audit). This keeps both sides simple and independently testable.

### 2. Claude as a governance gate, not the orchestrator

Claude is called once per new hire event. Its job is narrow: given structured employee data, return `provision | hold_for_review | reject` plus which systems and groups to assign. It never calls APIs or writes state.

This design has three advantages:
- **Blast radius is small**: if the LLM call fails or returns garbage, the engine falls back to rule-based assessment and continues. No hire gets silently skipped.
- **Auditability**: the prompt and response are logged. A reviewer can see exactly what Claude saw and why it decided what it did.
- **Rules stay legible**: the system prompt is the source of truth for governance rules (email domain checks, contractor restrictions, department-to-system mapping). It's readable by non-engineers without opening code.

### 3. Content-hash idempotency

The idempotency key is `sha256(employee_id + email + start_date)`. Using only `employee_id` isn't sufficient — a corrected rehire (same ID, different start date) should re-provision. Including `start_date` in the hash means a rescheduled hire creates a new key while a true duplicate webhook delivery is safely short-circuited.

### 4. Okta-first, then parallel dispatch with per-system retry

Okta is provisioned synchronously before any other system. It is the SSO anchor — if it fails, GWS, Slack, and Jira are skipped entirely (no orphaned accounts with no way to log in). An immediate Slack alert and FreshService ticket are created so IT can retry.

Once Okta succeeds, the remaining systems are dispatched in parallel (`ThreadPoolExecutor`). An Okta rate limit shouldn't block the Slack invite. Retry is per-system (3×, exponential backoff). Partial success is a first-class outcome recorded in the audit log — only the failed legs need to be replayed.

### 5. Field mapping at the boundary

Each system uses different field names. Mapping lives in the dispatcher callsite, not scattered across clients. Adding a new system means adding one entry to `SYSTEM_DISPATCHERS`.

---

## Failure Handling, Retries, and Edge Cases

| Scenario | Handling |
|---|---|
| Workday sends the same event twice | Idempotency hash fires; zero downstream calls on second delivery |
| Okta rate-limited (429) | Retry up to 3× with exponential backoff (1s, 2s, 4s) |
| One system fails after all retries | Partial result recorded; alert fired; other systems not rolled back (they're additive) |
| Claude API unavailable | Falls back to rule-based assessment; hire proceeds (no silent skip) |
| Claude returns malformed JSON | Exception caught; rule-based fallback used |
| Employee ID doesn't match EMP-XXXXX | Rejected immediately; no downstream calls; FreshService ticket created for HR to investigate |
| Non-company email domain | Held for review; FreshService ticket created; nothing provisioned until human approves |
| Contractor hire | Okta + Slack only; GWS and Jira excluded by default; flag in audit log |
| Start date in the past >7 days | Held for review — likely a data entry error or backdated termination re-hire |

**Rollback**: provisioning is additive (account creation). If a hire is rejected post-provisioning, deprovisioning is a separate workflow (Okta deactivate → GWS suspend → Slack deactivate). This is intentional: the hold/reject path blocks provisioning before it starts; it does not undo a completed provisioning run.

---

## Access Governance and Auditability

**Access governance:**
- Claude's system prompt is the policy document. Governance rules (which departments get which systems, what triggers a hold) live there, not in ad-hoc code paths. Changing a rule means changing the prompt — reviewable in a pull request like any other policy change.
- Okta is the SSO anchor and is provisioned first (before Slack, GWS, Jira). The reason: Okta controls login to all other systems. If it fails, the hire can't authenticate anywhere, so there's no point provisioning downstream. Failing fast on Okta prevents orphaned accounts in GWS or Jira with no way to log in.
- Group assignment is explicit in `ProvisioningDecision.groups` — Claude decides which Okta groups and Slack channels to assign, and that list is logged before any API call is made. No group is assigned without an audit record.
- The MCP server is the external governance boundary: each API key carries a scope (`it_ops`, `hr_ops`, `claude_agent`), and tools enforce scope before execution. HR Ops can query and approve held hires but cannot directly trigger provisioning — that requires IT Ops scope. This mirrors least-privilege in the human workflow.

**Auditability:**
- Every provisioning attempt writes a row to `audit_log`: system, success, attempt count, message, resource ID, timestamp.
- `processed_events` stores the full result JSON keyed by idempotency hash — full replay capability.
- Claude's decision (action, reason, flags) is logged before any downstream call.
- `GET /audit/{employee_id}` surfaces the complete trail for any hire.
- In production: audit log → Datadog / CloudWatch; `success = 0` rows trigger a PagerDuty / Slack alert within 60 seconds.

---

## What I Would Build Next

| Priority | Item | Current state | Why |
|---|---|---|---|
| 1 | Workday HMAC signature verification | Stub in `main.py` — skipped when no `WEBHOOK_SECRET` env var | Prevent spoofed provisioning events; wire in production with Workday-issued secret |
| 2 | Hold queue with Slack approval flow | FreshService ticket created; MCP `approve_held_hire` tool re-triggers provisioning | A Slack "approve/reject" interactive button is faster than a FreshService ticket for HR |
| 3 | Deprovisioning workflow | Not implemented | Terminations need the same parallel dispatch pattern in reverse |
| 4 | Postgres + connection pool | SQLite | SQLite is fine for a prototype; not for concurrent production traffic |
| 5 | Salesforce provisioning leg | Flag raised in audit log | Sales/Marketing currently gets a flag; it should auto-provision with RevOps approval |
| 6 | Claude prompt versioning | Prompt hardcoded in `claude_handler.py` | Pin the system prompt to a hash; diff it in code review like any other policy change |

---

## Assumptions

| Assumption | Impact if wrong |
|---|---|
| Workday can emit a webhook or be polled via REST | If neither, n8n uses a Workday Studio report scheduled export — adds latency |
| Email follows `firstname.lastname@helioshr.com` pattern | Email domain check in Claude prompt would need updating |
| Okta is the SSO provider for all four systems | If Jira or GWS uses a separate IdP, provisioning order changes |
| Contractors don't need GWS | If some contractors do, employment_type needs sub-types (e.g., `contractor-full-access`) |
| New hires always have a manager already in the system | If not, manager lookup adds a Workday API call before provisioning |
