# DESIGN.md — IncidentPulse: Autonomous API Incident Triage & Post-Mortem Engine

**Project**: `flyrank-capstone-10x-solution`  
**Author**: Deepak Prajapati (Backend Track)  
**Status**: Approved (Milestone 1 Complete)  

---

## 1. Problem Statement
When production backend APIs experience outages or elevated error rates, on-call site reliability engineers (SREs) are inundated with cryptic stack traces, log dumps, and fragmented metrics across disconnected monitoring tools. SREs spend 45 to 60 minutes manually cross-referencing internal runbooks, correlating error spikes, deducing root causes, and drafting executive post-mortem reports. This manual delay inflates Mean Time to Resolution (MTTR), burns out engineering teams, and leaves stakeholders uninformed during critical downtime.

### Who Has This Problem:
Backend engineering teams, DevOps/SREs, and technical leaders responsible for maintaining 99.9% SLA web services and reporting incident post-mortems to leadership.

---

## 2. The 10x Claim
**IncidentPulse transforms a 45–60 minute manual incident triage and post-mortem drafting marathon into an automated 15-second background pipeline (over 10x faster) at under $0.002 per incident.**

It automatically ingests raw error alerts, normalizes stack traces, correlates them against historical runbooks, generates deterministic root-cause hypotheses via a cost-tracked AI worker, caches diagnostic signatures, and compiles an executive post-mortem report (HTML/PDF) ready for stakeholders.

---

## 3. The 5+ Program Concepts Implemented

IncidentPulse implements **6 Core Program Concepts** (exceeding the required 5, with 0 swaps needed):

| # | Program Concept | Implementation in IncidentPulse | File Location |
| :-: | :--- | :--- | :--- |
| **1** | **API Endpoints** | FastAPI REST endpoints with strict Pydantic v2 schemas and standard HTTP status codes (`200`, `201`, `400`, `401`, `403`, `422`, `429`). | [`app/main.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/main.py) |
| **2** | **Database (Persistence)** | SQLite relational schema with migrations, WAL mode, foreign keys, and indexes surviving system restarts. | [`app/database.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/database.py) |
| **3** | **Authentication** | JWT Bearer token authentication with SHA-256 password hashing and role-based permissions (`admin` vs `engineer`). | [`app/auth.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/auth.py) |
| **4** | **Background Jobs / Queues** | Asynchronous triage worker taking slow AI root-cause analysis off the HTTP ingestion path with retry tracking. | [`app/jobs.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/jobs.py) |
| **5** | **Reporting (PDF / Email)** | Automated generation of styled Executive Incident Post-Mortem reports with MTTR metrics, timeline, and mitigation steps. | [`app/reporting.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/reporting.py) |
| **6** | **Caching Logic** | TTL cache storing expensive root-cause inference signatures to instantly resolve repeated error spikes without duplicate AI calls. | [`app/cache.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/cache.py) |
| **7** | **LLM Integration (Narrow Task)**| AI root-cause analysis engine with strict Pydantic schema validation, hallucination guardrails, and per-call micro-cost tracking. | [`app/llm_triage.py`](file:///x:/Medicaps/Internship/flyrank-capstone-10x-solution/app/llm_triage.py) |

---

## 4. Architecture Overview

```
 [ Client / Monitoring Alert ]
               │
               ▼
   POST /api/incidents/ingest
   (Pydantic Boundary Validation)
               │
               ├─► [ Authenticate JWT Token ]
               │
               ▼
 ┌───────────────────────────┐
 │   SQLite `incidents`      │ ──► [ Returns 202 Accepted in < 15ms ]
 │   Status: 'pending_triage'│
 └─────────────┬─────────────┘
               │
      (Background Job Worker)
               │
               ▼
 ┌───────────────────────────┐
 │  TTL Cache Signature Check│
 └─────────────┬─────────────┘
      ├── Hit  ──► Instant Diagnosis (0ms AI Cost)
      └── Miss
           │
           ▼
 ┌───────────────────────────┐
 │ LLM Root-Cause Analysis   │
 │ - Correlates with Runbooks│
 │ - Pydantic Output Schema  │
 │ - Per-call Cost Audit Log │
 └─────────────┬─────────────┘
               │
               ▼
 ┌───────────────────────────┐
 │ Executive Post-Mortem     │
 │ Report Engine (HTML/PDF)  │ ──► GET /api/incidents/{id}/report
 └───────────────────────────┘
```

---

## 5. Explicit Non-Goal
**What IncidentPulse will NOT build:**
- Not an APM agent monitoring server CPU/RAM metrics in real time.
- Not an SMS/PagerDuty on-call escalation paging network.
- Focus is strictly on post-incident ingestion, root-cause diagnosis, caching, and executive post-mortem reporting.

