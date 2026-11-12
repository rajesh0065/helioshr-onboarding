# HeliosHR Onboarding Automation

**Assignment:** AI Automation & Integration Engineer — Take-Home
**Scenario:** HeliosHR (600-person B2B SaaS) — automate new hire provisioning triggered from Workday

## Quick Start

```powershell
# 1. Create venv and install dependencies
uv venv .venv
uv pip install fastapi uvicorn pydantic anthropic httpx rich python-dotenv --python .venv\Scripts\python.exe

# 2. Run the demo (no credentials needed — all APIs are mocked)
.venv\Scripts\python.exe demo.py

# 3. Optional: enable live Claude assessment
$env:ANTHROPIC_API_KEY = "sk-ant-..."
.venv\Scripts\python.exe demo.py

# 4. Optional: run the webhook server
.venv\Scripts\python.exe -m uvicorn main:app --reload
# POST http://localhost:8000/webhooks/workday  (body: NewHireEvent JSON)
# GET  http://localhost:8000/audit/{employee_id}
```

## Demo Scenarios

| # | What it shows |
|---|---|
| 1 | Engineering hire — Okta retries on first attempt, Jira also retries; all 4 systems succeed |
| 2 | Product hire — Jira times out on attempt 1, retries and succeeds |
| 3 | Sales hire — 3 systems provisioned; Salesforce governance flag raised |
| 4 | Contractor — Okta + Slack only; GWS and Jira excluded by policy |
| 5 | Bad employee ID (`HR-9999`) — rejected immediately, nothing provisioned |

## Project Structure

```
models.py                 Pydantic data models
audit.py                  SQLite idempotency store + audit trail
claude_handler.py         Claude data-quality gate (falls back to rules if no API key)
provisioning_engine.py    Core orchestrator — idempotency → assess → dispatch → retry → audit
mock_clients/             Realistic mocks for Okta, Slack, Google Workspace, Jira
main.py                   FastAPI webhook server
demo.py                   Standalone runnable demo
mcp_server.py             MCP server — exposes 4 tools over stdio (JSON-RPC 2.0)
n8n_workflow.json         n8n workflow export — importable into any n8n instance
architecture_diagram.md   Deliverable 1 — Mermaid diagram + MCP tool table
technical_writeup.md      Deliverable 2 — design decisions, failure handling, governance
executive_summary.md      Deliverable 4 — plain-language summary for Head of People Ops
ai_usage_statement.md     Deliverable 5 — AI usage statement
```

## MCP Server

The MCP server (`mcp_server.py`) exposes the provisioning engine as AI tooling over the standard MCP stdio transport.

**Tools:** `provision_new_hire` · `get_provisioning_status` · `approve_held_hire` · `get_audit_trail`

**Configure in Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "helioshr-onboarding": {
      "command": "C:/Users/rajesh.patnam/helioshr-onboarding/.venv/Scripts/python.exe",
      "args": ["C:/Users/rajesh.patnam/helioshr-onboarding/mcp_server.py"]
    }
  }
}
```

Once connected, an HR Ops user can type in Claude: *"Set up Priya Sharma — she starts Monday in Engineering"* and Claude will call `provision_new_hire` with the right parameters.

## n8n Workflow

Import `n8n_workflow.json` into n8n via **Settings → Import Workflow**. Set two environment variables:
- `PROVISIONING_ENGINE_URL` — base URL of the FastAPI server
- `WEBHOOK_SECRET` — shared secret for HMAC signing

Wire two credentials: **Workday OAuth2** and **Slack Bot**.

## Deliverables

- **Deliverable 1:** [architecture_diagram.md](architecture_diagram.md)
- **Deliverable 2:** [technical_writeup.md](technical_writeup.md)
- **Deliverable 3:** This repo — `demo.py` (working prototype) + `n8n_workflow.json` (importable n8n export) + `mcp_server.py` (live MCP server)
- **Deliverable 4:** [executive_summary.md](executive_summary.md)
- **Deliverable 5:** [ai_usage_statement.md](ai_usage_statement.md)
