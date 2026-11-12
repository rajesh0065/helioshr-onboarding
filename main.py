import hashlib
import hmac
import os
from fastapi import FastAPI, HTTPException, Request, Depends
from models import NewHireEvent, ProvisioningResult
from provisioning_engine import process
from audit import init_db, get_audit

app = FastAPI(title="HeliosHR Onboarding Automation", version="1.0")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


async def verify_hmac(request: Request):
    """
    Verifies the X-HeliosHR-Signature header sent by n8n.
    In production: reject requests that fail signature check.
    Stub: logs the verification result but does not block (no secret configured in dev).
    """
    signature = request.headers.get("X-HeliosHR-Signature", "")
    if WEBHOOK_SECRET:
        body = await request.body()
        expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        print("  [hmac] No WEBHOOK_SECRET configured — signature check skipped (dev mode)")


@app.on_event("startup")
def startup():
    init_db()


@app.post("/webhooks/workday", response_model=ProvisioningResult,
          dependencies=[Depends(verify_hmac)])
async def workday_webhook(event: NewHireEvent):
    """
    Receives a new hire activation event from Workday (or n8n relay).
    Runs Claude assessment then provisions across Okta, Slack, Google Workspace, Jira.
    """
    return process(event)


@app.get("/audit/{employee_id}")
async def audit(employee_id: str):
    """Returns full audit trail for an employee."""
    rows = get_audit(employee_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No audit records found")
    return rows


@app.get("/health")
async def health():
    return {"status": "ok"}
