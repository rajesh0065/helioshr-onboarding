# Executive Summary — HeliosHR Onboarding Automation
*For: Head of People Ops*

---

## What It Does (in plain language)

Right now, when IT gets a Slack message saying someone is hired, a person manually logs into five different systems — Okta, Google Workspace, Slack, Jira, FreshService — and sets up each account one by one. That takes 3–5 business days and often leaves new hires without tools on Day 1.

This system makes that automatic. The moment Workday marks a new hire as active, the system:

1. **Validates the data** — checks that the employee record looks correct (right ID format, company email, valid start date). An AI reviews the record and flags anything unusual before anything is set up.
2. **Provisions accounts in parallel** — Okta (single sign-on), Google Workspace (email and Drive), Slack (team channels), and Jira (project tools) are all created at the same time, in under 2 minutes.
3. **Logs everything** — every action is recorded: which system was set up, when, whether it succeeded, and why anything was flagged.
4. **Alerts on problems** — if any step fails, IT gets a Slack notification immediately with what failed and what to do.

New hires arrive on Day 1 with everything ready.

---

## What It Will Improve

| Metric | Today | With automation |
|---|---|---|
| Time to full access | 3–5 business days | Under 5 minutes |
| Manual IT steps per hire | ~20 | 0 (for standard hires) |
| Human error rate | Varies | Near zero (consistent rules applied every time) |
| Visibility into access status | None | Real-time audit log per employee |
| New hire Day-1 experience | Often blocked | Accounts ready before they log in |

**How we'd measure success:**
- Time-to-access: compare Workday activation timestamp to first Okta login
- IT ticket volume: count provisioning-related FreshService tickets before/after
- Day-1 access complaints: track HR survey scores for onboarding experience

---

## Risks and Limitations

| Risk | Mitigation |
|---|---|
| A bad data entry in Workday creates wrong accounts | The AI reviews every record before any account is created; unusual data is flagged for human approval before provisioning proceeds |
| A system (Okta, Slack, etc.) is down when a hire activates | The system retries automatically. If it still fails, IT is alerted within seconds and can retry manually with one click |
| A contractor gets too much access | The system applies different rules for contractors automatically (Okta + Slack only, no Google Workspace or Jira unless explicitly approved) |
| This is a new system and something unexpected happens | Full audit trail of every action; nothing is deleted automatically — only accounts are created, not removed |

**What this system does not do (yet):**
- Offboarding / account deactivation (that's a separate workflow with its own approvals)
- Salesforce provisioning (Sales team accounts still need RevOps approval — the system flags these but doesn't auto-provision)
- Hardware requests (still routed through FreshService as today)

---

## What You Need to Know to Feel Confident

**The system does not replace human judgment — it eliminates the manual queue.** Every borderline case (unusual hire record, non-standard email, start date that looks wrong) is automatically routed to HR or IT for approval before anything is provisioned. The automation handles the routine 90%; your team still owns the exceptions.

**Your new hires won't notice the change — except that things will work.** From their perspective, Day 1 access just happens. No waiting on IT, no "my Slack isn't set up yet" on the first morning.

**You can answer any question about any hire in under 30 seconds.** Every action the system takes is logged with a timestamp — which system, when, whether it succeeded, who approved an exception. If a new hire says they're missing Jira access, IT can see exactly what happened and why in one lookup.

**Rolling it back is safe.** The system only *creates* accounts — it never deletes anything automatically. If something goes wrong, the worst case is that a hire has accounts they shouldn't have yet, not that they're locked out. Turning off the automation returns the process exactly to where it is today.

**No new tools to learn or vendors to approve.** Workday, Okta, Slack, and Jira are already in your stack. The automation runs inside n8n, which IT already manages. The only new component is the AI review step, which uses Claude — the same tool HeliosHR has already adopted across internal workflows.
