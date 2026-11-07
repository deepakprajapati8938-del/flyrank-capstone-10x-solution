from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

# -------------------------------------------------------------
# User & Auth Schemas (Concept 3)
# -------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="Plaintext password")
    role: Optional[str] = Field(default="engineer", description="Role: 'admin' | 'engineer'")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

class UserLoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: str

# -------------------------------------------------------------
# Incident & Ingestion Schemas (Concept 1 & 2)
# -------------------------------------------------------------

class IncidentIngestRequest(BaseModel):
    service_name: str = Field(..., min_length=2, description="Target backend service name (e.g. auth-service)")
    error_message: str = Field(..., min_length=5, description="High-level exception or error message")
    stack_trace: str = Field(..., min_length=10, description="Raw stack trace or error log dump")
    severity: Optional[str] = Field(default="high", pattern="^(critical|high|medium|low)$")

class IncidentResponse(BaseModel):
    id: str
    service_name: str
    error_message: str
    stack_trace: str
    severity: str
    status: str # "pending_triage" | "triaged" | "resolved"
    triage_summary: Optional[str] = None
    root_cause: Optional[str] = None
    ingested_at: str
    resolved_at: Optional[str] = None

# -------------------------------------------------------------
# AI Triage & Runbook Schemas (Concept 7)
# -------------------------------------------------------------

class MitigationStep(BaseModel):
    step_number: int
    action: str
    command_or_fix: Optional[str] = None

class IncidentTriageAnalysis(BaseModel):
    root_cause_hypothesis: str = Field(..., min_length=10)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    severity_assessment: str
    mitigation_steps: List[MitigationStep]
    matched_runbook_id: Optional[str] = None
    from_cache: bool = False

# -------------------------------------------------------------
# Executive Report Schemas (Concept 5)
# -------------------------------------------------------------

class IncidentReportResponse(BaseModel):
    id: str
    incident_id: str
    title: str
    executive_summary: str
    root_cause: str
    mttr_minutes: int
    mitigation_steps: List[Dict[str, Any]]
    html_url: str
    generated_at: str

# -------------------------------------------------------------
# AI Cost Audit Schemas
# -------------------------------------------------------------

class CostLogEntry(BaseModel):
    id: int
    timestamp: str
    operation: str
    model: str
    input_units: int
    output_units: int
    cost_usd: float

class CostSummaryResponse(BaseModel):
    total_calls: int
    total_cost_usd: float
    by_operation: Dict[str, Any]
    recent_logs: List[CostLogEntry]
