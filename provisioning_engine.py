import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from models import NewHireEvent, ProvisioningDecision, SystemResult, ProvisioningResult
from audit import init_db, event_hash, already_processed, mark_processed, log_result
from claude_handler import assess
from mock_clients import okta, slack, google_workspace, jira

MAX_RETRIES = 3
BACKOFF_BASE = 1.0

SYSTEM_DISPATCHERS = {
    "okta": lambda hire, groups: okta.provision_user(
        hire.employee_id, hire.full_name, hire.email, hire.department.value, groups
    ),
    "slack": lambda hire, groups: slack.invite_user(
        hire.employee_id, hire.email, hire.full_name,
        [g for g in groups if g.startswith("#")]
    ),
    "google_workspace": lambda hire, groups: google_workspace.create_account(
        hire.employee_id, hire.email, hire.full_name, hire.department.value, hire.manager_email
    ),
    "jira": lambda hire, groups: jira.add_user(
        hire.employee_id, hire.email, hire.full_name, hire.department.value
    ),
}


def _dispatch_one(system: str, hire: NewHireEvent, groups: list[str]) -> SystemResult:
    fn = SYSTEM_DISPATCHERS.get(system)
    if not fn:
        return SystemResult(system=system, success=False, attempts=0,
                            message=f"No dispatcher registered for '{system}'")

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = fn(hire, groups)
            resource_id = result.get("id") or result.get("user_id") or result.get("account_id")
            return SystemResult(
                system=system, success=True, attempts=attempt,
                message="OK", resource_id=resource_id
            )
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

    return SystemResult(system=system, success=False, attempts=MAX_RETRIES,
                        message=str(last_err))


def _alert_slack_failure(hire: NewHireEvent, failed: list[SystemResult]):
    """Mock: in production posts to #it-alerts via Slack API."""
    systems = ", ".join(r.system for r in failed)
    print(f"  [alert:slack] FAILURE — {hire.full_name} ({hire.employee_id}): {systems} failed after {MAX_RETRIES} retries")


def _create_freshservice_ticket(hire: NewHireEvent, decision: str, reason: str):
    """Mock: in production POSTs to FreshService /api/v2/tickets."""
    print(f"  [alert:freshservice] TICKET — {decision.upper()} for {hire.full_name} ({hire.employee_id}): {reason}")


def process(hire: NewHireEvent) -> ProvisioningResult:
    init_db()

    key = event_hash(hire.employee_id, hire.email, hire.start_date)
    cached = already_processed(key)
    if cached:
        print(f"  [engine] Duplicate event — returning cached result (hash={key})")
        return ProvisioningResult(**cached)

    print(f"  [engine] Assessing {hire.full_name} ({hire.employee_id})…")
    decision: ProvisioningDecision = assess(hire)
    print(f"  [claude] Decision: {decision.action} — {decision.reason}")
    if decision.flags:
        for f in decision.flags:
            print(f"  [claude]   ⚠  {f}")

    system_results = []

    if decision.action == "provision":
        slack_channels = ["#general", f"#{hire.department.value.lower()}", "#new-hires"]
        augmented_groups = decision.groups + slack_channels

        # Okta is provisioned first — it is the SSO anchor for all other systems.
        # If Okta fails, there is no point provisioning GWS/Slack/Jira since the
        # hire cannot authenticate to any of them.
        non_okta = [s for s in decision.systems if s != "okta"]

        if "okta" in decision.systems:
            okta_result = _dispatch_one("okta", hire, augmented_groups)
            system_results.append(okta_result)
            log_result(hire.employee_id, hire.full_name, "okta",
                       "provision", okta_result.success, okta_result.attempts,
                       okta_result.message, okta_result.resource_id)
            status = "✓" if okta_result.success else "✗"
            print(f"  [okta] {status} attempt={okta_result.attempts} — {okta_result.message}")

            if not okta_result.success:
                _alert_slack_failure(hire, [okta_result])
                _create_freshservice_ticket(hire, "okta_failure",
                                            f"Okta provisioning failed after {MAX_RETRIES} retries — downstream systems skipped")
                # Short-circuit: no point provisioning downstream without SSO
                overall = False
                result = ProvisioningResult(
                    employee_id=hire.employee_id,
                    employee_name=hire.full_name,
                    decision=decision.action,
                    overall_success=overall,
                    system_results=system_results,
                    idempotency_key=key,
                )
                mark_processed(key, hire.employee_id, result.model_dump(), hire.model_dump())
                return result

        # Okta succeeded — provision remaining systems in parallel
        if non_okta:
            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = {
                    ex.submit(_dispatch_one, sys, hire, augmented_groups): sys
                    for sys in non_okta
                }
                for future in as_completed(futures):
                    sr = future.result()
                    system_results.append(sr)
                    log_result(
                        hire.employee_id, hire.full_name, sr.system,
                        "provision", sr.success, sr.attempts,
                        sr.message, sr.resource_id
                    )
                    status = "✓" if sr.success else "✗"
                    print(f"  [{sr.system}] {status} attempt={sr.attempts} — {sr.message}")

        failed = [r for r in system_results if not r.success]
        if failed:
            _alert_slack_failure(hire, failed)

    elif decision.action == "hold_for_review":
        log_result(hire.employee_id, hire.full_name, "workflow", "hold_for_review",
                   False, 0, decision.reason)
        _create_freshservice_ticket(hire, "hold_for_review", decision.reason)
        print(f"  [engine] Held — no downstream calls made")

    else:  # reject
        log_result(hire.employee_id, hire.full_name, "workflow", "reject",
                   False, 0, decision.reason)
        _create_freshservice_ticket(hire, "reject", decision.reason)
        print(f"  [engine] Rejected — {decision.reason}")

    overall = decision.action == "provision" and all(r.success for r in system_results)

    result = ProvisioningResult(
        employee_id=hire.employee_id,
        employee_name=hire.full_name,
        decision=decision.action,
        overall_success=overall,
        system_results=system_results,
        idempotency_key=key,
    )

    mark_processed(key, hire.employee_id, result.model_dump(), hire.model_dump())
    return result
