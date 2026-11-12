"""
HeliosHR Onboarding Automation — demo
Runs 5 scenarios without any live credentials.
"""
import os
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from models import NewHireEvent
from provisioning_engine import process

console = Console()

SCENARIOS = [
    {
        "label": "1 — Engineering hire (Okta retries on first attempt; all 4 systems succeed)",
        "hire": NewHireEvent(
            employee_id="EMP-00042",
            full_name="Priya Sharma",
            email="priya.sharma@helioshr.com",
            department="Engineering",
            title="Senior Software Engineer",
            manager_email="alex.chen@helioshr.com",
            start_date="2026-11-17",
            location="San Francisco, CA",
        ),
    },
    {
        "label": "2 — Product hire (Jira retries on first attempt)",
        "hire": NewHireEvent(
            employee_id="EMP-00043",
            full_name="Marco Rivera",
            email="marco.rivera@helioshr.com",
            department="Product",
            title="Product Manager",
            manager_email="sarah.jones@helioshr.com",
            start_date="2026-11-17",
            location="New York, NY",
        ),
    },
    {
        "label": "3 — Sales hire (no Jira; Salesforce flag raised)",
        "hire": NewHireEvent(
            employee_id="EMP-00044",
            full_name="Aisha Okonkwo",
            email="aisha.okonkwo@helioshr.com",
            department="Sales",
            title="Account Executive",
            manager_email="tom.white@helioshr.com",
            start_date="2026-11-17",
            location="Chicago, IL",
        ),
    },
    {
        "label": "4 — Contractor (Okta + Slack only, no GWS/Jira)",
        "hire": NewHireEvent(
            employee_id="EMP-00045",
            full_name="Lee Park",
            email="lee.park@helioshr.com",
            department="Design",
            title="UX Contractor",
            manager_email="lisa.ray@helioshr.com",
            start_date="2026-11-17",
            location="Remote",
            employment_type="contractor",
        ),
    },
    {
        "label": "5 — Bad employee ID → rejected immediately",
        "hire": NewHireEvent(
            employee_id="HR-9999",
            full_name="Test User",
            email="test@helioshr.com",
            department="HR",
            title="HR Analyst",
            manager_email="boss@helioshr.com",
            start_date="2026-11-17",
            location="Remote",
        ),
    },
    {
        "label": "6 — Non-company email → held for review, FreshService ticket created",
        "hire": NewHireEvent(
            employee_id="EMP-00046",
            full_name="Jordan Casey",
            email="jordan.casey@contractor-agency.com",
            department="Operations",
            title="Operations Analyst",
            manager_email="ops.lead@helioshr.com",
            start_date="2026-11-17",
            location="Remote",
        ),
    },
]


def run():
    # remove stale db so scenarios are always fresh
    if os.path.exists("helioshr_audit.db"):
        os.remove("helioshr_audit.db")

    console.print(Panel.fit(
        "[bold cyan]HeliosHR Onboarding Automation[/bold cyan]\n"
        "Workday → Claude → Okta / Slack / Google Workspace / Jira\n"
        "[dim]All API calls are mocked — no live credentials needed[/dim]"
    ))

    summary_rows = []

    for i, scenario in enumerate(SCENARIOS, 1):
        console.print(f"\n[bold yellow]Scenario {scenario['label']}[/bold yellow]")
        result = process(scenario["hire"])

        systems_col = ", ".join(
            f"[green]{r.system}[/green]" if r.success else f"[red]{r.system}[/red]"
            for r in result.system_results
        ) or f"[dim]{result.decision}[/dim]"

        summary_rows.append({
            "scenario": scenario["label"].split("—")[0].strip(),
            "employee": result.employee_name,
            "decision": result.decision,
            "systems": systems_col,
            "ok": result.overall_success,
        })

    console.print("\n")
    tbl = Table(title="Summary", show_lines=True)
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("Employee")
    tbl.add_column("Decision")
    tbl.add_column("Systems")
    tbl.add_column("Overall")

    for i, row in enumerate(summary_rows, 1):
        overall = "[green]✓[/green]" if row["ok"] else (
            "[yellow]held/rejected[/yellow]" if row["decision"] in ("hold_for_review", "reject")
            else "[red]partial[/red]"
        )
        tbl.add_row(str(i), row["employee"], row["decision"], row["systems"], overall)

    console.print(tbl)
    console.print("\n[dim]Audit log written to helioshr_audit.db[/dim]")


if __name__ == "__main__":
    run()
