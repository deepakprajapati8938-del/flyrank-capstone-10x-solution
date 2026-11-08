# BUILD LOG & TECHNICAL DEFENSE: INCIDENTPULSE (YOUR 10X SOLUTION)

**Candidate:** Deepak Prajapati  
**Track:** Backend Track · FlyRank AI Internship  
**Project:** `flyrank-capstone-10x-solution`  
**Solution Title:** IncidentPulse — Autonomous API Incident Triage & Post-Mortem Engine  

---

## 1. AI Transparency & Authorship Disclosure

In compliance with the FlyRank AI Capstone transparency guidelines:
- **AI Pairing Assistant:** Claude 3.5 Sonnet / Antigravity AI
- **Human Role:** System architecture, 10x problem definition, schema design, security threat modeling, benchmark criteria, debugging SQLite concurrency on Windows, test design, and code defense.
- **AI Role:** Boilerplate scaffolding, test case expansion, HTML post-mortem styling, and syntax verification.

### Prompt Log & Design Iterations

1. **Architecture Formulation Prompt:**
   > *"We need to build 'Your 10x Solution' for the FlyRank Backend Track capstone. What is an acute operational backend problem that takes 45-60 minutes today that can be transformed into a 15-second sub-$0.002 automated pipeline using at least 5 program concepts?"*
   > **Design Outcome:** Selected **Incident Triage & Post-Mortem Generation (IncidentPulse)**. SREs spend 45–60 mins reading stack traces, correlating runbooks, and typing Google Docs post-mortems. IncidentPulse ingests alerts in <15ms, triggers an asynchronous triage worker, consults a deterministic TTL cache, executes narrow LLM root-cause synthesis against a runbook catalog, logs micro-costs, and outputs a printable HTML post-mortem.

2. **Database Concurrency & Locking Mitigation:**
   > *"On Windows with SQLite, background workers and HTTP threads can hit database locks when opening nested connections inside transactions."*
   > **Engineering Fix:** Implemented WAL journal mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`) and refactored `app/jobs.py` and `app/main.py` so that queries and writes never hold overlapping connection contexts.

3. **Deterministic Error Caching:**
   > *"How do we prevent duplicate alerts from wasting LLM tokens and latency?"*
   > **Engineering Fix:** Implemented `compute_error_signature` in `app/cache.py`, stripping volatile memory addresses (e.g. `0x7ffee1...`) and timestamps before SHA-256 hashing. Repeated identical incidents hit the cache with 0ms compute and $0 LLM cost.

---

## 2. Line-by-Line Technical Defense

### A. Why SQLite WAL Mode Instead of Standard Rollback Journal?
Standard SQLite locks the entire database file during write transactions, preventing concurrent readers. By configuring `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;`, SQLite permits multiple concurrent readers while a write transaction appends to the write-ahead log (`.db-wal`). This allows the HTTP ingestion endpoint (`POST /api/incidents/ingest`) to return in `< 20ms` even while the background queue worker is actively updating triage records.

### B. Why Decouple Alert Ingestion from LLM Triage?
Calling an LLM or running semantic search directly inside an HTTP alert webhook violates API reliability principles:
1. LLM latency ranges from 800ms to 4000ms, which risks client timeout errors (e.g. from PagerDuty or Datadog webhooks).
2. Rate limits on AI providers would cause alert drop-offs during outage storms.
By returning `HTTP 202 Accepted` immediately upon writing the alert to the `incidents` table (with status `pending_triage`), ingestion takes `< 15ms`. The background worker (`/api/jobs/triage-worker`) drains the queue safely and independently off the critical request path.

### C. Why SHA-256 Error Signature Caching?
During a real incident, an application often throws hundreds of identical exceptions (e.g. `ConnectionPoolTimeoutException`) across multiple worker instances. Sending all 500 identical exceptions to an LLM wastes dollars and risks quota exhaustion. `compute_error_signature` normalizes out dynamic timestamps and pointer addresses, hashing the stable service name and core error message. On the first incident, the LLM runs and costs \$0.000039; the next 499 incidents are served from the cache at \$0 cost and sub-millisecond retrieval.

### D. Why Salted PBKDF2-HMAC-SHA256 with Constant-Time Verification?
Storing plain MD5 or SHA-256 hashes exposes user credentials to rainbow table attacks. We use Python standard library's `hashlib.pbkdf2_hmac("sha256", ...)` with 100,000 iterations and a cryptographically secure 16-byte random salt (`os.urandom(16).hex()`). Password comparisons use `hmac.compare_digest` to prevent timing side-channel attacks.

### E. Why Standalone Printable HTML Instead of Heavy PDF Dependencies?
Heavy PDF rendering engines (like WeasyPrint or wkhtmltopdf) require external C libraries (GTK, cairo, pango) that break across different developer machines and violate the $0 zero-friction setup rule. IncidentPulse generates self-contained, CSS-styled HTML with `@media print` rules. Any engineer can view it in their browser (`/api/incidents/{id}/report.html`) and print or save directly to PDF with pixel-perfect executive styling.

---

## 3. Engineering Workload & Milestone Log

| Phase | Hours | Focus Area | Deliverable |
|---|---|---|---|
| **Phase 1: Architecture & Design** | 2.5h | Problem scoping, 10x claim formulation, concept selection, schema design | `DESIGN.md`, `My 10x Solution - Deepak Prajapati.md` |
| **Phase 2: Core Skeleton & Auth** | 3.0h | FastAPI app, SQLite WAL initialization, PBKDF2 hashing, JWT & RBAC | `app/database.py`, `app/auth.py`, `app/models.py` |
| **Phase 3: Worker & Caching** | 3.5h | Background queue worker, deterministic SHA-256 caching, error normalization | `app/jobs.py`, `app/cache.py` |
| **Phase 4: LLM & Reporting** | 3.5h | Runbook correlation, Pydantic validation, micro-cost ledger, HTML post-mortem | `app/llm_triage.py`, `app/reporting.py`, `app/main.py` |
| **Phase 5: Verification & Harness** | 2.5h | Seed script, automated acceptance probes, pytest suite, test evidence | `seed.py`, `run_probes.py`, `tests/`, `EVIDENCE.md` |
| **Total Workload** | **15.0h** | Fully built, end-to-end verified 10x solution | **100% Complete** |

