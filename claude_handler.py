import os
import json
import re
from datetime import date
from models import NewHireEvent, ProvisioningDecision

SYSTEM_PROMPT = """You are an IT access governance agent at HeliosHR.
When a new hire record arrives from Workday, your job is to:
1. Validate the data quality and flag anomalies
2. Decide which systems to provision and which groups/channels to assign
3. Flag anything that needs human review before provisioning proceeds

You must respond with valid JSON only — no commentary outside the JSON block.

Response schema:
{
  "action": "provision" | "hold_for_review" | "reject",
  "reason": "one sentence explanation",
  "systems": ["okta", "slack", "google_workspace", "jira"],
  "groups": ["list of Okta groups or Slack channels to assign"],
  "flags": ["any warnings for the reviewer"]
}

Rules:
- If email domain is not @helioshr.com, hold for review
- If start_date is in the past by more than 7 days, hold for review
- If employee_id looks malformed (not EMP-XXXXX pattern), reject
- If department or title is missing/blank, hold for review
- Engineering/Product/Design gets Jira; Sales/Marketing gets Salesforce note in flags
- All full-time hires get Okta + Google Workspace + Slack
- Contractors get Okta + Slack only (no Google Workspace or Jira by default)"""


def _rule_based(hire: NewHireEvent) -> ProvisioningDecision:
    flags = []
    action = "provision"
    systems = ["okta", "slack", "google_workspace"]
    groups = [f"dept-{hire.department.lower()}", "all-staff"]

    if not re.match(r"^EMP-\d{5}$", hire.employee_id):
        return ProvisioningDecision(
            action="reject",
            reason=f"Employee ID '{hire.employee_id}' does not match EMP-XXXXX format",
            systems=[], groups=[], flags=["Malformed employee_id — likely a data entry error"]
        )

    if not hire.email.endswith("@helioshr.com"):
        action = "hold_for_review"
        flags.append(f"Non-standard email domain: {hire.email}")

    try:
        start = date.fromisoformat(hire.start_date)
        days_past = (date.today() - start).days
        if days_past > 7:
            action = "hold_for_review"
            flags.append(f"Start date {hire.start_date} is {days_past} days in the past — possible data entry error or backdated rehire")
    except ValueError:
        action = "hold_for_review"
        flags.append(f"start_date '{hire.start_date}' is not a valid YYYY-MM-DD date")

    if hire.employment_type == "contractor":
        systems = ["okta", "slack"]
        flags.append("Contractor: Google Workspace and Jira not provisioned by default")

    if hire.department in ("Engineering", "Product", "Design") and hire.employment_type != "contractor":
        if "jira" not in systems:
            systems.append("jira")
        groups.append("jira-users")

    if hire.department in ("Sales", "Marketing"):
        flags.append("Sales/Marketing: Salesforce access requires separate approval from RevOps")

    return ProvisioningDecision(
        action=action,
        reason="Rule-based assessment passed" if action == "provision" else "Flagged for review",
        systems=systems,
        groups=groups,
        flags=flags
    )


def assess(hire: NewHireEvent) -> ProvisioningDecision:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [claude] No API key — using rule-based fallback")
        return _rule_based(hire)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = json.dumps(hire.model_dump(), indent=2)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}]
        )
        raw = response.content[0].text.strip()
        # strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("` \n")
        data = json.loads(raw)
        return ProvisioningDecision(**data)
    except Exception as e:
        print(f"  [claude] Error: {e} — falling back to rules")
        return _rule_based(hire)
