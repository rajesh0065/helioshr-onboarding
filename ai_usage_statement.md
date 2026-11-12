# AI Usage Statement

## Tools Used

- **Claude Code (claude-sonnet-4-6)** — primary development environment throughout this project
- **Claude (claude-sonnet-4-6)** — integrated directly into the prototype as the data-quality and governance gate

---

## What I Applied AI To

| Task | AI used | How |
|---|---|---|
| Initial scaffolding | Claude Code | Generated the base file structure for models, audit, and mock clients |
| Mock client design | Claude Code | Drafted the Okta, Slack, Google Workspace, and Jira mock implementations |
| System prompt design | Me + Claude Code | I wrote the governance rules (which depts get which systems, what triggers a hold); Claude Code helped format and stress-test edge cases in the prompt |
| Technical writeup | Me, Claude Code for structure | I made the design decisions; Claude Code helped organize the writeup and check that all five required sections were covered |
| Executive summary | Me, with Claude Code for clarity | I wrote the substance; Claude Code helped translate technical decisions into plain language |
| Architecture diagram | Me | ASCII diagrams written manually — AI is unreliable for precise ASCII layout |

---

## How I Validated and Refined AI Outputs

**Mock clients:** Claude Code's first draft of the Okta mock didn't simulate a transient failure (the scenario where retry logic is actually exercised). I added the `_call_count` counter and the conditional `raise ConnectionError` manually so the demo actually demonstrates retry, not just happy-path success.

**System prompt:** Claude Code generated a reasonable draft but missed the contractor employment-type distinction. I added the contractor rules explicitly (Okta + Slack only) because that's a real governance boundary that gets people fired if it's wrong — it needed to be deliberate, not emergent.

**Idempotency key:** Claude Code initially suggested using only `employee_id` as the unique key. I changed it to `hash(employee_id + email + start_date)` — the same reasoning as in the previous BetterUp prototype: Workday can re-fire events with corrected values, and a pure ID check would silently skip a legitimate re-hire.

**Executive summary:** Claude Code's first draft included too much technical detail for a non-technical audience. I rewrote the risk section to avoid words like "idempotency" and "ThreadPoolExecutor" and grounded it in outcomes the Head of People Ops actually cares about.

---

## Where I Chose NOT to Use AI

- **Architecture diagram**: AI-generated Mermaid diagrams tend to produce structurally valid but semantically shallow graphs — nodes connected without reflecting the actual data flow logic. I wrote the Mermaid manually so the arrows carry labeled payloads (e.g., "ProvisioningDecision: action + systems + groups + flags") and the subgraph groupings match the real architectural boundaries.
- **n8n workflow JSON**: The n8n node schema and connection format is specific enough that AI output would require significant correction. I wrote `n8n_workflow.json` by hand against the n8n 1.x schema, which is faster than iterating on AI-generated output that gets node types or connection arrays wrong.
- **Final review pass**: I read every file before including it in the submission. The goal was to catch anything that looked plausible but was wrong — especially in the governance logic, where a confident-sounding but incorrect rule is worse than no rule.

---

## AI Strategy Summary

I used Claude Code as a fast, capable pair programmer for boilerplate and structure, then applied my own judgment to every decision that had a real-world consequence: which systems get provisioned for which roles, what triggers a hold vs. a reject, how the idempotency key is constructed, and how to explain the system to a non-technical stakeholder without losing accuracy. The AI accelerated execution; the judgment was mine.

**For the debrief:** I'm prepared to walk through any file in the submission and explain the design choice behind it. The two decisions I'd most want to discuss are (1) why Claude is a narrow classifier rather than the orchestrator — and what the failure modes of the alternative would look like — and (2) how the idempotency key was designed and why a pure `employee_id` check is insufficient for Workday's re-fire behavior.
