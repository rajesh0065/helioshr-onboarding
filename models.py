from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum


class Department(str, Enum):
    ENGINEERING = "Engineering"
    SALES = "Sales"
    MARKETING = "Marketing"
    HR = "HR"
    FINANCE = "Finance"
    PRODUCT = "Product"
    DESIGN = "Design"
    LEGAL = "Legal"
    OPERATIONS = "Operations"


class NewHireEvent(BaseModel):
    employee_id: str
    full_name: str
    email: str
    department: Department
    title: str
    manager_email: str
    start_date: str
    location: str
    employment_type: str = "full-time"


class ProvisioningDecision(BaseModel):
    action: str           # "provision" | "hold_for_review" | "reject"
    reason: str
    systems: list[str]    # which systems to provision
    groups: list[str]     # Okta groups / Slack channels to assign
    flags: list[str]      # any warnings the reviewer should see


class SystemResult(BaseModel):
    system: str
    success: bool
    attempts: int
    message: str
    resource_id: Optional[str] = None


class ProvisioningResult(BaseModel):
    employee_id: str
    employee_name: str
    decision: str
    overall_success: bool
    system_results: list[SystemResult]
    idempotency_key: str
