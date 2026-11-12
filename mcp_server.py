"""
MCP server for HeliosHR Onboarding Automation.

Exposes four tools to AI agents and HR/IT ops:
  - provision_new_hire
  - get_provisioning_status
  - approve_held_hire
  - get_audit_trail

Run alongside the FastAPI app:
    .venv/Scripts/python.exe mcp_server.py

The server listens on stdio (standard MCP transport).
Configure it in Claude Desktop / claude_desktop_config.json:
  {
    "mcpServers": {
      "helioshr-onboarding": {
        "command": "C:/Users/rajesh.patnam/helioshr-onboarding/.venv/Scripts/python.exe",
        "args": ["C:/Users/rajesh.patnam/helioshr-onboarding/mcp_server.py"],
        "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
      }
    }
  }
"""

import json
import sys
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Minimal MCP stdio transport — no external dependency
# Each message is a JSON-RPC 2.0 object on its own line (Content-Length framed)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "provision_new_hire",
        "description": (
            "Trigger the full provisioning pipeline for a new hire. "
            "Creates accounts in Okta, Slack, Google Workspace, and Jira "
            "(subject to Claude's data-quality gate and department rules). "
            "Required scope: it_ops."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id":    {"type": "string", "description": "EMP-XXXXX format"},
                "full_name":      {"type": "string"},
                "email":          {"type": "string", "format": "email"},
                "department":     {"type": "string"},
                "title":          {"type": "string"},
                "manager_email":  {"type": "string", "format": "email"},
                "start_date":     {"type": "string", "description": "YYYY-MM-DD"},
                "location":       {"type": "string"},
                "employment_type":{"type": "string", "enum": ["full-time", "contractor"], "default": "full-time"}
            },
            "required": ["employee_id", "full_name", "email", "department",
                         "title", "manager_email", "start_date", "location"]
        }
    },
    {
        "name": "get_provisioning_status",
        "description": (
            "Return the provisioning decision and per-system result for a hire. "
            "Required scope: it_ops, hr_ops, or claude_agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"}
            },
            "required": ["employee_id"]
        }
    },
    {
        "name": "approve_held_hire",
        "description": (
            "Release a hire that was held for review into the provisioning pipeline. "
            "Requires the approver's email for the audit trail. "
            "Required scope: it_ops or hr_ops."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id":    {"type": "string"},
                "approver_email": {"type": "string", "format": "email"}
            },
            "required": ["employee_id", "approver_email"]
        }
    },
    {
        "name": "get_audit_trail",
        "description": (
            "Return the full audit log for a hire: every system provisioned, "
            "attempt count, success/failure, and timestamps. "
            "Required scope: it_ops, hr_ops, or claude_agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"}
            },
            "required": ["employee_id"]
        }
    }
]

# ---------------------------------------------------------------------------
# Tool handlers — call the provisioning engine and audit module directly
# ---------------------------------------------------------------------------

def _handle_provision_new_hire(args: dict) -> str:
    from models import NewHireEvent
    from provisioning_engine import process
    hire = NewHireEvent(**args)
    result = process(hire)
    return json.dumps(result.model_dump(), indent=2)


def _handle_get_provisioning_status(args: dict) -> str:
    from audit import _conn
    employee_id = args["employee_id"]
    with _conn() as conn:
        row = conn.execute(
            "SELECT event_hash, processed_at, result_json FROM processed_events WHERE employee_id = ?",
            (employee_id,)
        ).fetchone()
    if not row:
        return json.dumps({"error": f"No provisioning record found for {employee_id}"})
    result = json.loads(row[2])
    return json.dumps({
        "employee_id": employee_id,
        "idempotency_key": row[0],
        "processed_at": row[1],
        "decision": result.get("decision"),
        "overall_success": result.get("overall_success"),
        "systems": [
            {"system": r["system"], "success": r["success"], "attempts": r["attempts"]}
            for r in result.get("system_results", [])
        ]
    }, indent=2)


def _handle_approve_held_hire(args: dict) -> str:
    from audit import get_audit, log_result, _conn, get_held_event
    from models import NewHireEvent
    from provisioning_engine import process

    employee_id = args["employee_id"]
    approver = args["approver_email"]

    rows = get_audit(employee_id)
    held = [r for r in rows if r.get("action") == "hold_for_review"]
    if not held:
        return json.dumps({"error": f"No held record found for {employee_id}"})

    event_data = get_held_event(employee_id)
    if not event_data:
        return json.dumps({"error": f"Original event data not found for {employee_id} — cannot re-trigger automatically"})

    log_result(employee_id, held[0].get("employee_name", ""), "workflow",
               f"approved_by:{approver}", True, 0,
               f"Manually approved by {approver} at {datetime.utcnow().isoformat()}")

    # Clear idempotency so engine will re-process
    with _conn() as conn:
        conn.execute("DELETE FROM processed_events WHERE employee_id = ?", (employee_id,))

    # Re-trigger provisioning with the stored original event
    hire = NewHireEvent(**event_data)
    result = process(hire)
    return json.dumps({
        "status": "approved_and_provisioned",
        "employee_id": employee_id,
        "approver": approver,
        "provisioning_result": result.model_dump()
    }, indent=2)


def _handle_get_audit_trail(args: dict) -> str:
    from audit import get_audit
    rows = get_audit(args["employee_id"])
    if not rows:
        return json.dumps({"error": f"No audit records for {args['employee_id']}"})
    return json.dumps(rows, indent=2)


HANDLERS = {
    "provision_new_hire":      _handle_provision_new_hire,
    "get_provisioning_status": _handle_get_provisioning_status,
    "approve_held_hire":       _handle_approve_held_hire,
    "get_audit_trail":         _handle_get_audit_trail,
}

# ---------------------------------------------------------------------------
# MCP stdio transport (JSON-RPC 2.0, Content-Length framing)
# ---------------------------------------------------------------------------

def _send(obj: dict):
    body = json.dumps(obj)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def _recv() -> dict | None:
    header = sys.stdin.readline()
    if not header:
        return None
    length = int(header.split(":")[1].strip())
    sys.stdin.readline()  # blank line
    return json.loads(sys.stdin.read(length))


def serve():
    while True:
        msg = _recv()
        if msg is None:
            break

        method = msg.get("method", "")
        req_id = msg.get("id")

        if method == "initialize":
            _send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "helioshr-onboarding", "version": "1.0"},
                    "capabilities": {"tools": {}}
                }
            })

        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": TOOL_DEFINITIONS}
            })

        elif method == "tools/call":
            tool_name = msg["params"]["name"]
            tool_args  = msg["params"].get("arguments", {})
            handler = HANDLERS.get(tool_name)
            if not handler:
                _send({
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                })
                continue
            try:
                result_text = handler(tool_args)
                _send({
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False
                    }
                })
            except Exception as e:
                _send({
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True
                    }
                })

        elif method == "notifications/initialized":
            pass  # no response needed

        else:
            if req_id is not None:
                _send({
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                })


if __name__ == "__main__":
    serve()
