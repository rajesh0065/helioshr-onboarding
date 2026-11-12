# Architecture Diagram — HeliosHR Onboarding Automation

## System Overview (Mermaid)

```mermaid
flowchart TD
    subgraph Sources["Trigger Layer"]
        WD["Workday  HRIS\nNew hire record activated"]
    end

    subgraph Automation["n8n Automation Platform"]
        N8N["HTTP Trigger / Workday poll\nNormalize payload\nSign request with HMAC"]
    end

    subgraph Engine["Provisioning Engine  —  Python / FastAPI"]
        IDEM["Idempotency Check\nhash employee_id + email + start_date\nSQLite: processed_events"]
        CLAUDE["Claude  claude-sonnet\n─────────────────────────────\nValidate data quality\nDecide: provision / hold / reject\nAssign groups and Slack channels\nSurface governance flags"]
        DISPATCH["Parallel Dispatch\nThreadPoolExecutor x4\nRetry: 3x exponential backoff"]
        AUDIT["Audit Log  —  SQLite: audit_log\nsystem · success · attempts\nresource_id · timestamp"]
    end

    subgraph Targets["Provisioned Systems"]
        OKTA["Okta\nSSO + Groups API\nPOST /api/v1/users"]
        SLACK["Slack\nEnterprise invite\nChannel assignment"]
        GWS["Google Workspace\nAdmin SDK Directory API\nEmail + Drive + Calendar"]
        JIRA["Jira\nCloud REST API\nProject access by dept"]
    end

    subgraph MCP["MCP Server  —  runs alongside FastAPI"]
        MCP_TOOLS["Exposed Tools\n──────────────────────────────\nprovision_new_hire\nget_provisioning_status\napprove_held_hire\nget_audit_trail\n──────────────────────────────\nAuth: per-key API token\nScope: tool-level permissions\nTLS required · 100 req/min"]
    end

    subgraph Alerts["Alerting"]
        SLACK_ALERT["Slack Alert\nfailure notifications"]
        FS["FreshService Ticket\nhold and reject routing"]
    end

    subgraph Callers["MCP Callers"]
        AGENT["Claude AI Agent\ninternal workflow"]
        HROPS["HR Ops via Claude.ai\nSet up Priya, starts Monday"]
    end

    WD -->|"new hire activated\nwebhook / scheduled poll"| N8N
    N8N -->|"NewHireEvent JSON\nPOST /webhooks/workday"| IDEM
    IDEM -->|"new event"| CLAUDE
    IDEM -->|"duplicate — return cached"| AUDIT
    CLAUDE -->|"ProvisioningDecision\naction + systems + groups + flags"| DISPATCH
    CLAUDE -->|"hold or reject — no downstream calls"| AUDIT
    DISPATCH -->|"provision API call + retry"| OKTA
    DISPATCH -->|"invite + channels"| SLACK
    DISPATCH -->|"create account"| GWS
    DISPATCH -->|"add user + projects"| JIRA
    OKTA -->|"SystemResult"| AUDIT
    SLACK -->|"SystemResult"| AUDIT
    GWS -->|"SystemResult"| AUDIT
    JIRA -->|"SystemResult"| AUDIT
    AUDIT -->|"success=0 rows"| SLACK_ALERT
    AUDIT -->|"hold / reject events"| FS
    MCP_TOOLS <-->|"tool calls"| Engine
    AGENT -->|"tool calls"| MCP_TOOLS
    HROPS -->|"tool calls"| MCP_TOOLS

    style CLAUDE fill:#7c3aed,color:#fff
    style MCP fill:#1e40af,color:#fff
    style MCP_TOOLS fill:#1e3a8a,color:#fff
    style IDEM fill:#065f46,color:#fff
    style AUDIT fill:#78350f,color:#fff
```

## MCP Server — Tool Definitions

| Tool | Parameters | Scope required | What it does |
|---|---|---|---|
| `provision_new_hire` | employee_id, full_name, email, department, title, manager_email, start_date, location | `it_ops` | Triggers the full provisioning pipeline |
| `get_provisioning_status` | employee_id | `it_ops` · `hr_ops` · `claude_agent` | Returns current decision + per-system result |
| `approve_held_hire` | employee_id, approver_email | `it_ops` · `hr_ops` | Releases a held hire into provisioning |
| `get_audit_trail` | employee_id | `it_ops` · `hr_ops` · `claude_agent` | Full audit log for a hire |

**Security model:** Every MCP caller authenticates with an API key. Each key carries a scope list (`it_ops`, `hr_ops`, `claude_agent`). Tools check scope before executing. All traffic requires TLS. Rate limit: 100 req/min per key.

## Data Flow Summary

| Step | From | To | Data |
|---|---|---|---|
| 1 | Workday | n8n | New hire activation event |
| 2 | n8n | Provisioning Engine | Normalized `NewHireEvent` JSON |
| 3 | Engine | SQLite | Idempotency hash check |
| 4 | Engine | Claude | NewHireEvent for assessment |
| 5 | Claude | Engine | `ProvisioningDecision` (action, systems, groups, flags) |
| 6 | Engine x4 | Okta / Slack / GWS / Jira | Provisioning API calls |
| 7 | Each system | Engine | Success/failure + resource ID |
| 8 | Engine | SQLite audit_log | Per-system result |
| 9 | Engine | Slack / FreshService | Failure alert or hold ticket |

## Key Integration Points

- **Workday → n8n**: Workday Studio custom report trigger or REST API polling (n8n HTTP Request node on a schedule)
- **n8n → Engine**: HTTP POST to `/webhooks/workday`; n8n holds the Workday credential and signs the request with an HMAC header
- **Engine → Claude**: Anthropic Messages API; system prompt encodes governance rules
- **Engine → Okta**: Okta Users API (`POST /api/v1/users?activate=true`) + Groups API
- **Engine → Slack**: `users.admin.invite` (Enterprise Grid) or invite via email
- **Engine → Google Workspace**: Admin SDK Directory API (`POST /admin/directory/v1/users`)
- **Engine → Jira**: Jira Cloud REST API (`POST /rest/api/3/user`)
- **MCP → Engine**: FastAPI routes exposed as MCP tools; authenticated with per-key scopes
